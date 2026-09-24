"""Airline fuel-cost shock, version 1.1.0.

Version 1.0.0 with the timing of the changes: every scenario change takes effect in a
start month and lasts for a stated duration (to the end of the horizon unless one is set),
then the changed variables return to their baselines. The exchange rate therefore becomes
a monthly factor, propagated like every other change. Everything else — the equations, the
defaults, the ranges — is 1.0.0's. Version 1.0.0 stays registered unchanged, so its runs
remain verifiable.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.simulation.decimal_math import (
    MONTHS_PER_YEAR,
    ONE,
    ZERO,
    NumericalError,
    arithmetic,
    exp,
    percent_to_fraction,
)
from app.simulation.definitions import (
    EquationDefinition,
    InputDefinition,
    OutputDefinition,
    Term,
)
from app.simulation.models import airline_fuel_cost as v1
from app.simulation.models.common import (
    SHOCK_DURATION,
    SHOCK_START,
    START_WITHIN_HORIZON,
    TIMING_ASSUMPTION,
    TIMING_TEXT,
    timing_issues,
)
from app.simulation.runtime import ComputeContext, Issue, ModelResult, ResolvedValues
from app.simulation.units import PRICE_UNITS, VOLUME_UNITS, volume_conversion_factor

VERSION = "1.1.0"
JET_FUEL = v1.JET_FUEL
USD_INR = v1.USD_INR

D = Decimal


def _t(symbol: str, meaning: str, unit: str) -> Term:
    return Term(symbol, meaning, unit)


def _timed(item: InputDefinition) -> InputDefinition:
    return replace(
        item,
        description=item.description.replace("A permanent step change from month 1.", TIMING_TEXT),
    )


INPUTS: tuple[InputDefinition, ...] = (
    *(
        _timed(item)
        if item.id in ("crude_oil_change", "jet_fuel_margin_change", "usd_change")
        else item
        for item in v1.INPUTS
    ),
    SHOCK_START,
    SHOCK_DURATION,
)

_TIMING_TERMS = (
    _t("S", "the month the changes take effect", "months"),
    _t(
        "E",
        "the last month the changes last (the horizon's end unless a duration is set)",
        "months",
    ),
)

_REPLACED_EQUATIONS: dict[str, EquationDefinition] = {
    "E6": EquationDefinition(
        "E6",
        "Jet fuel log-change",
        "ℓ(m) = β · ln(1 + c) · 𝟙[S + L ≤ m ≤ E + L] + ln(1 + s) · 𝟙[S ≤ m ≤ E]",
        _t("ℓ(m)", "log-change of the jet fuel price in month m", "log change"),
        (
            _t("β", "crude-to-jet-fuel elasticity", "elasticity"),
            _t("c", "crude oil price change", "fraction"),
            _t("L", "crude-to-jet-fuel lag", "months"),
            _t("s", "additional jet fuel price change", "fraction"),
            *_TIMING_TERMS,
        ),
        "Propagated by the transmission engine along rule T1 (Brent crude → influences → "
        "jet fuel), plus the direct change to jet fuel itself. Each change lasts from S to E; "
        "the crude-driven part arrives L months later and ends L months later.",
        "monthly",
        assumptions=("A4", "A5"),
        limitations=("L5",),
    ),
    "E8": EquationDefinition(
        "E8",
        "Exchange rate relative to baseline",
        "q(m) = exp(ln(1 + x) · 𝟙[S ≤ m ≤ E])",
        _t("q(m)", "exchange rate in month m relative to the baseline", "ratio"),
        (_t("x", "exchange-rate change", "fraction"), *_TIMING_TERMS),
        "The reporting currency's price of a dollar in month m, relative to the baseline. "
        "Propagated by the transmission engine like every change, so it follows the "
        "scenario's timing.",
        "monthly",
        assumptions=("A4", "A8"),
    ),
    "E10": EquationDefinition(
        "E10",
        "Scenario monthly fuel cost",
        "b₁(m) = b₀ × q(m) × [h(m) + (1 − h(m)) × r(m)]",
        _t("b₁(m)", "fuel cost in month m under the scenario", "reporting currency per month"),
        (
            _t("b₀", "baseline monthly fuel cost", "reporting currency per month"),
            _t("q(m)", "exchange rate relative to baseline", "ratio"),
            _t("h(m)", "hedged share", "ratio"),
            _t("r(m)", "jet fuel price relative to baseline", "ratio"),
        ),
        "Hedged fuel keeps the baseline dollar price; unhedged fuel pays the new price. "
        "All fuel is paid in dollars converted at the month's exchange rate.",
        "monthly",
        assumptions=("A1", "A3", "A6", "A8"),
    ),
    "E17": EquationDefinition(
        "E17",
        "Run-rate annual effect",
        "ΔB* = B × [(1 + x) × exp(β·ln(1 + c) + ln(1 + s)) − 1]; ΔΠ* = (φ − 1) × ΔB*",
        _t(
            "ΔB*",
            "annual change in fuel cost while the changes last, once lags have passed and "
            "hedges expired",
            "reporting currency per year",
        ),
        (
            _t("B", "annual benchmark fuel cost", "reporting currency per year"),
            _t("x", "exchange-rate change", "fraction"),
            _t("φ", "fare pass-through", "fraction"),
        ),
        "The full annual effect while the changes last, after every lag has passed and every "
        "hedge has expired. For changes that last the whole horizon it is the steady state.",
        "steady_state",
        assumptions=("A4", "A5", "A7"),
    ),
    "E19": EquationDefinition(
        "E19",
        "Hedging effect",
        "G = Σₘ b₀ × (q(m) × r(m) − 1); hedging effect = ΣΔb − G",
        _t(
            "hedging effect",
            "how much the hedges change the fuel-cost change",
            "reporting currency",
        ),
        (
            _t("b₀", "baseline monthly fuel cost", "reporting currency per month"),
            _t("q(m)", "exchange rate relative to baseline", "ratio"),
            _t("r(m)", "jet fuel price relative to baseline", "ratio"),
            _t("ΣΔb", "change in fuel cost over the horizon", "reporting currency"),
        ),
        "G is the change the fuel bill would see with no hedges. The bridge "
        "−G − hedging effect + ΣΔr = ΣΔπ is exact.",
        "horizon",
        assumptions=("A6",),
    ),
}

EQUATIONS = tuple(_REPLACED_EQUATIONS.get(item.id, item) for item in v1.EQUATIONS)

_RELABELLED: dict[str, tuple[str, str]] = {
    "jet_fuel_price_change": (
        "Jet fuel price change (run rate)",
        "The jet fuel price change while the changes last, once the crude lag has passed.",
    ),
    "steady_state_fuel_cost_change": (
        "Run-rate annual fuel-cost change",
        "The yearly fuel-cost change while the changes last, once every lag has passed and "
        "the hedges have expired.",
    ),
    "steady_state_operating_profit_change": (
        "Run-rate annual operating-profit change",
        "The yearly operating-profit change at that run rate, after fare recovery.",
    ),
}

OUTPUTS = tuple(
    replace(item, label=_RELABELLED[item.id][0], description=_RELABELLED[item.id][1])
    if item.id in _RELABELLED
    else item
    for item in v1.OUTPUTS
)

MONTHLY_OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "fx_relative",
        "Exchange rate relative to baseline",
        "price_relative",
        "simulated",
        "q(m): 1.05 means the dollar costs 5 % more in the reporting currency.",
        "E8",
    ),
    *v1.MONTHLY_OUTPUTS,
)

ASSUMPTIONS = tuple(TIMING_ASSUMPTION if item.id == "A4" else item for item in v1.ASSUMPTIONS)

VALIDATION_RULES = (*v1.VALIDATION_RULES, START_WITHIN_HORIZON)

DEFINITION = replace(
    v1.DEFINITION,
    version=VERSION,
    description=v1.DEFINITION.description
    + " Version 1.1.0 adds the timing of the changes: a start month and a duration.",
    inputs=INPUTS,
    equations=EQUATIONS,
    outputs=OUTPUTS,
    monthly_outputs=MONTHLY_OUTPUTS,
    assumptions=ASSUMPTIONS,
    validation_rules=VALIDATION_RULES,
    shock_start_input="shock_start_month",
    shock_duration_input="shock_duration_months",
)


# --- Checks ------------------------------------------------------------------------------------


def check(values: ResolvedValues) -> list[Issue]:
    """1.0.0's cross-field rules, with lags measured from the start month, plus timing."""
    issues = [issue for issue in v1.check(values) if issue.code != "timing_within_horizon"]
    horizon = values.integer("horizon_months")
    start = values.integer("shock_start_month")
    hedge_ratio = values.number("hedge_ratio")
    hedge_months = values.integer("hedge_months")
    if hedge_ratio > ZERO and hedge_months == 0:
        issues.append(
            Issue(
                "timing_within_horizon",
                "A hedge ratio is set but the hedge cover is 0 months, so the hedges have no "
                "effect.",
                "warning",
                "hedge_months",
            )
        )
    if hedge_ratio == ZERO and hedge_months > 0:
        issues.append(
            Issue(
                "timing_within_horizon",
                "Hedge cover is set but the hedge ratio is 0 %, so nothing is hedged.",
                "warning",
                "hedge_ratio",
            )
        )
    if hedge_ratio > ZERO and 0 < hedge_months < start:
        issues.append(
            Issue(
                "timing_within_horizon",
                f"The hedges expire in month {hedge_months}, before the changes start in "
                f"month {start}, so they do not affect the results.",
                "warning",
                "hedge_months",
            )
        )
    if hedge_ratio > ZERO and hedge_months > horizon:
        issues.append(
            Issue(
                "timing_within_horizon",
                f"The hedges cover {hedge_months} months, beyond the {horizon}-month horizon; "
                "their expiry is not shown.",
                "warning",
                "hedge_months",
            )
        )
    if (
        values.number("fare_pass_through") > ZERO
        and start + values.integer("fare_pass_through_lag") > horizon
    ):
        issues.append(
            Issue(
                "timing_within_horizon",
                "Fares respond only after the horizon, so no fare recovery appears in the results.",
                "warning",
                "fare_pass_through_lag",
            )
        )
    if (
        values.number("crude_oil_change") != ZERO
        and start + values.integer("crude_pass_through_lag") > horizon
    ):
        issues.append(
            Issue(
                "timing_within_horizon",
                "The crude oil change reaches jet fuel only after the horizon, so it has no "
                "effect on the results.",
                "warning",
                "crude_pass_through_lag",
            )
        )
    issues.extend(timing_issues(values))
    return issues


