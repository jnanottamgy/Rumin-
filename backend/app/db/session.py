"""Engine and session management.

The engine and session factory are created by the application factory and stored on
``app.state`` (instead of module-level globals), so tests can build isolated apps that
each point at their own database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_db_engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # FastAPI runs synchronous endpoints in a thread pool; every request still gets
        # its own session, so sharing the SQLite connection pool across threads is safe.
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared in-memory database

    engine = create_engine(database_url, **kwargs)
    if is_sqlite:
        event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def _configure_sqlite_connection(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    # SQLite does not enforce foreign keys unless explicitly asked to, per connection.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session; uncommitted work is rolled back on exit."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session
