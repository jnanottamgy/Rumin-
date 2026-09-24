"""Floating-rate interest costs, version 1.0.0.

What a change in a policy rate does to the interest a company pays on floating-rate debt,
month by month, and so to its profit before tax and its interest coverage, holding
everything else constant: the amount of debt, fixed-rate debt and operating profit.

Two benchmarks are supported: the RBI policy repo rate (for rupee loans linked to it, such
as external-benchmark loans) and US short-term rates (the effective federal funds rate as
the graph's variable, for dollar loans). A policy-rate change is given in percentage points
(the Phase 1 rule for rates); it passes to the loans' rates by a stated share after a stated
repricing delay. The graph states which companies this matters for (the repo rate *affects
the financing of* Gridwell Power and Trakvel Logistics; US rates, of Lumeric Chemicals);
the amounts come from the user. RUMIN holds no company financial data and invents none.
"""

from __future__ import annotations

from decimal import Decimal

from app.simulation.decimal_math import MONTHS_PER_YEAR, ZERO, NumericalError, arithmetic
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
    FED_FUNDS,
    HORIZON,
    MAX_AMOUNT,
    MONTHLY_STEPS,
    NO_SHOCK,
    NOT_A_FORECAST,
    REPO_RATE,
    REPORTING_CURRENCY,
    SHOCK_DURATION,
    SHOCK_START,
    START_WITHIN_HORIZON,
    TIMING_ASSUMPTION,
    TIMING_TEXT,
    lag_issue,
    months_assumption,
    no_shock_issue,
    percent_assumption,
    rate_shock,
    timing_issues,
)
from app.simulation.runtime import ComputeContext, Issue, ModelResult, ResolvedValues

MODEL_ID = "floating_rate_interest"
VERSION = "1.0.0"

D = Decimal
TEN_THOUSAND = D(10_000)  # percent × percentage points → fraction


def _amount(input_id: str, label: str, description: str, unit: str) -> InputDefinition:
    return InputDefinition(
        id=input_id,
        label=label,
        category=InputCategory.COMPANY_INPUT,
        kind=InputKind.DECIMAL,
        description=description,
        unit=unit,
        minimum=ZERO,
        maximum=MAX_AMOUNT,
        max_decimals=6,
        sensitivity=SensitivitySpec("relative", D(10)),
    )


