"""The AI Analyst: the service behind ``/api/v1/analyst``.

Asking stores a queued turn and hands it to the bounded runner (429 when it is full); the
runner answers it with the orchestrator, recording each tool call as it happens, then
stores the answer. Everything else reads what was stored. Sessions can be renamed and
deleted (with their turns and tool calls); a final turn never changes.

Logs carry ids, intents, providers, tools, timings and token counts — never a question or
an answer.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.analyst import ANALYST_VERSION
from app.analyst.answer import Answer
from app.analyst.composer import possessive
from app.analyst.context import Focus
from app.analyst.evidence import KNOWLEDGE_LABEL
from app.analyst.orchestrator import Limits, Orchestrator, TurnResult
from app.analyst.providers.anthropic import AnthropicConfig, AnthropicProvider
from app.analyst.providers.base import Provider
from app.analyst.providers.grounded import GroundedProvider
from app.analyst.runner import AnalystBusy, TurnRunner
from app.analyst.tools import TOOLS
from app.analyst.tools.registry import ToolCall
from app.analyst.vocabulary import load, the
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, DomainValidationError, NotFoundError
from app.db.base import utcnow
from app.models import (
    AnalystSession,
    AnalystToolCall,
    AnalystTurn,
    EconomicSeries,
    ScenarioExecution,
)
from app.schemas.analyst import (
    AnalystProviderRead,
    AskRequest,
    CapabilitiesRead,
    KnowledgeKindRead,
    LimitsRead,
    SessionCreate,
    SessionPage,
    SessionRead,
    SessionSummaryRead,
    SessionUpdate,
    SuggestionRead,
    ToolCallRead,
    ToolInfoRead,
    TurnErrorRead,
    TurnRead,
    UsageRead,
)
from app.schemas.common import ErrorDetail
from app.simulation.definitions import sha256

logger = logging.getLogger(__name__)

POLL_MS = 500
PENDING = ("queued", "running")
DEFAULT_TITLE = "New conversation"
MAX_STORED_RESULT_CHARS = 32_000
INTERRUPTED = "The server stopped before this question was answered. Ask it again."
FAILED = "The question could not be answered; the error was logged."


class AnalystBusyError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many questions are being answered or waiting."


# --- Runtime ------------------------------------------------------------------------------------


class AnalystRuntime:
    """What the Analyst needs at run time: settings, the database, the provider and the
    bounded runner. One per API process (``app.state.analyst``)."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        provider: Provider | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._provider = provider
        self.runner = TurnRunner(
            self.run_turn,
            recover=self.recover,
            mode=settings.analyst_execution_mode,
            max_concurrent=settings.analyst_max_concurrent,
            max_queued=settings.analyst_max_queued,
        )

    # Provider -------------------------------------------------------------------------------

    def provider(self) -> Provider:
        if self._provider is not None:
            return self._provider
        settings = self.settings
        ready, _ = settings.analyst_ready
        if settings.analyst_provider == "anthropic" and ready:
            key = settings.anthropic_api_key
            assert key is not None and settings.analyst_model is not None  # noqa: S101
            self._provider = AnthropicProvider(
                AnthropicConfig(
                    api_key=key.get_secret_value(),
                    model=settings.analyst_model,
                    base_url=settings.anthropic_base_url,
                    timeout_seconds=settings.analyst_request_timeout_seconds,
                    max_retries=settings.analyst_max_retries,
                    max_tokens=settings.analyst_max_tokens,
                    thinking=settings.analyst_thinking,
                    max_requests=settings.analyst_max_model_requests,
                )
            )
        else:
            self._provider = GroundedProvider()
        return self._provider

    def provider_status(self) -> AnalystProviderRead:
        settings = self.settings
        ready, reason = settings.analyst_ready
        active = self.provider().name
        return AnalystProviderRead(
            configured=settings.analyst_provider,
            active="anthropic" if active == "anthropic" else "grounded",
            ready=ready,
            reason=reason,
            model=settings.analyst_model if active == "anthropic" else None,
        )

    # Lifecycle ------------------------------------------------------------------------------

    def start(self) -> None:
        self.runner.start()

    def stop(self) -> None:
        self.runner.stop()

    def recover(self) -> int:
        """Mark every unfinished turn failed (the process that ran it has stopped)."""
        with self.session_factory() as session:
            result = session.execute(
                update(AnalystTurn)
                .where(AnalystTurn.status.in_(PENDING))
                .values(
                    status="failed",
                    error={"code": "interrupted", "message": INTERRUPTED},
                    finished_at=utcnow(),
                )
                .execution_options(synchronize_session=False)
            )
            session.commit()
            marked = result.rowcount if isinstance(result, CursorResult) else 0
            if marked:
                logger.warning("event=analyst.recovered turns=%d", marked)
            return marked

    # A turn ---------------------------------------------------------------------------------

    def tokens_today(self, session: Session) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        used = session.scalar(
            select(func.coalesce(func.sum(AnalystTurn.tokens), 0)).where(
                AnalystTurn.requested_at >= start,
                AnalystTurn.requested_at < start + timedelta(days=1),
            )
        )
        return int(used or 0)

    def _store_call(self, turn_id: uuid.UUID, call: ToolCall) -> None:
        data = call.output.data if call.output is not None else None
        stored: dict[str, Any] | None = None
        digest: str | None = None
        if data is not None:
            text = json.dumps(data, default=str, sort_keys=True)
            digest = sha256(json.loads(text))
            stored = (
                data
                if len(text) <= MAX_STORED_RESULT_CHARS
                else {"truncated": True, "characters": len(text)}
            )
        with self.session_factory() as session:
            session.add(
                AnalystToolCall(
                    turn_id=turn_id,
                    position=call.position,
                    tool=call.tool[:64],
                    arguments=json.loads(json.dumps(call.arguments, default=str)),
                    status=call.status,
                    summary=(call.output.summary[:300] if call.output else None),
                    result=json.loads(json.dumps(stored, default=str)) if stored else None,
                    result_hash=digest,
                    evidence=list(call.output.evidence) if call.output else [],
                    error=call.error,
                    attempts=call.attempts,
                    started_at=call.started_at,
                    duration_ms=call.duration_ms,
                )
            )
            session.commit()

    def run_turn(self, turn_id: uuid.UUID) -> None:
        began = time.monotonic()
        with self.session_factory() as session:
            claimed = session.execute(
                update(AnalystTurn)
                .where(AnalystTurn.id == turn_id, AnalystTurn.status == "queued")
                .values(status="running", started_at=utcnow())
                .execution_options(synchronize_session=False)
            )
            session.commit()
            if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
                return
            turn = session.get_one(AnalystTurn, turn_id)
            owner = session.get_one(AnalystSession, turn.session_id)
            focus = Focus.from_json(owner.focus)
            history = [
                (question, headline or "")
                for question, headline in session.execute(
                    select(AnalystTurn.question, AnalystTurn.headline)
                    .where(
                        AnalystTurn.session_id == turn.session_id,
                        AnalystTurn.position < turn.position,
                        AnalystTurn.status == "completed",
                    )
                    .order_by(AnalystTurn.position.desc())
                    .limit(4)
                )
            ][::-1]
            question = turn.question
            session_id = turn.session_id
            provider = self.provider()
            skip = None
            if provider.name != "grounded":
                used = self.tokens_today(session)
                if used >= self.settings.analyst_daily_token_budget:
                    skip = "the daily token budget for the language model is used up"
        orchestrator = Orchestrator(
            self.session_factory,
            provider=provider,
            limits=Limits(
                deadline_seconds=self.settings.analyst_deadline_seconds,
                max_tool_calls=self.settings.analyst_max_tool_calls,
            ),
            skip_model=skip,
        )
        try:
            result = orchestrator.answer(
                question,
                focus=focus,
                history=history,
                on_call=lambda call: self._store_call(turn_id, call),
            )
        except Exception:
            logger.exception("event=analyst.turn_failed turn=%s", turn_id)
            self._finish_failed(turn_id, began)
            return
        self._finish(turn_id, session_id, result, began)

    def _finish_failed(self, turn_id: uuid.UUID, began: float) -> None:
        with self.session_factory() as session:
            session.execute(
                update(AnalystTurn)
                .where(AnalystTurn.id == turn_id, AnalystTurn.status == "running")
                .values(
                    status="failed",
                    error={"code": "failed", "message": FAILED},
                    finished_at=utcnow(),
                    duration_ms=int((time.monotonic() - began) * 1000),
                )
                .execution_options(synchronize_session=False)
            )
            session.commit()

    def _finish(
        self, turn_id: uuid.UUID, session_id: uuid.UUID, result: TurnResult, began: float
    ) -> None:
        answer = result.answer.model_dump(mode="json")
        now = utcnow()
        usage = result.usage.to_json()
        with self.session_factory() as session:
            done = session.execute(
                update(AnalystTurn)
                .where(AnalystTurn.id == turn_id, AnalystTurn.status == "running")
                .values(
                    status="completed",
                    intent=result.route.intent,
                    answer_status=result.answer.status,
                    headline=result.answer.headline[:300],
                    answer=answer,
                    answer_hash=sha256(answer),
                    route=json.loads(json.dumps(result.route.to_json(), default=str)),
                    focus_after=result.focus.to_json(),
                    grounded=result.answer.grounding.passed if result.answer.grounding else None,
                    provider=result.answer.provider,
                    model=result.model,
                    fallback=result.fallback,
                    rejected=result.rejected.model_dump(mode="json") if result.rejected else None,
                    usage=usage,
                    tokens=usage["input_tokens"] + usage["output_tokens"],
                    finished_at=now,
                    duration_ms=int((time.monotonic() - began) * 1000),
                )
                .execution_options(synchronize_session=False)
            )
            if isinstance(done, CursorResult) and done.rowcount == 1:
                session.execute(
                    update(AnalystSession)
                    .where(AnalystSession.id == session_id)
                    .values(focus=result.focus.to_json(), updated_at=now)
                    .execution_options(synchronize_session=False)
                )
            session.commit()


