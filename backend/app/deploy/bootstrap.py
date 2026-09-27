"""Preparing a database for first use (the Vercel build runs it; docs/deployment-vercel.md).

    python -m app.deploy.bootstrap

In order, each step doing nothing when it is already done, so it can run on every
deployment:

1. the migrations, to the latest schema;
2. the illustrative sample dataset, and the series catalogue (definitions only: nothing is
   fetched);
3. the knowledge graph, when none has been built or its sources changed since the latest
   build;
4. the first administrator, when no account is an active administrator: the e-mail address
   in ``RUMIN_BOOTSTRAP_ADMIN_EMAIL``, the name in ``RUMIN_BOOTSTRAP_ADMIN_NAME`` and a
   temporary password in ``RUMIN_BOOTSTRAP_ADMIN_PASSWORD``, which must be replaced at the
   first sign-in.

On PostgreSQL an advisory lock keeps two deployments from preparing the database at once.
Exit codes: 0 done, 1 a step failed (the build should stop).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator, MutableMapping, Sequence
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import AppError
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import GraphBuildStatus
from app.graph.sources import read_sources
from app.models import GraphBuild
from app.models.auth import User
from app.schemas.auth import UserCreateRequest
from app.services import auth

# "RUMIN" as a number: the key of the advisory lock held while the database is prepared.
LOCK_KEY = int.from_bytes(b"RUMIN", "big")


def say(message: str) -> None:
    print(f"==> {message}", flush=True)


@contextmanager
def exclusive(engine: Engine) -> Iterator[None]:
    """Hold RUMIN's advisory lock on PostgreSQL (other databases: nothing to hold)."""
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


def migrate(*, configure_logging: bool = True) -> None:
    # The URL comes from RUMIN's settings (migrations/env.py), never from alembic.ini.
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    # alembic.ini's logging shows each migration in the build log; tests keep their own.
    config.attributes["configure_logger"] = configure_logging
    command.upgrade(config, "head")


def graph_is_current(session: Session) -> bool:
    """Whether the latest successful graph build was made from the current sources."""
    latest = session.scalars(
        select(GraphBuild)
        .where(
            GraphBuild.status.in_(
                (GraphBuildStatus.COMPLETED, GraphBuildStatus.COMPLETED_WITH_WARNINGS)
            )
        )
        .order_by(GraphBuild.id.desc())
        .limit(1)
    ).first()
    return latest is not None and latest.source_fingerprint == read_sources(session).fingerprint()


def ensure_administrator(
    session_factory: sessionmaker[Session], environ: MutableMapping[str, str]
) -> str:
    """Create the first administrator if no account is an active one; what happened."""
    with session_factory() as session:
        active = (
            session.scalar(
                select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
            )
            or 0
        )
        if active:
            return f"{active} active administrator(s): none created."
        email = environ.get("RUMIN_BOOTSTRAP_ADMIN_EMAIL", "").strip()
        password = environ.get("RUMIN_BOOTSTRAP_ADMIN_PASSWORD", "")
        name = environ.get("RUMIN_BOOTSTRAP_ADMIN_NAME", "").strip() or "Administrator"
        if not email or not password:
            return (
                "No administrator yet, so nobody can sign in: set RUMIN_BOOTSTRAP_ADMIN_EMAIL "
                "and RUMIN_BOOTSTRAP_ADMIN_PASSWORD and deploy again, or run "
                "python -m app.auth create-user against this database."
            )
        payload = UserCreateRequest(
            email=email, name=name, role="admin", temporary_password=password
        )
        created = auth.create_user(session, payload, actor=None, must_change_password=True)
        return (
            f"Created the administrator {created.email}; the temporary password must be "
            "replaced at the first sign-in."
        )


def run_step(name: str, step: Callable[[], int]) -> bool:
    say(name)
    code = step()
    if code != 0:
        print(f"✗ {name} failed (exit {code}).", file=sys.stderr)
    return code == 0


def main(
    argv: Sequence[str] | None = None,
    environ: MutableMapping[str, str] | None = None,
    *,
    configure_logging: bool = True,
) -> int:
    del argv
    environ = os.environ if environ is None else environ
    from app.db import seed
    from app.graph import cli as graph_cli
    from app.ingestion import cli as ingestion_cli

    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        with exclusive(engine):
            say("Migrating the database to the latest schema")
            migrate(configure_logging=configure_logging)
            if not run_step("Loading the illustrative sample dataset", lambda: seed.main([])):
                return 1
            if not run_step(
                "Loading the series catalogue (definitions only: nothing is fetched)",
                lambda: ingestion_cli.main(["catalog"]),
            ):
                return 1
            with session_factory() as session:
                current = graph_is_current(session)
            if current:
                say("The knowledge graph is up to date with its sources")
            elif not run_step("Building the knowledge graph", lambda: graph_cli.main(["build"])):
                return 1
            say("Checking for an administrator")
            try:
                print(ensure_administrator(session_factory, environ), flush=True)
            except (AppError, ValidationError) as error:
                print(f"✗ The first administrator could not be created: {error}", file=sys.stderr)
                return 1
    finally:
        engine.dispose()
    say("The database is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