INPUTS: tuple[InputDefinition, ...] = (
    rate_shock(
        "repo_rate_change",
        "RBI repo rate change",
        "Change in the RBI policy repo rate, in percentage points (0.25 = 25 basis points). "
        f"{TIMING_TEXT}",
        REPO_RATE,
        "0.25",
    ),
    rate_shock(
        "us_rate_change",
        "US short-term rate change",
        "Change in US short-term rates (the effective federal funds rate), in percentage "
        f"points. {TIMING_TEXT}",
        FED_FUNDS,
        "0.25",
    ),
    ENTITY,
    REPORTING_CURRENCY,
    ANNUAL_REVENUE,
    ANNUAL_OPERATING_COSTS,
    _amount(
        "annual_interest_expense",
        "Annual interest expense",
        "Interest on all debt, fixed and floating, per year at today's rates, in the "
        "reporting currency.",
        "currency_per_year",
    ),
    _amount(
        "repo_linked_debt",
        "Debt linked to the repo rate",
        "Floating-rate debt whose rate is reset from the RBI repo rate (for example "
        "external-benchmark loans), outstanding, in the reporting currency (0 if none).",
        "currency",
    ),
    _amount(
        "us_rate_linked_debt",
        "Debt linked to US short-term rates",
        "Floating-rate debt whose rate is reset from US short-term rates, outstanding, "
        "stated in the reporting currency at today's exchange rate (0 if none).",
        "currency",
    ),
    percent_assumption(
        "repo_pass_through",
        "Repo pass-through",
        "The share of a repo-rate change that reaches the loans' rates, in percent.",
        "100: loans linked to the repo rate reprice one-for-one. Enter less if the spread "
        "absorbs part of the change.",
        default="100",
        maximum="200",
    ),
    months_assumption(
        "repo_repricing_lag",
        "Repo repricing delay",
        12,
        "0: the loans reprice in the month the rate changes. Enter your loans' reset delay "
        "(for example 3 months).",
    ),
    percent_assumption(
        "us_pass_through",
        "US-rate pass-through",
        "The share of a US-rate change that reaches the loans' rates, in percent.",
        "100: loans linked to US rates reprice one-for-one. Enter less if the spread absorbs "
        "part of the change.",
        default="100",
        maximum="200",
    ),
    months_assumption(
        "us_repricing_lag",
        "US-rate repricing delay",
        12,
        "0: the loans reprice in the month the rate changes. Enter your loans' reset delay.",
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
        "Benchmark change in effect",
        "Δk(m) = Δk · 𝟙[S ≤ m ≤ E]",
        _t("Δk(m)", "change in the benchmark rate in effect in month m", "percentage points"),
        (
            _t("Δk", "scenario change in the benchmark rate", "percentage points"),
            _t("S", "the month the change takes effect", "months"),
            _t("E", "the last month it lasts", "months"),
        ),
        "Applied by the transmission engine at the benchmark's own node (a change in "
        "percentage points is never carried along a log-linear relationship).",
        "monthly",
        assumptions=("A4",),
    ),
    EquationDefinition(
        "E2",
        "Change in interest on repo-linked debt",
        "ΔI_r(m) = D_r × p_r × Δk_r(m − L_r) / 10 000 / 12",
        _t("ΔI_r(m)", "change in interest on repo-linked debt in month m", CUR_MONTH),
        (
            _t("D_r", "debt linked to the repo rate", CUR),
            _t("p_r", "repo pass-through", "percent"),
            _t("Δk_r", "repo-rate change in effect", "percentage points"),
            _t("L_r", "repricing delay", "months"),
        ),
        "The loans' rate moves by p_r % of the benchmark change L_r months later. "
        "Percent × percentage points ÷ 10,000 is the change as a fraction; ÷ 12 is one "
        "month's interest.",
        "monthly",
        assumptions=("A1", "A2", "A3"),
        limitations=("L4",),
    ),
    EquationDefinition(
        "E3",
        "Change in interest on US-rate-linked debt",
        "ΔI_u(m) = D_u × p_u × Δk_u(m − L_u) / 10 000 / 12",
        _t("ΔI_u(m)", "change in interest on US-rate-linked debt in month m", CUR_MONTH),
        (
            _t("D_u", "debt linked to US short-term rates", CUR),
            _t("p_u", "US-rate pass-through", "percent"),
            _t("Δk_u", "US-rate change in effect", "percentage points"),
            _t("L_u", "repricing delay", "months"),
        ),
        "As E2, for debt linked to US short-term rates.",
        "monthly",
        assumptions=("A1", "A2", "A3", "A5"),
        limitations=("L4",),
    ),
    EquationDefinition(
        "E4",
        "Change in interest expense",
        "ΔI(m) = ΔI_r(m) + ΔI_u(m); ΣΔI = Σₘ ΔI(m), m = 1…H",
        _t("ΣΔI", "change in interest expense over the horizon", CUR),
        (
            _t("ΔI_r(m)", "change in interest on repo-linked debt", CUR_MONTH),
            _t("ΔI_u(m)", "change in interest on US-rate-linked debt", CUR_MONTH),
            _t("H", "horizon", "months"),
        ),
        "Monthly changes, summed over the horizon.",
        "horizon",
    ),
    EquationDefinition(
        "E5",
        "Profit before tax over the horizon",
        "P₀ = (R − O − I) × H / 12; ΔP = −ΣΔI; P₁ = P₀ + ΔP",
        _t("ΔP", "change in profit before tax over the horizon", CUR),
        (
            _t("R", "annual revenue", CUR_YEAR),
            _t("O", "annual operating costs", CUR_YEAR),
            _t("I", "annual interest expense", CUR_YEAR),
            _t("ΣΔI", "change in interest expense over the horizon", CUR),
        ),
        "Operating profit less interest, before and after the scenario. Operating profit "
        "itself does not change in this model.",
        "horizon",
        assumptions=("A1", "A2"),
        limitations=("L3",),
    ),
    EquationDefinition(
        "E6",
        "Interest coverage",
        "κ₀ = (R − O) / I; κ₁ = (R − O) × H / 12 / (I × H / 12 + ΣΔI)",
        _t("κ₁", "operating profit ÷ interest over the horizon, under the scenario", "times"),
        (
            _t("R − O", "annual operating profit", CUR_YEAR),
            _t("I", "annual interest expense", CUR_YEAR),
            _t("ΣΔI", "change in interest expense over the horizon", CUR),
        ),
        "How many times operating profit covers interest, before and after the scenario.",
        "horizon",
    ),
    EquationDefinition(
        "E7",
        "Run-rate annual interest change",
        "ΔI* = (D_r × p_r × Δk_r + D_u × p_u × Δk_u) / 10 000",
        _t("ΔI*", "annual change in interest once every loan has repriced", CUR_YEAR),
        (
            _t("D_r, D_u", "floating-rate debt by benchmark", CUR),
            _t("p_r, p_u", "pass-through", "percent"),
            _t("Δk_r, Δk_u", "benchmark changes", "percentage points"),
        ),
        "The yearly change while the changes last, once every loan has repriced.",
        "steady_state",
        assumptions=("A2",),
    ),
)

