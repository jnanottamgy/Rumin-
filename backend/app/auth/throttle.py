"""Slowing down password guessing (Phase 10).

Two limits are kept in this process's memory (one API process is the supported deployment,
decision 95), each a sliding window of failures:

- per **client address**: failed sign-ins and wrong current passwords, from any account;
- per **account and address**: failed sign-ins for one e-mail address from one client address,
  so someone guessing from one place must wait for that account without locking its owner
  out everywhere else.

A successful sign-in clears only its own account-and-address window: it never clears the
address's failures, so signing in to one's own account between guesses at others gains
nothing. Accounts also have a lock in the database (``users.locked_until``), reached only
after many failures from anywhere, which holds across processes and restarts.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

# Bounded memory: the keys that failed least recently are forgotten first.
MAX_KEYS = 10_000


class ClientThrottle:
    """Failures per key (a client address, or an account and address) in a sliding window."""

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
            return max(1, math.ceil(times[-self.max_failures] + self.window - now))

    def failed(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            times = self._prune(key, now)
            times.append(now)
            self._failures.pop(key, None)
            self._failures[key] = times  # most recent last
            while len(self._failures) > MAX_KEYS:
                self._failures.pop(next(iter(self._failures)))

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


@dataclass(frozen=True)
class LoginThrottle:
    """The two in-memory limits on guessing passwords."""

    client: ClientThrottle
    account: ClientThrottle

    @staticmethod
    def account_key(email: str, client: str) -> str:
        # A newline cannot occur in a validated e-mail address or a client address.
        return f"{email}\n{client}"
