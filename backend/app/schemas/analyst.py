"""AI Analyst: conversations, turns, the tool calls behind each answer, and capabilities.

An answer is a headline and blocks (paragraphs citing evidence as ``[E1]``, tables, series,
relationship paths, scenario cards, notices, clarifying choices) with the evidence they
cite and the result of the grounding check. Every tool call a turn made is listed with its
arguments, status and timing. Asking is asynchronous: ``POST …/turns`` answers ``202`` and
the turn is read again until it is final (``poll_after_ms``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.analyst.answer import Answer
from app.schemas.common import ApiModel, InputModel, Page, SafeText

TurnStatus = Literal["queued", "running", "completed", "failed"]
ProviderName = Literal["grounded", "anthropic"]


# --- Requests -----------------------------------------------------------------------------------


class SessionCreate(InputModel):
    title: SafeText | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Default: the first question, shortened.",
    )


class SessionUpdate(InputModel):
    title: SafeText = Field(min_length=1, max_length=120)


class AskRequest(InputModel):
    question: SafeText = Field(
        min_length=1,
        max_length=8000,
        description="The question, in plain English. The configured limit "
        "(`limits.max_question_chars`, 2000 by default) applies.",
        examples=["Which companies are exposed to the rupee?"],
    )


# --- Turns --------------------------------------------------------------------------------------


class ToolCallRead(ApiModel):
    position: int
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "invalid", "refused", "not_found", "failed", "timeout", "skipped"]
    summary: str | None
    evidence: list[str] = Field(description="Evidence ids this call produced.")
    error: str | None
    attempts: int
    started_at: datetime
    duration_ms: int


class TurnErrorRead(ApiModel):
    code: str
    message: str


class UsageRead(ApiModel):
    requests: int = Field(description="Requests to the language model (0 for grounded).")
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


class TurnRead(ApiModel):
    id: uuid.UUID
    session_id: uuid.UUID
    position: int
    question: str
    status: TurnStatus
    intent: str | None
    answer: Answer | None = Field(description="Present once the turn has completed.")
    error: TurnErrorRead | None = Field(description="Why the turn failed, if it did.")
    configured_provider: ProviderName
    provider: ProviderName | None = Field(description="What composed the answer.")
    model: str | None = Field(description="The language model that answered, if one did.")
    fallback: str | None = Field(
        description="Why RUMIN's grounded composer answered instead of the language model."
    )
    usage: UsageRead
    tool_calls: list[ToolCallRead]
    analyst_version: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    poll_after_ms: int | None = Field(description="While not final: when to read it again.")


class TurnSummaryRead(ApiModel):
    id: uuid.UUID
    position: int
    question: str
    status: TurnStatus
    headline: str | None
    intent: str | None


# --- Sessions -----------------------------------------------------------------------------------


class SessionSummaryRead(ApiModel):
    id: uuid.UUID
    title: str
    turn_count: int
    last_question: str | None
    created_at: datetime
    updated_at: datetime


class SessionRead(SessionSummaryRead):
    focus: dict[str, Any] = Field(
        description="What the conversation is about (record keys only), used to read "
        "follow-up questions."
    )
    turns: list[TurnRead]


class SessionPage(Page[SessionSummaryRead]):
    pass


# --- Capabilities -------------------------------------------------------------------------------


class AnalystProviderRead(ApiModel):
    configured: ProviderName
    active: ProviderName = Field(description="What answers now.")
    ready: bool
    reason: str | None = Field(description="Why the configured provider is not active.")
    model: str | None


class ToolInfoRead(ApiModel):
    name: str
    description: str
    kind: Literal["read", "compute"]


class LimitsRead(ApiModel):
    max_question_chars: int
    max_turns_per_session: int
    max_tool_calls: int
    deadline_seconds: float
    max_model_requests: int
    daily_token_budget: int
    tokens_used_today: int


class SuggestionRead(ApiModel):
    label: str
    question: str


class KnowledgeKindRead(ApiModel):
    id: str
    label: str


class CapabilitiesRead(ApiModel):
    version: str
    provider: AnalystProviderRead
    tools: list[ToolInfoRead]
    limits: LimitsRead
    suggestions: list[SuggestionRead] = Field(description="Questions built from what RUMIN holds.")
    knowledge_kinds: list[KnowledgeKindRead]
    notes: list[str]
