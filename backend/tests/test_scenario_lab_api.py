"""The Scenario Lab API end to end, on the real database (SQLite or PostgreSQL): versions,
plans and previews, executions and everything read from them, comparisons, templates and
the limits. Company figures are HYPOTHETICAL (``tests/scenario_support.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import ScenarioExecutionStatus
from app.models import ScenarioExecution, ScenarioVersion, SimulationRun
from app.scenario_lab import LAB_VERSION
from app.scenario_lab.explain import TARGETS
from tests.scenario_support import EXPECTED_LINES, brent_only, reference

API = "/api/v1"


@pytest.fixture
def lab(built_graph: Session, client: TestClient) -> Iterator[TestClient]:
    """A client on a database with a built knowledge graph."""
    yield client


def post(client: TestClient, path: str, payload: Any, expect: int) -> Any:
    response = client.post(f"{API}{path}", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def get(client: TestClient, path: str, expect: int = 200, **params: Any) -> Any:
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == expect, response.text
    return response.json()


def put(client: TestClient, path: str, payload: Any, expect: int = 200) -> Any:
    response = client.put(f"{API}{path}", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def details(error: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    return [(item["field"], item["type"]) for item in error["error"]["details"]]


def executed(client: TestClient, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    scenario = post(client, "/scenarios", body, 201)
    execution = post(client, f"/scenarios/{scenario['id']}/executions", {}, 202)
    return scenario["id"], execution


def count(session_factory: sessionmaker[Session], model: Any) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


# --- Versions -----------------------------------------------------------------------------------


def test_saving_adds_versions_and_never_rewrites_one(lab: TestClient) -> None:
    created = post(lab, "/scenarios", reference(), 201)
    path = f"/scenarios/{created['id']}"
    assert created["current_version"] == 1
    assert created["spec"]["entity"] == "company:co_aerisca_airways"
    assert created["spec"]["models"]["floating_rate_interest"]["mode"] == "include"

    same = put(lab, path, {**reference(), "base_version": 1})
    assert same["current_version"] == 1  # nothing changed, no version

    changed = reference(note="Rupee +7 %")
    changed["shocks"][1]["value"] = "7"
    saved = put(lab, path, {**changed, "base_version": 1})
    assert saved["current_version"] == 2
    assert [version["version"] for version in saved["versions"]] == [2, 1]
    assert saved["versions"][0]["note"] == "Rupee +7 %"

    first = get(lab, f"{path}/versions/1")
    assert first["shocks"][1]["value"] == "5"
    assert first["spec_hash"] != saved["versions"][0]["spec_hash"]

    stale = lab.put(f"{API}{path}", json={**reference(), "base_version": 1})
    assert stale.status_code == 409
    assert "was saved after the version you edited" in stale.json()["error"]["message"]

    restored = post(lab, f"{path}/versions/1/restore", None, 200)
    assert restored["current_version"] == 3
    assert restored["versions"][0]["derived_from"] == {
        "kind": "restore",
        "scenario_id": created["id"],
        "version": 1,
    }
    assert restored["versions"][0]["spec_hash"] == first["spec_hash"]
    assert get(lab, f"{path}/versions/9", 404)["error"]["code"] == "not_found"


def test_a_duplicate_is_a_new_scenario_that_remembers_its_origin(lab: TestClient) -> None:
    created = post(lab, "/scenarios", reference(), 201)

    response = lab.post(f"{API}/scenarios/{created['id']}/duplicate", json={"name": "Copy"})

    assert response.status_code == 201
    copy = response.json()
    assert response.headers["Location"] == f"/api/v1/scenarios/{copy['id']}"
    assert (copy["name"], copy["current_version"]) == ("Copy", 1)
    assert copy["versions"][0]["derived_from"]["scenario_id"] == created["id"]
    assert copy["versions"][0]["spec_hash"] != created["versions"][0]["spec_hash"]  # the name
    assert copy["spec"] == created["spec"]


def test_an_executed_scenario_cannot_be_deleted(lab: TestClient) -> None:
    scenario_id, _ = executed(lab, brent_only())
    draft = post(lab, "/scenarios", brent_only(), 201)

    refused = lab.delete(f"{API}/scenarios/{scenario_id}")

    assert refused.status_code == 409
    assert lab.delete(f"{API}/scenarios/{draft['id']}").status_code == 204


def test_malformed_scenarios_are_refused_with_every_field(lab: TestClient) -> None:
    body = reference(
        shocks=[
            {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": "1e3"},
            {"variable_id": "var_rbi_repo_rate", "change_type": "percent_change", "value": "5"},
        ],
    )

    error = post(lab, "/scenarios", body, 422)

    assert details(error) == [("shocks[0].value", "invalid_number")]
    body["shocks"][0]["value"] = "20"
    error = post(lab, "/scenarios", body, 422)
    assert details(error) == [("shocks[1].change_type", "invalid_change")]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        (
            {"stress_cases": [{"name": f"S{index}", "scale": "2"} for index in range(6)]},
            "stress_cases",
        ),
        ({"models": {f"model_{index:03d}": {} for index in range(11)}}, "models"),
        ({"timing": {"horizon_months": 37}}, "timing.horizon_months"),
        ({"entity": "industry:ind_air_transport"}, "entity"),
        ({"constraints": {"evidence": "strong"}}, "constraints.evidence"),
    ],
)
def test_request_shapes_are_bounded(lab: TestClient, changes: dict[str, Any], field: str) -> None:
    error = post(lab, "/scenarios", reference(**changes), 422)

    assert field in [item["field"] for item in error["error"]["details"]]


# --- Plans and previews -------------------------------------------------------------------------


def test_a_plan_explains_itself_and_stores_nothing(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    plan = post(lab, "/scenarios/plan", reference(), 200)

    assert plan["executable"] is True
    statuses = {model["model_id"]: model["status"] for model in plan["models"]}
    assert statuses["floating_rate_interest"] == "included"
    assert statuses["crude_linked_costs"] == "available"
    assert [change["models"] for change in plan["changes"]] == [
        ["airline_fuel_cost"],
        ["airline_fuel_cost", "fx_exposure"],
        ["floating_rate_interest"],
    ]
    assert {issue["code"] for issue in plan["issues"]} >= {"cross_effect", "fictional_entity"}
    assert plan["affected"]["entities"]
    assert count(session_factory, ScenarioVersion) == 0


def test_a_saved_version_can_be_planned(lab: TestClient) -> None:
    created = post(lab, "/scenarios", brent_only(company={}), 201)

    plan = get(lab, f"/scenarios/{created['id']}/plan")

    assert plan["executable"] is False
    fields = {issue["field"] for issue in plan["issues"] if issue["severity"] == "error"}
    assert {"company.annual_revenue", "company.reporting_currency"} <= fields


def test_a_preview_computes_without_storing(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    preview = post(lab, "/scenarios/preview", reference(), 200)

    assert preview["stored"] is False
    lines = {line["id"]: Decimal(line["change"]) for line in preview["results"]["lines"]}
    assert lines == {key: change for key, (_, change) in EXPECTED_LINES.items()}
    assert preview["results"]["execution_id"] is None
    assert preview["pathway"]["nodes"]
    assert count(session_factory, ScenarioExecution) == 0
    assert count(session_factory, SimulationRun) == 0

    blocked = post(lab, "/scenarios/preview", brent_only(company={}), 200)
    assert blocked["results"] is None and blocked["plan"]["executable"] is False


# --- Executions ---------------------------------------------------------------------------------


def test_an_execution_is_accepted_and_followed_to_its_results(lab: TestClient) -> None:
    scenario = post(lab, "/scenarios", reference(), 201)

    response = lab.post(f"{API}/scenarios/{scenario['id']}/executions", json={})

    assert response.status_code == 202
    execution = response.json()
    assert response.headers["Location"] == f"/api/v1/scenario-executions/{execution['id']}"
    assert execution["status"] == "completed"  # inline in tests
    assert execution["poll_after_ms"] is None
    assert [stage["stage"] for stage in execution["stages"]] == [
        "validating",
        "simulating",
        "propagating",
        "aggregating",
    ]
    assert [run["model_id"] for run in execution["runs"]] == [
        "airline_fuel_cost",
        "fx_exposure",
        "floating_rate_interest",
    ]
    assert execution["plan"]["executable"] and execution["lab_version"] == LAB_VERSION
    assert [item["id"] for item in execution["headline"]] == [
        "profit_before_tax",
        "operating_profit",
    ]

    results = get(lab, f"/scenario-executions/{execution['id']}/results")
    lines = {line["id"]: line for line in results["lines"]}
    assert {
        key: (Decimal(line["baseline"]), Decimal(line["change"])) for key, line in lines.items()
    } == EXPECTED_LINES
    assert lines["operating_profit"]["percent_change"] == "-12.65"
    assert lines["operating_costs"]["effect"] == "reduces_profit"
    assert len(lines["revenue"]["monthly"]) == 12
    assert [item["id"] for item in results["not_modelled"]] == ["cash_flow"]
    assert [case["name"] for case in results["stress_cases"]] == ["Half", "Double"]
    assert {event["month"] for event in results["timeline"]["events"]} == {1, 2, 3, 4, 7}
    assert "not forecasts" in results["note"]

    listing = get(lab, f"/scenarios/{scenario['id']}/executions")
    assert [item["id"] for item in listing["items"]] == [execution["id"]]
    assert get(lab, f"/scenarios/{scenario['id']}")["latest_execution"]["id"] == execution["id"]


def test_an_execution_explains_every_line_and_metric(lab: TestClient) -> None:
    _, execution = executed(lab, reference())
    path = f"/scenario-executions/{execution['id']}/explanation"

    for target in TARGETS:
        explanation = get(lab, path, target=target)
        assert explanation["target"] == target
        assert explanation["models"], target
    profit = get(lab, path, target="operating_profit")
    assert profit["equation"]["id"] == "AG3"
    credits = {item["variable_id"]: Decimal(item["value"]) for item in profit["by_change"]}
    assert credits == {"var_brent_crude": Decimal(-5_637_500), "var_usd_inr": Decimal(-687_500)}
    airline = next(model for model in profit["models"] if model["model_id"] == "airline_fuel_cost")
    assert {equation["id"] for equation in airline["equations"]} >= {"E6", "E10", "E11", "E12"}
    assert airline["worked_month"] == 1
    assert airline["transmission"] and airline["graph"]["build_id"] is not None
    assert get(lab, path, 422, target="cash_flow")["error"]["code"] == "validation_error"


def test_a_line_no_model_produces_cannot_be_explained(lab: TestClient) -> None:
    _, execution = executed(lab, brent_only())

    error = get(
        lab, f"/scenario-executions/{execution['id']}/explanation", 404, target="interest_coverage"
    )

    assert "no included model produces it" in error["error"]["message"]


def test_pathways_are_read_from_the_execution(lab: TestClient) -> None:
    _, execution = executed(lab, reference())

    pathway = get(lab, f"/scenario-executions/{execution['id']}/pathways")

    kinds = {link["kind"] for link in pathway["links"]}
    assert kinds == {"applies", "transmission", "equation", "aggregation", "cited"}
    assert {group["id"] for group in pathway["groups"]} == {
        "airline_fuel_cost",
        "fx_exposure",
        "floating_rate_interest",
    }
    assert pathway["unmodelled"]


def test_a_scenario_that_cannot_run_is_refused_and_nothing_is_stored(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    body = brent_only(
        shocks=[
            {
                "variable_id": "var_india_cpi_inflation",
                "change_type": "absolute_change",
                "value": "1",
            }
        ]
    )
    scenario = post(lab, "/scenarios", body, 201)

    error = post(lab, f"/scenarios/{scenario['id']}/executions", {}, 422)

    assert details(error) == [("shocks[0]", "unmodelled_change")]
    assert count(session_factory, ScenarioExecution) == 0


def test_results_exist_only_for_a_completed_execution(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    scenario = post(lab, "/scenarios", brent_only(), 201)
    with session_factory() as session:
        version = session.scalars(select(ScenarioVersion)).one()
        row = ScenarioExecution(
            id=uuid.uuid4(),
            scenario_id=version.scenario_id,
            scenario_version_id=version.id,
            version=1,
            status=ScenarioExecutionStatus.QUEUED,
            stages=[],
            lab_version=LAB_VERSION,
        )
        session.add(row)
        session.commit()
        queued = str(row.id)
    assert scenario["id"] == str(version.scenario_id)

    for path in ("results", "pathways", "explanation"):
        assert get(lab, f"/scenario-executions/{queued}/{path}", 409)["error"]["code"] == "conflict"
    waiting = get(lab, f"/scenario-executions/{queued}")
    assert waiting["poll_after_ms"] == 400 and waiting["results_available"] is False

    cancel = lab.post(f"{API}/scenario-executions/{queued}/cancel")
    assert cancel.status_code == 202 and cancel.json()["cancel_requested"] is True


def test_a_final_execution_cannot_be_cancelled(lab: TestClient) -> None:
    _, execution = executed(lab, brent_only())

    response = lab.post(f"{API}/scenario-executions/{execution['id']}/cancel")

    assert response.status_code == 409


def test_executions_are_bounded_by_the_worker_pool(lab: TestClient, app: FastAPI) -> None:
    scenario = post(lab, "/scenarios", brent_only(), 201)
    runner = app.state.scenario_runner
    for _ in range(runner.capacity):
        runner.reserve()
    try:
        error = post(lab, f"/scenarios/{scenario['id']}/executions", {}, 429)
    finally:
        for _ in range(runner.capacity):
            runner.release()

    assert error["error"]["code"] == "rate_limited"
    assert get(lab, f"/scenarios/{scenario['id']}/executions")["total"] == 0


def test_an_execution_is_reproducible_and_its_runs_are_phase_4_runs(lab: TestClient) -> None:
    _, execution = executed(lab, reference())

    verification = post(lab, f"/scenario-executions/{execution['id']}/verify", None, 200)

    assert verification["reproduced"] is True
    assert all(run["result_hash_matches"] for run in verification["runs"])
    run_id = execution["runs"][0]["run_id"]
    run = get(lab, f"/simulations/{run_id}")
    assert run["model_version"] == "1.1.0"
    assert post(lab, f"/simulations/{run_id}/verify", None, 200)["reproduced"] is True


# --- Sensitivity, comparison, templates ---------------------------------------------------------


def test_a_sensitivity_analysis_is_stored_and_listed(lab: TestClient) -> None:
    _, execution = executed(lab, reference())
    path = f"/scenario-executions/{execution['id']}/sensitivity"

    response = lab.post(f"{API}{path}", json={})

    assert response.status_code == 201
    analysis = response.json()
    assert response.headers["Location"] == f"/api/v1{path}/{analysis['id']}"
    assert analysis["metric"] == "profit_before_tax" and analysis["method"] == "one_at_a_time"
    assert "not a stochastic" in analysis["note"]
    assert [item["id"] for item in get(lab, path)["items"]] == [analysis["id"]]
    assert get(lab, f"{path}/{analysis['id']}")["result_hash"] == analysis["result_hash"]

    custom = post(
        lab,
        path,
        {
            "metric": "operating_margin",
            "inputs": [{"target": "shared:fx_rate", "mode": "values", "values": ["75", 85]}],
        },
        201,
    )
    (item,) = custom["items"]
    assert item["models"] == ["airline_fuel_cost", "fx_exposure"]
    assert [point["value"] for point in item["points"]] == ["75", "85"]
    bad = post(lab, path, {"inputs": [{"target": "change:var_henry_hub_gas"}]}, 422)
    assert details(bad) == [("inputs", "sensitivity_limit")]


def test_executions_are_compared_without_ranking(lab: TestClient) -> None:
    _, first = executed(lab, reference())
    _, second = executed(lab, brent_only())
    params = [("execution_id", first["id"]), ("execution_id", second["id"])]

    response = lab.get(f"{API}/scenario-comparisons", params=params)

    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["reference"] == first["id"]
    assert [row["id"] for row in comparison["lines"]][:3] == [
        "revenue",
        "operating_costs",
        "operating_profit",
    ]
    assert lab.get(f"{API}/scenario-comparisons", params=params[:1]).status_code == 422
    missing = [*params, ("execution_id", str(uuid.uuid4()))]
    assert lab.get(f"{API}/scenario-comparisons", params=missing).status_code == 404
    reference_elsewhere = [*params, ("reference", str(uuid.uuid4()))]
    assert lab.get(f"{API}/scenario-comparisons", params=reference_elsewhere).status_code == 422


def test_templates_list_what_is_implemented_and_what_is_not(lab: TestClient) -> None:
    templates = get(lab, "/scenario-templates")

    assert len(templates["items"]) == 7
    assert [item["id"] for item in templates["unsupported"]] == ["demand", "supply_chain"]
    combined = next(item for item in templates["items"] if item["id"] == "oil_rupee_rates")
    assert [entity["key"] for entity in combined["suggested_entities"]] == [
        "company:co_aerisca_airways",
        "company:co_skyvara_air",
    ]

    detail = get(lab, "/scenario-templates/oil_rupee_rates")
    required = {item["path"] for item in detail["required_inputs"]}
    assert {
        "company.annual_revenue",
        "markets.fx_rate",
        "models.fx_exposure.inputs.annual_usd_costs",
    } <= required
    assert detail["scenario"]["company"]["annual_revenue"] is None  # never filled in
    plan = post(lab, "/scenarios/plan", detail["scenario"], 200)
    assert plan["executable"] is False  # the figures are the user's to enter
    assert get(lab, "/scenario-templates/demand", 404)["error"]["code"] == "not_found"


def test_the_system_reports_the_scenario_lab(client: TestClient) -> None:
    capabilities = {item["id"]: item for item in get(client, "/system")["capabilities"]}

    assert capabilities["scenario_lab"]["available"] is True
    assert capabilities["probabilistic_simulation"]["available"] is False
