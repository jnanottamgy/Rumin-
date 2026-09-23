"""The series catalogue: which provider datasets and series RUMIN retrieves.

``app/data/series_catalog.json`` is curated like code: it is validated in full before
anything is written, and syncing it is idempotent. It defines *what to fetch and how to
describe it* — it never contains data values.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.types import decimal_fits
from app.domain.enums import (
    DatasetKind,
    EntityKind,
    Frequency,
    MeasureType,
    PriceBasis,
    SeasonalAdjustment,
)
from app.ingestion.providers.base import ProviderProfile
from app.ingestion.providers.worldbank import COUNTRY_ISO3, INDICATOR_CODE, PERIOD_FORMATS
from app.models import DataProvider, Dataset, EconomicSeries, Entity

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "series_catalog.json"

SeriesId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,95}$")]
DatasetId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=500)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogDataset(_Model):
    id: DatasetId
    provider_id: str
    provider_dataset_code: str | None = None
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    description: Text
    license: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    license_url: HttpsUrl | None = None
    terms_url: HttpsUrl | None = None
    homepage_url: HttpsUrl | None = None
    attribution: Text
    update_frequency: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    provenance_note: Text


class CatalogSeries(_Model):
    id: SeriesId
    dataset_id: DatasetId
    provider_code: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    country_iso3: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None
    country_id: str | None = None
    variable_id: str | None = None
    variable_relation: Text | None = None
    name: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    description: Text
    measure_type: MeasureType
    unit: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    frequency: Frequency
    aggregation: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    price_basis: PriceBasis
    seasonal_adjustment: SeasonalAdjustment
    plausible_min: Decimal | None = None
    plausible_max: Decimal | None = None
    start: str

    @property
    def provider_series_key(self) -> str:
        return f"{self.provider_code}|{self.country_iso3 or ''}"


class Catalog(_Model):
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
    note: str = ""
    datasets: list[CatalogDataset] = Field(min_length=1)
    series: list[CatalogSeries] = Field(min_length=1)


class CatalogError(Exception):
    def __init__(self, message: str, problems: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.problems = list(problems)


def validate_catalog(catalog: Catalog, profiles: dict[str, ProviderProfile]) -> list[str]:
    """Cross-record rules that the schema alone cannot express."""
    problems: list[str] = []
    datasets = {item.id: item for item in catalog.datasets}
    if len(datasets) != len(catalog.datasets):
        problems.append("Dataset IDs must be unique.")
    for item in catalog.datasets:
        if item.provider_id not in profiles:
            problems.append(f"{item.id}: unknown provider '{item.provider_id}'.")

    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    for series in catalog.series:
        where = f"series {series.id}"
        if series.id in seen_ids:
            problems.append(f"{where}: duplicate ID.")
        seen_ids.add(series.id)
        key = (series.dataset_id, series.provider_series_key)
        if key in seen_keys:
            problems.append(f"{where}: the same provider series is listed twice.")
        seen_keys.add(key)

        dataset = datasets.get(series.dataset_id)
        if dataset is None:
            problems.append(f"{where}: unknown dataset '{series.dataset_id}'.")
            continue
        if dataset.provider_id == "worldbank":
            if not INDICATOR_CODE.match(series.provider_code):
                problems.append(f"{where}: '{series.provider_code}' is not an indicator code.")
            if series.country_iso3 is None or not COUNTRY_ISO3.match(series.country_iso3):
                problems.append(f"{where}: World Bank series need a country_iso3.")
            pattern = PERIOD_FORMATS.get(series.frequency)
            if pattern is None:
                problems.append(f"{where}: the World Bank API has no {series.frequency} data.")
            elif not pattern.match(series.start):
                problems.append(
                    f"{where}: start '{series.start}' is not a {series.frequency} period."
                )
        for bound in (series.plausible_min, series.plausible_max):
            if bound is not None and not decimal_fits(bound):
                problems.append(f"{where}: plausible bounds must fit NUMERIC(38, 18).")
        if (
            series.plausible_min is not None
            and series.plausible_max is not None
            and series.plausible_min > series.plausible_max
        ):
            problems.append(f"{where}: plausible_min is greater than plausible_max.")
        if series.variable_id and not series.variable_relation:
            problems.append(
                f"{where}: linking to a variable requires variable_relation — say how the "
                "series and the variable differ."
            )
        if (
            series.measure_type is MeasureType.LEVEL
            and series.currency is None
            and "US$" in series.unit
        ):
            problems.append(f"{where}: a monetary level needs its currency.")
    return problems


def read_catalog(path: Path, profiles: dict[str, ProviderProfile]) -> Catalog:
    try:
        catalog = Catalog.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        problems = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise CatalogError(f"{path.name} does not match the catalogue schema.", problems) from exc
    problems = validate_catalog(catalog, profiles)
    if problems:
        raise CatalogError(f"{path.name} failed its integrity checks.", problems)
    return catalog


@dataclass
class SyncReport:
    providers: int = 0
    datasets: int = 0
    series_created: int = 0
    series_updated: int = 0
    # Links to Phase 1 entities that could not be made (e.g. reference data not loaded).
    unlinked: list[str] = field(default_factory=list)
    # Series in the database that the catalogue no longer lists (kept, never deleted).
    not_in_catalog: list[str] = field(default_factory=list)


def sync_providers(session: Session, profiles: dict[str, ProviderProfile]) -> int:
    for profile in profiles.values():
        row = session.get(DataProvider, profile.id) or DataProvider(id=profile.id)
        for name in (
            "name",
            "kind",
            "description",
            "homepage_url",
            "documentation_url",
            "terms_url",
            "authentication",
            "data_categories",
            "coverage",
            "update_frequency",
            "rate_limit_policy",
            "licensing",
            "commercial_use",
            "reliability",
            "known_limitations",
        ):
            setattr(row, name, getattr(profile, name))
        session.add(row)
    session.flush()
    return len(profiles)


def _entity_exists(session: Session, entity_id: str | None, kind: EntityKind) -> bool:
    if entity_id is None:
        return False
    entity = session.get(Entity, entity_id)
    return entity is not None and entity.kind == kind


def sync_catalog(
    session: Session, catalog: Catalog, profiles: dict[str, ProviderProfile]
) -> SyncReport:
    """Create or update providers, provider datasets and series. Never deletes anything,
    and never touches observations: those only change through ingestion."""
    report = SyncReport(providers=sync_providers(session, profiles))
    now = utcnow()
    for dataset_spec in catalog.datasets:
        dataset = session.get(Dataset, dataset_spec.id)
        if dataset is not None and dataset.kind is not DatasetKind.PROVIDER:
            raise CatalogError(f"Dataset '{dataset_spec.id}' already exists as a curated dataset.")
        dataset = dataset or Dataset(id=dataset_spec.id, kind=DatasetKind.PROVIDER, loaded_at=now)
        dataset.version = f"catalogue {catalog.version}"
        dataset.name = dataset_spec.name
        dataset.description = dataset_spec.description
        dataset.is_illustrative = False
        dataset.provenance_note = dataset_spec.provenance_note
        dataset.license = dataset_spec.license
        dataset.license_url = dataset_spec.license_url
        dataset.terms_url = dataset_spec.terms_url
        dataset.homepage_url = dataset_spec.homepage_url
        dataset.attribution = dataset_spec.attribution
        dataset.update_frequency = dataset_spec.update_frequency
        dataset.provider_id = dataset_spec.provider_id
        dataset.provider_dataset_code = dataset_spec.provider_dataset_code
        session.add(dataset)
        report.datasets += 1
    session.flush()

    listed = {item.id for item in catalog.series}
    for series_spec in catalog.series:
        series = session.get(EconomicSeries, series_spec.id)
        if series is None:
            series = EconomicSeries(id=series_spec.id)
            report.series_created += 1
        else:
            report.series_updated += 1
        country_ok = _entity_exists(session, series_spec.country_id, EntityKind.COUNTRY)
        variable_ok = _entity_exists(session, series_spec.variable_id, EntityKind.ECONOMIC_VARIABLE)
        if series_spec.country_id and not country_ok:
            report.unlinked.append(f"{series_spec.id} → {series_spec.country_id}")
        if series_spec.variable_id and not variable_ok:
            report.unlinked.append(f"{series_spec.id} → {series_spec.variable_id}")
        series.dataset_id = series_spec.dataset_id
        series.provider_series_key = series_spec.provider_series_key
        series.provider_code = series_spec.provider_code
        series.name = series_spec.name
        # The provider's own definition replaces this at the first successful ingestion.
        if not series.description:
            series.description = series_spec.description
        series.measure_type = series_spec.measure_type
        series.unit = series_spec.unit
        series.currency = series_spec.currency
        series.frequency = series_spec.frequency
        series.aggregation = series_spec.aggregation
        series.price_basis = series_spec.price_basis
        series.seasonal_adjustment = series_spec.seasonal_adjustment
        series.country_iso3 = series_spec.country_iso3
        series.country_id = series_spec.country_id if country_ok else None
        series.variable_id = series_spec.variable_id if variable_ok else None
        series.variable_relation = series_spec.variable_relation if variable_ok else None
        series.plausible_min = series_spec.plausible_min
        series.plausible_max = series_spec.plausible_max
        session.add(series)
    session.flush()

    report.not_in_catalog = [
        series_id
        for series_id in session.scalars(select(EconomicSeries.id)).all()
        if series_id not in listed
    ]
    return report


def catalog_start(catalog: Catalog) -> dict[str, str]:
    """Each series' first period to request."""
    return {spec.id: spec.start for spec in catalog.series}


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m app.ingestion.catalog [--file PATH]`` — validate without a database."""
    from app.ingestion.registry import PROFILES

    parser = argparse.ArgumentParser(description="Validate the series catalogue.")
    parser.add_argument("--file", type=Path, default=DEFAULT_CATALOG_PATH)
    args = parser.parse_args(argv)
    try:
        catalog = read_catalog(args.file, PROFILES)
    except CatalogError as error:
        print(f"✗ {error}")
        for problem in error.problems:
            print(f"  - {problem}")
        return 1
    print(
        f"✓ {args.file.name} is valid (catalogue v{catalog.version}: "
        f"{len(catalog.datasets)} dataset(s), {len(catalog.series)} series)"
    )
    print(json.dumps({"series": [s.id for s in catalog.series]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
