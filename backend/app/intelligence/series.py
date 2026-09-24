"""Observed data: changes, revisions, and the trend, volatility and anomaly signals.

Everything here reads **current** stored values (the latest revision of each period) with
their provenance, and computes with exact decimals. Missing values are skipped, never
treated as zero, and a gap breaks a chain of changes: a change is computed only between
consecutive periods (or consecutive bars of one price dataset).

How a change is measured depends on what the series measures (``measure_type``):

* ``level`` and ``exchange_rate`` series, and prices: relative change, in percent of the
  earlier value (which must be positive);
* ``change``, ``rate`` and ``ratio`` series, already in percent: a difference in percentage
  points — never a percent of a percent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ObservationStatus
from app.intelligence.model import Ref
from app.intelligence.stats import (
    least_squares,
    modified_z,
    percentile_rank,
    point_change,
    relative_change,
    rounded,
    sample_std,
    t_critical,
)
from app.intelligence.thresholds import Thresholds
from app.models import Dataset, EconomicObservation, EconomicSeries, Instrument, PriceBar
from app.simulation.decimal_math import ZERO, arithmetic, to_output

RELATIVE_MEASURES = frozenset({"level", "exchange_rate"})
MAX_POINTS = 2_000  # the most recent values read per series or instrument
MAX_REVISIONS = 50


@dataclass(frozen=True)
class DatasetInfo:
    id: str
    name: str
    version: str
    is_illustrative: bool
    license: str
    attribution: str | None


@dataclass(frozen=True)
class Point:
    label: str  # "2024", "2024-03", "2024-03-28"
    start: date
    value: Decimal
    record_id: int  # observation or price-bar id
    revision: int
    quality_status: str
    flags: str | None
    retrieved_at: datetime
    last_confirmed_at: datetime


@dataclass(frozen=True)
class Subject:
    """A series or an instrument, as the signals see it."""

    kind: str  # series | instrument
    id: str
    name: str
    unit: str
    frequency: str  # annual | quarterly | monthly | daily
    measure: str  # relative | points
    variable_id: str | None
    variable_relation: str | None
    country: str | None
    dataset: DatasetInfo

    @property
    def ref(self) -> Ref:
        return Ref(self.kind, self.id, self.name)

    @property
    def change_unit(self) -> str:
        return "percent" if self.measure == "relative" else "percentage_points"


@dataclass(frozen=True)
class History:
    subject: Subject
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Change:
    earlier: Point
    later: Point
    value: Decimal  # percent or percentage points (see subject.change_unit)

    @property
    def direction(self) -> str:
        return "up" if self.value > ZERO else "down" if self.value < ZERO else "none"

    @property
    def flagged(self) -> bool:
        return "warning" in (self.earlier.quality_status, self.later.quality_status)


@dataclass(frozen=True)
class Revision:
    label: str
    start: date
    previous: Decimal | None
    revised: Decimal | None
    previous_revision: int
    revised_at: datetime | None
    previous_id: int
    revised_id: int
    change: Decimal | None


def _dataset(row: Dataset) -> DatasetInfo:
    return DatasetInfo(
        id=row.id,
        name=row.name,
        version=row.version,
        is_illustrative=row.is_illustrative,
        license=row.license,
        attribution=row.attribution,
    )


def _dataset_row(session: Session, dataset_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:  # pragma: no cover - the foreign key forbids it
        raise LookupError(f"Dataset {dataset_id} is missing.")
    return dataset


def series_subject(row: EconomicSeries, dataset: Dataset) -> Subject:
    return Subject(
        kind="series",
        id=row.id,
        name=row.name,
        unit=row.unit,
        frequency=str(row.frequency.value),
        measure="relative" if str(row.measure_type.value) in RELATIVE_MEASURES else "points",
        variable_id=row.variable_id,
        variable_relation=row.variable_relation,
        country=row.country_iso3,
        dataset=_dataset(dataset),
    )


def load_series(session: Session, series_id: str) -> History | None:
    row = session.get(EconomicSeries, series_id)
    if row is None:
        return None
    dataset = _dataset_row(session, row.dataset_id)
    rows = session.scalars(
        select(EconomicObservation)
        .where(
            EconomicObservation.series_id == series_id,
            EconomicObservation.superseded_at.is_(None),
            EconomicObservation.status == ObservationStatus.REPORTED,
            EconomicObservation.value.is_not(None),
        )
        .order_by(EconomicObservation.period_start.desc())
        .limit(MAX_POINTS)
    ).all()
    points = tuple(
        Point(
            label=obs.period_label,
            start=obs.period_start,
            value=obs.value,  # type: ignore[arg-type]  # filtered: not null
            record_id=obs.id,
            revision=obs.revision,
            quality_status=str(obs.quality_status.value),
            flags=obs.provider_flags or None,
            retrieved_at=obs.first_seen_at,
            last_confirmed_at=obs.last_seen_at,
        )
        for obs in reversed(rows)
    )
    return History(series_subject(row, dataset), points)


def load_instrument(session: Session, instrument_id: str) -> list[History]:
    """One history per price dataset (prices from different datasets are never blended)."""
    row = session.get(Instrument, instrument_id)
    if row is None:
        return []
    dataset_ids = session.scalars(
        select(PriceBar.dataset_id)
        .where(PriceBar.instrument_id == instrument_id, PriceBar.superseded_at.is_(None))
        .distinct()
        .order_by(PriceBar.dataset_id)
    ).all()
    histories: list[History] = []
    for dataset_id in dataset_ids:
        dataset = _dataset_row(session, dataset_id)
        bars = session.scalars(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.dataset_id == dataset_id,
                PriceBar.superseded_at.is_(None),
            )
            .order_by(PriceBar.trade_date.desc())
            .limit(MAX_POINTS)
        ).all()
        subject = Subject(
            kind="instrument",
            id=row.id,
            name=row.name,
            unit=f"{row.currency} per share",
            frequency="daily",
            measure="relative",
            variable_id=None,
            variable_relation=None,
            country=row.country_id,
            dataset=_dataset(dataset),
        )
        points = tuple(
            Point(
                label=bar.trade_date.isoformat(),
                start=bar.trade_date,
                value=bar.close,
                record_id=bar.id,
                revision=bar.revision,
                quality_status=str(bar.quality_status.value),
                flags=None,
                retrieved_at=bar.first_seen_at,
                last_confirmed_at=bar.last_seen_at,
            )
            for bar in reversed(bars)
        )
        histories.append(History(subject, points))
    return histories


def period_index(start: date, frequency: str) -> int | None:
    if frequency == "annual":
        return start.year
    if frequency == "quarterly":
        return start.year * 4 + (start.month - 1) // 3
    if frequency == "monthly":
        return start.year * 12 + start.month - 1
    return None


def positions(history: History) -> list[int]:
    """Each point's period index (bars: their position; a missing day is not a gap)."""
    if history.subject.kind == "instrument":
        return list(range(len(history.points)))
    indexes = [period_index(p.start, history.subject.frequency) for p in history.points]
    if any(index is None for index in indexes):
        return list(range(len(history.points)))
    return [int(index) for index in indexes if index is not None]


