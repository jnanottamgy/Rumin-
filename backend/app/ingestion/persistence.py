"""Writing checked records to the database: captures, observations, price bars, issues.

**Revisions, not overwrites.** For each period (or trade date) there is at most one
*current* row. Receiving the same content again only updates "last seen". Receiving
different content — a new value, a value that became missing, a changed provider flag —
marks the current row as superseded (when, and by which job) and adds a new row with the
next revision number. Nothing is deleted or edited in place, so the full history of what
each provider said, and when RUMIN heard it, is kept.

Records absent from a response are left untouched: absence is not evidence that a
provider withdrew a value (the quality rules note unexpected gaps instead).
"""

from __future__ import annotations

import gzip
import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ObservationStatus, PriceAdjustment
from app.ingestion.http import SECRET_PARAMETERS
from app.ingestion.providers.base import Capture
from app.ingestion.quality import CheckedObservation, CheckedPriceBar, Finding
from app.models import (
    DataQualityIssue,
    EconomicObservation,
    EconomicSeries,
    Instrument,
    PriceBar,
    SourceCapture,
)

_FLAGS_LENGTH = 64  # economic_observations.provider_flags
_KEY_LENGTH = 32  # data_quality_issues.record_key
_LOCATOR_LENGTH = 1000  # source_captures.locator


@dataclass
class WriteCounts:
    new: int = 0
    revised: int = 0
    unchanged: int = 0


# --- Captures -----------------------------------------------------------------------------


