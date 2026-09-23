"""Airline fuel-cost shock, version 1.0.0.

What a change in crude oil, jet fuel and the exchange rate does to an airline's fuel bill
and operating profit over the next months, with hedging and fare pass-through, holding
everything else constant.

The fuel bill is modelled as consumption × benchmark jet fuel price (US dollars) × the
exchange rate. Crude oil reaches jet fuel through the knowledge-graph relationship
"Brent crude influences jet fuel" (rule T1), with an elasticity and a lag that are
explicit assumptions. Every input either comes from the user, from a stored observation
with its provenance, or is a labelled assumption with a stated default: RUMIN holds no
company financial data and invents none.
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
    ObservationSource,
    OutputDefinition,
    PathwayLink,
    SensitivitySpec,
    Statement,
    SupportingRelationship,
    Term,
    TransmissionRule,
    ValidationRuleDefinition,
)
from app.simulation.runtime import ComputeContext, Issue, ModelResult, ResolvedValues
from app.simulation.units import PRICE_UNITS, VOLUME_UNITS, volume_conversion_factor

MODEL_ID = "airline_fuel_cost"
VERSION = "1.0.0"

BRENT = "variable:var_brent_crude"
JET_FUEL = "variable:var_jet_fuel"
USD_INR = "variable:var_usd_inr"
AIR_TRANSPORT = "industry:ind_air_transport"

D = Decimal
PERCENT_CHANGE_MIN = D(-100)  # exclusive: a price cannot fall by 100 % or more
PERCENT_CHANGE_MAX = D(1000)  # the Phase 1 scenario-input limit

# --- Definition -------------------------------------------------------------------------------


def _shock(
    input_id: str, label: str, description: str, variable: str, step: str
) -> InputDefinition:
    return InputDefinition(
        id=input_id,
        label=label,
        category=InputCategory.SCENARIO_INPUT,
        kind=InputKind.DECIMAL,
        description=description,
        unit="percent_change",
        minimum=PERCENT_CHANGE_MIN,
        maximum=PERCENT_CHANGE_MAX,
        minimum_exclusive=True,
        max_decimals=4,
        required=False,
        default=ZERO,
        rationale="No change unless you enter one.",
        variable=variable,
        sensitivity=SensitivitySpec("absolute", D(step)),
    )


INPUTS: tuple[InputDefinition, ...] = (
    # Scenario inputs: the changes the user explores.
    _shock(
        "crude_oil_change",
        "Crude oil price change",
        "Change in the Brent crude oil price, in percent (30 means +30 %). A permanent step "
        "change from month 1. It reaches jet fuel only through the knowledge-graph "
        "relationship 'Brent crude influences jet fuel' (rule T1).",
        BRENT,
        "10",
    ),
    _shock(
        "jet_fuel_margin_change",
        "Additional jet fuel price change",
        "A change in the jet fuel price beyond what crude oil explains (for example a wider "
        "refining margin), in percent. A permanent step change from month 1.",
        JET_FUEL,
        "10",
    ),
    _shock(
        "usd_change",
        "Exchange-rate change",
        "Change in the price of one US dollar in the reporting currency, in percent. "
        "Positive means the reporting currency weakens (more rupees per dollar), which "
        "raises the cost of dollar-priced fuel. A permanent step change from month 1.",
        USD_INR,
        "5",
    ),
    # Market baseline: stored data or the user's figures.
    InputDefinition(
        id="jet_fuel_price",
        label="Baseline jet fuel price",
        category=InputCategory.MARKET_BASELINE,
        kind=InputKind.QUANTITY,
        description="The benchmark jet fuel price the airline's fuel is priced from, in US "
        "dollars per unit of volume. RUMIN holds no jet fuel prices: enter the benchmark "
        "and the date you rely on.",
        units=("usd_per_us_gallon", "usd_per_us_barrel", "usd_per_kilolitre"),
        minimum=ZERO,
        minimum_exclusive=True,
        maximum=D(100_000),
        max_decimals=6,
        variable=JET_FUEL,
        sensitivity=SensitivitySpec("relative", D(10)),
    ),
    InputDefinition(
        id="fx_rate",
        label="Baseline exchange rate",
        category=InputCategory.MARKET_BASELINE,
        kind=InputKind.DECIMAL,
        description="Units of the reporting currency per US dollar at the baseline. Enter "
        "a rate, or use the latest World Bank annual average stored in RUMIN.",
        unit="currency_per_usd",
        minimum=ZERO,
        minimum_exclusive=True,
        maximum=D(100_000),
        max_decimals=6,
        variable=USD_INR,
        sources=(
            ObservationSource(
                series_id="wb-ind-pa-nus-fcrf",
                label="World Bank: official exchange rate, INR per US$ (annual average)",
                unit="INR per USD",
                currency_pair=("INR", "USD"),
                caveat="An annual average of the official exchange rate, not a current "
                "market rate: movements within the year are smoothed out.",
            ),
        ),
        sensitivity=SensitivitySpec("relative", D(5)),
    ),
    # Company inputs: the user's figures about the airline.
    InputDefinition(
        id="entity",
        label="Airline in the knowledge graph",
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.GRAPH_NODE,
        description="Optional: the airline in RUMIN's knowledge graph this run is about. It "
        "must be a company that operates in air transport. RUMIN's sample airlines are "
        "fictional; the figures you enter are what the model uses.",
        unit="graph_node",
        required=False,
    ),
    InputDefinition(
        id="reporting_currency",
        label="Reporting currency",
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.CURRENCY,
        description="The currency the airline reports in (ISO 4217 code, e.g. INR).",
        unit="currency_code",
    ),
    InputDefinition(
        id="annual_revenue",
        label="Annual revenue",
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.DECIMAL,
        description="Annual revenue in the reporting currency, from the airline's own "
        "accounts or plan. RUMIN holds no company financial data.",
        unit="currency_per_year",
        minimum=ZERO,
        minimum_exclusive=True,
        maximum=D("1e15"),
        max_decimals=6,
        sensitivity=SensitivitySpec("relative", D(10)),
    ),
    InputDefinition(
        id="annual_operating_costs",
        label="Annual operating costs",
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.DECIMAL,
        description="Annual operating costs, including fuel, in the reporting currency.",
        unit="currency_per_year",
        minimum=ZERO,
        minimum_exclusive=True,
        maximum=D("1e15"),
        max_decimals=6,
        sensitivity=SensitivitySpec("relative", D(10)),
    ),
    InputDefinition(
        id="annual_fuel_consumption",
        label="Annual fuel consumption",
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.QUANTITY,
        description="Jet fuel consumed in a year, in kilolitres, US gallons or US barrels.",
        units=("kilolitre", "us_gallon", "us_barrel"),
        minimum=ZERO,
        minimum_exclusive=True,
        maximum=D("1e12"),
        max_decimals=6,
        sensitivity=SensitivitySpec("relative", D(10)),
    ),
    # Assumptions: stated defaults, each with its reason.
    InputDefinition(
        id="crude_pass_through",
        label="Crude-to-jet-fuel elasticity (β)",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.DECIMAL,
        description="How strongly jet fuel responds to crude oil: a 1 % change in crude "
        "changes jet fuel by β % (in log terms).",
        unit="elasticity",
        minimum=ZERO,
        maximum=D(3),
        max_decimals=4,
        required=False,
        default=ONE,
        rationale="β = 1 keeps the refining margin a constant proportion of the price, so "
        "jet fuel moves by the same percentage as crude. A neutral starting point, not an "
        "estimate: test other values with sensitivity analysis.",
        sensitivity=SensitivitySpec("absolute", D("0.2")),
    ),
    InputDefinition(
        id="crude_pass_through_lag",
        label="Crude-to-jet-fuel lag",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.INTEGER,
        description="Months before a crude oil change reaches jet fuel prices.",
        unit="months",
        minimum=ZERO,
        maximum=D(12),
        max_decimals=0,
        required=False,
        default=ZERO,
        rationale="0 assumes crude changes reach jet fuel in the same month. Set it to how "
        "the airline's fuel contracts reprice.",
        sensitivity=SensitivitySpec("absolute", D(1)),
    ),
    InputDefinition(
        id="hedge_ratio",
        label="Hedge ratio",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.DECIMAL,
        description="The share of fuel consumption hedged at the baseline US-dollar price, "
        "in percent.",
        unit="percent",
        minimum=ZERO,
        maximum=D(100),
        max_decimals=4,
        required=False,
        default=ZERO,
        rationale="0 assumes no hedging. Enter the share of the coming months' fuel the "
        "airline has hedged.",
        sensitivity=SensitivitySpec("absolute", D(20)),
    ),
    InputDefinition(
        id="hedge_months",
        label="Hedge cover",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.INTEGER,
        description="How many months, from month 1, the existing hedges cover.",
        unit="months",
        minimum=ZERO,
        maximum=D(36),
        max_decimals=0,
        required=False,
        default=ZERO,
        rationale="0 assumes no hedge cover. Hedges are assumed not to be rolled over when "
        "they expire.",
        sensitivity=SensitivitySpec("absolute", D(3)),
    ),
    InputDefinition(
        id="fare_pass_through",
        label="Fare pass-through",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.DECIMAL,
        description="The share of any change in fuel cost recovered through fares, in percent.",
        unit="percent",
        minimum=ZERO,
        maximum=D(100),
        max_decimals=4,
        required=False,
        default=ZERO,
        rationale="0 assumes fares do not change. Enter the share of a fuel-cost change the "
        "airline expects to pass on to passengers.",
        sensitivity=SensitivitySpec("absolute", D(20)),
    ),
    InputDefinition(
        id="fare_pass_through_lag",
        label="Fare pass-through lag",
        category=InputCategory.ASSUMPTION,
        kind=InputKind.INTEGER,
        description="Months before fares respond to a change in fuel cost.",
        unit="months",
        minimum=ZERO,
        maximum=D(12),
        max_decimals=0,
        required=False,
        default=ZERO,
        rationale="0 assumes fares adjust in the same month as the fuel cost. Enter the "
        "delay you expect.",
        sensitivity=SensitivitySpec("absolute", D(2)),
    ),
    # Setting.
    InputDefinition(
        id="horizon_months",
        label="Horizon",
        category=InputCategory.SETTING,
        kind=InputKind.INTEGER,
        description="How many months to simulate.",
        unit="months",
        minimum=ONE,
        maximum=D(36),
        max_decimals=0,
        required=False,
        default=D(12),
        rationale="Twelve months shows a full year after the shock.",
    ),
)


def _t(symbol: str, meaning: str, unit: str) -> Term:
    return Term(symbol, meaning, unit)


EQUATIONS: tuple[EquationDefinition, ...] = (
    EquationDefinition(
        "E1",
        "Consumption in the price's volume unit",
        "V = Q × λ(u_Q) / λ(u_P)",
        _t("V", "annual fuel consumption in the price's volume unit", "volume per year"),
        (
            _t("Q", "annual fuel consumption as entered", "volume per year"),
            _t("λ(u)", "litres in one unit u (exact legal definitions)", "litres"),
        ),
        "An explicit unit conversion. The factor is exact (barrel → gallon = 42) or "
        "correctly rounded to 34 significant digits (kilolitre → gallon).",
        "annual",
    ),
    EquationDefinition(
        "E2",
        "Baseline benchmark fuel cost in US dollars",
        "B_USD = V × P₀",
        _t("B_USD", "annual benchmark fuel cost", "USD per year"),
        (
            _t("V", "annual consumption in the price's volume unit", "volume per year"),
            _t("P₀", "baseline benchmark jet fuel price", "USD per volume"),
        ),
        "What the year's fuel costs at the benchmark price.",
        "annual",
        assumptions=("A3",),
        limitations=("L4",),
    ),
    EquationDefinition(
        "E3",
        "Baseline benchmark fuel cost in the reporting currency",
        "B = B_USD × X₀",
        _t("B", "annual benchmark fuel cost", "reporting currency per year"),
        (
            _t("B_USD", "annual benchmark fuel cost", "USD per year"),
            _t("X₀", "baseline exchange rate", "reporting currency per USD"),
        ),
        "An explicit currency conversion at the baseline exchange rate (an input, never assumed).",
        "annual",
        assumptions=("A8",),
    ),
    EquationDefinition(
        "E4",
        "Fuel share of operating costs",
        "f = B / O",
        _t("f", "benchmark fuel cost as a share of operating costs", "ratio"),
        (
            _t("B", "annual benchmark fuel cost", "reporting currency per year"),
            _t("O", "annual operating costs", "reporting currency per year"),
        ),
        "A consistency check: the fuel bill cannot exceed operating costs (f ≤ 1).",
        "annual",
    ),
    EquationDefinition(
        "E5",
        "Monthly baseline fuel cost",
        "b₀ = B / 12",
        _t("b₀", "baseline fuel cost in one month", "reporting currency per month"),
        (_t("B", "annual benchmark fuel cost", "reporting currency per year"),),
        "A frequency conversion: an annual flow spread evenly over twelve months.",
        "annual",
        assumptions=("A2",),
        limitations=("L6",),
    ),
    EquationDefinition(
        "E6",
        "Jet fuel log-change",
        "ℓ(m) = β · ln(1 + c) · 𝟙[m > L] + ln(1 + s)",
        _t("ℓ(m)", "log-change of the jet fuel price in month m", "log change"),
        (
            _t("β", "crude-to-jet-fuel elasticity", "elasticity"),
            _t("c", "crude oil price change", "fraction"),
            _t("L", "crude-to-jet-fuel lag", "months"),
            _t("s", "additional jet fuel price change", "fraction"),
        ),
        "Propagated by the transmission engine along rule T1 (Brent crude → influences → "
        "jet fuel), plus the direct change to jet fuel itself.",
        "monthly",
        assumptions=("A4", "A5"),
        limitations=("L5",),
    ),
    EquationDefinition(
        "E7",
        "Jet fuel price relative to baseline",
        "r(m) = exp(ℓ(m))",
        _t("r(m)", "jet fuel price in month m relative to the baseline", "ratio"),
        (_t("ℓ(m)", "log-change of the jet fuel price", "log change"),),
        "Turns the log-change back into a price ratio (r = 1.3 means +30 %).",
        "monthly",
    ),
    EquationDefinition(
        "E8",
        "Exchange rate relative to baseline",
        "q = 1 + x",
        _t("q", "exchange rate relative to the baseline", "ratio"),
        (_t("x", "exchange-rate change", "fraction"),),
        "The reporting currency's price of a dollar, relative to the baseline.",
        "monthly",
        assumptions=("A4", "A8"),
    ),
    EquationDefinition(
        "E9",
        "Hedged share in month m",
        "h(m) = h if m ≤ M_h, otherwise 0",
        _t("h(m)", "share of month m's fuel that is hedged", "ratio"),
        (
            _t("h", "hedge ratio", "fraction"),
            _t("M_h", "months of hedge cover", "months"),
        ),
        "Hedges cover the first M_h months and are not rolled over.",
        "monthly",
        assumptions=("A6",),
    ),
    EquationDefinition(
        "E10",
        "Scenario monthly fuel cost",
        "b₁(m) = b₀ × q × [h(m) + (1 − h(m)) × r(m)]",
        _t("b₁(m)", "fuel cost in month m under the scenario", "reporting currency per month"),
        (
            _t("b₀", "baseline monthly fuel cost", "reporting currency per month"),
            _t("q", "exchange rate relative to baseline", "ratio"),
            _t("h(m)", "hedged share", "ratio"),
            _t("r(m)", "jet fuel price relative to baseline", "ratio"),
        ),
        "Hedged fuel keeps the baseline dollar price; unhedged fuel pays the new price. "
        "All fuel is paid in dollars converted at the new exchange rate.",
        "monthly",
        assumptions=("A1", "A3", "A6", "A8"),
    ),
    EquationDefinition(
        "E11",
        "Change in fuel cost",
        "Δb(m) = b₁(m) − b₀",
        _t("Δb(m)", "change in fuel cost in month m", "reporting currency per month"),
        (
            _t("b₁(m)", "scenario monthly fuel cost", "reporting currency per month"),
            _t("b₀", "baseline monthly fuel cost", "reporting currency per month"),
        ),
        "Positive means the scenario costs more than the baseline.",
        "monthly",
    ),
    EquationDefinition(
        "E12",
        "Fare recovery",
        "Δr(m) = φ × Δb(m − L_f) if m > L_f, otherwise 0",
        _t("Δr(m)", "change in revenue from fares in month m", "reporting currency per month"),
        (
            _t("φ", "fare pass-through", "fraction"),
            _t("Δb", "change in fuel cost", "reporting currency per month"),
            _t("L_f", "fare pass-through lag", "months"),
        ),
        "Fares recover a share of the change in fuel cost after a delay, for rises and "
        "falls alike.",
        "monthly",
        assumptions=("A7",),
        limitations=("L2", "L3"),
    ),
    EquationDefinition(
        "E13",
        "Change in operating profit",
        "Δπ(m) = Δr(m) − Δb(m)",
        _t("Δπ(m)", "change in operating profit in month m", "reporting currency per month"),
        (
            _t("Δr(m)", "fare recovery", "reporting currency per month"),
            _t("Δb(m)", "change in fuel cost", "reporting currency per month"),
        ),
        "Everything else is held at its baseline.",
        "monthly",
        assumptions=("A1",),
        limitations=("L7",),
    ),
    EquationDefinition(
        "E14",
        "Totals over the horizon",
        "ΣΔb = Σₘ Δb(m); ΣΔr = Σₘ Δr(m); ΣΔπ = Σₘ Δπ(m), m = 1…H",
        _t("ΣΔπ", "change in operating profit over the horizon", "reporting currency"),
        (
            _t("Δb(m)", "change in fuel cost", "reporting currency per month"),
            _t("Δr(m)", "fare recovery", "reporting currency per month"),
            _t("H", "horizon", "months"),
        ),
        "Sums of the monthly changes.",
        "horizon",
    ),
    EquationDefinition(
        "E15",
        "Operating profit over the horizon",
        "Π₀ = (R − O) × H / 12; Π₁ = Π₀ + ΣΔπ",
        _t("Π₁", "operating profit over the horizon under the scenario", "reporting currency"),
        (
            _t("R", "annual revenue", "reporting currency per year"),
            _t("O", "annual operating costs", "reporting currency per year"),
            _t("H", "horizon", "months"),
            _t("ΣΔπ", "change in operating profit over the horizon", "reporting currency"),
        ),
        "The baseline is the entered annual figures, spread evenly over the horizon.",
        "horizon",
        assumptions=("A1", "A2"),
    ),
    EquationDefinition(
        "E16",
        "Operating margins",
        "μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔr − O·H/12 − ΣΔb) / (R·H/12 + ΣΔr)",
        _t("μ₁", "operating margin over the horizon under the scenario", "ratio"),
        (
            _t("R", "annual revenue", "reporting currency per year"),
            _t("O", "annual operating costs", "reporting currency per year"),
            _t("ΣΔr", "fare recovery over the horizon", "reporting currency"),
            _t("ΣΔb", "change in fuel cost over the horizon", "reporting currency"),
        ),
        "Operating profit divided by revenue, before and after the scenario.",
        "horizon",
    ),
    EquationDefinition(
        "E17",
        "Steady-state annual effect",
        "ΔB* = B × [q × exp(β·ln(1 + c) + ln(1 + s)) − 1]; ΔΠ* = (φ − 1) × ΔB*",
        _t(
            "ΔB*",
            "annual change in fuel cost once lags have passed and hedges expired",
            "reporting currency per year",
        ),
        (
            _t("B", "annual benchmark fuel cost", "reporting currency per year"),
            _t("q", "exchange rate relative to baseline", "ratio"),
            _t("φ", "fare pass-through", "fraction"),
        ),
        "The full annual effect after every lag has passed and every hedge has expired.",
        "steady_state",
        assumptions=("A4", "A5", "A7"),
    ),
    EquationDefinition(
        "E18",
        "Offsetting revenue change",
        "g = ΣΔb / (R × H / 12)",
        _t("g", "revenue change over the horizon that would offset the fuel-cost change", "ratio"),
        (
            _t("ΣΔb", "change in fuel cost over the horizon", "reporting currency"),
            _t("R", "annual revenue", "reporting currency per year"),
            _t("H", "horizon", "months"),
        ),
        "How much revenue would have to change, uniformly, to leave operating profit "
        "unchanged. It is arithmetic, not a recommendation to raise fares.",
        "horizon",
        limitations=("L2",),
    ),
    EquationDefinition(
        "E19",
        "Hedging effect",
        "G = Σₘ b₀ × (q × r(m) − 1); hedging effect = ΣΔb − G",
        _t(
            "hedging effect",
            "how much the hedges change the fuel-cost change",
            "reporting currency",
        ),
        (
            _t("b₀", "baseline monthly fuel cost", "reporting currency per month"),
            _t("q", "exchange rate relative to baseline", "ratio"),
            _t("r(m)", "jet fuel price relative to baseline", "ratio"),
            _t("ΣΔb", "change in fuel cost over the horizon", "reporting currency"),
        ),
        "G is the change the fuel bill would see with no hedges. The bridge "
        "−G − hedging effect + ΣΔr = ΣΔπ is exact.",
        "horizon",
        assumptions=("A6",),
    ),
)

CURRENCY = "currency"
CURRENCY_PER_YEAR = "currency_per_year"

OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "annual_consumption_in_price_unit",
        "Annual consumption in the price's unit",
        "volume_per_year",
        "derived",
        "Q converted to the price's volume unit.",
        "E1",
    ),
    OutputDefinition(
        "baseline_fuel_cost_usd",
        "Baseline fuel cost (USD)",
        "usd_per_year",
        "derived",
        "Annual benchmark fuel cost in US dollars.",
        "E2",
    ),
    OutputDefinition(
        "baseline_fuel_cost",
        "Baseline fuel cost",
        CURRENCY_PER_YEAR,
        "derived",
        "Annual benchmark fuel cost in the reporting currency.",
        "E3",
    ),
    OutputDefinition(
        "fuel_share",
        "Fuel share of operating costs",
        "ratio",
        "derived",
        "Benchmark fuel cost ÷ operating costs.",
        "E4",
    ),
    OutputDefinition(
        "monthly_baseline_fuel_cost",
        "Monthly baseline fuel cost",
        "currency_per_month",
        "derived",
        "One twelfth of the annual fuel cost.",
        "E5",
    ),
    OutputDefinition(
        "baseline_operating_profit",
        "Baseline operating profit (horizon)",
        CURRENCY,
        "derived",
        "Operating profit over the horizon with no change.",
        "E15",
    ),
    OutputDefinition(
        "baseline_operating_margin",
        "Baseline operating margin",
        "ratio",
        "derived",
        "Operating profit ÷ revenue with no change.",
        "E16",
    ),
    OutputDefinition(
        "jet_fuel_price_change",
        "Jet fuel price change (steady state)",
        "ratio",
        "simulated",
        "The jet fuel price change once the crude lag has passed.",
        "E7",
        attributable=True,
    ),
    OutputDefinition(
        "fuel_cost_change",
        "Change in fuel cost (horizon)",
        CURRENCY,
        "simulated",
        "Extra fuel cost over the horizon, after hedges. Positive means fuel costs more.",
        "E14",
        attributable=True,
    ),
    OutputDefinition(
        "gross_fuel_cost_change",
        "Change in fuel cost without hedges (horizon)",
        CURRENCY,
        "simulated",
        "The fuel-cost change over the horizon if nothing were hedged.",
        "E19",
        attributable=True,
    ),
    OutputDefinition(
        "hedging_effect",
        "Hedging effect (horizon)",
        CURRENCY,
        "simulated",
        "What the hedges changed: negative means they reduced the increase.",
        "E19",
        attributable=True,
    ),
    OutputDefinition(
        "fare_recovery",
        "Fare recovery (horizon)",
        CURRENCY,
        "simulated",
        "Extra revenue from fares over the horizon, as part of the fuel-cost change is passed on.",
        "E14",
        attributable=True,
    ),
    OutputDefinition(
        "operating_profit_change",
        "Change in operating profit (horizon)",
        CURRENCY,
        "simulated",
        "Fare recovery minus the fuel-cost change, over the horizon.",
        "E14",
        attributable=True,
    ),
    OutputDefinition(
        "scenario_operating_profit",
        "Scenario operating profit (horizon)",
        CURRENCY,
        "simulated",
        "Baseline operating profit plus the change, over the horizon.",
        "E15",
    ),
    OutputDefinition(
        "scenario_operating_margin",
        "Scenario operating margin",
        "ratio",
        "simulated",
        "Operating profit ÷ revenue over the horizon, under the scenario.",
        "E16",
    ),
    OutputDefinition(
        "operating_margin_change",
        "Change in operating margin",
        "ratio_points",
        "simulated",
        "Scenario margin minus baseline margin (0.01 is one percentage point).",
        "E16",
        attributable=True,
    ),
    OutputDefinition(
        "steady_state_fuel_cost_change",
        "Steady-state annual fuel-cost change",
        CURRENCY_PER_YEAR,
        "simulated",
        "The yearly fuel-cost change once every lag has passed and the hedges have expired.",
        "E17",
        attributable=True,
    ),
    OutputDefinition(
        "steady_state_operating_profit_change",
        "Steady-state annual operating-profit change",
        CURRENCY_PER_YEAR,
        "simulated",
        "The yearly operating-profit change in that steady state, after fare recovery.",
        "E17",
        attributable=True,
    ),
    OutputDefinition(
        "offsetting_revenue_change",
        "Offsetting revenue change",
        "ratio",
        "simulated",
        "The revenue increase, as a share of revenue, that would offset the fuel-cost change.",
        "E18",
        attributable=True,
    ),
)

MONTHLY_OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "jet_fuel_relative",
        "Jet fuel price relative to baseline",
        "price_relative",
        "simulated",
        "r(m): 1.3 means 30 % above the baseline.",
        "E7",
    ),
    OutputDefinition(
        "hedged_share",
        "Hedged share",
        "ratio",
        "derived",
        "h(m): the share of the month's fuel at the hedged price.",
        "E9",
    ),
    OutputDefinition(
        "baseline_fuel_cost",
        "Baseline fuel cost",
        "currency_per_month",
        "derived",
        "b₀: one twelfth of the annual benchmark fuel cost.",
        "E5",
    ),
    OutputDefinition(
        "scenario_fuel_cost",
        "Scenario fuel cost",
        "currency_per_month",
        "simulated",
        "b₁(m): the month's fuel cost under the scenario.",
        "E10",
    ),
    OutputDefinition(
        "fuel_cost_change",
        "Change in fuel cost",
        "currency_per_month",
        "simulated",
        "Δb(m) = b₁(m) − b₀.",
        "E11",
    ),
    OutputDefinition(
        "fare_recovery",
        "Fare recovery",
        "currency_per_month",
        "simulated",
        "Δr(m): revenue recovered through fares.",
        "E12",
    ),
    OutputDefinition(
        "operating_profit_change",
        "Change in operating profit",
        "currency_per_month",
        "simulated",
        "Δπ(m) = Δr(m) − Δb(m).",
        "E13",
    ),
)

ASSUMPTIONS: tuple[Statement, ...] = (
    Statement(
        "A1",
        "Everything the model does not include stays at its baseline: fuel "
        "consumption, other costs, traffic, capacity, fares (apart from the stated "
        "pass-through) and financing.",
    ),
    Statement(
        "A2",
        "Fuel is consumed evenly through the year: each month uses one twelfth "
        "of the annual volume, and annual revenue and costs accrue evenly.",
    ),
    Statement(
        "A3",
        "The fuel bill is consumption × the benchmark jet fuel price × the "
        "exchange rate. Taxes, fees and supplier margins that do not follow the "
        "benchmark are outside the model.",
    ),
    Statement(
        "A4",
        "Scenario changes are permanent step changes that start in month 1 and "
        "last for the whole horizon.",
    ),
    Statement(
        "A5",
        "Jet fuel responds to crude oil with a constant elasticity β after a lag: "
        "ln(jet fuel) changes by β × ln(1 + crude change). With β = 1 the refining "
        "margin stays a constant proportion of the price.",
    ),
    Statement(
        "A6",
        "Hedged fuel pays the baseline US-dollar price until the hedges expire; "
        "the exchange rate is not hedged; hedges are not rolled over.",
    ),
    Statement(
        "A7",
        "Fares recover a fixed share of the change in fuel cost after a lag, for "
        "rises and falls alike, and passenger demand does not respond.",
    ),
    Statement(
        "A8",
        "The exchange rate affects the fuel bill only: other dollar costs and "
        "any dollar revenue are outside the model.",
    ),
)

LIMITATIONS: tuple[Statement, ...] = (
    Statement(
        "L1",
        "The model shows the arithmetic consequence of the inputs and "
        "assumptions. It is not a forecast of what will happen, and not investment "
        "advice.",
    ),
    Statement("L2", "Passenger demand, capacity and schedules do not respond to fares or costs."),
    Statement("L3", "Competitors' responses and market share are not modelled."),
    Statement(
        "L4",
        "Only the benchmark-linked fuel cost is modelled. Ad-valorem taxes that "
        "scale with the price are not captured, so a real fuel bill can move more "
        "than the benchmark.",
    ),
    Statement(
        "L5",
        "The elasticity, lags, hedge terms and pass-through are assumptions with "
        "stated defaults. None has been estimated from data in RUMIN.",
    ),
    Statement(
        "L6", "Monthly steps: timing within a month is ignored, and seasonality is not modelled."
    ),
    Statement(
        "L7",
        "Operating profit only: no interest, tax, hedge accounting, working "
        "capital or cash-flow timing.",
    ),
)

VALIDATION_RULES: tuple[ValidationRuleDefinition, ...] = (
    ValidationRuleDefinition(
        "input_range",
        "Every number is within its range and has at "
        "most the allowed decimal places; required inputs are present.",
        "error",
    ),
    ValidationRuleDefinition(
        "percent_change_limits",
        "Scenario changes are greater than "
        "−100 % and at most +1,000 %, with at most 4 decimals — the "
        "limits Phase 1 publishes for scenario inputs.",
        "error",
    ),
    ValidationRuleDefinition(
        "unit_choice",
        "Quantities use one of the listed units; no other unit is converted.",
        "error",
    ),
    ValidationRuleDefinition(
        "usd_rate_is_one",
        "When the reporting currency is USD, the exchange rate must be exactly 1.",
        "error",
    ),
    ValidationRuleDefinition(
        "observation_matches",
        "A stored observation may supply the "
        "exchange rate only when its currency pair and unit match the "
        "reporting currency.",
        "error",
    ),
    ValidationRuleDefinition(
        "fuel_share_exceeds_costs",
        "The benchmark fuel cost of the stated consumption cannot exceed operating costs.",
        "error",
    ),
    ValidationRuleDefinition(
        "fuel_share_low",
        "A benchmark fuel cost below 1 % of operating "
        "costs is flagged: it usually means a wrong consumption or price "
        "unit.",
        "warning",
    ),
    ValidationRuleDefinition(
        "channel_confirmed",
        "A crude oil change reaches jet fuel only if "
        "the knowledge graph states that Brent crude influences jet "
        "fuel.",
        "error",
    ),
    ValidationRuleDefinition(
        "entity_is_airline",
        "A chosen entity must be a company that operates in air transport in the knowledge graph.",
        "error",
    ),
    ValidationRuleDefinition(
        "timing_within_horizon",
        "Hedges, lags and fare responses that fall outside the horizon are flagged.",
        "warning",
    ),
    ValidationRuleDefinition(
        "no_shock",
        "A run in which every scenario change is zero is flagged: it equals the baseline.",
        "warning",
    ),
)

TRANSMISSION_RULES: tuple[TransmissionRule, ...] = (
    TransmissionRule(
        id="T1",
        edge_type="influences",
        source=BRENT,
        target=JET_FUEL,
        coefficient_input="crude_pass_through",
        lag_input="crude_pass_through_lag",
        form="log_linear",
        description="A change in Brent crude reaches the jet fuel price with elasticity β "
        "after the stated lag.",
    ),
)

SUPPORTING: tuple[SupportingRelationship, ...] = (
    SupportingRelationship(
        "S1",
        "affects_costs",
        JET_FUEL,
        AIR_TRANSPORT,
        "Jet fuel is a cost of air transport: the reason the fuel bill (E2–E10) belongs in an "
        "airline's operating costs. Cited, not propagated.",
    ),
    SupportingRelationship(
        "S2",
        "in_industry",
        "{entity}",
        AIR_TRANSPORT,
        "The chosen airline operates in air transport.",
        required_with_entity=True,
    ),
    SupportingRelationship(
        "S3",
        "affects_costs",
        USD_INR,
        "{entity}",
        "The exchange rate affects the chosen airline's costs (E3, E8). Cited, not propagated.",
    ),
)

REFERENCES: tuple[Statement, ...] = (
    Statement(
        "U1",
        "Units: the US gallon is 231 cubic inches, exactly 3.785411784 litres; "
        "the US barrel of petroleum is 42 US gallons, exactly 158.987294928 litres.",
    ),
    Statement(
        "V1",
        "Variables: Brent crude (USD per barrel), jet fuel, U.S. Gulf Coast (USD "
        "per gallon) and USD/INR (INR per USD) are defined in RUMIN's reference data, "
        "with their publishers. RUMIN stores no values for them.",
    ),
    Statement(
        "D1",
        "Stored data: the exchange rate may come from the World Bank's World "
        "Development Indicators (PA.NUS.FCRF, CC BY 4.0) when a retrieval has stored "
        "it.",
    ),
)

DEFINITION = ModelDefinition(
    id=MODEL_ID,
    version=VERSION,
    name="Airline fuel-cost shock",
    summary="What a change in crude oil, jet fuel and the exchange rate does to an airline's "
    "fuel bill and operating profit, month by month, with hedging and fare pass-through.",
    description="A deterministic, monthly model of one airline. The baseline fuel bill is "
    "annual consumption × the benchmark jet fuel price × the exchange rate. Scenario "
    "changes to crude oil (propagated to jet fuel along a validated knowledge-graph "
    "relationship), to jet fuel directly and to the exchange rate change the monthly bill. "
    "Hedges fix the dollar price of part of the fuel for a number of months; fares recover "
    "a share of the change after a lag. Everything else stays at its baseline.",
    domain="Aviation · commodity prices · exchange rates",
    status=ModelStatus.PREVIEW,
    inputs=INPUTS,
    equations=EQUATIONS,
    outputs=OUTPUTS,
    monthly_outputs=MONTHLY_OUTPUTS,
    transmission_rules=TRANSMISSION_RULES,
    supporting_relationships=SUPPORTING,
    assumptions=ASSUMPTIONS,
    limitations=LIMITATIONS,
    validation_rules=VALIDATION_RULES,
    references=REFERENCES,
    pathway=(
        PathwayLink("input:crude_oil_change", BRENT, "changes"),
        PathwayLink(BRENT, JET_FUEL, "influences (β, lag)", ("E6",), rule="T1"),
        PathwayLink("input:jet_fuel_margin_change", JET_FUEL, "changes", ("E6",)),
        PathwayLink("input:usd_change", USD_INR, "changes", ("E8",)),
        PathwayLink(
            JET_FUEL, "output:fuel_cost_change", "prices the unhedged fuel", ("E7", "E10", "E11")
        ),
        PathwayLink(
            USD_INR, "output:fuel_cost_change", "converts the dollar bill", ("E3", "E8", "E10")
        ),
        PathwayLink(
            "input:hedge_ratio", "output:fuel_cost_change", "fixes part of the price", ("E9", "E10")
        ),
        PathwayLink(
            "output:fuel_cost_change", "output:fare_recovery", "is partly passed on", ("E12",)
        ),
        PathwayLink(
            "output:fuel_cost_change", "output:operating_profit_change", "reduces", ("E13",)
        ),
        PathwayLink(
            "output:fare_recovery", "output:operating_profit_change", "adds back", ("E13",)
        ),
    ),
    bridge=(
        BridgeItem("gross_fuel_cost_change", -1, "Fuel-cost change without hedges"),
        BridgeItem("hedging_effect", -1, "Hedging"),
        BridgeItem("fare_recovery", 1, "Fare recovery"),
    ),
    bridge_total="operating_profit_change",
    headline_outputs=(
        "fuel_cost_change",
        "operating_profit_change",
        "operating_margin_change",
        "steady_state_operating_profit_change",
    ),
    sensitivity_defaults=(
        "crude_oil_change",
        "usd_change",
        "crude_pass_through",
        "hedge_ratio",
        "fare_pass_through",
        "jet_fuel_price",
        "annual_fuel_consumption",
    ),
    sensitivity_metric="operating_profit_change",
)

# --- Checks ------------------------------------------------------------------------------------


def _annual_benchmark_cost(values: ResolvedValues) -> Decimal:
    consumption_unit = VOLUME_UNITS[values.unit("annual_fuel_consumption")]
    price_unit = PRICE_UNITS[values.unit("jet_fuel_price")]
    factor = volume_conversion_factor(consumption_unit, price_unit.volume)
    with arithmetic():
        return (
            values.number("annual_fuel_consumption")
            * factor
            * values.number("jet_fuel_price")
            * values.number("fx_rate")
        )


def _amount(value: Decimal, currency: str) -> str:
    return f"{currency} {value:,.0f}"


def check(values: ResolvedValues) -> list[Issue]:
    """Cross-field rules, once every input is resolved."""
    issues: list[Issue] = []
    currency = values.text("reporting_currency") or ""
    if currency == "USD" and values.number("fx_rate") != ONE:
        issues.append(
            Issue(
                "usd_rate_is_one",
                "The reporting currency is USD, so the exchange rate must be exactly 1 "
                "(one US dollar per US dollar).",
                field="fx_rate",
            )
        )
    cost = _annual_benchmark_cost(values)
    operating = values.number("annual_operating_costs")
    with arithmetic():
        share = cost / operating
    if share > ONE:
        issues.append(
            Issue(
                "fuel_share_exceeds_costs",
                f"The benchmark fuel cost of the stated consumption ({_amount(cost, currency)} a "
                f"year) exceeds the annual operating costs ({_amount(operating, currency)}). "
                "Check the consumption, the price and their units.",
                field="annual_fuel_consumption",
            )
        )
    elif share < D("0.01"):
        issues.append(
            Issue(
                "fuel_share_low",
                f"The benchmark fuel cost is {share:.2%} of operating costs, which is "
                "unusually low for an airline. Check the consumption and price units.",
                severity="warning",
                field="annual_fuel_consumption",
            )
        )

    horizon = values.integer("horizon_months")
    hedge_ratio = values.number("hedge_ratio")
    hedge_months = values.integer("hedge_months")
    if hedge_ratio > ZERO and hedge_months == 0:
        issues.append(
            Issue(
                "timing_within_horizon",
                "A hedge ratio is set but the hedge cover "
                "is 0 months, so the hedges have no effect.",
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
    if hedge_ratio > ZERO and hedge_months > horizon:
        issues.append(
            Issue(
                "timing_within_horizon",
                f"The hedges cover {hedge_months} months, "
                f"beyond the {horizon}-month horizon; their expiry is not shown.",
                "warning",
                "hedge_months",
            )
        )
    if (
        values.number("fare_pass_through") > ZERO
        and values.integer("fare_pass_through_lag") >= horizon
    ):
        issues.append(
            Issue(
                "timing_within_horizon",
                "Fares respond only after the horizon, so no fare recovery appears in the results.",
                "warning",
                "fare_pass_through_lag",
            )
        )
    crude = values.number("crude_oil_change")
    if crude != ZERO and values.integer("crude_pass_through_lag") >= horizon:
        issues.append(
            Issue(
                "timing_within_horizon",
                "The crude oil change reaches jet fuel "
                "only after the horizon, so it has no effect on the results.",
                "warning",
                "crude_pass_through_lag",
            )
        )
    if all(
        values.number(name) == ZERO
        for name in ("crude_oil_change", "jet_fuel_margin_change", "usd_change")
    ):
        issues.append(
            Issue(
                "no_shock",
                "Every scenario change is zero, so the scenario equals the baseline.",
                "warning",
            )
        )
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

        fx_relative = record(
            "E8",
            "Exchange rate relative to baseline",
            ("q", ONE + dollar, "ratio"),
            [("x", dollar, "fraction")],
        )

        months: dict[str, list[Decimal]] = {
            name: []
            for name in (
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
            # Δb(m − L_f): with no lag, this month's own change.
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
        steady_log = context.propagation.final(JET_FUEL)
        steady_relative = exp(steady_log)
        steady_change = record(
            "E17",
            "Steady-state annual fuel-cost change",
            ("ΔB*", cost * (fx_relative * steady_relative - ONE), per_year),
            [
                ("B", cost, per_year),
                ("q", fx_relative, "ratio"),
                ("exp(ℓ*)", steady_relative, "ratio"),
            ],
        )
        steady_profit = record(
            "E17",
            "Steady-state annual operating-profit change",
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
        jet_fuel_relative="price_relative",
        hedged_share="ratio",
        baseline_fuel_cost=per_month,
        scenario_fuel_cost=per_month,
        fuel_cost_change=per_month,
        fare_recovery=per_month,
        operating_profit_change=per_month,
    )
    return result
