"""The Analyst's API end to end on the real database (SQLite or PostgreSQL): conversations,
asking (202, inline in tests), polling, tool calls recorded as they run, follow-ups,
limits (length, turns, one question at a time, the bounded pool), failures, recovery,
deletion, logs without questions or answers, capabilities and the system status."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analyst.orchestrator import Orchestrator
from app.main import create_app
from app.models import AnalystSession, AnalystToolCall, AnalystTurn
from app.openapi_export import build_openapi
from app.services.analyst import AnalystRuntime
from tests.analyst_support import analyst_db  # noqa: F401 - a fixture
from tests.conftest import make_settings, wipe_analyst

API = "/api/v1/analyst"


def call(client: TestClient, method: str, path: str, expect: int, **kwargs: Any) -> Any:
    response = client.request(method, f"{API}{path}", **kwargs)
    assert response.status_code == expect, response.text
    return response.json() if response.content else None


def new_session(client: TestClient, **body: Any) -> dict[str, Any]:
    created: dict[str, Any] = call(client, "POST", "/sessions", 201, json=body)
    return created


def ask(client: TestClient, session_id: str, question: str, expect: int = 202) -> Any:
    return call(
        client, "POST", f"/sessions/{session_id}/turns", expect, json={"question": question}
    )


def runtime(client: TestClient) -> AnalystRuntime:
    app: FastAPI = client.app  # type: ignore[assignment]
    found: AnalystRuntime = app.state.analyst
    return found


@pytest.fixture
def custom_client(database_url: str, session_factory: sessionmaker[Session]) -> Iterator[Any]:
    """Build a client with other settings (cleaned up afterwards)."""
    clients: list[TestClient] = []

    def build(**overrides: Any) -> TestClient:
        client = TestClient(create_app(make_settings(database_url, **overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)
    with session_factory() as session:
        wipe_analyst(session)


# --- Conversations -----------------------------------------------------------------------------


def test_a_conversation_is_created_listed_renamed_and_deleted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(f"{API}/sessions", json={})
    assert response.status_code == 201
    created = response.json()
    assert response.headers["Location"] == f"{API}/sessions/{created['id']}"
    assert (created["title"], created["turn_count"], created["turns"]) == (
        "New conversation",
        0,
        [],
    )
    listed = call(client, "GET", "/sessions", 200)
    assert [item["id"] for item in listed["items"]] == [created["id"]]
    renamed = call(client, "PUT", f"/sessions/{created['id']}", 200, json={"title": "Oil"})
    assert renamed["title"] == "Oil"
    assert call(client, "DELETE", f"/sessions/{created['id']}", 204) is None
    call(client, "GET", f"/sessions/{created['id']}", 404)
    call(client, "DELETE", f"/sessions/{created['id']}", 404)


@pytest.mark.parametrize(
    "body",
    [{"title": ""}, {"title": "x" * 121}, {"title": "a\x00b"}, {"title": "ok", "extra": 1}],
)
def test_conversation_bodies_are_validated(client: TestClient, body: dict[str, Any]) -> None:
    call(client, "POST", "/sessions", 422, json=body)


def test_unknown_ids_are_not_found(client: TestClient) -> None:
    missing = uuid.uuid4()
    call(client, "GET", f"/sessions/{missing}", 404)
    call(client, "POST", f"/sessions/{missing}/turns", 404, json={"question": "Hi"})
    session = new_session(client)
    call(client, "GET", f"/sessions/{session['id']}/turns/{missing}", 404)
    call(client, "GET", "/sessions/not-a-uuid", 422)


# --- Asking -----------------------------------------------------------------------------------


def test_a_question_is_answered_with_evidence_and_recorded_tool_calls(
    analyst_db: TestClient,  # noqa: F811
) -> None:
    session = new_session(analyst_db)
    response = analyst_db.post(
        f"{API}/sessions/{session['id']}/turns",
        json={"question": "Which companies are exposed to the rupee?"},
    )
    assert response.status_code == 202
    turn = response.json()
    assert response.headers["Location"] == f"{API}/sessions/{session['id']}/turns/{turn['id']}"
    # Answered inline in tests; the same turn read again is identical.
    assert turn["status"] == "completed" and turn["poll_after_ms"] is None
    assert turn == call(analyst_db, "GET", f"/sessions/{session['id']}/turns/{turn['id']}", 200)
    answer = turn["answer"]
    assert (answer["intent"], answer["status"], answer["provider"]) == (
        "variable_reach",
        "answered",
        "grounded",
    )
    assert answer["grounding"]["passed"] is True
    assert turn["configured_provider"] == "grounded" and turn["provider"] == "grounded"
    assert turn["usage"]["requests"] == 0
    (tool,) = turn["tool_calls"]
    assert (tool["tool"], tool["status"], tool["arguments"]) == (
        "get_variable_reach",
        "ok",
        {"variable_key": "variable:var_usd_inr"},
    )
    evidence_ids = {item["id"] for item in answer["evidence"]}
    assert set(tool["evidence"]) <= evidence_ids
    cited = {cid for block in answer["blocks"] for cid in block.get("citations", [])}
    assert cited and cited <= evidence_ids
    stored = call(analyst_db, "GET", f"/sessions/{session['id']}", 200)
    assert stored["title"] == "Which companies are exposed to the rupee?"
    assert stored["turn_count"] == 1 and stored["focus"]["subject"] == "variable:var_usd_inr"


def test_a_follow_up_is_read_against_the_conversation(
    analyst_db: TestClient,  # noqa: F811
) -> None:
    session = new_session(analyst_db)
    ask(analyst_db, session["id"], "What does RUMIN know about Aerisca Airways?")
    follow = ask(analyst_db, session["id"], "and its revenue exposure?")
    assert follow["intent"] == "exposure"
    assert follow["tool_calls"][0]["arguments"]["entity_key"] == "company:co_aerisca_airways"
    notices = [b for b in follow["answer"]["blocks"] if b["type"] == "notice"]
    assert any(b["title"] == "Taken from the conversation" for b in notices)
    listed = call(analyst_db, "GET", f"/sessions/{session['id']}", 200)
    assert [turn["position"] for turn in listed["turns"]] == [1, 2]


@pytest.mark.parametrize(
    ("question", "expect"),
    [("", 422), ("   ", 422), ("a\x07b", 422), ("x" * 8001, 422)],
)
def test_questions_are_validated(client: TestClient, question: str, expect: int) -> None:
    session = new_session(client)
    ask(client, session["id"], question, expect)


def test_the_configured_length_limit_applies(custom_client: Any) -> None:
    client = custom_client(analyst_max_question_chars=100)
    session = new_session(client)
    error = ask(client, session["id"], "x" * 101, 422)["error"]
    assert error["details"][0]["field"] == "question"
    assert "limit is 100" in error["message"]


def test_the_turn_limit_applies(custom_client: Any) -> None:
    client = custom_client(analyst_max_turns_per_session=1)
    session = new_session(client)
    ask(client, session["id"], "What can you do?")
    assert (
        "start a new one" in ask(client, session["id"], "What can you do?", 409)["error"]["message"]
    )


def test_one_question_at_a_time_and_no_deletion_while_answering(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    session = new_session(client)
    with session_factory() as db:
        db.add(
            AnalystTurn(
                id=uuid.uuid4(),
                session_id=uuid.UUID(session["id"]),
                position=1,
                question="pending",
                status="running",
                configured_provider="grounded",
                usage={},
                tokens=0,
                analyst_version="1.0.0",
            )
        )
        db.get_one(AnalystSession, uuid.UUID(session["id"])).turn_count = 1
        db.commit()
    assert "still being answered" in ask(client, session["id"], "Hi", 409)["error"]["message"]
    call(client, "DELETE", f"/sessions/{session['id']}", 409)
    # A server that stops leaves nothing running: the next start marks it failed.
    assert runtime(client).recover() == 1
    turn = call(client, "GET", f"/sessions/{session['id']}", 200)["turns"][0]
    assert turn["status"] == "failed" and turn["error"]["code"] == "interrupted"
    call(client, "DELETE", f"/sessions/{session['id']}", 204)


def test_a_full_pool_refuses_before_storing(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    session = new_session(client)
    pool = runtime(client).runner
    for _ in range(pool.capacity):
        pool.reserve()
    try:
        error = ask(client, session["id"], "What can you do?", 429)["error"]
        assert error["code"] == "rate_limited"
    finally:
        for _ in range(pool.capacity):
            pool.release()
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystTurn)) == 0


def test_a_failure_is_stored_without_internals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("internal detail that must not leak")

    monkeypatch.setattr(Orchestrator, "answer", broken)
    session = new_session(client)
    turn = ask(client, session["id"], "What can you do?")
    assert turn["status"] == "failed" and turn["answer"] is None
    assert turn["error"] == {
        "code": "failed",
        "message": "The question could not be answered; the error was logged.",
    }


def test_a_final_turn_never_changes(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    session = new_session(analyst_db)
    turn = ask(analyst_db, session["id"], "What changed recently?")
    runtime(analyst_db).run_turn(uuid.UUID(turn["id"]))  # a second run does nothing
    again = call(analyst_db, "GET", f"/sessions/{session['id']}/turns/{turn['id']}", 200)
    assert again == turn


def test_deleting_a_conversation_removes_everything_in_it(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    keep = new_session(analyst_db)
    ask(analyst_db, keep["id"], "What changed recently?")
    gone = new_session(analyst_db)
    ask(analyst_db, gone["id"], "What does RUMIN know about Aerisca Airways?")
    call(analyst_db, "DELETE", f"/sessions/{gone['id']}", 204)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystSession)) == 1
        assert db.scalar(select(func.count()).select_from(AnalystTurn)) == 1
        assert {row.tool for row in db.scalars(select(AnalystToolCall))} == {"list_changes"}


def test_logs_carry_ids_and_timings_but_never_the_question_or_answer(
    analyst_db: TestClient,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The application's loggers do not propagate to the root logger; listen to them directly.
    app_logger = logging.getLogger("app")
    app_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="app")
    session = new_session(analyst_db)
    marker = "Zyxwvut"
    turn = ask(analyst_db, session["id"], f"What does RUMIN know about Aerisca Airways {marker}?")
    assert turn["status"] == "completed"
    app_logger.removeHandler(caplog.handler)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=analyst.turn" in logged and "event=analyst.tool" in logged
    assert marker not in logged
    assert turn["answer"]["headline"] not in logged


# --- Capabilities and status -------------------------------------------------------------------


def test_capabilities_describe_the_provider_tools_limits_and_suggestions(
    analyst_db: TestClient,  # noqa: F811
) -> None:
    found = call(analyst_db, "GET", "/capabilities", 200)
    assert found["provider"] == {
        "configured": "grounded",
        "active": "grounded",
        "ready": True,
        "reason": None,
        "model": None,
    }
    assert len(found["tools"]) == 17
    assert found["limits"]["max_question_chars"] == 2000
    assert found["limits"]["tokens_used_today"] == 0
    questions = [item["question"] for item in found["suggestions"]]
    assert "What does RUMIN know about Aerisca Airways?" in questions
    assert "What did the latest scenario on Aerisca Airways show?" in questions
    assert any(q.startswith("Show ") for q in questions)
    assert {kind["id"] for kind in found["knowledge_kinds"]} >= {"observed", "simulated"}


def test_the_system_reports_the_analyst(client: TestClient) -> None:
    capabilities = {c["id"]: c for c in client.get("/api/v1/system").json()["capabilities"]}
    analyst = capabilities["ai_analyst"]
    assert (analyst["available"], analyst["planned_phase"]) == (True, 7)
    assert "no language model is configured" in analyst["note"]


def test_the_contract_lists_the_analyst_routes() -> None:
    paths = build_openapi()["paths"]
    assert set(paths) >= {
        "/api/v1/analyst/capabilities",
        "/api/v1/analyst/sessions",
        "/api/v1/analyst/sessions/{session_id}",
        "/api/v1/analyst/sessions/{session_id}/turns",
        "/api/v1/analyst/sessions/{session_id}/turns/{turn_id}",
    }
    assert "429" in paths["/api/v1/analyst/sessions/{session_id}/turns"]["post"]["responses"]
