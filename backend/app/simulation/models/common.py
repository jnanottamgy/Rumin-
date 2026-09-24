"""Inputs and statements that several models share.

A Scenario Lab scenario gives one value to each *shared* input (the company, its
reporting currency, revenue and operating costs, the baseline exchange rate, the horizon
and the timing of the changes) and hands it to every model it runs. For that to be
meaningful, every model that uses one of these inputs must define it identically: same
id, meaning, unit, kind and range. They are defined here once; a test checks that no model
redefines them differently.
"""

from __future__ import annotations

from decimal import Decimal

from app.simulation.decimal_math import ZERO
from app.simulation.definitions import (
    PERCENT_CHANGE,
    PERCENTAGE_POINTS,
    InputCategory,
    InputDefinition,
    InputKind,
    ObservationSource,
    SensitivitySpec,
    Statement,
    ValidationRuleDefinition,
)
from app.simulation.runtime import Issue, ResolvedValues

D = Decimal
PERCENT_CHANGE_MIN = D(-100)  # exclusive: a level cannot fall by 100 % or more
PERCENT_CHANGE_MAX = D(1000)  # the Phase 1 scenario-input limit
RATE_CHANGE_LIMIT = D(25)  # percentage points, the Phase 1 limit for rates
MAX_AMOUNT = D("1e15")

BRENT = "variable:var_brent_crude"
JET_FUEL = "variable:var_jet_fuel"
HENRY_HUB = "variable:var_henry_hub_gas"
USD_INR = "variable:var_usd_inr"
REPO_RATE = "variable:var_rbi_repo_rate"
FED_FUNDS = "variable:var_us_fed_funds"

TIMING_TEXT = (
    "It takes effect in the start month and lasts for the stated duration (to the end of "
    "the horizon unless a duration is set)."
)


