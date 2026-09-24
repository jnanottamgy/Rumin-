"""The Scenario Lab's own equations: how the models' outputs combine into lines.

Every model of a scenario shares one reporting currency, one horizon and one set of
company figures, so their contributions add without conversion. Each model contributes
to a line only through the items its profile declares, and no two models may claim the
same item, so nothing is counted twice:

=====  =====================================================================================
AG1    Change in revenue: ΔR = Σ the models' revenue items (fare recovery, US-dollar revenue,
       price recovery)
AG2    Change in operating costs: ΔO = Σ the models' cost items (fuel, US-dollar costs,
       linked inputs)
AG3    Change in operating profit: ΔΠ = ΔR − ΔO, checked against Σ each model's own
       operating-profit change
AG4    Change in interest expense: ΔI = Σ the interest items
AG5    Change in profit before tax: ΔP = ΔΠ − ΔI (operating profit held at its baseline when
       no included model changes it)
AG6    Operating margin: μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΔR − O·H/12 − ΔO) / (R·H/12 + ΔR)
AG7    Interest coverage: κ₀ = (R − O) / I; κ₁ = ((R − O)·H/12 + ΔΠ) / (I·H/12 + ΔI)
=====  =====================================================================================

Baselines are the user's annual figures over the horizon (R·H/12, O·H/12, I·H/12), held
constant: they are inputs, not forecasts. Every scenario value is a model-derived
(simulated) value. A line no included model contributes to is not shown — it is not
modelled, which is not the same as unchanged. Cash flow is never shown: no model covers
working capital, tax or investment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from app.scenario_lab.profiles import LINE_LABELS, ScenarioProfile
from app.simulation.decimal_math import (
    HUNDRED,
    MONTHS_PER_YEAR,
    ZERO,
    NumericalError,
    arithmetic,
    text,
    to_output,
)
from app.simulation.engine import Execution
from app.simulation.runtime import ModelResult, ResolvedValues, StepRecorder

LineId = Literal[
    "revenue", "operating_costs", "operating_profit", "interest_expense", "profit_before_tax"
]

EQUATIONS: dict[str, dict[str, str]] = {
    "AG0": {
        "name": "Baselines over the horizon",
        "formula": "R·H/12; O·H/12; (R − O)·H/12; I·H/12; (R − O − I)·H/12",
        "explanation": "Your annual figures over the horizon, held constant. They are inputs, "
        "not forecasts.",
    },
    "AG1": {
        "name": "Change in revenue",
        "formula": "ΔR = Σ models' revenue items",
        "explanation": "The revenue items of every included model, added: each item is claimed "
        "by one model only.",
    },
    "AG2": {
        "name": "Change in operating costs",
        "formula": "ΔO = Σ models' cost items",
        "explanation": "The operating-cost items of every included model, added: each item is "
        "claimed by one model only.",
    },
    "AG3": {
        "name": "Change in operating profit",
        "formula": "ΔΠ = ΔR − ΔO",
        "explanation": "Checked against the sum of each model's own operating-profit change.",
    },
    "AG4": {
        "name": "Change in interest expense",
        "formula": "ΔI = Σ models' interest items",
        "explanation": "The interest items of the included interest model.",
    },
    "AG5": {
        "name": "Change in profit before tax",
        "formula": "ΔP = ΔΠ − ΔI",
        "explanation": "Operating profit is held at its baseline when no included model changes "
        "it.",
    },
    "AG6": {
        "name": "Operating margin",
        "formula": "μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΔR − O·H/12 − ΔO) / (R·H/12 + ΔR)",
        "explanation": "Operating profit as a share of revenue over the horizon, before and "
        "under the scenario.",
    },
    "AG7": {
        "name": "Interest coverage",
        "formula": "κ₀ = (R − O) / I; κ₁ = ((R − O)·H/12 + ΔΠ) / (I·H/12 + ΔI)",
        "explanation": "How many times operating profit covers interest expense over the "
        "horizon, before and under the scenario.",
    },
}

LINE_EQUATIONS: dict[str, str] = {
    "revenue": "AG1",
    "operating_costs": "AG2",
    "operating_profit": "AG3",
    "interest_expense": "AG4",
    "profit_before_tax": "AG5",
}
# How a rise in each line moves profit (accounting, not a judgement).
PROFIT_SIGN: dict[str, int] = {
    "revenue": 1,
    "operating_costs": -1,
    "operating_profit": 1,
    "interest_expense": -1,
    "profit_before_tax": 1,
}
METRIC_LABELS = {"operating_margin": "Operating margin", "interest_coverage": "Interest coverage"}
IDENTITY_TOLERANCE = Decimal("1e-9")


@dataclass(frozen=True)
class Outcome:
    """One model's results, as the aggregation reads them (rounded to the output quantum)."""

    model_id: str
    scalars: Mapping[str, Decimal]
    monthly: Mapping[str, Sequence[Decimal]]
    # output → [(input, value)], from Shapley attribution; empty when not computed.
    contributions: Mapping[str, Sequence[tuple[str, Decimal]]] = field(default_factory=dict)


