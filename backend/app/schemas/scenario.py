"""Scenario Lab request and response schemas (Phase 5; scenarios since Phase 1).

Request schemas validate *shape* (types, lengths, patterns). Domain rules that need the
database or the models — does the variable exist, is this kind of change allowed for it,
is this an input of that model — are checked in ``app.scenario_lab.validation``; whether a
scenario can be *executed* is its plan.

Numbers in requests are exact decimal strings (``"2.35"``) or JSON numbers, read through
their shortest form. Numbers in responses are exact decimal strings in plain notation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt, StringConstraints

from app.domain.enums import ChangeType, EpistemicCategory, ScenarioExecutionStatus, ScenarioStatus
from app.domain.scenario_rules import MAX_SHOCKS_PER_SCENARIO
from app.schemas.common import ApiModel, DecimalString, EntityId, InputModel, Page, SafeText
from app.schemas.simulation import (
    BridgeRead,
    GraphSnapshotRead,
    InputId,
    NumberInput,
    ResolvedInputRead,
    SimulationInputValue,
    SimulationIssueRead,
    SimulationObservationRead,
    StatementRead,
    StepValueRead,
    TransmissionPathRead,
)
from app.simulation.definitions import MODEL_ID_PATTERN

TEMPLATE_ID = r"^[a-z][a-z0-9_]{2,63}$"
COMPANY_KEY = r"^company:[a-z0-9_]{2,120}$"
TARGET_ID = (
    r"^(change:[a-z]{2,4}_[a-z0-9_]{2,59}|shared:[a-z_]{2,40}"
    r"|model:[a-z][a-z0-9_]{2,63}:[a-z][a-z0-9_]{1,63})$"
)
METRIC_ID = r"^[a-z_]{2,40}$"

ModelId = Annotated[str, StringConstraints(pattern=MODEL_ID_PATTERN.pattern)]
TemplateId = Annotated[str, StringConstraints(pattern=TEMPLATE_ID)]
MonthInput = Annotated[StrictInt, Field(ge=1, le=36)]
Severity = Literal["error", "warning"]
ExecutionStatus = ScenarioExecutionStatus

# --- Requests -----------------------------------------------------------------------------------


class ShockInput(InputModel):
    variable_id: EntityId = Field(examples=["var_brent_crude"])
    change_type: ChangeType
    value: NumberInput = Field(
        description="An exact decimal string or a JSON number. Percent for `percent_change` "
        "(30 = +30 %); the variable's unit for `absolute_change` (percentage points for "
        "rates). At most 4 decimal places.",
        examples=["20"],
    )
    note: SafeText = Field(default="", max_length=500)


class TimingInput(InputModel):
    start_month: MonthInput = Field(default=1, description="The month the changes take effect.")
    duration_months: StrictInt = Field(
        default=0, ge=0, le=36, description="How many months they last; 0 = to the horizon."
    )
    horizon_months: MonthInput = Field(default=12, description="Months simulated.")


class CompanyInput(InputModel):
    reporting_currency: str | None = Field(
        default=None, pattern=r"^[A-Z]{3}$", examples=["INR"], description="ISO 4217 code."
    )
    annual_revenue: NumberInput | None = Field(
        default=None, description="Per year, in the reporting currency.", examples=["300000000"]
    )
    annual_operating_costs: NumberInput | None = Field(
        default=None, description="Per year, in the reporting currency.", examples=["250000000"]
    )


class MarketsInput(InputModel):
    fx_rate: SimulationInputValue | None = Field(
        default=None,
        description="The exchange rate (reporting currency per US dollar) every model that "
        "needs it uses: a typed value, or `source: stored_observation` for the latest stored "
        "World Bank annual average.",
    )


class ModelSettingsInput(InputModel):
    mode: Literal["auto", "include", "exclude"] = Field(
        default="auto",
        description="`auto`: included when a company is chosen and the knowledge graph states "
        "its exposure. `include` / `exclude`: your choice.",
    )
    inputs: dict[InputId, SimulationInputValue] = Field(
        default_factory=dict, max_length=20, description="The model's own figures."
    )
    assumptions: dict[InputId, NumberInput] = Field(
        default_factory=dict,
        max_length=20,
        description="The model's assumptions; omitted ones take the stated default.",
    )


class ConstraintsInput(InputModel):
    evidence: Literal["any", "evidence_backed"] = Field(
        default="any",
        description="`evidence_backed`: rely only on knowledge-graph relationships backed by "
        "evidence (transmission and exposure).",
    )
    stored_market_data: bool = Field(
        default=False, description="Market baselines must be stored observations, not typed."
    )


class StressCaseInput(InputModel):
    name: SafeText = Field(min_length=1, max_length=60, examples=["Stress"])
    scale: NumberInput | None = Field(
        default=None, description="Every change × this multiple (above 0, at most 10)."
    )
    changes: dict[EntityId, NumberInput] = Field(
        default_factory=dict,
        max_length=MAX_SHOCKS_PER_SCENARIO,
        description="Explicit values for some of the scenario's changes, by variable.",
    )


class ScenarioInput(InputModel):
    """A scenario version's content: the body of POST, PUT and the plan and preview."""

    name: SafeText = Field(min_length=1, max_length=120, examples=["Oil price shock"])
    description: SafeText = Field(default="", max_length=2000)
    template_id: TemplateId | None = None
    shocks: list[ShockInput] = Field(min_length=1, max_length=MAX_SHOCKS_PER_SCENARIO)
    entity: str | None = Field(
        default=None,
        pattern=COMPANY_KEY,
        max_length=128,
        description="A company in the knowledge graph.",
        examples=["company:co_aerisca_airways"],
    )
    timing: TimingInput = Field(default_factory=TimingInput)
    company: CompanyInput = Field(default_factory=CompanyInput)
    markets: MarketsInput = Field(default_factory=MarketsInput)
    models: dict[ModelId, ModelSettingsInput] = Field(default_factory=dict, max_length=10)
    constraints: ConstraintsInput = Field(default_factory=ConstraintsInput)
    stress_cases: list[StressCaseInput] = Field(default_factory=list, max_length=5)
    note: SafeText = Field(default="", max_length=500, description="What this version changes.")


