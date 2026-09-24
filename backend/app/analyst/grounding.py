"""The grounding check: every figure in an answer must be found in the evidence it cites.

The check reads the headline, every paragraph and every notice, sentence by sentence:

* It extracts each **figure** — signs (+, −, and a dash written against the digits),
  accounting brackets ("(5)" is −5), thousands separators (Western or Indian), decimals,
  percentages, percentage points, basis points, currencies (₹, $, €, £, INR, USD, Rs …) and
  scale words (thousand, lakh, crore, lakh crore, million, billion, trillion, and k, m, bn,
  tn) — and requires it in the evidence the **sentence** cites: equal to a cited value **at
  the precision displayed** (``24.29 %`` matches the stored ``24.2914979757…``; ``₹1.25
  crore`` matches ``12,450,000`` only to the nearest lakh), or present word for word in a
  cited record's text (a year, a date, a period, a version).
* A figure matches only a value **of its kind**: a percentage only a value recorded as a
  percentage, percentage points only a change in points, an amount (with a currency or a
  scale word) only a value that is neither, in the same currency when both say which
  (``Evidence.value_units``). "3 %" never matches a count of 3.
* An unsigned figure may match a value's magnitude ("fell by 6,325,000" for −6,325,000);
  a written sign must match.
* Anything that looks like a figure but cannot be read exactly **fails** rather than being
  skipped: digits left over once every figure is read, other numerals (½, ², digits of
  other scripts), numbers in scientific notation, decimal commas, digits grouped by spaces,
  leading zeros, a figure run into letters ("5x", "3rd"), and figures written in words
  ("five hundred crore", "a million"). "Doubles", "halves" and "triples" are read as
  +100 %, −50 % and +200 %.
* A sentence with a figure and no citation fails. A citation to an id that does not exist
  fails. The headline may use any evidence of the answer.
* **Interpretation** and **general knowledge** paragraphs may not contain figures at all.
* Phrasing: nothing may predict, claim a cause, guarantee or advise (``policy.FORBIDDEN``).
* A **quotation** that is word for word in a cited record's text is the record speaking, not
  the answer: it is exempt from the figure and phrasing checks. A cited record's name,
  title or identifier written as stored is exempt from the figure check ("Population ages
  15-64" names a series; it states no figure).

Tables, series, paths and scenario cards are built by RUMIN from tool results, so only their
citations are checked here.
"""

from __future__ import annotations

import re
import unicodedata
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
    "lacs": Decimal(10) ** 5,
    "crore": Decimal(10) ** 7,
    "crores": Decimal(10) ** 7,
    "cr": Decimal(10) ** 7,
    "lakh crore": Decimal(10) ** 12,
    "lakh crores": Decimal(10) ** 12,
    "million": Decimal(10) ** 6,
    "mn": Decimal(10) ** 6,
    "m": Decimal(10) ** 6,
    "billion": Decimal(10) ** 9,
    "bn": Decimal(10) ** 9,
    "b": Decimal(10) ** 9,
    "trillion": Decimal(10) ** 12,
    "tn": Decimal(10) ** 12,
}
CURRENCIES = {
    "₹": "INR",
    "inr": "INR",
    "rs": "INR",
    "rs.": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}
PERCENT_UNITS = ("%", "percent", "per cent")
POINT_UNITS = ("pp", "percentage point", "percentage points")
BASIS_UNITS = ("bps", "basis point", "basis points")

