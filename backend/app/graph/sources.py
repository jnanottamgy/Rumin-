"""Reads everything the graph is built from, as plain immutable records.

This is the build's only contact with the Phase 1 and Phase 2 tables. Everything after it
(rules, resolution, validation) works on these records, so it can be tested without a
database, and the snapshot's fingerprint says exactly what a build was made from.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import (
    DatasetKind,
    EvidenceLevel,
    Frequency,
    InstrumentType,
    MeasureType,
    Polarity,
    RelationshipType,
    Strength,
    ValueKind,
    VariableCategory,
)
from app.models import (
    Company,
    Country,
    Dataset,
    EconomicSeries,
    EconomicVariable,
    Industry,
    Instrument,
    Relationship,
)

# Bump when a construction rule changes what it produces: a build with other rules is a
# different graph, even from identical sources.
RULES_VERSION = "1"


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    kind: DatasetKind
    version: str
    name: str
    is_illustrative: bool
    checksum_sha256: str | None
    license: str
    attribution: str | None
    provider_id: str | None
    loaded_at: datetime


@dataclass(frozen=True)
class CountryRecord:
    id: str
    name: str
    description: str
    is_fictional: bool
    iso_alpha2: str
    currency_code: str
    reference: str | None
    reference_url: str | None
    dataset_id: str


@dataclass(frozen=True)
class IndustryRecord:
    id: str
    name: str
    description: str
    is_fictional: bool
    classification_system: str
    classification_code: str
    reference: str | None
    reference_url: str | None
    dataset_id: str


@dataclass(frozen=True)
class CompanyRecord:
    id: str
    name: str
    description: str
    is_fictional: bool
    industry_id: str
    country_id: str
    reference: str | None
    reference_url: str | None
    dataset_id: str


@dataclass(frozen=True)
class VariableRecord:
    id: str
    name: str
    description: str
    is_fictional: bool
    unit: str
    frequency: Frequency
    category: VariableCategory
    value_kind: ValueKind
    country_id: str | None
    reference: str | None
    reference_url: str | None
    dataset_id: str


@dataclass(frozen=True)
class RelationshipRecord:
    id: str
    type: RelationshipType
    source_id: str
    target_id: str
    polarity: Polarity
    strength: Strength
    evidence_level: EvidenceLevel
    description: str
    rationale: str
    reference: str | None
    dataset_id: str


@dataclass(frozen=True)
class SeriesRecord:
    id: str
    dataset_id: str
    provider_series_key: str
    provider_code: str
    name: str
    description: str
    source_organization: str | None
    measure_type: MeasureType
    unit: str
    currency: str | None
    frequency: Frequency
    country_iso3: str | None
    country_id: str | None
    variable_id: str | None
    variable_relation: str | None
    created_at: datetime
    last_successful_ingestion_at: datetime | None


@dataclass(frozen=True)
class InstrumentRecord:
    id: str
    name: str
    instrument_type: InstrumentType
    isin: str | None
    exchange_mic: str
    symbol: str
    currency: str
    country_id: str | None
    dataset_id: str
    created_at: datetime


@dataclass(frozen=True)
class SourceSnapshot:
    """Every record the graph is built from, sorted by ID (so builds are deterministic)."""

    datasets: dict[str, DatasetRecord]
    countries: tuple[CountryRecord, ...] = ()
    industries: tuple[IndustryRecord, ...] = ()
    companies: tuple[CompanyRecord, ...] = ()
    variables: tuple[VariableRecord, ...] = ()
    relationships: tuple[RelationshipRecord, ...] = ()
    series: tuple[SeriesRecord, ...] = ()
    instruments: tuple[InstrumentRecord, ...] = ()

    def record_counts(self) -> dict[str, int]:
        return {
            "countries": len(self.countries),
            "industries": len(self.industries),
            "companies": len(self.companies),
            "economic_variables": len(self.variables),
            "relationships": len(self.relationships),
            "economic_series": len(self.series),
            "instruments": len(self.instruments),
        }

    def summary(self) -> dict[str, Any]:
        """What a build read, stored with the build (datasets with versions, counts)."""
        return {
            "rules_version": RULES_VERSION,
            "datasets": [
                {
                    "id": dataset.id,
                    "kind": dataset.kind.value,
                    "version": dataset.version,
                    "checksum_sha256": dataset.checksum_sha256,
                    "is_illustrative": dataset.is_illustrative,
                }
                for dataset in sorted(self.datasets.values(), key=lambda item: item.id)
            ],
            "records": self.record_counts(),
        }

    def fingerprint(self) -> str:
        """SHA-256 over every record and the rules version. Equal fingerprints mean the
        same graph would be built; a different one means the stored graph is out of date."""
        payload = {
            "rules_version": RULES_VERSION,
            "datasets": [_fields(item) for item in sorted(self.datasets.values(), key=_by_id)],
            "countries": [_fields(item) for item in self.countries],
            "industries": [_fields(item) for item in self.industries],
            "companies": [_fields(item) for item in self.companies],
            "variables": [_fields(item) for item in self.variables],
            "relationships": [_fields(item) for item in self.relationships],
            "series": [_fields(item) for item in self.series],
            "instruments": [_fields(item) for item in self.instruments],
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fields(record: object) -> dict[str, object]:
    """A record's fields as a dict. The records are flat, so this equals
    ``dataclasses.asdict`` without its deep copies (several times faster)."""
    return {field.name: getattr(record, field.name) for field in fields(record)}  # type: ignore[arg-type]


def _by_id(item: DatasetRecord) -> str:
    return item.id


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Cannot fingerprint {type(value).__name__}")


def read_sources(session: Session) -> SourceSnapshot:
    """Read the current source tables. Read-only."""
    datasets = {
        row.id: DatasetRecord(
            id=row.id,
            kind=row.kind,
            version=row.version,
            name=row.name,
            is_illustrative=row.is_illustrative,
            checksum_sha256=row.checksum_sha256,
            license=row.license,
            attribution=row.attribution,
            provider_id=row.provider_id,
            loaded_at=row.loaded_at,
        )
        for row in session.scalars(select(Dataset).order_by(Dataset.id))
    }
    return SourceSnapshot(
        datasets=datasets,
        countries=tuple(
            CountryRecord(
                id=row.id,
                name=row.name,
                description=row.description,
                is_fictional=row.is_fictional,
                iso_alpha2=row.iso_alpha2,
                currency_code=row.currency_code,
                reference=row.reference,
                reference_url=row.reference_url,
                dataset_id=row.dataset_id,
            )
            for row in session.scalars(select(Country).order_by(Country.id))
        ),
        industries=tuple(
            IndustryRecord(
                id=row.id,
                name=row.name,
                description=row.description,
                is_fictional=row.is_fictional,
                classification_system=row.classification_system,
                classification_code=row.classification_code,
                reference=row.reference,
                reference_url=row.reference_url,
                dataset_id=row.dataset_id,
            )
            for row in session.scalars(select(Industry).order_by(Industry.id))
        ),
        companies=tuple(
            CompanyRecord(
                id=row.id,
                name=row.name,
                description=row.description,
                is_fictional=row.is_fictional,
                industry_id=row.industry_id,
                country_id=row.country_id,
                reference=row.reference,
                reference_url=row.reference_url,
                dataset_id=row.dataset_id,
            )
            for row in session.scalars(select(Company).order_by(Company.id))
        ),
        variables=tuple(
            VariableRecord(
                id=row.id,
                name=row.name,
                description=row.description,
                is_fictional=row.is_fictional,
                unit=row.unit,
                frequency=row.frequency,
                category=row.category,
                value_kind=row.value_kind,
                country_id=row.country_id,
                reference=row.reference,
                reference_url=row.reference_url,
                dataset_id=row.dataset_id,
            )
            for row in session.scalars(select(EconomicVariable).order_by(EconomicVariable.id))
        ),
        relationships=tuple(
            RelationshipRecord(
                id=row.id,
                type=row.type,
                source_id=row.source_id,
                target_id=row.target_id,
                polarity=row.polarity,
                strength=row.strength,
                evidence_level=row.evidence_level,
                description=row.description,
                rationale=row.rationale,
                reference=row.reference,
                dataset_id=row.dataset_id,
            )
            for row in session.scalars(select(Relationship).order_by(Relationship.id))
        ),
        series=tuple(
            SeriesRecord(
                id=row.id,
                dataset_id=row.dataset_id,
                provider_series_key=row.provider_series_key,
                provider_code=row.provider_code,
                name=row.name,
                description=row.description,
                source_organization=row.source_organization,
                measure_type=row.measure_type,
                unit=row.unit,
                currency=row.currency,
                frequency=row.frequency,
                country_iso3=row.country_iso3,
                country_id=row.country_id,
                variable_id=row.variable_id,
                variable_relation=row.variable_relation,
                created_at=row.created_at,
                last_successful_ingestion_at=row.last_successful_ingestion_at,
            )
            for row in session.scalars(select(EconomicSeries).order_by(EconomicSeries.id))
        ),
        instruments=tuple(
            InstrumentRecord(
                id=row.id,
                name=row.name,
                instrument_type=row.instrument_type,
                isin=row.isin,
                exchange_mic=row.exchange_mic,
                symbol=row.symbol,
                currency=row.currency,
                country_id=row.country_id,
                dataset_id=row.dataset_id,
                created_at=row.created_at,
            )
            for row in session.scalars(select(Instrument).order_by(Instrument.id))
        ),
    )