CURRENCY = "currency"

OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "floating_rate_debt",
        "Floating-rate debt",
        CURRENCY,
        "derived",
        "Debt linked to the repo rate plus debt linked to US short-term rates.",
        "E4",
    ),
    OutputDefinition(
        "baseline_interest_expense",
        "Baseline interest expense (horizon)",
        CURRENCY,
        "derived",
        "Interest over the horizon at today's rates.",
        "E5",
    ),
    OutputDefinition(
        "baseline_profit_before_tax",
        "Baseline profit before tax (horizon)",
        CURRENCY,
        "derived",
        "Operating profit less interest over the horizon, with no change.",
        "E5",
    ),
    OutputDefinition(
        "baseline_interest_coverage",
        "Baseline interest coverage",
        "times",
        "derived",
        "Operating profit ÷ interest, with no change.",
        "E6",
    ),
    OutputDefinition(
        "repo_interest_change",
        "Change in interest on repo-linked debt (horizon)",
        CURRENCY,
        "simulated",
        "Extra interest over the horizon on debt linked to the repo rate.",
        "E4",
        attributable=True,
    ),
    OutputDefinition(
        "us_interest_change",
        "Change in interest on US-rate-linked debt (horizon)",
        CURRENCY,
        "simulated",
        "Extra interest over the horizon on debt linked to US short-term rates.",
        "E4",
        attributable=True,
    ),
    OutputDefinition(
        "interest_expense_change",
        "Change in interest expense (horizon)",
        CURRENCY,
        "simulated",
        "Extra interest over the horizon. Positive means more interest is paid.",
        "E4",
        attributable=True,
    ),
    OutputDefinition(
        "profit_before_tax_change",
        "Change in profit before tax (horizon)",
        CURRENCY,
        "simulated",
        "Minus the change in interest expense, over the horizon.",
        "E5",
        attributable=True,
    ),
    OutputDefinition(
        "scenario_profit_before_tax",
        "Scenario profit before tax (horizon)",
        CURRENCY,
        "simulated",
        "Baseline profit before tax plus the change, over the horizon.",
        "E5",
    ),
    OutputDefinition(
        "scenario_interest_coverage",
        "Scenario interest coverage",
        "times",
        "simulated",
        "Operating profit ÷ interest over the horizon, under the scenario.",
        "E6",
    ),
    OutputDefinition(
        "interest_coverage_change",
        "Change in interest coverage",
        "times",
        "simulated",
        "Scenario coverage minus baseline coverage.",
        "E6",
        attributable=True,
    ),
    OutputDefinition(
        "run_rate_interest_change",
        "Run-rate annual interest change",
        "currency_per_year",
        "simulated",
        "The yearly change in interest once every loan has repriced, while the changes last.",
        "E7",
        attributable=True,
    ),
)

