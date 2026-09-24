"""Foreign-currency revenue and costs, version 1.0.0.

What a change in the exchange rate does to a company's revenue and costs invoiced in US
dollars, month by month, with hedges, holding everything else constant: the US-dollar
amounts, volumes and every other cost.

Revenue and costs in US dollars are converted at the month's exchange rate. The exchange
rate's change is propagated by the transmission engine, so it follows the scenario's
timing. Hedged shares keep the baseline rate while their hedges last. The graph states which
companies this matters for (USD/INR *affects the revenue* of Kovalent Digital and *the
costs* of Deltrin Refining and the two airlines); the size comes from the figures the user
enters. RUMIN holds no company financial data and invents none.
"""

from __future__ import annotations

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
    ENTITY,
    FX_RATE,
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
    USD_INR,
    amount,
    months_assumption,
    no_shock_issue,
    percent_assumption,
    percent_shock,
    timing_issues,
)
from app.simulation.runtime import ComputeContext, Issue, ModelResult, ResolvedValues

MODEL_ID = "fx_exposure"
VERSION = "1.0.0"

D = Decimal


def _usd_amount(input_id: str, label: str, description: str) -> InputDefinition:
    return InputDefinition(
        id=input_id,
        label=label,
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.DECIMAL,
        description=description,
        unit="usd_per_year",
        minimum=ZERO,
        maximum=MAX_AMOUNT,
        max_decimals=6,
        sensitivity=SensitivitySpec("relative", D(10)),
    )


INPUTS: tuple[InputDefinition, ...] = (
    percent_shock(
        "fx_change",
        "Exchange-rate change",
        "Change in the price of one US dollar in the reporting currency, in percent. "
        "Positive means the reporting currency weakens (more rupees per dollar): dollar "
        f"revenue is worth more and dollar costs cost more. {TIMING_TEXT}",
        USD_INR,
        "5",
    ),
    FX_RATE,
    ENTITY,
    REPORTING_CURRENCY,
    ANNUAL_REVENUE,
    ANNUAL_OPERATING_COSTS,
    _usd_amount(
        "annual_usd_revenue",
        "Annual revenue invoiced in US dollars",
        "Revenue billed and received in US dollars, per year, in dollars (0 if none). It is "
        "part of the annual revenue above.",
    ),
    _usd_amount(
        "annual_usd_costs",
        "Annual costs paid in US dollars",
        "Operating costs paid in US dollars, per year, in dollars (0 if none): leases, "
        "maintenance, imported inputs. Leave out costs another model in the same scenario "
        "already converts (for example jet fuel in the airline model).",
    ),
    percent_assumption(
        "revenue_hedge_ratio",
        "Revenue hedge ratio",
        "The share of US-dollar revenue sold forward at the baseline rate, in percent.",
        "0: no hedging unless you enter it.",
    ),
    percent_assumption(
        "cost_hedge_ratio",
        "Cost hedge ratio",
        "The share of US-dollar costs bought forward at the baseline rate, in percent.",
        "0: no hedging unless you enter it.",
    ),
    months_assumption(
        "hedge_months",
        "Hedge cover",
        36,
        "0: no hedges. Hedges cover the first months of the horizon and are not rolled over.",
    ),
    HORIZON,
    SHOCK_START,
    SHOCK_DURATION,
)


def _t(symbol: str, meaning: str, unit: str) -> Term:
    return Term(symbol, meaning, unit)


CUR_YEAR = "reporting currency per year"
CUR_MONTH = "reporting currency per month"
CUR = "reporting currency"

