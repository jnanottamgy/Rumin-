"""Enumerations that define RUMIN's financial domain vocabulary."""

from __future__ import annotations

from enum import StrEnum


class EpistemicCategory(StrEnum):
    """What kind of knowledge a value represents. RUMIN never blurs these categories.

    * ``observation`` — historical data collected from a cited source.
    * ``assumption`` — a rule, parameter or relationship defined by the model.
    * ``scenario_input`` — a value changed by the user to explore "what if".
    * ``simulated_output`` — a value computed by a simulation engine.
    * ``uncertainty`` — limitations and ranges attached to any of the above.
    """

    OBSERVATION = "observation"
    ASSUMPTION = "assumption"
    SCENARIO_INPUT = "scenario_input"
    SIMULATED_OUTPUT = "simulated_output"
    UNCERTAINTY = "uncertainty"


class EntityKind(StrEnum):
    COMPANY = "company"
    INDUSTRY = "industry"
    COUNTRY = "country"
    ECONOMIC_VARIABLE = "economic_variable"


class RelationshipType(StrEnum):
    """Curated relationships stored in the database (economic assertions)."""

    SUPPLIES_TO = "supplies_to"
    LENDS_TO = "lends_to"
    COMPETES_WITH = "competes_with"
    AFFECTS_COSTS = "affects_costs"
    AFFECTS_REVENUE = "affects_revenue"
    AFFECTS_FINANCING = "affects_financing"
    INFLUENCES = "influences"


class StructuralLinkType(StrEnum):
    """Links derived from entity attributes (never stored as relationship rows)."""

    IN_INDUSTRY = "in_industry"
    DOMICILED_IN = "domiciled_in"
    MEASURED_FOR = "measured_for"


class RelationshipCategory(StrEnum):
    ECONOMIC = "economic"
    STRUCTURAL = "structural"


class Polarity(StrEnum):
    """Assumed direction of effect: does an *increase* in the source raise the target?"""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NOT_APPLICABLE = "not_applicable"


class Strength(StrEnum):
    """Ordinal, illustrative strength. Deliberately not a precise-looking number."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class EvidenceLevel(StrEnum):
    """How well a relationship is supported. Phase 1 data is entirely ``illustrative``.

    * ``illustrative`` — constructed to demonstrate the model; not evidence-based.
    * ``documented`` — qualitatively supported by a cited public source.
    * ``estimated`` — quantified by a documented statistical estimate.
    * ``validated`` — an estimate that has also been validated out of sample.
    """

    ILLUSTRATIVE = "illustrative"
    DOCUMENTED = "documented"
    ESTIMATED = "estimated"
    VALIDATED = "validated"


class ValueKind(StrEnum):
    """How a variable's values behave; determines which scenario changes make sense."""

    PRICE = "price"
    RATE = "rate"
    EXCHANGE_RATE = "exchange_rate"
    INDEX = "index"


class Frequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    IRREGULAR = "irregular"


class VariableCategory(StrEnum):
    COMMODITY = "commodity"
    MONETARY_POLICY = "monetary_policy"
    EXCHANGE_RATE = "exchange_rate"
    INFLATION = "inflation"


class ChangeType(StrEnum):
    PERCENT_CHANGE = "percent_change"
    ABSOLUTE_CHANGE = "absolute_change"


class ScenarioStatus(StrEnum):
    """Phase 1 only supports drafts. Simulation runs arrive in Phase 4 as a separate
    resource, so a scenario's configuration and its results are never conflated."""

    DRAFT = "draft"


# --- Phase 2: financial data infrastructure ------------------------------------------------


class DatasetKind(StrEnum):
    """Where a dataset's records came from.

    * ``curated`` — reference data written for RUMIN and loaded from a file in the
      repository (the Phase 1 illustrative network).
    * ``provider`` — data retrieved from an external provider (an API or a file the user
      is licensed to use), with the provider's licence and attribution.
    """

    CURATED = "curated"
    PROVIDER = "provider"


class ProviderKind(StrEnum):
    API = "api"
    FILE = "file"


class ProviderAuth(StrEnum):
    NONE = "none"
    API_KEY = "api_key"
    NOT_APPLICABLE = "not_applicable"


class MeasureType(StrEnum):
    """What a series' numbers are, so they are never read as something else.

    * ``level`` — an amount, price or index level (e.g. GDP in current US$).
    * ``change`` — a growth rate or percentage change (e.g. annual CPI inflation).
    * ``rate`` — an interest rate or yield, in percent per annum.
    * ``ratio`` — a share of another quantity (e.g. exports as % of GDP).
    * ``exchange_rate`` — units of one currency per unit of another.
    """

    LEVEL = "level"
    CHANGE = "change"
    RATE = "rate"
    RATIO = "ratio"
    EXCHANGE_RATE = "exchange_rate"


class PriceBasis(StrEnum):
    """Nominal (current prices) versus real (inflation-adjusted, constant prices)."""

    NOMINAL = "nominal"
    REAL = "real"
    NOT_APPLICABLE = "not_applicable"


class SeasonalAdjustment(StrEnum):
    SEASONALLY_ADJUSTED = "seasonally_adjusted"
    NOT_SEASONALLY_ADJUSTED = "not_seasonally_adjusted"
    NOT_APPLICABLE = "not_applicable"


class ObservationStatus(StrEnum):
    """``reported`` carries a value; ``missing`` means the provider listed the period
    without a value. RUMIN records the gap and never fills it in."""

    REPORTED = "reported"
    MISSING = "missing"


class QualityStatus(StrEnum):
    """Quality of a *stored* record. Rejected records are never stored as data; they are
    kept as data-quality issues with the raw record and the reason."""

    VALIDATED = "validated"
    WARNING = "warning"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueOutcome(StrEnum):
    """What happened to the record the issue is about."""

    REJECTED = "rejected"  # not stored
    FLAGGED = "flagged"  # stored with quality status ``warning``
    NOTED = "noted"  # stored; informational only


class ReviewStatus(StrEnum):
    """Human review state of an issue. There is no review workflow yet, so every issue
    stays ``unreviewed``; the column exists so one can be added without a migration."""

    UNREVIEWED = "unreviewed"


class JobStatus(StrEnum):
    """Lifecycle of an ingestion job. The final status always reflects what happened:

    * ``completed`` — every target succeeded; nothing was rejected or flagged.
    * ``completed_with_warnings`` — every target succeeded, but some records were
      rejected or flagged, or a target returned no data.
    * ``partially_failed`` — some targets failed and others succeeded.
    * ``failed`` — no target succeeded, or the job could not run.
    * ``cancelled`` — stopped before finishing (e.g. interrupted from the keyboard).
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobItemStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobTrigger(StrEnum):
    """Who started a job. Phase 2 starts jobs from the command line only."""

    CLI = "cli"


class JobTargetKind(StrEnum):
    ECONOMIC_SERIES = "economic_series"
    INSTRUMENT = "instrument"


class CaptureKind(StrEnum):
    HTTP_RESPONSE = "http_response"
    FILE = "file"


class InstrumentType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"


class PriceAdjustment(StrEnum):
    """Whether open/high/low/close are as traded (``unadjusted``) or adjusted for
    corporate actions by the source (``adjusted``). RUMIN never adjusts prices itself."""

    UNADJUSTED = "unadjusted"
    ADJUSTED = "adjusted"
