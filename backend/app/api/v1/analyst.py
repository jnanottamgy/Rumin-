"""The AI Analyst: questions answered from RUMIN's records, with the evidence behind every
figure.

A conversation (session) holds turns. Asking stores the question and answers it on a
bounded worker pool: ``POST …/turns`` answers ``202`` with the queued turn, which is read
again at ``Location`` until it is final (``poll_after_ms``). Each answer lists the tool
calls that produced it, the evidence it cites and the result of the grounding check.
Conversations can be renamed and deleted; nothing else is written. Since Phase 10 a
conversation is private to the person who started it: another person's is "not found".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep, UserDep
from app.schemas.analyst import (
    AskRequest,
    CapabilitiesRead,
    SessionCreate,
    SessionPage,
    SessionRead,
    SessionUpdate,
    TurnRead,
)
from app.schemas.common import ErrorResponse
from app.services import analyst
from app.services.analyst import AnalystRuntime

router = APIRouter(prefix="/analyst", tags=["analyst"])

SessionId = Annotated[uuid.UUID, Path(description="A conversation.")]
TurnId = Annotated[uuid.UUID, Path(description="A question in the conversation.")]
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "A question is still being answered."}
}
BUSY: dict[int | str, dict[str, Any]] = {
    429: {"model": ErrorResponse, "description": "Every worker is busy; ask again shortly."}
}


def get_runtime(request: Request) -> AnalystRuntime:
    runtime: AnalystRuntime = request.app.state.analyst
    return runtime


RuntimeDep = Annotated[AnalystRuntime, Depends(get_runtime)]


@router.get(
    "/capabilities",
    response_model=CapabilitiesRead,
    summary="What the Analyst can do",
    description="The provider that answers (RUMIN's grounded composer, or a language model "
    "when one is configured), the tools it may call, its limits, the kinds of knowledge it "
    "labels, and suggested questions built from what RUMIN holds.",
)
def get_capabilities(session: SessionDep, runtime: RuntimeDep) -> CapabilitiesRead:
    return analyst.capabilities(session, runtime)


@router.get(
    "/sessions",
    response_model=SessionPage,
    summary="Conversations",
    description="Stored conversations, most recently active first.",
)
def list_sessions(session: SessionDep, user: UserDep, page: PaginationDep) -> SessionPage:
    return analyst.list_sessions(session, limit=page.limit, offset=page.offset, owner=user)


@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_session(
    session: SessionDep, user: UserDep, payload: SessionCreate, response: Response
) -> SessionRead:
    created = analyst.create_session(session, payload, owner=user)
    response.headers["Location"] = f"/api/v1/analyst/sessions/{created.id}"
    return created


@router.get(
    "/sessions/{session_id}",
    response_model=SessionRead,
    summary="A conversation with every turn",
    responses=NOT_FOUND,
)
def get_session(session: SessionDep, user: UserDep, session_id: SessionId) -> SessionRead:
    return analyst.get_session(session, session_id, owner=user)


@router.put(
    "/sessions/{session_id}",
    response_model=SessionRead,
    summary="Rename a conversation",
    responses=NOT_FOUND,
)
def rename_session(
    session: SessionDep, user: UserDep, session_id: SessionId, payload: SessionUpdate
) -> SessionRead:
    return analyst.rename_session(session, session_id, payload, owner=user)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
    description="Deletes the conversation with its questions, answers and tool calls. "
    "Refused (409) while a question in it is being answered.",
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_session(
    session: SessionDep, user: UserDep, session_id: SessionId, runtime: RuntimeDep
) -> Response:
    analyst.delete_session(session, session_id, runtime.settings, owner=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/turns",
    response_model=TurnRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask a question",
    description="Stores the question and answers it on the bounded worker pool (429 when it "
    "is full). Follow it at `Location` until it is `completed` or `failed`. One question at "
    "a time per conversation (409 otherwise).",
    responses={**NOT_FOUND, **CONFLICT, **BUSY},
)
def ask(
    session: SessionDep,
    user: UserDep,
    runtime: RuntimeDep,
    session_id: SessionId,
    payload: AskRequest,
    response: Response,
) -> TurnRead:
    turn = analyst.ask(session, runtime, session_id, payload, owner=user)
    response.headers["Location"] = f"/api/v1/analyst/sessions/{session_id}/turns/{turn.id}"
    return turn


@router.get(
    "/sessions/{session_id}/turns/{turn_id}",
    response_model=TurnRead,
    summary="A question and its answer",
    description="While not final, `poll_after_ms` says when to read it again; its tool calls "
    "appear as they are made.",
    responses=NOT_FOUND,
)
def get_turn(
    session: SessionDep, user: UserDep, session_id: SessionId, turn_id: TurnId
) -> TurnRead:
    return analyst.get_turn(session, session_id, turn_id, owner=user)
