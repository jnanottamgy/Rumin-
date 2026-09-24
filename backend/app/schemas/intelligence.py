"""Financial intelligence: insights with their evidence chains, exposure, drivers, signals,
detected changes, entity briefs and stored analyses.

Every insight carries the chain of evidence it rests on — observations, exact calculations,
knowledge-graph relationships (with their evidence status), RUMIN's own records, simulations
and the thresholds that selected it — and an **evidence grade**, the weakest link of that
chain (observed > documented > curated > simulated > assumed > unverified). The grade is
not a probability. Values are exact decimals in plain notation.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.graph.drafts import NODE_KEY_PATTERN
from app.schemas.common import ApiModel, DecimalString, InputModel, Page, SafeText

Grade = Literal["observed", "documented", "curated", "simulated", "assumed", "unverified"]
Basis = Literal[
    "observation", "calculation", "relationship", "record", "simulation", "assumption", "threshold"
]
Freshness = Literal["current", "stale", "not_built"]
EvidenceStatus = Literal["evidence_backed", "analyst_created", "model_assumption", "unverified"]
EvidenceFilter = Literal["any", "evidence_backed"]
Scope = Literal["entity", "workspace"]
ThresholdValue = str | int | None


# --- Evidence ----------------------------------------------------------------------------------


class RefRead(ApiModel):
    kind: str = Field(
        description="What is referred to: dataset, series, observation, instrument, price_bar, "
        "graph_build, graph_node, graph_edge, scenario, execution, run, sensitivity_analysis, "
        "template, threshold, catalogue or calculation."
    )
    id: str
    label: str | None


class EvidenceStepRead(ApiModel):
    basis: Basis
    text: str
    refs: list[RefRead]
    evidence_status: EvidenceStatus | None = Field(description="Relationship steps only.")
    value: str | None = Field(description="Exact decimal text, when the step has a value.")
    unit: str | None


class FactRead(ApiModel):
    label: str
    value: str | None = Field(description="Exact decimal text for numbers; text otherwise.")
    unit: str | None
    basis: Basis
    refs: list[RefRead]
    period: str | None


class RelationshipRefRead(ApiModel):
    edge_key: str
    edge_type: str
    label: str
    source: str
    source_name: str
    target: str
    target_name: str
    evidence_status: EvidenceStatus
    is_illustrative: bool


class PeriodRead(ApiModel):
    kind: Literal["observation", "graph_build", "scenario", "analysis"]
    label: str
    start: str | None
    end: str | None


class ModelRefRead(ApiModel):
    kind: Literal["execution", "run"]
    id: str
    label: str
    models: list[str] = Field(description="'model_id version' of each model used.")


class NextStepRead(ApiModel):
    action: str = Field(
        description="run_template, run_scenario, run_sensitivity, ingest_series, "
        "find_evidence, model_gap, review_revision or open_execution."
    )
    text: str
    target: RefRead | None


class InsightEvidenceRead(ApiModel):
    grade: Grade = Field(description="The weakest step of the chain. Not a probability.")
    conditional_on_simulation: bool = Field(
        description="True when a step is a simulation: the statement holds only under the "
        "scenario's inputs and assumptions."
    )
    includes_observations: bool
    statement: str
    weakest_step: int | None = Field(description="Index in `chain` of the step that set it.")


class InsightRead(ApiModel):
    id: str = Field(description="Stable for the same rule, subject and facts.")
    rule: str
    rule_title: str
    kind: str
    headline: str
    statement: str = Field(description="A documented template filled with computed values.")
    subject: RefRead
    entities: list[RefRead]
    relationships: list[RelationshipRefRead]
    period: PeriodRead
    facts: list[FactRead]
    models: list[ModelRefRead]
    evidence: InsightEvidenceRead
    chain: list[EvidenceStepRead] = Field(min_length=1)
    assumptions: list[str]
    limitations: list[str]
    next_steps: list[NextStepRead]
    sources: list[RefRead]


class SignalRead(ApiModel):
    id: str
    name: str
    subject: RefRead
    status: Literal["computed", "insufficient_data", "not_applicable"]
    level: str | None
    level_label: str | None
    summary: str
    values: list[FactRead]
    period: PeriodRead
    inputs: list[RefRead]
    thresholds: dict[str, ThresholdValue]
    evidence: InsightEvidenceRead
    limitations: list[str]


class BuildRead(ApiModel):
    id: int | None = Field(description="The latest completed knowledge-graph build.")
    finished_at: datetime | None
    freshness: Freshness
    message: str | None


class ThresholdsRead(ApiModel):
    relative_change_percent: DecimalString
    point_change: DecimalString
    price_move_percent: DecimalString
    anomaly_score: DecimalString
    trend_significance: str
    volatility_high_percentile: DecimalString
    dependency_share_percent: DecimalString
    min_history: int
    window: int | None


# --- Knowledge graph ---------------------------------------------------------------------------


class NodeRead(ApiModel):
    key: str
    name: str
    node_type: str
    nature: str
    attributes: dict[str, Any]


class EdgeInfoRead(ApiModel):
    key: str
    edge_type: str
    label: str
    source: str
    target: str
    evidence_status: EvidenceStatus
    is_illustrative: bool
    quality_status: str
    description: str
    caveat: str
    polarity: str | None
    strength: str | None
    rationale: str | None
    evidence_level: str | None
    stated_difference: str | None


class SeriesInfoRead(ApiModel):
    series_id: str
    name: str
    unit: str
    frequency: str
    measure_type: str
    observation_count: int
    first_period: date | None
    last_period: date | None


class ExposurePathRead(ApiModel):
    origin: NodeRead = Field(description="The variable the path starts from.")
    variable: NodeRead = Field(description="The variable that reaches the entity.")
    channel: Literal["costs", "revenue", "financing"]
    directness: Literal["direct", "via_industry", "upstream"]
    base: Literal["direct", "via_industry"]
    industry: NodeRead | None
    hops: list[NodeRead]
    edges: list[EdgeInfoRead]
    evidence_status: EvidenceStatus = Field(description="The weakest along the path.")
    models: list[str] = Field(description="Registered models that can simulate this path.")
    group: str


class CounterpartyRead(ApiModel):
    relationship: Literal["supplies_to", "lends_to"]
    role: Literal["supplier", "customer", "lender", "borrower"]
    counterparty: NodeRead
    level: Literal["company", "industry"]
    edge: EdgeInfoRead


class ContextLinkRead(ApiModel):
    kind: str
    node: NodeRead
    edges: list[EdgeInfoRead]


class SeriesCoverageRead(ApiModel):
    variable: str
    series_key: str
    info: SeriesInfoRead | None
    edge: EdgeInfoRead


class ExposureSummaryRead(ApiModel):
    paths: int
    variables: int
    by_channel: dict[str, int]
    by_directness: dict[str, int]
    by_group: dict[str, int]
    by_evidence: dict[str, int]


class ExposureMapRead(ApiModel):
    entity: NodeRead
    build_id: int | None
    evidence_filter: EvidenceFilter
    paths: list[ExposurePathRead]
    counterparties: list[CounterpartyRead]
    context: list[ContextLinkRead]
    series: list[SeriesCoverageRead]
    flagged: list[EdgeInfoRead] = Field(
        description="Relationships the build flagged: listed, never used as exposure."
    )
    removed_by_filter: int
    notes: list[str]
    summary: ExposureSummaryRead
    variables: list[NodeRead]


# --- Observed data -----------------------------------------------------------------------------


class DatasetInfoRead(ApiModel):
    id: str
    name: str
    version: str
    is_illustrative: bool
    license: str
    attribution: str | None


class SubjectRead(ApiModel):
    kind: Literal["series", "instrument"]
    id: str
    name: str
    unit: str
    frequency: str
    measure: Literal["relative", "points"]
    variable_id: str | None
    variable_relation: str | None
    country: str | None
    dataset: DatasetInfoRead
    change_unit: Literal["percent", "percentage_points"]


class PointRead(ApiModel):
    label: str
    start: date
    value: DecimalString
    record_id: int
    revision: int
    quality_status: str
    flags: str | None
    retrieved_at: datetime
    last_confirmed_at: datetime


class ChangeRead(ApiModel):
    earlier: PointRead
    later: PointRead
    value: DecimalString = Field(description="Percent, or percentage points (`change_unit`).")
    direction: Literal["up", "down", "none"]
    flagged: bool


class RevisionRead(ApiModel):
    label: str
    start: date
    previous: DecimalString | None
    revised: DecimalString | None
    previous_revision: int
    revised_at: datetime | None
    previous_id: int
    revised_id: int
    change: DecimalString | None


class TrendRead(ApiModel):
    window: int
    n: int
    first: str
    last: str
    slope: DecimalString
    relative_slope: DecimalString | None
    t: DecimalString | None
    critical: DecimalString | None
    significance: str
    direction: Literal["rising", "falling", "no_clear_direction", "exact_line"]
    exact_fit: bool


class VolatilityRead(ApiModel):
    window: int
    latest: DecimalString
    windows: int
    percentile: DecimalString | None
    median_earlier: DecimalString | None
    level: Literal["high", "not_high", "insufficient_history"]
    first: str
    last: str


class AnomalyRead(ApiModel):
    change: ChangeRead
    reference: int
    score: DecimalString | None
    level: Literal["unusual", "not_unusual", "undefined", "insufficient_history"]


class SeriesAnalysisRead(ApiModel):
    subject: SubjectRead
    points: list[PointRead] = Field(description="The latest stored values (at most 400).")
    points_total: int
    changes: list[ChangeRead] = Field(description="The latest changes (at most 60).")
    changes_total: int
    threshold_name: str
    threshold: DecimalString
    detected: list[ChangeRead] = Field(
        description="Changes of the latest window that meet the threshold."
    )
    latest: ChangeRead | None
    trend: TrendRead | None
    volatility: VolatilityRead | None
    anomaly: AnomalyRead | None
    revisions: list[RevisionRead]
    signals: list[SignalRead]


class SeriesSummaryRead(ApiModel):
    subject: SubjectRead
    points_total: int
    first: str | None
    last: str | None
    latest_value: DecimalString | None
    latest: ChangeRead | None
    threshold_name: str
    threshold: DecimalString
    detected: int
    latest_detected: bool
    trend: str | None
    volatility: str | None
    anomaly: str | None
    revisions: int


# --- Simulations -------------------------------------------------------------------------------


class ChangeInputRead(ApiModel):
    variable_id: str
    name: str
    change_type: Literal["percent_change", "absolute_change"]
    value: DecimalString
    unit: str
    modelled: bool


class DriverContributionRead(ApiModel):
    variable_id: str
    name: str
    value: DecimalString = Field(description="Stored contribution, in the line's currency.")
    share_of_change: DecimalString | None = Field(description="Percent of the line's change.")
    points_of_baseline: DecimalString | None = Field(description="Percent of the baseline.")
    per_unit: DecimalString | None = Field(
        description="Contribution per 1 % (or per percentage point) of the change: an "
        "average over the scenario's change, not a slope."
    )
    per_unit_label: str | None


class ItemDriversRead(ApiModel):
    model_id: str
    item: str
    label: str
    value: DecimalString
    by_change: dict[str, DecimalString]


class LineDriversRead(ApiModel):
    id: str
    label: str
    currency: str
    baseline: DecimalString
    change: DecimalString
    scenario: DecimalString
    percent_change: DecimalString | None
    direction: str
    effect: str
    contributions: list[DriverContributionRead]
    residual: DecimalString = Field(description="Change the contributions leave unattributed.")
    items: list[ItemDriversRead]


class MetricChangeRead(ApiModel):
    id: str
    label: str
    unit: str
    baseline: DecimalString | None
    scenario: DecimalString | None
    change: DecimalString | None
    change_unit: str | None


class ModelUsedRead(ApiModel):
    model_id: str
    version: str
    name: str
    run_id: str
    definition_hash: str


class RankedQuantityRead(ApiModel):
    target: str
    label: str
    spread: DecimalString


class SensitivityRankingRead(ApiModel):
    analysis_id: str
    metric: str
    metric_label: str
    created_at: datetime
    ranking: list[RankedQuantityRead]


class ExecutionRefRead(ApiModel):
    id: str
    scenario_id: str
    scenario_name: str
    version: int
    finished_at: datetime | None
    currency: str
    horizon_months: int
    graph_build_id: int | None
    graph_freshness: str | None
    inputs_hash: str | None
    result_hash: str | None


class UnstatedExposureRead(ApiModel):
    model_id: str
    model_name: str
    variable_ids: list[str]
    message: str


class FigureRead(ApiModel):
    label: str
    value: str
    unit: str


class DriverAnalysisRead(ApiModel):
    entity_key: str
    execution: ExecutionRefRead
    changes: list[ChangeInputRead]
    lines: list[LineDriversRead]
    metrics: list[MetricChangeRead]
    headline: str | None
    models: list[ModelUsedRead]
    assumptions: list[str]
    figures: list[FigureRead] = Field(description="Figures the user entered: not RUMIN data.")
    sensitivity: SensitivityRankingRead | None
    notes: list[str]
    not_modelled: list[str]
    unstated: list[UnstatedExposureRead] = Field(
        description="Models included although the graph states no exposure: those parts "
        "rest on the entered figures alone."
    )


class InterpretedLineRead(ApiModel):
    id: str
    label: str
    currency: str
    baseline: DecimalString
    change: DecimalString
    percent_change: DecimalString | None


class InterpretationRead(ApiModel):
    execution_id: str
    scenario_name: str
    version: int
    variable_id: str
    variable_name: str
    series_id: str
    series_name: str
    stated_difference: str | None
    observed: ChangeRead
    observed_unit: str
    applied: DecimalString
    applied_type: str
    lines: list[InterpretedLineRead]
    headline: str | None
    models: list[str]
    graph_build_id: int | None
    note: str


class NotInterpretedRead(ApiModel):
    variable_id: str
    series_id: str
    reason: str


class ImpactRead(ApiModel):
    execution: ExecutionRefRead
    line: str
    label: str
    currency: str
    baseline: DecimalString
    change: DecimalString
    percent_change: DecimalString | None
    changes: list[ChangeInputRead]


# --- Analyses ----------------------------------------------------------------------------------


class EntityAnalysisRead(ApiModel):
    engine_version: str
    entity: NodeRead
    build: BuildRead
    thresholds: ThresholdsRead
    exposure: ExposureMapRead
    executions: list[ExecutionRefRead]
    drivers: DriverAnalysisRead | None = Field(description="The latest completed execution.")
    previous: DriverAnalysisRead | None = Field(
        description="The previous execution of the same scenario, if any."
    )
    series: list[SeriesAnalysisRead] = Field(
        description="Stored series recorded as related measures of the entity's exposure variables."
    )
    interpretations: list[InterpretationRead] = Field(
        description="Model interpretations of observed changes: computed on request, never "
        "stored as results."
    )
    not_interpreted: list[NotInterpretedRead]
    signals: list[SignalRead]
    insights: list[InsightRead]
    grades: dict[str, int]
    kinds: dict[str, int]
    next_steps: list[NextStepRead]


class CoverageRead(ApiModel):
    companies: int
    companies_with_exposure: int
    exposure_paths: int
    variables: int
    series: int
    series_with_data: int
    observations: int
    instruments: int
    instruments_with_data: int
    related_series: int
    related_with_data: int
    executions: int
    companies_with_executions: int
    truncated: bool


class MatrixCellRead(ApiModel):
    company: str
    variable: str
    paths: int
    channels: list[str]
    directness: list[str]
    evidence_status: EvidenceStatus = Field(description="The weakest of its paths.")
    models: list[str]


class ExposureMatrixRead(ApiModel):
    build_id: int | None
    companies: list[NodeRead]
    variables: list[NodeRead]
    cells: list[MatrixCellRead]
    truncated: bool


class BuildRefRead(ApiModel):
    id: int
    finished_at: datetime | None
    status: str


class EdgeChangeRead(ApiModel):
    change: Literal["added", "changed", "retired"]
    edge_key: str
    edge_type: str
    label: str
    source: str
    source_name: str
    target: str
    target_name: str
    evidence_status: str
    quality_status: str
    exposure_relevant: bool


class RelationshipChangesRead(ApiModel):
    build: BuildRefRead | None
    previous: BuildRefRead | None
    edges: list[EdgeChangeRead]
    counts: dict[str, int]
    truncated: bool
    note: str


class OverviewRead(ApiModel):
    engine_version: str
    build: BuildRead
    thresholds: ThresholdsRead
    coverage: CoverageRead
    insights: list[InsightRead]
    grades: dict[str, int]
    kinds: dict[str, int]
    next_steps: list[NextStepRead]
    exposure: ExposureMatrixRead
    series: list[SeriesSummaryRead]
    instruments: list[SeriesSummaryRead]
    relationships: RelationshipChangesRead
    impacts: list[ImpactRead] = Field(description="The latest simulated headline per company.")


class InsightListRead(ApiModel):
    scope: Scope
    subject: RefRead | None
    build: BuildRead
    thresholds: ThresholdsRead
    items: list[InsightRead]
    total: int


class ObservedChangeRead(ApiModel):
    subject: SubjectRead
    change: ChangeRead
    threshold_name: str
    threshold: DecimalString
    latest: bool = Field(description="The most recent change of its series.")


class RevisionChangeRead(ApiModel):
    subject: SubjectRead
    revision: RevisionRead


class ExecutionChangeRead(ApiModel):
    entity: NodeRead
    line: str
    label: str
    currency: str
    previous: ExecutionRefRead
    latest: ExecutionRefRead
    previous_change: DecimalString
    latest_change: DecimalString
    difference: DecimalString


class ChangesRead(ApiModel):
    build: BuildRead
    thresholds: ThresholdsRead
    observed: list[ObservedChangeRead] = Field(
        description="Stored values: changes of each latest window that meet their threshold."
    )
    revisions: list[RevisionChangeRead]
    relationships: RelationshipChangesRead
    executions: list[ExecutionChangeRead] = Field(
        description="Simulated: the headline between two executions of the same scenario."
    )
    notes: list[str]


class EntitySummaryRead(ApiModel):
    entity: NodeRead
    paths: int
    variables: int
    by_channel: dict[str, int]
    by_directness: dict[str, int]
    weakest_evidence: EvidenceStatus | None
    latest_impact: ImpactRead | None


class EntityListRead(ApiModel):
    build: BuildRead
    items: list[EntitySummaryRead]
    total: int


class SignalListRead(ApiModel):
    subject: RefRead
    build: BuildRead
    thresholds: ThresholdsRead
    items: list[SignalRead]


class DriversRead(ApiModel):
    entity: NodeRead
    executions: list[ExecutionRefRead]
    drivers: DriverAnalysisRead | None
    previous: DriverAnalysisRead | None
    note: str


class VariableReachRead(ApiModel):
    company: NodeRead
    paths: list[ExposurePathRead]


class VariableExposureRead(ApiModel):
    variable: NodeRead
    build: BuildRead
    companies: list[VariableReachRead]
    note: str


class SeriesIntelligenceRead(ApiModel):
    build: BuildRead
    thresholds: ThresholdsRead
    analysis: SeriesAnalysisRead
    variable: NodeRead | None
    reached: list[NodeRead] = Field(
        description="Companies the related variable reaches through validated relationships."
    )
    insights: list[InsightRead]


class InstrumentIntelligenceRead(ApiModel):
    thresholds: ThresholdsRead
    analyses: list[SeriesAnalysisRead] = Field(description="One per price dataset.")
    insights: list[InsightRead]


# --- Brief ---------------------------------------------------------------------------------------


class BriefThresholdRead(ApiModel):
    name: str
    value: DecimalString


class BriefSignalRead(ApiModel):
    id: str
    status: str
    level: str | None
    summary: str
    values: list[FactRead]
    evidence_grade: Grade


class BriefObservationRead(ApiModel):
    subject: SubjectRead
    latest_change: ChangeRead | None
    meets_threshold: bool
    threshold: BriefThresholdRead
    signals: list[BriefSignalRead]
    revisions: list[RevisionRead]
    evidence_grade: Grade


class BriefDriverLineRead(ApiModel):
    id: str
    label: str
    change: DecimalString
    currency: str
    contributions: list[DriverContributionRead]
    unattributed: DecimalString


class BriefDriversRead(ApiModel):
    headline: str | None
    lines: list[BriefDriverLineRead]
    sensitivity: SensitivityRankingRead | None
    method: str
    evidence_grade: Grade


class BriefResultLineRead(ApiModel):
    id: str
    label: str
    currency: str
    baseline: DecimalString
    change: DecimalString
    scenario: DecimalString
    percent_change: DecimalString | None


class BriefSimulationRead(ApiModel):
    execution: ExecutionRefRead
    changes: list[ChangeInputRead]
    lines: list[BriefResultLineRead]
    metrics: list[MetricChangeRead]
    not_modelled: list[str]
    unstated_exposures: list[UnstatedExposureRead]
    interpretations: list[InterpretationRead]
    evidence_grade: Grade


class BriefEvidenceRead(ApiModel):
    insight_id: str
    rule: str
    kind: str
    statement: str
    grade: Grade
    conditional_on_simulation: bool
    facts: list[FactRead]
    chain: list[EvidenceStepRead]


class BriefRead(ApiModel):
    """What a future AI Analyst would receive about one entity. Numbers are computed by
    RUMIN, never by the model that narrates them (see `narration_rules`)."""

    format: Literal["rumin.intelligence.brief/1"]
    engine_version: str
    generated_at: datetime
    entity: NodeRead
    build: BuildRead
    thresholds: ThresholdsRead
    observations: list[BriefObservationRead]
    exposures: list[ExposurePathRead]
    counterparties: list[CounterpartyRead]
    context: list[ContextLinkRead]
    relationships: list[EdgeInfoRead]
    drivers: BriefDriversRead | None
    simulation_results: BriefSimulationRead | None
    figures_entered: list[FigureRead]
    assumptions: list[str]
    evidence: list[BriefEvidenceRead]
    limitations: list[str]
    next_steps: list[NextStepRead]
    narration_rules: list[str]


# --- Methods -----------------------------------------------------------------------------------


class ModuleRead(ApiModel):
    id: str
    title: str
    question: str
    reads: list[str]
    method: str
    produces: list[str]
    limitations: list[str]
    version: str


class LevelRead(ApiModel):
    id: str
    label: str


class SignalSpecRead(ApiModel):
    id: str
    name: str
    subjects: list[str]
    question: str
    definition: str
    method: str
    inputs: str
    levels: list[LevelRead]
    thresholds: list[str]
    limitations: list[str]


class InsightRuleRead(ApiModel):
    id: str
    kind: str
    title: str
    purpose: str


class ThresholdSpecRead(ApiModel):
    name: str
    label: str
    unit: str
    default: str | None
    minimum: str | None
    maximum: str | None
    choices: list[str] | None
    integer: bool
    rationale: str


class GradeRead(ApiModel):
    id: Grade
    strength: int
    statement: str


class MethodsRead(ApiModel):
    engine_version: str
    modules: list[ModuleRead]
    signals: list[SignalSpecRead]
    rules: list[InsightRuleRead]
    kinds: list[str] = Field(description="Insight kinds in display order.")
    thresholds: list[ThresholdSpecRead]
    defaults: ThresholdsRead
    grades: list[GradeRead]
    edge_grades: dict[str, Grade]
    notes: list[str]


# --- Stored analyses ---------------------------------------------------------------------------


class AnalysisRequest(InputModel):
    scope: Scope
    entity: str | None = Field(
        default=None,
        pattern=NODE_KEY_PATTERN,
        max_length=128,
        description="The company or industry (graph key); required for scope `entity`.",
        examples=["company:co_aerisca_airways"],
    )
    thresholds: dict[str, Any] | None = Field(
        default=None,
        description="Overrides of the default thresholds (see GET /intelligence/methods).",
        examples=[{"relative_change_percent": "3"}],
    )
    evidence: EvidenceFilter = Field(
        default="any",
        description="`evidence_backed` keeps only relationships with a cited source.",
    )
    label: SafeText | None = Field(default=None, max_length=200)

    @field_validator("thresholds")
    @classmethod
    def _bounded(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and len(value) > 20:
            raise ValueError("At most 20 thresholds can be set.")
        return value

    @model_validator(mode="after")
    def _entity_matches_scope(self) -> AnalysisRequest:
        if self.scope == "entity" and not self.entity:
            raise ValueError("An entity analysis needs `entity`.")
        if self.scope == "workspace" and self.entity:
            raise ValueError("A workspace analysis takes no `entity`.")
        return self


class AnalysisFreshnessRead(ApiModel):
    status: Literal["current", "stale"]
    changed: list[str] = Field(
        description="What changed since: graph, data, executions, engine or subject."
    )
    checked_at: datetime
    message: str


class AnalysisSummaryRead(ApiModel):
    id: uuid.UUID
    scope: Scope
    subject_key: str | None
    subject_name: str
    label: str | None
    engine_version: str
    graph_build_id: int | None
    inputs_hash: str
    result_hash: str
    insight_count: int
    duration_ms: int
    created_at: datetime


class AnalysisRead(AnalysisSummaryRead):
    thresholds: ThresholdsRead
    inputs: dict[str, Any] = Field(description="Fingerprint of everything the analysis read.")
    entity: EntityAnalysisRead | None = Field(description="Scope `entity`: the analysis.")
    workspace: OverviewRead | None = Field(description="Scope `workspace`: the analysis.")
    freshness: AnalysisFreshnessRead


AnalysisPage = Page[AnalysisSummaryRead]
