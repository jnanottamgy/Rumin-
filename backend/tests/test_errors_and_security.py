from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import ALLOWED_ORIGIN, make_settings


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nothing-here")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "details": [],
            "request_id": response.headers["X-Request-ID"],
        }
    }


def test_wrong_method_uses_the_error_envelope(client: TestClient) -> None:
    response = client.delete("/api/v1/network")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["Allow"]


def test_unhandled_exceptions_never_leak_internals(database_url: str) -> None:
    app: FastAPI = create_app(make_settings(database_url))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret connection string: postgres://admin:hunter2@db")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert response.headers["X-Request-ID"]


def test_database_outage_returns_service_unavailable() -> None:
    settings = make_settings("sqlite:////nonexistent-directory/rumin.db")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/entities")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "nonexistent-directory" not in response.text


def test_generates_request_ids_and_preserves_safe_incoming_ones(client: TestClient) -> None:
    generated = client.get("/health").headers["X-Request-ID"]
    preserved = client.get("/health", headers={"X-Request-ID": "trace-123"}).headers
    replaced = client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"}).headers

    assert len(generated) == 32
    assert preserved["X-Request-ID"] == "trace-123"
    assert replaced["X-Request-ID"] != "bad id\nwith newline"


def test_sets_security_headers(client: TestClient) -> None:
    headers = client.get("/api/v1/network").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_docs_page_is_served_without_the_strict_api_csp(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers


def test_docs_can_be_disabled(database_url: str) -> None:
    with TestClient(create_app(make_settings(database_url, docs_enabled=False))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_cors_allows_configured_origins(client: TestClient) -> None:
    preflight = client.options(
        "/api/v1/scenarios",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    simple = client.get("/api/v1/network", headers={"Origin": ALLOWED_ORIGIN})

    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert simple.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert "Access-Control-Allow-Credentials" not in simple.headers


def test_cors_rejects_other_origins(client: TestClient) -> None:
    preflight = client.options(
        "/api/v1/scenarios",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    simple = client.get("/api/v1/network", headers={"Origin": "https://evil.example"})

    assert preflight.status_code == 400
    assert "Access-Control-Allow-Origin" not in simple.headers


def test_settings_parse_comma_separated_origins() -> None:
    settings = Settings(_env_file=None, cors_origins="http://a.test, https://b.test/")

    assert settings.cors_origins == ["http://a.test", "https://b.test"]


@pytest.mark.parametrize("origins", ["*", "localhost:5173"])
def test_settings_reject_unsafe_origins(origins: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=origins)
