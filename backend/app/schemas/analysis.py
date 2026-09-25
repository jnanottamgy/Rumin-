"""Requests and responses for the advanced analyses of a scenario execution (Phase 9):
what an execution can vary, Monte Carlo analyses and joint sensitivity grids."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from app.scenario_lab.sampling import MAX_DISCRETE_VALUES, MAX_SEED
from app.schemas.common import ApiModel, DecimalString, InputModel
from app.schemas.scenario import METRIC_ID, TARGET_ID, LabSensitivityItemInput
from app.schemas.simulation import NumberInput

TargetKind = Literal["change", "shared", "company", "market", "assumption"]
MetricKind = Literal["line_change", "metric_value"]
AnalysisKind = Literal["monte_carlo", "joint_sensitivity"]

# --- What an execution can vary -----------------------------------------------------------------


class DefaultVariationRead(ApiModel):
    mode: Literal["absolute", "relative"]
    step: DecimalString


class AnalysisTargetRead(ApiModel):
    id: str = Field(examples=["change:var_brent_crude"])
    label: str
    kind: TargetKind
    models: list[str] = Field(description="Every included model that uses the quantity.")
    unit: str | None
    unit_label: str
    integer: bool = Field(description="Whole months: only discrete distributions apply.")
    base_value: DecimalString = Field(description="The execution's value.")
    minimum: DecimalString | None
    maximum: DecimalString | None
    minimum_exclusive: bool
    maximum_exclusive: bool
    max_decimals: int
    default_variation: DefaultVariationRead | None = Field(
        description="The model's default low/high variation for sensitivity analysis."
    )


class AnalysisMetricRead(ApiModel):
    id: str
    label: str
    kind: MetricKind
    base: DecimalString = Field(description="The execution's value: a line's change or a metric.")


class MonteCarloLimitsRead(ApiModel):
    min_draws: int
    max_draws: int
    default_draws: int
    max_quantities: int
    max_discrete_values: int
    min_accepted: int
    deadline_seconds: float


class JointLimitsRead(ApiModel):
    max_axis_points: int
    deadline_seconds: float


class SensitivityLimitsRead(ApiModel):
    max_items: int
    max_points: int
    max_evaluations: int


class AnalysisLimitsRead(ApiModel):
    monte_carlo: MonteCarloLimitsRead
    joint: JointLimitsRead
    sensitivity: SensitivityLimitsRead


class AnalysisTargetsRead(ApiModel):
    execution_id: uuid.UUID
    currency: str | None
    horizon_months: int
    targets: list[AnalysisTargetRead]
    metrics: list[AnalysisMetricRead]
    limits: AnalysisLimitsRead


# --- Requests -----------------------------------------------------------------------------------


class UniformInput(InputModel):
    kind: Literal["uniform"]
    low: NumberInput
    high: NumberInput


class TriangularInput(InputModel):
    kind: Literal["triangular"]
    low: NumberInput
    mode: NumberInput = Field(description="The most likely value.")
    high: NumberInput


class DiscreteInput(InputModel):
    kind: Literal["discrete"]
    values: list[NumberInput] = Field(min_length=2, max_length=MAX_DISCRETE_VALUES)
    weights: list[NumberInput] | None = Field(
        default=None,
        min_length=2,
        max_length=MAX_DISCRETE_VALUES,
        description="Positive, one per value. Default: equal weights.",
    )


DistributionInput = Annotated[
    UniformInput | TriangularInput | DiscreteInput, Field(discriminator="kind")
]


class QuantityInput(InputModel):
    target: str = Field(
        pattern=TARGET_ID,
        description="`change:<variable>`, `shared:<input>` or `model:<model>:<input>`.",
        examples=["change:var_brent_crude"],
    )
    distribution: DistributionInput


class MonteCarloRequest(InputModel):
    kind: Literal["monte_carlo"]
    metric: str | None = Field(
        default=None,
        pattern=METRIC_ID,
        description="A line (its change) or a metric. Default: profit before tax when "
        "interest is modelled, otherwise operating profit.",
    )
    quantities: list[QuantityInput] = Field(min_length=1, max_length=8)
    draws: StrictInt = Field(default=500, ge=100, le=2_000)
    seed: StrictInt | None = Field(
        default=None,
        ge=0,
        le=MAX_SEED,
        description="Reproduces the draws exactly. Chosen by the server (and recorded) when "
        "not given.",
    )
    threshold: NumberInput | None = Field(
        default=None,
        description="Also report the share of draws at or below this value (a covenant level, "
        "say).",
    )


class JointSensitivityRequest(InputModel):
    kind: Literal["joint_sensitivity"]
    metric: str | None = Field(default=None, pattern=METRIC_ID)
    rows: LabSensitivityItemInput
    columns: LabSensitivityItemInput


AnalysisRequest = Annotated[
    MonteCarloRequest | JointSensitivityRequest, Field(discriminator="kind")
]


# --- Monte Carlo results ------------------------------------------------------------------------


class DistributionRead(ApiModel):
    kind: Literal["uniform", "triangular", "discrete"]
    low: DecimalString | None = None
    mode: DecimalString | None = None
    high: DecimalString | None = None
    values: list[DecimalString] | None = None
    weights: list[DecimalString] | None = None


class MonteCarloQuantityRead(ApiModel):
    target: str
    label: str
    kind: TargetKind
    models: list[str]
    unit: str | None
    base_value: DecimalString
    distribution: DistributionRead
    distribution_mean: DecimalString
    distribution_sd: DecimalString
    accepted_mean: DecimalString = Field(description="The mean of the accepted draws' values.")
    rank_correlation: DecimalString | None = Field(
        description="Spearman's rank correlation with the line or metric; null when either "
        "does not vary. Monotonic association in the sample, not causation."
    )


class PercentileIntervalRead(ApiModel):
    lower: DecimalString
    upper: DecimalString
    lower_rank: int
    upper_rank: int
    coverage: DecimalString = Field(
        description="The exact probability that the interval contains the percentile."
    )


class PercentileRead(ApiModel):
    p: int
    value: DecimalString
    interval: PercentileIntervalRead | None


class MonteCarloSummaryRead(ApiModel):
    mean: DecimalString
    standard_deviation: DecimalString
    standard_error: DecimalString = Field(description="Of the mean: s/√n.")
    relative_standard_error: DecimalString | None
    minimum: DecimalString
    maximum: DecimalString
    percentiles: list[PercentileRead]
    share_below_zero: DecimalString | None = Field(
        description="For a line's change: the share of accepted draws below zero."
    )
    threshold: DecimalString | None
    share_at_or_below_threshold: DecimalString | None


class HistogramBinRead(ApiModel):
    low: DecimalString
    high: DecimalString
    count: int


class CheckpointRead(ApiModel):
    draws: int
    mean: DecimalString
    standard_error: DecimalString | None


class ConvergenceRead(ApiModel):
    checkpoints: list[CheckpointRead]
    first_half_mean: DecimalString
    second_half_mean: DecimalString
    halves_z: DecimalString | None
    halves_flagged: bool


class OutputSummaryRead(ApiModel):
    id: str
    label: str
    kind: MetricKind
    base: DecimalString
    mean: DecimalString
    p5: DecimalString
    p50: DecimalString
    p95: DecimalString


class RejectionRead(ApiModel):
    code: str
    count: int
    example: str


class MonteCarloResultsRead(ApiModel):
    metric: str
    metric_label: str
    metric_kind: MetricKind
    base: DecimalString
    draws: int
    accepted: int
    rejected: int
    rejections: list[RejectionRead]
    quantities: list[MonteCarloQuantityRead]
    summary: MonteCarloSummaryRead
    histogram: list[HistogramBinRead]
    convergence: ConvergenceRead
    outputs: list[OutputSummaryRead]
    notes: list[str]


# --- Joint sensitivity results ------------------------------------------------------------------


class JointAxisRead(ApiModel):
    target: str
    label: str
    kind: TargetKind
    models: list[str]
    unit: str | None
    base_value: DecimalString
    values: list[DecimalString]


class JointCellRead(ApiModel):
    metric: DecimalString | None
    delta: DecimalString | None
    interaction: DecimalString | None
    skipped: str | None


class JointCellRefRead(ApiModel):
    row: int
    column: int
    value: DecimalString


class JointSummaryRead(ApiModel):
    largest_interaction: JointCellRefRead | None
    largest_change: JointCellRefRead | None
    interactions_computed: int
    additive: bool
    tolerance: DecimalString
    skipped: int


class JointResultsRead(ApiModel):
    metric: str
    metric_label: str
    metric_kind: MetricKind
    base: DecimalString
    rows: JointAxisRead
    columns: JointAxisRead
    cells: list[list[JointCellRead]]
    summary: JointSummaryRead


# --- Stored analyses ------------------------------------------------------------------------------


class AnalysisRunRead(ApiModel):
    model_id: str
    version: str
    definition_hash: str
    run_id: uuid.UUID
    inputs_hash: str
    graph_build_id: int | None
    graph_fingerprint: str | None


class AnalysisConfigRead(ApiModel):
    analysis_version: str
    lab_version: str
    engine_version: str
    execution_result_hash: str | None
    runs: list[AnalysisRunRead]
    seed: int | None
    generator: str | None
    sampler_version: str | None
    draws: int | None


class ScenarioAnalysisRead(ApiModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    kind: AnalysisKind
    metric: str
    request: dict[str, Any] = Field(description="The normalised request, exactly as run.")
    config: AnalysisConfigRead
    monte_carlo: MonteCarloResultsRead | None
    joint: JointResultsRead | None
    evaluations: int
    duration_ms: int
    inputs_hash: str
    result_hash: str
    created_at: datetime
    note: str


class ScenarioAnalysisSummaryRead(ApiModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    kind: AnalysisKind
    metric: str
    metric_label: str
    quantities: list[str] = Field(description="The labels of the quantities varied.")
    draws: int | None
    seed: int | None
    accepted: int | None
    mean: DecimalString | None
    largest_interaction: DecimalString | None
    evaluations: int
    duration_ms: int
    result_hash: str
    created_at: datetime


class ScenarioAnalysisList(ApiModel):
    items: list[ScenarioAnalysisSummaryRead]


class AnalysisVerificationRead(ApiModel):
    analysis_id: uuid.UUID
    reproduced: bool
    inputs_hash_matches: bool
    result_hash_matches: bool
    stored_result_hash: str
    recomputed_result_hash: str | None
    message: str
