"""Validated, idempotent loading of curated datasets.

Usage (from ``backend/``)::

    python -m app.db.seed                  # load the sample dataset (no-op if unchanged)
    python -m app.db.seed --validate-only  # check the file without touching the database
    python -m app.db.seed --reset          # replace existing data (also deletes scenarios)

A dataset file is checked in two stages before anything is written:

1. **Shape** — Pydantic models reject unknown fields, wrong types and invalid enums.
2. **Integrity** — cross-record rules: unique IDs, resolvable references, relationship
   types allowed for the kinds they connect, consistent polarity, and provenance rules
   (a non-fictional entity must cite a reference; evidence above ``illustrative`` must
   cite a source).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import (
    DatasetKind,
    EntityKind,
    EvidenceLevel,
    Frequency,
    Polarity,
    RelationshipType,
    Strength,
    ValueKind,
    VariableCategory,
)
from app.domain.relationship_types import get_spec
from app.models import (
    Company,
    Country,
    Dataset,
    EconomicVariable,
    Entity,
    Industry,
    Relationship,
    Scenario,
    ScenarioExecution,
    ScenarioExecutionRun,
    ScenarioSensitivityAnalysis,
    ScenarioShock,
    ScenarioVersion,
)
from app.schemas.common import EntityId

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_dataset.json"

NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=500)]


# --- File schema (stage 1: shape) ---------------------------------------------------


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetMeta(_Record):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,64}$")]
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
    name: NonEmpty
    description: NonEmpty
    is_illustrative: bool
    provenance_note: NonEmpty
    license: NonEmpty


class EntityRecord(_Record):
    id: EntityId
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    description: NonEmpty
    is_fictional: bool = False
    reference: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    reference_url: HttpsUrl | None = None
    attributes: dict[str, str | bool | int | float] = Field(default_factory=dict)


class CountryRecord(EntityRecord):
    iso_alpha2: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
    currency_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class IndustryRecord(EntityRecord):
    classification_system: NonEmpty
    classification_code: NonEmpty


class VariableRecord(EntityRecord):
    unit: NonEmpty
    value_kind: ValueKind
    frequency: Frequency
    category: VariableCategory
    country_id: EntityId | None


class CompanyRecord(EntityRecord):
    industry_id: EntityId
    country_id: EntityId


class RelationshipRecord(_Record):
    id: EntityId
    type: RelationshipType
    source_id: EntityId
    target_id: EntityId
    polarity: Polarity
    strength: Strength
    evidence_level: EvidenceLevel = EvidenceLevel.ILLUSTRATIVE
    description: NonEmpty
    rationale: NonEmpty
    reference: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None


class DatasetFile(_Record):
    dataset: DatasetMeta
    countries: list[CountryRecord]
    industries: list[IndustryRecord]
    economic_variables: list[VariableRecord]
    companies: list[CompanyRecord]
    relationships: list[RelationshipRecord]


# --- Integrity rules (stage 2) --------------------------------------------------------

_PREFIXES: dict[EntityKind, str] = {
    EntityKind.COUNTRY: "cty_",
    EntityKind.INDUSTRY: "ind_",
    EntityKind.ECONOMIC_VARIABLE: "var_",
    EntityKind.COMPANY: "co_",
}


def validate_integrity(data: DatasetFile) -> list[str]:
    """Return every cross-record problem found (an empty list means the file is valid)."""
    problems: list[str] = []
    groups: list[tuple[EntityKind, Sequence[EntityRecord]]] = [
        (EntityKind.COUNTRY, data.countries),
        (EntityKind.INDUSTRY, data.industries),
        (EntityKind.ECONOMIC_VARIABLE, data.economic_variables),
        (EntityKind.COMPANY, data.companies),
    ]

    kinds: dict[str, EntityKind] = {}
    for kind, records in groups:
        for record in records:
            if not record.id.startswith(_PREFIXES[kind]):
                problems.append(f"{record.id}: {kind} IDs must start with '{_PREFIXES[kind]}'.")
            if record.id in kinds:
                problems.append(f"{record.id}: duplicate entity ID.")
            kinds[record.id] = kind
            if not record.is_fictional and not record.reference:
                problems.append(f"{record.id}: a real-world entity must cite a reference.")

    for code, count in Counter(c.iso_alpha2 for c in data.countries).items():
        if count > 1:
            problems.append(f"ISO code {code} is used by more than one country.")

    def expect(entity_id: str | None, kind: EntityKind, where: str) -> None:
        if entity_id is not None and kinds.get(entity_id) is not kind:
            problems.append(f"{where}: '{entity_id}' is not a known {kind}.")

    for company in data.companies:
        expect(company.industry_id, EntityKind.INDUSTRY, f"{company.id}.industry_id")
        expect(company.country_id, EntityKind.COUNTRY, f"{company.id}.country_id")
    for variable in data.economic_variables:
        expect(variable.country_id, EntityKind.COUNTRY, f"{variable.id}.country_id")

    relationship_ids: set[str] = set()
    edges: set[tuple[RelationshipType, str, str]] = set()
    for rel in data.relationships:
        where = rel.id
        if not rel.id.startswith("rel_"):
            problems.append(f"{where}: relationship IDs must start with 'rel_'.")
        if rel.id in relationship_ids or rel.id in kinds:
            problems.append(f"{where}: duplicate ID.")
        relationship_ids.add(rel.id)

        source_kind, target_kind = kinds.get(rel.source_id), kinds.get(rel.target_id)
        if source_kind is None or target_kind is None:
            missing = rel.source_id if source_kind is None else rel.target_id
            problems.append(f"{where}: unknown entity '{missing}'.")
            continue
        if rel.source_id == rel.target_id:
            problems.append(f"{where}: an entity cannot be related to itself.")

        spec = get_spec(rel.type)
        if not spec.allows(source_kind, target_kind):
            problems.append(f"{where}: '{rel.type}' cannot connect {source_kind} → {target_kind}.")
        if not spec.directed and rel.source_id > rel.target_id:
            problems.append(f"{where}: undirected relationships must list IDs in sorted order.")
        if spec.has_polarity and rel.polarity is Polarity.NOT_APPLICABLE:
            problems.append(f"{where}: '{rel.type}' requires a polarity.")
        if not spec.has_polarity and rel.polarity is not Polarity.NOT_APPLICABLE:
            problems.append(f"{where}: '{rel.type}' must use polarity 'not_applicable'.")
        if rel.evidence_level is not EvidenceLevel.ILLUSTRATIVE and not rel.reference:
            problems.append(f"{where}: evidence level '{rel.evidence_level}' requires a reference.")

        key = (rel.type, rel.source_id, rel.target_id)
        if key in edges:
            problems.append(f"{where}: duplicate {rel.type} relationship.")
        edges.add(key)

    return problems


# --- Loading -------------------------------------------------------------------------


class DatasetError(Exception):
    """The dataset file is invalid or conflicts with what is already loaded."""

    def __init__(self, message: str, problems: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.problems = list(problems)


@dataclass
class SeedResult:
    status: Literal["loaded", "unchanged"]
    dataset_id: str
    version: str
    counts: dict[str, int] = field(default_factory=dict)


def read_dataset_file(path: Path) -> tuple[DatasetFile, str]:
    """Parse and fully validate a dataset file. Returns the data and its SHA-256."""
    raw = path.read_bytes()
    try:
        data = DatasetFile.model_validate_json(raw)
    except ValidationError as exc:
        problems = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise DatasetError(f"{path.name} does not match the dataset schema.", problems) from exc
    problems = validate_integrity(data)
    if problems:
        raise DatasetError(f"{path.name} failed integrity checks.", problems)
    return data, hashlib.sha256(raw).hexdigest()


def clear_domain_data(session: Session) -> None:
    """Delete scenarios (with their versions and executions), relationships, entities and
    datasets, in dependency order. Simulation runs are kept: they record the graph and data
    they used, and do not refer to these rows."""
    session.execute(delete(ScenarioSensitivityAnalysis))
    session.execute(delete(ScenarioExecutionRun))
    session.execute(delete(ScenarioExecution))
    session.execute(delete(ScenarioShock))
    session.execute(delete(ScenarioVersion))
    session.execute(delete(Scenario))
    session.execute(delete(Relationship))
    # Subtype rows are removed by ON DELETE CASCADE from `entities`. Kinds are deleted
    # in an order that respects the RESTRICT foreign keys between them.
    for kind in (
        EntityKind.COMPANY,
        EntityKind.ECONOMIC_VARIABLE,
        EntityKind.INDUSTRY,
        EntityKind.COUNTRY,
    ):
        session.execute(delete(Entity).where(Entity.kind == kind))
    # Only curated reference datasets: provider datasets and their series are kept.
    session.execute(delete(Dataset).where(Dataset.kind == DatasetKind.CURATED))


def load_dataset(
    session: Session, path: Path = DEFAULT_DATASET_PATH, *, reset: bool = False
) -> SeedResult:
    data, checksum = read_dataset_file(path)
    meta = data.dataset

    existing = session.get(Dataset, meta.id)
    if existing is not None and not reset:
        if existing.checksum_sha256 == checksum:
            return SeedResult("unchanged", meta.id, meta.version, count_records(session))
        raise DatasetError(
            f"Dataset '{meta.id}' v{existing.version} is already loaded and differs from "
            f"{path.name} (v{meta.version}). Re-run with --reset to replace it; note that "
            "this also deletes all scenarios."
        )
    if reset:
        clear_domain_data(session)
        session.flush()

    session.add(
        Dataset(
            id=meta.id,
            kind=DatasetKind.CURATED,
            version=meta.version,
            name=meta.name,
            description=meta.description,
            is_illustrative=meta.is_illustrative,
            provenance_note=meta.provenance_note,
            license=meta.license,
            checksum_sha256=checksum,
            loaded_at=utcnow(),
        )
    )
    common = {"dataset_id": meta.id}
    session.add_all(Country(**c.model_dump(), **common) for c in data.countries)
    session.add_all(Industry(**i.model_dump(), **common) for i in data.industries)
    session.flush()
    session.add_all(EconomicVariable(**v.model_dump(), **common) for v in data.economic_variables)
    session.add_all(Company(**c.model_dump(), **common) for c in data.companies)
    session.flush()
    session.add_all(Relationship(**r.model_dump(), **common) for r in data.relationships)
    session.commit()
    return SeedResult("loaded", meta.id, meta.version, count_records(session))


def count_records(session: Session) -> dict[str, int]:
    counts = {
        str(kind): count
        for kind, count in session.execute(
            select(Entity.kind, func.count()).group_by(Entity.kind)
        ).tuples()
    }
    counts["relationships"] = session.scalar(select(func.count()).select_from(Relationship)) or 0
    return counts


# --- Command line ----------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load a curated dataset into RUMIN.")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing domain data AND all scenarios before loading.",
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate the file without loading it."
    )
    args = parser.parse_args(argv)

    try:
        data, checksum = read_dataset_file(args.file)
    except DatasetError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"✓ {args.file.name} is valid ({data.dataset.id} v{data.dataset.version}, "
        f"sha256 {checksum[:12]}…)"
    )
    if args.validate_only:
        return 0

    engine = create_db_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            result = load_dataset(session, args.file, reset=args.reset)
    except DatasetError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc.orig}", file=sys.stderr)
        print("  Has the schema been created? Run: alembic upgrade head", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    verb = "Loaded" if result.status == "loaded" else "Already up to date:"
    print(f"✓ {verb} {result.dataset_id} v{result.version}")
    for name, count in sorted(result.counts.items()):
        print(f"  {name:<18} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