# --- Reads --------------------------------------------------------------------------------------


def _call_read(row: AnalystToolCall) -> ToolCallRead:
    return ToolCallRead.model_validate(
        {
            "position": row.position,
            "tool": row.tool,
            "arguments": row.arguments,
            "status": row.status,
            "summary": row.summary,
            "evidence": row.evidence or [],
            "error": row.error,
            "attempts": row.attempts,
            "started_at": row.started_at,
            "duration_ms": row.duration_ms,
        }
    )


def turn_read(row: AnalystTurn, calls: list[AnalystToolCall] | None = None) -> TurnRead:
    usage = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        **(row.usage or {}),
    }
    return TurnRead(
        id=row.id,
        session_id=row.session_id,
        position=row.position,
        question=row.question,
        status=row.status,
        intent=row.intent,
        answer=Answer.model_validate(row.answer) if row.answer else None,
        error=TurnErrorRead.model_validate(row.error) if row.error else None,
        configured_provider=row.configured_provider,
        provider=row.provider,
        model=row.model,
        fallback=row.fallback,
        usage=UsageRead.model_validate(usage),
        tool_calls=[_call_read(call) for call in (calls if calls is not None else row.tool_calls)],
        analyst_version=row.analyst_version,
        requested_at=row.requested_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        poll_after_ms=POLL_MS if row.status in PENDING else None,
    )


