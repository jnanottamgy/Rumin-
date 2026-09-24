"""Answers: what the Analyst returns for one question.

An answer is a headline and a list of **blocks**: paragraphs of text that cite evidence
(``[E1]``), tables, stored series, relationship paths, scenario cards, notices and
clarifying choices. Tables, series, paths and scenario cards are built by RUMIN from tool
results — never written by a language model — so each of their figures comes straight from
a service. Paragraphs carry a **role** that says what kind of statement they are:

* ``answer`` and ``detail`` — statements from the evidence they cite;
* ``interpretation`` — a reading of that evidence (by a language model), labelled as such;
* ``general`` — general knowledge, not from RUMIN's records, labelled as such;
* ``policy`` — what the Analyst does not do and why.

Interpretation and general paragraphs may not contain figures (``grounding.py``).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field

from app.analyst.evidence import Evidence
from app.schemas.common import ApiModel

CITATION = re.compile(r"\[(E\d+(?:\s*,\s*E\d+)*)\]")

TextRole = Literal["answer", "detail", "interpretation", "general", "policy"]
AnswerStatus = Literal[
    "answered", "partial", "no_data", "clarification", "declined", "unsupported", "failed"
]
NoticeKind = Literal[
    "missing_data",
    "assumption",
    "limitation",
    "conflict",
    "policy",
    "not_stored",
    "illustrative",
    "fallback",
]


def citations_in(text: str) -> list[str]:
    """The evidence ids ``text`` cites, in order of first appearance."""
    found: list[str] = []
    for group in CITATION.findall(text):
        for item in group.split(","):
            evidence_id = item.strip()
            if evidence_id not in found:
                found.append(evidence_id)
    return found


class TextBlock(ApiModel):
    type: Literal["text"] = "text"
    role: TextRole
    text: str = Field(description="Cites evidence inline as [E1] or [E1, E4].")
    citations: list[str] = Field(default_factory=list)


class Column(ApiModel):
    key: str
    label: str
    align: Literal["start", "end"] = "start"


class TableRow(ApiModel):
    cells: dict[str, str | None]
    link: str | None = None
    citations: list[str] = Field(default_factory=list)


class TableBlock(ApiModel):
    type: Literal["table"] = "table"
    title: str
    columns: list[Column]
    rows: list[TableRow]
    total: int | None = Field(default=None, description="Rows available when more exist.")
    note: str | None = None
    citations: list[str] = Field(default_factory=list)


class SeriesPoint(ApiModel):
    period: str
    start: str = Field(description="ISO date the period starts.")
    value: str


class SeriesBlock(ApiModel):
    type: Literal["series"] = "series"
    title: str
    series_id: str
    unit: str
    frequency: str
    points: list[SeriesPoint]
    highlight: list[str] = Field(default_factory=list, description="Periods to mark.")
    link: str | None = None
    note: str | None = None
    citations: list[str] = Field(default_factory=list)


class PathStep(ApiModel):
    key: str
    name: str
    kind: str
    link: str | None = None


class PathLink(ApiModel):
    key: str
    label: str
    evidence_status: str | None = None
    illustrative: bool = False


class PathItem(ApiModel):
    steps: list[PathStep]
    links: list[PathLink] = Field(description="Between consecutive steps.")
    channel: str | None = None
    directness: str | None = None
    evidence_status: str | None = None
    models: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class PathsBlock(ApiModel):
    type: Literal["paths"] = "paths"
    title: str
    paths: list[PathItem]
    total: int
    note: str | None = None
    citations: list[str] = Field(default_factory=list)


class ScenarioChange(ApiModel):
    variable_id: str
    name: str
    change_type: str
    value: str
    unit: str
    modelled: bool | None = None


class ScenarioLine(ApiModel):
    id: str
    label: str
    currency: str
    baseline: str | None = None
    change: str
    scenario: str | None = None
    percent_change: str | None = None
    citations: list[str] = Field(default_factory=list)


class EntityRef(ApiModel):
    key: str
    name: str
    link: str | None = None


class ScenarioBlock(ApiModel):
    """A stored execution, a preview computed on request, or a plan that still needs figures."""

    type: Literal["scenario"] = "scenario"
    status: Literal["stored", "preview", "plan"]
    title: str
    entity: EntityRef | None = None
    changes: list[ScenarioChange]
    horizon_months: int | None = None
    lines: list[ScenarioLine] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list, description="'model_id version' or ids.")
    missing: list[str] = Field(
        default_factory=list, description="Figures a person must enter before it can run."
    )
    headline: str | None = None
    scenario_id: str | None = None
    execution_id: str | None = None
    link: str | None = None
    draft: dict[str, Any] | None = Field(
        default=None,
        description="A scenario body to open in the Scenario Lab; nothing is saved until a "
        "person saves it there.",
    )
    notes: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class NoticeBlock(ApiModel):
    type: Literal["notice"] = "notice"
    kind: NoticeKind
    title: str
    text: str
    citations: list[str] = Field(default_factory=list)


class ClarificationOption(ApiModel):
    label: str
    question: str = Field(description="The question to ask instead, if this option is chosen.")


class ClarificationBlock(ApiModel):
    type: Literal["clarification"] = "clarification"
    question: str
    options: list[ClarificationOption]


Block = Annotated[
    TextBlock
    | TableBlock
    | SeriesBlock
    | PathsBlock
    | ScenarioBlock
    | NoticeBlock
    | ClarificationBlock,
    Field(discriminator="type"),
]


class GroundingProblem(ApiModel):
    block: int | None = Field(description="Index of the block; null for the headline.")
    text: str = Field(description="The sentence or figure concerned.")
    reason: str


class GroundingRead(ApiModel):
    passed: bool
    figures_checked: int
    citations_checked: int
    problems: list[GroundingProblem]


class Answer(ApiModel):
    status: AnswerStatus
    intent: str
    headline: str
    blocks: list[Block]
    evidence: list[Evidence]
    follow_ups: list[str] = Field(default_factory=list)
    provider: str = Field(description="What composed the answer: grounded, anthropic, scripted.")
    grounding: GroundingRead | None = None


def text(role: TextRole, body: str) -> TextBlock:
    """A paragraph, with its citations read from the text."""
    return TextBlock(role=role, text=body, citations=citations_in(body))


def cite(*ids: str | None) -> str:
    """`` [E1, E3]`` for the ids given (empty ids skipped, order kept, no repeats)."""
    unique: list[str] = []
    for item in ids:
        if item and item not in unique:
            unique.append(item)
    return f" [{', '.join(unique)}]" if unique else ""