def changes(history: History) -> list[Change]:
    """Changes between consecutive values; a gap in the periods breaks the chain."""
    found: list[Change] = []
    places = positions(history)
    for (earlier, later), (a, b) in zip(pairwise(history.points), pairwise(places), strict=True):
        if b - a != 1:
            continue
        if history.subject.measure == "relative":
            value = relative_change(earlier.value, later.value)
            if value is None:
                continue
        else:
            value = point_change(earlier.value, later.value)
        found.append(Change(earlier, later, to_output(value, "A change")))
    return found


def threshold_for(subject: Subject, thresholds: Thresholds) -> tuple[str, Decimal]:
    if subject.kind == "instrument":
        return "price_move_percent", thresholds.price_move_percent
    if subject.measure == "relative":
        return "relative_change_percent", thresholds.relative_change_percent
    return "point_change", thresholds.point_change


def meets(change: Change, threshold: Decimal) -> bool:
    return abs(change.value) >= threshold


# --- Signals on a history ------------------------------------------------------------------


@dataclass(frozen=True)
class TrendResult:
    window: int
    n: int
    first: str
    last: str
    slope: Decimal  # series unit per period
    relative_slope: Decimal | None  # percent of the window's mean per period (relative only)
    t: Decimal | None
    critical: Decimal | None
    significance: str
    direction: str  # rising | falling | no_clear_direction | exact_line
    exact_fit: bool


def trend(history: History, thresholds: Thresholds) -> TrendResult | None:
    window = thresholds.window_for(history.subject.frequency)
    points = list(history.points[-window:])
    if len(points) < 3:
        return None
    places = positions(history)[-window:]
    values = [p.value for p in points]
    fit = least_squares(values, [place - places[0] for place in places])
    significance = thresholds.trend_significance
    critical = t_critical(len(points) - 2, significance)
    relative: Decimal | None = None
    if history.subject.measure == "relative":
        with arithmetic():
            average = sum(values, ZERO) / Decimal(len(values))
            relative = fit.slope / average * Decimal(100) if average > ZERO else None
    if fit.exact_fit:
        direction = "exact_line" if fit.slope != ZERO else "no_clear_direction"
    elif fit.t is not None and abs(fit.t) > critical:
        direction = "rising" if fit.slope > ZERO else "falling"
    else:
        direction = "no_clear_direction"
    return TrendResult(
        window=window,
        n=len(points),
        first=points[0].label,
        last=points[-1].label,
        slope=to_output(fit.slope, "A slope"),
        relative_slope=rounded(relative),
        t=rounded(fit.t),
        critical=critical,
        significance=significance,
        direction=direction,
        exact_fit=fit.exact_fit,
    )