class ScenarioUpdate(ScenarioInput):
    base_version: StrictInt | None = Field(
        default=None,
        ge=1,
        description="The version this edit started from; if a newer version was saved since, "
        "the save is refused (409) instead of overwriting it.",
    )


class ScenarioDuplicateRequest(InputModel):
    name: SafeText | None = Field(default=None, min_length=1, max_length=120)
    version: StrictInt | None = Field(default=None, ge=1, description="Default: the latest.")


class ExecutionRequest(InputModel):
    version: StrictInt | None = Field(default=None, ge=1, description="Default: the latest.")


class LabSensitivityItemInput(InputModel):
    target: str = Field(
        pattern=TARGET_ID,
        description="`change:<variable>`, `shared:<input>` or `model:<model>:<input>`.",
        examples=["change:var_brent_crude"],
    )
    mode: Literal["default", "absolute", "relative", "values"] = "default"
    step: NumberInput | None = None
    values: list[NumberInput] = Field(default_factory=list, max_length=7)


class LabSensitivityRequest(InputModel):
    metric: str | None = Field(
        default=None,
        pattern=METRIC_ID,
        description="A line (its change) or a metric (its scenario value). Default: profit "
        "before tax when interest is modelled, otherwise operating profit.",
    )
    inputs: list[LabSensitivityItemInput] = Field(default_factory=list, max_length=8)


# --- Scenarios and versions ---------------------------------------------------------------------


class ShockRead(ApiModel):
    variable_id: str
    change_type: ChangeType
    value: DecimalString
    note: str
    epistemic_category: Literal[EpistemicCategory.SCENARIO_INPUT] = EpistemicCategory.SCENARIO_INPUT


class ValueRead(ApiModel):
    value: str | None
    unit: str | None
    source: Literal["user", "stored_observation"] | None
    series_id: str | None


