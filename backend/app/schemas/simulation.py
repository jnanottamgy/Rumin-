"""Request and response schemas of the simulation API (Phase 4).

Numbers in responses are exact decimal strings in plain notation (the Phase 2 convention).
Inputs accept exact decimal strings (``"2.35"``) or JSON numbers, read through their
shortest representation; exponents, separators and symbols are refused.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StrictFloat, StrictInt, StringConstraints

from app.schemas.common import ApiModel, DecimalString, InputModel, Page, SafeText
from app.simulation.definitions import MODEL_ID_PATTERN, VERSION_PATTERN

INPUT_ID = r"^[a-z][a-z0-9_]{1,63}$"
UNIT_ID = r"^[a-z_]{1,32}$"
SERIES_ID = r"^[a-z0-9][a-z0-9-]{0,95}$"
# A value as sent: an exact decimal string (bounded), a JSON number, or a code/node key.
# Strict numbers: a string is never coerced into an int or a float.
NumberInput = Annotated[str, StringConstraints(max_length=128)] | StrictInt | StrictFloat
InputId = Annotated[str, StringConstraints(pattern=INPUT_ID)]

# --- Requests -----------------------------------------------------------------------------------


class SimulationInputValue(InputModel):
    value: NumberInput | None = Field(
        default=None,
        description='The value: an exact decimal string ("2.35") or a JSON number; a code or '
        "node key for text inputs. Omit it to take the model's default (optional inputs) or "
        "to use a stored observation.",
        examples=["30"],
    )
    unit: str | None = Field(
        default=None, pattern=UNIT_ID, description="For quantities: one of the listed units."
    )
    source: Literal["user", "stored_observation"] | None = Field(
        default=None,
        description="`stored_observation` takes the latest stored value of a series the "
        "model lists for this input.",
    )
    series_id: str | None = Field(default=None, pattern=SERIES_ID, max_length=96)


class SimulationRequest(InputModel):
    model_id: str = Field(pattern=MODEL_ID_PATTERN.pattern, examples=["airline_fuel_cost"])
    model_version: str | None = Field(
        default=None,
        pattern=VERSION_PATTERN.pattern,
        description="Defaults to the latest runnable version.",
    )
    inputs: dict[InputId, SimulationInputValue] = Field(
        default_factory=dict, max_length=40, description="Input values by input id."
    )


class SimulationRunRequest(SimulationRequest):
    label: SafeText | None = Field(
        default=None, max_length=120, description="An optional name for the run."
    )


class SensitivityInputRequest(InputModel):
    input: str = Field(pattern=INPUT_ID)
    mode: Literal["default", "absolute", "relative", "values"] = Field(
        default="default",
        description="`default`: the model's own low/high variation. `absolute`: base ± step "
        "(in the input's unit). `relative`: base × (1 ± step %). `values`: the listed values.",
    )
    step: NumberInput | None = None
    values: list[NumberInput] = Field(default_factory=list, max_length=7)


class SensitivityRequest(InputModel):
    inputs: list[SensitivityInputRequest] = Field(
        default_factory=list,
        max_length=8,
        description="Inputs to vary; empty means the model's default selection.",
    )
    metric: str | None = Field(
        default=None, pattern=INPUT_ID, description="The output to rank inputs by."
    )


# --- Model definitions --------------------------------------------------------------------------


class UnitChoice(ApiModel):
    id: str
    label: str


class ObservationSourceRead(ApiModel):
    series_id: str
    label: str
    unit: str
    currency_pair: list[str]
    caveat: str
    available: bool = Field(description="Whether RUMIN stores a value of this series now.")
    latest_period: str | None
    latest_value: DecimalString | None
    last_confirmed_at: datetime | None


class SensitivitySpecRead(ApiModel):
    mode: Literal["absolute", "relative"]
    step: DecimalString


class InputDefinitionRead(ApiModel):
    id: str
    label: str
    category: Literal["scenario_input", "market_baseline", "company_input", "assumption", "setting"]
    kind: Literal["decimal", "integer", "quantity", "currency", "graph_node"]
    description: str
    unit: str | None
    unit_label: str | None
    units: list[UnitChoice]
    minimum: DecimalString | None
    maximum: DecimalString | None
    minimum_exclusive: bool
    maximum_exclusive: bool
    max_decimals: int
    required: bool
    default: str | None
    rationale: str | None
    variable: str | None
    variable_name: str | None
    sources: list[ObservationSourceRead]
    sensitivity: SensitivitySpecRead | None


class TermRead(ApiModel):
    symbol: str
    meaning: str
    unit: str


class StatementRead(ApiModel):
    id: str
    text: str


class EquationRead(ApiModel):
    id: str
    name: str
    formula: str
    output: TermRead
    terms: list[TermRead]
    explanation: str
    scope: Literal["annual", "monthly", "horizon", "steady_state"]
    assumptions: list[str]
    limitations: list[str]


class OutputDefinitionRead(ApiModel):
    id: str
    label: str
    unit: str
    kind: Literal["derived", "simulated"]
    description: str
    equation: str
    attributable: bool


class GraphEdgeRead(ApiModel):
    rule: str
    role: Literal["transmission", "supporting"]
    edge_key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str
    is_illustrative: bool
    description: str


class TransmissionRuleRead(ApiModel):
    id: str
    edge_type: str
    source: str
    source_name: str | None
    target: str
    target_name: str | None
    coefficient_input: str
    lag_input: str | None
    form: str
    description: str
    graph_edge: GraphEdgeRead | None = Field(
        description="The confirming edge in the latest graph build, or null if the graph does "
        "not state it (then a shock needing it cannot run)."
    )


class SupportingRelationshipRead(ApiModel):
    id: str
    edge_type: str
    source: str
    target: str
    role: str
    required_with_entity: bool


class SimulationValidationRuleRead(ApiModel):
    id: str
    description: str
    severity: Literal["error", "warning"]


class PathwayLinkRead(ApiModel):
    source: str
    target: str
    label: str
    equations: list[str]
    rule: str | None


class BridgeItemRead(ApiModel):
    output: str
    sign: int
    label: str


class SimulationModelSummary(ApiModel):
    id: str
    version: str
    name: str
    summary: str
    domain: str
    status: Literal["preview", "active", "deprecated"]
    definition_hash: str
    versions: list[str]
    runs: int = Field(description="Stored runs of this model (all versions).")


class SimulationModelDetail(SimulationModelSummary):
    description: str
    inputs: list[InputDefinitionRead]
    equations: list[EquationRead]
    outputs: list[OutputDefinitionRead]
    monthly_outputs: list[OutputDefinitionRead]
    transmission_rules: list[TransmissionRuleRead]
    supporting_relationships: list[SupportingRelationshipRead]
    assumptions: list[StatementRead]
    limitations: list[StatementRead]
    validation_rules: list[SimulationValidationRuleRead]
    references: list[StatementRead]
    pathway: list[PathwayLinkRead]
    bridge: list[BridgeItemRead]
    bridge_total: str | None
    headline_outputs: list[str] = Field(description="The outputs a summary of a run leads with.")
    sensitivity_defaults: list[str]
    sensitivity_metric: str | None
    time_step: str
    max_horizon_months: int
    max_propagation_depth: int
    graph_build_id: int | None
    graph_freshness: Literal["current", "stale", "not_built"]


# --- Validation and runs ------------------------------------------------------------------------


class SimulationIssueRead(ApiModel):
    code: str
    message: str
    field: str | None


class SimulationObservationRead(ApiModel):
    series_id: str
    series_name: str
    series_unit: str
    frequency: str
    period_label: str
    period_start: str
    value: DecimalString
    raw_value: str | None
    quality_status: str
    revision: int
    last_confirmed_at: str
    capture_id: int | None
    job_id: str
    dataset_id: str
    dataset_version: str
    license: str
    attribution: str | None


Knowledge = Literal["scenario_input", "historical_data", "user_input", "assumption", "setting"]


class ResolvedInputRead(ApiModel):
    id: str
    label: str
    category: str
    knowledge: Knowledge
    source: Literal["user", "default", "stored_observation"]
    value: str | None
    unit: str | None
    unit_label: str
    default: str | None
    rationale: str | None
    variable: str | None
    observation: SimulationObservationRead | None


class EntityRead(ApiModel):
    key: str
    name: str
    nature: str


class UnusedEdgeRead(ApiModel):
    edge_key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str


class GraphSnapshotRead(ApiModel):
    build_id: int | None
    build_finished_at: str | None
    source_fingerprint: str | None
    freshness: str
    transmission: dict[str, GraphEdgeRead | None]
    supporting: dict[str, GraphEdgeRead | None]
    entity: EntityRead | None
    unused: list[UnusedEdgeRead] = Field(
        description="Graph relationships around the model's variables that no rule accepts: "
        "listed, never followed."
    )
    unused_total: int
    names: dict[str, str]


class ValidationReport(ApiModel):
    valid: bool
    model_id: str
    model_version: str
    definition_hash: str
    errors: list[SimulationIssueRead]
    warnings: list[SimulationIssueRead]
    inputs: list[ResolvedInputRead]
    graph: GraphSnapshotRead
    inputs_hash: str | None = Field(
        description="What the run's inputs hash will be (null while the inputs are invalid)."
    )


class OutputRead(ApiModel):
    id: str
    label: str
    value: DecimalString
    unit: str
    kind: Literal["derived", "simulated"]
    description: str
    equation: str


class MonthlySeriesRead(ApiModel):
    id: str
    label: str
    unit: str
    kind: Literal["derived", "simulated"]
    equation: str
    values: list[DecimalString]


class ContributionItemRead(ApiModel):
    input: str
    label: str
    value: DecimalString


class ContributionRead(ApiModel):
    output: str
    label: str
    items: list[ContributionItemRead]


class BridgeStepRead(ApiModel):
    output: str
    label: str
    sign: int
    value: DecimalString


class BridgeTotalRead(ApiModel):
    output: str
    value: DecimalString


class BridgeRead(ApiModel):
    steps: list[BridgeStepRead]
    total: BridgeTotalRead


class SimulationRunSummary(ApiModel):
    id: uuid.UUID
    model_id: str
    model_version: str
    label: str | None
    entity: EntityRead | None
    horizon_months: int
    created_at: datetime
    headline: list[OutputRead]
    result_hash: str


class SimulationRunRead(ApiModel):
    id: uuid.UUID
    model_id: str
    model_name: str
    model_version: str
    definition_hash: str
    status: Literal["completed"]
    label: str | None
    entity: EntityRead | None
    horizon_months: int
    inputs: list[ResolvedInputRead]
    outputs: list[OutputRead]
    monthly: list[MonthlySeriesRead]
    contributions: list[ContributionRead]
    bridge: BridgeRead | None
    warnings: list[SimulationIssueRead]
    limitations: list[StatementRead]
    inputs_hash: str
    result_hash: str
    engine_version: str
    random_seed: int | None
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    created_at: datetime
    sensitivity_analyses: int
    note: str = Field(
        description="What the numbers are, and are not, in one sentence.",
    )


SimulationRunPage = Page[SimulationRunSummary]


# --- Explanation and provenance -----------------------------------------------------------------


class StepValueRead(ApiModel):
    symbol: str
    value: DecimalString
    unit: str


class StepRead(ApiModel):
    sequence: int
    equation: str
    label: str
    month: int | None
    output: StepValueRead
    inputs: list[StepValueRead]


class EquationUseRead(ApiModel):
    id: str
    name: str
    formula: str
    output: TermRead
    terms: list[TermRead]
    explanation: str
    scope: str
    used: bool
    assumptions: list[StatementRead]
    limitations: list[StatementRead]


class PathwayNodeRead(ApiModel):
    id: str
    kind: Literal["input", "variable", "output"]
    label: str
    value: str | None
    unit: str | None
    knowledge: str


class PathwayEdgeRead(ApiModel):
    source: str
    target: str
    label: str
    equations: list[str]
    rule: str | None
    edge: GraphEdgeRead | None
    coefficient: str | None
    lag_months: str | None


class PathwayRead(ApiModel):
    nodes: list[PathwayNodeRead]
    links: list[PathwayEdgeRead]


class ParameterRead(ApiModel):
    id: str
    label: str
    value: str | None
    unit: str
    default: str | None
    source: str
    changed_from_default: bool
    rationale: str | None


class ExplanationRead(ApiModel):
    run_id: uuid.UUID
    equations: list[EquationUseRead]
    steps: list[StepRead]
    pathway: PathwayRead
    contributions: list[ContributionRead]
    bridge: BridgeRead | None
    parameters: list[ParameterRead]
    assumptions: list[StatementRead]
    limitations: list[StatementRead]
    warnings: list[SimulationIssueRead]
    method: dict[str, str]


class TransmissionPathRead(ApiModel):
    input: str
    nodes: list[str]
    rules: list[str]
    edge_keys: list[str | None]
    coefficient: DecimalString
    lag: int
    first_month: int
    log_change: DecimalString


class ModelVersionRead(ApiModel):
    model_id: str
    version: str
    name: str
    status: str
    definition_hash: str
    registered_at: datetime


class ProvenanceRead(ApiModel):
    run_id: uuid.UUID
    model: ModelVersionRead
    engine_version: str
    inputs_hash: str
    result_hash: str
    random_seed: int | None
    started_at: datetime
    finished_at: datetime
    created_at: datetime
    inputs: list[ResolvedInputRead]
    observations: list[SimulationObservationRead]
    graph: GraphSnapshotRead
    transmission: list[TransmissionPathRead]
    reproducibility: str


class VerificationRead(ApiModel):
    run_id: uuid.UUID
    reproduced: bool
    inputs_hash_matches: bool
    result_hash_matches: bool
    stored_result_hash: str
    recomputed_result_hash: str | None
    model_registered: bool
    definition_matches: bool
    graph_edges: list[dict[str, Any]] = Field(
        description="Whether each graph edge the run used is still current in the latest "
        "build (informational: verification re-uses the stored snapshot)."
    )
    message: str


# --- Sensitivity --------------------------------------------------------------------------------


class SensitivityPointRead(ApiModel):
    role: str
    value: str
    outputs: dict[str, DecimalString] | None
    deltas: dict[str, DecimalString] | None
    skipped: str | None


class SensitivityRangeRead(ApiModel):
    low: DecimalString
    high: DecimalString
    spread: DecimalString


class SensitivityItemRead(ApiModel):
    input: str
    label: str
    category: str
    unit: str | None
    base_value: str
    mode: str
    step: str | None
    points: list[SensitivityPointRead]
    range: SensitivityRangeRead | None


class SensitivityRankRead(ApiModel):
    input: str
    label: str
    spread: DecimalString


class SensitivityAnalysisRead(ApiModel):
    id: uuid.UUID
    run_id: uuid.UUID
    metric: str
    metric_label: str
    base: dict[str, DecimalString]
    items: list[SensitivityItemRead]
    ranking: list[SensitivityRankRead]
    evaluations: int
    duration_ms: int
    result_hash: str
    created_at: datetime
    note: str


class SensitivityAnalysisList(ApiModel):
    items: list[SensitivityAnalysisRead]
