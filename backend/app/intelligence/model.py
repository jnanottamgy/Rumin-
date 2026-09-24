"""The shapes every intelligence result is made of, and how evidence is graded.

* A **reference** points at a stored record (an observation, a graph edge, an execution…)
  or a calculation, so every value can be followed back.
* A **step** is one link of an evidence chain, with its *basis*: an observation, a
  calculation on observations, a relationship from the knowledge graph (with its evidence
  status), one of RUMIN's own records, a simulation, an assumption or a threshold.
* A **fact** is one supporting value with its unit, basis and references.
* An **insight** is a statement produced by a named rule, with the facts, entities,
  relationships, period, models, evidence grade, assumptions, sources, limitations, chain
  and next steps it rests on. It cannot exist without a chain.

The **evidence grade** of a chain is its weakest step, strongest first:

    observed > documented > curated > simulated > assumed > unverified

* observed — stored observations and exact calculations on them, or RUMIN's own records;
* documented / curated / assumed / unverified — the evidence status of a graph relationship
  (evidence-backed, analyst-created, model assumption, unverified);
* simulated — a stored model output: deterministic, conditional on its inputs and
  assumptions, never a forecast.

The grade is not a probability. It says what kind of support the statement has.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from app.simulation.definitions import sha256


class Basis(StrEnum):
    OBSERVATION = "observation"
    CALCULATION = "calculation"
    RELATIONSHIP = "relationship"
    RECORD = "record"
    SIMULATION = "simulation"
    ASSUMPTION = "assumption"
    THRESHOLD = "threshold"


class Grade(StrEnum):
    OBSERVED = "observed"
    DOCUMENTED = "documented"
    CURATED = "curated"
    SIMULATED = "simulated"
    ASSUMED = "assumed"
    UNVERIFIED = "unverified"


GRADE_STRENGTH: dict[Grade, int] = {
    Grade.OBSERVED: 5,
    Grade.DOCUMENTED: 4,
    Grade.CURATED: 3,
    Grade.SIMULATED: 2,
    Grade.ASSUMED: 1,
    Grade.UNVERIFIED: 0,
}
EDGE_GRADE: dict[str, Grade] = {
    "evidence_backed": Grade.DOCUMENTED,
    "analyst_created": Grade.CURATED,
    "model_assumption": Grade.ASSUMED,
    "unverified": Grade.UNVERIFIED,
}
GRADE_STATEMENT: dict[Grade, str] = {
    Grade.OBSERVED: "Rests on stored observations, exact calculations on them and RUMIN's "
    "own records.",
    Grade.DOCUMENTED: "Rests on relationships stated by a cited external source "
    "(evidence-backed); RUMIN transcribed them and did not measure them.",
    Grade.CURATED: "Rests on relationships written by a RUMIN curator with their reasoning "
    "recorded; not an external source.",
    Grade.SIMULATED: "Rests on stored model outputs: deterministic results of the stated "
    "inputs and assumptions, not forecasts.",
    Grade.ASSUMED: "Rests on at least one relationship recorded as a model assumption: "
    "an assumed effect with a written rationale, not an empirical finding.",
    Grade.UNVERIFIED: "Rests on at least one relationship declared in supplied data that "
    "RUMIN could not check.",
}
CONDITIONAL_NOTE = (
    " Its figures are simulated: they hold only under the scenario's inputs and assumptions."
)


@dataclass(frozen=True)
class Ref:
    """A stored record or calculation. ``kind`` is one of: dataset, series, observation,
    instrument, price_bar, graph_build, graph_node, graph_edge, scenario, execution, run,
    sensitivity_analysis, calculation, threshold."""

    kind: str
    id: str
    label: str | None = None


@dataclass(frozen=True)
class Step:
    basis: Basis
    text: str
    refs: tuple[Ref, ...] = ()
    evidence_status: str | None = None  # relationship steps only
    value: str | None = None  # exact decimal text
    unit: str | None = None


@dataclass(frozen=True)
class Fact:
    label: str
    value: str | None
    unit: str | None
    basis: Basis
    refs: tuple[Ref, ...] = ()
    period: str | None = None


@dataclass(frozen=True)
class RelationshipRef:
    edge_key: str
    edge_type: str
    label: str
    source: str
    source_name: str
    target: str
    target_name: str
    evidence_status: str
    is_illustrative: bool


@dataclass(frozen=True)
class Period:
    """What the statement is about in time: periods of observations, a graph build, or a
    scenario's simulated months."""

    kind: str  # observation | graph_build | scenario | analysis
    label: str
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class ModelRef:
    kind: str  # execution | run
    id: str
    label: str
    models: tuple[str, ...] = ()  # "model_id version"