EQUATIONS: tuple[EquationDefinition, ...] = (
    EquationDefinition(
        "E1",
        "Baseline US-dollar revenue in the reporting currency",
        "R$ = U_R × X₀",
        _t("R$", "annual revenue invoiced in US dollars, converted", CUR_YEAR),
        (
            _t("U_R", "annual revenue invoiced in US dollars", "USD per year"),
            _t("X₀", "baseline exchange rate", "reporting currency per USD"),
        ),
        "An explicit currency conversion at the baseline exchange rate (an input, never assumed).",
        "annual",
        assumptions=("A2",),
    ),
    EquationDefinition(
        "E2",
        "Baseline US-dollar costs in the reporting currency",
        "C$ = U_C × X₀",
        _t("C$", "annual costs paid in US dollars, converted", CUR_YEAR),
        (
            _t("U_C", "annual costs paid in US dollars", "USD per year"),
            _t("X₀", "baseline exchange rate", "reporting currency per USD"),
        ),
        "An explicit currency conversion at the baseline exchange rate.",
        "annual",
        assumptions=("A2", "A6"),
    ),
    EquationDefinition(
        "E3",
        "Shares of revenue and costs in US dollars",
        "s_R = R$ / R; s_C = C$ / O",
        _t("s_R", "share of revenue invoiced in US dollars", "ratio"),
        (
            _t("R", "annual revenue", CUR_YEAR),
            _t("O", "annual operating costs", CUR_YEAR),
        ),
        "Consistency checks: the dollar part cannot exceed the whole (s ≤ 1).",
        "annual",
    ),
    EquationDefinition(
        "E4",
        "Monthly baselines",
        "r₀ = R$ / 12; c₀ = C$ / 12",
        _t("r₀", "baseline US-dollar revenue in one month, converted", CUR_MONTH),
        (
            _t("R$", "annual US-dollar revenue, converted", CUR_YEAR),
            _t("C$", "annual US-dollar costs, converted", CUR_YEAR),
        ),
        "A frequency conversion: annual flows spread evenly over twelve months.",
        "annual",
        assumptions=("A2",),
        limitations=("L6",),
    ),
    EquationDefinition(
        "E5",
        "Exchange rate relative to baseline",
        "q(m) = exp(ln(1 + x) · 𝟙[S ≤ m ≤ E])",
        _t("q(m)", "exchange rate in month m relative to the baseline", "ratio"),
        (
            _t("x", "exchange-rate change", "fraction"),
            _t("S", "the month the change takes effect", "months"),
            _t("E", "the last month it lasts", "months"),
        ),
        "Propagated by the transmission engine from the change to USD/INR, so it follows the "
        "scenario's timing.",
        "monthly",
        assumptions=("A4",),
    ),
    EquationDefinition(
        "E6",
        "Hedged shares in month m",
        "h_R(m) = h_R if m ≤ M_h, otherwise 0; h_C(m) likewise",
        _t("h_R(m)", "share of month m's US-dollar revenue that is hedged", "ratio"),
        (
            _t("h_R", "revenue hedge ratio", "fraction"),
            _t("h_C", "cost hedge ratio", "fraction"),
            _t("M_h", "months of hedge cover", "months"),
        ),
        "Hedges cover the first M_h months and are not rolled over.",
        "monthly",
        assumptions=("A5",),
    ),
    EquationDefinition(
        "E7",
        "Change in revenue",
        "Δr(m) = r₀ × (1 − h_R(m)) × (q(m) − 1)",
        _t("Δr(m)", "change in revenue in month m", CUR_MONTH),
        (
            _t("r₀", "baseline monthly US-dollar revenue, converted", CUR_MONTH),
            _t("h_R(m)", "hedged share of revenue", "ratio"),
            _t("q(m)", "exchange rate relative to baseline", "ratio"),
        ),
        "Unhedged dollar revenue is converted at the month's rate; hedged revenue keeps the "
        "baseline rate.",
        "monthly",
        assumptions=("A1", "A3", "A5"),
    ),
    EquationDefinition(
        "E8",
        "Change in costs",
        "Δc(m) = c₀ × (1 − h_C(m)) × (q(m) − 1)",
        _t("Δc(m)", "change in costs in month m", CUR_MONTH),
        (
            _t("c₀", "baseline monthly US-dollar costs, converted", CUR_MONTH),
            _t("h_C(m)", "hedged share of costs", "ratio"),
            _t("q(m)", "exchange rate relative to baseline", "ratio"),
        ),
        "Unhedged dollar costs are converted at the month's rate; hedged costs keep the "
        "baseline rate.",
        "monthly",
        assumptions=("A1", "A3", "A5", "A6"),
    ),
    EquationDefinition(
        "E9",
        "Change in operating profit",
        "Δπ(m) = Δr(m) − Δc(m)",
        _t("Δπ(m)", "change in operating profit in month m", CUR_MONTH),
        (
            _t("Δr(m)", "change in revenue", CUR_MONTH),
            _t("Δc(m)", "change in costs", CUR_MONTH),
        ),
        "Dollar revenue and dollar costs offset each other: the net exposure is what moves profit.",
        "monthly",
        limitations=("L5",),
    ),
    EquationDefinition(
        "E10",
        "Totals over the horizon",
        "ΣΔr = Σₘ Δr(m); ΣΔc = Σₘ Δc(m); ΣΔπ = Σₘ Δπ(m), m = 1…H",
        _t("ΣΔπ", "change in operating profit over the horizon", CUR),
        (
            _t("Δr(m)", "change in revenue", CUR_MONTH),
            _t("Δc(m)", "change in costs", CUR_MONTH),
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
        "μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔr − O·H/12 − ΣΔc) / (R·H/12 + ΣΔr)",
        _t("μ₁", "operating margin over the horizon under the scenario", "ratio"),
        (
            _t("R", "annual revenue", CUR_YEAR),
            _t("O", "annual operating costs", CUR_YEAR),
            _t("ΣΔr", "change in revenue over the horizon", CUR),
            _t("ΣΔc", "change in costs over the horizon", CUR),
        ),
        "Operating profit divided by revenue, before and after the scenario.",
        "horizon",
    ),
    EquationDefinition(
        "E13",
        "Hedging effects",
        "G_R = Σₘ r₀ (q(m) − 1); revenue hedging effect = ΣΔr − G_R; "
        "G_C = Σₘ c₀ (q(m) − 1); cost hedging effect = ΣΔc − G_C",
        _t("ΣΔr − G_R", "how much the revenue hedges change the revenue change", CUR),
        (
            _t("r₀", "baseline monthly US-dollar revenue, converted", CUR_MONTH),
            _t("c₀", "baseline monthly US-dollar costs, converted", CUR_MONTH),
            _t("q(m)", "exchange rate relative to baseline", "ratio"),
        ),
        "G_R and G_C are the changes with no hedges. The bridge "
        "G_R + (ΣΔr − G_R) − G_C − (ΣΔc − G_C) = ΣΔπ is exact.",
        "horizon",
        assumptions=("A5",),
    ),
    EquationDefinition(
        "E14",
        "Net exposure and run rate",
        "N = U_R − U_C; ΔΠ* = N × X₀ × x",
        _t("ΔΠ*", "annual change in operating profit while the change lasts, unhedged", CUR_YEAR),
        (
            _t("U_R", "annual revenue invoiced in US dollars", "USD per year"),
            _t("U_C", "annual costs paid in US dollars", "USD per year"),
            _t("X₀", "baseline exchange rate", "reporting currency per USD"),
            _t("x", "exchange-rate change", "fraction"),
        ),
        "The net dollar position: positive means the company earns more dollars than it "
        "spends and gains from a weaker reporting currency.",
        "steady_state",
        assumptions=("A3",),
    ),
)

CURRENCY = "currency"

OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "baseline_usd_revenue",
        "Baseline US-dollar revenue",
        "currency_per_year",
        "derived",
        "Annual revenue invoiced in US dollars, at the baseline rate.",
        "E1",
    ),
    OutputDefinition(
        "baseline_usd_costs",
        "Baseline US-dollar costs",
        "currency_per_year",
        "derived",
        "Annual costs paid in US dollars, at the baseline rate.",
        "E2",
    ),
    OutputDefinition(
        "usd_revenue_share",
        "Share of revenue in US dollars",
        "ratio",
        "derived",
        "US-dollar revenue ÷ annual revenue.",
        "E3",
    ),
    OutputDefinition(
        "usd_cost_share",
        "Share of costs in US dollars",
        "ratio",
        "derived",
        "US-dollar costs ÷ annual operating costs.",
        "E3",
    ),
    OutputDefinition(
        "net_usd_exposure",
        "Net US-dollar exposure",
        "usd_per_year",
        "derived",
        "US-dollar revenue minus US-dollar costs: what the exchange rate acts on.",
        "E14",
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
        "revenue_change",
        "Change in revenue (horizon)",
        CURRENCY,
        "simulated",
        "Extra revenue over the horizon from converting dollar revenue at the new rate, "
        "after hedges.",
        "E10",
        attributable=True,
    ),
    OutputDefinition(
        "cost_change",
        "Change in US-dollar costs (horizon)",
        CURRENCY,
        "simulated",
        "Extra cost over the horizon from converting dollar costs at the new rate, after "
        "hedges. Positive means costs rise.",
        "E10",
        attributable=True,
    ),
    OutputDefinition(
        "operating_profit_change",
        "Change in operating profit (horizon)",
        CURRENCY,
        "simulated",
        "The revenue change minus the cost change, over the horizon.",
        "E10",
        attributable=True,
    ),
    OutputDefinition(
        "gross_revenue_change",
        "Change in revenue without hedges (horizon)",
        CURRENCY,
        "simulated",
        "The revenue change over the horizon if nothing were hedged.",
        "E13",
        attributable=True,
    ),
    OutputDefinition(
        "revenue_hedging_effect",
        "Revenue hedging effect (horizon)",
        CURRENCY,
        "simulated",
        "What the revenue hedges changed: negative means they gave up part of a gain.",
        "E13",
        attributable=True,
    ),
    OutputDefinition(
        "gross_cost_change",
        "Change in US-dollar costs without hedges (horizon)",
        CURRENCY,
        "simulated",
        "The cost change over the horizon if nothing were hedged.",
        "E13",
        attributable=True,
    ),
    OutputDefinition(
        "cost_hedging_effect",
        "Cost hedging effect (horizon)",
        CURRENCY,
        "simulated",
        "What the cost hedges changed: negative means they reduced the increase.",
        "E13",
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
        "run_rate_operating_profit_change",
        "Run-rate annual operating-profit change",
        "currency_per_year",
        "simulated",
        "The yearly change in operating profit while the change lasts, with no hedges.",
        "E14",
        attributable=True,
    ),
)