_FIGURE = re.compile(
    r"(?<![\w.\-/±])"
    # a sign: +, - or −, or a dash written against the digits ("–5", not "India – 5")
    r"(?:(?P<sign>[+\-−])\s?|(?P<dash>[–—])(?=[0-9₹$€£]|US\$|INR|USD|EUR|GBP|Rs))?"
    r"(?:(?P<cur>US\$|[₹$€£]|(?:INR|USD|EUR|GBP|Rs\.?)(?![a-z]))\s?)?"
    r"(?P<int>[0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]+)(?P<dec>\.[0-9]+)?"
    r"(?:\s?(?P<unit>%|percent\b|per\s+cent\b|pp\b|percentage\s+points?\b|bps\b"
    r"|basis\s+points?\b|lakh\s+crores?\b|lakhs?\b|lacs?\b|crores?\b|cr\b|thousand\b|k\b"
    r"|million\b|mn\b|m\b|billion\b|bn\b|b\b|trillion\b|tn\b))?"
    r"(?:\s?(?P<cur2>INR|USD|EUR|GBP|rupees?|dollars?|euros?)\b)?",
    re.IGNORECASE,
)
# Dates, periods and versions are checked word for word against the cited records' text.
_LITERALS = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # a date
    r"|\b\d{4}[-–/]\d{2}\b"  # a month (2024-03) or a financial year (2023-24)
    r"|\b\d{4}-?[QH][1-4]\b"  # a quarter or a half (2024-Q1)
    r"|\b[QH][1-4]\b"
    r"|\bFY\s?\d{2,4}\b"
    r"|\bv?\d+\.\d+\.\d+\b"  # a version
)
_TIMES = re.compile(r"T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+\-]\d{2}:\d{2})?\b")
# Evidence ids carry no figures; nor do identifiers (wb-ind-pa-nus-fcrf, var_usd_inr) that
# are written as a cited record holds them.
_EVIDENCE_IDS = re.compile(r"\bE\d+\b")
_IDENTIFIERS = re.compile(r"\b[a-z][a-z0-9]*(?:[_\-:.][a-z0-9]+)+\b")
_QUOTED = re.compile(r"[“\"]([^”\"]{3,})[”\"]")
_ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|vs|etc|no|u\.s|approx|incl|est)\.", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\[(\"“A-Z0-9−+\-₹$])")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
_HOLD = chr(0x2024)  # stands in for the full stop of an abbreviation while splitting

# Changes written as words, read as the percentages they are.
_MULTIPLES = re.compile(r"\b(doubl|tripl|quadrupl|halv)(?:e|es|ed|ing)\b(?!-)", re.IGNORECASE)
_MULTIPLE_VALUE = {
    "doubl": Decimal(100),
    "tripl": Decimal(200),
    "quadrupl": Decimal(300),
    "halv": Decimal(-50),
}
# Figures written in words cannot be checked; they fail.
_WORD = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundred|a|an|half|several|few|dozens?)"
)
_WORDED = re.compile(
    rf"\b{_WORD}(?:[\s-]+(?:and\s+)?{_WORD})*[\s-]+(?:hundred|thousand|lakhs?|lacs?|crores?|"
    r"million|billion|trillion|percent\b|per\s+cent\b|percentage\s+points?\b|basis\s+points?\b)"
    r"|\b(?:hundreds|thousands|lakhs|crores|millions|billions|trillions)\s+of\b"
    r"|\b(?:a|one|two|three|four|nine)\s+(?:thirds?|quarters?|fifths?|tenths?)\s+of\b",
    re.IGNORECASE,
)
_UNREADABLE = (
    (re.compile(r"[0-9],[0-9](?![0-9])"), "a decimal comma"),
    (
        re.compile(r"(?<![0-9.,])[0-9]{1,3}(?:[ \u00a0\u2009\u202f][0-9]{3})+(?![0-9.,])"),
        "digits grouped by spaces",
    ),
)


@dataclass(frozen=True)
class Figure:
    text: str
    value: Decimal
    quantum: Decimal  # the precision displayed, in the value's own units
    signed: bool
    kind: str  # "number", "amount", "percent", "points", "year"
    currency: str | None = None  # for amounts written with a currency


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    """``text`` with every match of ``pattern`` replaced by as many spaces (positions keep)."""
    return pattern.sub(lambda match: " " * len(match.group(0)), text)


def _numeral(character: str) -> bool:
    return character.isdigit() or unicodedata.numeric(character, None) is not None


def literals(text: str) -> list[str]:
    """Dates, periods and versions in ``text``, which must appear as written in the evidence."""
    return _LITERALS.findall(_blank(_blank(text, CITATION), _TIMES))


