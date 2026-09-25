"""Operations (Phase 10): metrics, JSON logs and the limit on guessing a current password.

Every password is for this disposable database only.
"""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import configure_logging
from app.core.metrics import Counter, Histogram, Metrics
from app.main import create_app
from app.models import AuditEvent, User, UserSession
from tests.conftest import COOKIE, TEST_ADMIN_EMAIL, TEST_PASSWORD, make_settings, session_token

API = "/api/v1"


@pytest.fixture
def people(session_factory: sessionmaker[Session]) -> Iterator[None]:
    yield
    with session_factory() as session:
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


# --- The exposition format ---------------------------------------------------------------------


def test_counters_escape_label_values_and_histograms_are_cumulative() -> None:
    counter = Counter("demo_total", "A demonstration.", ("path",))
    counter.inc('/a"b\\c\nd')
    counter.inc('/a"b\\c\nd', amount=2)
    assert list(counter.render())[-1] == 'demo_total{path="/a\\"b\\\\c\\nd"} 3'

    histogram = Histogram("demo_seconds", "Durations.", ("route",), buckets=(0.1, 1.0))
    for value in (0.05, 0.5, 0.5, 5.0):
        histogram.observe(value, "/x")
    lines = list(histogram.render())
    assert 'demo_seconds_bucket{route="/x",le="0.1"} 1' in lines
    assert 'demo_seconds_bucket{route="/x",le="1"} 3' in lines
    assert 'demo_seconds_bucket{route="/x",le="+Inf"} 4' in lines
    assert 'demo_seconds_count{route="/x"} 4' in lines
    assert 'demo_seconds_sum{route="/x"} 6.05' in lines


# --- GET /metrics -------------------------------------------------------------------------------


def test_metrics_are_for_administrators_and_listed_scrapers(
    database_url: str, session_factory: sessionmaker[Session], people: None
) -> None:
    app = create_app(make_settings(database_url))
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        client.cookies.set(
            COOKIE, session_token(session_factory, "viewer-metrics@rumin.test", role="viewer")
        )
        refused = client.get("/metrics")
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "forbidden"

    listed = create_app(make_settings(database_url, metrics_allowed_clients=["testclient"]))
    with TestClient(listed) as client:
        assert client.get("/metrics").status_code == 200


def test_metrics_count_requests_by_route_template_never_by_raw_path(
    database_url: str, session_factory: sessionmaker[Session], admin_token: str, people: None
) -> None:
    app = create_app(make_settings(database_url))
    unknown = "00000000-0000-4000-8000-000000000000"
    with TestClient(app) as client:
        client.cookies.set(COOKIE, admin_token)
        assert client.get(f"{API}/scenarios/{unknown}").status_code == 404
        assert client.get(f"{API}/no-such-thing").status_code == 404
        client.post(f"{API}/auth/login", json={"email": "x@rumin.test", "password": "wrong!"})
        text = client.get("/metrics").text

    assert unknown not in text
    assert (
        'rumin_http_requests_total{method="GET",route="/api/v1/scenarios/{scenario_id}",'
        'status="404"} 1' in text
    )
    assert 'rumin_http_requests_total{method="GET",route="unmatched",status="404"} 1' in text
    assert re.search(
        r'rumin_http_request_duration_seconds_count\{method="GET",'
        r'route="/api/v1/scenarios/\{scenario_id\}"\} 1',
        text,
    )
    assert 'rumin_security_events_total{event="login_failed"}' in text
    assert "rumin_scenario_executions_capacity " in text
    assert "rumin_analyst_turns_pending 0" in text
    # The request reading the metrics is itself still in flight.
    assert "rumin_http_requests_in_flight 1" in text
    # Nothing identifying: no e-mail address, no client address.
    assert "@" not in text and "testclient" not in text


def test_a_metrics_instance_starts_empty() -> None:
    text = Metrics().render()
    assert "# TYPE rumin_http_requests_total counter" in text
    assert "rumin_http_requests_in_flight 0" in text
    assert text.endswith("\n")