MONTHLY_OUTPUTS: tuple[OutputDefinition, ...] = (
    OutputDefinition(
        "repo_rate_change_in_effect",
        "Repo-rate change in effect",
        "percentage_points",
        "simulated",
        "Δk_r(m): the benchmark change in force in the month.",
        "E1",
    ),
    OutputDefinition(
        "us_rate_change_in_effect",
        "US-rate change in effect",
        "percentage_points",
        "simulated",
        "Δk_u(m): the benchmark change in force in the month.",
        "E1",
    ),
    OutputDefinition(
        "repo_interest_change",
        "Change in interest on repo-linked debt",
        "currency_per_month",
        "simulated",
        "ΔI_r(m).",
        "E2",
    ),
    OutputDefinition(
        "us_interest_change",
        "Change in interest on US-rate-linked debt",
        "currency_per_month",
        "simulated",
        "ΔI_u(m).",
        "E3",
    ),
    OutputDefinition(
        "interest_expense_change",
        "Change in interest expense",
        "currency_per_month",
        "simulated",
        "ΔI(m) = ΔI_r(m) + ΔI_u(m).",
        "E4",
    ),
    OutputDefinition(
        "profit_before_tax_change",
        "Change in profit before tax",
        "currency_per_month",
        "simulated",
        "−ΔI(m).",
        "E5",
    ),
)

ASSUMPTIONS: tuple[Statement, ...] = (
    Statement(
        "A1",
        "Everything the model does not include stays at its baseline: the amount of debt (no "
        "repayments or new borrowing), fixed-rate debt, operating profit and other income.",
    ),
    Statement(
        "A2",
        "Floating-rate loans reprice by the stated share of the benchmark change after the "
        "stated delay, then keep that rate while the change lasts. Interest accrues evenly: "
        "each month carries one twelfth of the annual rate.",
    ),
    Statement(
        "A3",
        "The benchmark change is taken as given. RUMIN does not predict policy rates.",
    ),
    TIMING_ASSUMPTION,
    Statement(
        "A5",
        "Debt linked to US rates is stated in the reporting currency at today's exchange "
        "rate; exchange-rate movements on it are not modelled here.",
    ),
)

LIMITATIONS: tuple[Statement, ...] = (
    NOT_A_FORECAST,
    Statement(
        "L2",
        "No refinancing, repayment, covenant, credit-spread or rating effects, and no "
        "change in deposits or interest income.",
    ),
    Statement("L3", "Before tax: the tax deductibility of interest is not modelled."),
    Statement(
        "L4",
        "The pass-through shares and repricing delays are assumptions with neutral defaults. "
        "None is estimated in RUMIN.",
    ),
    Statement("L5", "Two benchmarks only: the RBI repo rate and US short-term rates."),
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
        "rate_change_limits",
        "Rate changes are in percentage points, between −25 and +25, with at most 4 "
        "decimals — the limits Phase 1 publishes for rates.",
        "error",
    ),
    ValidationRuleDefinition(
        "has_floating_debt",
        "At least one of the floating-rate debt amounts must be above zero.",
        "error",
    ),
    ValidationRuleDefinition(
        "interest_positive",
        "Interest expense must be above zero when floating-rate debt is stated.",
        "error",
    ),
    ValidationRuleDefinition(
        "operating_profit_positive",
        "Interest coverage is only meaningful with a positive operating profit; a loss is flagged.",
        "warning",
    ),
    START_WITHIN_HORIZON,
    ValidationRuleDefinition(
        "timing_within_horizon",
        "Repricing that happens only after the horizon is flagged.",
        "warning",
    ),
    NO_SHOCK,
)

SUPPORTING: tuple[SupportingRelationship, ...] = (
    SupportingRelationship(
        "S1",
        "affects_financing",
        REPO_RATE,
        "{entity}",
        "The repo rate affects the chosen company's financing costs (E2). Cited, not propagated.",
    ),
    SupportingRelationship(
        "S2",
        "affects_financing",
        FED_FUNDS,
        "{entity}",
        "US short-term rates affect the chosen company's financing costs (E3). Cited, not "
        "propagated.",
    ),
)

REFERENCES: tuple[Statement, ...] = (
    Statement(
        "V1",
        "Variables: the RBI policy repo rate and the U.S. effective federal funds rate "
        "(percent per annum) are defined in RUMIN's reference data, with their publishers. "
        "RUMIN stores no values for them.",
    ),
    Statement(
        "R1",
        "Rates are changed in percentage points, never in percent of the rate: +10 % of a "
        "6.5 % rate would be ambiguous (the Phase 1 scenario rule).",
    ),
)

