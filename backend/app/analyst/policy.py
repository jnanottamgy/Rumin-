"""What the Analyst will not do, and the checks that keep it that way.

* **Screening** a question before anything runs: instructions aimed at the Analyst itself
  (prompt injection), requests for secrets, requests for an investment decision, for a
  forecast, or for live market data. Each has a fixed, documented response.
* **Phrasing**: answer text may not predict, claim causes, guarantee, or tell anyone what to
  buy or sell (the same rule as Phase 6's findings).
* **Retrieved text is data**: names and descriptions read from the store are cleaned
  (control characters removed, length capped) and withheld if they read like instructions,
  before any of it reaches a language model.

Screening is by patterns, so it is deliberately conservative: it catches the common forms,
and everything after it is built so that a question that slips through still cannot reach
beyond read-only tools or put an uncited figure in front of anyone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

MAX_QUESTION_CHARS = 2000
MAX_DATA_TEXT = 600

Screen = Literal["injection", "secrets", "advice", "forecast", "live_data"]

_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|preceding)?\s*"
    r"(?:instructions?|rules?|prompts?|directions?)"
    r"|disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous\s+|prior\s+|above\s+)?"
    r"(?:instructions?|rules?|prompts?)"
    r"|forget\s+(?:all\s+|your\s+|the\s+)?(?:previous\s+)?(?:instructions?|rules?)"
    r"|(?:reveal|show|print|repeat|output|display|leak)\s+(?:me\s+)?(?:your\s+|the\s+)?"
    r"(?:system\s+prompt|instructions|hidden\s+prompt|prompt|configuration|rules)"
    r"|system\s+prompt|developer\s+mode|jailbreak|\bdan\s+mode\b"
    r"|you\s+are\s+now\b|pretend\s+(?:to\s+be|you\s+are)|act\s+as\s+(?:an?\s+)?(?:unrestricted|"
    r"different|new)\b|new\s+instructions?\s*:|<\s*/?\s*(?:system|instructions?|tool)\s*>"
    r"|\bbegin\s+(?:system|admin)\b|\boverride\s+(?:your\s+|the\s+)?(?:rules|policy|safety)"
    r"|\b(?:drop|truncate|delete\s+from|insert\s+into|update\s+\w+\s+set)\b.*\b(?:table|from|"
    r"set|into)\b|;\s*--|\brm\s+-rf\b|\bimport\s+os\b|\bsubprocess\b|\beval\s*\(|\bexec\s*\(",
    re.IGNORECASE,
)
_SECRETS = re.compile(
    r"\b(?:api[\s_-]?keys?|secret\s+keys?|access\s+tokens?|passwords?|credentials?|"
    r"environment\s+variables?|env\s+vars?|\.env\b|database\s+url|connection\s+string)\b",
    re.IGNORECASE,
)
_ADVICE = re.compile(
    r"\bshould\s+(?:i|we|you|one)\s+(?:buy|sell|invest|hold|short|exit|add|reduce|trim|"
    r"go\s+long|go\s+short|put\s+money)\b"
    r"|\b(?:is|are)\s+(?:\w+\s+){0,4}(?:a\s+)?(?:good|bad|safe|smart|great)\s+"
    r"(?:investment|buy|bet|stock|share|pick)s?\b"
    r"|\b(?:buy|sell)\s+or\s+(?:sell|buy|hold)\b|\bworth\s+(?:buying|investing|selling)\b"
    r"|\b(?:recommend|suggest)\s+(?:a\s+|some\s+)?(?:stocks?|shares?|investments?|portfolio|"
    r"trades?)\b|\bwhich\s+(?:stocks?|shares?|companies)\s+(?:should|to)\s+(?:i\s+|we\s+)?"
    r"(?:buy|sell|invest|pick)\b|\bprice\s+target\b|\bportfolio\s+(?:allocation|weights?)\b"
    r"|\bhow\s+much\s+(?:should\s+i|to)\s+invest\b|\bbest\s+(?:stock|share|investment)s?\b"
    r"|\bgood\s+time\s+to\s+(?:buy|sell|invest)\b",
    re.IGNORECASE,
)
_FORECAST = re.compile(
    r"\b(?:forecast|predict|prediction|projection|project(?:ed)?\s+to|outlook)\b"
    r"|\bwhat\s+will\b|\bwill\s+(?:\w+\s+){0,5}(?:rise|fall|go|be|increase|decrease|drop|"
    r"climb|crash|recover|hit|reach|move|change|cut|hike|raise)\b"
    r"|\bgoing\s+to\s+(?:rise|fall|go|be|increase|decrease|drop|climb|crash|hit|reach)\b"
    r"|\bnext\s+(?:year|quarter|month|week)(?:'s)?\b|\bin\s+the\s+future\b"
    r"|\bexpected\s+(?:price|level|value|rate)\b|\bwhere\s+will\b",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(
    r"\bif\b|\bsuppose\b|\bassum(?:e|ing)\b|\bscenario\b|\bwhat\s+happens\b|\bwhat\s+would\b"
    r"|\bin\s+case\b|\bwere\s+to\b|\bshock\b|\bsimulat",
    re.IGNORECASE,
)
_LIVE = re.compile(
    r"\b(?:today|right\s+now|at\s+the\s+moment|this\s+(?:morning|minute|hour|week)|live|"
    r"real[\s-]?time|currently\s+trading|intraday|as\s+of\s+now|current\s+(?:price|level|"
    r"quote|value|rate))\b",
    re.IGNORECASE,
)

FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwill\b", re.I), "predictive 'will'"),
    (re.compile(r"\bgoing\s+to\b", re.I), "prediction"),
    (re.compile(r"\bexpected\s+to\b", re.I), "prediction"),
    (re.compile(r"\bcaus(?:e|es|ed|ing)\b", re.I), "a causal claim"),
    (re.compile(r"\bguarantee", re.I), "a guarantee"),
    (re.compile(r"\brecommend", re.I), "a recommendation"),
    (re.compile(r"\b(?:should|must)\s+(?:buy|sell|hold|invest|short)\b", re.I), "advice"),
    (re.compile(r"\b(?:buy|sell|strong\s+buy)\s+(?:rating|signal|call)\b", re.I), "advice"),
    (re.compile(r"\bcertain(?:ly|ty)?\b|\bdefinitely\b|\bno\s+doubt\b", re.I), "certainty"),
    (re.compile(r"\brisk[\s-]free\b|\bsafe\s+bet\b", re.I), "a guarantee"),
)

WITHHELD = "[withheld: this stored text reads like an instruction]"
# Control, format (zero-width, direction, tag), surrogate, private-use and unassigned
# characters: invisible, or not text at all.
_INVISIBLE = frozenset(("Cc", "Cf", "Cs", "Co", "Cn"))


@dataclass(frozen=True)
class Screening:
    flags: tuple[Screen, ...]
    conditional: bool

    def has(self, flag: Screen) -> bool:
        return flag in self.flags


def clean(value: object, *, lines: bool = False) -> str:
    """Text without invisible characters (see ``_INVISIBLE``); tabs and, with ``lines``,
    line breaks are kept."""
    keep = "\t\n" if lines else "\t"
    return "".join(
        character
        for character in str(value)
        if character in keep or unicodedata.category(character) not in _INVISIBLE
    )


def _plain(text: str) -> str:
    """``text`` as the screening patterns read it: compatibility forms folded (full-width
    letters, ligatures) and invisible characters removed."""
    return clean(unicodedata.normalize("NFKC", text))


def screen(question: str) -> Screening:
    flags: list[Screen] = []
    question = _plain(question)
    if _INJECTION.search(question):
        flags.append("injection")
    if _SECRETS.search(question):
        flags.append("secrets")
    if _ADVICE.search(question):
        flags.append("advice")
    if _FORECAST.search(question):
        flags.append("forecast")
    if _LIVE.search(question):
        flags.append("live_data")
    return Screening(tuple(flags), conditional=bool(_CONDITIONAL.search(question)))


def phrasing_problems(text: str) -> list[str]:
    """What in ``text`` breaks the phrasing rules (empty when nothing does)."""
    return [reason for pattern, reason in FORBIDDEN if pattern.search(text)]


def data_text(value: object, limit: int = MAX_DATA_TEXT) -> str:
    """Stored text made safe to show a language model as data: invisible characters
    (control, zero-width, direction-override, tag) removed, whitespace collapsed, capped at
    ``limit`` characters, and withheld entirely if it reads like an instruction (also once
    full-width letters and other compatibility forms are folded)."""
    text = re.sub(r"\s+", " ", clean(value)).strip()
    if _INJECTION.search(text) or _INJECTION.search(_plain(text)):
        return WITHHELD
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- Fixed responses ---------------------------------------------------------------------------

DECLINED_INJECTION = (
    "This question contains instructions aimed at the Analyst itself, such as setting aside "
    "its rules or showing its configuration. The Analyst answers questions about RUMIN's "
    "records only, through a fixed set of read-only tools, so it has not acted on them."
)
DECLINED_SECRETS = (
    "The Analyst has no access to keys, passwords, connection details or other settings, and "
    "does not discuss them. It can answer questions about RUMIN's companies, relationships, "
    "stored data and scenarios."
)
ADVICE = (
    "RUMIN does not make investment decisions or tell anyone what to buy, sell or hold. What "
    "it can show is the context for a decision: which variables reach a company and through "
    "which relationships, what the stored data shows, and what stored scenarios simulated, "
    "with their assumptions and limits."
)
FORECAST = (
    "RUMIN does not forecast. It holds stored values up to their latest period and simulates "
    "the effect of changes a person states; a simulation holds only under its stated changes, "
    "figures and assumptions."
)
LIVE_DATA = (
    "RUMIN holds stored values, not live market data: every value has the period it describes "
    "and the time it was retrieved, shown with the evidence."
)
UNSUPPORTED = (
    "This is outside what the Analyst can answer from RUMIN's records. It answers questions "
    "about the companies, industries and economic variables in RUMIN, the relationships "
    "between them, stored data series, simulation models, scenarios and their results, and "
    "Financial Intelligence findings."
)