MONTHLY_OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "fx_relative",
        "Exchange rate relative to baseline",
        "price_relative",
        "simulated",
        "q(m): 1.05 means the dollar costs 5 % more in the reporting currency.",
        "E5",
    ),
    OutputDefinition(
        "revenue_change",
        "Change in revenue",
        "currency_per_month",
        "simulated",
        "Δr(m): converted dollar revenue minus its baseline.",
        "E7",
    ),
    OutputDefinition(
        "cost_change",
        "Change in US-dollar costs",
        "currency_per_month",
        "simulated",
        "Δc(m): converted dollar costs minus their baseline.",
        "E8",
    ),
    OutputDefinition(
        "operating_profit_change",
        "Change in operating profit",
        "currency_per_month",
        "simulated",
        "Δπ(m) = Δr(m) − Δc(m).",
        "E9",
    ),
)

ASSUMPTIONS: tuple[Statement, ...] = (
    Statement(
        "A1",
        "Everything the model does not include stays at its baseline: the US-dollar amounts, "
        "volumes, prices in every currency, other costs and financing.",
    ),
    Statement(
        "A2",
        "US-dollar revenue and costs accrue evenly through the year: each month carries one "
        "twelfth.",
    ),
    Statement(
        "A3",
        "Dollar amounts are converted at the month's exchange rate. Dollar prices, volumes "
        "and demand do not respond to the exchange rate.",
    ),
    TIMING_ASSUMPTION,
    Statement(
        "A5",
        "Hedges fix the baseline exchange rate for the hedged share during the first months "
        "of cover, then expire; they are not rolled over. Revenue and cost hedges are "
        "separate.",
    ),
    Statement(
        "A6",
        "Only amounts invoiced or paid in US dollars are exposed. Costs another model in the "
        "same scenario already converts must be left out of the US-dollar costs.",
    ),
)

