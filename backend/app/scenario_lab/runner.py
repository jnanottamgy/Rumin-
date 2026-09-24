"""The bounded worker pool that carries out scenario executions.

Executions run in the API process on a small thread pool: at most ``max_concurrent`` at
once and ``max_queued`` waiting; beyond that a request is refused (429) before anything is
stored, never queued without bound. Each execution has a time limit and can be cancelled
between stages (``executor``). An execution left unfinished by a stopped server is marked
failed when the server starts again, so no execution stays "running" forever.

``inline`` mode runs each execution in the request that created it (tests, and a
fallback when threads are not wanted). The pool is per API process, and recovery assumes
one API process: a starting process marks every unfinished execution interrupted,
including one another live process is running (that run then stops and stores nothing;
a final execution is never changed). A shared job queue is Phase 10 work.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import utcnow
from app.domain.enums import ScenarioExecutionStatus
from app.models import ScenarioExecution
from app.scenario_lab.executor import TERMINAL, run_execution

logger = logging.getLogger(__name__)

RunnerMode = Literal["thread", "inline"]
INTERRUPTED = (
    "The server stopped before this execution finished; nothing was stored. Execute the "
    "scenario again."
)


class RunnerBusy(RuntimeError):
    """Every worker is busy and the queue is full."""


class ExecutionRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        freshness: Callable[[Session], str],
        mode: RunnerMode = "thread",
        max_concurrent: int = 2,
        max_queued: int = 8,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.session_factory = session_factory
        self.freshness = freshness
        self.mode = mode
        self.max_concurrent = max_concurrent
        self.max_queued = max_queued
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._pending = 0
        self._pool: ThreadPoolExecutor | None = None

    @property
    def capacity(self) -> int:
        return self.max_concurrent + self.max_queued

    @property
    def pending(self) -> int:
        with self._lock:
            return self._pending

    def start(self) -> None:
        """Start the pool and mark executions a previous process left unfinished."""
        recover(self.session_factory)
        if self.mode == "thread" and self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self.max_concurrent, thread_name_prefix="rumin-scenario"
            )

    def stop(self, *, drain: bool = False) -> None:
        """Stop taking work and wait for running executions (each has a time limit). Queued
        ones are dropped — the next start marks them interrupted — unless ``drain``, which
        waits for them too."""
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=not drain)
        with self._lock:
            self._pending = 0  # dropped work never reaches its own release

    def reserve(self) -> None:
        """Claim a place before an execution is stored; ``RunnerBusy`` if there is none."""
        with self._lock:
            if self._pending >= self.capacity:
                raise RunnerBusy(
                    f"{self._pending} executions are running or waiting (the limit is "
                    f"{self.capacity}). Try again when one has finished."
                )
            self._pending += 1

    def release(self) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)

    def submit(self, execution_id: uuid.UUID) -> None:
        """Carry out a stored, queued execution (after ``reserve``)."""
        if self.mode == "inline" or self._pool is None:
            self._run(execution_id)
            return
        try:
            self._pool.submit(self._run, execution_id)
        except RuntimeError:  # the pool is shutting down
            self.release()
            raise

    def _run(self, execution_id: uuid.UUID) -> None:
        try:
            run_execution(
                self.session_factory,
                execution_id,
                freshness=self.freshness,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception:  # pragma: no cover - run_execution records its own failures
            logger.exception("Scenario execution %s could not be carried out", execution_id)
        finally:
            self.release()


def recover(session_factory: sessionmaker[Session]) -> int:
    """Mark every unfinished execution failed (the process that ran it has stopped). Each
    update applies only while the execution is still unfinished, so one that became final
    in the meantime is left as it is."""
    with session_factory() as session:
        rows = session.execute(
            select(ScenarioExecution.id, ScenarioExecution.stages).where(
                ScenarioExecution.status.not_in(list(TERMINAL))
            )
        ).all()
        now = utcnow()
        marked = 0
        for execution_id, stored_stages in rows:
            stages = [dict(item) for item in stored_stages or []]
            if stages and stages[-1]["finished_at"] is None:
                stages[-1]["finished_at"] = now.isoformat()
            result = session.execute(
                update(ScenarioExecution)
                .where(
                    ScenarioExecution.id == execution_id,
                    ScenarioExecution.status.not_in(list(TERMINAL)),
                )
                .values(
                    stages=stages,
                    status=ScenarioExecutionStatus.FAILED,
                    error={"code": "interrupted", "message": INTERRUPTED, "details": []},
                    finished_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if isinstance(result, CursorResult):
                marked += result.rowcount
        session.commit()
        if marked:
            logger.warning("Marked %d interrupted scenario executions as failed", marked)
        return marked
