from __future__ import annotations

from alembic import command
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import alembic_config, make_settings


def test_liveness_reports_ok_without_touching_the_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rumin-api", "version": "0.1.0"}


def test_readiness_is_ready_when_migrated_and_seeded(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "up_to_date", "dataset": "loaded"},
    }


def test_readiness_reports_missing_migrations(fresh_sqlite_url: str) -> None:
    with TestClient(create_app(make_settings(fresh_sqlite_url))) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "database": "ok",
        "migrations": "missing",
        "dataset": "unknown",
    }


def test_readiness_reports_missing_dataset(fresh_sqlite_url: str) -> None:
    command.upgrade(alembic_config(fresh_sqlite_url), "head")

    with TestClient(create_app(make_settings(fresh_sqlite_url))) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["dataset"] == "missing"


def test_readiness_reports_unreachable_database() -> None:
    settings = make_settings("sqlite:////nonexistent-directory/rumin.db")

    with TestClient(create_app(settings)) as client:
        liveness = client.get("/health")
        readiness = client.get("/health/ready")

    assert liveness.status_code == 200  # the process itself is alive
    assert readiness.status_code == 503
    assert readiness.json()["checks"]["database"] == "unavailable"