def _session_or_404(session: Session, session_id: uuid.UUID) -> AnalystSession:
    found = session.get(AnalystSession, session_id)
    if found is None:
        raise NotFoundError(f"No conversation has the id {session_id}.")
    return found


def _summary(session: Session, row: AnalystSession) -> SessionSummaryRead:
    last = session.scalar(
        select(AnalystTurn.question)
        .where(AnalystTurn.session_id == row.id)
        .order_by(AnalystTurn.position.desc())
        .limit(1)
    )
    return SessionSummaryRead(
        id=row.id,
        title=row.title,
        turn_count=row.turn_count,
        last_question=last,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_sessions(session: Session, *, limit: int, offset: int) -> SessionPage:
    total = session.scalar(select(func.count()).select_from(AnalystSession)) or 0
    rows = session.scalars(
        select(AnalystSession)
        .order_by(AnalystSession.updated_at.desc(), AnalystSession.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return SessionPage(
        items=[_summary(session, row) for row in rows], total=total, limit=limit, offset=offset
    )


def get_session(session: Session, session_id: uuid.UUID) -> SessionRead:
    row = _session_or_404(session, session_id)
    turns = session.scalars(
        select(AnalystTurn).where(AnalystTurn.session_id == row.id).order_by(AnalystTurn.position)
    ).all()
    calls: dict[uuid.UUID, list[AnalystToolCall]] = {turn.id: [] for turn in turns}
    if turns:
        for call in session.scalars(
            select(AnalystToolCall)
            .where(AnalystToolCall.turn_id.in_(list(calls)))
            .order_by(AnalystToolCall.turn_id, AnalystToolCall.position)
        ):
            calls[call.turn_id].append(call)
    summary = _summary(session, row)
    return SessionRead(
        **summary.model_dump(),
        focus=row.focus or {},
        turns=[turn_read(turn, calls[turn.id]) for turn in turns],
    )


def get_turn(session: Session, session_id: uuid.UUID, turn_id: uuid.UUID) -> TurnRead:
    row = session.get(AnalystTurn, turn_id)
    if row is None or row.session_id != session_id:
        raise NotFoundError(f"No question has the id {turn_id} in this conversation.")
    calls = list(
        session.scalars(
            select(AnalystToolCall)
            .where(AnalystToolCall.turn_id == row.id)
            .order_by(AnalystToolCall.position)
        )
    )
    return turn_read(row, calls)


# --- Writes -------------------------------------------------------------------------------------


def create_session(session: Session, payload: SessionCreate) -> SessionRead:
    row = AnalystSession(id=uuid.uuid4(), title=payload.title or DEFAULT_TITLE, focus={})
    session.add(row)
    session.commit()
    return get_session(session, row.id)


def rename_session(session: Session, session_id: uuid.UUID, payload: SessionUpdate) -> SessionRead:
    row = _session_or_404(session, session_id)
    row.title = payload.title
    session.commit()
    return get_session(session, row.id)


def delete_session(session: Session, session_id: uuid.UUID) -> None:
    row = _session_or_404(session, session_id)
    pending = session.scalar(
        select(func.count()).where(
            AnalystTurn.session_id == row.id, AnalystTurn.status.in_(PENDING)
        )
    )
    if pending:
        raise ConflictError(
            "A question in this conversation is still being answered; delete it when that "
            "has finished (each question has a time limit)."
        )
    turn_ids = select(AnalystTurn.id).where(AnalystTurn.session_id == row.id)
    session.execute(delete(AnalystToolCall).where(AnalystToolCall.turn_id.in_(turn_ids)))
    session.execute(delete(AnalystTurn).where(AnalystTurn.session_id == row.id))
    session.execute(delete(AnalystSession).where(AnalystSession.id == row.id))
    session.commit()
    logger.info("event=analyst.session_deleted session=%s", session_id)


def _title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:79].rstrip() + "…"


def ask(
    session: Session, runtime: AnalystRuntime, session_id: uuid.UUID, payload: AskRequest
) -> TurnRead:
    settings = runtime.settings
    row = _session_or_404(session, session_id)
    question = payload.question.strip()
    if len(question) > settings.analyst_max_question_chars:
        message = (
            f"The question is {len(question)} characters long; the limit is "
            f"{settings.analyst_max_question_chars}."
        )
        raise DomainValidationError(
            message,
            details=[
                ErrorDetail(location="body", field="question", message=message, type="too_long")
            ],
        )
    if row.turn_count >= settings.analyst_max_turns_per_session:
        raise ConflictError(
            f"This conversation has reached {settings.analyst_max_turns_per_session} questions; "
            "start a new one."
        )
    pending = session.scalar(
        select(func.count()).where(
            AnalystTurn.session_id == row.id, AnalystTurn.status.in_(PENDING)
        )
    )
    if pending:
        raise ConflictError(
            "The previous question in this conversation is still being answered; ask when it "
            "has finished."
        )
    try:
        runtime.runner.reserve()
    except AnalystBusy as busy:
        raise AnalystBusyError(str(busy)) from busy
    try:
        position = row.turn_count + 1
        turn = AnalystTurn(
            id=uuid.uuid4(),
            session_id=row.id,
            position=position,
            question=question,
            status="queued",
            configured_provider=runtime.settings.analyst_provider,
            usage={},
            tokens=0,
            analyst_version=ANALYST_VERSION,
        )
        row.turn_count = position
        if position == 1 and row.title == DEFAULT_TITLE:
            row.title = _title(question)
        row.updated_at = utcnow()
        session.add(turn)
        session.commit()
    except Exception:
        runtime.runner.release()
        raise
    logger.info("event=analyst.asked session=%s turn=%s position=%d", row.id, turn.id, position)
    runtime.runner.submit(turn.id)
    session.expire_all()
    return get_turn(session, row.id, turn.id)


# --- Capabilities -------------------------------------------------------------------------------


def _suggestions(session: Session) -> list[SuggestionRead]:
    vocabulary = load(session)
    found: list[SuggestionRead] = []
    companies = vocabulary.of_kind("company")
    executed = session.execute(
        select(ScenarioExecution.plan).where(ScenarioExecution.status == "completed").limit(20)
    ).scalars()
    with_execution = next(
        (
            vocabulary.get(str(plan["entity"]["key"]))
            for plan in executed
            if isinstance(plan, dict)
            and isinstance(plan.get("entity"), dict)
            and vocabulary.get(str(plan["entity"].get("key")))
        ),
        None,
    )
    subject = with_execution or (companies[0] if companies else None)
    if subject is not None:
        found.append(
            SuggestionRead(
                label=f"About {subject.label}",
                question=f"What does RUMIN know about {subject.label}?",
            )
        )
        found.append(
            SuggestionRead(
                label="Cost exposure",
                question=f"Which variables affect {possessive(subject.label)} costs?",
            )
        )
    rupee = vocabulary.by_record("var_usd_inr") or next(iter(vocabulary.of_kind("variable")), None)
    if rupee is not None:
        found.append(
            SuggestionRead(
                label=f"Who is exposed to {the(rupee.label)}",
                question=f"Which companies are exposed to {the(rupee.label)}?",
            )
        )
    series = session.scalars(
        select(EconomicSeries)
        .where(EconomicSeries.observation_count > 0)
        .order_by(EconomicSeries.observation_count.desc(), EconomicSeries.name)
        .limit(1)
    ).first()
    if series is not None:
        found.append(
            SuggestionRead(
                label="A stored series", question=f"Show the stored history of {series.name}."
            )
        )
    else:
        found.append(
            SuggestionRead(label="What data is stored", question="What data does RUMIN hold?")
        )
    if with_execution is not None:
        found.append(
            SuggestionRead(
                label="Latest simulation",
                question=f"What did the latest scenario on {with_execution.label} show?",
            )
        )
    brent = vocabulary.by_record("var_brent_crude")
    airline = next((c for c in companies if c.record_id == "co_aerisca_airways"), subject)
    if brent is not None and airline is not None:
        found.append(
            SuggestionRead(
                label="A what-if", question=f"What if Brent crude rises 20% for {airline.label}?"
            )
        )
    found.append(SuggestionRead(label="What changed", question="What changed recently?"))
    return found[:6]


def capabilities(session: Session, runtime: AnalystRuntime) -> CapabilitiesRead:
    settings = runtime.settings
    return CapabilitiesRead(
        version=ANALYST_VERSION,
        provider=runtime.provider_status(),
        tools=[
            ToolInfoRead(name=tool.name, description=tool.description, kind=tool.kind)
            for tool in TOOLS.tools.values()
        ],
        limits=LimitsRead(
            max_question_chars=settings.analyst_max_question_chars,
            max_turns_per_session=settings.analyst_max_turns_per_session,
            max_tool_calls=settings.analyst_max_tool_calls,
            deadline_seconds=settings.analyst_deadline_seconds,
            max_model_requests=settings.analyst_max_model_requests,
            daily_token_budget=settings.analyst_daily_token_budget,
            tokens_used_today=runtime.tokens_today(session),
        ),
        suggestions=_suggestions(session),
        knowledge_kinds=[
            KnowledgeKindRead(id=kind.value, label=label) for kind, label in KNOWLEDGE_LABEL.items()
        ],
        notes=[
            "Answers come from RUMIN's records through read-only tools; every figure cites the "
            "evidence it comes from, and an answer that fails that check is not shown.",
            "RUMIN does not forecast, does not hold live market data and does not make "
            "investment decisions.",
            "A what-if is computed on request and never stored; saving or executing a scenario "
            "is done in the Scenario Lab.",
            "Conversations are stored so they can be reopened, and can be deleted.",
        ],
    )