def outcome_of(model_id: str, execution: Execution) -> Outcome:
    return Outcome(
        model_id=model_id,
        scalars={name: item["value"] for name, item in execution.outputs.items()},
        monthly={name: list(item["values"]) for name, item in execution.monthly.items()},
        contributions={
            output: [(entry["input"], entry["value"]) for entry in items]
            for output, items in execution.contributions.items()
        },
    )


def outcome_of_result(model_id: str, result: ModelResult) -> Outcome:
    """An unrounded evaluation (stress case, sensitivity point), rounded like a run."""
    return Outcome(
        model_id=model_id,
        scalars={name: to_output(value, name) for name, value in result.scalars.items()},
        monthly={
            name: [to_output(value, name) for value in values]
            for name, values in result.monthly.items()
        },
    )


@dataclass(frozen=True)
class Part:
    profile: ScenarioProfile
    values: ResolvedValues
    outcome: Outcome


@dataclass
class Line:
    id: str
    baseline: Decimal
    change: Decimal
    monthly: list[Decimal]
    items: list[dict[str, Any]]
    by_change: dict[str, Decimal]
    note: str | None = None

    @property
    def scenario(self) -> Decimal:
        return self.baseline + self.change


@dataclass
class Metric:
    id: str
    baseline: Decimal
    scenario: Decimal
    unit: str

    @property
    def change(self) -> Decimal:
        return self.scenario - self.baseline


@dataclass
class Aggregate:
    horizon: int
    lines: dict[str, Line]
    metrics: dict[str, Metric]


def _series(length: int) -> list[Decimal]:
    return [ZERO] * length


def _add(left: list[Decimal], right: Sequence[Decimal], sign: int = 1) -> list[Decimal]:
    return [a + sign * b for a, b in zip(left, right, strict=True)]


def _shared(parts: Sequence[Part], name: str) -> Decimal:
    values = {part.values.numbers[name] for part in parts if name in part.values.numbers}
    if len(values) != 1:
        raise NumericalError(
            f"The models do not share one value for {name}; the scenario is inconsistent.",
            code="aggregation_inconsistent",
        )
    return values.pop()


def _record(
    recorder: StepRecorder | None,
    equation: str,
    label: str,
    output: tuple[str, Decimal, str],
    inputs: Sequence[tuple[str, Decimal, str]],
) -> None:
    if recorder is not None:
        recorder.record(equation, label, output, inputs)