# --- Compute -----------------------------------------------------------------------------------


def compute(context: ComputeContext) -> ModelResult:
    values = context.values
    record = context.recorder.record
    horizon = context.horizon
    currency = values.text("reporting_currency") or ""
    per_year = f"{currency} per year"
    per_month = f"{currency} per month"
    consumption_unit = VOLUME_UNITS[values.unit("annual_fuel_consumption")]
    price_unit = PRICE_UNITS[values.unit("jet_fuel_price")]
    result = ModelResult()

    with arithmetic():
        quantity = values.number("annual_fuel_consumption")
        price = values.number("jet_fuel_price")
        rate = values.number("fx_rate")
        revenue = values.number("annual_revenue")
        costs = values.number("annual_operating_costs")
        factor = volume_conversion_factor(consumption_unit, price_unit.volume)
        volume = record(
            "E1",
            "Annual consumption in the price's volume unit",
            ("V", quantity * factor, f"{price_unit.volume.label} per year"),
            [
                ("Q", quantity, f"{consumption_unit.label} per year"),
                (
                    "λ(u_Q)/λ(u_P)",
                    factor,
                    f"{price_unit.volume.label} per {consumption_unit.label}",
                ),
            ],
        )
        cost_usd = record(
            "E2",
            "Baseline benchmark fuel cost in US dollars",
            ("B_USD", volume * price, "USD per year"),
            [("V", volume, f"{price_unit.volume.label} per year"), ("P₀", price, price_unit.label)],
        )
        cost = record(
            "E3",
            "Baseline benchmark fuel cost in the reporting currency",
            ("B", cost_usd * rate, per_year),
            [("B_USD", cost_usd, "USD per year"), ("X₀", rate, f"{currency} per USD")],
        )
        share = record(
            "E4",
            "Fuel share of operating costs",
            ("f", cost / costs, "ratio"),
            [("B", cost, per_year), ("O", costs, per_year)],
        )
        base_month = record(
            "E5",
            "Monthly baseline fuel cost",
            ("b₀", cost / MONTHS_PER_YEAR, per_month),
            [("B", cost, per_year)],
        )

        crude = percent_to_fraction(values.number("crude_oil_change"))
        margin = percent_to_fraction(values.number("jet_fuel_margin_change"))
        dollar = percent_to_fraction(values.number("usd_change"))
        beta = values.number("crude_pass_through")
        crude_lag = values.integer("crude_pass_through_lag")
        hedge = percent_to_fraction(values.number("hedge_ratio"))
        hedge_months = values.integer("hedge_months")
        fare = percent_to_fraction(values.number("fare_pass_through"))
        fare_lag = values.integer("fare_pass_through_lag")
        start = values.integer("shock_start_month")
        duration = values.integer("shock_duration_months")
        end = start + duration - 1 if duration > 0 else horizon

        months: dict[str, list[Decimal]] = {
            name: []
            for name in (
                "fx_relative",
                "jet_fuel_relative",
                "hedged_share",
                "baseline_fuel_cost",
                "scenario_fuel_cost",
                "fuel_cost_change",
                "fare_recovery",
                "operating_profit_change",
            )
        }
        gross = ZERO
        for month in range(1, horizon + 1):
            log_change = record(
                "E6",
                "Jet fuel log-change",
                ("ℓ", context.propagation.at(JET_FUEL, month), "log change"),
                [
                    ("β", beta, "elasticity"),
                    ("c", crude, "fraction"),
                    ("L", Decimal(crude_lag), "months"),
                    ("s", margin, "fraction"),
                    ("S", Decimal(start), "months"),
                    ("E", Decimal(end), "months"),
                ],
                month=month,
            )
            relative = record(
                "E7",
                "Jet fuel price relative to baseline",
                ("r", exp(log_change), "ratio"),
                [("ℓ", log_change, "log change")],
                month=month,
            )
            fx_relative = record(
                "E8",
                "Exchange rate relative to baseline",
                ("q", exp(context.propagation.at(USD_INR, month)), "ratio"),
                [
                    ("x", dollar, "fraction"),
                    ("S", Decimal(start), "months"),
                    ("E", Decimal(end), "months"),
                ],
                month=month,
            )
            hedged = record(
                "E9",
                "Hedged share",
                ("h", hedge if month <= hedge_months else ZERO, "ratio"),
                [("h", hedge, "fraction"), ("M_h", Decimal(hedge_months), "months")],
                month=month,
            )
            scenario_cost = record(
                "E10",
                "Scenario monthly fuel cost",
                ("b₁", base_month * fx_relative * (hedged + (ONE - hedged) * relative), per_month),
                [
                    ("b₀", base_month, per_month),
                    ("q", fx_relative, "ratio"),
                    ("h", hedged, "ratio"),
                    ("r", relative, "ratio"),
                ],
                month=month,
            )
            change = record(
                "E11",
                "Change in fuel cost",
                ("Δb", scenario_cost - base_month, per_month),
                [("b₁", scenario_cost, per_month), ("b₀", base_month, per_month)],
                month=month,
            )
            months["fuel_cost_change"].append(change)
            earlier = months["fuel_cost_change"][month - 1 - fare_lag] if month > fare_lag else None
            recovery = record(
                "E12",
                "Fare recovery",
                ("Δr", fare * earlier if earlier is not None else ZERO, per_month),
                [
                    ("φ", fare, "fraction"),
                    ("Δb(m − L_f)", earlier if earlier is not None else ZERO, per_month),
                    ("L_f", Decimal(fare_lag), "months"),
                ],
                month=month,
            )
            profit = record(
                "E13",
                "Change in operating profit",
                ("Δπ", recovery - change, per_month),
                [("Δr", recovery, per_month), ("Δb", change, per_month)],
                month=month,
            )
            gross += base_month * (fx_relative * relative - ONE)
            months["fx_relative"].append(fx_relative)
            months["jet_fuel_relative"].append(relative)
            months["hedged_share"].append(hedged)
            months["baseline_fuel_cost"].append(base_month)
            months["scenario_fuel_cost"].append(scenario_cost)
            months["fare_recovery"].append(recovery)
            months["operating_profit_change"].append(profit)

        months_d = Decimal(horizon)
        total_change = sum(months["fuel_cost_change"], ZERO)
        total_recovery = sum(months["fare_recovery"], ZERO)
        total_profit = record(
            "E14",
            "Change in operating profit over the horizon",
            ("ΣΔπ", sum(months["operating_profit_change"], ZERO), currency),
            [
                ("ΣΔb", total_change, currency),
                ("ΣΔr", total_recovery, currency),
                ("H", months_d, "months"),
            ],
        )
        base_profit = record(
            "E15",
            "Baseline operating profit over the horizon",
            ("Π₀", (revenue - costs) * months_d / MONTHS_PER_YEAR, currency),
            [("R", revenue, per_year), ("O", costs, per_year), ("H", months_d, "months")],
        )
        scenario_profit = record(
            "E15",
            "Scenario operating profit over the horizon",
            ("Π₁", base_profit + total_profit, currency),
            [("Π₀", base_profit, currency), ("ΣΔπ", total_profit, currency)],
        )
        base_margin = record(
            "E16",
            "Baseline operating margin",
            ("μ₀", (revenue - costs) / revenue, "ratio"),
            [("R", revenue, per_year), ("O", costs, per_year)],
        )
        scenario_revenue = revenue * months_d / MONTHS_PER_YEAR + total_recovery
        scenario_costs = costs * months_d / MONTHS_PER_YEAR + total_change
        if scenario_revenue <= ZERO:
            raise NumericalError(
                "Revenue over the horizon would fall to zero or below; the operating margin "
                "is undefined. Check the fare pass-through and the scenario changes."
            )
        scenario_margin = record(
            "E16",
            "Scenario operating margin",
            ("μ₁", (scenario_revenue - scenario_costs) / scenario_revenue, "ratio"),
            [
                ("R·H/12 + ΣΔr", scenario_revenue, currency),
                ("O·H/12 + ΣΔb", scenario_costs, currency),
            ],
        )
        steady_relative = exp(context.propagation.final(JET_FUEL))
        steady_fx = exp(context.propagation.final(USD_INR))
        steady_change = record(
            "E17",
            "Run-rate annual fuel-cost change",
            ("ΔB*", cost * (steady_fx * steady_relative - ONE), per_year),
            [
                ("B", cost, per_year),
                ("1 + x", steady_fx, "ratio"),
                ("exp(ℓ*)", steady_relative, "ratio"),
            ],
        )
        steady_profit = record(
            "E17",
            "Run-rate annual operating-profit change",
            ("ΔΠ*", (fare - ONE) * steady_change, per_year),
            [("φ", fare, "fraction"), ("ΔB*", steady_change, per_year)],
        )
        offsetting = record(
            "E18",
            "Offsetting revenue change",
            ("g", total_change / (revenue * months_d / MONTHS_PER_YEAR), "ratio"),
            [("ΣΔb", total_change, currency), ("R", revenue, per_year), ("H", months_d, "months")],
        )
        hedging_effect = record(
            "E19",
            "Hedging effect",
            ("ΣΔb − G", total_change - gross, currency),
            [("ΣΔb", total_change, currency), ("G", gross, currency)],
        )
        jet_fuel_change = steady_relative - ONE
        margin_change = scenario_margin - base_margin

    result.scalars.update(
        annual_consumption_in_price_unit=volume,
        baseline_fuel_cost_usd=cost_usd,
        baseline_fuel_cost=cost,
        fuel_share=share,
        monthly_baseline_fuel_cost=base_month,
        baseline_operating_profit=base_profit,
        baseline_operating_margin=base_margin,
        jet_fuel_price_change=jet_fuel_change,
        fuel_cost_change=total_change,
        gross_fuel_cost_change=gross,
        hedging_effect=hedging_effect,
        fare_recovery=total_recovery,
        operating_profit_change=total_profit,
        scenario_operating_profit=scenario_profit,
        scenario_operating_margin=scenario_margin,
        operating_margin_change=margin_change,
        steady_state_fuel_cost_change=steady_change,
        steady_state_operating_profit_change=steady_profit,
        offsetting_revenue_change=offsetting,
    )
    result.monthly.update(months)
    result.units.update(
        annual_consumption_in_price_unit=f"{price_unit.volume.label} per year",
        baseline_fuel_cost_usd="USD per year",
        baseline_fuel_cost=per_year,
        fuel_share="ratio",
        monthly_baseline_fuel_cost=per_month,
        baseline_operating_profit=currency,
        baseline_operating_margin="ratio",
        jet_fuel_price_change="ratio",
        fuel_cost_change=currency,
        gross_fuel_cost_change=currency,
        hedging_effect=currency,
        fare_recovery=currency,
        operating_profit_change=currency,
        scenario_operating_profit=currency,
        scenario_operating_margin="ratio",
        operating_margin_change="ratio_points",
        steady_state_fuel_cost_change=per_year,
        steady_state_operating_profit_change=per_year,
        offsetting_revenue_change="ratio",
    )
    result.monthly_units.update(
        fx_relative="price_relative",
        jet_fuel_relative="price_relative",
        hedged_share="ratio",
        baseline_fuel_cost=per_month,
        scenario_fuel_cost=per_month,
        fuel_cost_change=per_month,
        fare_recovery=per_month,
        operating_profit_change=per_month,
    )
    return result