@dataclass(frozen=True)
class VolatilityResult:
    window: int
    latest: Decimal  # standard deviation of the latest window's changes
    windows: int  # earlier windows compared (0 when history is too short)
    percentile: Decimal | None
    median_earlier: Decimal | None
    level: str  # high | not_high | insufficient_history
    first: str
    last: str


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with arithmetic():
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def volatility(
    found: Sequence[Change], thresholds: Thresholds, frequency: str
) -> VolatilityResult | None:
    window = thresholds.window_for(frequency)
    if len(found) < max(window, 2):
        return None
    values = [change.value for change in found]
    latest = sample_std(values[-window:])
    earlier = [
        sample_std(values[start : start + window]) for start in range(0, len(values) - window)
    ]
    if len(values) - window < thresholds.min_history:
        return VolatilityResult(
            window,
            to_output(latest, "A standard deviation"),
            0,
            None,
            None,
            "insufficient_history",
            found[-window].earlier.label,
            found[-1].later.label,
        )
    rank = percentile_rank(latest, [*earlier, latest])
    return VolatilityResult(
        window=window,
        latest=to_output(latest, "A standard deviation"),
        windows=len(earlier),
        percentile=rounded(rank),
        median_earlier=rounded(_median(earlier)),
        level="high" if rank >= thresholds.volatility_high_percentile else "not_high",
        first=found[-window].earlier.label,
        last=found[-1].later.label,
    )


@dataclass(frozen=True)
class AnomalyResult:
    change: Change
    reference: int  # earlier changes compared
    score: Decimal | None  # modified z; None when the MAD is zero
    level: str  # unusual | not_unusual | undefined | insufficient_history


def anomaly(found: Sequence[Change], thresholds: Thresholds) -> AnomalyResult | None:
    if not found:
        return None
    latest, earlier = found[-1], [change.value for change in found[:-1]]
    if len(earlier) < thresholds.min_history:
        return AnomalyResult(latest, len(earlier), None, "insufficient_history")
    score = modified_z(latest.value, earlier)
    if score is None:
        return AnomalyResult(latest, len(earlier), None, "undefined")
    level = "unusual" if abs(score) >= thresholds.anomaly_score else "not_unusual"
    return AnomalyResult(latest, len(earlier), rounded(score), level)


# --- Revisions -------------------------------------------------------------------------------


def revisions(session: Session, history: History) -> list[Revision]:
    """Values that were replaced, newest first: each superseded value and its successor."""
    if history.subject.kind != "series":
        return []
    old_rows = session.scalars(
        select(EconomicObservation)
        .where(
            EconomicObservation.series_id == history.subject.id,
            EconomicObservation.superseded_at.is_not(None),
        )
        .order_by(EconomicObservation.superseded_at.desc(), EconomicObservation.id.desc())
        .limit(MAX_REVISIONS)
    ).all()
    found: list[Revision] = []
    for old in old_rows:
        new = session.scalars(
            select(EconomicObservation).where(
                EconomicObservation.series_id == old.series_id,
                EconomicObservation.period_start == old.period_start,
                EconomicObservation.revision == old.revision + 1,
            )
        ).first()
        if new is None:
            continue
        change: Decimal | None = None
        if old.value is not None and new.value is not None:
            change = (
                relative_change(old.value, new.value)
                if history.subject.measure == "relative"
                else point_change(old.value, new.value)
            )
        found.append(
            Revision(
                label=old.period_label,
                start=old.period_start,
                previous=old.value,
                revised=new.value,
                previous_revision=old.revision,
                revised_at=old.superseded_at,
                previous_id=old.id,
                revised_id=new.id,
                change=rounded(change),
            )
        )
    return found


def series_with_data(session: Session, limit: int = 500) -> list[str]:
    return list(
        session.scalars(
            select(EconomicSeries.id)
            .where(EconomicSeries.observation_count > 1)
            .order_by(EconomicSeries.id)
            .limit(limit)
        ).all()
    )


def instruments_with_data(session: Session, limit: int = 200) -> list[str]:
    return list(
        session.scalars(
            select(Instrument.id)
            .where(Instrument.bar_count > 1)
            .order_by(Instrument.id)
            .limit(limit)
        ).all()
    )