LIMITATIONS: tuple[Statement, ...] = (
    NOT_A_FORECAST,
    Statement(
        "L2",
        "Transaction exposure only: revaluing dollar debt or other balance-sheet items "
        "(translation exposure) and the effect on competitiveness or demand (economic "
        "exposure) are not modelled.",
    ),
    Statement("L3", "One foreign currency, the US dollar."),
    Statement(
        "L4",
        "The hedge ratios and cover are the user's figures or neutral defaults. None is "
        "estimated in RUMIN.",
    ),
    Statement(
        "L5",
        "Operating profit only: no interest, tax, hedge accounting, working capital or "
        "cash-flow timing.",
    ),
    MONTHLY_STEPS,
)

VALIDATION_RULES: tuple[ValidationRuleDefinition, ...] = (
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
        "not_usd_reporter",
        "A company that reports in US dollars has no US-dollar exposure in this model.",
        "error",
    ),
    ValidationRuleDefinition(
        "observation_matches",
        "A stored observation may supply the exchange rate only when its currency pair and "
        "unit match the reporting currency.",
        "error",
    ),
    ValidationRuleDefinition(
        "usd_revenue_within_revenue",
        "US-dollar revenue, converted, cannot exceed annual revenue.",
        "error",
    ),
    ValidationRuleDefinition(
        "usd_costs_within_costs",
        "US-dollar costs, converted, cannot exceed annual operating costs.",
        "error",
    ),
    ValidationRuleDefinition(
        "has_exposure",
        "At least one of US-dollar revenue and US-dollar costs must be above zero.",
        "error",
    ),
    START_WITHIN_HORIZON,
    ValidationRuleDefinition(
        "timing_within_horizon",
        "Hedges that have no effect or outlast the horizon are flagged.",
        "warning",
    ),
    NO_SHOCK,
)