@dataclass(frozen=True)
class NextStep:
    action: str  # run_template | run_scenario | run_sensitivity | ingest_series |
    #              find_evidence | model_gap | review_revision
    text: str
    target: Ref | None = None


@dataclass(frozen=True)
class Evidence:
    grade: Grade
    conditional_on_simulation: bool
    includes_observations: bool
    statement: str
    weakest_step: int | None  # index in the chain of the step that set the grade


class ChainError(ValueError):
    """An insight was built without an evidence chain."""


def evidence_of(chain: Iterable[Step]) -> Evidence:
    """The grade of a chain: its weakest step (see the module docstring)."""
    steps = list(chain)
    if not steps:
        raise ChainError("An insight needs an evidence chain; none was given.")
    graded: list[tuple[Grade, int]] = []
    for index, step in enumerate(steps):
        if step.basis is Basis.RELATIONSHIP:
            if step.evidence_status not in EDGE_GRADE:
                raise ChainError(f"Relationship step {index} has no known evidence status.")
            graded.append((EDGE_GRADE[step.evidence_status], index))
        elif step.basis is Basis.SIMULATION:
            graded.append((Grade.SIMULATED, index))
        elif step.basis in (Basis.OBSERVATION, Basis.CALCULATION, Basis.RECORD):
            graded.append((Grade.OBSERVED, index))
    if not graded:
        raise ChainError(
            "An evidence chain needs at least one observation, record, relationship or simulation."
        )
    grade, weakest = min(graded, key=lambda item: (GRADE_STRENGTH[item[0]], item[1]))
    conditional = any(step.basis is Basis.SIMULATION for step in steps)
    statement = GRADE_STATEMENT[grade]
    if conditional and grade is not Grade.SIMULATED:
        statement += CONDITIONAL_NOTE
    return Evidence(
        grade=grade,
        conditional_on_simulation=conditional,
        includes_observations=any(step.basis is Basis.OBSERVATION for step in steps),
        statement=statement,
        weakest_step=weakest,
    )


@dataclass(frozen=True)
class Insight:
    id: str
    rule: str
    kind: str
    headline: str
    statement: str
    subject: Ref
    entities: tuple[Ref, ...]
    relationships: tuple[RelationshipRef, ...]
    period: Period
    facts: tuple[Fact, ...]
    models: tuple[ModelRef, ...]
    evidence: Evidence
    chain: tuple[Step, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    next_steps: tuple[NextStep, ...]
    sources: tuple[Ref, ...]


def insight_id(rule: str, subject: Ref, key: object) -> str:
    """Stable for the same rule, subject and facts: recomputing gives the same id."""
    return "ins-" + sha256({"rule": rule, "subject": subject, "key": key})[:16]


@dataclass
class InsightDraft:
    """Mutable while a rule assembles it; ``build`` checks the chain and grades it."""

    rule: str
    kind: str
    headline: str
    statement: str
    subject: Ref
    key: object
    period: Period
    chain: list[Step] = field(default_factory=list)
    entities: list[Ref] = field(default_factory=list)
    relationships: list[RelationshipRef] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    models: list[ModelRef] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    next_steps: list[NextStep] = field(default_factory=list)
    sources: list[Ref] = field(default_factory=list)

    def build(self) -> Insight:
        chain = _unique(self.chain)  # a repeated link adds nothing to the chain
        return Insight(
            id=insight_id(self.rule, self.subject, self.key),
            rule=self.rule,
            kind=self.kind,
            headline=self.headline,
            statement=self.statement,
            subject=self.subject,
            entities=tuple(_unique(self.entities)),
            relationships=tuple(_unique(self.relationships)),
            period=self.period,
            facts=tuple(self.facts),
            models=tuple(_unique(self.models)),
            evidence=evidence_of(chain),
            chain=tuple(chain),
            assumptions=tuple(_unique(self.assumptions)),
            limitations=tuple(_unique(self.limitations)),
            next_steps=tuple(_unique(self.next_steps)),
            sources=tuple(_unique(self.sources)),
        )


T = TypeVar("T")


def _unique(items: Iterable[T]) -> list[T]:
    seen: list[T] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
