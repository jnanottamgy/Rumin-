"""The Scenario Lab below the API: specs, validation, profiles, templates, planning,
aggregation, pathways, timeline, execution stages, the runner, reproducibility,
sensitivity and comparison — on the real database with a built knowledge graph.

Company figures are HYPOTHETICAL (``tests/scenario_support.py``), worked out by hand.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import ChangeType, ScenarioExecutionStatus
from app.models import (
    Scenario,
    ScenarioExecution,
    ScenarioExecutionRun,
    ScenarioVersion,
    SimulationRun,
)
from app.scenario_lab import LAB_VERSION
from app.scenario_lab.aggregate import IDENTITY_TOLERANCE
from app.scenario_lab.comparison import compare
from app.scenario_lab.executor import (
    _timeline,
    combine,
    evaluate_stress,
    members_of,
    run_execution,
    simulate,
    spec_of,
)
from app.scenario_lab.pathways import complete, trace
from app.scenario_lab.planner import Plan, build_plan
from app.scenario_lab.profiles import (
    ITEMS,
    PROFILES,
    LineContribution,
    check_profiles,
    scenario_events,
)
from app.scenario_lab.runner import ExecutionRunner, RunnerBusy, recover
from app.scenario_lab.sensitivity import Item, LabSensitivityError, analyse, default_items
from app.scenario_lab.spec import ScenarioSpec, from_parts, spec_hash, spec_json
from app.scenario_lab.templates import TEMPLATES, UNSUPPORTED, requirements, spec_for
from app.scenario_lab.validation import load_variables, validate_spec
from app.schemas.scenario import ScenarioInput
from app.services import scenarios as scenario_service
from tests.conftest import wipe_scenarios
from tests.scenario_support import AERISCA, EXPECTED_LINES, D, brent_only, near, reference

S = ScenarioExecutionStatus


@pytest.fixture(autouse=True)
def _no_scenarios(session_factory: sessionmaker[Session]) -> Iterator[None]:
    with session_factory() as session:
        wipe_scenarios(session)
    yield
    with session_factory() as session:
        wipe_scenarios(session)


def stored(value: dict[str, Any] | None) -> dict[str, Any]:
    assert value is not None
    return value


def to_spec(body: dict[str, Any]) -> ScenarioSpec:
    return scenario_service.to_spec(ScenarioInput.model_validate(body))


def plan_of(session: Session, body: dict[str, Any]) -> Plan:
    return build_plan(
        session,
        to_spec(body),
        freshness=scenario_service.freshness(session),
        variables=load_variables(session),
    )


def statuses(plan: Plan) -> dict[str, str]:
    return {item.model_id: item.status for item in plan.models}


def issue_codes(plan: Plan, severity: str = "error") -> list[str]:
    return [issue.code for issue in plan.all_issues if issue.severity == severity]


def computed(plan: Plan) -> Any:
    members = members_of(plan)
    executions = simulate(members)
    return (
        members,
        executions,
        combine(plan.spec, members, executions, evaluate_stress(plan.spec, members)),
    )


def queue(session: Session, body: dict[str, Any]) -> uuid.UUID:
    """Store the scenario and a queued execution of its version 1 (as the API would)."""
    created = scenario_service.create_scenario(session, ScenarioInput.model_validate(body))
    version = session.scalars(
        select(ScenarioVersion).where(ScenarioVersion.scenario_id == created.id)
    ).one()
    row = ScenarioExecution(
        id=uuid.uuid4(),
        scenario_id=created.id,
        scenario_version_id=version.id,
        version=1,
        status=S.QUEUED,
        stages=[],
        lab_version=LAB_VERSION,
    )
    session.add(row)
    session.commit()
    return row.id


def carry_out(factory: sessionmaker[Session], execution_id: uuid.UUID, **options: Any) -> None:
    run_execution(
        factory,
        execution_id,
        freshness=scenario_service.freshness,
        timeout_seconds=options.get("timeout_seconds", 20.0),
    )


# --- Specs and validation -----------------------------------------------------------------------


def test_the_spec_hash_ignores_how_numbers_were_typed() -> None:
    typed = reference()
    typed["shocks"][0]["value"] = 20
    typed["company"]["annual_revenue"] = "0300000000.00"
    changed = reference()
    changed["shocks"][0]["value"] = "21"

    assert spec_hash(to_spec(typed)) == spec_hash(to_spec(reference()))
    assert spec_hash(to_spec(changed)) != spec_hash(to_spec(reference()))


def test_a_spec_round_trips_through_its_stored_form() -> None:
    spec = to_spec(reference())
    stored = from_parts(
        name=spec.name,
        description=spec.description,
        template_id=spec.template_id,
        shocks=spec.shocks,
        spec=spec_json(spec),
    )

    assert stored == spec
    assert spec_hash(stored) == spec_hash(spec)


@pytest.mark.parametrize(
    ("changes", "field", "code"),
    [
        ({"models": {"no_such_model": {}}}, "models.no_such_model", "unknown_model"),
        (
            {"models": {"fx_exposure": {"inputs": {"annual_revenue": {"value": "1"}}}}},
            "models.fx_exposure.inputs.annual_revenue",
            "unknown_input",
        ),
        (
            {"models": {"fx_exposure": {"assumptions": {"fare_pass_through": "5"}}}},
            "models.fx_exposure.assumptions.fare_pass_through",
            "unknown_input",
        ),
        (
            {"models": {"fx_exposure": {"assumptions": {"cost_hedge_ratio": "lots"}}}},
            "models.fx_exposure.assumptions.cost_hedge_ratio",
            "invalid_number",
        ),
        ({"timing": {"start_month": 13, "horizon_months": 12}}, "timing.start_month", "timing"),
        ({"company": {"annual_revenue": "-5"}}, "company.annual_revenue", "input_range"),
        ({"company": {"annual_revenue": "1e6"}}, "company.annual_revenue", "invalid_number"),
        ({"entity": "company:co_does_not_exist"}, "entity", "entity_unavailable"),
        ({"template_id": "no_such_template"}, "template_id", "unknown_template"),
        (
            {"stress_cases": [{"name": "Both", "scale": "2", "changes": {"var_brent_crude": "5"}}]},
            "stress_cases[0]",
            "stress_case",
        ),
        (
            {"stress_cases": [{"name": "Zero", "scale": "0"}]},
            "stress_cases[0].scale",
            "stress_case",
        ),
        (
            {"stress_cases": [{"name": "Huge", "scale": "11"}]},
            "stress_cases[0].scale",
            "stress_case",
        ),
        (
            {"stress_cases": [{"name": "Other", "changes": {"var_henry_hub_gas": "5"}}]},
            "stress_cases[0].changes.var_henry_hub_gas",
            "stress_case",
        ),
        (
            # Brent 20 % × 60 = 1,200 %: beyond the change rules, refused (not clipped).
            {
                "stress_cases": [
                    {"name": "Too far", "scale": "10"},
                    {"name": "too far", "scale": "1"},
                ]
            },
            "stress_cases[1].name",
            "duplicate_name",
        ),
    ],
)
def test_saving_refuses_malformed_scenarios(
    built_graph: Session, changes: dict[str, Any], field: str, code: str
) -> None:
    issues = validate_spec(built_graph, to_spec(reference(**changes)), load_variables(built_graph))

    assert (field, code) in [(issue.field, issue.code) for issue in issues]


def test_a_stress_case_that_breaks_the_change_rules_is_refused_not_clipped(
    built_graph: Session,
) -> None:
    body = brent_only(
        shocks=[
            {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": "200"}
        ],
        stress_cases=[{"name": "Six times", "scale": "6"}],
    )

    issues = validate_spec(built_graph, to_spec(body), load_variables(built_graph))

    assert [(issue.field, issue.code) for issue in issues] == [
        ("stress_cases[0].scale", "stress_case")
    ]
    assert "1200" in issues[0].message


# --- Profiles and templates ---------------------------------------------------------------------


def test_every_profile_matches_its_model_and_no_item_is_claimed_twice() -> None:
    check_profiles(PROFILES)
    claimed = [(line.line, line.item) for profile in PROFILES.values() for line in profile.lines]

    assert len(claimed) == len(set(claimed))
    assert {item for _, item in claimed} <= set(ITEMS)


def test_a_profile_that_claims_another_models_item_is_refused() -> None:
    thief = replace(
        PROFILES["fx_exposure"],
        lines=(
            LineContribution(
                "operating_costs", "jet_fuel", "Jet fuel", "cost_change", "cost_change", ()
            ),
        ),
    )

    with pytest.raises(ValueError, match="both cover"):
        check_profiles({**PROFILES, "fx_exposure": thief})


def test_templates_are_built_on_implemented_models_only() -> None:
    for template in TEMPLATES:
        needs = requirements(template)
        spec = spec_for(template)
        assert spec.reporting_currency is None and spec.annual_revenue is None  # no figures
        assert needs["required_inputs"], template.id
        assert all(model in PROFILES for model in template.models)
        for shock in template.shocks:
            assert any(
                (binding := PROFILES[model].binding(shock.variable_id)) is not None
                and binding.change_type is shock.change_type
                for model in template.models
            )
    assert {item["id"] for item in UNSUPPORTED} == {"demand", "supply_chain"}


# --- Planning -----------------------------------------------------------------------------------


def test_a_model_applies_by_default_when_the_graph_states_the_exposure(
    built_graph: Session,
) -> None:
    plan = plan_of(built_graph, brent_only())

    assert plan.executable, plan.errors
    assert statuses(plan) == {
        "airline_fuel_cost": "included",
        "fx_exposure": "not_applicable",
        "floating_rate_interest": "not_applicable",
        "crude_linked_costs": "available",
        "gas_linked_costs": "not_applicable",
    }
    airline = next(item for item in plan.models if item.model_id == "airline_fuel_cost")
    (chain,) = airline.exposure
    assert [(edge.edge_type, edge.source, edge.target) for edge in chain] == [
        ("affects_costs", "variable:var_jet_fuel", "industry:ind_air_transport"),
        ("in_industry", AERISCA, "industry:ind_air_transport"),
    ]
    assert "decides whether the model applies, not how much" in airline.reasons[0]


def test_a_model_that_requires_an_exposure_does_not_apply_without_it(built_graph: Session) -> None:
    body = brent_only(entity="company:co_deltrin_refining")

    plan = plan_of(built_graph, body)

    assert statuses(plan)["airline_fuel_cost"] == "not_applicable"
    assert statuses(plan)["crude_linked_costs"] == "blocked"  # applies, lacks its figures
    assert "unmodelled_change" in issue_codes(plan)
    assert ("models.crude_linked_costs.inputs.linked_annual_cost", "required") in [
        (issue.field, issue.code) for issue in plan.errors
    ]
    assert not plan.executable


def test_without_a_company_models_run_only_when_included(built_graph: Session) -> None:
    body = brent_only(entity=None)
    body["models"]["airline_fuel_cost"]["mode"] = "include"
    available = brent_only(entity=None)

    assert statuses(plan_of(built_graph, body))["airline_fuel_cost"] == "included"
    assert statuses(plan_of(built_graph, available))["airline_fuel_cost"] == "available"
    assert not plan_of(built_graph, available).executable


def test_every_change_must_be_modelled(built_graph: Session) -> None:
    excluded = brent_only()
    excluded["models"]["airline_fuel_cost"]["mode"] = "exclude"
    absolute = brent_only(
        shocks=[{"variable_id": "var_brent_crude", "change_type": "absolute_change", "value": "10"}]
    )
    cpi = brent_only(
        shocks=[
            *brent_only()["shocks"],
            {
                "variable_id": "var_india_cpi_inflation",
                "change_type": "absolute_change",
                "value": "1",
            },
        ]
    )

    plan = plan_of(built_graph, excluded)
    assert statuses(plan)["airline_fuel_cost"] == "excluded"
    assert "unmodelled_change" in issue_codes(plan)
    (reason,) = [change.reason for change in plan_of(built_graph, absolute).changes]
    assert reason is not None and "never converted" in reason
    unmodelled = [change for change in plan_of(built_graph, cpi).changes if not change.modelled]
    assert [change.shock.variable_id for change in unmodelled] == ["var_india_cpi_inflation"]
    assert "No registered model" in (unmodelled[0].reason or "")


def test_the_evidence_constraint_refuses_relationships_that_are_assumptions(
    built_graph: Session,
) -> None:
    with_company = brent_only(constraints={"evidence": "evidence_backed"})
    without = brent_only(entity=None, constraints={"evidence": "evidence_backed"})
    without["models"]["airline_fuel_cost"]["mode"] = "include"

    # The sample graph states the airline's exposure as a model assumption: not counted.
    assert statuses(plan_of(built_graph, with_company))["airline_fuel_cost"] == "not_applicable"
    plan = plan_of(built_graph, without)
    assert statuses(plan)["airline_fuel_cost"] == "blocked"
    assert ("constraints.evidence", "constraint_evidence") in [
        (issue.field, issue.code) for issue in plan.errors
    ]


def test_the_stored_data_constraint_refuses_typed_market_baselines(built_graph: Session) -> None:
    plan = plan_of(built_graph, brent_only(constraints={"stored_market_data": True}))

    fields = {issue.field for issue in plan.errors if issue.code == "constraint_stored_data"}
    assert fields == {"markets.fx_rate", "models.airline_fuel_cost.inputs.jet_fuel_price"}
    assert statuses(plan)["airline_fuel_cost"] == "blocked"


def test_models_that_touch_the_same_costs_carry_a_caution(built_graph: Session) -> None:
    plan = plan_of(built_graph, reference())

    assert plan.executable, plan.errors
    assert [issue.code for issue in plan.cautions] == ["cross_effect"]
    assert "Leave jet fuel out of the US-dollar costs" in plan.cautions[0].message


def test_the_plan_previews_the_companies_the_graph_ties_to_the_changes(
    built_graph: Session,
) -> None:
    plan = plan_of(built_graph, brent_only())

    assert plan.affected is not None
    ties = {
        entry["entity"]["key"]: {model for item in entry["exposures"] for model in item["models"]}
        for entry in plan.affected["entities"]
    }
    assert ties[AERISCA] == {"airline_fuel_cost"}
    assert ties["company:co_deltrin_refining"] == {"crude_linked_costs"}
    assert ties["company:co_orvane_petroleum"] == set()  # stated, but no model simulates it
    assert "not evidence of causation" in plan.affected["note"]


# --- Aggregation, pathway and timeline ----------------------------------------------------------


def test_the_lines_add_the_models_items_worked_out_by_hand(built_graph: Session) -> None:
    plan = plan_of(built_graph, reference())
    _, executions, combined = computed(plan)

    lines = combined.main.lines
    assert {key: (line.baseline, line.change) for key, line in lines.items()} == EXPECTED_LINES
    for line in lines.values():
        assert abs(sum(line.by_change.values(), D(0)) - line.change) <= IDENTITY_TOLERANCE
    assert lines["operating_costs"].by_change == {
        "var_brent_crude": D("9225000"),
        "var_usd_inr": D("4025000"),
    }
    margin = combined.main.metrics["operating_margin"]
    coverage = combined.main.metrics["interest_coverage"]
    assert near(margin.baseline, D(50) / D(300))
    assert near(margin.scenario, D("43.675") / D("306.925"))
    assert near(coverage.baseline, D(50) / D(12))
    assert near(coverage.scenario, D("43.675") / D("12.375"))
    assert [step["equation"] for step in combined.steps] == [
        "AG1",
        "AG2",
        "AG3",
        "AG4",
        "AG5",
        "AG6",
        "AG7",
    ]
    # AG3's check: the models' own operating-profit changes add up to the line.
    own = sum(
        (
            executions[model_id].outputs["operating_profit_change"]["value"]
            for model_id in executions
            if PROFILES[model_id].operating_profit_output
        ),
        D(0),
    )
    assert own == lines["operating_profit"].change


def test_with_one_model_the_lab_agrees_with_the_model(built_graph: Session) -> None:
    plan = plan_of(built_graph, brent_only())
    _, executions, combined = computed(plan)
    outputs = executions["airline_fuel_cost"].outputs

    assert (
        combined.main.lines["operating_profit"].change
        == outputs["operating_profit_change"]["value"]
    )
    assert near(
        combined.main.metrics["operating_margin"].scenario,
        outputs["scenario_operating_margin"]["value"],
        "1e-10",
    )
    assert "interest_expense" not in combined.main.lines  # not modelled, not zero


def test_interest_alone_holds_operating_profit_at_its_baseline(built_graph: Session) -> None:
    body = reference(
        entity="company:co_gridwell_power",
        shocks=[reference()["shocks"][2]],
        models={"floating_rate_interest": reference()["models"]["floating_rate_interest"]},
        stress_cases=[],
    )
    plan = plan_of(built_graph, body)
    _, executions, combined = computed(plan)
    outputs = executions["floating_rate_interest"].outputs

    assert set(combined.main.lines) == {"interest_expense", "profit_before_tax"}
    assert combined.main.lines["profit_before_tax"].change == D(-375000)
    assert "held at its baseline" in (combined.main.lines["profit_before_tax"].note or "")
    assert near(
        combined.main.metrics["interest_coverage"].scenario,
        outputs["scenario_interest_coverage"]["value"],
        "1e-10",
    )


def test_stress_cases_reuse_the_models_and_assumptions(built_graph: Session) -> None:
    plan = plan_of(built_graph, reference())
    _, _, combined = computed(plan)
    half, double = combined.stress

    # Interest is linear in the rate change: ×0.5 and ×2 exactly.
    assert half.lines["interest_expense"].change == D(187500)
    assert double.lines["interest_expense"].change == D(750000)
    # US-dollar revenue at +10 % for 12 months: 40,000,000 × 10 %.
    items = {item["item"]: item["value"] for item in double.lines["revenue"].items}
    assert items["usd_revenue"] == D(4_000_000)


def test_the_pathway_shows_only_what_the_engine_computed(built_graph: Session) -> None:
    plan = plan_of(built_graph, brent_only())
    _, executions, combined = computed(plan)
    pathway = complete(trace(plan, executions), plan, combined.main)
    nodes = {node["id"]: node for node in pathway["nodes"]}
    links = {link["id"]: link for link in pathway["links"]}

    transmission = links[
        "airline_fuel_cost:variable:var_brent_crude→airline_fuel_cost:variable:var_jet_fuel"
    ]
    assert transmission["kind"] == "transmission"
    assert transmission["simulation"] == "propagated"
    assert transmission["coefficient"] == "1"
    assert transmission["lag_months"] == 1
    assert transmission["edge"]["evidence_status"] == "model_assumption"
    assert {entry["id"] for entry in transmission["assumptions"]} >= {
        "crude_pass_through",
        "crude_pass_through_lag",
    }
    # The rupee did not change, so nothing about it is drawn.
    assert not any("var_usd_inr" in node_id for node_id in nodes)
    assert nodes["airline_fuel_cost:variable:var_jet_fuel"]["first_month"] == 2
    cited = [link for link in pathway["links"] if link["kind"] == "cited"]
    assert cited and all(link["simulation"] == "context_only" for link in cited)
    unmodelled = {(edge["source"], edge["target"]) for edge in pathway["unmodelled"]}
    assert ("variable:var_brent_crude", "variable:var_india_cpi_inflation") in unmodelled
    used = {link["edge"]["edge_key"] for link in pathway["links"] if link["edge"]}
    assert not used & {edge["edge_key"] for edge in pathway["unmodelled"]}


def test_timeline_events_follow_from_the_runs(built_graph: Session) -> None:
    body = reference(timing={"start_month": 1, "duration_months": 9, "horizon_months": 12})
    plan = plan_of(built_graph, body)
    members, executions, combined = computed(plan)

    events = [
        (event["month"], event["label"])
        for event in _timeline(plan.spec, members, executions, combined.main)["events"]
    ]

    assert events == [
        (1, "The changes take effect"),
        (2, "The crude oil change reaches jet fuel (1-month lag)"),
        (3, "Fares start to recover fuel costs"),
        (4, "Repo-linked loans reprice"),
        (7, "Fuel hedges expire"),
        (10, "The changes end; the variables return to their baselines"),
    ]
    assert scenario_events(1, 12, 12)[-1].month == 1  # no end event when they last


# --- Execution ----------------------------------------------------------------------------------


def test_an_execution_records_its_stages_and_stores_every_model_run(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    execution_id = queue(built_graph, reference())
    carry_out(session_factory, execution_id)

    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        assert row.status is S.COMPLETED, row.error
        assert [stage["stage"] for stage in row.stages] == [
            "validating",
            "simulating",
            "propagating",
            "aggregating",
        ]
        assert all(stage["finished_at"] >= stage["started_at"] for stage in row.stages)
        assert [(run.position, run.model_id) for run in row.runs] == [
            (0, "airline_fuel_cost"),
            (1, "fx_exposure"),
            (2, "floating_rate_interest"),
        ]
        lines = {line["id"]: D(line["change"]) for line in stored(row.results)["lines"]}
        assert lines == {key: change for key, (_, change) in EXPECTED_LINES.items()}
        assert stored(row.plan)["executable"] and row.inputs_hash and row.result_hash
        assert row.duration_ms is not None


def test_executing_the_same_version_twice_gives_the_same_hashes(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    first = queue(built_graph, brent_only())
    carry_out(session_factory, first)
    with session_factory() as session:
        original = session.get_one(ScenarioExecution, first)
        second = ScenarioExecution(
            id=uuid.uuid4(),
            scenario_id=original.scenario_id,
            scenario_version_id=original.scenario_version_id,
            version=1,
            status=S.QUEUED,
            stages=[],
            lab_version=LAB_VERSION,
        )
        session.add(second)
        session.commit()
        second_id = second.id
    carry_out(session_factory, second_id)

    with session_factory() as session:
        a = session.get_one(ScenarioExecution, first)
        b = session.get_one(ScenarioExecution, second_id)
        assert (a.inputs_hash, a.result_hash) == (b.inputs_hash, b.result_hash)
        assert stored(a.results)["lines"] == stored(b.results)["lines"]


def test_a_cancelled_execution_stores_nothing(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    execution_id = queue(built_graph, brent_only())
    with session_factory() as session:
        session.get_one(ScenarioExecution, execution_id).cancel_requested = True
        session.commit()

    carry_out(session_factory, execution_id)

    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        assert row.status is S.CANCELLED
        assert stored(row.error)["code"] == "cancelled"
        assert row.results is None and row.runs == []
        assert session.scalar(select(func.count()).select_from(SimulationRun)) == 0


def test_an_execution_that_runs_out_of_time_is_stopped(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    execution_id = queue(built_graph, brent_only())

    carry_out(session_factory, execution_id, timeout_seconds=-1)

    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        assert (row.status, stored(row.error)["code"]) == (S.FAILED, "timeout")
        assert row.results is None and row.runs == []


def test_a_version_that_cannot_run_fails_with_its_plan(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    # Stored directly (the API would refuse it): the airline's figures are missing.
    body = brent_only(company={}, markets={})
    execution_id = queue(built_graph, body)

    carry_out(session_factory, execution_id)

    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        assert (row.status, stored(row.error)["code"]) == (S.FAILED, "plan_blocked")
        assert row.plan is not None and not stored(row.plan)["executable"]
        assert {detail["field"] for detail in stored(row.error)["details"]} >= {
            "company.annual_revenue",
            "markets.fx_rate",
        }


def test_a_final_execution_is_never_run_again(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    execution_id = queue(built_graph, brent_only())
    carry_out(session_factory, execution_id)
    with session_factory() as session:
        before = session.get_one(ScenarioExecution, execution_id).finished_at

    carry_out(session_factory, execution_id)

    with session_factory() as session:
        assert session.get_one(ScenarioExecution, execution_id).finished_at == before
        assert session.scalar(select(func.count()).select_from(ScenarioExecutionRun)) == 1


# --- The runner ---------------------------------------------------------------------------------


def test_the_runner_refuses_work_beyond_its_capacity(
    session_factory: sessionmaker[Session],
) -> None:
    runner = ExecutionRunner(
        session_factory, freshness=scenario_service.freshness, max_concurrent=1, max_queued=1
    )
    runner.reserve()
    runner.reserve()

    with pytest.raises(RunnerBusy, match="limit is 2"):
        runner.reserve()
    runner.release()
    runner.reserve()
    assert runner.pending == 2


def test_executions_left_unfinished_by_a_stopped_server_are_marked_failed(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    execution_id = queue(built_graph, brent_only())
    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        row.status = S.SIMULATING
        row.stages = [
            {
                "stage": "validating",
                "started_at": "2026-09-24T00:00:00+00:00",
                "finished_at": None,
                "detail": "",
            }
        ]
        session.commit()

    assert recover(session_factory) == 1

    with session_factory() as session:
        row = session.get_one(ScenarioExecution, execution_id)
        assert (row.status, stored(row.error)["code"]) == (S.FAILED, "interrupted")
        assert row.stages[0]["finished_at"] is not None


def test_the_threaded_runner_carries_out_executions(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    runner = ExecutionRunner(session_factory, freshness=scenario_service.freshness, mode="thread")
    runner.start()
    ids = [queue(built_graph, brent_only()) for _ in range(3)]
    for execution_id in ids:
        runner.reserve()
        runner.submit(execution_id)
    runner.stop(drain=True)

    with session_factory() as session:
        assert [session.get_one(ScenarioExecution, item).status for item in ids] == [
            S.COMPLETED
        ] * 3
    assert runner.pending == 0


# --- Sensitivity and comparison -----------------------------------------------------------------


def test_sensitivity_varies_one_quantity_at_a_time_across_models(built_graph: Session) -> None:
    plan = plan_of(built_graph, reference())
    members = members_of(plan)
    items = default_items(plan.spec, members)

    analysis = analyse(plan.spec, members, items, metric="profit_before_tax")

    assert analysis["base"] == "-6700000"
    targets = [item.target for item in items]
    assert targets[:3] == [
        "change:var_brent_crude",
        "change:var_usd_inr",
        "change:var_rbi_repo_rate",
    ]
    usd = next(item for item in analysis["items"] if item["target"] == "change:var_usd_inr")
    assert usd["models"] == ["airline_fuel_cost", "fx_exposure"]
    spreads = [D(entry["spread"]) for entry in analysis["ranking"]]
    assert spreads == sorted(spreads, reverse=True)
    repo = next(item for item in analysis["items"] if item["target"] == "change:var_rbi_repo_rate")
    # ±0.25 pp on 100,000,000 for 9 months: ±187,500 of interest.
    assert [point["delta"] for point in repo["points"]] == ["187500", "-187500"]


def test_sensitivity_skips_points_outside_a_range_and_enforces_limits(built_graph: Session) -> None:
    plan = plan_of(built_graph, brent_only())
    members = members_of(plan)
    fare = Item("model:airline_fuel_cost:fare_pass_through", mode="absolute", step=D(60))

    analysis = analyse(plan.spec, members, [fare], metric="operating_profit")

    skipped = [point["skipped"] for point in analysis["items"][0]["points"]]
    assert all(skipped) and "at most 100 %" in (skipped[1] or "")
    with pytest.raises(LabSensitivityError, match="not a quantity"):
        analyse(plan.spec, members, [Item("change:var_usd_inr")], metric="operating_profit")
    with pytest.raises(LabSensitivityError, match="no interest coverage"):
        analyse(plan.spec, members, [Item("change:var_brent_crude")], metric="interest_coverage")
    with pytest.raises(LabSensitivityError, match="At most 8"):
        analyse(
            plan.spec,
            members,
            [Item(f"change:var_{index}") for index in range(9)],
            metric="operating_profit",
        )


def test_comparison_differences_only_like_with_like(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    ids = [
        queue(built_graph, reference()),
        queue(built_graph, brent_only()),
        queue(built_graph, brent_only(timing={"horizon_months": 6})),
    ]
    for execution_id in ids:
        carry_out(session_factory, execution_id)
    with session_factory() as session:
        rows = [session.get_one(ScenarioExecution, item) for item in ids]
        runs = {
            str(row.id): [
                session.get_one(SimulationRun, link.simulation_run_id) for link in row.runs
            ]
            for row in rows
        }
        result = compare(rows, {str(row.id): "x" for row in rows}, runs, {}, str(ids[0]))

    assert result["comparable"] == {str(ids[0]): True, str(ids[1]): True, str(ids[2]): False}
    profit = next(row for row in result["lines"] if row["id"] == "operating_profit")["values"]
    assert profit[0]["difference"] is None  # the reference itself
    assert profit[1]["difference"]["absolute"] == str(D(-5_500_000) - D(-6_325_000))
    assert profit[2]["difference"] is None  # another horizon: shown, not differenced
    interest = next(row for row in result["lines"] if row["id"] == "interest_expense")["values"]
    assert [cell["modelled"] for cell in interest] == [True, False, False]
    assert ("airline_fuel_cost", "usd_change") in [
        (i["model_id"], i["input"]) for i in result["inputs"]
    ]
    assert "Nothing is ranked" in result["note"]


def test_a_change_to_a_stored_result_is_detected(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    from app.services.scenario_lab import verify_execution

    execution_id = queue(built_graph, reference())
    carry_out(session_factory, execution_id)
    with session_factory() as session:
        assert verify_execution(session, execution_id).reproduced
        session.get_one(ScenarioExecution, execution_id).result_hash = "0" * 64
        session.commit()
        verification = verify_execution(session, execution_id)

    assert not verification.reproduced and not verification.result_hash_matches
    assert all(run.result_hash_matches for run in verification.runs)


def test_the_scenario_row_mirrors_the_latest_version(built_graph: Session) -> None:
    created = scenario_service.create_scenario(
        built_graph, ScenarioInput.model_validate(brent_only())
    )

    scenario = built_graph.get_one(Scenario, created.id)
    assert (scenario.current_version, scenario.name) == (1, "Brent on Aerisca")
    assert spec_of(scenario.versions[0]).shocks[0].change_type is ChangeType.PERCENT_CHANGE


def test_stopping_the_runner_drops_queued_work_and_frees_its_places(
    built_graph: Session, session_factory: sessionmaker[Session]
) -> None:
    runner = ExecutionRunner(
        session_factory, freshness=scenario_service.freshness, mode="thread", max_concurrent=1
    )
    runner.start()
    ids = [queue(built_graph, brent_only()) for _ in range(4)]
    for execution_id in ids:
        runner.reserve()
        runner.submit(execution_id)
    runner.stop()
    runner.start()  # marks what the stop dropped as interrupted

    with session_factory() as session:
        final = [session.get_one(ScenarioExecution, item).status for item in ids]
    assert runner.pending == 0
    assert S.QUEUED not in final
    assert set(final) <= {S.COMPLETED, S.FAILED}
    runner.stop()