class ModelSettingsRead(ApiModel):
    mode: Literal["auto", "include", "exclude"]
    inputs: dict[str, ValueRead]
    assumptions: dict[str, str]


class TimingRead(ApiModel):
    start_month: int
    duration_months: int
    horizon_months: int


class ScenarioCompanyRead(ApiModel):
    reporting_currency: str | None
    annual_revenue: str | None
    annual_operating_costs: str | None


class MarketsRead(ApiModel):
    fx_rate: ValueRead | None


class ConstraintsRead(ApiModel):
    evidence: Literal["any", "evidence_backed"]
    stored_market_data: bool


class StressCaseRead(ApiModel):
    name: str
    scale: str | None
    changes: dict[str, str]


class ScenarioSpecRead(ApiModel):
    entity: str | None
    timing: TimingRead
    company: ScenarioCompanyRead
    markets: MarketsRead
    models: dict[str, ModelSettingsRead]
    constraints: ConstraintsRead
    stress_cases: list[StressCaseRead]


class DerivedFromRead(ApiModel):
    kind: Literal["duplicate", "restore"]
    scenario_id: uuid.UUID
    version: int


class VersionSummaryRead(ApiModel):
    version: int
    name: str
    spec_hash: str
    note: str
    derived_from: DerivedFromRead | None
    created_at: datetime
    executions: int


class VersionRead(VersionSummaryRead):
    scenario_id: uuid.UUID
    description: str
    template_id: str | None
    shocks: list[ShockRead]
    spec: ScenarioSpecRead


class HeadlineRead(ApiModel):
    id: str
    label: str
    change: DecimalString
    percent_change: DecimalString | None
    currency: str