def aggregate(
    parts: Sequence[Part], *, horizon: int, recorder: StepRecorder | None = None
) -> Aggregate:
    """Combine the included models' outcomes into lines and metrics (AG0–AG7)."""
    if not parts:
        raise NumericalError("No model results to combine.", code="aggregation_inconsistent")
    with arithmetic():

        def over_horizon(annual: Decimal) -> Decimal:
            # Multiplied first, as the models do (exact whenever the figures allow it).
            return annual * Decimal(horizon) / MONTHS_PER_YEAR

        revenue = _shared(parts, "annual_revenue")
        costs = _shared(parts, "annual_operating_costs")
        interest_parts = [
            part for part in parts if "annual_interest_expense" in part.values.numbers
        ]
        interest = _shared(interest_parts, "annual_interest_expense") if interest_parts else None

        sums: dict[str, Line] = {}
        for part in parts:
            for contribution in part.profile.lines:
                line = sums.setdefault(
                    contribution.line,
                    Line(contribution.line, ZERO, ZERO, _series(horizon), [], {}),
                )
                value = part.outcome.scalars[contribution.output]
                monthly = part.outcome.monthly[contribution.monthly]
                line.change += value
                line.monthly = _add(line.monthly, monthly)
                credits: dict[str, Decimal] = {}
                for input_id, credit in part.outcome.contributions.get(contribution.output, ()):
                    binding = next(
                        (item for item in part.profile.shocks if item.input_id == input_id), None
                    )
                    if binding is not None:
                        credits[binding.variable_id] = (
                            credits.get(binding.variable_id, ZERO) + credit
                        )
                for variable_id, credit in credits.items():
                    line.by_change[variable_id] = line.by_change.get(variable_id, ZERO) + credit
                line.items.append(
                    {
                        "model_id": part.profile.model_id,
                        "item": contribution.item,
                        "label": contribution.label,
                        "output": contribution.output,
                        "monthly_output": contribution.monthly,
                        "value": value,
                        "by_change": credits,
                    }
                )

        lines: dict[str, Line] = {}
        operating = "revenue" in sums or "operating_costs" in sums
        if operating:
            for line_id, annual in (("revenue", revenue), ("operating_costs", costs)):
                line = sums.get(line_id) or Line(line_id, ZERO, ZERO, _series(horizon), [], {})
                line.baseline = over_horizon(annual)
                if line_id not in sums:
                    line.note = "No included model changes it."
                lines[line_id] = line
                _record(
                    recorder,
                    LINE_EQUATIONS[line_id],
                    f"Change in {LINE_LABELS[line_id].lower()}",
                    (f"Δ{line_id}", line.change, "currency"),
                    [
                        (f"{item['model_id']}.{item['output']}", item["value"], "currency")
                        for item in line.items
                    ],
                )
            profit = Line(
                "operating_profit",
                over_horizon(revenue - costs),
                lines["revenue"].change - lines["operating_costs"].change,
                _add(lines["revenue"].monthly, lines["operating_costs"].monthly, -1),
                [],
                {
                    variable: lines["revenue"].by_change.get(variable, ZERO)
                    - lines["operating_costs"].by_change.get(variable, ZERO)
                    for variable in {
                        **lines["revenue"].by_change,
                        **lines["operating_costs"].by_change,
                    }
                },
            )
            own = [
                part.outcome.scalars[part.profile.operating_profit_output]
                for part in parts
                if part.profile.operating_profit_output is not None
            ]
            if abs(sum(own, ZERO) - profit.change) > IDENTITY_TOLERANCE:
                raise NumericalError(
                    "The models' operating-profit changes do not add up to revenue less costs; "
                    "a model profile is inconsistent.",
                    code="aggregation_inconsistent",
                )
            lines["operating_profit"] = profit
            _record(
                recorder,
                "AG3",
                "Change in operating profit",
                ("ΔΠ", profit.change, "currency"),
                [
                    ("ΔR", lines["revenue"].change, "currency"),
                    ("ΔO", lines["operating_costs"].change, "currency"),
                ],
            )

        if "interest_expense" in sums and interest is not None:
            interest_line = sums["interest_expense"]
            interest_line.baseline = over_horizon(interest)
            lines["interest_expense"] = interest_line
            _record(
                recorder,
                "AG4",
                "Change in interest expense",
                ("ΔI", interest_line.change, "currency"),
                [
                    (f"{item['model_id']}.{item['output']}", item["value"], "currency")
                    for item in interest_line.items
                ],
            )
            profit_line = lines.get("operating_profit")
            operating_change = profit_line.change if profit_line else ZERO
            operating_monthly = profit_line.monthly if profit_line else _series(horizon)
            by_change = dict(profit_line.by_change) if profit_line else {}
            for variable, credit in interest_line.by_change.items():
                by_change[variable] = by_change.get(variable, ZERO) - credit
            pbt = Line(
                "profit_before_tax",
                over_horizon(revenue - costs - interest),
                operating_change - interest_line.change,
                _add(operating_monthly, interest_line.monthly, -1),
                [],
                by_change,
                None
                if profit_line
                else "Operating profit is held at its baseline: no included model changes it.",
            )
            lines["profit_before_tax"] = pbt
            _record(
                recorder,
                "AG5",
                "Change in profit before tax",
                ("ΔP", pbt.change, "currency"),
                [("ΔΠ", operating_change, "currency"), ("ΔI", interest_line.change, "currency")],
            )

        metrics: dict[str, Metric] = {}
        if operating and revenue > 0:
            base_revenue = over_horizon(revenue)
            scenario_revenue = base_revenue + lines["revenue"].change
            if scenario_revenue != 0:
                margin = Metric(
                    "operating_margin",
                    (revenue - costs) / revenue,
                    (scenario_revenue - over_horizon(costs) - lines["operating_costs"].change)
                    / scenario_revenue,
                    "ratio",
                )
                metrics["operating_margin"] = margin
                _record(
                    recorder,
                    "AG6",
                    "Operating margin under the scenario",
                    ("μ₁", margin.scenario, "ratio"),
                    [
                        ("R·H/12", base_revenue, "currency"),
                        ("ΔR", lines["revenue"].change, "currency"),
                        ("O·H/12", over_horizon(costs), "currency"),
                        ("ΔO", lines["operating_costs"].change, "currency"),
                    ],
                )
        if "interest_expense" in lines and interest is not None and interest > 0:
            base_interest = over_horizon(interest)
            scenario_interest = base_interest + lines["interest_expense"].change
            if scenario_interest > 0:
                operating_change = (
                    lines["operating_profit"].change if "operating_profit" in lines else ZERO
                )
                coverage = Metric(
                    "interest_coverage",
                    (revenue - costs) / interest,
                    (over_horizon(revenue - costs) + operating_change) / scenario_interest,
                    "times",
                )
                metrics["interest_coverage"] = coverage
                _record(
                    recorder,
                    "AG7",
                    "Interest coverage under the scenario",
                    ("κ₁", coverage.scenario, "times"),
                    [
                        ("(R − O)·H/12", over_horizon(revenue - costs), "currency"),
                        ("ΔΠ", operating_change, "currency"),
                        ("I·H/12", base_interest, "currency"),
                        ("ΔI", lines["interest_expense"].change, "currency"),
                    ],
                )
    return Aggregate(horizon=horizon, lines=lines, metrics=metrics)