SUPPORTING: tuple[SupportingRelationship, ...] = (
    SupportingRelationship(
        "S1",
        "affects_revenue",
        USD_INR,
        "{entity}",
        "The exchange rate affects the chosen company's revenue (E1, E7). Cited, not propagated.",
    ),
    SupportingRelationship(
        "S2",
        "affects_costs",
        USD_INR,
        "{entity}",
        "The exchange rate affects the chosen company's costs (E2, E8). Cited, not propagated.",
    ),
)

REFERENCES: tuple[Statement, ...] = (
    Statement(
        "V1",
        "Variables: USD/INR (INR per USD) is defined in RUMIN's reference data, with its "
        "publisher. RUMIN stores no values for it beyond the World Bank series below.",
    ),
    Statement(
        "D1",
        "Stored data: the exchange rate may come from the World Bank's World Development "
        "Indicators (PA.NUS.FCRF, CC BY 4.0) when a retrieval has stored it.",
    ),
)

DEFINITION = ModelDefinition(
    id=MODEL_ID,
    version=VERSION,
    name="Foreign-currency revenue and costs",
    summary="What a change in the exchange rate does to revenue and costs invoiced in US "
    "dollars, month by month, with hedges.",
    description="A deterministic, monthly model of one company's US-dollar revenue and costs. "
    "Each month's dollar amounts are converted at that month's exchange rate; hedged shares "
    "keep the baseline rate while the hedges last. The change to the exchange rate takes "
    "effect in the start month and lasts for the stated duration. Everything else stays at "
    "its baseline.",
    domain="Exchange rates · treasury",
    status=ModelStatus.PREVIEW,
    inputs=INPUTS,
    equations=EQUATIONS,
    outputs=OUTPUTS,
    monthly_outputs=MONTHLY_OUTPUTS,
    transmission_rules=(),
    supporting_relationships=SUPPORTING,
    assumptions=ASSUMPTIONS,
    limitations=LIMITATIONS,
    validation_rules=VALIDATION_RULES,
    references=REFERENCES,
    pathway=(
        PathwayLink("input:fx_change", USD_INR, "changes", ("E5",)),
        PathwayLink(USD_INR, "output:revenue_change", "converts dollar revenue", ("E1", "E7")),
        PathwayLink(USD_INR, "output:cost_change", "converts dollar costs", ("E2", "E8")),
        PathwayLink(
            "input:revenue_hedge_ratio", "output:revenue_change", "fixes part of the rate", ("E6",)
        ),
        PathwayLink(
            "input:cost_hedge_ratio", "output:cost_change", "fixes part of the rate", ("E6",)
        ),
        PathwayLink("output:revenue_change", "output:operating_profit_change", "adds", ("E9",)),
        PathwayLink("output:cost_change", "output:operating_profit_change", "reduces", ("E9",)),
    ),
    bridge=(
        BridgeItem("gross_revenue_change", 1, "Revenue change without hedges"),
        BridgeItem("revenue_hedging_effect", 1, "Revenue hedges"),
        BridgeItem("gross_cost_change", -1, "Cost change without hedges"),
        BridgeItem("cost_hedging_effect", -1, "Cost hedges"),
    ),
    bridge_total="operating_profit_change",
    headline_outputs=(
        "revenue_change",
        "cost_change",
        "operating_profit_change",
        "operating_margin_change",
    ),
    sensitivity_defaults=(
        "fx_change",
        "fx_rate",
        "annual_usd_revenue",
        "annual_usd_costs",
        "revenue_hedge_ratio",
        "cost_hedge_ratio",
    ),
    sensitivity_metric="operating_profit_change",
    shock_start_input="shock_start_month",
    shock_duration_input="shock_duration_months",
)


