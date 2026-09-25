"""The advanced analyses API end to end on the real database: what an execution can vary,
Monte Carlo and joint analyses stored, listed, read and re-run, the limits, and the one-at-a-
time analysis's method version. Company figures are HYPOTHETICAL (``scenario_support``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import ScenarioAnalysis, ScenarioSensitivityAnalysis
from app.scenario_lab.sampling import GENERATOR
from app.services import scenario_analyses
from tests.scenario_support import brent_only, reference

API = "/api/v1"
MONTE_CARLO = {
    "kind": "monte_carlo",
    "metric": "profit_before_tax",
    "draws": 200,
    "seed": 42,
    "quantities": [
        {
            "target": "change:var_brent_crude",
            "distribution": {"kind": "triangular", "low": "-10", "mode": "20", "high": "60"},
        },
        {
            "target": "model:floating_rate_interest:repo_repricing_lag",
            "distribution": {"kind": "discrete", "values": [0, 3, 6], "weights": [1, 2, 1]},
        },
    ],
}


@pytest.fixture
def lab(built_graph: Session, client: TestClient) -> Iterator[TestClient]:
    yield client


def post(client: TestClient, path: str, payload: Any, expect: int) -> Any:
    response = client.post(f"{API}{path}", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def get(client: TestClient, path: str, expect: int = 200) -> Any:
    response = client.get(f"{API}{path}")
    assert response.status_code == expect, response.text
    return response.json()


def executed(client: TestClient, body: dict[str, Any]) -> str:
    scenario = post(client, "/scenarios", body, 201)
    return str(post(client, f"/scenarios/{scenario['id']}/executions", {}, 202)["id"])


def stored(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(ScenarioAnalysis)) or 0


def test_the_targets_list_what_an_execution_can_vary(lab: TestClient) -> None:
    execution = executed(lab, reference())

    listing = get(lab, f"/scenario-executions/{execution}/analysis-targets")

    targets = {item["id"]: item for item in listing["targets"]}
    crude = targets["change:var_brent_crude"]
    assert (crude["unit"], crude["base_value"], crude["integer"]) == ("percent_change", "20", False)
    assert (crude["minimum"], crude["maximum"]) == ("-100", "1000")
    assert crude["default_variation"] == {"mode": "absolute", "step": "10"}
    assert targets["shared:annual_revenue"]["models"] == [
        "airline_fuel_cost",
        "fx_exposure",
        "floating_rate_interest",
    ]
    assert targets["shared:annual_revenue"]["unit_label"] == "INR per year"
    lag = targets["model:floating_rate_interest:repo_repricing_lag"]
    assert (lag["integer"], lag["max_decimals"], lag["base_value"]) == (True, 0, "3")
    metrics = {item["id"]: item for item in listing["metrics"]}
    assert metrics["profit_before_tax"]["base"] == "-6700000"
    assert metrics["interest_coverage"]["kind"] == "metric_value"
    assert listing["limits"]["monte_carlo"]["max_draws"] == 2_000
    assert listing["limits"]["joint"]["max_axis_points"] == 7


def test_a_monte_carlo_analysis_is_stored_read_and_reproduced(lab: TestClient) -> None:
    execution = executed(lab, reference())
    path = f"/scenario-executions/{execution}/analyses"

    response = lab.post(f"{API}{path}", json=MONTE_CARLO)

    assert response.status_code == 201, response.text
    analysis = response.json()
    assert response.headers["Location"] == f"/api/v1{path}/{analysis['id']}"
    assert analysis["kind"] == "monte_carlo" and analysis["joint"] is None
    config = analysis["config"]
    assert (config["seed"], config["draws"], config["generator"]) == (42, 200, GENERATOR)
    assert [run["model_id"] for run in config["runs"]] == [
        "airline_fuel_cost",
        "floating_rate_interest",
        "fx_exposure",
    ]
    assert all(run["graph_build_id"] is not None for run in config["runs"])
    results = analysis["monte_carlo"]
    assert results["accepted"] == 200
    assert [item["distribution"]["kind"] for item in results["quantities"]] == [
        "triangular",
        "discrete",
    ]
    assert results["quantities"][1]["distribution"]["weights"] == ["1", "2", "1"]
    assert "not a forecast" in analysis["note"]

    listing = get(lab, path)["items"]
    assert [(item["id"], item["draws"], item["seed"]) for item in listing] == [
        (analysis["id"], 200, 42)
    ]
    assert listing[0]["quantities"] == [item["label"] for item in results["quantities"]]
    assert listing[0]["quantities"][0] == "Crude oil price change"
    assert get(lab, f"{path}/{analysis['id']}")["result_hash"] == analysis["result_hash"]

    check = post(lab, f"{path}/{analysis['id']}/verify", {}, 200)
    assert check["reproduced"] is True and "seed 42" in check["message"]

    again = post(lab, path, MONTE_CARLO, 201)
    assert again["id"] != analysis["id"]
    assert again["result_hash"] == analysis["result_hash"]  # same seed, same results


def test_a_seed_is_chosen_and_recorded_when_none_is_given(lab: TestClient) -> None:
    execution = executed(lab, reference())
    path = f"/scenario-executions/{execution}/analyses"

    analysis = post(lab, path, {**MONTE_CARLO, "seed": None}, 201)

    assert isinstance(analysis["config"]["seed"], int)
    assert 0 <= analysis["config"]["seed"] < 2**53
    assert analysis["request"]["seed"] == analysis["config"]["seed"]
    assert post(lab, f"{path}/{analysis['id']}/verify", {}, 200)["reproduced"] is True


def test_a_joint_analysis_through_the_api(lab: TestClient) -> None:
    execution = executed(lab, reference())
    path = f"/scenario-executions/{execution}/analyses"

    analysis = post(
        lab,
        path,
        {
            "kind": "joint_sensitivity",
            "metric": "operating_profit",
            "rows": {"target": "change:var_brent_crude"},
            "columns": {"target": "change:var_usd_inr"},
        },
        201,
    )

    grid = analysis["joint"]
    assert analysis["monte_carlo"] is None and analysis["config"]["seed"] is None
    assert grid["cells"][0][0]["interaction"] == "-137500"
    assert grid["summary"]["additive"] is False
    assert "No probability" in analysis["note"]
    summary = get(lab, path)["items"][0]
    assert summary["largest_interaction"] == "-137500"
    assert post(lab, f"{path}/{analysis['id']}/verify", {}, 200)["reproduced"] is True


@pytest.mark.parametrize(
    ("payload", "field", "kind"),
    [
        ({**MONTE_CARLO, "kind": "bootstrap"}, None, None),
        ({**MONTE_CARLO, "surprise": 1}, None, None),
        ({**MONTE_CARLO, "draws": 50}, None, None),
        ({**MONTE_CARLO, "seed": -1}, None, None),
        ({**MONTE_CARLO, "seed": 2**53}, None, None),  # beyond what a browser reads exactly
        (
            {
                **MONTE_CARLO,
                "quantities": [
                    {
                        "target": "change:var_brent_crude",
                        "distribution": {"kind": "uniform", "low": "30", "high": "10"},
                    }
                ],
            },
            "quantities[0]",
            "analysis_limit",
        ),
        (
            {
                **MONTE_CARLO,
                "quantities": [
                    {
                        "target": "change:var_brent_crude",
                        "distribution": {"kind": "uniform", "low": "ten", "high": "10"},
                    }
                ],
            },
            "quantities[0].distribution.low",
            "invalid_number",
        ),
        (
            {
                "kind": "joint_sensitivity",
                "rows": {"target": "change:var_brent_crude"},
                "columns": {"target": "change:var_brent_crude"},
            },
            "columns",
            "analysis_limit",
        ),
    ],
)
def test_invalid_requests_are_refused_and_nothing_is_stored(
    lab: TestClient,
    session_factory: sessionmaker[Session],
    payload: dict[str, Any],
    field: str | None,
    kind: str | None,
) -> None:
    execution = executed(lab, reference())

    error = post(lab, f"/scenario-executions/{execution}/analyses", payload, 422)

    if field is not None:
        assert [(item["field"], item["type"]) for item in error["error"]["details"]] == [
            (field, kind)
        ]
    assert stored(session_factory) == 0


def test_unknown_executions_and_analyses_are_not_found(lab: TestClient) -> None:
    execution = executed(lab, brent_only())
    missing = uuid.uuid4()

    get(lab, f"/scenario-executions/{missing}/analysis-targets", 404)
    post(lab, f"/scenario-executions/{missing}/analyses", MONTE_CARLO, 404)
    get(lab, f"/scenario-executions/{missing}/analyses", 404)
    get(lab, f"/scenario-executions/{execution}/analyses/{missing}", 404)
    post(lab, f"/scenario-executions/{execution}/analyses/{missing}/verify", {}, 404)


def test_a_changed_stored_request_is_not_reproduced(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    execution = executed(lab, reference())
    path = f"/scenario-executions/{execution}/analyses"
    analysis = post(lab, path, MONTE_CARLO, 201)
    with session_factory() as session:
        row = session.get_one(ScenarioAnalysis, uuid.UUID(analysis["id"]))
        session.execute(
            update(ScenarioAnalysis)
            .where(ScenarioAnalysis.id == row.id)
            .values(request={**row.request, "seed": 43})
        )
        session.commit()

    check = post(lab, f"{path}/{analysis['id']}/verify", {}, 200)

    assert check["reproduced"] is False
    assert check["inputs_hash_matches"] is False and check["result_hash_matches"] is False


def test_at_most_two_analyses_compute_at_once(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    execution = executed(lab, reference())
    held = [scenario_analyses._slots.acquire(blocking=False) for _ in range(2)]
    try:
        error = post(lab, f"/scenario-executions/{execution}/analyses", MONTE_CARLO, 429)
    finally:
        for taken in held:
            if taken:
                scenario_analyses._slots.release()

    assert error["error"]["code"] == "rate_limited"
    assert stored(session_factory) == 0
    post(lab, f"/scenario-executions/{execution}/analyses", MONTE_CARLO, 201)


def test_the_sensitivity_method_is_recorded_and_older_results_carry_a_caveat(
    lab: TestClient, session_factory: sessionmaker[Session]
) -> None:
    execution = executed(lab, reference())
    path = f"/scenario-executions/{execution}/sensitivity"
    request = {
        "metric": "operating_margin",
        "inputs": [{"target": "shared:annual_revenue", "mode": "relative", "step": "10"}],
    }

    current = post(lab, path, request, 201)
    assert (current["method_version"], current["caveats"]) == ("1.1.0", [])
    # As an analysis stored before the correction would read.
    with session_factory() as session:
        session.execute(
            update(ScenarioSensitivityAnalysis)
            .where(ScenarioSensitivityAnalysis.id == uuid.UUID(current["id"]))
            .values(method_version="1.0.0")
        )
        session.commit()

    older = get(lab, f"{path}/{current['id']}")
    assert older["method_version"] == "1.0.0"
    [caveat] = older["caveats"]
    assert "method 1.0.0" in caveat and "operating margin" in caveat