# --- JSON --------------------------------------------------------------------------------------


def _percent(change: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline == 0:
        return None
    with arithmetic():
        return to_output(change / abs(baseline) * HUNDRED)


def _direction(value: Decimal) -> str:
    return "up" if value > 0 else "down" if value < 0 else "none"


def _effect(line_id: str, change: Decimal) -> str:
    signed = PROFIT_SIGN[line_id] * change
    return "raises_profit" if signed > 0 else "reduces_profit" if signed < 0 else "none"


def line_json(line: Line, *, currency: str) -> dict[str, Any]:
    with arithmetic():
        cumulative: list[Decimal] = []
        total = ZERO
        for value in line.monthly:
            total += value
            cumulative.append(to_output(total))
        baseline_monthly = (
            to_output(line.baseline / Decimal(len(line.monthly))) if line.monthly else ZERO
        )
        return {
            "id": line.id,
            "label": LINE_LABELS[line.id],
            "equation": LINE_EQUATIONS[line.id],
            "unit": "currency",
            "currency": currency,
            "baseline": text(to_output(line.baseline)),
            "change": text(to_output(line.change)),
            "scenario": text(to_output(line.scenario)),
            "percent_change": text(pct)
            if (pct := _percent(line.change, line.baseline)) is not None
            else None,
            "direction": _direction(line.change),
            "effect": _effect(line.id, line.change),
            "items": [
                {
                    **{
                        key: value
                        for key, value in item.items()
                        if key not in ("value", "by_change")
                    },
                    "value": text(to_output(item["value"])),
                    "by_change": {
                        variable: text(to_output(credit))
                        for variable, credit in sorted(item["by_change"].items())
                    },
                }
                for item in line.items
            ],
            "by_change": {
                variable: text(to_output(credit))
                for variable, credit in sorted(line.by_change.items())
            },
            "monthly": [text(to_output(value)) for value in line.monthly],
            "cumulative": [text(value) for value in cumulative],
            "baseline_monthly": text(baseline_monthly),
            "note": line.note,
            "knowledge": "simulated",
        }


def metric_json(metric: Metric) -> dict[str, Any]:
    with arithmetic():
        return {
            "id": metric.id,
            "label": METRIC_LABELS[metric.id],
            "equation": "AG6" if metric.id == "operating_margin" else "AG7",
            "unit": metric.unit,
            "baseline": text(to_output(metric.baseline)),
            "scenario": text(to_output(metric.scenario)),
            "change": text(to_output(metric.change)),
            "change_unit": "ratio_points" if metric.unit == "ratio" else metric.unit,
            "direction": _direction(metric.change),
            "knowledge": "simulated",
        }


def aggregate_json(result: Aggregate, *, currency: str) -> dict[str, Any]:
    order = list(LINE_EQUATIONS)
    return {
        "lines": [
            line_json(result.lines[line_id], currency=currency)
            for line_id in order
            if line_id in result.lines
        ],
        "metrics": [metric_json(metric) for metric in result.metrics.values()],
        "not_modelled": [
            {
                "id": line_id,
                "label": LINE_LABELS[line_id],
                "reason": "No included model covers it. Not modelled is not the same as unchanged.",
            }
            for line_id in order
            if line_id not in result.lines
        ]
        + [
            {
                "id": "cash_flow",
                "label": "Cash flow",
                "reason": "No model covers working capital, tax or investment, so a cash-flow "
                "figure would be invented.",
            }
        ],
    }


def totals(result: Aggregate) -> dict[str, Decimal]:
    """Each line's change and each metric's scenario value (for stress cases, sensitivity
    and comparisons)."""
    values = {line_id: to_output(line.change) for line_id, line in result.lines.items()}
    values.update(
        {metric_id: to_output(metric.scenario) for metric_id, metric in result.metrics.items()}
    )
    return values
