"""Importing licensed price files. Every file and manifest here is SYNTHETIC: made-up
prices for a made-up instrument (its ISIN is invented, with a valid check digit)."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import (
    DatasetKind,
    IssueOutcome,
    JobItemStatus,
    JobStatus,
    PriceAdjustment,
    QualityStatus,
)
from app.ingestion import jobs
from app.ingestion.prices import (
    ImportResult,
    ManifestError,
    PriceManifest,
    import_price_file,
    read_manifest,
)
from app.ingestion.providers.price_file import PriceFileProvider
from app.ingestion.registry import PROFILES
from app.models import DataQualityIssue, Dataset, Instrument, PriceBar, SourceCapture

TODAY = date(2026, 9, 23)
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
CSV = (
    "date,open,high,low,close,volume\n"
    "2026-09-21,100.10,101.00,99.50,100.75,1500\n"
    "2026-09-22,100.75,102.25,100.00,101.90,1700\n"
)
MANIFEST: dict[str, Any] = {
    "dataset": {
        "id": "test-prices",
        "name": "Synthetic price file",
        "description": "Synthetic prices for tests.",
        "license": "Test licence (synthetic)",
        "attribution": "Synthetic attribution",
        "provenance_note": "Generated for tests; not market data.",
        "is_illustrative": True,
    },
    "instrument": {
        "id": "xnse-testco",
        "name": "Synthetic Test Co",
        "instrument_type": "equity",
        "isin": "INTESTCO0007",
        "exchange_mic": "XNSE",
        "symbol": "TESTCO",
        "currency": "INR",
    },
    "adjustment": "unadjusted",
}


def manifest(**changes: Any) -> PriceManifest:
    data = copy.deepcopy(MANIFEST)
    for path, value in changes.items():
        section, _, key = path.partition("__")
        if key:
            data[section][key] = value
        else:
            data[section] = value
    return PriceManifest.model_validate(data)


def write(tmp_path: Path, text: str, name: str = "prices.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def do_import(session: Session, file_path: Path, spec: PriceManifest | None = None) -> ImportResult:
    return import_price_file(
        session,
        PriceFileProvider(max_bytes=1024 * 1024, clock=lambda: NOW),
        manifest=spec or manifest(),
        file_path=file_path,
        profiles=PROFILES,
        today=TODAY,
        clock=lambda: NOW,
    )


def bars(session: Session, *, current_only: bool = True) -> list[PriceBar]:
    query = select(PriceBar).order_by(PriceBar.trade_date, PriceBar.revision)
    if current_only:
        query = query.where(PriceBar.superseded_at.is_(None))
    return list(session.scalars(query))


def test_a_file_is_stored_exactly_with_its_licence_and_source(
    ingestion_session: Session, tmp_path: Path
) -> None:
    session = ingestion_session
    path = write(tmp_path, CSV)
    job = do_import(session, path).job

    assert job.status is JobStatus.COMPLETED
    assert (job.records_received, job.records_new) == (2, 2)
    first, second = bars(session)
    assert (first.trade_date, first.open, first.close, first.volume) == (
        date(2026, 9, 21),
        Decimal("100.1"),
        Decimal("100.75"),
        1500,
    )
    assert (first.currency, first.adjustment, first.quality_status, first.source_row) == (
        "INR",
        PriceAdjustment.UNADJUSTED,
        QualityStatus.VALIDATED,
        2,
    )
    assert second.close == Decimal("101.9")

    capture = session.get_one(SourceCapture, first.capture_id)
    assert capture.locator == "prices.csv"  # the name only, never a local path
    assert capture.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert job.bytes_received == len(path.read_bytes())

    dataset = session.get_one(Dataset, "test-prices")
    assert (dataset.kind, dataset.provider_id) == (DatasetKind.PROVIDER, "price-file")
    assert dataset.license == "Test licence (synthetic)"
    assert dataset.attribution == "Synthetic attribution"
    assert dataset.is_illustrative is True

    instrument = session.get_one(Instrument, "xnse-testco")
    assert (instrument.first_trade_date, instrument.last_trade_date, instrument.bar_count) == (
        date(2026, 9, 21),
        date(2026, 9, 22),
        2,
    )


def test_reimporting_the_same_file_changes_nothing(
    ingestion_session: Session, tmp_path: Path
) -> None:
    session = ingestion_session
    path = write(tmp_path, CSV)
    do_import(session, path)
    job = do_import(session, path).job
    assert (job.records_new, job.records_unchanged, job.records_revised) == (0, 2, 0)
    assert len(bars(session, current_only=False)) == 2


def test_a_corrected_file_creates_revisions_and_keeps_the_old_prices(
    ingestion_session: Session, tmp_path: Path
) -> None:
    session = ingestion_session
    do_import(session, write(tmp_path, CSV))
    corrected = CSV.replace("101.90,1700", "101.95,1700")
    job = do_import(session, write(tmp_path, corrected, "corrected.csv")).job

    assert (job.records_revised, job.records_unchanged) == (1, 1)
    history = [bar for bar in bars(session, current_only=False) if bar.trade_date.day == 22]
    assert [(bar.revision, bar.close) for bar in history] == [
        (1, Decimal("101.9")),
        (2, Decimal("101.95")),
    ]
    assert history[0].superseded_by_job_id == job.id


def test_bad_rows_are_rejected_and_recorded(ingestion_session: Session, tmp_path: Path) -> None:
    session = ingestion_session
    text = CSV + "2026-09-23,10,9,11,10,5\n" + "23/09/2026,1,1,1,1,1\n"
    job = do_import(session, write(tmp_path, text)).job

    assert job.status is JobStatus.COMPLETED_WITH_WARNINGS
    assert (job.records_received, job.records_rejected, job.records_new) == (4, 2, 2)
    found = session.scalars(
        select(DataQualityIssue).where(DataQualityIssue.outcome == IssueOutcome.REJECTED)
    ).all()
    assert sorted(issue.rule for issue in found) == ["high_below_low", "invalid_date"]
    assert all(issue.raw_record and "line" in issue.raw_record for issue in found)


def test_an_unreadable_file_is_recorded_as_a_failed_job(
    ingestion_session: Session, tmp_path: Path
) -> None:
    session = ingestion_session
    job = do_import(session, write(tmp_path, "date,close\n2026-09-21,100\n")).job
    (item,) = jobs.job_items(session, job)
    assert (item.status, item.error_code) == (JobItemStatus.FAILED, "invalid_file")
    assert item.error_message is not None and "open" in item.error_message
    assert job.status is JobStatus.FAILED
    assert bars(session) == []


def test_manifest_problems_are_listed_before_anything_runs(tmp_path: Path) -> None:
    broken = copy.deepcopy(MANIFEST)
    broken["instrument"]["isin"] = "INTESTCO0008"  # wrong check digit
    broken["instrument"]["exchange_mic"] = "NSE"
    broken["dataset"]["licence"] = "a misspelt field"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        read_manifest(path)
    problems = "\n".join(caught.value.problems)
    assert "instrument.isin" in problems
    assert "instrument.exchange_mic" in problems
    assert "dataset.licence" in problems


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"instrument__currency": "USD"}, "does not convert or mix currencies"),
        ({"instrument__id": "xnse-other"}, "already belong to instrument"),
        ({"adjustment": "adjusted"}, "separate dataset"),
        ({"dataset__id": "rumin-sample"}, "choose another dataset id"),
    ],
)
def test_conflicting_declarations_are_refused(
    ingestion_session: Session, tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    session = ingestion_session
    do_import(session, write(tmp_path, CSV))
    with pytest.raises(ManifestError, match=message):
        do_import(session, write(tmp_path, CSV), manifest(**changes))
    session.rollback()