def percent_shock(
    input_id: str, label: str, description: str, variable: str, step: str
) -> InputDefinition:
    """A scenario change to a price or an exchange rate, in percent."""
    return InputDefinition(
        id=input_id,
        label=label,
        category=InputCategory.SCENARIO_INPUT,
        kind=InputKind.DECIMAL,
        description=description,
        unit=PERCENT_CHANGE,
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


def rate_shock(
    input_id: str, label: str, description: str, variable: str, step: str
) -> InputDefinition:
    """A scenario change to a rate, in percentage points (the Phase 1 rule for rates)."""
    return InputDefinition(
        id=input_id,
        label=label,
        category=InputCategory.SCENARIO_INPUT,
        kind=InputKind.DECIMAL,
        description=description,
        unit=PERCENTAGE_POINTS,
        minimum=-RATE_CHANGE_LIMIT,
        maximum=RATE_CHANGE_LIMIT,
        max_decimals=4,
        required=False,
        default=ZERO,
        rationale="No change unless you enter one.",
        variable=variable,
        sensitivity=SensitivitySpec("absolute", D(step)),
    )


FX_SOURCE = ObservationSource(
    series_id="wb-ind-pa-nus-fcrf",
    label="World Bank: official exchange rate, INR per US$ (annual average)",
    unit="INR per USD",
    currency_pair=("INR", "USD"),
    caveat="An annual average of the official exchange rate, not a current market rate: "
    "movements within the year are smoothed out.",
)

ENTITY = InputDefinition(
    id="entity",
    label="Company in the knowledge graph",
    category=InputCategory.COMPANY_INPUT,
    kind=InputKind.GRAPH_NODE,
    description="Optional: the company in RUMIN's knowledge graph this run is about. "
    "RUMIN's sample companies are fictional; the figures you enter are what the model uses.",
    unit="graph_node",
    required=False,
)

REPORTING_CURRENCY = InputDefinition(
    id="reporting_currency",
    label="Reporting currency",
    category=InputCategory.COMPANY_INPUT,
    kind=InputKind.CURRENCY,
    description="The currency the company reports in (ISO 4217 code, e.g. INR).",
    unit="currency_code",
)

ANNUAL_REVENUE = InputDefinition(
    id="annual_revenue",
    label="Annual revenue",
    category=InputCategory.COMPANY_INPUT,
    kind=InputKind.DECIMAL,
    description="Annual revenue in the reporting currency, from the company's own accounts "
    "or plan. RUMIN holds no company financial data.",
    unit="currency_per_year",
    minimum=ZERO,
    minimum_exclusive=True,
    maximum=MAX_AMOUNT,
    max_decimals=6,
    sensitivity=SensitivitySpec("relative", D(10)),
)

ANNUAL_OPERATING_COSTS = InputDefinition(
    id="annual_operating_costs",
    label="Annual operating costs",
    category=InputCategory.COMPANY_INPUT,
    kind=InputKind.DECIMAL,
    description="Annual operating costs (everything above operating profit) in the reporting "
    "currency.",
    unit="currency_per_year",
    minimum=ZERO,
    minimum_exclusive=True,
    maximum=MAX_AMOUNT,
    max_decimals=6,
    sensitivity=SensitivitySpec("relative", D(10)),
)

FX_RATE = InputDefinition(
    id="fx_rate",
    label="Baseline exchange rate",
    category=InputCategory.MARKET_BASELINE,
    kind=InputKind.DECIMAL,
    description="Units of the reporting currency per US dollar at the baseline. Type your "
    "own figure, or use the latest value stored in RUMIN (with its source and period).",
    unit="currency_per_usd",
    minimum=ZERO,
    minimum_exclusive=True,
    maximum=D(100_000),
    max_decimals=6,
    variable=USD_INR,
    sources=(FX_SOURCE,),
    sensitivity=SensitivitySpec("relative", D(5)),
)

HORIZON = InputDefinition(
    id="horizon_months",
    label="Horizon",
    category=InputCategory.SETTING,
    kind=InputKind.INTEGER,
    description="How many months to simulate.",
    unit="months",
    minimum=D(1),
    maximum=D(36),
    max_decimals=0,
    required=False,
    default=D(12),
    rationale="Twelve months shows a full year after the change.",
)

SHOCK_START = InputDefinition(
    id="shock_start_month",
    label="Changes start in month",
    category=InputCategory.SETTING,
    kind=InputKind.INTEGER,
    description="The month of the horizon in which every scenario change takes effect "
    "(1 is the first month).",
    unit="months",
    minimum=D(1),
    maximum=D(36),
    max_decimals=0,
    required=False,
    default=D(1),
    rationale="The changes take effect in the first month unless you set a later one.",
)

SHOCK_DURATION = InputDefinition(
    id="shock_duration_months",
    label="Changes last for (months)",
    category=InputCategory.SETTING,
    kind=InputKind.INTEGER,
    description="How many months the changes last before the variables return to their "
    "baselines. 0 means they last until the end of the horizon.",
    unit="months",
    minimum=ZERO,
    maximum=D(36),
    max_decimals=0,
    required=False,
    default=ZERO,
    rationale="0: the changes last for the rest of the horizon (a permanent step).",
)

SHARED_INPUTS: dict[str, InputDefinition] = {
    item.id: item
    for item in (
        ENTITY,
        REPORTING_CURRENCY,
        ANNUAL_REVENUE,
        ANNUAL_OPERATING_COSTS,
        FX_RATE,
        HORIZON,
        SHOCK_START,
        SHOCK_DURATION,
    )
}


def months_assumption(item: str, label: str, maximum: int, rationale: str) -> InputDefinition:
    return InputDefinition(
        id=item,
        label=label,
        category=InputCategory.ASSUMPTION,
        kind=InputKind.INTEGER,
        description=f"{label}, in whole months.",
        unit="months",
        minimum=ZERO,
        maximum=D(maximum),
        max_decimals=0,
        required=False,
        default=ZERO,
        rationale=rationale,
        sensitivity=SensitivitySpec("absolute", D(2)),
    )


def percent_assumption(
    item: str,
    label: str,
    description: str,
    rationale: str,
    *,
    default: str = "0",
    maximum: str = "100",
    step: str = "25",
) -> InputDefinition:
    return InputDefinition(
        id=item,
        label=label,
        category=InputCategory.ASSUMPTION,
        kind=InputKind.DECIMAL,
        description=description,
        unit="percent",
        minimum=ZERO,
        maximum=D(maximum),
        max_decimals=2,
        required=False,
        default=D(default),
        rationale=rationale,
        sensitivity=SensitivitySpec("absolute", D(step)),
    )


TIMING_ASSUMPTION = Statement(
    "A4",
    "Scenario changes are step changes: they take effect in the start month and last for "
    "the stated duration (to the end of the horizon unless one is set), after which the "
    "changed variables return to their baselines. Every change in a run shares this timing.",
)

NOT_A_FORECAST = Statement(
    "L1",
    "The model shows the arithmetic consequence of the inputs and assumptions. It is not a "
    "forecast of what will happen, and not investment advice.",
)

MONTHLY_STEPS = Statement(
    "L6", "Monthly steps: timing within a month is ignored, and seasonality is not modelled."
)

START_WITHIN_HORIZON = ValidationRuleDefinition(
    "start_within_horizon",
    "The changes must take effect within the horizon.",
    "error",
)

NO_SHOCK = ValidationRuleDefinition(
    "no_shock",
    "A run in which every scenario change is zero is flagged: it equals the baseline.",
    "warning",
)


def timing_issues(values: ResolvedValues) -> list[Issue]:
    """The start month must fall inside the horizon."""
    start = values.integer("shock_start_month")
    horizon = values.integer("horizon_months")
    if start > horizon:
        return [
            Issue(
                "start_within_horizon",
                f"The changes start in month {start}, after the {horizon}-month horizon ends. "
                "Choose an earlier start or a longer horizon.",
                field="shock_start_month",
            )
        ]
    return []


def lag_issue(values: ResolvedValues, lag_input: str, what: str) -> Issue | None:
    """A warning when a lagged response starts only after the horizon."""
    start = values.integer("shock_start_month")
    horizon = values.integer("horizon_months")
    if start + values.integer(lag_input) > horizon:
        return Issue(
            "timing_within_horizon",
            f"{what} only after the horizon ends, so it does not appear in the results.",
            "warning",
            lag_input,
        )
    return None


def no_shock_issue(values: ResolvedValues, inputs: tuple[str, ...]) -> Issue | None:
    if all(values.number(name) == ZERO for name in inputs):
        return Issue(
            "no_shock",
            "Every scenario change is zero, so the scenario equals the baseline.",
            "warning",
        )
    return None


def amount(value: Decimal, currency: str) -> str:
    return f"{currency} {value:,.0f}"
