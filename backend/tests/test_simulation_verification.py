"""The model verification register: every registered model version passes its checks, and
the checks have teeth — a deliberately broken model fails the checks it should, and only
those. Every figure is HYPOTHETICAL (the model pages' worked examples).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.simulation import verification
from app.simulation.registry import REGISTRY, RegisteredModel
from app.simulation.runtime import ComputeContext, ModelResult

API = "/api/v1/simulation-models"
ALL_VERSIONS = [
    model for model_id in sorted(verification.CHECKS) for model in REGISTRY.versions(model_id)
]


def failing(register: verification.Register) -> set[str]:
    return {check.id for check in register.checks if not check.passed}


@pytest.mark.parametrize("model", ALL_VERSIONS, ids=lambda model: model.definition.key)
def test_every_registered_model_version_passes_its_checks(model: RegisteredModel) -> None:
    register = verification.verify(model)

    assert failing(register) == set(), [
        (check.id, check.detail) for check in register.checks if not check.passed
    ]
    kinds = {check.kind for check in register.checks}
    assert kinds == {"reference", "property", "range", "reproducibility"}
    assert any(item[0] == "back_testing" for item in register.not_verified)


def test_every_registered_model_has_checks() -> None:
    assert {model.definition.id for model in REGISTRY.latest()} == set(verification.CHECKS)


def broken(change: Callable[[ModelResult], None]) -> RegisteredModel:
    """The airline model with its computed result altered after the equations ran."""
    model = REGISTRY.get("airline_fuel_cost")
    assert model is not None

    def compute(context: ComputeContext) -> ModelResult:
        result = model.compute(context)
        change(result)
        return result

    return RegisteredModel(definition=model.definition, check=model.check, compute=compute)


def test_a_wrong_total_fails_the_worked_example_and_the_monthly_check() -> None:
    def off_by_one(result: ModelResult) -> None:
        result.scalars["fuel_cost_change"] += Decimal(1)

    register = verification.verify(broken(off_by_one))

    # A constant error also shows with no change at all, breaks proportionality, and is not
    # reached by the contributions (built from differences, which cancel it). A constant
    # offset keeps the direction, the units and the bridge (which does not use this output).
    assert failing(register) == {
        "worked_example",
        "monthly_totals",
        "proportional",
        "no_change_no_effect",
        "contributions_add_up",
    }
    [example] = [check for check in register.checks if check.id == "worked_example"]
    assert example.expected == {"fuel_cost_change": "5250000"}
    assert example.actual == {"fuel_cost_change": "5250001"}


def test_an_effect_without_a_cause_fails_no_change_no_effect() -> None:
    def phantom(result: ModelResult) -> None:
        result.scalars["jet_fuel_price_change"] += Decimal("0.001")

    register = verification.verify(broken(phantom))

    assert "no_change_no_effect" in failing(register)
    assert "bridge_closes" not in failing(register)


def test_a_bridge_that_does_not_close_is_reported_not_raised() -> None:
    def leak(result: ModelResult) -> None:
        result.scalars["fare_recovery"] += Decimal(10)

    register = verification.verify(broken(leak))

    # The engine itself refuses an unbalanced bridge, so every check that runs the model
    # reports the engine's refusal instead of crashing the register.
    [example] = [check for check in register.checks if check.id == "worked_example"]
    assert not example.passed and "bridge does not close" in example.detail


def test_the_command_reports_every_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert verification.main() == 0
    output = capsys.readouterr().out
    for model in ALL_VERSIONS:
        assert model.definition.key in output
    assert "FAIL" not in output


def test_the_register_through_the_api(client: TestClient) -> None:
    response = client.get(f"{API}/floating_rate_interest/verification")

    assert response.status_code == 200, response.text
    register = response.json()
    assert (register["model_id"], register["version"]) == ("floating_rate_interest", "1.0.0")
    assert register["passed"] == register["total"] == 9 and register["failed"] == 0
    limits = next(check for check in register["checks"] if check["id"] == "range_limits")
    assert "repo_rate_change = -25" in limits["actual"]
    assert "not validate" in register["note"]

    older = client.get(f"{API}/airline_fuel_cost/verification", params={"version": "1.0.0"})
    assert older.json()["version"] == "1.0.0"
    assert client.get(f"{API}/no_such_model/verification").status_code == 404
    missing = client.get(f"{API}/airline_fuel_cost/verification", params={"version": "9.9.9"})
    assert missing.status_code == 404