# --- JSON logs ----------------------------------------------------------------------------------


def test_json_logs_carry_the_request_id_and_structured_access_fields(
    database_url: str, admin_token: str
) -> None:
    app = create_app(make_settings(database_url, log_level="INFO", log_format="json"))
    stream = io.StringIO()
    handler = logging.getLogger("app").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    previous = handler.setStream(stream)
    try:
        with TestClient(app) as client:
            client.cookies.set(COOKIE, admin_token)
            client.get("/health", headers={"X-Request-ID": "trace-me-1"})
    finally:
        handler.setStream(previous)
        configure_logging("WARNING")

    entries = [json.loads(line) for line in stream.getvalue().splitlines() if line]
    access = next(entry for entry in entries if entry["request_id"] == "trace-me-1")
    assert access["level"] == "INFO"
    assert access["http"] == {
        "method": "GET",
        "path": "/health",
        "status": 200,
        "duration_ms": access["http"]["duration_ms"],
    }
    assert access["time"].endswith("+00:00")
    assert "cookie" not in stream.getvalue().lower()


def test_invented_methods_share_one_label_and_a_logged_path_stays_on_one_line(
    database_url: str, admin_token: str
) -> None:
    """A client chooses the method and the path: neither may grow the metrics without bound
    or forge a log entry (the independent review's F1 and F6)."""
    app = create_app(make_settings(database_url, log_level="INFO"))
    stream = io.StringIO()
    handler = logging.getLogger("app").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    previous = handler.setStream(stream)
    try:
        with TestClient(app) as client:
            for index in range(3):
                assert client.request(f"INVENTED{index}" * 20, "/health").status_code == 405
            client.get("/health%0AINFO forged entry")
            client.cookies.set(COOKIE, admin_token)
            text = client.get("/metrics").text
    finally:
        handler.setStream(previous)
        configure_logging("WARNING")

    assert "INVENTED" not in text and 'method="OTHER"' in text
    other = r'rumin_http_requests_total\{method="OTHER",route="[^"]*",status="405"\} 3'
    assert re.search(other, text)
    lines = stream.getvalue().splitlines()
    assert not any(line.startswith("INFO forged entry") for line in lines)
    assert any("/health\\x0aINFO forged entry" in line for line in lines)
    assert not any("INVENTED" in line for line in lines)


def test_api_answers_are_never_cached(database_url: str, admin_token: str) -> None:
    app = create_app(make_settings(database_url))
    with TestClient(app) as client:
        client.cookies.set(COOKIE, admin_token)
        assert client.get(f"{API}/entities").headers["cache-control"] == "no-store"
        assert client.get(f"{API}/nothing-here").headers["cache-control"] == "no-store"
        assert "cache-control" not in client.get("/health").headers


# --- Guessing a current password ----------------------------------------------------------------


def test_wrong_current_passwords_count_towards_the_client_limit(
    database_url: str, session_factory: sessionmaker[Session], people: None
) -> None:
    app = create_app(make_settings(database_url, login_client_max_failures=5))
    with TestClient(app) as client:
        client.cookies.set(
            COOKIE, session_token(session_factory, "guess@rumin.test", role="analyst")
        )
        body = {"current_password": "not it at all", "new_password": "a new long passphrase"}
        for _ in range(5):
            assert client.post(f"{API}/auth/password", json=body).status_code == 422
        waited = client.post(
            f"{API}/auth/password",
            json={"current_password": TEST_PASSWORD, "new_password": "a new long passphrase"},
        )
        assert waited.status_code == 429
        assert waited.headers["retry-after"]
        assert "failed attempts from this address" in waited.json()["error"]["message"]

    with session_factory() as session:
        events = session.scalars(select(AuditEvent.event).order_by(AuditEvent.occurred_at)).all()
    assert events.count("password_change_failed") == 5
    assert events[-1] == "login_throttled"
