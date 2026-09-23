"""Hand-made source records for graph tests (no database needed).

``snapshot()`` returns a small, valid world: two real countries, three ISIC industries, two
fictional companies, two variables, two relationships and two World Bank-style series.
Tests change one thing at a time: ``snapshot(companies=(...))``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

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
from app.graph.sources import (
    CompanyRecord,
    CountryRecord,
    DatasetRecord,
    IndustryRecord,
    InstrumentRecord,
    RelationshipRecord,
    SeriesRecord,
    SourceSnapshot,
    VariableRecord,
)

LOADED = datetime(2026, 9, 1, tzinfo=UTC)

CURATED = DatasetRecord(
    id="test-reference",
    kind=DatasetKind.CURATED,
    version="1.0.0",
    name="Test reference data",
    is_illustrative=True,
    checksum_sha256="0" * 64,
    license="Test",
    attribution=None,
    provider_id=None,
    loaded_at=LOADED,
)
PROVIDER = DatasetRecord(
    id="test-wdi",
    kind=DatasetKind.PROVIDER,
    version="catalogue 1.0.0",
    name="Test indicators",
    is_illustrative=False,
    checksum_sha256=None,
    license="CC BY 4.0",
    attribution="Test attribution",
    provider_id="test",
    loaded_at=LOADED,
)
SAMPLE_PRICES = replace(
    PROVIDER, id="test-sample-prices", version="user import", is_illustrative=True, name="Sample"
)
REAL_PRICES = replace(PROVIDER, id="test-real-prices", version="user import", name="Real prices")


def country(id: str, name: str, iso2: str, currency: str) -> CountryRecord:
    return CountryRecord(
        id=id,
        name=name,
        description=f"{name}.",
        is_fictional=False,
        iso_alpha2=iso2,
        currency_code=currency,
        reference=f"ISO 3166-1 alpha-2 {iso2}; ISO 4217 {currency}.",
        reference_url=None,
        dataset_id=CURATED.id,
    )


def industry(id: str, name: str, code: str, system: str = "ISIC Rev. 4") -> IndustryRecord:
    return IndustryRecord(
        id=id,
        name=name,
        description=f"{name}.",
        is_fictional=False,
        classification_system=system,
        classification_code=code,
        reference=f"{system} {code}",
        reference_url=None,
        dataset_id=CURATED.id,
    )


def company(
    id: str, name: str, industry_id: str, country_id: str, *, fictional: bool = True
) -> CompanyRecord:
    return CompanyRecord(
        id=id,
        name=name,
        description=f"{name}.",
        is_fictional=fictional,
        industry_id=industry_id,
        country_id=country_id,
        reference=None if fictional else "Annual report",
        reference_url=None,
        dataset_id=CURATED.id,
    )


def variable(id: str, name: str, country_id: str | None) -> VariableRecord:
    return VariableRecord(
        id=id,
        name=name,
        description=f"{name}.",
        is_fictional=False,
        unit="percent",
        frequency=Frequency.MONTHLY,
        category=VariableCategory.INFLATION,
        value_kind=ValueKind.RATE,
        country_id=country_id,
        reference="Publisher",
        reference_url="https://example.org/definition",
        dataset_id=CURATED.id,
    )


def relationship(
    id: str,
    type: RelationshipType,
    source: str,
    target: str,
    level: EvidenceLevel = EvidenceLevel.ILLUSTRATIVE,
) -> RelationshipRecord:
    return RelationshipRecord(
        id=id,
        type=type,
        source_id=source,
        target_id=target,
        polarity=Polarity.POSITIVE,
        strength=Strength.MODERATE,
        evidence_level=level,
        description=f"{source} {type.value} {target}.",
        rationale="Because of a test.",
        reference=None if level is EvidenceLevel.ILLUSTRATIVE else "A cited source",
        dataset_id=CURATED.id,
    )


def series(
    id: str,
    country_iso3: str | None,
    country_id: str | None,
    *,
    variable_id: str | None = None,
    currency: str | None = None,
) -> SeriesRecord:
    return SeriesRecord(
        id=id,
        dataset_id=PROVIDER.id,
        provider_series_key=f"{id.upper()}|{country_iso3}",
        provider_code="CODE.X",
        name=f"Test indicator — {country_iso3}",
        description="A test indicator.",
        source_organization="Test",
        measure_type=MeasureType.CHANGE,
        unit="%",
        currency=currency,
        frequency=Frequency.ANNUAL,
        country_iso3=country_iso3,
        country_id=country_id,
        variable_id=variable_id,
        variable_relation="Annual, not monthly." if variable_id else None,
        created_at=LOADED,
        last_successful_ingestion_at=None,
    )


def instrument(
    id: str,
    name: str,
    *,
    dataset: DatasetRecord = SAMPLE_PRICES,
    mic: str = "XTST",
    symbol: str | None = None,
    isin: str | None = None,
    currency: str = "INR",
    country_id: str | None = None,
) -> InstrumentRecord:
    return InstrumentRecord(
        id=id,
        name=name,
        instrument_type=InstrumentType.EQUITY,
        isin=isin,
        exchange_mic=mic,
        symbol=symbol or id.upper(),
        currency=currency,
        country_id=country_id,
        dataset_id=dataset.id,
        created_at=LOADED,
    )


INDIA = country("cty_in", "India", "IN", "INR")
USA = country("cty_us", "United States", "US", "USD")
AIR = industry("ind_air", "Air transport", "51")
REFINING = industry("ind_refining", "Refined petroleum products", "19")
LAND = industry("ind_land", "Land transport", "49")
AERISCA = company("co_aerisca", "Aerisca Airways", AIR.id, INDIA.id)
DELTRIN = company("co_deltrin", "Deltrin Refining", REFINING.id, INDIA.id)
CPI = variable("var_cpi", "India CPI inflation", INDIA.id)
FUEL = variable("var_fuel", "Jet fuel price", None)
COSTS = relationship("rel_fuel_air", RelationshipType.AFFECTS_COSTS, FUEL.id, AIR.id)
SUPPLY = relationship("rel_supply", RelationshipType.SUPPLIES_TO, DELTRIN.id, AERISCA.id)
CPI_SERIES = series("wb-cpi-ind", "IND", INDIA.id, variable_id=CPI.id)
GDP_SERIES = series("wb-gdp-ind", "IND", INDIA.id, currency="USD")


def snapshot(**changes: object) -> SourceSnapshot:
    base = SourceSnapshot(
        datasets={item.id: item for item in (CURATED, PROVIDER, SAMPLE_PRICES, REAL_PRICES)},
        countries=(INDIA, USA),
        industries=(AIR, LAND, REFINING),
        companies=(AERISCA, DELTRIN),
        variables=(CPI, FUEL),
        relationships=(COSTS, SUPPLY),
        series=(CPI_SERIES, GDP_SERIES),
        instruments=(),
    )
    return replace(base, **changes)  # type: ignore[arg-type]