# --- Checks ------------------------------------------------------------------------------------


def check(values: ResolvedValues) -> list[Issue]:
    issues: list[Issue] = []
    currency = values.text("reporting_currency") or ""
    rate = values.number("fx_rate")
    if currency == "USD":
        issues.append(
            Issue(
                "not_usd_reporter",
                "The reporting currency is USD, so dollar amounts carry no exchange-rate "
                "exposure in this model.",
                field="reporting_currency",
            )
        )
    usd_revenue = values.number("annual_usd_revenue")
    usd_costs = values.number("annual_usd_costs")
    if usd_revenue == ZERO and usd_costs == ZERO:
        issues.append(
            Issue(
                "has_exposure",
                "Both US-dollar revenue and US-dollar costs are zero, so nothing is exposed "
                "to the exchange rate.",
                field="annual_usd_revenue",
            )
        )
    with arithmetic():
        converted_revenue = usd_revenue * rate
        converted_costs = usd_costs * rate
    revenue = values.number("annual_revenue")
    costs = values.number("annual_operating_costs")
    if converted_revenue > revenue:
        issues.append(
            Issue(
                "usd_revenue_within_revenue",
                f"US-dollar revenue at the baseline rate ({amount(converted_revenue, currency)} "
                f"a year) exceeds annual revenue ({amount(revenue, currency)}). Check the "
                "amounts and the exchange rate.",
                field="annual_usd_revenue",
            )
        )
    if converted_costs > costs:
        issues.append(
            Issue(
                "usd_costs_within_costs",
                f"US-dollar costs at the baseline rate ({amount(converted_costs, currency)} a "
                f"year) exceed annual operating costs ({amount(costs, currency)}). Check the "
                "amounts and the exchange rate.",
                field="annual_usd_costs",
            )
        )
    hedge_months = values.integer("hedge_months")
    hedged = values.number("revenue_hedge_ratio") > ZERO or values.number("cost_hedge_ratio") > ZERO
    if hedged and hedge_months == 0:
        issues.append(
            Issue(
                "timing_within_horizon",
                "A hedge ratio is set but the hedge cover is 0 months, so the hedges have no "
                "effect.",
                "warning",
                "hedge_months",
            )
        )
    if hedged and hedge_months > values.integer("horizon_months"):
        issues.append(
            Issue(
                "timing_within_horizon",
                f"The hedges cover {hedge_months} months, beyond the horizon; their expiry is "
                "not shown.",
                "warning",
                "hedge_months",
            )
        )
    issues.extend(timing_issues(values))
    issue = no_shock_issue(values, ("fx_change",))
    if issue:
        issues.append(issue)
    return issues


# --- Compute -----------------------------------------------------------------------------------