def read(text: str) -> tuple[list[Figure], list[str]]:
    """Every figure in ``text``, and every fragment that looks like a figure but cannot be
    read exactly (citations, dates, periods, times, versions and identifiers are set aside
    first; dates, periods and versions are checked separately, see ``literals``)."""
    cleaned = _blank(text, CITATION)
    cleaned = _blank(cleaned, _TIMES)
    cleaned = _blank(cleaned, _LITERALS)
    cleaned = _blank(cleaned, _EVIDENCE_IDS)
    found: list[Figure] = []
    unreadable: list[str] = []
    for pattern, what in _UNREADABLE:
        for match in pattern.finditer(cleaned):
            unreadable.append(f"{match.group(0).strip()} ({what})")
        cleaned = _blank(cleaned, pattern)
    for match in _WORDED.finditer(cleaned):
        unreadable.append(f"{match.group(0).strip()} (a figure in words)")
    cleaned = _blank(cleaned, _WORDED)
    for match in _MULTIPLES.finditer(cleaned):
        multiple = _MULTIPLE_VALUE[match.group(1).lower()]
        found.append(Figure(match.group(0), multiple, Decimal(1), True, "percent"))
    cleaned = _blank(cleaned, _MULTIPLES)
    spans: list[tuple[int, int]] = []
    for match in _FIGURE.finditer(cleaned):
        start, end = match.span()
        spans.append((start, end))
        written = match.group(0).strip()
        whole = match.group("int").replace(",", "")
        if len(whole) > 1 and whole.startswith("0"):
            unreadable.append(f"{written} (a leading zero)")
            continue
        if end < len(cleaned) and (cleaned[end].isalpha() or _numeral(cleaned[end])):
            unreadable.append(f"{written}{cleaned[end]} (a figure run into other characters)")
            continue
        decimals = match.group("dec") or ""
        parsed = _decimal(whole + decimals)
        if parsed is None:
            unreadable.append(written)
            continue
        value = parsed
        places = len(decimals) - 1 if decimals else 0
        quantum = Decimal(1).scaleb(-places)
        unit = re.sub(r"\s+", " ", (match.group("unit") or "").lower().strip())
        mark = match.group("cur") or match.group("cur2")
        currency = CURRENCIES.get(mark.lower()) if mark else None
        sign = match.group("sign") or match.group("dash")
        kind = "number"
        if unit in PERCENT_UNITS:
            kind = "percent"
        elif unit in POINT_UNITS:
            kind = "points"
        elif unit in BASIS_UNITS:
            kind = "points"
            value, quantum = value / 100, quantum / 100
        elif unit in SCALES:
            kind = "amount"
            value, quantum = value * SCALES[unit], quantum * SCALES[unit]
        elif currency is not None:
            kind = "amount"
        elif not decimals and _YEAR.match(whole) and sign is None:
            kind = "year"
        negative = sign is not None and sign != "+"
        if sign is None and kind != "year":
            # Accounting brackets: "(5)" or "(₹5 crore)" is a negative figure.
            before = cleaned[:start].rstrip()
            after = cleaned[end:].lstrip()
            if before.endswith("(") and after.startswith(")"):
                negative = True
                sign = "("
        if negative:
            value = -value
        found.append(Figure(written, value, quantum, sign is not None, kind, currency))
    for start, end in spans:
        cleaned = cleaned[:start] + " " * (end - start) + cleaned[end:]
    leftover = [position for position, character in enumerate(cleaned) if _numeral(character)]
    if leftover:
        first = leftover[0]
        unreadable.append(
            f"{text[max(0, first - 12) : first + 12].strip()} (a figure that cannot be read)"
        )
    if "±" in cleaned:
        unreadable.append("± (a range)")
    return found, unreadable


def figures(text: str) -> list[Figure]:
    """Every figure in ``text`` that can be read (see ``read``)."""
    return read(text)[0]


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


def _compatible(figure: Figure, item: Evidence, key: str) -> bool:
    """Whether ``figure`` may be read as the value ``key`` of ``item``: of the same kind."""
    unit = item.value_units.get(key)
    if figure.kind == "percent":
        return unit == "percent"
    if figure.kind == "points":
        return unit == "points"
    if figure.kind == "amount":
        if unit is not None:
            return False
        return not (figure.currency and item.currency and figure.currency != item.currency)
    return True


def supported(figure: Figure, cited: Sequence[Evidence]) -> bool:
    for item in cited:
        for key, text in item.values.items():
            stored = _decimal(text)
            if stored is not None and _compatible(figure, item, key) and _rounds_to(stored, figure):
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


