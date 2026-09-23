"""Data validation: the sample dataset's honesty rules and the loader's integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from sqlalchemy import func, select

from app.db.seed import (
    DEFAULT_DATASET_PATH,
    DatasetError,
    DatasetFile,
    load_dataset,
    read_dataset_file,
    validate_integrity,
)
from app.db.session import create_db_engine, create_session_factory
from app.models import Entity, Scenario, ScenarioShock
from tests.conftest import alembic_config


@pytest.fixture(scope="module")
def sample() -> DatasetFile:
    data, _ = read_dataset_file(DEFAULT_DATASET_PATH)
    return data


def minimal_dataset() -> dict[str, Any]:
    """A tiny valid dataset that individual tests break in one specific way."""
    return {
        "dataset": {
            "id": "test-data",
            "version": "0.0.1",
            "name": "Test",
            "description": "Test data.",
            "is_illustrative": True,
            "provenance_note": "Invented for tests.",
            "license": "Test only.",
        },
        "countries": [
            {
                "id": "cty_in",
                "name": "India",
                "description": "Country.",
                "iso_alpha2": "IN",
                "currency_code": "INR",
                "reference": "ISO 3166-1",
            }
        ],
        "industries": [
            {
                "id": "ind_air",
                "name": "Air transport",
                "description": "Airlines.",
                "classification_system": "ISIC Rev. 4",
                "classification_code": "51",
                "reference": "ISIC Rev. 4",
            }
        ],
        "economic_variables": [
            {
                "id": "var_fuel",
                "name": "Fuel price",
                "description": "Fuel.",
                "unit": "USD per gallon",
                "value_kind": "price",
                "frequency": "daily",
                "category": "commodity",
                "country_id": None,
                "reference": "Publisher",
            }
        ],
        "companies": [
            {
                "id": "co_alpha",
                "name": "Alpha Air",
                "description": "Fictional.",
                "industry_id": "ind_air",
                "country_id": "cty_in",
                "is_fictional": True,
            },
            {
                "id": "co_beta",
                "name": "Beta Air",
                "description": "Fictional.",
                "industry_id": "ind_air",
                "country_id": "cty_in",
                "is_fictional": True,
            },
        ],
        "relationships": [
            {
                "id": "rel_fuel_costs_alpha",
                "type": "affects_costs",
                "source_id": "var_fuel",
                "target_id": "co_alpha",
                "polarity": "positive",
                "strength": "strong",
                "description": "Fuel affects Alpha's costs.",
                "rationale": "Fuel is a major cost.",
            }
        ],
    }


def problems_for(data: dict[str, Any]) -> list[str]:
    return validate_integrity(DatasetFile.model_validate(data))


# --- The bundled sample dataset ------------------------------------------------------------


def test_sample_dataset_passes_every_integrity_rule(sample: DatasetFile) -> None:
    assert validate_integrity(sample) == []


def test_sample_dataset_is_labelled_illustrative(sample: DatasetFile) -> None:
    assert sample.dataset.is_illustrative is True
    assert "fictional" in sample.dataset.provenance_note
    assert "no observed financial values" in sample.dataset.provenance_note


def test_sample_companies_are_all_fictional(sample: DatasetFile) -> None:
    assert sample.companies
    assert all(company.is_fictional for company in sample.companies)
    assert all("Fictional" in company.description for company in sample.companies)


def test_sample_real_world_entities_cite_references(sample: DatasetFile) -> None:
    real = [*sample.countries, *sample.industries, *sample.economic_variables]
    assert all(entity.reference for entity in real)
    assert all(v.reference_url for v in sample.economic_variables)


def test_sample_relationships_do_not_claim_evidence(sample: DatasetFile) -> None:
    assert all(rel.evidence_level == "illustrative" for rel in sample.relationships)
    assert all(rel.rationale for rel in sample.relationships)


def test_sample_contains_no_numeric_financial_figures(sample: DatasetFile) -> None:
    raw = json.loads(DEFAULT_DATASET_PATH.read_text())
    entities = [
        *raw["countries"],
        *raw["industries"],
        *raw["economic_variables"],
        *raw["companies"],
    ]
    for record in [*entities, *raw["relationships"]]:
        numbers = [
            key
            for key, value in record.items()
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        assert numbers == [], f"{record['id']} has numeric fields {numbers}"
    assert all(not entity.get("attributes") for entity in entities)


# --- Integrity rules -------------------------------------------------------------------------


def test_minimal_dataset_is_valid() -> None:
    assert problems_for(minimal_dataset()) == []


def test_detects_duplicate_ids() -> None:
    data = minimal_dataset()
    data["companies"][1]["id"] = "co_alpha"

    assert any("duplicate entity ID" in p for p in problems_for(data))


def test_detects_wrong_id_prefixes() -> None:
    data = minimal_dataset()
    data["companies"][0]["id"] = "ind_alpha"
    data["relationships"][0]["target_id"] = "ind_alpha"

    assert any("company IDs must start with 'co_'" in p for p in problems_for(data))


def test_detects_unresolvable_references() -> None:
    data = minimal_dataset()
    data["companies"][0]["industry_id"] = "ind_missing"
    data["relationships"][0]["source_id"] = "var_missing"

    problems = problems_for(data)
    assert any("'ind_missing' is not a known industry" in p for p in problems)
    assert any("unknown entity 'var_missing'" in p for p in problems)


def test_detects_relationship_types_that_do_not_fit_the_entities() -> None:
    data = minimal_dataset()
    data["relationships"][0].update(
        {"type": "lends_to", "source_id": "var_fuel", "polarity": "not_applicable"}
    )

    assert any("cannot connect economic_variable → company" in p for p in problems_for(data))


def test_detects_self_loops() -> None:
    data = minimal_dataset()
    data["relationships"][0].update(
        {"type": "supplies_to", "source_id": "co_alpha", "polarity": "not_applicable"}
    )

    assert any("cannot be related to itself" in p for p in problems_for(data))


def test_undirected_relationships_must_be_in_sorted_order() -> None:
    data = minimal_dataset()
    data["relationships"][0].update(
        {
            "type": "competes_with",
            "source_id": "co_beta",
            "target_id": "co_alpha",
            "polarity": "not_applicable",
        }
    )

    assert any("sorted order" in p for p in problems_for(data))


def test_polarity_must_match_the_relationship_type() -> None:
    missing = minimal_dataset()
    missing["relationships"][0]["polarity"] = "not_applicable"
    unexpected = minimal_dataset()
    unexpected["relationships"][0].update(
        {"type": "competes_with", "source_id": "co_alpha", "target_id": "co_beta"}
    )

    assert any("requires a polarity" in p for p in problems_for(missing))
    assert any("must use polarity 'not_applicable'" in p for p in problems_for(unexpected))


def test_evidence_above_illustrative_requires_a_reference() -> None:
    data = minimal_dataset()
    data["relationships"][0]["evidence_level"] = "validated"

    assert any("requires a reference" in p for p in problems_for(data))

    data["relationships"][0]["reference"] = "Journal article, 2024"
    assert problems_for(data) == []


def test_real_world_entities_require_a_reference() -> None:
    data = minimal_dataset()
    data["companies"][0]["is_fictional"] = False

    assert any("must cite a reference" in p for p in problems_for(data))


def test_detects_duplicate_relationships() -> None:
    data = minimal_dataset()
    duplicate = {**data["relationships"][0], "id": "rel_again"}
    data["relationships"].append(duplicate)

    assert any("duplicate affects_costs relationship" in p for p in problems_for(data))


def test_schema_rejects_unknown_fields(tmp_path: Path) -> None:
    data = minimal_dataset()
    data["companies"][0]["revenue_usd"] = 1_000_000
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))

    with pytest.raises(DatasetError) as info:
        read_dataset_file(path)

    assert any("revenue_usd" in problem for problem in info.value.problems)


# --- Loading ----------------------------------------------------------------------------------


def test_loading_is_idempotent_and_reset_replaces_data(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    command.upgrade(alembic_config(url), "head")
    engine = create_db_engine(url)
    session_factory = create_session_factory(engine)
    dataset_path = tmp_path / "data.json"
    dataset_path.write_text(json.dumps(minimal_dataset()))

    with session_factory() as session:
        first = load_dataset(session, dataset_path)
        second = load_dataset(session, dataset_path)
        session.add(
            Scenario(
                name="Kept until reset",
                shocks=[
                    ScenarioShock(
                        position=0, variable_id="var_fuel", change_type="percent_change", value=5
                    )
                ],
            )
        )
        session.commit()

        changed = minimal_dataset()
        changed["dataset"]["version"] = "0.0.2"
        dataset_path.write_text(json.dumps(changed))
        with pytest.raises(DatasetError, match="--reset"):
            load_dataset(session, dataset_path)
        reset = load_dataset(session, dataset_path, reset=True)

        entity_count = session.scalar(select(func.count()).select_from(Entity))
        scenario_count = session.scalar(select(func.count()).select_from(Scenario))
    engine.dispose()

    assert first.status == "loaded"
    assert second.status == "unchanged"
    assert (
        first.counts
        == second.counts
        == {
            "company": 2,
            "country": 1,
            "economic_variable": 1,
            "industry": 1,
            "relationships": 1,
        }
    )
    assert reset.status == "loaded" and reset.version == "0.0.2"
    assert entity_count == 5
    assert scenario_count == 0  # reset is documented to delete scenarios