DEFINITION = ModelDefinition(
    id=MODEL_ID,
    version=VERSION,
    name="Floating-rate interest costs",
    summary="What a change in the repo rate or US short-term rates does to interest on "
    "floating-rate debt, profit before tax and interest coverage, month by month.",
    description="A deterministic, monthly model of one company's floating-rate debt. A "
    "benchmark change, in percentage points, reaches each loan's rate by a stated share after "
    "a stated repricing delay; interest changes by the debt × that rate change ÷ 12 each "
    "month. The change takes effect in the start month and lasts for the stated duration. "
    "Operating profit and everything else stay at their baselines.",
    domain="Interest rates · corporate finance",
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
        PathwayLink("input:repo_rate_change", REPO_RATE, "changes", ("E1",)),
        PathwayLink("input:us_rate_change", FED_FUNDS, "changes", ("E1",)),
        PathwayLink(
            REPO_RATE, "output:repo_interest_change", "reprices repo-linked loans", ("E2",)
        ),
        PathwayLink(
            FED_FUNDS, "output:us_interest_change", "reprices US-rate-linked loans", ("E3",)
        ),
        PathwayLink(
            "input:repo_pass_through", "output:repo_interest_change", "sets the share", ("E2",)
        ),
        PathwayLink(
            "output:repo_interest_change", "output:interest_expense_change", "adds", ("E4",)
        ),
        PathwayLink("output:us_interest_change", "output:interest_expense_change", "adds", ("E4",)),
        PathwayLink(
            "output:interest_expense_change", "output:profit_before_tax_change", "reduces", ("E5",)
        ),
    ),
    bridge=(
        BridgeItem("repo_interest_change", -1, "Interest on repo-linked debt"),
        BridgeItem("us_interest_change", -1, "Interest on US-rate-linked debt"),
    ),
    bridge_total="profit_before_tax_change",
    headline_outputs=(
        "interest_expense_change",
        "profit_before_tax_change",
        "interest_coverage_change",
        "run_rate_interest_change",
    ),
    sensitivity_defaults=(
        "repo_rate_change",
        "us_rate_change",
        "repo_pass_through",
        "repo_repricing_lag",
        "repo_linked_debt",
        "us_rate_linked_debt",
    ),
    sensitivity_metric="profit_before_tax_change",
    shock_start_input="shock_start_month",
    shock_duration_input="shock_duration_months",
)


# --- Checks ------------------------------------------------------------------------------------


