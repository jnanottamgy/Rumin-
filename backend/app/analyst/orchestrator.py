"""One turn of the Analyst, from question to checked answer.

1. **Read** the question: load the vocabulary, route it (policy screening first).
2. **Answer** it with the configured provider. Questions the policy declines, and questions
   the router needs to clarify, never reach a language model: their answer is fixed.
3. **Check** the draft against the evidence the tool calls recorded (``grounding.py``). A
   language model's draft that fails the check — or a model that fails, refuses, runs out
   of budget or time — is replaced by the grounded composer's answer, and the reason is
   kept with the turn.
4. Return the answer, the route, every tool call and the conversation's new focus.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.analyst import grounding
from app.analyst.answer import Answer, GroundingRead, NoticeBlock
from app.analyst.composer import Draft
from app.analyst.context import Focus
from app.analyst.evidence import EvidenceLedger
from app.analyst.providers.base import Provider, ProviderContext, ProviderFailed, Usage
from app.analyst.providers.grounded import GroundedProvider
from app.analyst.router import Route, route
from app.analyst.tools import TOOLS
from app.analyst.tools.registry import Access, ToolCall, ToolRegistry, ToolRunner
from app.analyst.vocabulary import load

logger = logging.getLogger(__name__)

# Intents answered by fixed text or a clarifying question: never sent to a language model.
FIXED = {"injection", "secrets", "clarify", "capabilities", "unsupported"}


@dataclass(frozen=True)
class Limits:
    deadline_seconds: float = 30.0
    max_tool_calls: int = 12


@dataclass
class TurnResult:
    answer: Answer
    route: Route
    calls: list[ToolCall]
    focus: Focus
    usage: Usage = field(default_factory=Usage)
    model: str | None = None
    fallback: str | None = None  # why the grounded answer replaced the provider's
    rejected: GroundingRead | None = None  # the check the provider's draft failed
    duration_ms: int = 0


WITHHELD = NoticeBlock(
    kind="limitation",
    title="Part of this answer was withheld",
    text="RUMIN's grounding check could not match every figure, date or citation in it to the "
    "evidence it read, so those parts are not shown.",
)


def _withhold(draft: Draft, checked: GroundingRead) -> Draft:
    """RUMIN's own draft without the parts the grounding check found a problem in: an
    answer is never shown with a figure its evidence does not hold, whoever wrote it."""
    bad = {problem.block for problem in checked.problems}
    kept = [block for index, block in enumerate(draft.blocks) if index not in bad]
    substance = any(not isinstance(block, NoticeBlock) for block in kept)
    status = draft.status
    if status == "answered":
        status = "partial" if substance else "failed"
    headline = "Part of this answer could not be verified" if None in bad else draft.headline
    return Draft(
        status=status,
        headline=headline,
        blocks=[*kept, WITHHELD],
        follow_ups=draft.follow_ups,
        focus=draft.focus,
    )


def _new_focus(previous: Focus, found: Route, draft: Draft) -> Focus:
    if found.intent in ("clarify", "injection", "secrets", "unsupported", "capabilities"):
        return previous
    data: dict[str, Any] = {**previous.to_json(), "intent": found.intent}
    data.update(draft.focus)
    if not draft.focus.get("changes") and found.intent != "what_if":
        data.pop("changes", None)
    return Focus.from_json(data)


class Orchestrator:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        provider: Provider | None = None,
        limits: Limits | None = None,
        registry: ToolRegistry = TOOLS,
        access: Access | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        skip_model: str | None = None,
    ) -> None:
        """``skip_model``: a reason not to call the configured model for this turn (for
        example an exhausted token budget); the grounded composer answers instead."""
        self.session_factory = session_factory
        self.skip_model = skip_model
        self.provider: Provider = provider or GroundedProvider()
        self.grounded = GroundedProvider()
        self.limits = limits or Limits()
        self.registry = registry
        self.access = access or Access()
        self.clock = clock

    def answer(
        self,
        question: str,
        *,
        focus: Focus | None = None,
        history: list[tuple[str, str]] | None = None,
        on_call: Callable[[ToolCall], None] | None = None,
    ) -> TurnResult:
        began = time.monotonic()
        focus = focus or Focus()
        with self.session_factory() as session:
            vocabulary = load(session)
            session.rollback()
        found = route(question, vocabulary, focus)
        ledger = EvidenceLedger()
        runner = ToolRunner(
            self.registry,
            self.session_factory,
            vocabulary,
            ledger,
            access=self.access,
            deadline=began + self.limits.deadline_seconds,
            max_calls=self.limits.max_tool_calls,
            clock=self.clock,
            on_call=on_call,
        )
        context = ProviderContext(found, runner, vocabulary, focus, history or [])
        usage = Usage()
        model: str | None = None
        fallback: str | None = None
        rejected: GroundingRead | None = None
        provider_name = self.provider.name
        try:
            if found.intent in FIXED or provider_name == "grounded" or self.skip_model:
                result = self.grounded.answer(context)
                if provider_name != "grounded" and found.intent not in FIXED:
                    fallback = self.skip_model
                provider_name = "grounded"
            else:
                try:
                    result = self.provider.answer(context)
                    usage, model = result.usage, result.model
                except ProviderFailed as failure:
                    usage = failure.usage
                    fallback = failure.reason
                    result = self.grounded.answer(context)
                    provider_name = "grounded"
            draft = result.draft
            checked = grounding.check(draft.headline, draft.blocks, ledger.items)
            if not checked.passed and provider_name != "grounded":
                rejected = checked
                count = len(checked.problems)
                fallback = (
                    f"its draft did not pass the grounding check ({count} "
                    f"problem{'s' if count != 1 else ''}, the first: "
                    f"{checked.problems[0].reason.rstrip('.')})"
                )
                logger.warning(
                    "event=analyst.grounding_failed provider=%s problems=%d",
                    provider_name,
                    count,
                )
                draft = self.grounded.answer(context).draft
                provider_name = "grounded"
                checked = grounding.check(draft.headline, draft.blocks, ledger.items)
            if not checked.passed:
                # RUMIN's own composer is held to the same check as a model.
                logger.warning(
                    "event=analyst.grounding_failed provider=grounded problems=%d",
                    len(checked.problems),
                )
                draft = _withhold(draft, checked)
                checked = grounding.check(draft.headline, draft.blocks, ledger.items)
            if fallback:
                reason = fallback[0].lower() + fallback[1:]
                draft.blocks.append(
                    NoticeBlock(
                        kind="fallback",
                        title="Answered by RUMIN's grounded composer",
                        text=f"The language model's answer was not used: {reason.rstrip('.')}. "
                        "This answer was composed by RUMIN from the same tools.",
                    )
                )
            answer = Answer(
                status=draft.status,
                intent=found.intent,
                headline=draft.headline,
                blocks=draft.blocks,
                evidence=ledger.items,
                follow_ups=draft.follow_ups[:4],
                provider=provider_name,
                grounding=checked,
            )
        finally:
            runner.close()
        duration = int((time.monotonic() - began) * 1000)
        logger.info(
            "event=analyst.turn intent=%s provider=%s status=%s tools=%d evidence=%d "
            "grounded=%s duration_ms=%d",
            found.intent,
            provider_name,
            answer.status,
            len(runner.calls),
            len(ledger),
            answer.grounding.passed if answer.grounding else None,
            duration,
        )
        return TurnResult(
            answer=answer,
            route=found,
            calls=runner.calls,
            focus=_new_focus(focus, found, draft),
            usage=usage,
            model=model,
            fallback=fallback,
            rejected=rejected,
            duration_ms=duration,
        )