def compute(context: ComputeContext) -> ModelResult:
    values = context.values
    record = context.recorder.record
    horizon = context.horizon
    currency = values.text("reporting_currency") or ""
    per_year = f"{currency} per year"
    per_month = f"{currency} per month"
    result = ModelResult()

    with arithmetic():
        rate = values.number("fx_rate")
        revenue = values.number("annual_revenue")
        costs = values.number("annual_operating_costs")
        usd_revenue = values.number("annual_usd_revenue")
        usd_costs = values.number("annual_usd_costs")
        dollar = percent_to_fraction(values.number("fx_change"))
        hedge_r = percent_to_fraction(values.number("revenue_hedge_ratio"))
        hedge_c = percent_to_fraction(values.number("cost_hedge_ratio"))
        hedge_months = values.integer("hedge_months")
        start = values.integer("shock_start_month")
        duration = values.integer("shock_duration_months")
        end = start + duration - 1 if duration > 0 else horizon

        revenue_usd = record(
            "E1",
            "Baseline US-dollar revenue in the reporting currency",
            ("R$", usd_revenue * rate, per_year),
            [("U_R", usd_revenue, "USD per year"), ("X₀", rate, f"{currency} per USD")],
        )
        costs_usd = record(
            "E2",
            "Baseline US-dollar costs in the reporting currency",
            ("C$", usd_costs * rate, per_year),
            [("U_C", usd_costs, "USD per year"), ("X₀", rate, f"{currency} per USD")],
        )
        revenue_share = record(
            "E3",
            "Share of revenue invoiced in US dollars",
            ("s_R", revenue_usd / revenue, "ratio"),
            [("R$", revenue_usd, per_year), ("R", revenue, per_year)],
        )
        cost_share = record(
            "E3",
            "Share of costs paid in US dollars",
            ("s_C", costs_usd / costs, "ratio"),
            [("C$", costs_usd, per_year), ("O", costs, per_year)],
        )
        revenue_month = record(
            "E4",
            "Monthly baseline US-dollar revenue",
            ("r₀", revenue_usd / MONTHS_PER_YEAR, per_month),
            [("R$", revenue_usd, per_year)],
        )
        cost_month = record(
            "E4",
            "Monthly baseline US-dollar costs",
            ("c₀", costs_usd / MONTHS_PER_YEAR, per_month),
            [("C$", costs_usd, per_year)],
        )

        months: dict[str, list[Decimal]] = {
            name: []
            for name in ("fx_relative", "revenue_change", "cost_change", "operating_profit_change")
        }
        gross_revenue = ZERO
        gross_costs = ZERO
        for month in range(1, horizon + 1):
            relative = record(
                "E5",
                "Exchange rate relative to baseline",
                ("q", exp(context.propagation.at(USD_INR, month)), "ratio"),
                [
                    ("x", dollar, "fraction"),
                    ("S", Decimal(start), "months"),
                    ("E", Decimal(end), "months"),
                ],
                month=month,
            )
            covered = month <= hedge_months
            hedged_r = record(
                "E6",
                "Hedged share of US-dollar revenue",
                ("h_R", hedge_r if covered else ZERO, "ratio"),
                [("h_R", hedge_r, "fraction"), ("M_h", Decimal(hedge_months), "months")],
                month=month,
            )
            hedged_c = record(
                "E6",
                "Hedged share of US-dollar costs",
                ("h_C", hedge_c if covered else ZERO, "ratio"),
                [("h_C", hedge_c, "fraction"), ("M_h", Decimal(hedge_months), "months")],
                month=month,
            )
            revenue_delta = record(
                "E7",
                "Change in revenue",
                ("Δr", revenue_month * (ONE - hedged_r) * (relative - ONE), per_month),
                [
                    ("r₀", revenue_month, per_month),
                    ("h_R", hedged_r, "ratio"),
                    ("q", relative, "ratio"),
                ],
                month=month,
            )
            cost_delta = record(
                "E8",
                "Change in costs",
                ("Δc", cost_month * (ONE - hedged_c) * (relative - ONE), per_month),
                [
                    ("c₀", cost_month, per_month),
                    ("h_C", hedged_c, "ratio"),
                    ("q", relative, "ratio"),
                ],
                month=month,
            )
            profit = record(
                "E9",
                "Change in operating profit",
                ("Δπ", revenue_delta - cost_delta, per_month),
                [("Δr", revenue_delta, per_month), ("Δc", cost_delta, per_month)],
                month=month,
            )
            gross_revenue += revenue_month * (relative - ONE)
            gross_costs += cost_month * (relative - ONE)
            months["fx_relative"].append(relative)
            months["revenue_change"].append(revenue_delta)
            months["cost_change"].append(cost_delta)
            months["operating_profit_change"].append(profit)

        months_d = Decimal(horizon)
        total_revenue = sum(months["revenue_change"], ZERO)
        total_costs = sum(months["cost_change"], ZERO)
        total_profit = record(
            "E10",
            "Change in operating profit over the horizon",
            ("ΣΔπ", sum(months["operating_profit_change"], ZERO), currency),
            [
                ("ΣΔr", total_revenue, currency),
                ("ΣΔc", total_costs, currency),
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
        scenario_revenue = revenue * months_d / MONTHS_PER_YEAR + total_revenue
        scenario_costs = costs * months_d / MONTHS_PER_YEAR + total_costs
        if scenario_revenue <= ZERO:
            raise NumericalError(
                "Revenue over the horizon would fall to zero or below; the operating margin "
                "is undefined."
            )
        scenario_margin = record(
            "E12",
            "Scenario operating margin",
            ("μ₁", (scenario_revenue - scenario_costs) / scenario_revenue, "ratio"),
            [
                ("R·H/12 + ΣΔr", scenario_revenue, currency),
                ("O·H/12 + ΣΔc", scenario_costs, currency),
            ],
        )
        revenue_hedging = record(
            "E13",
            "Revenue hedging effect",
            ("ΣΔr − G_R", total_revenue - gross_revenue, currency),
            [("ΣΔr", total_revenue, currency), ("G_R", gross_revenue, currency)],
        )
        cost_hedging = record(
            "E13",
            "Cost hedging effect",
            ("ΣΔc − G_C", total_costs - gross_costs, currency),
            [("ΣΔc", total_costs, currency), ("G_C", gross_costs, currency)],
        )
        net = record(
            "E14",
            "Net US-dollar exposure",
            ("N", usd_revenue - usd_costs, "USD per year"),
            [("U_R", usd_revenue, "USD per year"), ("U_C", usd_costs, "USD per year")],
        )
        run_rate_fx = exp(context.propagation.final(USD_INR))
        run_rate = record(
            "E14",
            "Run-rate annual operating-profit change",
            ("ΔΠ*", net * rate * (run_rate_fx - ONE), per_year),
            [
                ("N", net, "USD per year"),
                ("X₀", rate, f"{currency} per USD"),
                ("1 + x", run_rate_fx, "ratio"),
            ],
        )
        margin_change = scenario_margin - base_margin

    result.scalars.update(
        baseline_usd_revenue=revenue_usd,
        baseline_usd_costs=costs_usd,
        usd_revenue_share=revenue_share,
        usd_cost_share=cost_share,
        net_usd_exposure=net,
        baseline_operating_profit=base_profit,
        baseline_operating_margin=base_margin,
        revenue_change=total_revenue,
        cost_change=total_costs,
        operating_profit_change=total_profit,
        gross_revenue_change=gross_revenue,
        revenue_hedging_effect=revenue_hedging,
        gross_cost_change=gross_costs,
        cost_hedging_effect=cost_hedging,
        scenario_operating_profit=scenario_profit,
        scenario_operating_margin=scenario_margin,
        operating_margin_change=margin_change,
        run_rate_operating_profit_change=run_rate,
    )
    result.monthly.update(months)
    result.units.update(
        baseline_usd_revenue=per_year,
        baseline_usd_costs=per_year,
        usd_revenue_share="ratio",
        usd_cost_share="ratio",
        net_usd_exposure="USD per year",
        baseline_operating_profit=currency,
        baseline_operating_margin="ratio",
        revenue_change=currency,
        cost_change=currency,
        operating_profit_change=currency,
        gross_revenue_change=currency,
        revenue_hedging_effect=currency,
        gross_cost_change=currency,
        cost_hedging_effect=currency,
        scenario_operating_profit=currency,
        scenario_operating_margin="ratio",
        operating_margin_change="ratio_points",
        run_rate_operating_profit_change=per_year,
    )
    result.monthly_units.update(
        fx_relative="price_relative",
        revenue_change=per_month,
        cost_change=per_month,
        operating_profit_change=per_month,
    )
    return result
