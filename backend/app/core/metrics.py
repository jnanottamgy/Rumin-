"""Operational metrics in the Prometheus text format (Phase 10).

A handful of counters, gauges and histograms kept in this process and read at
``GET /metrics``: requests by route template and status, their durations, requests in
flight, security events by kind, and the work queued in the scenario and analyst runners.
Label values are route *templates* (``/api/v1/scenarios/{scenario_id}``), never raw paths
or anything a client chose, so the number of series stays bounded.

No third-party client library: the exposition format is small and stable, and one API
process (ADR 58) needs no multi-process aggregation. Values reset when the process
restarts, as Prometheus counters are expected to.
"""

from __future__ import annotations

import bisect
import math
import threading
import time
from collections.abc import Callable, Iterable, Sequence

LabelValues = tuple[str, ...]

# Request durations, in seconds: most reads answer in milliseconds, a Monte Carlo analysis
# can take seconds.
DURATION_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(names: Sequence[str], values: Sequence[str], extra: str = "") -> str:
    pairs = [f'{name}="{_escape(value)}"' for name, value in zip(names, values, strict=True)]
    if extra:
        pairs.append(extra)
    return "{" + ",".join(pairs) + "}" if pairs else ""


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return repr(float(value)) if not float(value).is_integer() else str(int(value))


class Counter:
    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()) -> None:
        self.name, self.help, self.label_names = name, help_text, tuple(labels)
        self._values: dict[LabelValues, float] = {}
        self._lock = threading.Lock()

    def inc(self, *labels: str, amount: float = 1.0) -> None:
        with self._lock:
            self._values[labels] = self._values.get(labels, 0.0) + amount

    def value(self, *labels: str) -> float:
        with self._lock:
            return self._values.get(labels, 0.0)

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} counter"
        with self._lock:
            items = sorted(self._values.items())
        for labels, value in items:
            yield f"{self.name}{_labels(self.label_names, labels)} {_number(value)}"


class Gauge:
    """A value read when the metrics are collected (``read``), or set directly."""

    def __init__(self, name: str, help_text: str, read: Callable[[], float] | None = None) -> None:
        self.name, self.help, self._read = name, help_text, read
        self._value = 0.0
        self._lock = threading.Lock()

    def add(self, amount: float) -> None:
        with self._lock:
            self._value += amount

    def value(self) -> float:
        if self._read is not None:
            return float(self._read())
        with self._lock:
            return self._value

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} gauge"
        yield f"{self.name} {_number(self.value())}"


class Histogram:
    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Sequence[str] = (),
        buckets: Sequence[float] = DURATION_BUCKETS,
    ) -> None:
        self.name, self.help, self.label_names = name, help_text, tuple(labels)
        self.buckets = tuple(sorted(buckets))
        self._series: dict[LabelValues, tuple[list[int], list[float]]] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, *labels: str) -> None:
        index = bisect.bisect_left(self.buckets, value)
        with self._lock:
            counts, totals = self._series.setdefault(labels, ([0] * len(self.buckets), [0.0, 0.0]))
            if index < len(counts):
                counts[index] += 1
            totals[0] += value  # sum
            totals[1] += 1  # count

    def count(self, *labels: str) -> int:
        with self._lock:
            series = self._series.get(labels)
            return int(series[1][1]) if series else 0

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} histogram"
        with self._lock:
            items = sorted((labels, (list(c), list(t))) for labels, (c, t) in self._series.items())
        for labels, (counts, (total, count)) in items:
            running = 0
            for bound, observed in zip(self.buckets, counts, strict=True):
                running += observed
                le = f'le="{_number(bound)}"'
                yield f"{self.name}_bucket{_labels(self.label_names, labels, le)} {running}"
            inf = 'le="+Inf"'
            yield f"{self.name}_bucket{_labels(self.label_names, labels, inf)} {int(count)}"
            yield f"{self.name}_sum{_labels(self.label_names, labels)} {_number(total)}"
            yield f"{self.name}_count{_labels(self.label_names, labels)} {int(count)}"


class Registry:
    def __init__(self) -> None:
        self._metrics: list[Counter | Gauge | Histogram] = []

    def register(self, metric: Counter | Gauge | Histogram) -> None:
        self._metrics.append(metric)

    def render(self) -> str:
        return "\n".join(line for metric in self._metrics for line in metric.render()) + "\n"


class Metrics:
    """The API's metrics. One instance per app (``app.state.metrics``)."""

    def __init__(self) -> None:
        self.registry = Registry()
        self.started = time.time()
        self.requests = Counter(
            "rumin_http_requests_total",
            "HTTP requests answered, by method, route template and status code.",
            ("method", "route", "status"),
        )
        self.durations = Histogram(
            "rumin_http_request_duration_seconds",
            "Time to answer an HTTP request, by method and route template.",
            ("method", "route"),
        )
        self.in_flight = Gauge("rumin_http_requests_in_flight", "HTTP requests being answered now.")
        self.security_events = Counter(
            "rumin_security_events_total",
            "Security events recorded in the audit trail, by kind (e.g. login_failed).",
            ("event",),
        )
        for metric in (self.requests, self.durations, self.in_flight, self.security_events):
            self.registry.register(metric)
        self.registry.register(
            Gauge(
                "rumin_process_start_time_seconds",
                "When this API process started, in seconds since the Unix epoch.",
                read=lambda: self.started,
            )
        )

    def watch(self, name: str, help_text: str, read: Callable[[], float]) -> None:
        """Add a gauge read at collection time (e.g. a runner's queue)."""
        self.registry.register(Gauge(name, help_text, read=read))

    def render(self) -> str:
        return self.registry.render()


# Security events are recorded deep in the services; they count into the process's
# metrics through this hook, which the app sets at start-up.
_security_counter: Counter | None = None


def count_security_events_in(metrics: Metrics | None) -> None:
    global _security_counter
    _security_counter = metrics.security_events if metrics else None


def security_event(event: str) -> None:
    if _security_counter is not None:
        _security_counter.inc(event)