class ExecutionErrorRead(ApiModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionSummaryRead(ApiModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    version: int
    status: ExecutionStatus
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    inputs_hash: str | None
    result_hash: str | None
    headline: list[HeadlineRead]
    models: list[str]
    error: ExecutionErrorRead | None


class ScenarioRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    status: ScenarioStatus
    template_id: str | None
    current_version: int
    shocks: list[ShockRead] = Field(description="The latest version's changes.")
    spec: ScenarioSpecRead = Field(description="The latest version's content.")
    versions: list[VersionSummaryRead]
    latest_execution: ExecutionSummaryRead | None = Field(
        description="The most recent execution of any version, or null if none: RUMIN never "
        "shows results that were not computed."
    )
    executions: int
    created_at: datetime
    updated_at: datetime


class ScenarioSummaryRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    template_id: str | None
    current_version: int
    shocks: list[ShockRead]
    entity: str | None
    latest_execution: ExecutionSummaryRead | None
    executions: int
    created_at: datetime
    updated_at: datetime


class ScenarioPage(Page[ScenarioSummaryRead]):
    """A page of scenarios, most recently changed first."""


class ExecutionPage(Page[ExecutionSummaryRead]):
    """A page of executions, newest first."""


# --- Plans --------------------------------------------------------------------------------------


class PlanIssueRead(ApiModel):
    code: str
    message: str
    severity: Severity
    field: str | None
    model_id: str | None


class EdgeRead(ApiModel):
    edge_key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str
    is_illustrative: bool


class EntityIndustryRead(ApiModel):
    key: str
    name: str


class EntityInfoRead(ApiModel):
    key: str
    name: str
    nature: str
    industries: list[EntityIndustryRead]


class ResponseBindingRead(ApiModel):
    variable_id: str
    change_type: ChangeType
    input: str


class LineItemRead(ApiModel):
    line: str
    item: str
    label: str
    output: str


class ModelExposureRead(ApiModel):
    checked: bool = Field(description="A company is chosen, so the graph was consulted.")
    required: bool = Field(description="The model only simulates companies with this exposure.")
    stated: bool
    chains: list[list[EdgeRead]]


class ModelPlanRead(ApiModel):
    model_id: str
    version: str
    name: str
    title: str
    covers: str
    definition_hash: str
    profile_hash: str
    mode: Literal["auto", "include", "exclude"]
    status: Literal["not_applicable", "available", "excluded", "included", "blocked"]
    reasons: list[str]
    changes: list[str]
    responds_to: list[ResponseBindingRead]
    lines: list[LineItemRead]
    exposure: ModelExposureRead
    issues: list[PlanIssueRead]
    inputs: list[ResolvedInputRead]
    graph: GraphSnapshotRead | None


class ChangePlanRead(ApiModel):
    index: int
    variable_id: str
    name: str
    change_type: ChangeType
    value: DecimalString
    unit: str
    modelled: bool
    models: list[str]
    reason: str | None


class StressPlanRead(ApiModel):
    index: int
    name: str
    changes: dict[str, DecimalString]
    valid: bool
    issues: list[PlanIssueRead]


class GraphStateRead(ApiModel):
    build_id: int | None
    freshness: Literal["current", "stale", "not_built"]


class AffectedNodeRead(ApiModel):
    key: str
    name: str
    type: str
    nature: str


class AffectedExposureRead(ApiModel):
    changed_variable: str
    via: list[str]
    relationship: str
    exposed_variable: str
    industry: AffectedNodeRead | None
    edges: list[EdgeRead]
    models: list[str] = Field(description="Models that simulate this tie; empty: none does.")


class AffectedEntityRead(ApiModel):
    entity: AffectedNodeRead
    exposures: list[AffectedExposureRead]


class AffectedEntitiesRead(ApiModel):
    entities: list[AffectedEntityRead]
    variables: dict[str, str]
    truncated: bool
    limit: int
    note: str


class PlanRead(ApiModel):
    spec_hash: str
    executable: bool
    graph: GraphStateRead
    entity: EntityInfoRead | None
    changes: list[ChangePlanRead]
    models: list[ModelPlanRead]
    stress_cases: list[StressPlanRead]
    issues: list[PlanIssueRead]
    errors: int
    ties: list[EdgeRead]
    names: dict[str, str]
    affected: AffectedEntitiesRead | None


# --- Results ------------------------------------------------------------------------------------


class ResultItemRead(ApiModel):
    model_id: str
    item: str
    label: str
    output: str
    monthly_output: str
    value: DecimalString
    by_change: dict[str, DecimalString]


class LineRead(ApiModel):
    id: str
    label: str
    equation: str
    unit: str
    currency: str
    baseline: DecimalString = Field(description="Your figures over the horizon, held constant.")
    change: DecimalString
    scenario: DecimalString
    percent_change: DecimalString | None
    direction: Literal["up", "down", "none"]
    effect: Literal["raises_profit", "reduces_profit", "none"]
    items: list[ResultItemRead]
    by_change: dict[str, DecimalString]
    monthly: list[DecimalString]
    cumulative: list[DecimalString]
    baseline_monthly: DecimalString
    note: str | None
    knowledge: Literal["simulated"]


class MetricRead(ApiModel):
    id: str
    label: str
    equation: str
    unit: str
    baseline: DecimalString
    scenario: DecimalString
    change: DecimalString
    change_unit: str
    direction: Literal["up", "down", "none"]
    knowledge: Literal["simulated"]


class NotModelledRead(ApiModel):
    id: str
    label: str
    reason: str


class KeyOutputRead(ApiModel):
    id: str
    label: str
    value: DecimalString
    unit: str
    kind: Literal["derived", "simulated"]


class ModelResultRead(ApiModel):
    model_id: str
    version: str
    name: str
    title: str
    definition_hash: str
    profile_hash: str
    run_id: uuid.UUID | None
    inputs_hash: str
    result_hash: str
    key_outputs: list[KeyOutputRead]
    bridge: BridgeRead | None
    warnings: list[SimulationIssueRead]


class TimelineLineRead(ApiModel):
    line: str
    values: list[DecimalString]


class TimelineEventRead(ApiModel):
    month: int
    label: str
    model_id: str


class TimelineRead(ApiModel):
    months: int
    start_month: int
    end_month: int
    lines: list[TimelineLineRead]
    events: list[TimelineEventRead]
    knowledge: Literal["simulated"]
    note: str


class EquationRefRead(ApiModel):
    id: str
    name: str
    formula: str


class PathwayEdgeInfoRead(ApiModel):
    edge_key: str
    edge_type: str
    relationship: str
    evidence_status: str
    is_illustrative: bool


class WindowRead(ApiModel):
    first_month: int | None
    last_month: int | None


class LinkAssumptionRead(ApiModel):
    id: str
    label: str
    value: str | None
    unit: str
    source: str
    default: str | None


class LabPathwayNodeRead(ApiModel):
    id: str
    kind: Literal["change", "variable", "driver", "line", "metric", "context"]
    label: str
    group: str | None
    knowledge: str
    value: str | None
    unit: str | None
    first_month: int | None
    monthly: list[str] | None
    detail: str | None
    line: str | None = None
    item: str | None = None


class LabPathwayLinkRead(ApiModel):
    id: str
    source: str
    target: str
    kind: Literal["applies", "transmission", "equation", "aggregation", "cited"]
    simulation: Literal["applied", "propagated", "computed", "aggregated", "context_only"]
    label: str
    group: str | None
    equations: list[EquationRefRead]
    rule: str | None
    edge: PathwayEdgeInfoRead | None
    coefficient: str | None
    lag_months: int | None
    window: WindowRead | None
    assumptions: list[LinkAssumptionRead]
    statements: list[StatementRead]
    sign: int | None
    active: bool


class PathwayGroupRead(ApiModel):
    id: str
    title: str
    version: str
    nodes: list[str]


class UnmodelledEdgeRead(EdgeRead):
    relationship: str
    source_name: str
    target_name: str
    reason: str


class LabPathwayRead(ApiModel):
    nodes: list[LabPathwayNodeRead]
    links: list[LabPathwayLinkRead]
    groups: list[PathwayGroupRead]
    unmodelled: list[UnmodelledEdgeRead]
    note: str


class StressResultRead(ApiModel):
    name: str
    scale: str | None
    changes: dict[str, DecimalString]
    lines: list[LineRead]
    metrics: list[MetricRead]
    knowledge: Literal["simulated"]


class LabStepRead(ApiModel):
    sequence: int
    equation: str
    label: str
    output: StepValueRead
    inputs: list[StepValueRead]


class LabEquationRead(ApiModel):
    id: str
    name: str
    formula: str
    explanation: str


class TimingResultRead(ApiModel):
    start_month: int
    end_month: int
    duration_months: int


class ResultsRead(ApiModel):
    execution_id: uuid.UUID | None = Field(description="Null for a preview (not stored).")
    lab_version: str
    engine_version: str
    currency: str
    horizon_months: int
    timing: TimingResultRead
    entity: EntityInfoRead | None
    lines: list[LineRead]
    metrics: list[MetricRead]
    not_modelled: list[NotModelledRead]
    models: list[ModelResultRead]
    timeline: TimelineRead
    stress_cases: list[StressResultRead]
    steps: list[LabStepRead]
    equations: list[LabEquationRead]
    configuration: dict[str, str | int]
    note: str


class PreviewRead(ApiModel):
    """A plan and, when it is executable, the results — computed, not stored."""

    plan: PlanRead
    results: ResultsRead | None
    pathway: LabPathwayRead | None
    stored: Literal[False] = False
    note: str


# --- Executions ---------------------------------------------------------------------------------


class StageRead(ApiModel):
    stage: Literal["validating", "simulating", "propagating", "aggregating"]
    started_at: datetime
    finished_at: datetime | None
    detail: str


class ExecutionRunRead(ApiModel):
    position: int
    model_id: str
    model_version: str
    run_id: uuid.UUID


class ExecutionRead(ExecutionSummaryRead):
    scenario_name: str
    lab_version: str
    cancel_requested: bool
    stages: list[StageRead]
    plan: PlanRead | None
    runs: list[ExecutionRunRead]
    results_available: bool
    poll_after_ms: int | None = Field(
        description="While the execution is not final: when to ask again (milliseconds)."
    )


class RunCheckRead(ApiModel):
    model_id: str
    run_id: uuid.UUID
    inputs_hash_matches: bool
    result_hash_matches: bool


class ExecutionVerificationRead(ApiModel):
    execution_id: uuid.UUID
    reproduced: bool
    inputs_hash_matches: bool
    result_hash_matches: bool
    stored_result_hash: str | None
    recomputed_result_hash: str | None
    runs: list[RunCheckRead]
    message: str


# --- Explanation --------------------------------------------------------------------------------


class ExplanationTermRead(ApiModel):
    id: str
    label: str
    change: DecimalString


class ChangeCreditRead(ApiModel):
    variable_id: str
    name: str
    change: str | None
    unit: str | None
    value: DecimalString


class ExplainedItemRead(ApiModel):
    item: str
    label: str
    output: str
    value: DecimalString
    by_change: dict[str, DecimalString]


class ExplainedEquationRead(ApiModel):
    id: str
    name: str
    formula: str
    scope: str
    explanation: str
    assumptions: list[StatementRead]
    limitations: list[StatementRead]


class ExplainedStepRead(ApiModel):
    sequence: int
    equation: str
    label: str
    month: int | None
    output: StepValueRead
    inputs: list[StepValueRead]


class ExplainedGraphRead(ApiModel):
    build_id: int | None
    freshness: str | None
    transmission: dict[str, Any]
    supporting: dict[str, Any]
    entity: dict[str, Any] | None
    names: dict[str, str]


class ExplainedModelRead(ApiModel):
    model_id: str
    version: str
    run_id: uuid.UUID
    inputs_hash: str
    result_hash: str
    engine_version: str
    items: list[ExplainedItemRead]
    changes: list[ResolvedInputRead]
    inputs: list[ResolvedInputRead]
    equations: list[ExplainedEquationRead]
    worked_month: int | None
    steps: list[ExplainedStepRead]
    transmission: list[TransmissionPathRead]
    graph: ExplainedGraphRead
    data: list[SimulationObservationRead]
    assumptions: list[StatementRead]
    limitations: list[StatementRead]
    warnings: list[SimulationIssueRead]


class ProfileNoteRead(ApiModel):
    title: str
    covers: str


class LabExplanationRead(ApiModel):
    execution_id: uuid.UUID
    target: str
    label: str
    equation: LabEquationRead
    terms: list[ExplanationTermRead]
    by_change: list[ChangeCreditRead]
    lab_steps: list[LabStepRead]
    models: list[ExplainedModelRead]
    profiles: dict[str, ProfileNoteRead]
    chain: list[str]
    method: dict[str, str]


# --- Sensitivity --------------------------------------------------------------------------------


class LabSensitivityPointRead(ApiModel):
    role: str
    value: DecimalString
    metric: DecimalString | None
    delta: DecimalString | None
    skipped: str | None


class LabSensitivityRangeRead(ApiModel):
    low: DecimalString
    high: DecimalString
    spread: DecimalString


class LabSensitivityItemRead(ApiModel):
    target: str
    label: str
    kind: Literal["change", "shared", "company", "market", "assumption"]
    models: list[str]
    unit: str | None
    base_value: DecimalString
    mode: str
    step: DecimalString | None
    points: list[LabSensitivityPointRead]
    range: LabSensitivityRangeRead | None


class LabSensitivityRankRead(ApiModel):
    target: str
    label: str
    spread: DecimalString


class LabSensitivityRead(ApiModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    metric: str
    metric_label: str
    metric_kind: Literal["line_change", "metric_value"]
    base: DecimalString
    items: list[LabSensitivityItemRead]
    ranking: list[LabSensitivityRankRead]
    evaluations: int
    duration_ms: int
    result_hash: str
    created_at: datetime
    method: Literal["one_at_a_time"] = "one_at_a_time"
    note: str


class LabSensitivityList(ApiModel):
    items: list[LabSensitivityRead]


# --- Comparison ---------------------------------------------------------------------------------


class ComparedModelRead(ApiModel):
    model_id: str
    version: str
    title: str


class ComparedExecutionRead(ApiModel):
    execution_id: uuid.UUID
    scenario_id: uuid.UUID
    scenario_name: str
    version: int
    requested_at: datetime
    currency: str | None
    horizon_months: int | None
    timing: TimingResultRead | None
    entity: EntityInfoRead | None
    changes: list[ChangePlanRead]
    models: list[ComparedModelRead]
    result_hash: str | None


class DifferenceRead(ApiModel):
    absolute: DecimalString
    percent: DecimalString | None


class ComparedCellRead(ApiModel):
    execution_id: uuid.UUID
    baseline: DecimalString | None
    change: DecimalString | None
    scenario: DecimalString | None
    percent_change: DecimalString | None
    modelled: bool
    difference: DifferenceRead | None


class ComparedRowRead(ApiModel):
    id: str
    label: str
    values: list[ComparedCellRead]


class ComparedValueRead(ApiModel):
    value: str | None
    unit: str
    source: str


class ComparedInputRead(ApiModel):
    model_id: str
    input: str
    label: str
    category: str
    values: list[ComparedValueRead | None]


class ComparedLinkRead(ApiModel):
    link: str
    present: list[bool]


class ComparedSensitivityRead(ApiModel):
    execution_id: uuid.UUID
    metric: str | None
    ranking: list[LabSensitivityRankRead]


class ComparisonRead(ApiModel):
    reference: uuid.UUID
    executions: list[ComparedExecutionRead]
    comparable: dict[str, bool]
    lines: list[ComparedRowRead]
    metrics: list[ComparedRowRead]
    inputs: list[ComparedInputRead]
    pathways: list[ComparedLinkRead]
    sensitivity: list[ComparedSensitivityRead]
    note: str


# --- Templates ----------------------------------------------------------------------------------


class TemplateChangeRead(ApiModel):
    variable_id: str
    change_type: ChangeType
    value: DecimalString


class TemplateInputRead(ApiModel):
    path: str
    input: str
    label: str
    kind: Literal["entity", "change", "market", "company", "assumption", "setting"]
    unit: str | None
    unit_label: str | None
    units: list[str]
    default: str | None
    description: str
    shared: bool
    models: list[str]


class TemplateRuleRead(ApiModel):
    model_id: str
    id: str
    description: str
    severity: Severity


class TemplateLineRead(ApiModel):
    line: str
    label: str
    items: list[dict[str, str]]


class TemplateDerivedRead(ApiModel):
    id: str
    label: str


class TemplateOutputRead(ApiModel):
    model_id: str
    id: str
    label: str
    unit: str


class TemplateExpectedRead(ApiModel):
    lines: list[TemplateLineRead]
    derived: list[TemplateDerivedRead]
    model_outputs: list[TemplateOutputRead]


class TemplateModelRead(ApiModel):
    model_id: str
    title: str
    version: str


class TemplateSummaryRead(ApiModel):
    id: str
    title: str
    category: Literal["commodity", "currency", "interest_rate", "energy_cost", "combined"]
    question: str
    summary: str
    changes: list[TemplateChangeRead]
    models: list[TemplateModelRead]
    stress_cases: list[StressCaseRead]
    suggested_entities: list[AffectedNodeRead] = Field(
        description="Companies whose exposure the knowledge graph states for the template's "
        "models (none when the graph is not built)."
    )


class TemplateRead(TemplateSummaryRead):
    required_inputs: list[TemplateInputRead]
    optional_inputs: list[TemplateInputRead]
    validation_rules: list[TemplateRuleRead]
    expected_outputs: TemplateExpectedRead
    scenario: ScenarioInput = Field(description="The template as a scenario body to start from.")


class UnsupportedTemplateRead(ApiModel):
    id: str
    title: str
    reason: str


class TemplateList(ApiModel):
    items: list[TemplateSummaryRead]
    unsupported: list[UnsupportedTemplateRead]
