"""Slowing down password guessing from one client address.

Failed sign-ins are counted per client address in a sliding window, in this process's
memory (one API process is the supported deployment). Accounts have their own lock in the
database (``users.locked_until``), which holds across processes and restarts.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque

# Bounded memory: the least recently failing clients are forgotten first.
MAX_CLIENTS = 10_000


class ClientThrottle:
    def __init__(self, *, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        times = self._failures.get(key, deque())
        while times and times[0] <= now - self.window:
            times.popleft()
        return times

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may try again (0 when it may try now)."""
        now = time.monotonic()
        with self._lock:
            times = self._prune(key, now)
            if len(times) < self.max_failures:
                return 0
            return max(1, math.ceil(times[0] + self.window - now))

    def failed(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            times = self._prune(key, now)
            times.append(now)
            self._failures.pop(key, None)
            self._failures[key] = times  # most recent last
            while len(self._failures) > MAX_CLIENTS:
                self._failures.pop(next(iter(self._failures)))

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
