"""Running RUMIN on Vercel (a test deployment, docs/deployment-vercel.md): the settings it is
given there, the answer without a database, the forwarded headers it trusts there, and the
database preparation its build runs."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, REPO_ROOT, Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.deploy import bootstrap
from app.deploy.vercel import (
    DATABASE_VARIABLES,
    NOT_CONFIGURED,
    not_configured,
    prepare_environment,
)
from app.main import create_app
from app.models import Dataset, EconomicSeries, GraphBuild
from app.models.auth import AuditEvent, User
from tests.conftest import make_settings

NEON = "postgres://user:secret@ep-example.ap-south-1.aws.neon.tech/neondb?sslmode=require"


# --- The settings Vercel gets --------------------------------------------------------------


def test_the_direct_database_connection_is_preferred_and_set_settings_win() -> None:
    environ = {
        "DATABASE_URL": "postgres://user:secret@pooled.example/neondb",
        "DATABASE_URL_UNPOOLED": "postgres://user:secret@direct.example/neondb",
        "RUMIN_LOG_FORMAT": "text",
    }
    assert prepare_environment(environ) is True
    assert environ["RUMIN_DATABASE_URL"] == "postgres://user:secret@direct.example/neondb"
    assert environ["RUMIN_LOG_FORMAT"] == "text"  # the project's own choice
    assert environ["RUMIN_ENVIRONMENT"] == "production"
    assert environ["RUMIN_SCENARIO_EXECUTION_MODE"] == "inline"
    assert environ["RUMIN_ANALYST_EXECUTION_MODE"] == "inline"
    assert environ["RUMIN_TRUST_FORWARDED_HEADERS"] == "true"


def test_an_explicit_database_url_is_kept() -> None:
    environ = {"RUMIN_DATABASE_URL": "postgresql+psycopg://a:b@chosen/db", "DATABASE_URL": NEON}
    assert prepare_environment(environ) is True
    assert environ["RUMIN_DATABASE_URL"] == "postgresql+psycopg://a:b@chosen/db"


def test_without_a_database_nothing_is_invented() -> None:
    environ: dict[str, str] = {}
    assert prepare_environment(environ) is False
    assert "RUMIN_DATABASE_URL" not in environ


def test_the_settings_vercel_gets_are_a_safe_production_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environ = {"DATABASE_URL_UNPOOLED": NEON}
    prepare_environment(environ)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.environment == "production"  # it would refuse to start otherwise
    assert settings.database_url == NEON.replace("postgres://", "postgresql+psycopg://", 1)
    assert settings.cors_origins == []
    assert settings.docs_enabled is False and settings.cookie_secure is True
    assert settings.session_cookie_name == "__Host-rumin_session"
    assert settings.trust_forwarded_headers is True
    assert settings.scenario_execution_mode == settings.analyst_execution_mode == "inline"
    # An Analyst turn ends well within the function's time limit (60 s).
    assert settings.analyst_deadline_seconds == 45


@pytest.mark.parametrize(
    ("given", "used"),
    [
        ("postgres://a:b@host/db", "postgresql+psycopg://a:b@host/db"),
        (
            "postgresql://a:b@host/db?sslmode=require",
            "postgresql+psycopg://a:b@host/db?sslmode=require",
        ),
        ("postgresql+psycopg://a:b@host/db", "postgresql+psycopg://a:b@host/db"),
        ("sqlite:///rumin.db", "sqlite:///rumin.db"),
    ],
)
def test_postgresql_urls_as_providers_give_them_use_psycopg(given: str, used: str) -> None:
    assert Settings(_env_file=None, database_url=given).database_url == used


def test_vercel_routes_the_api_and_sends_the_web_servers_protections() -> None:
    config = json.loads((REPO_ROOT / "vercel.json").read_text())
    routes = {rule["source"]: rule["destination"] for rule in config["rewrites"]}
    for source in ("/api/(.*)", "/health", "/health/ready"):
        assert routes[source] == {"service": "api"}
    assert list(routes)[-1] == "/(.*)" and routes["/(.*)"] == {"service": "web"}
    assert config["services"]["api"]["entrypoint"] == "app.deploy.vercel_app:app"

    nginx = (REPO_ROOT / "frontend" / "nginx" / "snippets" / "security-headers.conf").read_text()
    wanted = dict(re.findall(r'add_header ([A-Za-z-]+) "([^"]+)" always;', nginx))
    # Vercel sends its own Strict-Transport-Security, longer, on every response.
    del wanted["Strict-Transport-Security"]
    sent = {
        header["key"]: header["value"]
        for rule in config["headers"]
        if rule["source"] == "/(.*)"
        for header in rule["headers"]
    }
    assert sent == wanted


# --- Without a database ----------------------------------------------------------------------


def test_without_a_database_every_request_is_told_what_is_missing() -> None:
    client = TestClient(not_configured())
    for response in (
        client.get("/api/v1/network"),
        client.post("/api/v1/auth/login", json={}),
        client.get("/health/ready"),
    ):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_configured"
        assert response.json()["error"]["message"] == NOT_CONFIGURED
        assert response.headers["cache-control"] == "no-store"
    assert "Storage tab" in NOT_CONFIGURED


def _entrypoint(environ: dict[str, str]) -> str:
    """What Vercel's entrypoint serves, imported in a separate process (it prepares the
    environment it runs in)."""
    clean = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("RUMIN_") and name not in DATABASE_VARIABLES
    }
    script = (
        "import app.deploy.vercel_app as m; "
        "settings = getattr(m.app.state, 'settings', None); "
        "print(m.app.title, '|', getattr(settings, 'environment', None))"
    )
    result = subprocess.run(  # noqa: S603 - this interpreter, importing the entrypoint
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env={**clean, **environ},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return result.stdout.strip()


def test_the_vercel_entrypoint_serves_rumin_once_a_database_is_configured() -> None:
    assert _entrypoint({}) == "FastAPI | None"  # the explanation, not RUMIN
    # No connection is made at start: the unreachable database is only named.
    assert _entrypoint({"DATABASE_URL_UNPOOLED": NEON}) == "RUMIN API | production"


def _top_level_names(module: ast.Module) -> set[str]:
    names: set[str] = set()
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            names |= {target.id for target in statement.targets if isinstance(target, ast.Name)}
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            names.add(statement.target.id)
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            names |= {alias.asname or alias.name for alias in statement.names}
        elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(statement.name)
    return names


def test_the_vercel_entrypoint_defines_its_handler_at_the_top_level() -> None:
    """Vercel's build looks for the handler among the module's own statements, not inside an
    ``if``, and fails without it (a first deployment did)."""
    config = json.loads((REPO_ROOT / "vercel.json").read_text())
    module, handler = config["services"]["api"]["entrypoint"].split(":")
    path = BACKEND_DIR.joinpath(*module.split(".")).with_suffix(".py")
    assert handler in _top_level_names(ast.parse(path.read_text()))
    assert "app" not in _top_level_names(ast.parse("if True:\n    app = None\n"))


# --- Forwarded headers -----------------------------------------------------------------------


def _failed_sign_in(client: TestClient, session_factory: sessionmaker[Session]) -> str | None:
    email = f"nobody-{uuid.uuid4().hex[:8]}@rumin.test"
    client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "not the password at all"},
        headers={"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"},
    )
    with session_factory() as session:
        event = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event == "login_failed")
            .order_by(AuditEvent.occurred_at.desc())
            .limit(1)
        ).one()
        return event.client


def test_forwarded_headers_are_trusted_only_where_configured(
    database_url: str, engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    del engine
    trusted = TestClient(
        create_app(make_settings(database_url, cors_origins=[], trust_forwarded_headers=True))
    )
    plain = TestClient(create_app(make_settings(database_url, cors_origins=[])))

    # The platform's address, not the connection's, is the one limits and the audit use.
    assert _failed_sign_in(trusted, session_factory) == "203.0.113.7"
    assert _failed_sign_in(plain, session_factory) == "testclient"

    # A page served over https posts with an https Origin: the scheme comes from the platform.
    change = {
        "json": {"email": "nobody@rumin.test", "password": "not the password"},
        "headers": {"Origin": "https://testserver", "X-Forwarded-Proto": "https"},
    }
    assert trusted.post("/api/v1/auth/login", **change).status_code == 401  # type: ignore[arg-type]
    assert plain.post("/api/v1/auth/login", **change).status_code == 403  # type: ignore[arg-type]


# --- Preparing the database ------------------------------------------------------------------


@pytest.fixture
def fresh_database(
    tmp_path: os.PathLike[str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker[Session]]:
    url = f"sqlite:///{tmp_path}/fresh.db"
    monkeypatch.setenv("RUMIN_DATABASE_URL", url)
    get_settings.cache_clear()
    engine = create_db_engine(url)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_a_fresh_database_is_prepared_once_and_left_alone_after(
    fresh_database: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    administrator = {
        "RUMIN_BOOTSTRAP_ADMIN_EMAIL": "First.Admin@rumin.test",
        "RUMIN_BOOTSTRAP_ADMIN_NAME": "First Administrator",
        "RUMIN_BOOTSTRAP_ADMIN_PASSWORD": "a temporary bootstrap phrase",
    }

    assert bootstrap.main([], environ={}, configure_logging=False) == 0
    assert "No administrator yet" in capsys.readouterr().out

    assert bootstrap.main([], environ=administrator, configure_logging=False) == 0
    second = capsys.readouterr().out
    assert "Created the administrator first.admin@rumin.test" in second
    assert "up to date with its sources" in second

    assert bootstrap.main([], environ=administrator, configure_logging=False) == 0
    assert "1 active administrator(s): none created." in capsys.readouterr().out

    with fresh_database() as session:
        assert session.scalar(select(func.count()).select_from(GraphBuild)) == 1
        assert (session.scalar(select(func.count()).select_from(Dataset)) or 0) >= 1
        assert session.scalar(select(func.count()).select_from(EconomicSeries)) == 11
        admin = session.scalars(select(User)).one()
        assert (admin.email, admin.role, admin.must_change_password) == (
            "first.admin@rumin.test",
            "admin",
            True,
        )


def test_a_weak_bootstrap_password_stops_the_build(
    fresh_database: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    del fresh_database
    weak = {
        "RUMIN_BOOTSTRAP_ADMIN_EMAIL": "admin@rumin.test",
        "RUMIN_BOOTSTRAP_ADMIN_PASSWORD": "short",
    }
    assert bootstrap.main([], environ=weak, configure_logging=False) == 1
    assert "could not be created" in capsys.readouterr().err


def test_two_deployments_cannot_prepare_one_database_at_once(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("advisory locks are PostgreSQL's; SQLite has one writer anyway")
    probe = text("SELECT pg_try_advisory_lock(:key)")
    with bootstrap.exclusive(engine), engine.connect() as other:
        assert other.execute(probe, {"key": bootstrap.LOCK_KEY}).scalar() is False
    with engine.connect() as other:
        assert other.execute(probe, {"key": bootstrap.LOCK_KEY}).scalar() is True
        other.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": bootstrap.LOCK_KEY})
