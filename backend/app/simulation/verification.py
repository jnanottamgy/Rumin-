"""The model verification register: what has been checked about each registered model
version by running it through the engine — and what has not.

Every check runs the real engine path (``validate_inputs`` → the model's ``check`` →
``execute``) without a database. A check's graph snapshot states the model's transmission
relationships as present: the checks test the arithmetic and the model's stated properties;
whether a real knowledge graph holds a relationship is checked when a run is prepared.

Four kinds of check:

* **reference** — the model page's worked example (HYPOTHETICAL round figures, calculated by
  hand) reproduced exactly, to the output quantum;
* **property** — a stated property holds: no change, no effect; the accounting bridge
  closes; monthly values add up to the horizon totals; contributions add up to the total;
  an effect doubles when its cause doubles (where the equations are linear); an effect moves
  in one direction as its cause grows; the same quantity stated in other units gives the
  same result;
* **range** — each scenario input's and assumption's documented limits run, and a value just
  beyond is refused;
* **reproducibility** — the same inputs twice give the same inputs and result hashes.

Passing every check does **not** make a model validated: its parameters are not estimated
from data and its results are not back-tested (``not_verified``). RUMIN never says otherwise.

    python -m app.simulation.verification     # every registered version; exit 1 on a failure
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal

from app.simulation.decimal_math import OUTPUT_QUANTUM, NumericalError, text
from app.simulation.definitions import InputCategory, InputDefinition, InputKind, ModelDefinition
from app.simulation.engine import Execution, Preparation, channel_issues, execute
from app.simulation.graph_context import GraphContext, GraphEdgeRef
from app.simulation.registry import ENGINE_VERSION, REGISTRY, RegisteredModel
from app.simulation.runtime import Issue
from app.simulation.validation import InputValue, validate_inputs

REGISTER_VERSION = "1.0.0"
Kind = Literal["reference", "property", "range", "reproducibility"]
# Input id → {"value": …, "unit": …}; every figure HYPOTHETICAL.
Values = Mapping[str, Mapping[str, str]]
D = Decimal

NOT_VERIFIED_COMMON = (
    (
        "parameters",
        "Parameters — elasticities, delays, pass-through and hedge terms — are assumptions with "
        "stated defaults. None has been estimated from data.",
    ),
    (
        "back_testing",
        "No result has been compared with what happened (no back-testing): RUMIN stores no "
        "observed company or market outcomes to test against.",
    ),
    (
        "sample_data",
        "The companies in RUMIN's sample network are fictional, and these checks use "
        "hypothetical round figures: they show the arithmetic and the stated properties hold, "
        "not that the model describes any real company.",
    ),
)
NOT_VERIFIED_GRAPH = (
    "graph",
    "The knowledge-graph relationship the model propagates along is recorded in the sample "
    "network as a model assumption on illustrative data, not an empirical finding.",
)
NOTE = (
    "These checks run the model through the engine now, on hypothetical figures. Passing them "
    "shows the arithmetic reproduces hand calculations and the stated properties hold; it does "
    "not validate the model's assumptions or show that its results match reality."
)


@dataclass(frozen=True)
class CheckResult:
    id: str
    kind: Kind
    title: str
    description: str
    passed: bool
    detail: str
    expected: dict[str, str] = field(default_factory=dict)
    actual: dict[str, str] = field(default_factory=dict)


class Failed(Exception):
    def __init__(
        self,
        detail: str,
        *,
        expected: dict[str, str] | None = None,
        actual: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.expected = expected or {}
        self.actual = actual or {}


# --- Running a case -----------------------------------------------------------------------------


def graph_for(definition: ModelDefinition) -> GraphContext:
    """A snapshot in which every relationship the model may propagate along is present."""
    return GraphContext(
        build_id=None,
        build_finished_at=None,
        source_fingerprint=None,
        freshness="verification",
        transmission={
            rule.id: GraphEdgeRef(
                rule=rule.id,
                role="transmission",
                edge_key=f"verification:{rule.id}",
                edge_type=rule.edge_type,
                source=rule.source,
                target=rule.target,
                evidence_status="model_assumption",
                is_illustrative=True,
                description="Stated as present for the verification checks only.",
            )
            for rule in definition.transmission_rules
        },
        supporting={},
        entity=None,
        unused=(),
        unused_total=0,
        names={},
    )


def prepare(model: RegisteredModel, values: Values) -> Preparation:
    raw = {
        name: InputValue(
            value=item.get("value"), unit=item.get("unit"), source=None, series_id=None
        )
        for name, item in values.items()
    }
    resolved, resolved_values, issues = validate_inputs(
        model.definition, raw, lookup=lambda _series: None
    )
    context = graph_for(model.definition)
    if resolved_values is not None and not any(issue.severity == "error" for issue in issues):
        try:
            issues.extend(model.check(resolved_values))
        except NumericalError as error:
            issues.append(Issue(error.code, error.message))
        issues.extend(channel_issues(model, resolved_values, context))
    failed = any(issue.severity == "error" for issue in issues)
    return Preparation(model, resolved, None if failed else resolved_values, context, issues)


def run(model: RegisteredModel, values: Values) -> Execution:
    preparation = prepare(model, values)
    if not preparation.ok:
        raise Failed(
            "The inputs were refused: " + "; ".join(issue.message for issue in preparation.errors)
        )
    try:
        return execute(preparation)
    except NumericalError as error:
        raise Failed(f"The engine stopped: {error.message}") from error


def output(execution: Execution, name: str) -> Decimal:
    return D(execution.outputs[name]["value"])


def with_values(values: Values, **changes: str) -> dict[str, dict[str, str]]:
    merged = {name: dict(item) for name, item in values.items()}
    for name, value in changes.items():
        merged[name] = {**merged.get(name, {}), "value": value}
    return merged


def close(a: Decimal, b: Decimal, quanta: int = 1) -> bool:
    return abs(a - b) <= OUTPUT_QUANTUM * quanta


# --- What each model declares -------------------------------------------------------------------


@dataclass(frozen=True)
class Proportional:
    """Doubling ``input`` doubles ``output`` (the equations are linear in it)."""

    input: str
    output: str
    values: Values  # with ``input`` at a non-zero value


@dataclass(frozen=True)
class Direction:
    """As ``input`` climbs ``ladder``, ``output`` rises (or falls) at every step."""

    input: str
    output: str
    ladder: tuple[str, ...]
    rising: bool
    values: Values


@dataclass(frozen=True)
class ModelChecks:
    reference: Values
    reference_source: str
    expected: Mapping[str, str]
    monthly_totals: tuple[str, ...]
    proportional: Proportional
    direction: Direction
    attribution: Values | None = None  # two or more changes at once
    units: tuple[Values, ...] = ()  # one case stated in different units
    unit_outputs: tuple[str, ...] = ()


def company(revenue: str, costs: str) -> dict[str, dict[str, str]]:
    return {
        "reporting_currency": {"value": "INR"},
        "annual_revenue": {"value": revenue},
        "annual_operating_costs": {"value": costs},
        "horizon_months": {"value": "12"},
    }


AIRLINE = {
    **company("300000000", "250000000"),
    "crude_oil_change": {"value": "10"},
    "jet_fuel_price": {"value": "750", "unit": "usd_per_kilolitre"},
    "fx_rate": {"value": "80"},
    "annual_fuel_consumption": {"value": "1000", "unit": "kilolitre"},
    "hedge_ratio": {"value": "50"},
    "hedge_months": {"value": "3"},
    "fare_pass_through": {"value": "40"},
    "fare_pass_through_lag": {"value": "2"},
}
FX = {
    **company("500000000", "400000000"),
    "fx_change": {"value": "5"},
    "fx_rate": {"value": "80"},
    "annual_usd_revenue": {"value": "2000000"},
    "annual_usd_costs": {"value": "500000"},
    "revenue_hedge_ratio": {"value": "50"},
    "hedge_months": {"value": "6"},
}
INTEREST = {
    **company("500000000", "400000000"),
    "annual_interest_expense": {"value": "80000000"},
    "repo_linked_debt": {"value": "1000000000"},
    "us_rate_linked_debt": {"value": "0"},
    "repo_rate_change": {"value": "0.5"},
    "repo_repricing_lag": {"value": "3"},
}
CRUDE = {
    **company("500000000", "400000000"),
    "crude_oil_change": {"value": "20"},
    "linked_annual_cost": {"value": "120000000"},
    "hedge_ratio": {"value": "25"},
    "hedge_months": {"value": "6"},
    "price_recovery": {"value": "50"},
    "price_recovery_lag": {"value": "1"},
}
GAS = {
    **company("500000000", "400000000"),
    "gas_price_change": {"value": "30"},
    "linked_annual_cost": {"value": "60000000"},
}


def _unhedged(values: Values, *names: str) -> dict[str, dict[str, str]]:
    return with_values(values, **{name: "0" for name in names})


AIRLINE_CHECKS = ModelChecks(
    reference=AIRLINE,
    reference_source="docs/simulation/airline-fuel-cost.md, worked example",
    expected={
        "baseline_fuel_cost_usd": "750000",
        "baseline_fuel_cost": "60000000",
        "fuel_share": "0.24",
        "monthly_baseline_fuel_cost": "5000000",
        "fuel_cost_change": "5250000",
        "fare_recovery": "1700000",
        "operating_profit_change": "-3550000",
        "baseline_operating_profit": "50000000",
        "scenario_operating_profit": "46450000",
        "baseline_operating_margin": "0.1666666667",
        "scenario_operating_margin": "0.1539608883",
        "operating_margin_change": "-0.0127057784",
        "steady_state_fuel_cost_change": "6000000",
        "steady_state_operating_profit_change": "-3600000",
        "offsetting_revenue_change": "0.0175",
        "gross_fuel_cost_change": "6000000",
        "hedging_effect": "-750000",
    },
    monthly_totals=("fuel_cost_change", "fare_recovery", "operating_profit_change"),
    proportional=Proportional("crude_oil_change", "fuel_cost_change", AIRLINE),
    direction=Direction(
        "crude_oil_change", "fuel_cost_change", ("-20", "-10", "0", "10", "20", "40"), True, AIRLINE
    ),
    attribution=with_values(AIRLINE, usd_change="5"),
    # 1,000 US barrels = 42,000 US gallons exactly; 84 USD a barrel = 2 USD a gallon.
    units=(
        with_values(
            AIRLINE,
            annual_fuel_consumption="1000",
            jet_fuel_price="84",
        )
        | {
            "annual_fuel_consumption": {"value": "1000", "unit": "us_barrel"},
            "jet_fuel_price": {"value": "84", "unit": "usd_per_us_barrel"},
        },
        dict(AIRLINE)
        | {
            "annual_fuel_consumption": {"value": "42000", "unit": "us_gallon"},
            "jet_fuel_price": {"value": "2", "unit": "usd_per_us_gallon"},
        },
        dict(AIRLINE)
        | {
            "annual_fuel_consumption": {"value": "1000", "unit": "us_barrel"},
            "jet_fuel_price": {"value": "2", "unit": "usd_per_us_gallon"},
        },
    ),
    unit_outputs=(
        "baseline_fuel_cost",
        "fuel_cost_change",
        "fare_recovery",
        "operating_profit_change",
        "scenario_operating_margin",
    ),
)

CHECKS: dict[str, ModelChecks] = {
    "airline_fuel_cost": AIRLINE_CHECKS,
    "fx_exposure": ModelChecks(
        reference=FX,
        reference_source="docs/simulation/fx-exposure.md, worked example",
        expected={
            "baseline_usd_revenue": "160000000",
            "baseline_usd_costs": "40000000",
            "usd_revenue_share": "0.32",
            "usd_cost_share": "0.1",
            "revenue_change": "6000000",
            "cost_change": "2000000",
            "operating_profit_change": "4000000",
            "baseline_operating_profit": "100000000",
            "scenario_operating_profit": "104000000",
            "baseline_operating_margin": "0.2",
            "scenario_operating_margin": "0.2055335968",
            "operating_margin_change": "0.0055335968",
            "gross_revenue_change": "8000000",
            "revenue_hedging_effect": "-2000000",
            "gross_cost_change": "2000000",
            "cost_hedging_effect": "0",
            "net_usd_exposure": "1500000",
            "run_rate_operating_profit_change": "6000000",
        },
        monthly_totals=("revenue_change", "cost_change", "operating_profit_change"),
        proportional=Proportional(
            "fx_change", "operating_profit_change", _unhedged(FX, "revenue_hedge_ratio")
        ),
        direction=Direction(
            "fx_change",
            "operating_profit_change",
            ("-10", "-5", "0", "5", "10"),
            True,
            _unhedged(FX, "revenue_hedge_ratio"),
        ),
    ),
    "floating_rate_interest": ModelChecks(
        reference=INTEREST,
        reference_source="docs/simulation/floating-rate-interest.md, worked example",
        expected={
            "floating_rate_debt": "1000000000",
            "repo_interest_change": "3750000",
            "us_interest_change": "0",
            "interest_expense_change": "3750000",
            "profit_before_tax_change": "-3750000",
            "baseline_profit_before_tax": "20000000",
            "scenario_profit_before_tax": "16250000",
            "baseline_interest_coverage": "1.25",
            "scenario_interest_coverage": "1.1940298507",
            "run_rate_interest_change": "5000000",
        },
        monthly_totals=(
            "repo_interest_change",
            "us_interest_change",
            "interest_expense_change",
            "profit_before_tax_change",
        ),
        proportional=Proportional("repo_linked_debt", "interest_expense_change", INTEREST),
        direction=Direction(
            "repo_rate_change",
            "interest_expense_change",
            ("-1", "-0.5", "0", "0.5", "1", "2"),
            True,
            INTEREST,
        ),
        attribution=with_values(
            INTEREST,
            repo_rate_change="1",
            us_rate_change="-0.5",
            repo_linked_debt="600000000",
            us_rate_linked_debt="240000000",
        ),
    ),
    "crude_linked_costs": ModelChecks(
        reference=CRUDE,
        reference_source="docs/simulation/crude-linked-costs.md, worked example",
        expected={
            "linked_cost_share": "0.3",
            "monthly_baseline_linked_cost": "10000000",
            "input_price_change": "0.2",
            "linked_cost_change": "21000000",
            "price_recovery": "9500000",
            "operating_profit_change": "-11500000",
            "gross_linked_cost_change": "24000000",
            "hedging_effect": "-3000000",
            "baseline_operating_profit": "100000000",
            "scenario_operating_profit": "88500000",
            "baseline_operating_margin": "0.2",
            "scenario_operating_margin": "0.1736997056",
            "operating_margin_change": "-0.0263002944",
            "run_rate_cost_change": "24000000",
            "run_rate_operating_profit_change": "-12000000",
        },
        monthly_totals=("linked_cost_change", "price_recovery", "operating_profit_change"),
        proportional=Proportional("crude_oil_change", "linked_cost_change", CRUDE),
        direction=Direction(
            "crude_oil_change",
            "linked_cost_change",
            ("-20", "-10", "0", "10", "20", "40"),
            True,
            CRUDE,
        ),
    ),
    "gas_linked_costs": ModelChecks(
        reference=GAS,
        reference_source="docs/simulation/gas-linked-costs.md, worked example",
        expected={
            "linked_cost_share": "0.15",
            "monthly_baseline_linked_cost": "5000000",
            "input_price_change": "0.3",
            "linked_cost_change": "18000000",
            "price_recovery": "0",
            "operating_profit_change": "-18000000",
            "baseline_operating_margin": "0.2",
            "scenario_operating_margin": "0.164",
            "run_rate_cost_change": "18000000",
            "run_rate_operating_profit_change": "-18000000",
        },
        monthly_totals=("linked_cost_change", "price_recovery", "operating_profit_change"),
        proportional=Proportional("gas_price_change", "linked_cost_change", GAS),
        direction=Direction(
            "gas_price_change",
            "linked_cost_change",
            ("-20", "-10", "0", "10", "30", "60"),
            True,
            GAS,
        ),
    ),
}


# --- The checks ---------------------------------------------------------------------------------


def _reference(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    execution = run(model, spec.reference)
    actual = {name: text(output(execution, name)) for name in spec.expected}
    wrong = [name for name, value in spec.expected.items() if not close(D(actual[name]), D(value))]
    if wrong:
        raise Failed(
            f"{len(wrong)} of {len(spec.expected)} outputs differ from the hand calculation: "
            + ", ".join(wrong),
            expected={name: spec.expected[name] for name in wrong},
            actual={name: actual[name] for name in wrong},
        )
    return _passed(
        f"All {len(spec.expected)} outputs equal the hand calculation to the output quantum "
        f"({text(OUTPUT_QUANTUM)}).",
        expected=dict(spec.expected),
        actual=actual,
    )


def _scenario_inputs(definition: ModelDefinition) -> list[InputDefinition]:
    return [item for item in definition.inputs if item.category is InputCategory.SCENARIO_INPUT]


def _no_change(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    definition = model.definition
    quiet = with_values(spec.reference, **{item.id: "0" for item in _scenario_inputs(definition)})
    execution = run(model, quiet)
    moved = {
        item.id: text(output(execution, item.id))
        for item in definition.outputs
        if item.attributable and output(execution, item.id) != 0
    }
    if moved:
        raise Failed(
            "With every change at zero, these outputs still moved: " + ", ".join(moved),
            actual=moved,
        )
    count = sum(1 for item in definition.outputs if item.attributable)
    return _passed(f"All {count} outputs attributed to the changes are zero.")


def _bridge(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    definition = model.definition
    execution = run(model, spec.reference)
    total = sum((step.sign * output(execution, step.output) for step in definition.bridge), D(0))
    closing = output(execution, definition.bridge_total or "")
    if not close(total, closing, len(definition.bridge)):
        raise Failed(
            "The bridge's steps do not add up to its total.",
            expected={"total": text(closing)},
            actual={"sum of steps": text(total)},
        )
    steps = " + ".join(f"{'−' if step.sign < 0 else ''}{step.output}" for step in definition.bridge)
    return _passed(f"{steps} = {definition.bridge_total} ({text(closing)}).")


def _monthly(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    execution = run(model, spec.reference)
    horizon = execution.horizon
    wrong: dict[str, str] = {}
    expected: dict[str, str] = {}
    for name in spec.monthly_totals:
        total = sum((D(value) for value in execution.monthly[name]["values"]), D(0))
        if not close(total, output(execution, name), horizon):
            wrong[name] = text(total)
            expected[name] = text(output(execution, name))
    if wrong:
        raise Failed(
            "Monthly values do not add up to the horizon totals.", expected=expected, actual=wrong
        )
    return _passed(
        f"Over {horizon} months, the monthly values of {', '.join(spec.monthly_totals)} add up "
        "to their totals."
    )


def _attribution(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    assert spec.attribution is not None  # noqa: S101 - only registered when set
    execution = run(model, spec.attribution)
    wrong: dict[str, str] = {}
    for name, credits in execution.contributions.items():
        total = sum((D(item["value"]) for item in credits), D(0))
        if not close(total, output(execution, name), len(credits)):
            wrong[name] = text(total)
    if wrong or not execution.contributions:
        raise Failed("Contributions do not add up to the outputs.", actual=wrong)
    changes = len(next(iter(execution.contributions.values())))
    return _passed(
        f"With {changes} changes at once, each of the {len(execution.contributions)} attributed "
        "outputs equals the sum of its contributions (Shapley values)."
    )


def _proportional(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    rule = spec.proportional
    base = D(rule.values[rule.input]["value"])
    single = output(run(model, rule.values), rule.output)
    double = output(
        run(model, with_values(rule.values, **{rule.input: text(base * 2)})), rule.output
    )
    if single == 0 or not close(double, single * 2, 2):
        raise Failed(
            f"Doubling {rule.input} did not double {rule.output}.",
            expected={rule.output: text(single * 2)},
            actual={rule.output: text(double)},
        )
    return _passed(
        f"{rule.input} {text(base)} → {text(base * 2)}: {rule.output} {text(single)} → "
        f"{text(double)}."
    )


def _direction(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    rule = spec.direction
    values = [
        output(run(model, with_values(rule.values, **{rule.input: step})), rule.output)
        for step in rule.ladder
    ]
    ok = all((b > a) if rule.rising else (b < a) for a, b in pairwise(values))
    shown = {step: text(value) for step, value in zip(rule.ladder, values, strict=True)}
    if not ok:
        raise Failed(
            f"{rule.output} does not {'rise' if rule.rising else 'fall'} at every step of "
            f"{rule.input}.",
            actual=shown,
        )
    return _passed(
        f"{rule.output} {'rises' if rule.rising else 'falls'} at every step as {rule.input} goes "
        f"{' → '.join(rule.ladder)}.",
        actual=shown,
    )


def _units(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    results = [run(model, case) for case in spec.units]
    first = results[0]
    wrong = {
        name: " / ".join(text(output(result, name)) for result in results)
        for name in spec.unit_outputs
        if any(not close(output(result, name), output(first, name)) for result in results[1:])
    }
    if wrong:
        raise Failed("The same quantities in other units gave other results.", actual=wrong)
    return _passed(
        f"{len(spec.units)} statements of the same fuel volume and price (barrels, gallons, "
        f"mixed) give identical {', '.join(spec.unit_outputs)}."
    )


def _step(item: InputDefinition) -> Decimal:
    return D(1) if item.kind is InputKind.INTEGER else D(1).scaleb(-item.max_decimals)


def _at_limit(model: RegisteredModel, values: Values, item: InputDefinition) -> str | None:
    """None if the case runs; the model's stated reason if one of its rules stops it. Raises
    ``Failed`` if the input's own range refuses a documented limit or the engine crashes."""
    preparation = prepare(model, values)
    if any(issue.field == item.id and issue.code == "input_range" for issue in preparation.errors):
        raise Failed(f"{item.id} is refused at its own documented limit.")
    if preparation.errors:
        return preparation.errors[0].message
    try:
        execute(preparation)
    except NumericalError as error:
        return error.message
    return None


