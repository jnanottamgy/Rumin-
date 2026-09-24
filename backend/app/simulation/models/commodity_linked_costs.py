"""Commodity-linked operating costs, version 1.0.0 — two models from one template.

* ``crude_linked_costs``: costs priced off Brent crude (feedstock crude, diesel and other
  fuels), for refiners and road freight;
* ``gas_linked_costs``: costs priced off natural gas (Henry Hub), used as fuel or
  feedstock, for chemicals.

What a change in the commodity's price does to those costs and to operating profit, month
by month, with hedging and a partial recovery through selling prices, holding everything
else constant. The company's input price follows the benchmark's percentage change with an
elasticity β after a lag — both explicit assumptions inside the model, because the
company's input price is not a node of the knowledge graph. The graph states which
companies and industries this matters for (Brent *affects the costs of* refining and land
transport; Henry Hub, of Lumeric Chemicals); the amounts come from the user. RUMIN holds no
company financial data and invents none.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    BridgeItem,
    EquationDefinition,
    InputCategory,
    InputDefinition,
    InputKind,
    ModelDefinition,
    ModelStatus,
    OutputDefinition,
    PathwayLink,
    SensitivitySpec,
    Statement,
    SupportingRelationship,
    Term,
    ValidationRuleDefinition,
)
from app.simulation.models.common import (
    ANNUAL_OPERATING_COSTS,
    ANNUAL_REVENUE,
    BRENT,
    ENTITY,
    HENRY_HUB,
    HORIZON,
    MAX_AMOUNT,
    MONTHLY_STEPS,
    NO_SHOCK,
    NOT_A_FORECAST,
    REPORTING_CURRENCY,
    SHOCK_DURATION,
    SHOCK_START,
    START_WITHIN_HORIZON,
    TIMING_ASSUMPTION,
    TIMING_TEXT,
    amount,
    lag_issue,
    months_assumption,
    no_shock_issue,
    percent_assumption,
    percent_shock,
    timing_issues,
)
from app.simulation.runtime import (
    CheckFunction,
    ComputeContext,
    ComputeFunction,
    Issue,
    ModelResult,
    ResolvedValues,
)

VERSION = "1.0.0"
D = Decimal


@dataclass(frozen=True)
class Commodity:
    model_id: str
    name: str
    commodity: str  # in prose: "crude oil", "natural gas"
    benchmark: str  # graph node
    benchmark_name: str
    shock_id: str
    shock_label: str
    cost_label: str
    cost_description: str
    domain: str
    supporting: tuple[SupportingRelationship, ...]
    reference: Statement


CRUDE = Commodity(
    model_id="crude_linked_costs",
    name="Crude-oil-linked costs",
    commodity="crude oil",
    benchmark=BRENT,
    benchmark_name="Brent crude",
    shock_id="crude_oil_change",
    shock_label="Crude oil price change",
    cost_label="Annual costs priced off crude oil",
    cost_description="Operating costs whose price follows crude oil — feedstock crude, "
    "diesel and other fuels — per year, in the reporting currency. Leave out jet fuel if the "
    "airline model is also used: it covers fuel itself.",
    domain="Commodity prices · refining · road freight",
    # Brent is stated to affect the costs of two industries in the graph: cited as the reason
    # the model exists, like the airline model's "jet fuel affects the costs of air transport".
    supporting=(
        SupportingRelationship(
            "S1",
            "affects_costs",
            BRENT,
            "{entity}",
            "Crude oil affects the chosen company's costs. Cited, not propagated.",
        ),
        SupportingRelationship(
            "S2",
            "affects_costs",
            BRENT,
            "industry:ind_petroleum_refining",
            "Crude oil is a cost of refining (feedstock). Cited, not propagated.",
        ),
        SupportingRelationship(
            "S3",
            "affects_costs",
            BRENT,
            "industry:ind_land_transport",
            "Crude oil is a cost of land transport (diesel). Cited, not propagated.",
        ),
    ),
    reference=Statement(
        "V1",
        "Variables: the Brent crude oil price (USD per barrel) is defined in RUMIN's reference "
        "data, with its publisher. RUMIN stores no values for it.",
    ),
)

GAS = Commodity(
    model_id="gas_linked_costs",
    name="Natural-gas-linked costs",
    commodity="natural gas",
    benchmark=HENRY_HUB,
    benchmark_name="Henry Hub natural gas",
    shock_id="gas_price_change",
    shock_label="Natural gas price change",
    cost_label="Annual costs priced off natural gas",
    cost_description="Operating costs whose price follows natural gas — gas used as fuel or "
    "as feedstock — per year, in the reporting currency.",
    domain="Energy prices · chemicals",
    supporting=(
        SupportingRelationship(
            "S1",
            "affects_costs",
            HENRY_HUB,
            "{entity}",
            "Natural gas affects the chosen company's costs. Cited, not propagated.",
        ),
    ),
    reference=Statement(
        "V1",
        "Variables: the Henry Hub natural gas price (USD per million Btu) is defined in "
        "RUMIN's reference data, with its publisher. RUMIN stores no values for it.",
    ),
)


def _t(symbol: str, meaning: str, unit: str) -> Term:
    return Term(symbol, meaning, unit)


CUR_YEAR = "reporting currency per year"
CUR_MONTH = "reporting currency per month"
CUR = "reporting currency"
CURRENCY = "currency"


def _definition(spec: Commodity) -> ModelDefinition:
    inputs: tuple[InputDefinition, ...] = (
        percent_shock(
            spec.shock_id,
            spec.shock_label,
            f"Change in the {spec.benchmark_name} price, in percent (30 means +30 %). "
            f"{TIMING_TEXT}",
            spec.benchmark,
            "10",
        ),
        ENTITY,
        REPORTING_CURRENCY,
        ANNUAL_REVENUE,
        ANNUAL_OPERATING_COSTS,
        InputDefinition(
            id="linked_annual_cost",
            label=spec.cost_label,
            category=InputCategory.COMPANY_INPUT,
            kind=InputKind.DECIMAL,
            description=spec.cost_description,
            unit="currency_per_year",
            minimum=ZERO,
            minimum_exclusive=True,
            maximum=MAX_AMOUNT,
            max_decimals=6,
            sensitivity=SensitivitySpec("relative", D(10)),
        ),
        InputDefinition(
            id="cost_pass_through",
            label=f"Elasticity to {spec.commodity}",
            category=InputCategory.ASSUMPTION,
            kind=InputKind.DECIMAL,
            description=f"How strongly the company's input price follows {spec.commodity}: "
            f"ln(input price) changes by β × ln(1 + {spec.commodity} change).",
            unit="elasticity",
            minimum=ZERO,
            maximum=D(3),
            max_decimals=4,
            required=False,
            default=ONE,
            rationale="1: the input's price moves in proportion to the benchmark. Enter less "
            "if part of the price does not follow it (transport, margins, fixed contracts).",
            sensitivity=SensitivitySpec("absolute", D("0.2")),
        ),
        months_assumption(
            "cost_pass_through_lag",
            "Price delay",
            12,
            "0: the input's price follows the benchmark in the same month. Enter the delay of "
            "your contracts or inventory.",
        ),
        percent_assumption(
            "hedge_ratio",
            "Hedge ratio",
            f"The share of the linked costs whose {spec.commodity} price is fixed by hedges, "
            "in percent.",
            "0: no hedging unless you enter it.",
        ),
        months_assumption(
            "hedge_months",
            "Hedge cover",
            36,
            "0: no hedges. Hedges cover the first months of the horizon and are not rolled over.",
        ),
        percent_assumption(
            "price_recovery",
            "Price recovery",
            "The share of the change in linked costs recovered through the company's own "
            "selling prices, in percent.",
            "0: no recovery unless you enter it.",
        ),
        months_assumption(
            "price_recovery_lag",
            "Price recovery delay",
            12,
            "0: selling prices adjust in the same month as the costs. Enter the delay you expect.",
        ),
        HORIZON,
        SHOCK_START,
        SHOCK_DURATION,
    )

    equations: tuple[EquationDefinition, ...] = (
        EquationDefinition(
            "E1",
            "Linked share of operating costs",
            "f = K / O",
            _t("f", "linked costs as a share of operating costs", "ratio"),
            (
                _t("K", spec.cost_label.lower(), CUR_YEAR),
                _t("O", "annual operating costs", CUR_YEAR),
            ),
            "A consistency check: the linked costs cannot exceed operating costs (f ≤ 1).",
            "annual",
        ),
        EquationDefinition(
            "E2",
            "Monthly baseline linked cost",
            "k₀ = K / 12",
            _t("k₀", "baseline linked cost in one month", CUR_MONTH),
            (_t("K", spec.cost_label.lower(), CUR_YEAR),),
            "A frequency conversion: an annual flow spread evenly over twelve months.",
            "annual",
            assumptions=("A2",),
            limitations=("L6",),
        ),
        EquationDefinition(
            "E3",
            f"{spec.benchmark_name} log-change in effect",
            "ℓ_B(m) = ln(1 + c) · 𝟙[S ≤ m ≤ E]",
            _t("ℓ_B(m)", "log-change of the benchmark in month m", "log change"),
            (
                _t("c", f"{spec.commodity} price change", "fraction"),
                _t("S", "the month the change takes effect", "months"),
                _t("E", "the last month it lasts", "months"),
            ),
            "Propagated by the transmission engine from the change to the benchmark, so it "
            "follows the scenario's timing.",
            "monthly",
            assumptions=("A4",),
        ),
        EquationDefinition(
            "E4",
            "Input price relative to baseline",
            "r(m) = exp(β · ℓ_B(m − L))",
            _t("r(m)", "the company's input price in month m relative to the baseline", "ratio"),
            (
                _t("β", f"elasticity to {spec.commodity}", "elasticity"),
                _t("ℓ_B", "benchmark log-change", "log change"),
                _t("L", "price delay", "months"),
            ),
            "The input's price follows the benchmark's percentage change, scaled by β, L months "
            "later (1 before then).",
            "monthly",
            assumptions=("A3",),
            limitations=("L3", "L4"),
        ),
        EquationDefinition(
            "E5",
            "Hedged share in month m",
            "h(m) = h if m ≤ M_h, otherwise 0",
            _t("h(m)", "share of month m's linked costs that is hedged", "ratio"),
            (_t("h", "hedge ratio", "fraction"), _t("M_h", "months of hedge cover", "months")),
            "Hedges cover the first M_h months and are not rolled over.",
            "monthly",
            assumptions=("A5",),
        ),
        EquationDefinition(
            "E6",
            "Scenario monthly linked cost",
            "k₁(m) = k₀ × [h(m) + (1 − h(m)) × r(m)]",
            _t("k₁(m)", "linked cost in month m under the scenario", CUR_MONTH),
            (
                _t("k₀", "baseline monthly linked cost", CUR_MONTH),
                _t("h(m)", "hedged share", "ratio"),
                _t("r(m)", "input price relative to baseline", "ratio"),
            ),
            "Hedged inputs keep the baseline price; the rest pay the new price.",
            "monthly",
            assumptions=("A1", "A3", "A5"),
        ),
        EquationDefinition(
            "E7",
            "Change in linked cost",
            "Δk(m) = k₁(m) − k₀",
            _t("Δk(m)", "change in linked cost in month m", CUR_MONTH),
            (
                _t("k₁(m)", "scenario monthly linked cost", CUR_MONTH),
                _t("k₀", "baseline monthly linked cost", CUR_MONTH),
            ),
            "Positive means the scenario costs more than the baseline.",
            "monthly",
        ),
        EquationDefinition(
            "E8",
            "Price recovery",
            "Δp(m) = φ × Δk(m − L_p) if m > L_p, otherwise 0",
            _t("Δp(m)", "change in revenue from selling prices in month m", CUR_MONTH),
            (
                _t("φ", "price recovery", "fraction"),
                _t("Δk", "change in linked cost", CUR_MONTH),
                _t("L_p", "price recovery delay", "months"),
            ),
            "Selling prices recover a share of the change in linked costs after a delay, for "
            "rises and falls alike.",
            "monthly",
            assumptions=("A6",),
            limitations=("L2",),
        ),
        EquationDefinition(
            "E9",
            "Change in operating profit",
            "Δπ(m) = Δp(m) − Δk(m)",
            _t("Δπ(m)", "change in operating profit in month m", CUR_MONTH),
            (
                _t("Δp(m)", "price recovery", CUR_MONTH),
                _t("Δk(m)", "change in linked cost", CUR_MONTH),
            ),
            "Everything else is held at its baseline.",
            "monthly",
            assumptions=("A1",),
            limitations=("L5",),
        ),
        EquationDefinition(
            "E10",
            "Totals over the horizon",
            "ΣΔk = Σₘ Δk(m); ΣΔp = Σₘ Δp(m); ΣΔπ = Σₘ Δπ(m), m = 1…H",
            _t("ΣΔπ", "change in operating profit over the horizon", CUR),
            (
                _t("Δk(m)", "change in linked cost", CUR_MONTH),
                _t("Δp(m)", "price recovery", CUR_MONTH),
                _t("H", "horizon", "months"),
            ),
            "Sums of the monthly changes.",
            "horizon",
        ),
        EquationDefinition(
            "E11",
            "Operating profit over the horizon",
            "Π₀ = (R − O) × H / 12; Π₁ = Π₀ + ΣΔπ",
            _t("Π₁", "operating profit over the horizon under the scenario", CUR),
            (
                _t("R", "annual revenue", CUR_YEAR),
                _t("O", "annual operating costs", CUR_YEAR),
                _t("H", "horizon", "months"),
                _t("ΣΔπ", "change in operating profit over the horizon", CUR),
            ),
            "The baseline is the entered annual figures, spread evenly over the horizon.",
            "horizon",
            assumptions=("A1", "A2"),
        ),
        EquationDefinition(
            "E12",
            "Operating margins",
            "μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔp − O·H/12 − ΣΔk) / (R·H/12 + ΣΔp)",
            _t("μ₁", "operating margin over the horizon under the scenario", "ratio"),
            (
                _t("R", "annual revenue", CUR_YEAR),
                _t("O", "annual operating costs", CUR_YEAR),
                _t("ΣΔp", "price recovery over the horizon", CUR),
                _t("ΣΔk", "change in linked cost over the horizon", CUR),
            ),
            "Operating profit divided by revenue, before and after the scenario.",
            "horizon",
        ),
        EquationDefinition(
            "E13",
            "Run-rate annual effect",
            "ΔK* = K × (exp(β · ln(1 + c)) − 1); ΔΠ* = (φ − 1) × ΔK*",
            _t(
                "ΔK*",
                "annual change in linked cost while the change lasts, once lags have passed "
                "and hedges expired",
                CUR_YEAR,
            ),
            (
                _t("K", spec.cost_label.lower(), CUR_YEAR),
                _t("β", f"elasticity to {spec.commodity}", "elasticity"),
                _t("c", f"{spec.commodity} price change", "fraction"),
                _t("φ", "price recovery", "fraction"),
            ),
            "The full annual effect while the change lasts, after every lag has passed and "
            "every hedge has expired.",
            "steady_state",
            assumptions=("A3", "A6"),
        ),
        EquationDefinition(
            "E14",
            "Hedging effect",
            "G = Σₘ k₀ × (r(m) − 1); hedging effect = ΣΔk − G",
            _t("hedging effect", "how much the hedges change the linked-cost change", CUR),
            (
                _t("k₀", "baseline monthly linked cost", CUR_MONTH),
                _t("r(m)", "input price relative to baseline", "ratio"),
                _t("ΣΔk", "change in linked cost over the horizon", CUR),
            ),
            "G is the change the linked costs would see with no hedges. The bridge "
            "−G − hedging effect + ΣΔp = ΣΔπ is exact.",
            "horizon",
            assumptions=("A5",),
        ),
    )

    outputs: tuple[OutputDefinition, ...] = (
        OutputDefinition(
            "linked_cost_share",
            "Linked share of operating costs",
            "ratio",
            "derived",
            "Linked costs ÷ operating costs.",
            "E1",
        ),
        OutputDefinition(
            "monthly_baseline_linked_cost",
            "Monthly baseline linked cost",
            "currency_per_month",
            "derived",
            "One twelfth of the annual linked costs.",
            "E2",
        ),
        OutputDefinition(
            "baseline_operating_profit",
            "Baseline operating profit (horizon)",
            CURRENCY,
            "derived",
            "Operating profit over the horizon with no change.",
            "E11",
        ),
        OutputDefinition(
            "baseline_operating_margin",
            "Baseline operating margin",
            "ratio",
            "derived",
            "Operating profit ÷ revenue with no change.",
            "E12",
        ),
        OutputDefinition(
            "input_price_change",
            "Input price change (run rate)",
            "ratio",
            "simulated",
            "The change in the company's input price while the change lasts, once the delay "
            "has passed.",
            "E13",
            attributable=True,
        ),
        OutputDefinition(
            "linked_cost_change",
            "Change in linked costs (horizon)",
            CURRENCY,
            "simulated",
            "Extra linked cost over the horizon, after hedges. Positive means costs rise.",
            "E10",
            attributable=True,
        ),
        OutputDefinition(
            "gross_linked_cost_change",
            "Change in linked costs without hedges (horizon)",
            CURRENCY,
            "simulated",
            "The linked-cost change over the horizon if nothing were hedged.",
            "E14",
            attributable=True,
        ),
        OutputDefinition(
            "hedging_effect",
            "Hedging effect (horizon)",
            CURRENCY,
            "simulated",
            "What the hedges changed: negative means they reduced the increase.",
            "E14",
            attributable=True,
        ),
        OutputDefinition(
            "price_recovery",
            "Price recovery (horizon)",
            CURRENCY,
            "simulated",
            "Extra revenue from selling prices over the horizon, as part of the cost change is "
            "passed on.",
            "E10",
            attributable=True,
        ),
        OutputDefinition(
            "operating_profit_change",
            "Change in operating profit (horizon)",
            CURRENCY,
            "simulated",
            "Price recovery minus the linked-cost change, over the horizon.",
            "E10",
            attributable=True,
        ),
        OutputDefinition(
            "scenario_operating_profit",
            "Scenario operating profit (horizon)",
            CURRENCY,
            "simulated",
            "Baseline operating profit plus the change, over the horizon.",
            "E11",
        ),
        OutputDefinition(
            "scenario_operating_margin",
            "Scenario operating margin",
            "ratio",
            "simulated",
            "Operating profit ÷ revenue over the horizon, under the scenario.",
            "E12",
        ),
        OutputDefinition(
            "operating_margin_change",
            "Change in operating margin",
            "ratio_points",
            "simulated",
            "Scenario margin minus baseline margin (0.01 is one percentage point).",
            "E12",
            attributable=True,
        ),
        OutputDefinition(
            "run_rate_cost_change",
            "Run-rate annual linked-cost change",
            "currency_per_year",
            "simulated",
            "The yearly change in linked costs while the change lasts, after delays and hedges.",
            "E13",
            attributable=True,
        ),
        OutputDefinition(
            "run_rate_operating_profit_change",
            "Run-rate annual operating-profit change",
            "currency_per_year",
            "simulated",
            "The yearly change in operating profit at that run rate, after price recovery.",
            "E13",
            attributable=True,
        ),
    )

    monthly_outputs: tuple[OutputDefinition, ...] = (
        OutputDefinition(
            "benchmark_relative",
            f"{spec.benchmark_name} relative to baseline",
            "price_relative",
            "simulated",
            "exp(ℓ_B(m)): the benchmark relative to its baseline.",
            "E3",
        ),
        OutputDefinition(
            "input_price_relative",
            "Input price relative to baseline",
            "price_relative",
            "simulated",
            "r(m): the company's input price relative to its baseline.",
            "E4",
        ),
        OutputDefinition(
            "hedged_share", "Hedged share", "ratio", "derived", "h(m): the share hedged.", "E5"
        ),
        OutputDefinition(
            "linked_cost_change",
            "Change in linked costs",
            "currency_per_month",
            "simulated",
            "Δk(m) = k₁(m) − k₀.",
            "E7",
        ),
        OutputDefinition(
            "price_recovery",
            "Price recovery",
            "currency_per_month",
            "simulated",
            "Δp(m): revenue recovered through selling prices.",
            "E8",
        ),
        OutputDefinition(
            "operating_profit_change",
            "Change in operating profit",
            "currency_per_month",
            "simulated",
            "Δπ(m) = Δp(m) − Δk(m).",
            "E9",
        ),
    )

    assumptions: tuple[Statement, ...] = (
        Statement(
            "A1",
            "Everything the model does not include stays at its baseline: volumes, other "
            "costs, demand, selling prices (apart from the stated recovery) and financing.",
        ),
        Statement(
            "A2",
            "Linked costs, revenue and operating costs accrue evenly through the year: each "
            "month carries one twelfth.",
        ),
        Statement(
            "A3",
            f"The company's input price, in the reporting currency, follows {spec.commodity} "
            "with a constant elasticity β after a delay L: ln(input price) changes by β × "
            f"ln(1 + {spec.commodity} change). Exchange-rate effects on the input are not "
            "part of this model.",
        ),
        TIMING_ASSUMPTION,
        Statement(
            "A5",
            "Hedged inputs keep their baseline price until the hedges expire; hedges are not "
            "rolled over.",
        ),
        Statement(
            "A6",
            "Selling prices recover a fixed share of the change in linked costs after a delay, "
            "for rises and falls alike, and demand does not respond.",
        ),
    )

    limitations: tuple[Statement, ...] = (
        NOT_A_FORECAST,
        Statement("L2", "Demand, volumes and market share do not respond to selling prices."),
        Statement(
            "L3",
            "For inputs paid in US dollars, a simultaneous exchange-rate change also moves "
            "their cost. Model that with the currency model; the combination leaves out the "
            "small cross effect (commodity change × currency change).",
        ),
        Statement(
            "L4",
            "The elasticity, delays, hedge terms and recovery are assumptions with neutral "
            "defaults. None is estimated in RUMIN.",
        ),
        Statement(
            "L5",
            "Operating profit only: no interest, tax, hedge accounting, working capital or "
            "cash-flow timing.",
        ),
        MONTHLY_STEPS,
    )

    rules: tuple[ValidationRuleDefinition, ...] = (
        ValidationRuleDefinition(
            "input_range",
            "Every number is within its range and has at most the allowed decimal places; "
            "required inputs are present.",
            "error",
        ),
        ValidationRuleDefinition(
            "percent_change_limits",
            "Scenario changes are greater than −100 % and at most +1,000 %, with at most 4 "
            "decimals — the limits Phase 1 publishes for scenario inputs.",
            "error",
        ),
        ValidationRuleDefinition(
            "linked_cost_within_costs",
            "The linked costs cannot exceed annual operating costs.",
            "error",
        ),
        START_WITHIN_HORIZON,
        ValidationRuleDefinition(
            "timing_within_horizon",
            "Delays, hedges and price responses that fall outside the horizon are flagged.",
            "warning",
        ),
        NO_SHOCK,
    )

    return ModelDefinition(
        id=spec.model_id,
        version=VERSION,
        name=spec.name,
        summary=f"What a change in the price of {spec.commodity} does to operating costs "
        f"priced off it and to operating profit, month by month, with hedging and price "
        "recovery.",
        description=f"A deterministic, monthly model of one company's costs priced off "
        f"{spec.commodity}. The input's price follows the benchmark with an elasticity after a "
        "delay; hedges fix part of the price for a number of months; selling prices recover a "
        "share of the change after a delay. The change takes effect in the start month and "
        "lasts for the stated duration. Everything else stays at its baseline.",
        domain=spec.domain,
        status=ModelStatus.PREVIEW,
        inputs=inputs,
        equations=equations,
        outputs=outputs,
        monthly_outputs=monthly_outputs,
        transmission_rules=(),
        supporting_relationships=spec.supporting,
        assumptions=assumptions,
        limitations=limitations,
        validation_rules=rules,
        references=(spec.reference,),
        pathway=(
            PathwayLink(f"input:{spec.shock_id}", spec.benchmark, "changes", ("E3",)),
            PathwayLink(
                spec.benchmark,
                "output:linked_cost_change",
                "prices the linked inputs (β, delay)",
                ("E4", "E6", "E7"),
            ),
            PathwayLink(
                "input:hedge_ratio",
                "output:linked_cost_change",
                "fixes part of the price",
                ("E5", "E6"),
            ),
            PathwayLink(
                "output:linked_cost_change", "output:price_recovery", "is partly passed on", ("E8",)
            ),
            PathwayLink(
                "output:linked_cost_change", "output:operating_profit_change", "reduces", ("E9",)
            ),
            PathwayLink(
                "output:price_recovery", "output:operating_profit_change", "adds back", ("E9",)
            ),
        ),
        bridge=(
            BridgeItem("gross_linked_cost_change", -1, "Linked-cost change without hedges"),
            BridgeItem("hedging_effect", -1, "Hedging"),
            BridgeItem("price_recovery", 1, "Price recovery"),
        ),
        bridge_total="operating_profit_change",
        headline_outputs=(
            "linked_cost_change",
            "operating_profit_change",
            "operating_margin_change",
            "run_rate_operating_profit_change",
        ),
        sensitivity_defaults=(
            spec.shock_id,
            "cost_pass_through",
            "hedge_ratio",
            "price_recovery",
            "linked_annual_cost",
        ),
        sensitivity_metric="operating_profit_change",
        shock_start_input="shock_start_month",
        shock_duration_input="shock_duration_months",
    )


def _check(spec: Commodity) -> CheckFunction:
    def check(values: ResolvedValues) -> list[Issue]:
        issues: list[Issue] = []
        currency = values.text("reporting_currency") or ""
        linked = values.number("linked_annual_cost")
        costs = values.number("annual_operating_costs")
        if linked > costs:
            issues.append(
                Issue(
                    "linked_cost_within_costs",
                    f"The costs priced off {spec.commodity} ({amount(linked, currency)} a year) "
                    f"exceed annual operating costs ({amount(costs, currency)}).",
                    field="linked_annual_cost",
                )
            )
        hedge_ratio = values.number("hedge_ratio")
        hedge_months = values.integer("hedge_months")
        if hedge_ratio > ZERO and hedge_months == 0:
            issues.append(
                Issue(
                    "timing_within_horizon",
                    "A hedge ratio is set but the hedge cover is 0 months, so the hedges have "
                    "no effect.",
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
        if values.number(spec.shock_id) != ZERO:
            issue = lag_issue(values, "cost_pass_through_lag", "The input's price follows")
            if issue:
                issues.append(issue)
        if values.number("price_recovery") > ZERO:
            issue = lag_issue(values, "price_recovery_lag", "Selling prices respond")
            if issue:
                issues.append(issue)
        issues.extend(timing_issues(values))
        issue = no_shock_issue(values, (spec.shock_id,))
        if issue:
            issues.append(issue)
        return issues

    return check


def _compute(spec: Commodity) -> ComputeFunction:
    def compute(context: ComputeContext) -> ModelResult:
        values = context.values
        record = context.recorder.record
        horizon = context.horizon
        currency = values.text("reporting_currency") or ""
        per_year = f"{currency} per year"
        per_month = f"{currency} per month"
        result = ModelResult()

        with arithmetic():
            revenue = values.number("annual_revenue")
            costs = values.number("annual_operating_costs")
            linked = values.number("linked_annual_cost")
            change = percent_to_fraction(values.number(spec.shock_id))
            beta = values.number("cost_pass_through")
            lag = values.integer("cost_pass_through_lag")
            hedge = percent_to_fraction(values.number("hedge_ratio"))
            hedge_months = values.integer("hedge_months")
            recovery_share = percent_to_fraction(values.number("price_recovery"))
            recovery_lag = values.integer("price_recovery_lag")
            start = values.integer("shock_start_month")
            duration = values.integer("shock_duration_months")
            end = start + duration - 1 if duration > 0 else horizon

            share = record(
                "E1",
                "Linked share of operating costs",
                ("f", linked / costs, "ratio"),
                [("K", linked, per_year), ("O", costs, per_year)],
            )
            base_month = record(
                "E2",
                "Monthly baseline linked cost",
                ("k₀", linked / MONTHS_PER_YEAR, per_month),
                [("K", linked, per_year)],
            )

            months: dict[str, list[Decimal]] = {
                name: []
                for name in (
                    "benchmark_relative",
                    "input_price_relative",
                    "hedged_share",
                    "linked_cost_change",
                    "price_recovery",
                    "operating_profit_change",
                )
            }
            gross = ZERO
            for month in range(1, horizon + 1):
                benchmark_log = record(
                    "E3",
                    f"{spec.benchmark_name} log-change",
                    ("ℓ_B", context.propagation.at(spec.benchmark, month), "log change"),
                    [
                        ("c", change, "fraction"),
                        ("S", Decimal(start), "months"),
                        ("E", Decimal(end), "months"),
                    ],
                    month=month,
                )
                delayed = (
                    context.propagation.at(spec.benchmark, month - lag) if month > lag else ZERO
                )
                relative = record(
                    "E4",
                    "Input price relative to baseline",
                    ("r", exp(beta * delayed), "ratio"),
                    [
                        ("β", beta, "elasticity"),
                        ("ℓ_B(m − L)", delayed, "log change"),
                        ("L", Decimal(lag), "months"),
                    ],
                    month=month,
                )
                hedged = record(
                    "E5",
                    "Hedged share",
                    ("h", hedge if month <= hedge_months else ZERO, "ratio"),
                    [("h", hedge, "fraction"), ("M_h", Decimal(hedge_months), "months")],
                    month=month,
                )
                scenario_cost = record(
                    "E6",
                    "Scenario monthly linked cost",
                    ("k₁", base_month * (hedged + (ONE - hedged) * relative), per_month),
                    [
                        ("k₀", base_month, per_month),
                        ("h", hedged, "ratio"),
                        ("r", relative, "ratio"),
                    ],
                    month=month,
                )
                delta = record(
                    "E7",
                    "Change in linked cost",
                    ("Δk", scenario_cost - base_month, per_month),
                    [("k₁", scenario_cost, per_month), ("k₀", base_month, per_month)],
                    month=month,
                )
                months["linked_cost_change"].append(delta)
                earlier = (
                    months["linked_cost_change"][month - 1 - recovery_lag]
                    if month > recovery_lag
                    else None
                )
                recovered = record(
                    "E8",
                    "Price recovery",
                    ("Δp", recovery_share * earlier if earlier is not None else ZERO, per_month),
                    [
                        ("φ", recovery_share, "fraction"),
                        ("Δk(m − L_p)", earlier if earlier is not None else ZERO, per_month),
                        ("L_p", Decimal(recovery_lag), "months"),
                    ],
                    month=month,
                )
                profit = record(
                    "E9",
                    "Change in operating profit",
                    ("Δπ", recovered - delta, per_month),
                    [("Δp", recovered, per_month), ("Δk", delta, per_month)],
                    month=month,
                )
                gross += base_month * (relative - ONE)
                months["benchmark_relative"].append(exp(benchmark_log))
                months["input_price_relative"].append(relative)
                months["hedged_share"].append(hedged)
                months["price_recovery"].append(recovered)
                months["operating_profit_change"].append(profit)

            months_d = Decimal(horizon)
            total_cost = sum(months["linked_cost_change"], ZERO)
            total_recovery = sum(months["price_recovery"], ZERO)
            total_profit = record(
                "E10",
                "Change in operating profit over the horizon",
                ("ΣΔπ", sum(months["operating_profit_change"], ZERO), currency),
                [
                    ("ΣΔk", total_cost, currency),
                    ("ΣΔp", total_recovery, currency),
                    ("H", months_d, "months"),
                ],
            )
            base_profit = record(
                "E11",
                "Baseline operating profit over the horizon",
                ("Π₀", (revenue - costs) * months_d / MONTHS_PER_YEAR, currency),
                [("R", revenue, per_year), ("O", costs, per_year), ("H", months_d, "months")],
            )
            scenario_profit = record(
                "E11",
                "Scenario operating profit over the horizon",
                ("Π₁", base_profit + total_profit, currency),
                [("Π₀", base_profit, currency), ("ΣΔπ", total_profit, currency)],
            )
            base_margin = record(
                "E12",
                "Baseline operating margin",
                ("μ₀", (revenue - costs) / revenue, "ratio"),
                [("R", revenue, per_year), ("O", costs, per_year)],
            )
            scenario_revenue = revenue * months_d / MONTHS_PER_YEAR + total_recovery
            scenario_costs = costs * months_d / MONTHS_PER_YEAR + total_cost
            if scenario_revenue <= ZERO:
                raise NumericalError(
                    "Revenue over the horizon would fall to zero or below; the operating "
                    "margin is undefined. Check the price recovery and the scenario changes."
                )
            scenario_margin = record(
                "E12",
                "Scenario operating margin",
                ("μ₁", (scenario_revenue - scenario_costs) / scenario_revenue, "ratio"),
                [
                    ("R·H/12 + ΣΔp", scenario_revenue, currency),
                    ("O·H/12 + ΣΔk", scenario_costs, currency),
                ],
            )
            run_rate_relative = exp(beta * context.propagation.final(spec.benchmark))
            run_rate_cost = record(
                "E13",
                "Run-rate annual linked-cost change",
                ("ΔK*", linked * (run_rate_relative - ONE), per_year),
                [("K", linked, per_year), ("exp(β·ℓ*)", run_rate_relative, "ratio")],
            )
            run_rate_profit = record(
                "E13",
                "Run-rate annual operating-profit change",
                ("ΔΠ*", (recovery_share - ONE) * run_rate_cost, per_year),
                [("φ", recovery_share, "fraction"), ("ΔK*", run_rate_cost, per_year)],
            )
            hedging_effect = record(
                "E14",
                "Hedging effect",
                ("ΣΔk − G", total_cost - gross, currency),
                [("ΣΔk", total_cost, currency), ("G", gross, currency)],
            )
            margin_change = scenario_margin - base_margin

        result.scalars.update(
            linked_cost_share=share,
            monthly_baseline_linked_cost=base_month,
            baseline_operating_profit=base_profit,
            baseline_operating_margin=base_margin,
            input_price_change=run_rate_relative - ONE,
            linked_cost_change=total_cost,
            gross_linked_cost_change=gross,
            hedging_effect=hedging_effect,
            price_recovery=total_recovery,
            operating_profit_change=total_profit,
            scenario_operating_profit=scenario_profit,
            scenario_operating_margin=scenario_margin,
            operating_margin_change=margin_change,
            run_rate_cost_change=run_rate_cost,
            run_rate_operating_profit_change=run_rate_profit,
        )
        result.monthly.update(months)
        result.units.update(
            linked_cost_share="ratio",
            monthly_baseline_linked_cost=per_month,
            baseline_operating_profit=currency,
            baseline_operating_margin="ratio",
            input_price_change="ratio",
            linked_cost_change=currency,
            gross_linked_cost_change=currency,
            hedging_effect=currency,
            price_recovery=currency,
            operating_profit_change=currency,
            scenario_operating_profit=currency,
            scenario_operating_margin="ratio",
            operating_margin_change="ratio_points",
            run_rate_cost_change=per_year,
            run_rate_operating_profit_change=per_year,
        )
        result.monthly_units.update(
            benchmark_relative="price_relative",
            input_price_relative="price_relative",
            hedged_share="ratio",
            linked_cost_change=per_month,
            price_recovery=per_month,
            operating_profit_change=per_month,
        )
        return result

    return compute


CRUDE_DEFINITION = _definition(CRUDE)
crude_check = _check(CRUDE)
crude_compute = _compute(CRUDE)

GAS_DEFINITION = _definition(GAS)
gas_check = _check(GAS)
gas_compute = _compute(GAS)