def _quoted(sentence: str, cited: Sequence[Evidence]) -> str:
    """``sentence`` without the quotations that are word for word in a cited record's text:
    the record speaking, not the answer."""
    visible = sentence
    for match in _QUOTED.finditer(sentence):
        if any(match.group(1) in _texts(item) for item in cited):
            visible = visible.replace(match.group(0), " " * len(match.group(0)))
    return visible


def _named(sentence: str, cited: Sequence[Evidence]) -> str:
    """``sentence`` without the names, titles and identifiers of the cited records, where
    they are written as stored: digits in a name ("Population ages 15-64") are not figures."""
    texts = " ".join(_texts(item) for item in cited)
    names = {
        name
        for item in cited
        for name in (item.title, item.source.label)
        if len(name) > 3 and any(character.isalpha() for character in name)
    }
    visible = sentence
    for name in sorted(names, key=len, reverse=True):
        visible = re.sub(
            rf"(?<!\w){re.escape(name)}(?!\w)", lambda match: " " * len(match.group(0)), visible
        )
    return _IDENTIFIERS.sub(
        lambda match: " " * len(match.group(0)) if match.group(0) in texts else match.group(0),
        visible,
    )


def phrasing(text: str) -> list[str]:
    return [reason for pattern, reason in FORBIDDEN if pattern.search(text)]


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

    def problem(index: int | None, text: str, reason: str) -> None:
        problems.append(GroundingProblem(block=index, text=text[:200], reason=reason))

    def read_text(text: str, index: int | None, role: str, fallback: list[str] | None) -> None:
        nonlocal figures_checked
        for sentence in sentences(text):
            ids = citations_in(sentence) or (fallback or [])
            unknown(citations_in(sentence), index, sentence)
            cited = [ledger[item] for item in ids if item in ledger]
            visible = _quoted(sentence, cited)
            for reason in phrasing(visible):
                problem(index, sentence, f"Phrasing: {reason}.")
            visible = _named(visible, cited)
            for literal in literals(visible):
                figures_checked += 1
                if not any(literal.lstrip("v") in _texts(item) for item in cited):
                    problem(
                        index,
                        literal,
                        "A date, period or version not found in the evidence its sentence cites.",
                    )
            found, unreadable = read(visible)
            for fragment in unreadable:
                figures_checked += 1
                problem(
                    index,
                    fragment,
                    "A figure that cannot be checked; figures are written in digits, with a "
                    "sign, %, percentage points, basis points, a currency or a scale word.",
                )
            if not found:
                continue
            if role in ("interpretation", "general"):
                article = "An" if role[0] in "aeiou" else "A"
                problem(index, sentence, f"{article} {role} paragraph may not contain figures.")
                continue
            for figure in found:
                figures_checked += 1
                if not ids:
                    problem(index, figure.text, "A figure without a citation.")
                elif not supported(figure, cited):
                    where = (
                        "any evidence of the answer"
                        if index is None
                        else f"the evidence its sentence cites ({', '.join(ids)})"
                    )
                    problem(index, figure.text, f"Not found in {where}.")

    read_text(headline, None, "answer", list(ledger))
    for index, block in enumerate(blocks):
        if isinstance(block, TextBlock):
            read_text(block.text, index, block.role, None)
        elif isinstance(block, NoticeBlock):
            unknown(block.citations, index, block.title)
            read_text(block.text, index, "answer", block.citations or None)
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


def follow_ups(items: Sequence[str], evidence: Iterable[Evidence]) -> list[str]:
    """The follow-up questions that may be offered: short, plain questions that do not read
    like instructions, advice or forecasts, and whose figures either come from the evidence
    or are the stated changes of a what-if. The rest are dropped."""
    from app.analyst import policy

    ledger = list(evidence)
    kept: list[str] = []
    for item in items:
        question = policy.data_text(item, 200)
        if (
            not question
            or question.startswith("[withheld")
            or len(question) > 160
            or CITATION.search(question)
        ):
            continue
        screened = policy.screen(question)
        if screened.flags or phrasing(question):
            continue
        found, unreadable = read(question)
        if unreadable:
            continue
        if found and not screened.conditional and not check(question, [], ledger).passed:
            continue
        if question not in kept:
            kept.append(question)
    return kept[:4]