def check(values: ResolvedValues) -> list[Issue]:
    issues: list[Issue] = []
    repo_debt = values.number("repo_linked_debt")
    us_debt = values.number("us_rate_linked_debt")
    if repo_debt == ZERO and us_debt == ZERO:
        issues.append(
            Issue(
                "has_floating_debt",
                "Both floating-rate debt amounts are zero, so no interest reprices.",
                field="repo_linked_debt",
            )
        )
    elif values.number("annual_interest_expense") == ZERO:
        issues.append(
            Issue(
                "interest_positive",
                "Floating-rate debt is stated but interest expense is zero. Enter the interest "
                "the company pays per year at today's rates.",
                field="annual_interest_expense",
            )
        )
    if values.number("annual_revenue") <= values.number("annual_operating_costs"):
        issues.append(
            Issue(
                "operating_profit_positive",
                "Operating costs are at or above revenue, so operating profit is zero or "
                "negative and interest coverage is not meaningful.",
                "warning",
                "annual_operating_costs",
            )
        )
    for change, debt, lag, what in (
        ("repo_rate_change", repo_debt, "repo_repricing_lag", "Repo-linked loans reprice"),
        ("us_rate_change", us_debt, "us_repricing_lag", "US-rate-linked loans reprice"),
    ):
        if values.number(change) != ZERO and debt > ZERO:
            issue = lag_issue(values, lag, what)
            if issue:
                issues.append(issue)
    issues.extend(timing_issues(values))
    issue = no_shock_issue(values, ("repo_rate_change", "us_rate_change"))
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
        revenue = values.number("annual_revenue")
        costs = values.number("annual_operating_costs")
        interest = values.number("annual_interest_expense")
        repo_debt = values.number("repo_linked_debt")
        us_debt = values.number("us_rate_linked_debt")
        repo_share = values.number("repo_pass_through")
        us_share = values.number("us_pass_through")
        repo_lag = values.integer("repo_repricing_lag")
        us_lag = values.integer("us_repricing_lag")
        start = values.integer("shock_start_month")
        duration = values.integer("shock_duration_months")
        end = start + duration - 1 if duration > 0 else horizon

        months: dict[str, list[Decimal]] = {
            name: []
            for name in (
                "repo_rate_change_in_effect",
                "us_rate_change_in_effect",
                "repo_interest_change",
                "us_interest_change",
                "interest_expense_change",
                "profit_before_tax_change",
            )
        }

        def in_effect(node: str, month: int) -> Decimal:
            return context.propagation.at(node, month) if month >= 1 else ZERO

        for month in range(1, horizon + 1):
            repo_now = record(
                "E1",
                "Repo-rate change in effect",
                ("Δk_r", in_effect(REPO_RATE, month), "percentage points"),
                [
                    ("Δk_r", values.number("repo_rate_change"), "percentage points"),
                    ("S", Decimal(start), "months"),
                    ("E", Decimal(end), "months"),
                ],
                month=month,
            )
            us_now = record(
                "E1",
                "US-rate change in effect",
                ("Δk_u", in_effect(FED_FUNDS, month), "percentage points"),
                [
                    ("Δk_u", values.number("us_rate_change"), "percentage points"),
                    ("S", Decimal(start), "months"),
                    ("E", Decimal(end), "months"),
                ],
                month=month,
            )
            repo_repriced = in_effect(REPO_RATE, month - repo_lag)
            us_repriced = in_effect(FED_FUNDS, month - us_lag)
            repo_delta = record(
                "E2",
                "Change in interest on repo-linked debt",
                (
                    "ΔI_r",
                    repo_debt * repo_share * repo_repriced / TEN_THOUSAND / MONTHS_PER_YEAR,
                    per_month,
                ),
                [
                    ("D_r", repo_debt, currency),
                    ("p_r", repo_share, "percent"),
                    ("Δk_r(m − L_r)", repo_repriced, "percentage points"),
                    ("L_r", Decimal(repo_lag), "months"),
                ],
                month=month,
            )
            us_delta = record(
                "E3",
                "Change in interest on US-rate-linked debt",
                (
                    "ΔI_u",
                    us_debt * us_share * us_repriced / TEN_THOUSAND / MONTHS_PER_YEAR,
                    per_month,
                ),
                [
                    ("D_u", us_debt, currency),
                    ("p_u", us_share, "percent"),
                    ("Δk_u(m − L_u)", us_repriced, "percentage points"),
                    ("L_u", Decimal(us_lag), "months"),
                ],
                month=month,
            )
            total = record(
                "E4",
                "Change in interest expense",
                ("ΔI", repo_delta + us_delta, per_month),
                [("ΔI_r", repo_delta, per_month), ("ΔI_u", us_delta, per_month)],
                month=month,
            )
            months["repo_rate_change_in_effect"].append(repo_now)
            months["us_rate_change_in_effect"].append(us_now)
            months["repo_interest_change"].append(repo_delta)
            months["us_interest_change"].append(us_delta)
            months["interest_expense_change"].append(total)
            months["profit_before_tax_change"].append(-total)

        months_d = Decimal(horizon)
        repo_total = sum(months["repo_interest_change"], ZERO)
        us_total = sum(months["us_interest_change"], ZERO)
        interest_total = record(
            "E4",
            "Change in interest expense over the horizon",
            ("ΣΔI", repo_total + us_total, currency),
            [
                ("ΣΔI_r", repo_total, currency),
                ("ΣΔI_u", us_total, currency),
                ("H", months_d, "months"),
            ],
        )
        floating = record(
            "E4",
            "Floating-rate debt",
            ("D_r + D_u", repo_debt + us_debt, currency),
            [("D_r", repo_debt, currency), ("D_u", us_debt, currency)],
        )
        base_interest = record(
            "E5",
            "Baseline interest over the horizon",
            ("I·H/12", interest * months_d / MONTHS_PER_YEAR, currency),
            [("I", interest, per_year), ("H", months_d, "months")],
        )
        base_pbt = record(
            "E5",
            "Baseline profit before tax over the horizon",
            ("P₀", (revenue - costs - interest) * months_d / MONTHS_PER_YEAR, currency),
            [
                ("R", revenue, per_year),
                ("O", costs, per_year),
                ("I", interest, per_year),
                ("H", months_d, "months"),
            ],
        )
        pbt_change = record(
            "E5",
            "Change in profit before tax over the horizon",
            ("ΔP", -interest_total, currency),
            [("ΣΔI", interest_total, currency)],
        )
        scenario_pbt = record(
            "E5",
            "Scenario profit before tax over the horizon",
            ("P₁", base_pbt + pbt_change, currency),
            [("P₀", base_pbt, currency), ("ΔP", pbt_change, currency)],
        )
        if interest == ZERO:
            raise NumericalError(
                "Interest expense is zero, so interest coverage is undefined.",
                code="interest_positive",
            )
        operating = revenue - costs
        base_coverage = record(
            "E6",
            "Baseline interest coverage",
            ("κ₀", operating / interest, "times"),
            [("R − O", operating, per_year), ("I", interest, per_year)],
        )
        scenario_interest = base_interest + interest_total
        if scenario_interest <= ZERO:
            raise NumericalError(
                "Interest over the horizon would fall to zero or below; interest coverage is "
                "undefined. Check the rate changes and the pass-through.",
                code="interest_positive",
            )
        scenario_coverage = record(
            "E6",
            "Scenario interest coverage",
            ("κ₁", operating * months_d / MONTHS_PER_YEAR / scenario_interest, "times"),
            [
                ("(R − O)·H/12", operating * months_d / MONTHS_PER_YEAR, currency),
                ("I·H/12 + ΣΔI", scenario_interest, currency),
            ],
        )
        run_rate = record(
            "E7",
            "Run-rate annual interest change",
            (
                "ΔI*",
                (
                    repo_debt * repo_share * context.propagation.final(REPO_RATE)
                    + us_debt * us_share * context.propagation.final(FED_FUNDS)
                )
                / TEN_THOUSAND,
                per_year,
            ),
            [
                ("D_r", repo_debt, currency),
                ("p_r", repo_share, "percent"),
                ("Δk_r", context.propagation.final(REPO_RATE), "percentage points"),
                ("D_u", us_debt, currency),
                ("p_u", us_share, "percent"),
                ("Δk_u", context.propagation.final(FED_FUNDS), "percentage points"),
            ],
        )
        coverage_change = scenario_coverage - base_coverage

    result.scalars.update(
        floating_rate_debt=floating,
        baseline_interest_expense=base_interest,
        baseline_profit_before_tax=base_pbt,
        baseline_interest_coverage=base_coverage,
        repo_interest_change=repo_total,
        us_interest_change=us_total,
        interest_expense_change=interest_total,
        profit_before_tax_change=pbt_change,
        scenario_profit_before_tax=scenario_pbt,
        scenario_interest_coverage=scenario_coverage,
        interest_coverage_change=coverage_change,
        run_rate_interest_change=run_rate,
    )
    result.monthly.update(months)
    result.units.update(
        floating_rate_debt=currency,
        baseline_interest_expense=currency,
        baseline_profit_before_tax=currency,
        baseline_interest_coverage="times",
        repo_interest_change=currency,
        us_interest_change=currency,
        interest_expense_change=currency,
        profit_before_tax_change=currency,
        scenario_profit_before_tax=currency,
        scenario_interest_coverage="times",
        interest_coverage_change="times",
        run_rate_interest_change=per_year,
    )
    result.monthly_units.update(
        repo_rate_change_in_effect="percentage points",
        us_rate_change_in_effect="percentage points",
        repo_interest_change=per_month,
        us_interest_change=per_month,
        interest_expense_change=per_month,
        profit_before_tax_change=per_month,
    )
    return result
