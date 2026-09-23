"""Stored observations that may supply a model input: Phase 2 data, with its provenance.

Only a series a model definition names as a source can be used, and only its latest
*current* (not superseded), *reported* value. The run records the series, the period,
the value, when RUMIN last confirmed it and the dataset's licence, so the input can be
traced to the exact capture it came from. Nothing is interpolated or filled in: if no
value is stored, the input must be entered.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ObservationStatus
from app.models import Dataset, EconomicObservation, EconomicSeries
from app.simulation.decimal_math import text


@dataclass(frozen=True)
class StoredObservation:
    series_id: str
    series_name: str
    series_unit: str
    frequency: str
    period_label: str
    period_start: str
    value: Decimal
    raw_value: str | None
    quality_status: str
    revision: int
    last_confirmed_at: str
    capture_id: int | None
    job_id: str
    dataset_id: str
    dataset_version: str
    license: str
    attribution: str | None

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data["value"] = text(self.value)
        return data


def latest_observation(session: Session, series_id: str) -> StoredObservation | None:
    """The latest current, reported value of a series, or None if nothing is stored."""
    series = session.get(EconomicSeries, series_id)
    if series is None:
        return None
    row = session.scalars(
        select(EconomicObservation)
        .where(
            EconomicObservation.series_id == series_id,
            EconomicObservation.superseded_at.is_(None),
            EconomicObservation.status == ObservationStatus.REPORTED,
            EconomicObservation.value.is_not(None),
        )
        .order_by(EconomicObservation.period_start.desc())
        .limit(1)
    ).first()
    if row is None or row.value is None:
        return None
    dataset = session.get(Dataset, series.dataset_id)
    return StoredObservation(
        series_id=series.id,
        series_name=series.name,
        series_unit=series.unit,
        frequency=series.frequency.value,
        period_label=row.period_label,
        period_start=row.period_start.isoformat(),
        value=row.value,
        raw_value=row.raw_value,
        quality_status=row.quality_status.value,
        revision=row.revision,
        last_confirmed_at=row.last_seen_at.isoformat(),
        capture_id=row.capture_id,
        job_id=str(row.last_seen_job_id),
        dataset_id=series.dataset_id,
        dataset_version=dataset.version if dataset else "",
        license=dataset.license if dataset else "",
        attribution=dataset.attribution if dataset else None,
    )
