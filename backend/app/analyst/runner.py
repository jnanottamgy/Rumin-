"""The bounded worker pool that answers questions.

The same design as the Scenario Lab's runner: at most ``max_concurrent`` turns at once and
``max_queued`` waiting; beyond that a question is refused (429) before anything is stored.
Each turn has its own deadline (``RUMIN_ANALYST_DEADLINE_SECONDS``). A turn left unfinished
by a stopped server is marked failed when the server starts again. ``inline`` mode answers
in the request that asked (tests). The pool is per API process; a shared queue is Phase 10
work.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

logger = logging.getLogger(__name__)

RunnerMode = Literal["thread", "inline"]


class AnalystBusy(RuntimeError):
    """Every worker is busy and the queue is full."""


class TurnRunner:
    def __init__(
        self,
        work: Callable[[uuid.UUID], None],
        *,
        recover: Callable[[], int] | None = None,
        mode: RunnerMode = "thread",
        max_concurrent: int = 2,
        max_queued: int = 8,
    ) -> None:
        self.work = work
        self.recover = recover
        self.mode = mode
        self.max_concurrent = max_concurrent
        self.max_queued = max_queued
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
        if self.recover is not None:
            self.recover()
        if self.mode == "thread" and self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self.max_concurrent, thread_name_prefix="rumin-analyst"
            )

    def stop(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            self._pending = 0

    def reserve(self) -> None:
        with self._lock:
            if self._pending >= self.capacity:
                raise AnalystBusy(
                    f"{self._pending} questions are being answered or waiting (the limit is "
                    f"{self.capacity}). Ask again when one has finished."
                )
            self._pending += 1

    def release(self) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)

    def submit(self, turn_id: uuid.UUID) -> None:
        if self.mode == "inline" or self._pool is None:
            self._run(turn_id)
            return
        try:
            self._pool.submit(self._run, turn_id)
        except RuntimeError:  # the pool is shutting down
            self.release()
            raise

    def _run(self, turn_id: uuid.UUID) -> None:
        try:
            self.work(turn_id)
        except Exception:  # pragma: no cover - the work records its own failures
            logger.exception("event=analyst.turn_crashed turn=%s", turn_id)
        finally:
            self.release()