def _ranges(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    """At each documented limit the input is accepted and the model either runs or stops for
    a reason it states (a combination its rules exclude, such as interest falling below
    zero); just beyond the limit the input is refused."""
    definition = model.definition
    checked = [
        item
        for item in definition.inputs
        if item.category in (InputCategory.SCENARIO_INPUT, InputCategory.ASSUMPTION)
        and item.minimum is not None
        and item.maximum is not None
    ]
    problems: dict[str, str] = {}
    stopped: dict[str, str] = {}
    for item in checked:
        if item.minimum is None or item.maximum is None:  # pragma: no cover - filtered above
            continue
        step = _step(item)
        inside = (
            item.minimum + step if item.minimum_exclusive else item.minimum,
            item.maximum - step if item.maximum_exclusive else item.maximum,
        )
        beyond = (
            item.minimum if item.minimum_exclusive else item.minimum - step,
            item.maximum if item.maximum_exclusive else item.maximum + step,
        )
        for value in inside:
            label = f"{item.id} = {text(value)}"
            try:
                reason = _at_limit(
                    model, with_values(spec.reference, **{item.id: text(value)}), item
                )
            except Failed as failure:
                problems[label] = failure.detail
                continue
            if reason is not None:
                stopped[label] = reason
        for value in beyond:
            preparation = prepare(model, with_values(spec.reference, **{item.id: text(value)}))
            if not any(
                issue.code == "input_range" and issue.field == item.id
                for issue in preparation.errors
            ):
                problems[f"{item.id} = {text(value)}"] = "was not refused"
    if problems:
        raise Failed(
            f"{len(problems)} limit checks failed: " + "; ".join(problems), actual=problems
        )
    detail = (
        f"{len(checked)} inputs: every documented limit is accepted, and a value just beyond it "
        "is refused."
    )
    if stopped:
        detail += (
            " With the worked example's other figures, "
            + ("1 limit stops" if len(stopped) == 1 else f"{len(stopped)} limits stop")
            + " at a rule the model states rather than produce a result: "
            + "; ".join(f"{key} ({value})" for key, value in stopped.items())
        )
    else:
        detail += " Each limit runs with the worked example's other figures."
    return _passed(detail, actual=stopped)


def _reproducible(model: RegisteredModel, spec: ModelChecks) -> CheckResult:
    first, second = run(model, spec.reference), run(model, spec.reference)
    if (first.inputs_hash, first.result_hash) != (second.inputs_hash, second.result_hash):
        raise Failed(
            "Two runs of the same inputs gave different hashes.",
            expected={"result_hash": first.result_hash},
            actual={"result_hash": second.result_hash},
        )
    return _passed(f"Inputs hash and result hash identical ({first.result_hash[:12]}…).")


def _passed(
    detail: str, *, expected: dict[str, str] | None = None, actual: dict[str, str] | None = None
) -> CheckResult:
    return CheckResult("", "property", "", "", True, detail, expected or {}, actual or {})


@dataclass(frozen=True)
class Check:
    id: str
    kind: Kind
    title: str
    description: str
    run: Callable[[RegisteredModel, ModelChecks], CheckResult]
    applies: Callable[[ModelChecks], bool] = lambda _spec: True


REGISTERED_CHECKS: tuple[Check, ...] = (
    Check(
        "worked_example",
        "reference",
        "Worked example",
        "The model page's worked example, calculated by hand on hypothetical round figures, is "
        "reproduced exactly.",
        _reference,
    ),
    Check(
        "no_change_no_effect",
        "property",
        "No change, no effect",
        "With every scenario change at zero, every output attributed to the changes is zero.",
        _no_change,
    ),
    Check(
        "bridge_closes",
        "property",
        "The accounting bridge closes",
        "The bridge's steps add up exactly to the change it explains.",
        _bridge,
    ),
    Check(
        "monthly_totals",
        "property",
        "Months add up to the horizon",
        "Each monthly series adds up to the matching total over the horizon.",
        _monthly,
    ),
    Check(
        "contributions_add_up",
        "property",
        "Contributions add up",
        "With several changes at once, each output equals the sum of the changes' "
        "contributions (Shapley values), whatever their interaction.",
        _attribution,
        lambda spec: spec.attribution is not None,
    ),
    Check(
        "proportional",
        "property",
        "Linear where the equations are linear",
        "Doubling a quantity the equations are linear in doubles its effect.",
        _proportional,
    ),
    Check(
        "direction",
        "property",
        "The effect moves one way",
        "As a change grows, its effect moves in one direction at every step.",
        _direction,
    ),
    Check(
        "unit_invariance",
        "property",
        "Units do not change the result",
        "The same volume and price stated in other units (exact conversions) give the same result.",
        _units,
        lambda spec: bool(spec.units),
    ),
    Check(
        "range_limits",
        "range",
        "Documented limits",
        "Each scenario input's and assumption's documented limits run, and a value just beyond "
        "is refused.",
        _ranges,
    ),
    Check(
        "reproducible",
        "reproducibility",
        "Reproducible",
        "The same inputs, run twice, give the same inputs hash and result hash.",
        _reproducible,
    ),
)


@dataclass(frozen=True)
class Register:
    model_id: str
    version: str
    status: str
    definition_hash: str
    checks: list[CheckResult]
    not_verified: list[tuple[str, str]]
    duration_ms: int
    reference_source: str

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def failed(self) -> int:
        return len(self.checks) - self.passed


def verify(model: RegisteredModel, checks: Sequence[Check] = REGISTERED_CHECKS) -> Register:
    """Run every applicable check on one registered model version."""
    definition = model.definition
    spec = CHECKS.get(definition.id)
    if spec is None:
        raise KeyError(f"No verification checks are registered for {definition.id}.")
    started = time.monotonic()
    results: list[CheckResult] = []
    for check in checks:
        if not check.applies(spec):
            continue
        try:
            outcome = check.run(model, spec)
            results.append(
                CheckResult(
                    check.id,
                    check.kind,
                    check.title,
                    check.description,
                    True,
                    outcome.detail,
                    outcome.expected,
                    outcome.actual,
                )
            )
        except Failed as failure:
            results.append(
                CheckResult(
                    check.id,
                    check.kind,
                    check.title,
                    check.description,
                    False,
                    failure.detail,
                    failure.expected,
                    failure.actual,
                )
            )
        except Exception as error:
            results.append(
                CheckResult(
                    check.id,
                    check.kind,
                    check.title,
                    check.description,
                    False,
                    f"The check could not run: {type(error).__name__}: {error}",
                )
            )
    not_verified = list(NOT_VERIFIED_COMMON)
    if definition.transmission_rules:
        not_verified.insert(2, NOT_VERIFIED_GRAPH)
    return Register(
        model_id=definition.id,
        version=definition.version,
        status=definition.status.value,
        definition_hash=model.definition_hash,
        checks=results,
        not_verified=not_verified,
        duration_ms=round((time.monotonic() - started) * 1000),
        reference_source=spec.reference_source,
    )


def register_json(register: Register) -> dict[str, Any]:
    return {
        "model_id": register.model_id,
        "version": register.version,
        "status": register.status,
        "definition_hash": register.definition_hash,
        "engine_version": ENGINE_VERSION,
        "register_version": REGISTER_VERSION,
        "passed": register.passed,
        "failed": register.failed,
        "total": len(register.checks),
        "checks": [
            {
                "id": check.id,
                "kind": check.kind,
                "title": check.title,
                "description": check.description,
                "passed": check.passed,
                "detail": check.detail,
                "expected": check.expected,
                "actual": check.actual,
            }
            for check in register.checks
        ],
        "not_verified": [{"id": key, "text": value} for key, value in register.not_verified],
        "reference_source": register.reference_source,
        "duration_ms": register.duration_ms,
        "note": NOTE,
    }


def main() -> int:
    failures = 0
    for model_id in sorted({model.definition.id for model in REGISTRY.latest()}):
        for model in REGISTRY.versions(model_id):
            register = verify(model)
            failures += register.failed
            print(
                f"{model.definition.key:32} {register.passed}/{len(register.checks)} checks "
                f"passed ({register.duration_ms} ms)"
            )
            for check in register.checks:
                mark = "pass" if check.passed else "FAIL"
                print(f"  {mark}  {check.title}: {check.detail}")
    print("Not verified for any model: parameters estimated from data; back-testing.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
