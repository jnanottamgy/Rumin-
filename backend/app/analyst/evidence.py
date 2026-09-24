"""Evidence: what an answer may cite.

Every tool result is turned into **evidence records**, each with a short id (``E1``,
``E2`` …) that answer text cites. A record says what kind of knowledge it is, which stored
record it comes from (with a link to it), for which period, when it was retrieved, in which
units, with what provenance, and — for simulated results — which models, versions and
assumptions produced it. Its ``values`` are the figures it supports: the grounding check
(``grounding.py``) accepts a figure in the text only if a cited record carries it. Values that
are percentages or percentage-point changes say so (``value_units``), so that "3 %" is never
matched against a count of 3 or an amount.

The same stored record reached by two tools is one piece of evidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from urllib.parse import quote

from pydantic import Field

from app.schemas.common import ApiModel


class Knowledge(StrEnum):
    """What kind of knowledge a piece of evidence is, strongest claim to fact first."""

    OBSERVED = "observed"  # stored observations (Phase 2)
    RECORD = "record"  # RUMIN's own records: catalogue, graph builds, registries
    RELATIONSHIP = "relationship"  # a knowledge-graph edge; its evidence status says which kind
    FINDING = "finding"  # a Financial Intelligence finding, with its grade
    USER_INPUT = "user_input"  # figures a person entered in a scenario
    ASSUMPTION = "assumption"  # a model assumption or a stated default
    SIMULATED = "simulated"  # a stored execution or model run
    PREVIEW = "preview"  # computed on request by the models and not stored


KNOWLEDGE_LABEL: dict[Knowledge, str] = {
    Knowledge.OBSERVED: "Observed data",
    Knowledge.RECORD: "RUMIN record",
    Knowledge.RELATIONSHIP: "Relationship",
    Knowledge.FINDING: "Finding",
    Knowledge.USER_INPUT: "Figure entered by a user",
    Knowledge.ASSUMPTION: "Model assumption",
    Knowledge.SIMULATED: "Simulated result",
    Knowledge.PREVIEW: "Preview, not stored",
}


ValueUnit = Literal["percent", "points"]
# Values that are percentages by their name, wherever they are recorded.
_PERCENT_NAMES = ("percent_change", ".share", "strict_equivalent")


def percent_unit(unit: str | None) -> bool:
    """Whether a unit is a percentage: 'percent per annum', '% change on previous year' …"""
    text = (unit or "").lower()
    return "%" in text or "percent" in text


def change_unit(change_type: str, variable_unit: str | None) -> ValueUnit | None:
    """What a stated change's value is: a percentage for a percentage change; percentage
    points for an absolute change to a variable measured in percent (a rate); otherwise the
    variable's own unit (``None``)."""
    if change_type == "percent_change":
        return "percent"
    return "points" if percent_unit(variable_unit) else None


def fact_unit(label: str, unit: str | None) -> ValueUnit | None:
    """Whether a finding's figure is a percentage or a change in percentage points. A figure
    in a rate's unit ('percent per annum', '% change on previous year') is a percentage when
    it is a value, and percentage points when it is a change."""
    text = (unit or "").lower().replace("_", " ").strip()
    if text in ("percentage points", "percentage point", "pp", "points"):
        return "points"
    if text in ("percent", "%"):
        return "percent"
    if percent_unit(text):
        return "points" if re.search(r"change|revision|difference", label, re.I) else "percent"
    return None


def series_units(
    measure: str,
    *,
    levels: Iterable[str] = (),
    changes: Iterable[str] = (),
    differences: Iterable[str] = (),
) -> dict[str, ValueUnit]:
    """Which of a series' values are percentages or percentage points.

    ``measure`` is the series' measure as Financial Intelligence reads it: ``relative`` for
    levels and exchange rates (their changes are percentages), ``points`` for rates, ratios
    and growth rates (their values are percentages, their changes percentage points).
    ``levels`` are stored values, ``changes`` changes as RUMIN computes them for the
    measure, ``differences`` plain differences in the series' unit."""
    units: dict[str, ValueUnit] = {}
    if measure == "points":
        units.update({key: "percent" for key in levels})
        units.update({key: "points" for key in (*changes, *differences)})
    else:
        units.update({key: "percent" for key in changes})
    return units


class SourceRef(ApiModel):
    """The stored record a piece of evidence comes from."""

    kind: str = Field(
        description="graph_node, graph_edge, graph_build, series, instrument, dataset, "
        "scenario, execution, run, model, template, insight or catalogue."
    )
    id: str
    label: str
    link: str | None = Field(default=None, description="Where the record can be opened.")


