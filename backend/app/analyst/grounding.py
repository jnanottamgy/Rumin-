"""The grounding check: every figure in an answer must be found in the evidence it cites.

The check reads the headline, every paragraph and every notice, sentence by sentence:

* It extracts each **figure** — signs (+, −), thousands separators (Western or Indian),
  decimals, percentages, percentage points, basis points, and scale words (thousand,
  lakh, crore, million, billion) — and requires it in the evidence the **sentence** cites:
  equal to a cited value **at the precision displayed** (``24.29 %`` matches the stored
  ``24.2914979757…``; ``₹1.25 crore`` matches ``12,450,000`` only to the nearest lakh), or
  present word for word in a cited record's text (a year, a date, a version).
* An unsigned figure may match a value's magnitude ("fell by 6,325,000" for −6,325,000);
  a written sign must match.
* A sentence with a figure and no citation fails. A citation to an id that does not exist
  fails. The headline may use any evidence of the answer.
* **Interpretation** and **general knowledge** paragraphs may not contain figures at all.
* Phrasing: nothing may predict, claim a cause, guarantee or advise (``policy.FORBIDDEN``),
  except inside a quotation that is word for word a cited record's text.

Tables, series, paths and scenario cards are built by RUMIN from tool results, so only their
citations are checked here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

from app.analyst.answer import (
    CITATION,
    Block,
    ClarificationBlock,
    GroundingProblem,
    GroundingRead,
    NoticeBlock,
    PathsBlock,
    ScenarioBlock,
    SeriesBlock,
    TableBlock,
    TextBlock,
    citations_in,
)
from app.analyst.evidence import Evidence
from app.analyst.policy import FORBIDDEN

SCALES = {
    "thousand": Decimal(10) ** 3,
    "k": Decimal(10) ** 3,
    "lakh": Decimal(10) ** 5,
    "lakhs": Decimal(10) ** 5,
    "lac": Decimal(10) ** 5,
    "crore": Decimal(10) ** 7,
    "crores": Decimal(10) ** 7,
    "cr": Decimal(10) ** 7,
    "million": Decimal(10) ** 6,
    "mn": Decimal(10) ** 6,
    "billion": Decimal(10) ** 9,
    "bn": Decimal(10) ** 9,
}
_FIGURE = re.compile(
    r"(?<![\w.\-/])(?P<sign>[+\-−])?\s?(?:[₹$€£]\s?)?"
    r"(?P<int>\d{1,3}(?:,\d{2,3})+|\d+)(?P<dec>\.\d+)?"
    r"(?:\s?(?P<unit>%|percent\b|per\s+cent\b|pp\b|percentage\s+points?\b|bps\b|"
    r"basis\s+points?\b|thousand\b|k\b|lakhs?\b|lac\b|crores?\b|cr\b|million\b|mn\b|"
    r"billion\b|bn\b))?",
    re.IGNORECASE,
)
# Dates and versions are checked word for word against the cited records' text.
_LITERALS = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\bv?\d+\.\d+\.\d+\b")
_TIMES = re.compile(r"T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+\-]\d{2}:\d{2})?\b")
# Identifiers (wb-ind-pa-nus-fcrf, var_usd_inr) and evidence ids carry no figures.
_IDENTIFIERS = re.compile(r"\b[a-z][a-z0-9]*(?:[_\-][a-z0-9]+)+\b|\bE\d+\b")
_QUOTED = re.compile(r"[“\"]([^”\"]{3,})[”\"]")
_ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|vs|etc|no|u\.s|approx|incl|est)\.", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\[(\"“A-Z0-9−+\-₹$])")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
_HOLD = chr(0x2024)  # stands in for the full stop of an abbreviation while splitting


@dataclass(frozen=True)
class Figure:
    text: str
    value: Decimal
    quantum: Decimal  # the precision displayed, in the value's own units
    signed: bool
    kind: str  # "number", "percent", "points", "year"


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def literals(text: str) -> list[str]:
    """Dates and versions in ``text``, which must appear as written in the evidence."""
    return _LITERALS.findall(_TIMES.sub(" ", CITATION.sub(" ", text)))


def figures(text: str) -> list[Figure]:
    """Every figure in ``text`` (citations, dates, times, versions and identifiers removed
    first; dates and versions are checked separately, see ``literals``)."""
    cleaned = CITATION.sub(" ", text)
    cleaned = _TIMES.sub(" ", cleaned)
    cleaned = _LITERALS.sub(" ", cleaned)
    cleaned = _IDENTIFIERS.sub(" ", cleaned)
    found: list[Figure] = []
    for match in _FIGURE.finditer(cleaned):
        whole = match.group("int").replace(",", "")
        decimals = match.group("dec") or ""
        value = _decimal(whole + decimals)
        if value is None:
            continue
        places = len(decimals) - 1 if decimals else 0
        quantum = Decimal(1).scaleb(-places)
        unit = (match.group("unit") or "").lower().strip()
        unit = re.sub(r"\s+", " ", unit)
        kind = "number"
        if unit in ("%", "percent", "per cent"):
            kind = "percent"
        elif unit in ("pp", "percentage point", "percentage points"):
            kind = "points"
        elif unit in ("bps", "basis point", "basis points"):
            kind = "points"
            value, quantum = value / 100, quantum / 100
        elif unit in SCALES:
            scale = SCALES[unit]
            value, quantum = value * scale, quantum * scale
        elif not decimals and _YEAR.match(whole) and not match.group("sign"):
            kind = "year"
        sign = match.group("sign")
        if sign in ("-", "−"):
            value = -value
        found.append(Figure(match.group(0).strip(), value, quantum, sign is not None, kind))
    return found


def _rounds_to(stored: Decimal, figure: Figure) -> bool:
    for rounding in (ROUND_HALF_EVEN, ROUND_HALF_UP):
        try:
            shown = (stored / figure.quantum).quantize(Decimal(1), rounding=rounding)
        except (InvalidOperation, ZeroDivisionError):
            return False
        target = figure.value / figure.quantum
        if figure.signed and shown == target:
            return True
        if not figure.signed and abs(shown) == abs(target):
            return True
    return False


def _texts(item: Evidence) -> str:
    parts = [
        item.retrieved_at.isoformat(),
        item.title,
        item.detail or "",
        item.period or "",
        item.as_of or "",
        item.source.label,
        item.source.id,
        *item.models,
        *item.assumptions,
        *item.provenance.values(),
        *item.values.keys(),
    ]
    return " ".join(parts)


def supported(figure: Figure, cited: Sequence[Evidence]) -> bool:
    for item in cited:
        for text in item.values.values():
            stored = _decimal(text)
            if stored is not None and _rounds_to(stored, figure):
                return True
        if figure.kind == "year" and re.search(
            rf"(?<!\d){re.escape(figure.text)}(?!\d)", _texts(item)
        ):
            return True
    return False


def sentences(text: str) -> list[str]:
    """Sentences, with a citation that follows a full stop kept with the sentence before."""
    protected = _ABBREVIATIONS.sub(lambda m: m.group(0).replace(".", _HOLD), text)
    parts = [part.replace(_HOLD, ".") for part in _SENTENCE.split(protected) if part.strip()]
    merged: list[str] = []
    for part in parts:
        leading = re.match(r"^((?:\[E\d+(?:\s*,\s*E\d+)*\]\s*)+)(.*)$", part, re.S)
        if leading and merged:
            merged[-1] = f"{merged[-1]} {leading.group(1).strip()}"
            if leading.group(2).strip():
                merged.append(leading.group(2).strip())
        else:
            merged.append(part.strip())
    return merged


def _phrasing(sentence: str, cited: Sequence[Evidence]) -> list[str]:
    visible = sentence
    for match in _QUOTED.finditer(sentence):
        quote = match.group(1)
        if any(quote in _texts(item) for item in cited):
            visible = visible.replace(match.group(0), " ")
    return [reason for pattern, reason in FORBIDDEN if pattern.search(visible)]


def check(headline: str, blocks: Sequence[Block], evidence: Iterable[Evidence]) -> GroundingRead:
    ledger = {item.id: item for item in evidence}
    problems: list[GroundingProblem] = []
    figures_checked = 0
    citations_checked = 0

    def unknown(ids: Iterable[str], index: int | None, where: str) -> None:
        nonlocal citations_checked
        for evidence_id in ids:
            citations_checked += 1
            if evidence_id not in ledger:
                problems.append(
                    GroundingProblem(
                        block=index,
                        text=where[:200],
                        reason=f"Cites {evidence_id}, which does not exist.",
                    )
                )

    def read(text: str, index: int | None, role: str, fallback: list[str] | None) -> None:
        nonlocal figures_checked
        for sentence in sentences(text):
            ids = citations_in(sentence) or (fallback or [])
            unknown(citations_in(sentence), index, sentence)
            cited = [ledger[item] for item in ids if item in ledger]
            for reason in _phrasing(sentence, cited):
                problems.append(
                    GroundingProblem(
                        block=index, text=sentence[:200], reason=f"Phrasing: {reason}."
                    )
                )
            for literal in literals(sentence):
                figures_checked += 1
                if not any(literal.lstrip("v") in _texts(item) for item in cited):
                    problems.append(
                        GroundingProblem(
                            block=index,
                            text=literal,
                            reason="A date or version not found in the evidence "
                            "its sentence cites.",
                        )
                    )
            found = figures(sentence)
            if not found:
                continue
            if role in ("interpretation", "general"):
                problems.append(
                    GroundingProblem(
                        block=index,
                        text=sentence[:200],
                        reason=f"{'An' if role[0] in 'aeiou' else 'A'} {role} paragraph may "
                        "not contain figures.",
                    )
                )
                continue
            for figure in found:
                figures_checked += 1
                if not ids:
                    problems.append(
                        GroundingProblem(
                            block=index, text=figure.text, reason="A figure without a citation."
                        )
                    )
                elif not supported(figure, cited):
                    where = (
                        "any evidence of the answer"
                        if index is None
                        else f"the evidence its sentence cites ({', '.join(ids)})"
                    )
                    problems.append(
                        GroundingProblem(
                            block=index, text=figure.text, reason=f"Not found in {where}."
                        )
                    )

    read(headline, None, "answer", list(ledger))
    for index, block in enumerate(blocks):
        if isinstance(block, TextBlock):
            read(block.text, index, block.role, None)
        elif isinstance(block, NoticeBlock):
            unknown(block.citations, index, block.title)
            read(block.text, index, "answer", block.citations or None)
        elif isinstance(block, TableBlock):
            unknown(block.citations, index, block.title)
            for row in block.rows:
                unknown(row.citations, index, block.title)
        elif isinstance(block, SeriesBlock | PathsBlock):
            unknown(block.citations, index, block.title)
            if isinstance(block, PathsBlock):
                for path in block.paths:
                    unknown(path.citations, index, block.title)
        elif isinstance(block, ScenarioBlock):
            unknown(block.citations, index, block.title)
            for line in block.lines:
                unknown(line.citations, index, block.title)
        elif isinstance(block, ClarificationBlock):
            continue
    return GroundingRead(
        passed=not problems,
        figures_checked=figures_checked,
        citations_checked=citations_checked,
        problems=problems[:50],
    )
