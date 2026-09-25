"""Accounts, sessions, roles and ownership (Phase 10).

Every figure is HYPOTHETICAL; every password is for this disposable database only.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.auth import passwords
from app.auth.__main__ import main as cli
from app.core.config import Settings
from app.db.base import utcnow
from app.main import create_app
from app.models import (
    AnalystSession,
    AuditEvent,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
    User,
    UserSession,
)
from tests.conftest import (
    ALLOWED_ORIGIN,
    COOKIE,
    TEST_ADMIN_EMAIL,
    TEST_PASSWORD,
    make_settings,
    session_token,
    wipe_analyst,
    wipe_scenarios,
)
from tests.scenario_support import reference

API = "/api/v1"


@pytest.fixture
def accounts(session_factory: sessionmaker[Session]) -> Iterator[None]:
    """People created by a test are removed afterwards (the suite's administrator stays)."""
    yield
    with session_factory() as session:
        wipe_analyst(session)
        wipe_scenarios(session)
        # Runs a test made on its own (the Simulation page's kind) go too.
        standalone = select(SimulationRun.id).where(SimulationRun.owner_id.is_not(None))
        session.execute(
            delete(SimulationSensitivityAnalysis).where(
                SimulationSensitivityAnalysis.run_id.in_(standalone)
            )
        )
        session.execute(delete(SimulationRunStep).where(SimulationRunStep.run_id.in_(standalone)))
        session.execute(delete(SimulationRun).where(SimulationRun.owner_id.is_not(None)))
        others = select(User.id).where(User.email != TEST_ADMIN_EMAIL)
        session.execute(delete(UserSession).where(UserSession.user_id.in_(others)))
        session.execute(delete(AuditEvent))
        session.execute(delete(User).where(User.email != TEST_ADMIN_EMAIL))
        session.execute(
            update(User)
            .where(User.email == TEST_ADMIN_EMAIL)
            .values(role="admin", is_active=True, failed_logins=0, locked_until=None)
        )
        session.commit()


def email(role: str) -> str:
    return f"{role}-{uuid.uuid4().hex[:8]}@rumin.test"


def as_person(
    client: TestClient, session_factory: sessionmaker[Session], role: str, **user: Any
) -> str:
    """Sign ``client`` in as a new person with ``role``; returns their e-mail."""
    address = email(role)
    client.cookies.set(COOKIE, session_token(session_factory, address, role=role, **user))
    return address


def login(client: TestClient, address: str, password: str = TEST_PASSWORD) -> Any:
    return client.post(f"{API}/auth/login", json={"email": address, "password": password})


# --- Signing in ----------------------------------------------------------------------------------


def test_every_route_but_signing_in_needs_a_session(app: FastAPI) -> None:
    anonymous = TestClient(app)
    for method, path in [
        ("GET", "/entities"),
        ("GET", "/network"),
        ("GET", "/scenarios"),
        ("POST", "/scenarios"),
        ("GET", "/system"),
        ("GET", "/graph/overview"),
        ("GET", f"/scenario-executions/{uuid.uuid4()}/results"),
        ("GET", "/analyst/sessions"),
        ("GET", "/users"),
        ("GET", "/auth/session"),
    ]:
        response = anonymous.request(method, f"{API}{path}", json={})
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"]["code"] == "unauthorized"
    # Health checks answer without a session; they reveal nothing about the data.
    assert anonymous.get("/health").status_code == 200


def test_every_api_route_is_protected_except_signing_in(app: FastAPI) -> None:
    anonymous = TestClient(app)
    public = {"/api/v1/auth/login", "/api/v1/auth/logout"}
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/") or path in public:
            continue
        concrete = path.replace("{", "").replace("}", "")
        for method in operations:
            response = anonymous.request(method.upper(), concrete, json={})
            assert response.status_code == 401, (method, path, response.status_code)
            checked += 1
    assert checked > 80


def test_signing_in_sets_an_httponly_cookie_and_never_returns_the_token(
    app: FastAPI, session_factory: sessionmaker[Session], accounts: None
) -> None:
    address = email("analyst")
    with session_factory() as session:
        from tests.conftest import ensure_user

        ensure_user(session, address, role="analyst", name="Ana Rao")
    client = TestClient(app)

    response = login(client, address.upper())  # e-mail compared case-insensitively

    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Max-Age" not in cookie and "expires" not in cookie.lower()  # a browser session
    token = cookie.split(";")[0].split("=", 1)[1]
    assert token not in response.text
    body = response.json()
    assert body["user"]["email"] == address and body["permissions"] == ["read", "write"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get(f"{API}/auth/session").json()["user"]["name"] == "Ana Rao"
    assert client.get(f"{API}/entities").status_code == 200
    with session_factory() as session:
        stored = session.scalars(select(UserSession.token_hash)).all()
    assert token not in stored  # only its hash is kept


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(
    app: FastAPI, session_factory: sessionmaker[Session], accounts: None
) -> None:
    address = email("viewer")
    with session_factory() as session:
        from tests.conftest import ensure_user

        ensure_user(session, address, role="viewer")
    client = TestClient(app)

    wrong = login(client, address, "not the password at all")
    unknown = login(client, email("nobody"), "not the password at all")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert "set-cookie" not in wrong.headers


def test_repeated_failures_lock_the_account_and_are_audited(
    app: FastAPI, session_factory: sessionmaker[Session], accounts: None
) -> None:
    address = email("analyst")
    with session_factory() as session:
        from tests.conftest import ensure_user

        ensure_user(session, address, role="analyst")
    client = TestClient(app)

    for _ in range(5):
        assert login(client, address, "a wrong password again").status_code == 401
    locked = login(client, address)  # even the right password must wait

    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) >= 1
    with session_factory() as session:
        events = [row.event for row in session.scalars(select(AuditEvent))]
        recorded = json.dumps([row.detail for row in session.scalars(select(AuditEvent))])
    assert events.count("login_failed") == 5 and "login_throttled" in events
    assert TEST_PASSWORD not in recorded and "a wrong password" not in recorded


def test_a_client_that_keeps_failing_must_wait(
    database_url: str, session_factory: sessionmaker[Session], accounts: None
) -> None:
    app = create_app(make_settings(database_url, login_client_max_failures=5))
    client = TestClient(app)

    for _ in range(5):
        assert login(client, email("nobody"), "whatever it may be").status_code == 401
    waited = login(client, TEST_ADMIN_EMAIL)

    assert waited.status_code == 429 and waited.headers["retry-after"]


def test_sessions_end_when_idle_expired_revoked_or_the_account_is_deactivated(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    def fresh() -> tuple[str, uuid.UUID]:
        address = as_person(client, session_factory, "viewer")
        with session_factory() as session:
            user = session.scalar(select(User).where(User.email == address))
            assert user is not None
            return address, user.id

    for change in (
        {"last_seen_at": utcnow() - timedelta(hours=3)},  # idle beyond two hours
        {"expires_at": utcnow() - timedelta(seconds=1)},  # past its maximum age
        {"revoked_at": utcnow()},
    ):
        _, user_id = fresh()
        assert client.get(f"{API}/entities").status_code == 200
        with session_factory() as session:
            session.execute(
                update(UserSession).where(UserSession.user_id == user_id).values(**change)
            )
            session.commit()
        ended = client.get(f"{API}/entities")
        assert ended.status_code == 401, change
        assert ended.json()["error"]["message"] == "Your session has ended. Sign in again."

    _, user_id = fresh()
    with session_factory() as session:
        session.execute(update(User).where(User.id == user_id).values(is_active=False))
        session.commit()
    assert client.get(f"{API}/entities").status_code == 401


def test_signing_out_ends_the_session_and_clears_the_cookie(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    as_person(client, session_factory, "analyst")
    token = client.cookies.get(COOKIE)

    response = client.post(f"{API}/auth/logout")

    assert response.status_code == 204
    assert (
        f'{COOKIE}=""' in response.headers["set-cookie"]
        or "Max-Age=0" in response.headers["set-cookie"]
    )
    client.cookies.set(COOKIE, token or "")
    assert client.get(f"{API}/entities").status_code == 401
    assert client.post(f"{API}/auth/logout").status_code == 204  # idempotent


# --- Passwords -----------------------------------------------------------------------------------


def test_the_password_policy() -> None:
    assert passwords.password_problems("a long enough phrase") == []
    assert passwords.password_problems("short") == ["Use at least 12 characters."]
    assert "This password is too common; choose another." in passwords.password_problems(
        "Password1234"
    )
    assert passwords.password_problems("ana@example.com", email="ana@example.com")
    assert passwords.password_problems("anaraoanarao", name="AnaRao AnaRao".replace(" ", " "))
    assert passwords.password_problems("aaaaaaaaaaaaaaab")  # three characters or fewer
    assert passwords.password_problems(" padded password ")
    hashed = passwords.hash_password("a long enough phrase")
    assert hashed.startswith("$argon2id$")
    assert passwords.verify_password(hashed, "a long enough phrase")
    assert not passwords.verify_password(hashed, "a long enough phrase ")
    assert not passwords.verify_password("not a hash", "anything at all")


def test_a_temporary_password_must_be_replaced_before_anything_else(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    address = as_person(client, session_factory, "analyst", must_change_password=True)
    other = TestClient(client.app)
    other.cookies.set(COOKIE, session_token(session_factory, address))

    blocked = client.get(f"{API}/entities")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert client.get(f"{API}/auth/session").json()["user"]["must_change_password"] is True

    wrong = client.post(
        f"{API}/auth/password",
        json={"current_password": "not the current one", "new_password": "a brand new phrase"},
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["details"][0]["field"] == "current_password"
    weak = client.post(
        f"{API}/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422 and weak.json()["error"]["details"][0]["field"] == "new_password"

    changed = client.post(
        f"{API}/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "a brand new phrase"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False
    assert client.get(f"{API}/entities").status_code == 200
    assert other.get(f"{API}/auth/session").status_code == 401  # other sessions ended
    assert login(TestClient(client.app), address, "a brand new phrase").status_code == 200


# --- Roles and ownership -------------------------------------------------------------------------


def test_a_viewer_reads_the_workspace_but_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    as_person(client, session_factory, "viewer")

    assert client.get(f"{API}/scenarios").status_code == 200
    refused = client.post(f"{API}/scenarios", json=reference())
    assert refused.status_code == 403
    assert "analyst role" in refused.json()["error"]["message"]
    assert client.post(f"{API}/simulations", json={"model_id": "fx_exposure"}).status_code == 403
    stored = client.post(f"{API}/intelligence/analyses", json={"scope": "workspace"})
    assert stored.status_code == 403
    # Planning and previewing store nothing, so a viewer may explore.
    assert client.post(f"{API}/scenarios/plan", json=reference()).status_code == 200
    # The Analyst is for everyone; its conversations are the viewer's own.
    assert client.post(f"{API}/analyst/sessions", json={}).status_code == 201
    assert client.get(f"{API}/users").status_code == 403


def test_only_the_owner_or_an_administrator_changes_a_scenario(
    built_graph: Session,
    client: TestClient,
    session_factory: sessionmaker[Session],
    admin_token: str,
    accounts: None,
) -> None:
    owner = as_person(client, session_factory, "analyst", name="Owner One")
    created = client.post(f"{API}/scenarios", json=reference())
    assert created.status_code == 201, created.text
    scenario = created.json()
    assert scenario["owner"]["name"] == "Owner One"
    scenario_id = scenario["id"]

    as_person(client, session_factory, "analyst", name="Someone Else")
    assert client.get(f"{API}/scenarios/{scenario_id}").status_code == 200  # shared reading
    for method, path, body in [
        ("PUT", f"/scenarios/{scenario_id}", {**reference(), "name": "Changed"}),
        ("DELETE", f"/scenarios/{scenario_id}", None),
        ("POST", f"/scenarios/{scenario_id}/versions/1/restore", None),
        ("POST", f"/scenarios/{scenario_id}/executions", {}),
    ]:
        response = client.request(method, f"{API}{path}", json=body)
        assert response.status_code == 403, (method, path, response.text)
        assert "Duplicate it" in response.json()["error"]["message"]
    copy = client.post(f"{API}/scenarios/{scenario_id}/duplicate", json={})
    assert copy.status_code == 201 and copy.json()["owner"]["name"] == "Someone Else"

    client.cookies.set(COOKIE, session_token(session_factory, owner))
    executed = client.post(f"{API}/scenarios/{scenario_id}/executions", json={})
    assert executed.status_code == 202, executed.text
    execution_id = executed.json()["id"]

    as_person(client, session_factory, "analyst")
    for path, body in [
        (f"/scenario-executions/{execution_id}/cancel", None),
        (f"/scenario-executions/{execution_id}/sensitivity", {"metric": None, "inputs": []}),
        (
            f"/scenario-executions/{execution_id}/analyses",
            {
                "kind": "joint_sensitivity",
                "rows": {"target": "change:var_brent_crude"},
                "columns": {"target": "change:var_usd_inr"},
            },
        ),
    ]:
        assert client.post(f"{API}{path}", json=body).status_code == 403, path
    # Checking that an execution reproduces changes nothing: anyone may.
    assert client.post(f"{API}/scenario-executions/{execution_id}/verify").status_code == 200

    client.cookies.set(COOKIE, admin_token)
    assert (
        client.post(
            f"{API}/scenario-executions/{execution_id}/sensitivity",
            json={"metric": None, "inputs": []},
        ).status_code
        == 201
    )


def test_a_run_belongs_to_whoever_ran_it(
    built_graph: Session, client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    from tests.simulation_support import BASE

    as_person(client, session_factory, "analyst")
    run = client.post(f"{API}/simulations", json={"model_id": "airline_fuel_cost", "inputs": BASE})
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    as_person(client, session_factory, "analyst")
    assert client.get(f"{API}/simulations/{run_id}").status_code == 200
    assert client.post(f"{API}/simulations/{run_id}/sensitivity", json={}).status_code == 403
    assert client.post(f"{API}/simulations/{run_id}/verify").status_code == 200


def test_conversations_are_private_even_from_administrators(
    client: TestClient, session_factory: sessionmaker[Session], admin_token: str, accounts: None
) -> None:
    as_person(client, session_factory, "viewer")
    mine = client.post(f"{API}/analyst/sessions", json={"title": "Private"}).json()["id"]
    turn = client.post(
        f"{API}/analyst/sessions/{mine}/turns", json={"question": "What is RUMIN?"}
    ).json()["id"]

    for token in (session_token(session_factory, email("analyst"), role="analyst"), admin_token):
        client.cookies.set(COOKIE, token)
        assert mine not in [
            item["id"] for item in client.get(f"{API}/analyst/sessions").json()["items"]
        ]
        for method, path, body in [
            ("GET", f"/analyst/sessions/{mine}", None),
            ("GET", f"/analyst/sessions/{mine}/turns/{turn}", None),
            ("PUT", f"/analyst/sessions/{mine}", {"title": "Mine now"}),
            ("POST", f"/analyst/sessions/{mine}/turns", {"question": "And now?"}),
            ("DELETE", f"/analyst/sessions/{mine}", None),
        ]:
            response = client.request(method, f"{API}{path}", json=body)
            assert response.status_code == 404, (method, path, response.status_code)


def test_conversations_from_before_accounts_are_visible_to_administrators_only(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    with session_factory() as session:
        legacy = AnalystSession(id=uuid.uuid4(), title="Before accounts", focus={})
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id

    assert client.get(f"{API}/analyst/sessions/{legacy_id}").status_code == 200  # administrator
    as_person(client, session_factory, "analyst")
    assert client.get(f"{API}/analyst/sessions/{legacy_id}").status_code == 404


# --- Administration ------------------------------------------------------------------------------


def test_administrators_manage_people_and_every_change_is_audited(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    address = email("new")
    weak = client.post(
        f"{API}/users",
        json={"email": address, "name": "New Person", "role": "viewer", "temporary_password": "x1"},
    )
    assert weak.status_code == 422
    created = client.post(
        f"{API}/users",
        json={
            "email": address,
            "name": "New Person",
            "role": "viewer",
            "temporary_password": "a temporary phrase",
        },
    )
    assert created.status_code == 201, created.text
    person = created.json()
    assert person["must_change_password"] is True and "password" not in json.dumps(
        {key: value for key, value in person.items() if key != "must_change_password"}
    ).replace("password_changed_at", "")
    duplicate = client.post(
        f"{API}/users",
        json={
            "email": address.upper(),
            "name": "Again",
            "role": "viewer",
            "temporary_password": "a temporary phrase",
        },
    )
    assert duplicate.status_code == 409

    their_client = TestClient(client.app)
    assert login(their_client, address, "a temporary phrase").status_code == 200

    promoted = client.put(f"{API}/users/{person['id']}", json={"role": "analyst"})
    assert promoted.json()["role"] == "analyst"
    reset = client.post(
        f"{API}/users/{person['id']}/password", json={"temporary_password": "another temporary one"}
    )
    assert reset.status_code == 200 and reset.json()["must_change_password"] is True
    assert their_client.get(f"{API}/auth/session").status_code == 401  # reset ends sessions
    assert login(their_client, address, "another temporary one").status_code == 200
    assert client.post(f"{API}/users/{person['id']}/sessions/revoke").status_code == 204
    assert their_client.get(f"{API}/auth/session").status_code == 401
    deactivated = client.put(f"{API}/users/{person['id']}", json={"is_active": False})
    assert deactivated.json()["is_active"] is False
    assert login(their_client, address, "another temporary one").status_code == 401

    events = client.get(f"{API}/audit-events").json()["items"]
    names = [item["event"] for item in events]
    for expected in ("user_created", "user_updated", "password_reset", "sessions_revoked"):
        assert expected in names
    dumped = json.dumps(events)
    assert "temporary phrase" not in dumped and "another temporary one" not in dumped


def test_the_last_administrator_cannot_be_removed(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    with session_factory() as session:
        admin = session.scalar(select(User).where(User.email == TEST_ADMIN_EMAIL))
        assert admin is not None
        admin_id = admin.id
        session.execute(
            update(User).where(User.role == "admin", User.id != admin_id).values(is_active=False)
        )
        session.commit()

    for change in ({"role": "analyst"}, {"is_active": False}):
        refused = client.put(f"{API}/users/{admin_id}", json=change)
        assert refused.status_code == 409, change


def test_people_cannot_administer_or_act_as_administrators(
    client: TestClient, session_factory: sessionmaker[Session], accounts: None
) -> None:
    as_person(client, session_factory, "analyst")
    for method, path in [
        ("GET", "/users"),
        ("POST", "/users"),
        ("PUT", f"/users/{uuid.uuid4()}"),
        ("POST", f"/users/{uuid.uuid4()}/password"),
        ("POST", f"/users/{uuid.uuid4()}/sessions/revoke"),
        ("GET", "/audit-events"),
    ]:
        body = {"temporary_password": "whatever it is"} if path.endswith("password") else {}
        assert client.request(method, f"{API}{path}", json=body).status_code == 403, path


# --- Cross-site requests and production settings -------------------------------------------------


def test_cross_site_writes_are_refused(client: TestClient) -> None:
    for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
        refused = client.post(f"{API}/analyst/sessions", json={}, headers=headers)
        assert refused.status_code == 403, headers
        assert refused.json()["error"]["code"] == "forbidden"
        assert client.post(f"{API}/auth/login", json={}, headers=headers).status_code == 403
    # Reading is not a cross-site risk; the allowed origin and the server's own origin write.
    assert (
        client.get(f"{API}/entities", headers={"Origin": "https://evil.example"}).status_code == 200
    )
    for origin in (ALLOWED_ORIGIN, "http://testserver"):
        assert (
            client.post(f"{API}/analyst/sessions", json={}, headers={"Origin": origin}).status_code
            == 201
        )


def test_production_refuses_development_defaults() -> None:
    with pytest.raises(ValidationError) as refused:
        Settings(_env_file=None, environment="production")
    message = str(refused.value)
    assert "PostgreSQL" in message and "local development origins" in message
    with pytest.raises(ValidationError, match="must not be false"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://rumin:x@db/rumin",
            cors_origins=[],
            session_cookie_secure=False,
        )
    with pytest.raises(ValidationError, match="must use https"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://rumin:x@db/rumin",
            cors_origins=["http://rumin.example"],
        )
    production = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://rumin:x@db/rumin",
        cors_origins=[],
    )
    assert production.cookie_secure is True and production.docs_enabled is False


# --- The command line ----------------------------------------------------------------------------


def test_the_command_line_creates_and_manages_accounts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_url: str,
    session_factory: sessionmaker[Session],
    accounts: None,
) -> None:
    import io

    monkeypatch.setenv("RUMIN_DATABASE_URL", database_url)
    from app.core.config import get_settings

    get_settings.cache_clear()
    address = email("cli")
    try:
        monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
        assert (
            cli(
                [
                    "create-user",
                    "--email",
                    address,
                    "--name",
                    "Cli",
                    "--role",
                    "admin",
                    "--password-stdin",
                ]
            )
            == 1
        )
        monkeypatch.setattr("sys.stdin", io.StringIO("a command-line phrase\n"))
        assert (
            cli(
                [
                    "create-user",
                    "--email",
                    address,
                    "--name",
                    "Cli Person",
                    "--role",
                    "admin",
                    "--password-stdin",
                ]
            )
            == 0
        )
        assert cli(["list-users"]) == 0
        assert address in capsys.readouterr().out
        with session_factory() as session:
            user = session.scalar(select(User).where(User.email == address))
            assert user is not None and user.must_change_password is False
        monkeypatch.setattr("sys.stdin", io.StringIO("another command-line phrase\n"))
        assert cli(["set-password", "--email", address, "--password-stdin"]) == 0
        assert cli(["deactivate", "--email", address]) == 0
        assert cli(["revoke-sessions", "--email", "nobody@rumin.test"]) == 1
        assert cli(["prune", "--events-older-than-days", "30"]) == 0
        with session_factory() as session:
            user = session.scalar(select(User).where(User.email == address))
            assert user is not None and user.is_active is False
            assert passwords.verify_password(user.password_hash, "another command-line phrase")
    finally:
        get_settings.cache_clear()
