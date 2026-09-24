"""The tool layer: the only way the Analyst reaches RUMIN's data.

A tool is a name, a description, a typed input (unknown fields refused), a **fetch** that
reads through an existing service, and a **render** that turns what was fetched into
evidence, display blocks and a compact result. The registry is an allowlist: a call to any
other name is refused, and so is a call whose arguments do not validate.

* Every fetch runs on a worker thread with **its own database session** and a time limit.
  A fetch that overruns is abandoned (its session is closed when it ends; tools only read,
  so nothing is left half-written) and the call is reported as timed out.
* A fetch that fails on a transient database error is tried again, once.
* Evidence is recorded on the calling thread, from the fetched result, so an abandoned
  fetch can never add evidence to a turn.
* Every call carries an **access context**. RUMIN has no users yet (Phase 10), so today it
  only says whether a tool may compute (the scenario preview); per-user checks will go here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.analyst.answer import Block
from app.analyst.evidence import EvidenceLedger
from app.analyst.vocabulary import Vocabulary
from app.core.errors import AppError, NotFoundError

logger = logging.getLogger(__name__)

ToolKind = Literal["read", "compute"]
CallStatus = Literal["ok", "invalid", "refused", "not_found", "failed", "timeout", "skipped"]
MAX_RESULT_CHARS = 12_000


class ToolProblem(Exception):
    """A tool could not answer; ``message`` is safe to show and to give a language model."""

    def __init__(self, message: str, *, status: CallStatus = "failed") -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Access:
    """Who is asking. Every call passes one (see the module docstring)."""

    principal: str = "anonymous"
    may_compute: bool = True


@dataclass
class Fetched:
    """What a fetch returned, before it becomes evidence."""

    value: Any
    read_at: datetime


@dataclass
class ToolOutput:
    data: dict[str, Any]  # compact, bounded: what a language model sees and what is stored
    summary: str  # one line for the method trace
    evidence: list[str] = field(default_factory=list)
    display: list[Block] = field(default_factory=list)
    facts: Any = None  # the fetched objects, for the grounded composer (never stored)


@dataclass
class ToolCall:
    position: int
    tool: str
    arguments: dict[str, Any]
    status: CallStatus
    started_at: datetime
    duration_ms: int
    attempts: int
    output: ToolOutput | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.output is not None


@dataclass(frozen=True)
class RenderContext:
    ledger: EvidenceLedger
    call: int
    vocabulary: Vocabulary


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    fetch: Callable[[Session, Any, Vocabulary], Any]
    render: Callable[[RenderContext, Any, Any, datetime], ToolOutput]
    kind: ToolKind = "read"
    timeout_seconds: float = 8.0

    def schema(self) -> dict[str, Any]:
        """The tool as a language model is shown it."""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}


def _problem(error: ValidationError) -> str:
    parts = []
    for item in error.errors()[:5]:
        where = ".".join(str(part) for part in item["loc"]) or "arguments"
        parts.append(f"{where}: {item['msg']}")
    return "Invalid arguments — " + "; ".join(parts)


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self.tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self.tools:
                raise ValueError(f"Tool {tool.name} is registered twice.")
            self.tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        return list(self.tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.tools.values()]


@dataclass
class ToolRunner:
    """Runs tool calls for one turn, in order, recording each (see the module docstring)."""

    registry: ToolRegistry
    session_factory: sessionmaker[Session]
    vocabulary: Vocabulary
    ledger: EvidenceLedger
    access: Access = field(default_factory=Access)
    deadline: float | None = None  # time.monotonic() value after which no call starts
    max_calls: int = 16
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    calls: list[ToolCall] = field(default_factory=list)
    on_call: Callable[[ToolCall], None] | None = None
    _pool: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)

    def _executor(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rumin-tool")
        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    def _fetch(self, tool: Tool, arguments: BaseModel) -> Fetched:
        with self.session_factory() as session:
            value = tool.fetch(session, arguments, self.vocabulary)
            read_at = self.clock()
            session.rollback()  # tools only read; nothing may be left pending
            return Fetched(value, read_at)

    def call(self, name: str, arguments: Mapping[str, Any] | None) -> ToolCall:
        position = len(self.calls) + 1
        started = self.clock()
        began = time.monotonic()
        raw = dict(arguments or {})

        def finish(
            status: CallStatus,
            *,
            output: ToolOutput | None = None,
            error: str | None = None,
            attempts: int = 0,
            args: dict[str, Any] | None = None,
        ) -> ToolCall:
            record = ToolCall(
                position=position,
                tool=name,
                arguments=args if args is not None else raw,
                status=status,
                started_at=started,
                duration_ms=int((time.monotonic() - began) * 1000),
                attempts=attempts,
                output=output,
                error=error,
            )
            self.calls.append(record)
            logger.info(
                "event=analyst.tool tool=%s status=%s duration_ms=%d attempts=%d",
                name,
                status,
                record.duration_ms,
                attempts,
            )
            if self.on_call is not None:
                self.on_call(record)
            return record

        tool = self.registry.tools.get(name)
        if tool is None:
            return finish("refused", error=f"'{name}' is not one of the Analyst's tools.")
        if len(self.calls) >= self.max_calls:
            return finish("skipped", error="The limit of tool calls for one question is reached.")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return finish("skipped", error="The time allowed for this question has run out.")
        if tool.kind == "compute" and not self.access.may_compute:
            return finish("refused", error="This tool is not available to you.")
        try:
            parsed = tool.input_model.model_validate(raw)
        except ValidationError as error:
            return finish("invalid", error=_problem(error))
        args = parsed.model_dump(mode="json", exclude_none=True)

        timeout = tool.timeout_seconds
        if self.deadline is not None:
            timeout = max(0.1, min(timeout, self.deadline - time.monotonic()))
        attempts = 0
        while True:
            attempts += 1
            future = self._executor().submit(self._fetch, tool, parsed)
            try:
                fetched = future.result(timeout=timeout)
                break
            except FutureTimeout:
                future.cancel()
                return finish(
                    "timeout",
                    error=f"The tool did not finish within {timeout:.1f} s.",
                    attempts=attempts,
                    args=args,
                )
            except ToolProblem as problem:
                return finish(problem.status, error=problem.message, attempts=attempts, args=args)
            except NotFoundError as error:
                return finish("not_found", error=error.message, attempts=attempts, args=args)
            except AppError as error:
                return finish("failed", error=error.message, attempts=attempts, args=args)
            except OperationalError:
                if attempts < 2:
                    continue
                return finish(
                    "failed",
                    error="The database could not be read; try again shortly.",
                    attempts=attempts,
                    args=args,
                )
            except Exception:
                logger.exception("event=analyst.tool_error tool=%s", name)
                return finish(
                    "failed",
                    error="The tool failed unexpectedly; the error was logged.",
                    attempts=attempts,
                    args=args,
                )
        try:
            output = tool.render(
                RenderContext(self.ledger, position, self.vocabulary),
                parsed,
                fetched.value,
                fetched.read_at,
            )
        except ToolProblem as problem:
            return finish(problem.status, error=problem.message, attempts=attempts, args=args)
        return finish("ok", output=output, attempts=attempts, args=args)
