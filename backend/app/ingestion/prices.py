"""Importing a licensed price file: manifest → instrument and dataset → checked bars.

A price file never arrives alone. Its **manifest** (JSON) says what the file is — which
instrument, in which currency, whether prices are adjusted — and where it came from: the
licence the user holds and the attribution it requires. RUMIN stores that with the prices
and shows it wherever they appear. Example::

    {
      "dataset": {
        "id": "broker-eod-reliance",
        "name": "End-of-day prices — broker export",
        "description": "Daily prices exported from our broker's terminal.",
        "license": "Broker terminal licence — internal use only",
        "attribution": "Source: <broker name>",
        "provenance_note": "Exported by <person> on 2026-09-01."
      },
      "instrument": {
        "id": "xnse-reliance",
        "name": "Reliance Industries Ltd",
        "instrument_type": "equity",
        "isin": "INE002A01018",
        "exchange_mic": "XNSE",
        "symbol": "RELIANCE",
        "currency": "INR"
      },
      "adjustment": "unadjusted"
    }
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domain.enums import (
    DatasetKind,
    EntityKind,
    InstrumentType,
    IssueSeverity,
    JobTargetKind,
    PriceAdjustment,
)
from app.ingestion import jobs
from app.ingestion.catalog import sync_providers
from app.ingestion.errors import ProviderError
from app.ingestion.jobs import ItemCounts
from app.ingestion.logs import log_event
from app.ingestion.normalize import isin_is_valid
from app.ingestion.persistence import (
    record_issues,
    refresh_instrument_summary,
    save_price_bars,
    store_captures,
)
from app.ingestion.providers.base import PriceFileSource, ProviderProfile
from app.ingestion.quality import Finding, assess_price_rows
from app.models import Dataset, Entity, IngestionJob, Instrument, PriceBar

logger = logging.getLogger(__name__)

MAX_MANIFEST_BYTES = 64 * 1024

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=500)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ManifestDataset(_Model):
    id: Identifier
    name: Name
    description: Text
    license: Name
    license_url: HttpsUrl | None = None
    terms_url: HttpsUrl | None = None
    homepage_url: HttpsUrl | None = None
    attribution: Text
    provenance_note: Text
    # True for sample or test files: the data is then labelled illustrative everywhere.
    is_illustrative: bool = False


class ManifestInstrument(_Model):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,95}$")]
    name: Name
    instrument_type: InstrumentType
    isin: str | None = None
    exchange_mic: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{4}$")]
    symbol: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9&._-]{0,31}$")]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    country_id: str | None = None

    @field_validator("isin")
    @classmethod
    def _valid_isin(cls, value: str | None) -> str | None:
        if value is not None and not isin_is_valid(value):
            raise ValueError("not a valid ISIN (format or check digit)")
        return value


class PriceManifest(_Model):
    dataset: ManifestDataset
    instrument: ManifestInstrument
    adjustment: PriceAdjustment


class ManifestError(Exception):
    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or []


def read_manifest(path: Path) -> PriceManifest:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError(f"The manifest is larger than {MAX_MANIFEST_BYTES:,} bytes.")
        return PriceManifest.model_validate_json(path.read_bytes())
    except OSError as error:
        raise ManifestError(f"The manifest {path.name} cannot be read.") from error
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in error.errors()
        ]
        raise ManifestError(f"{path.name} is not a valid price manifest.", problems) from error


@dataclass
class ImportResult:
    job: IngestionJob
    notes: list[str] = field(default_factory=list)


def _upsert_dataset(
    session: Session, spec: ManifestDataset, profile: ProviderProfile, now: datetime
) -> Dataset:
    dataset = session.get(Dataset, spec.id)
    if dataset is not None and (
        dataset.kind is not DatasetKind.PROVIDER or dataset.provider_id != profile.id
    ):
        raise ManifestError(
            f"Dataset '{spec.id}' already exists and does not hold imported price files; "
            "choose another dataset id."
        )
    dataset = dataset or Dataset(id=spec.id, kind=DatasetKind.PROVIDER, loaded_at=now)
    dataset.version = "user import"
    dataset.name = spec.name
    dataset.description = spec.description
    dataset.is_illustrative = spec.is_illustrative
    dataset.provenance_note = spec.provenance_note
    dataset.license = spec.license
    dataset.license_url = spec.license_url
    dataset.terms_url = spec.terms_url
    dataset.homepage_url = spec.homepage_url
    dataset.attribution = spec.attribution
    dataset.update_frequency = "When the user imports a new file."
    dataset.provider_id = profile.id
    dataset.provider_dataset_code = None
    session.add(dataset)
    return dataset


def _upsert_instrument(
    session: Session, spec: ManifestInstrument, dataset: Dataset, notes: list[str]
) -> Instrument:
    """Identifiers are never merged: any conflict with a stored instrument is an error."""
    existing = session.get(Instrument, spec.id)
    by_listing = session.scalar(
        select(Instrument).where(
            Instrument.exchange_mic == spec.exchange_mic, Instrument.symbol == spec.symbol
        )
    )
    by_isin = (
        session.scalar(select(Instrument).where(Instrument.isin == spec.isin))
        if spec.isin
        else None
    )
    for other, what in ((by_listing, "exchange and symbol"), (by_isin, "ISIN")):
        if other is not None and other.id != spec.id:
            raise ManifestError(
                f"The {what} of '{spec.id}' already belong to instrument '{other.id}'."
            )
    if existing is not None:
        if (existing.exchange_mic, existing.symbol) != (spec.exchange_mic, spec.symbol):
            raise ManifestError(
                f"Instrument '{spec.id}' is stored as {existing.exchange_mic}:{existing.symbol}, "
                f"not {spec.exchange_mic}:{spec.symbol}."
            )
        if existing.currency != spec.currency:
            raise ManifestError(
                f"Instrument '{spec.id}' is priced in {existing.currency}; this file says "
                f"{spec.currency}. RUMIN does not convert or mix currencies."
            )
        if existing.isin and spec.isin and existing.isin != spec.isin:
            raise ManifestError(f"Instrument '{spec.id}' has ISIN {existing.isin}.")
    instrument = existing or Instrument(id=spec.id, dataset_id=dataset.id)
    instrument.name = spec.name
    instrument.instrument_type = spec.instrument_type
    instrument.isin = spec.isin or instrument.isin
    instrument.exchange_mic = spec.exchange_mic
    instrument.symbol = spec.symbol
    instrument.currency = spec.currency
    if spec.country_id:
        country = session.get(Entity, spec.country_id)
        if country is not None and country.kind == EntityKind.COUNTRY:
            instrument.country_id = spec.country_id
        else:
            notes.append(f"Country '{spec.country_id}' was not found; it is not linked.")
    session.add(instrument)
    return instrument


def _check_adjustment(
    session: Session, instrument_id: str, dataset_id: str, adjustment: PriceAdjustment
) -> None:
    stored = session.scalar(
        select(PriceBar.adjustment)
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.dataset_id == dataset_id,
            PriceBar.superseded_at.is_(None),
        )
        .limit(1)
    )
    if stored is not None and stored is not adjustment:
        raise ManifestError(
            f"Dataset '{dataset_id}' holds {stored} prices for this instrument; the manifest "
            f"declares {adjustment}. Import them into a separate dataset."
        )


def import_price_file(
    session: Session,
    source: PriceFileSource,
    *,
    manifest: PriceManifest,
    file_path: Path,
    profiles: dict[str, ProviderProfile],
    today: date,
    keep_bodies: bool = True,
    clock: Callable[[], datetime] = utcnow,
) -> ImportResult:
    """Import one file. Manifest problems raise ``ManifestError`` before any job starts;
    everything after that is recorded on the job, including an unreadable file."""
    notes: list[str] = []
    sync_providers(session, profiles)
    dataset = _upsert_dataset(session, manifest.dataset, source.profile, clock())
    session.flush()
    instrument = _upsert_instrument(session, manifest.instrument, dataset, notes)
    session.flush()
    _check_adjustment(session, instrument.id, dataset.id, manifest.adjustment)

    job = jobs.create_job(
        session,
        provider_id=source.profile.id,
        dataset_id=dataset.id,
        parameters={
            "file": file_path.name,
            "instrument": instrument.id,
            "adjustment": str(manifest.adjustment),
        },
        now=clock(),
    )
    item = jobs.add_item(
        session,
        job,
        target_kind=JobTargetKind.INSTRUMENT,
        label=f"{instrument.id} ({instrument.exchange_mic}:{instrument.symbol})",
        instrument_id=instrument.id,
    )
    jobs.start_job(job, clock())
    jobs.start_item(item, clock())
    session.commit()

    try:
        read = source.read_price_file(file_path)
    except ProviderError as error:
        jobs.fail_item(item, error.code, error.message, clock())
    else:
        try:
            now = clock()
            captures = store_captures(
                session,
                job_id=job.id,
                provider_id=source.profile.id,
                captures=read.captures,
                keep_bodies=keep_bodies,
            )
            job.bytes_received = sum(capture.size_bytes for capture in captures)
            assessment = assess_price_rows(read.rows, today)
            written, bars = save_price_bars(
                session,
                job_id=job.id,
                instrument=instrument,
                dataset_id=dataset.id,
                adjustment=manifest.adjustment,
                accepted=assessment.accepted,
                capture=captures[0] if captures else None,
                now=now,
            )
            findings: list[Finding] = [*assessment.rejected, *assessment.file_findings]
            record_issues(session, findings, job_id=job.id, now=now, instrument_id=instrument.id)
            for bar in assessment.accepted:
                if bar.findings:
                    record_issues(
                        session,
                        bar.findings,
                        job_id=job.id,
                        now=now,
                        instrument_id=instrument.id,
                        price_bar_id=bars[bar.trade_date].id,
                    )
                    findings.extend(bar.findings)
            refresh_instrument_summary(session, instrument)
            counts = ItemCounts(
                received=len(read.rows),
                new=written.new,
                revised=written.revised,
                unchanged=written.unchanged,
                rejected=len(assessment.rejected),
                warnings=sum(f.severity is IssueSeverity.WARNING for f in findings),
                errors=sum(f.severity is IssueSeverity.ERROR for f in findings),
            )
        except Exception:
            logger.exception("event=import.store_failed job=%s", job.id)
            session.rollback()
            jobs.fail_item(
                item,
                "storage_error",
                "The file was read but could not be stored; nothing from it was saved. See "
                "the server log for details.",
                clock(),
            )
        else:
            if counts.received and counts.rejected == counts.received:
                jobs.fail_item(
                    item,
                    "all_records_rejected",
                    f"All {counts.received} rows failed validation; see the quality issues.",
                    clock(),
                    counts,
                )
            else:
                jobs.succeed_item(item, counts, clock())

    jobs.finish_job(job, [item], clock())
    session.commit()
    log_event(
        logger,
        "import.finished",
        level=logging.INFO if job.status.startswith("completed") else logging.WARNING,
        job=job.id,
        status=job.status,
        instrument=instrument.id,
        rows=item.records_received,
        new=item.records_new,
        revised=item.records_revised,
        rejected=item.records_rejected,
    )
    return ImportResult(job=job, notes=notes)


def manifest_template() -> str:
    """A blank manifest to fill in (printed by the command line)."""
    return json.dumps(
        {
            "dataset": {
                "id": "my-price-source",
                "name": "…",
                "description": "…",
                "license": "The licence under which you hold this file",
                "attribution": "The attribution your licence requires",
                "provenance_note": "Where and when the file was obtained",
                "is_illustrative": False,
            },
            "instrument": {
                "id": "xnse-symbol",
                "name": "…",
                "instrument_type": "equity",
                "isin": None,
                "exchange_mic": "XNSE",
                "symbol": "SYMBOL",
                "currency": "INR",
                "country_id": None,
            },
            "adjustment": "unadjusted",
        },
        indent=2,
    )