class Evidence(ApiModel):
    id: str = Field(description="Cited in answer text as [E1], [E2] …")
    tool: str = Field(description="The tool whose result it came from.")
    call: int = Field(description="The position of that tool call in the turn (1-based).")
    kind: Knowledge
    title: str
    detail: str | None = None
    source: SourceRef
    period: str | None = Field(default=None, description="The period the figures describe.")
    as_of: str | None = Field(
        default=None, description="The data's own date: a period, or when a build finished."
    )
    retrieved_at: datetime = Field(description="When the tool read it.")
    unit: str | None = None
    currency: str | None = None
    provenance: dict[str, str] = Field(
        default_factory=dict, description="Dataset, licence, provider, build … as available."
    )
    evidence_status: str | None = Field(
        default=None, description="For relationships: evidence-backed, analyst-created, …"
    )
    grade: str | None = Field(default=None, description="For findings: the evidence grade.")
    models: list[str] = Field(
        default_factory=list, description="For simulated results: 'model_id version'."
    )
    assumptions: list[str] = Field(default_factory=list)
    values: dict[str, str] = Field(
        default_factory=dict,
        description="The figures this record supports, as exact decimal strings.",
    )
    value_units: dict[str, ValueUnit] = Field(
        default_factory=dict,
        description="For the values that are percentages ('percent') or changes in percentage "
        "points ('points'). Every other value is in the record's unit or currency, or is a "
        "count.",
    )


def exact(value: Decimal | int | str | None) -> str | None:
    """A figure as an exact plain decimal string (``None`` stays ``None``)."""
    if value is None:
        return None
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class EvidenceLedger:
    """The evidence of one turn, in the order it was found."""

    def __init__(self) -> None:
        self._items: list[Evidence] = []
        self._by_key: dict[tuple[str, str, str | None, str], Evidence] = {}

    def add(
        self,
        *,
        tool: str,
        call: int,
        kind: Knowledge,
        title: str,
        source: SourceRef,
        retrieved_at: datetime,
        detail: str | None = None,
        period: str | None = None,
        as_of: str | None = None,
        unit: str | None = None,
        currency: str | None = None,
        provenance: Mapping[str, str | None] | None = None,
        evidence_status: str | None = None,
        grade: str | None = None,
        models: Iterable[str] = (),
        assumptions: Iterable[str] = (),
        values: Mapping[str, Decimal | int | str | None] | None = None,
        value_units: Mapping[str, ValueUnit | None] | None = None,
    ) -> str:
        """Record a piece of evidence (or add figures to one already recorded for the same
        source, period and kind) and return its id. ``value_units`` says which values are
        percentages or percentage points; values named as percentages (``…percent_change``,
        ``….share``) are marked without being listed."""
        clean = {
            label: text
            for label, value in (values or {}).items()
            if (text := exact(value)) is not None
        }
        stated = {k: v for k, v in (value_units or {}).items() if v is not None}
        units: dict[str, ValueUnit] = {
            label: stated.get(label) or "percent"
            for label in clean
            if label in stated or label.endswith(_PERCENT_NAMES)
        }
        key = (source.kind, source.id, period, kind.value)
        existing = self._by_key.get(key)
        if existing is not None:
            for label, text in clean.items():
                if label not in existing.values:
                    existing.values[label] = text
                    if label in units:
                        existing.value_units[label] = units[label]
            return existing.id
        item = Evidence(
            id=f"E{len(self._items) + 1}",
            tool=tool,
            call=call,
            kind=kind,
            title=title,
            detail=detail,
            source=source,
            period=period,
            as_of=as_of,
            retrieved_at=retrieved_at,
            unit=unit,
            currency=currency,
            provenance={k: v for k, v in (provenance or {}).items() if v},
            evidence_status=evidence_status,
            grade=grade,
            models=list(models),
            assumptions=list(assumptions),
            values=clean,
            value_units=units,
        )
        self._items.append(item)
        self._by_key[key] = item
        return item.id

    def get(self, evidence_id: str) -> Evidence | None:
        return next((item for item in self._items if item.id == evidence_id), None)

    def ids_for(self, kind: str, record_id: str) -> list[str]:
        return [
            item.id
            for item in self._items
            if item.source.kind == kind and item.source.id == record_id
        ]

    @property
    def items(self) -> list[Evidence]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


# --- Links to the records, as the web app routes them --------------------------------------


def node_link(key: str) -> str:
    if key.startswith(("company:", "industry:")):
        return f"/intelligence/{quote(key, safe='')}"
    if key.startswith("series:"):
        return f"/data/series/{quote(key.partition(':')[2], safe='')}"
    return f"/graph?focus={quote(key, safe='')}"


def series_link(series_id: str) -> str:
    return f"/data/series/{quote(series_id, safe='')}"


def instrument_link(instrument_id: str) -> str:
    return f"/data/instruments/{quote(instrument_id, safe='')}"


def scenario_link(scenario_id: str, execution_id: str | None = None) -> str:
    base = f"/scenarios/{quote(scenario_id, safe='')}"
    return f"{base}?execution={quote(execution_id, safe='')}" if execution_id else base


def model_link(_model_id: str) -> str:
    return "/simulation"


def template_link(template_id: str) -> str:
    return f"/scenarios/new?template={quote(template_id, safe='')}"
