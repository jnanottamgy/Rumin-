"""Reading figures, periods and horizons out of a question.

Only what a person wrote is read: a change ("rises 20 %", "up 50 bps", "doubles"), the
periods they name ("2015", "between 2015 and 2020", "since 2018", "the last 5 years") and a
horizon ("over 18 months"). Nothing is guessed: a figure that cannot be tied to a variable
is left out, and every reading that is not literal — a rate change written in percent read
as percentage points, a weaker rupee read as a higher USD/INR — is reported as an
assumption so the answer can state it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MAX_HORIZON_MONTHS = 36

_NUMBER = r"(?P<sign>[+\-−])?\s*(?P<number>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_PERCENT = re.compile(_NUMBER + r"\s*(?:%|percent\b|per\s+cent\b|pc\b)", re.IGNORECASE)
_POINTS = re.compile(
    _NUMBER + r"\s*(?:pp\b|ppts?\b|percentage[\s-]points?\b|points?\b)", re.IGNORECASE
)
_BASIS = re.compile(_NUMBER + r"\s*(?:bps\b|bp\b|basis[\s-]points?\b)", re.IGNORECASE)
_DOLLARS = re.compile(
    r"(?P<sign>[+\-−])?\s*(?:\$|usd\s*)(?P<number>\d+(?:\.\d+)?)"
    r"|(?P<sign2>[+\-−])?\s*(?P<number2>\d+(?:\.\d+)?)\s*(?:dollars?\b|usd\b)",
    re.IGNORECASE,
)
_MULTIPLE = re.compile(r"\b(doubles?|doubling|halves|halved|halving|triples?|tripling)\b", re.I)
_MULTIPLE_VALUE = {
    "double": Decimal(100),
    "doubles": Decimal(100),
    "doubling": Decimal(100),
    "halves": Decimal(-50),
    "halved": Decimal(-50),
    "halving": Decimal(-50),
    "triple": Decimal(200),
    "triples": Decimal(200),
    "tripling": Decimal(200),
}

UP_WORDS = (
    "rise",
    "rises",
    "rising",
    "rose",
    "up",
    "increase",
    "increases",
    "increased",
    "jump",
    "jumps",
    "climb",
    "climbs",
    "spike",
    "spikes",
    "surge",
    "surges",
    "higher",
    "hike",
    "hikes",
    "hiked",
    "raise",
    "raised",
    "goes up",
    "go up",
    "gains",
    "gain",
    "strengthens",
    "strengthen",
    "appreciates",
    "appreciate",
)
DOWN_WORDS = (
    "fall",
    "falls",
    "falling",
    "fell",
    "down",
    "drop",
    "drops",
    "decline",
    "declines",
    "decrease",
    "decreases",
    "cut",
    "cuts",
    "lower",
    "lowered",
    "slump",
    "slumps",
    "plunge",
    "plunges",
    "goes down",
    "go down",
    "weakens",
    "weaken",
    "depreciates",
    "depreciate",
    "loses",
    "lose",
    "slides",
    "eases",
    "ease",
)
_DIRECTION = re.compile(
    r"\b(" + "|".join(sorted({*UP_WORDS, *DOWN_WORDS}, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_YEAR = r"(?:19[5-9]\d|20\d\d)"
_RANGE = re.compile(
    rf"\b(?:between|from)\s+(?P<a>{_YEAR})\s+(?:and|to|until|till)\s+(?P<b>{_YEAR})\b"
    rf"|\b(?P<c>{_YEAR})\s*(?:-|–|—|to)\s*(?P<d>{_YEAR})\b",
    re.IGNORECASE,
)
_SINCE = re.compile(rf"\b(?:since|after|from)\s+(?P<a>{_YEAR})\b", re.IGNORECASE)
_LAST = re.compile(
    r"\b(?:last|past|previous)\s+(?P<n>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+(?:years?|periods?|observations?|values?)\b",
    re.IGNORECASE,
)
_YEARS = re.compile(rf"\b{_YEAR}\b")
_HORIZON = re.compile(
    r"\b(?:over|for|across|within|in|during|horizon\s+of)\s+(?:the\s+next\s+|a\s+|the\s+)?"
    r"(?P<n>\d{1,2}|one|two|three|six|twelve|eighteen)[\s-]+(?P<unit>months?|years?)\b"
    r"|\b(?P<m>\d{1,2})[\s-]month\b",
    re.IGNORECASE,
)
_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "eighteen": 18,
}


@dataclass(frozen=True)
class Magnitude:
    """A change a person wrote, before it is tied to a variable."""

    start: int
    end: int
    value: Decimal = field(compare=False)  # unsigned unless the text carried a sign
    unit: str  # "percent", "points" (percentage points), "absolute" (the variable's unit)
    signed: bool
    text: str


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _sign(match: re.Match[str], *groups: str) -> str | None:
    for group in groups:
        value = match.groupdict().get(group)
        if value:
            return value
    return None


def magnitudes(question: str) -> list[Magnitude]:
    """Every change written in ``question``, in order, without overlaps."""
    found: list[Magnitude] = []
    taken: list[tuple[int, int]] = []

    def add(match: re.Match[str], value: Decimal | None, unit: str, sign: str | None) -> None:
        if value is None:
            return
        start, end = match.span()
        if any(start < b and a < end for a, b in taken):
            return
        if sign in ("-", "−"):
            value = -value
        taken.append((start, end))
        found.append(
            Magnitude(
                start=start,
                end=end,
                value=value,
                unit=unit,
                signed=sign is not None,
                text=match.group(0).strip(),
            )
        )

    for match in _BASIS.finditer(question):
        number = _decimal(match.group("number"))
        add(match, number / 100 if number is not None else None, "points", match.group("sign"))
    for match in _POINTS.finditer(question):
        add(match, _decimal(match.group("number")), "points", match.group("sign"))
    for match in _PERCENT.finditer(question):
        add(match, _decimal(match.group("number")), "percent", match.group("sign"))
    for match in _DOLLARS.finditer(question):
        written = match.group("number") or match.group("number2")
        add(match, _decimal(written), "absolute", _sign(match, "sign", "sign2"))
    for match in _MULTIPLE.finditer(question):
        value = _MULTIPLE_VALUE[match.group(1).lower()]
        start, end = match.span()
        if any(start < b and a < end for a, b in taken):
            continue
        taken.append((start, end))
        found.append(
            Magnitude(start, end, value, "percent", signed=True, text=match.group(0).strip())
        )
    return sorted(found, key=lambda item: item.start)


def direction_near(
    question: str, subject: tuple[int, int], figure: tuple[int, int]
) -> tuple[int, str] | None:
    """The direction word that goes with a change: between the subject and the figure
    first ("Brent *rises* 20 %", "a 20 % *rise* in Brent"), then before both in the same
    clause, then just after the figure. Returns ``(+1 | -1, word)``."""
    first, second = sorted((subject, figure))
    between = list(_DIRECTION.finditer(question, first[1], second[0]))
    if between:
        word = between[-1].group(1).lower()
        return (1 if word in UP_WORDS else -1), word
    start = first[0]
    clause_start = max(question.rfind(sep, 0, start) for sep in (",", ";", " and ", " but "))
    clause_start = 0 if clause_start < 0 else clause_start
    before = [
        match
        for match in _DIRECTION.finditer(question, clause_start, start)
        if match.end() <= start
    ]
    if before:
        word = before[-1].group(1).lower()
        return (1 if word in UP_WORDS else -1), word
    end = second[1]
    after = _DIRECTION.search(question, end, min(len(question), end + 24))
    if after:
        word = after.group(1).lower()
        return (1 if word in UP_WORDS else -1), word
    return None


@dataclass(frozen=True)
class Periods:
    """The periods a question names. ``years`` are listed in the order written."""

    start: int | None = None
    end: int | None = None
    years: tuple[int, ...] = ()
    last: int | None = None
    text: str | None = None

    @property
    def empty(self) -> bool:
        return self.start is None and self.end is None and not self.years and self.last is None


def periods(question: str) -> Periods:
    match = _RANGE.search(question)
    if match:
        first = int(match.group("a") or match.group("c"))
        second = int(match.group("b") or match.group("d"))
        low, high = sorted((first, second))
        return Periods(start=low, end=high, years=(first, second), text=match.group(0))
    match = _SINCE.search(question)
    if match:
        year = int(match.group("a"))
        return Periods(start=year, years=(year,), text=match.group(0))
    match = _LAST.search(question)
    if match:
        raw = match.group("n").lower()
        count = _WORD_NUMBERS.get(raw) or int(raw)
        return Periods(last=max(1, min(count, 60)), text=match.group(0))
    years = tuple(int(item) for item in _YEARS.findall(question))
    if years:
        return Periods(years=years, text=", ".join(str(year) for year in years))
    return Periods()


def horizon_months(question: str) -> int | None:
    """A horizon written in months or years, capped at the Lab's limit."""
    match = _HORIZON.search(question)
    if not match:
        return None
    if match.group("m"):
        months = int(match.group("m"))
    else:
        raw = match.group("n").lower()
        count = _WORD_NUMBERS.get(raw) or int(raw)
        months = count * 12 if match.group("unit").lower().startswith("year") else count
    return max(1, min(months, MAX_HORIZON_MONTHS))


def year_spans(question: str) -> list[tuple[int, int]]:
    """Where years appear, so they are not read as changes."""
    return [match.span() for match in _YEARS.finditer(question)]