def store_captures(
    session: Session,
    *,
    job_id: uuid.UUID,
    provider_id: str,
    captures: Sequence[Capture],
    keep_bodies: bool,
) -> list[SourceCapture]:
    """Store what was received, in order (a record's ``capture_index`` points into it)."""
    rows = []
    for capture in captures:
        params = (
            {
                name: "[redacted]" if name.lower() in SECRET_PARAMETERS else value
                for name, value in capture.request_params.items()
            }
            if capture.request_params is not None
            else None
        )
        locator = capture.locator
        if len(locator) > _LOCATOR_LENGTH:
            locator = locator[: _LOCATOR_LENGTH - 1] + "…"
        row = SourceCapture(
            job_id=job_id,
            provider_id=provider_id,
            kind=capture.kind,
            locator=locator,
            request_params=params,
            http_status=capture.http_status,
            received_at=capture.received_at,
            content_type=capture.content_type[:100] if capture.content_type else None,
            size_bytes=len(capture.body),
            sha256=hashlib.sha256(capture.body).hexdigest(),
            # mtime=0 keeps the compressed bytes deterministic for identical content.
            body_gzip=gzip.compress(capture.body, mtime=0) if keep_bodies else None,
            provider_last_updated=capture.provider_last_updated,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _capture_id(captures: Sequence[SourceCapture], index: int | None) -> int | None:
    if index is None or not 0 <= index < len(captures):
        return None
    return captures[index].id


# --- Economic observations ----------------------------------------------------------------


def _same_observation(row: EconomicObservation, checked: CheckedObservation) -> bool:
    # Numbers are compared as numbers: 5.10 and 5.1 are the same value.
    return (
        row.status is checked.status
        and row.value == checked.value
        and row.provider_flags == _flags(checked.flags)
    )


def _flags(flags: str | None) -> str | None:
    # A longer flag is cut to fit; its full text stays in the provider_flag issue and in
    # the stored response.
    return flags[:_FLAGS_LENGTH] if flags else None


def save_observations(
    session: Session,
    *,
    job_id: uuid.UUID,
    series: EconomicSeries,
    accepted: Sequence[CheckedObservation],
    captures: Sequence[SourceCapture],
    now: datetime,
) -> tuple[WriteCounts, dict[date, EconomicObservation]]:
    """Insert, confirm or revise each accepted observation. Returns what happened and the
    current row for every period written (to link quality issues to it)."""
    counts = WriteCounts()
    current = {
        row.period_start: row
        for row in session.scalars(
            select(EconomicObservation).where(
                EconomicObservation.series_id == series.id,
                EconomicObservation.superseded_at.is_(None),
            )
        )
    }
    result: dict[date, EconomicObservation] = {}
    to_insert: list[tuple[CheckedObservation, int]] = []
    for checked in accepted:
        row = current.get(checked.period.start)
        if row is None:
            counts.new += 1
            to_insert.append((checked, 1))
        elif _same_observation(row, checked):
            counts.unchanged += 1
            row.last_seen_job_id = job_id
            row.last_seen_at = now
            row.quality_status = checked.quality  # re-assessed with the current rules
            result[checked.period.start] = row
        else:
            counts.revised += 1
            row.superseded_at = now
            row.superseded_by_job_id = job_id
            to_insert.append((checked, row.revision + 1))
    # Supersede first, so the "one current row per period" index is never violated.
    session.flush()
    for checked, revision in to_insert:
        row = EconomicObservation(
            series_id=series.id,
            period_start=checked.period.start,
            period_label=checked.period.label,
            value=checked.value,
            raw_value=checked.raw_value,
            status=checked.status,
            quality_status=checked.quality,
            provider_flags=_flags(checked.flags),
            revision=revision,
            first_seen_job_id=job_id,
            first_seen_at=now,
            last_seen_job_id=job_id,
            last_seen_at=now,
            capture_id=_capture_id(captures, checked.capture_index),
        )
        session.add(row)
        result[checked.period.start] = row
    session.flush()
    return counts, result


def refresh_series_summary(session: Session, series: EconomicSeries) -> None:
    current = (
        EconomicObservation.series_id == series.id,
        EconomicObservation.superseded_at.is_(None),
    )
    reported = (*current, EconomicObservation.status == ObservationStatus.REPORTED)
    first, last, count = session.execute(
        select(
            func.min(EconomicObservation.period_start),
            func.max(EconomicObservation.period_start),
            func.count(),
        ).where(*reported)
    ).one()
    missing = session.scalar(
        select(func.count()).where(
            *current, EconomicObservation.status == ObservationStatus.MISSING
        )
    )
    series.first_period = first
    series.last_period = last
    series.observation_count = count
    series.missing_count = missing or 0


# --- Price bars ---------------------------------------------------------------------------


def _same_bar(row: PriceBar, checked: CheckedPriceBar) -> bool:
    return (
        row.open == checked.open
        and row.high == checked.high
        and row.low == checked.low
        and row.close == checked.close
        and row.adjusted_close == checked.adjusted_close
        and row.volume == checked.volume
    )


def save_price_bars(
    session: Session,
    *,
    job_id: uuid.UUID,
    instrument: Instrument,
    dataset_id: str,
    adjustment: PriceAdjustment,
    accepted: Sequence[CheckedPriceBar],
    capture: SourceCapture | None,
    now: datetime,
) -> tuple[WriteCounts, dict[date, PriceBar]]:
    counts = WriteCounts()
    current = {
        row.trade_date: row
        for row in session.scalars(
            select(PriceBar).where(
                PriceBar.instrument_id == instrument.id,
                PriceBar.dataset_id == dataset_id,
                PriceBar.superseded_at.is_(None),
            )
        )
    }
    result: dict[date, PriceBar] = {}
    to_insert: list[tuple[CheckedPriceBar, int]] = []
    for checked in accepted:
        row = current.get(checked.trade_date)
        if row is None:
            counts.new += 1
            to_insert.append((checked, 1))
        elif _same_bar(row, checked):
            counts.unchanged += 1
            row.last_seen_job_id = job_id
            row.last_seen_at = now
            row.quality_status = checked.quality
            row.source_row = checked.line
            result[checked.trade_date] = row
        else:
            counts.revised += 1
            row.superseded_at = now
            row.superseded_by_job_id = job_id
            to_insert.append((checked, row.revision + 1))
    session.flush()
    for checked, revision in to_insert:
        row = PriceBar(
            instrument_id=instrument.id,
            dataset_id=dataset_id,
            trade_date=checked.trade_date,
            open=checked.open,
            high=checked.high,
            low=checked.low,
            close=checked.close,
            adjusted_close=checked.adjusted_close,
            volume=checked.volume,
            currency=instrument.currency,
            adjustment=adjustment,
            quality_status=checked.quality,
            source_row=checked.line,
            revision=revision,
            first_seen_job_id=job_id,
            first_seen_at=now,
            last_seen_job_id=job_id,
            last_seen_at=now,
            capture_id=capture.id if capture is not None else None,
        )
        session.add(row)
        result[checked.trade_date] = row
    session.flush()
    return counts, result


def refresh_instrument_summary(session: Session, instrument: Instrument) -> None:
    first, last, count = session.execute(
        select(
            func.min(PriceBar.trade_date),
            func.max(PriceBar.trade_date),
            func.count(func.distinct(PriceBar.trade_date)),
        ).where(PriceBar.instrument_id == instrument.id, PriceBar.superseded_at.is_(None))
    ).one()
    instrument.first_trade_date = first
    instrument.last_trade_date = last
    instrument.bar_count = count


# --- Quality issues -----------------------------------------------------------------------


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def record_issues(
    session: Session,
    findings: Sequence[Finding],
    *,
    job_id: uuid.UUID,
    now: datetime,
    series_id: str | None = None,
    instrument_id: str | None = None,
    observation_id: int | None = None,
    price_bar_id: int | None = None,
) -> None:
    for finding in findings:
        key = finding.record_key
        raw = _jsonable(finding.raw) if finding.raw is not None else None
        session.add(
            DataQualityIssue(
                job_id=job_id,
                series_id=series_id,
                instrument_id=instrument_id,
                observation_id=observation_id,
                price_bar_id=price_bar_id,
                rule=finding.rule,
                severity=finding.severity,
                outcome=finding.outcome,
                message=finding.message,
                record_key=key[:_KEY_LENGTH] if key else None,
                raw_record=raw if isinstance(raw, dict) else None,
                detected_at=now,
            )
        )
