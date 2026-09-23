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
