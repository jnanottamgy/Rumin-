"""The simulation API end to end, on the real database (SQLite or PostgreSQL): models,
validation, runs, explanations, provenance, verification, sensitivity and persistence.

Company figures are HYPOTHETICAL round numbers (``tests/simulation_support.py``); the
exchange-rate observation is SYNTHETIC, stored through the real ingestion pipeline from a
scripted response (``tests/fakes.py``). No test touches the network.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import GraphEdgeType, JobStatus, QualityStatus, SimulationModelStatus
from app.graph.build import run_build
from app.ingestion.catalog import DEFAULT_CATALOG_PATH, read_catalog, sync_catalog
from app.ingestion.economic import run_economic_ingestion
from app.ingestion.providers.worldbank import WorldBankProvider
from app.ingestion.registry import PROFILES
from app.models import (
    Company,
    Dataset,
    EconomicSeries,
    GraphEdge,
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
)
from app.services import simulation as simulation_service
from app.simulation.registry import ModelRegistry
from tests.conftest import wipe_graph
from tests.fakes import ScriptedTransport, make_client, response, wb_indicator, wb_page, wb_record
from tests.simulation_support import MODEL, inputs, with_model
from tests.test_ingestion_pipeline import Clock

API = "/api/v1"
AERISCA = "company:co_aerisca_airways"
FX_SERIES = "wb-ind-pa-nus-fcrf"


def wipe_simulations(session: Session) -> None:
    for model in (
        SimulationSensitivityAnalysis,
        SimulationRunStep,
        SimulationRun,
        SimulationModelVersion,
    ):
        session.execute(delete(model))
    session.commit()


@pytest.fixture(autouse=True)
def _no_stored_runs(session_factory: sessionmaker[Session]) -> Iterator[None]:
    with session_factory() as session:
        wipe_simulations(session)
    yield
    with session_factory() as session:
        wipe_simulations(session)


@pytest.fixture
def built(graph_session: Session) -> Iterator[Session]:
    """The reference network plus the World Bank catalogue, built into a graph."""
    sync_catalog(graph_session, read_catalog(DEFAULT_CATALOG_PATH, PROFILES), PROFILES)
    graph_session.commit()
    run_build(graph_session)
    yield graph_session


def body(**changes: Any) -> dict[str, Any]:
    return {"model_id": "airline_fuel_cost", "inputs": inputs(**changes)}


def post(client: TestClient, path: str, payload: Any, expect: int) -> Any:
    response = client.post(f"{API}{path}", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def get(client: TestClient, path: str, expect: int = 200, **params: Any) -> Any:
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == expect, response.text
    return response.json()


def create_run(client: TestClient, **changes: Any) -> dict[str, Any]:
    run: dict[str, Any] = post(client, "/simulations", body(**changes), 201)
    return run


def outputs(run: dict[str, Any]) -> dict[str, Decimal]:
    return {item["id"]: Decimal(item["value"]) for item in run["outputs"]}


def details(error: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item["field"], item["type"]) for item in error["error"]["details"]]


def store_fx_observation(session: Session, value: str) -> None:
    """Store a SYNTHETIC value of the exchange-rate series via the ingestion pipeline."""
    transport = ScriptedTransport(
        [
            response(wb_page([wb_record("2025", value, code="PA.NUS.FCRF")])),
            response(wb_indicator("PA.NUS.FCRF")),
        ]
    )
    http, _ = make_client(transport)
    clock = Clock()
    job = run_economic_ingestion(
        session,
        WorldBankProvider(http, clock=clock),
        dataset=session.get_one(Dataset, "worldbank-wdi"),
        series=[session.get_one(EconomicSeries, FX_SERIES)],
        start={FX_SERIES: "2019"},
        end={FX_SERIES: "2025"},
        parameters={"test": True},
        today=date(2026, 9, 23),
        http=http,
        clock=clock,
    )
    assert job.status is JobStatus.COMPLETED


# --- Models -------------------------------------------------------------------------------------


def test_models_are_listed_with_their_version_and_status(client: TestClient) -> None:
    [model] = get(client, "/simulation-models")

    assert (model["id"], model["version"], model["status"]) == (
        "airline_fuel_cost",
        "1.0.0",
        "preview",
    )
    assert model["definition_hash"] == MODEL.definition_hash
    assert model["runs"] == 0


def test_a_model_shows_which_graph_relationship_confirms_each_rule(
    built: Session, client: TestClient
) -> None:
    model = get(client, "/simulation-models/airline_fuel_cost")
    [rule] = model["transmission_rules"]
    inputs_by_id = {item["id"]: item for item in model["inputs"]}

    assert model["graph_freshness"] == "current"
    assert rule["graph_edge"]["edge_type"] == "influences"
    assert rule["graph_edge"]["evidence_status"] == "model_assumption"
    assert (rule["source_name"], rule["target_name"]) == (
        "Brent crude oil price",
        "Jet fuel price (U.S. Gulf Coast)",
    )
    assert len(model["equations"]) == 19
    assert inputs_by_id["fx_rate"]["sources"][0]["available"] is False  # nothing stored
    assert inputs_by_id["hedge_ratio"]["category"] == "assumption"
    assert inputs_by_id["jet_fuel_price"]["units"][0] == {
        "id": "usd_per_us_gallon",
        "label": "USD per US gallon",
    }


def test_unknown_models_and_versions_are_not_found(client: TestClient) -> None:
    get(client, "/simulation-models/no_such_model", expect=404)
    get(client, "/simulation-models/airline_fuel_cost", expect=404, version="9.9.9")
    get(client, "/simulation-models/Not-A-Model", expect=422)
    error = post(client, "/simulations", {"model_id": "no_such_model", "inputs": {}}, 422)
    assert details(error) == [("model_id", "unknown_model")]


# --- Validation ---------------------------------------------------------------------------------


def test_validation_explains_every_problem_and_stores_nothing(
    built: Session, client: TestClient
) -> None:
    report = post(
        client,
        "/simulations/validate",
        body(hedge_ratio="150", annual_revenue=None, colour="blue"),
        200,
    )

    assert report["valid"] is False
    assert {(item["field"], item["code"]) for item in report["errors"]} == {
        ("colour", "unknown_input"),
        ("annual_revenue", "required"),
        ("hedge_ratio", "input_range"),
    }
    assert report["inputs_hash"] is None
    assert built.scalar(select(func.count()).select_from(SimulationRun)) == 0


def test_valid_inputs_report_warnings_and_the_future_inputs_hash(
    built: Session, client: TestClient
) -> None:
    report = post(client, "/simulations/validate", body(), 200)
    run = create_run(client)

    assert report["valid"] is True
    assert [item["code"] for item in report["warnings"]] == ["assumption_based_channel"]
    assert report["inputs_hash"] == run["inputs_hash"]
    assert report["graph"]["transmission"]["T1"]["edge_key"].startswith("e-")


# --- Runs ---------------------------------------------------------------------------------------


def test_a_run_is_stored_with_everything_needed_to_explain_it(
    built: Session, client: TestClient
) -> None:
    response = client.post(f"{API}/simulations", json={**body(), "label": "Crude +10 %"})
    assert response.status_code == 201, response.text
    run = response.json()

    assert response.headers["location"] == f"/api/v1/simulations/{run['id']}"
    assert get(client, f"/simulations/{run['id']}") == run
    assert run["label"] == "Crude +10 %"
    assert run["status"] == "completed"
    assert outputs(run)["operating_profit_change"] == Decimal(-6_000_000)
    assert "not a forecast" in run["note"]
    assert run["random_seed"] is None  # deterministic: nothing is drawn at random
    assert run["monthly"][0]["id"] == "jet_fuel_relative"
    assert all(len(series["values"]) == 12 for series in run["monthly"])

    knowledge = {item["id"]: item["knowledge"] for item in run["inputs"]}
    assert knowledge["crude_oil_change"] == "scenario_input"
    assert knowledge["annual_revenue"] == "user_input"
    assert knowledge["hedge_ratio"] == "assumption"
    assert {item["kind"] for item in run["outputs"]} == {"derived", "simulated"}

    stored = built.get_one(SimulationRun, uuid.UUID(run["id"]))
    version = built.get_one(SimulationModelVersion, stored.model_version_id)
    steps = built.scalar(select(func.count()).where(SimulationRunStep.run_id == stored.id))
    assert version.definition_hash == MODEL.definition_hash
    assert version.status is SimulationModelStatus.PREVIEW
    assert steps and steps > 12 * 8
    assert stored.graph_snapshot["build_id"] is not None


def test_runs_are_append_only_and_reproducible(client: TestClient) -> None:
    first = create_run(client, crude_oil_change="0", usd_change="5")
    second = create_run(client, crude_oil_change="0", usd_change="5")

    assert first["id"] != second["id"]
    assert (first["inputs_hash"], first["result_hash"]) == (
        second["inputs_hash"],
        second["result_hash"],
    )
    for method in ("put", "patch", "delete"):
        assert client.request(method, f"{API}/simulations/{first['id']}").status_code == 405
    assert get(client, "/simulations")["total"] == 2


def test_runs_are_listed_newest_first_with_their_headline(client: TestClient) -> None:
    for change in ("1", "2", "3"):
        create_run(client, crude_oil_change="0", usd_change=change)

    page = get(client, "/simulations", limit=2)
    empty = get(client, "/simulations", model_id="another_model")

    assert (page["total"], len(page["items"]), page["limit"]) == (3, 2, 2)
    assert [item["id"] for item in page["items"][0]["headline"]] == [
        item for item in MODEL.definition.headline_outputs
    ]
    assert empty["total"] == 0
    get(client, "/simulations", expect=422, model_id="Bad-Id")
    get(client, f"/simulations/{uuid.uuid4()}", expect=404)
    get(client, "/simulations/not-a-uuid", expect=422)


def test_a_calculation_that_cannot_be_done_is_refused_and_not_stored(
    client: TestClient, db_session: Session
) -> None:
    error = post(
        client,
        "/simulations",
        body(
            crude_oil_change="0",
            usd_change="-99",
            annual_revenue="10000000",
            annual_operating_costs="70000000",
            fare_pass_through="100",
        ),
        422,
    )
    assert details(error) == [("inputs", "numerical_limit")]
    assert "margin is undefined" in error["error"]["details"][0]["message"]
    assert db_session.scalar(select(func.count()).select_from(SimulationRun)) == 0


def test_request_sizes_are_bounded(client: TestClient) -> None:
    many = {f"input_{index:02d}": {"value": "1"} for index in range(41)}
    post(client, "/simulations/validate", {"model_id": "airline_fuel_cost", "inputs": many}, 422)
    post(client, "/simulations", {**body(), "label": "x" * 121}, 422)
    post(
        client,
        "/simulations/validate",
        {"model_id": "airline_fuel_cost", "inputs": {"crude_oil_change": {"value": "1" * 129}}},
        422,
    )
    post(
        client,
        "/simulations/validate",
        {"model_id": "airline_fuel_cost", "inputs": {"Not An Input": {"value": "1"}}},
        422,
    )


# --- The knowledge graph ------------------------------------------------------------------------


def test_without_a_graph_a_crude_shock_is_refused_but_direct_changes_run(
    graph_session: Session, client: TestClient
) -> None:
    error = post(client, "/simulations", body(), 422)
    run = create_run(client, crude_oil_change="0", usd_change="5")

    assert details(error) == [("inputs.crude_oil_change", "channel_confirmed")]
    assert "has not been built" in error["error"]["details"][0]["message"]
    assert run["entity"] is None
    assert outputs(run)["fuel_cost_change"] == Decimal(3_000_000)


def test_the_airline_must_be_an_air_transport_company_in_the_graph(
    built: Session, client: TestClient
) -> None:
    run = create_run(client, entity=AERISCA)
    other = post(client, "/simulations", body(entity="company:co_kovalent_digital"), 422)
    missing = post(client, "/simulations", body(entity="company:co_nobody"), 422)
    industry = post(client, "/simulations", body(entity="industry:ind_air_transport"), 422)

    assert run["entity"] == {"key": AERISCA, "name": "Aerisca Airways", "nature": "fictional"}
    assert "fictional_entity" in [item["code"] for item in run["warnings"]]
    assert "does not state that Kovalent Digital" in other["error"]["details"][0]["message"]
    assert details(missing) == [("inputs.entity", "entity_is_airline")]
    assert "not a company" in industry["error"]["details"][0]["message"]


def test_a_stale_graph_is_reported_with_the_build_it_used(
    built: Session, client: TestClient
) -> None:
    company = built.get_one(Company, "co_kovalent_digital")
    original = company.name
    try:
        company.name = "Kovalent Digital (renamed)"
        built.commit()
        run = create_run(client)
    finally:
        company.name = original
        built.commit()

    assert "graph_stale" in [item["code"] for item in run["warnings"]]


def test_a_relationship_flagged_by_the_graph_is_not_followed(
    built: Session, client: TestClient
) -> None:
    rule = MODEL.definition.transmission_rules[0]
    edge = built.scalars(
        select(GraphEdge).where(
            GraphEdge.retired_build_id.is_(None),
            GraphEdge.edge_type == GraphEdgeType(rule.edge_type),
            GraphEdge.source_node_id == rule.source,
            GraphEdge.target_node_id == rule.target,
        )
    ).one()
    try:
        edge.quality_status = QualityStatus.WARNING
        built.commit()
        error = post(client, "/simulations", body(), 422)
        run = create_run(client, crude_oil_change="0", usd_change="5")
    finally:
        edge.quality_status = QualityStatus.VALIDATED
        built.commit()

    message = error["error"]["details"][0]["message"]
    assert details(error) == [("inputs.crude_oil_change", "channel_confirmed")]
    assert "does not contain it as a validated relationship" in message
    assert outputs(run)["fuel_cost_change"] == Decimal(3_000_000)


# --- Explanation, provenance and verification ---------------------------------------------------


def test_the_explanation_is_structured_and_complete(built: Session, client: TestClient) -> None:
    run = create_run(client, usd_change="5", hedge_ratio="50", hedge_months="3")
    explanation = get(client, f"/simulations/{run['id']}/explanation")

    assert {item["id"] for item in explanation["equations"] if item["used"]} == {
        f"E{n}" for n in range(1, 20)
    }
    sequences = [step["sequence"] for step in explanation["steps"]]
    assert sequences == list(range(1, len(sequences) + 1))
    kinds = {node["kind"] for node in explanation["pathway"]["nodes"]}
    assert kinds == {"input", "variable", "output"}
    [crude_link] = [link for link in explanation["pathway"]["links"] if link["rule"] == "T1"]
    assert crude_link["edge"]["edge_key"] == run_edge(built, client, run["id"])
    assert crude_link["coefficient"] == "1"
    hedge = next(item for item in explanation["parameters"] if item["id"] == "hedge_ratio")
    assert (hedge["value"], hedge["default"], hedge["changed_from_default"]) == ("50", "0", True)
    assert len(explanation["contributions"]) >= 1
    assert explanation["bridge"]["total"]["output"] == "operating_profit_change"
    assert "Shapley" in explanation["method"]["contributions"]


def run_edge(_session: Session, client: TestClient, run_id: str) -> str:
    provenance = get(client, f"/simulations/{run_id}/provenance")
    return str(provenance["graph"]["transmission"]["T1"]["edge_key"])


def test_provenance_records_the_model_graph_and_paths(built: Session, client: TestClient) -> None:
    run = create_run(client)
    provenance = get(client, f"/simulations/{run['id']}/provenance")

    assert provenance["model"]["definition_hash"] == MODEL.definition_hash
    assert provenance["engine_version"] == "1.0.0"
    assert provenance["inputs_hash"] == run["inputs_hash"]
    assert provenance["graph"]["freshness"] == "current"
    assert provenance["observations"] == []
    paths = [path["nodes"] for path in provenance["transmission"]]
    assert ["variable:var_brent_crude", "variable:var_jet_fuel"] in paths
    assert provenance["graph"]["unused_total"] >= 1  # listed, never followed


def test_a_run_reproduces_from_its_snapshot_even_after_the_graph_is_gone(
    built: Session, client: TestClient
) -> None:
    run = create_run(client, fare_pass_through="40", fare_pass_through_lag="2")
    wipe_graph(built)

    check = post(client, f"/simulations/{run['id']}/verify", None, 200)

    assert check["reproduced"] is True
    assert check["recomputed_result_hash"] == run["result_hash"]
    assert check["graph_edges"] == [
        {"rule": "T1", "edge_key": run_edge(built, client, run["id"]), "still_current": False}
    ]


def test_a_stored_exchange_rate_is_used_with_its_provenance(
    built: Session, client: TestClient
) -> None:
    store_fx_observation(built, "81.123456789")  # synthetic
    run = create_run(client, fx_rate={"value": None, "source": "stored_observation"})
    fx = next(item for item in run["inputs"] if item["id"] == "fx_rate")
    provenance = get(client, f"/simulations/{run['id']}/provenance")

    assert (fx["value"], fx["source"], fx["knowledge"]) == (
        "81.123456789",
        "stored_observation",
        "historical_data",
    )
    assert fx["observation"]["period_label"] == "2025"
    assert "historical_baseline" in [item["code"] for item in run["warnings"]]
    [observation] = provenance["observations"]
    assert (observation["series_id"], observation["license"]) == (FX_SERIES, "CC BY 4.0")
    model = get(client, "/simulation-models/airline_fuel_cost")
    source = next(item for item in model["inputs"] if item["id"] == "fx_rate")["sources"][0]
    assert (source["available"], source["latest_value"]) == (True, "81.123456789")
    assert post(client, f"/simulations/{run['id']}/verify", None, 200)["reproduced"] is True


# --- Sensitivity --------------------------------------------------------------------------------


def test_a_sensitivity_analysis_is_stored_and_can_be_listed(
    built: Session, client: TestClient
) -> None:
    run = create_run(client, fare_pass_through="40")
    response = client.post(f"{API}/simulations/{run['id']}/sensitivity", json={})
    assert response.status_code == 201, response.text
    analysis = response.json()

    assert response.headers["location"].endswith(f"/sensitivity/{analysis['id']}")
    assert analysis["metric"] == "operating_profit_change"
    base = Decimal(analysis["base"]["operating_profit_change"])
    assert base == outputs(run)["operating_profit_change"]
    assert [item["input"] for item in analysis["items"]] == list(
        MODEL.definition.sensitivity_defaults
    )
    assert "not how likely" in analysis["note"]
    assert get(client, f"/simulations/{run['id']}/sensitivity")["items"] == [analysis]
    assert get(client, f"/simulations/{run['id']}/sensitivity/{analysis['id']}") == analysis
    assert get(client, f"/simulations/{run['id']}")["sensitivity_analyses"] == 1


def test_a_custom_sensitivity_analysis(built: Session, client: TestClient) -> None:
    run = create_run(client)
    analysis = post(
        client,
        f"/simulations/{run['id']}/sensitivity",
        {
            "inputs": [
                {"input": "crude_pass_through", "mode": "values", "values": ["0.5", "1.5", 5]},
                {"input": "jet_fuel_price", "mode": "relative", "step": "10"},
            ],
            "metric": "fuel_cost_change",
        },
        201,
    )
    beta, price = analysis["items"]

    assert [point["value"] for point in beta["points"]] == ["0.5", "1.5", "5"]
    assert "at most 3" in beta["points"][2]["skipped"]
    assert [point["value"] for point in price["points"]] == ["675", "825"]
    assert Decimal(price["points"][1]["deltas"]["fuel_cost_change"]) == Decimal(600_000)


def test_sensitivity_requests_are_bounded_and_checked(built: Session, client: TestClient) -> None:
    run = create_run(client)
    path = f"/simulations/{run['id']}/sensitivity"

    too_many = [{"input": f"input_{n}"} for n in range(9)]
    post(client, path, {"inputs": too_many}, 422)
    post(client, path, {"inputs": [{"input": "hedge_ratio", "values": ["1"] * 8}]}, 422)
    error = post(client, path, {"inputs": [{"input": "horizon_months"}]}, 422)
    assert details(error) == [("horizon_months", "sensitivity_limit")]
    error = post(client, path, {"inputs": [{"input": "hedge_ratio", "step": "1e3"}]}, 422)
    assert details(error) == [("inputs[0].step", "invalid_number")]
    post(client, f"/simulations/{uuid.uuid4()}/sensitivity", {}, 404)
    other = create_run(client, crude_oil_change="0", usd_change="1")
    analysis = post(client, path, {}, 201)
    get(client, f"/simulations/{other['id']}/sensitivity/{analysis['id']}", expect=404)


# --- Versions and history -----------------------------------------------------------------------


def test_a_model_whose_code_changed_under_the_same_version_is_refused(
    built: Session, client: TestClient, db_session: Session
) -> None:
    run = create_run(client)
    version = db_session.scalars(select(SimulationModelVersion)).one()
    version.definition_hash = "0" * 64  # as if the stored definition differed from the code
    db_session.commit()

    conflict = post(client, "/simulations", body(), 409)
    check = post(client, f"/simulations/{run['id']}/verify", None, 200)
    post(client, f"/simulations/{run['id']}/sensitivity", {}, 409)

    assert conflict["error"]["code"] == "conflict"
    assert "needs a new version number" in conflict["error"]["message"]
    assert (check["reproduced"], check["definition_matches"]) == (False, False)
    # The stored explanation stays readable.
    assert get(client, f"/simulations/{run['id']}/explanation")["steps"]


def test_a_deprecated_version_keeps_its_runs_but_no_longer_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    deprecated = with_model(status=SimulationModelStatus.DEPRECATED)
    monkeypatch.setattr(simulation_service, "REGISTRY", ModelRegistry([deprecated]))

    error = post(client, "/simulations", {**body(), "model_version": "1.0.0"}, 422)

    assert details(error) == [("model_version", "deprecated_model")]


def test_the_database_protects_stored_history(
    built: Session, client: TestClient, db_session: Session
) -> None:
    run = create_run(client)
    post(client, f"/simulations/{run['id']}/sensitivity", {}, 201)

    with pytest.raises(IntegrityError):  # an analysis keeps its run
        db_session.execute(delete(SimulationRun).where(SimulationRun.id == uuid.UUID(run["id"])))
        db_session.flush()
    db_session.rollback()
    with pytest.raises(IntegrityError):  # a run keeps its model version
        db_session.execute(delete(SimulationModelVersion))
        db_session.flush()
    db_session.rollback()
    with pytest.raises(IntegrityError):  # one row per model version
        db_session.add(
            SimulationModelVersion(
                model_id="airline_fuel_cost",
                version="1.0.0",
                name="Duplicate",
                status=SimulationModelStatus.PREVIEW,
                definition={},
                definition_hash="1" * 64,
            )
        )
        db_session.flush()
    db_session.rollback()


def test_system_reports_the_simulation_capabilities(client: TestClient) -> None:
    capabilities = {item["id"]: item for item in client.get(f"{API}/system").json()["capabilities"]}
    assert capabilities["simulation_engine"]["available"] is True
    assert capabilities["probabilistic_simulation"]["available"] is False
    assert capabilities["scenario_drafts"]["available"] is True
