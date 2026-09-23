"""Name normalisation and identifier checks for entity resolution.

Normalised names are used **only to suggest** that two records may describe the same
entity. They never merge anything: a merge needs a shared identifier or an explicit link
(see ``app.graph.resolution``). Original names are always kept and displayed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.ingestion.normalize import currency_is_valid, isin_is_valid, mic_is_valid

# Legal-form words removed from the *end* of a name ("Acme Steel Pvt Ltd" → "acme steel").
LEGAL_FORMS = frozenset(
    {
        "ag",
        "bv",
        "co",
        "company",
        "corp",
        "corporation",
        "gmbh",
        "inc",
        "incorporated",
        "kk",
        "limited",
        "llc",
        "llp",
        "lp",
        "ltd",
        "nv",
        "plc",
        "private",
        "pte",
        "pty",
        "pvt",
        "sa",
        "spa",
        "srl",
    }
)

# Common abbreviations, expanded so "Kovalent Intl" and "Kovalent International" compare
# equal. Kept short on purpose: every entry makes more names look alike.
ABBREVIATIONS = {
    "grp": "group",
    "hldgs": "holdings",
    "intl": "international",
    "mfg": "manufacturing",
    "natl": "national",
    "svcs": "services",
}

STOP_WORDS = frozenset({"and", "of", "the"})
_NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")


def _fold(text: str) -> str:
    """Lower-case, with accents removed ("Réfining" → "refining")."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def name_tokens(name: str) -> list[str]:
    """The words of a normalised name, in order."""
    text = _fold(name).replace("&", " and ")
    tokens = [ABBREVIATIONS.get(token, token) for token in _NON_ALPHANUMERIC.sub(" ", text).split()]
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in LEGAL_FORMS:
        tokens = tokens[:-1]
    return tokens


def normalize_name(name: str) -> str:
    """A comparison key for a name: case, accents, punctuation, ``&``, a leading "The",
    common abbreviations and trailing legal forms are normalised.

    >>> normalize_name("The Deltrin Refining Co. Pvt. Ltd.")
    'deltrin refining'
    """
    return " ".join(name_tokens(name))


class MatchStrength(StrEnum):
    """How strongly two names suggest the same entity. Neither is proof."""

    # The normalised names are identical.
    STRONG = "strong"
    # Every distinctive word of one name appears in the other ("Tata Steel" /
    # "Tata Steel Europe"): often a parent and a subsidiary, i.e. different entities.
    WEAK = "weak"


@dataclass(frozen=True)
class NameMatch:
    strength: MatchStrength
    reason: str


def name_words(normalized: str) -> frozenset[str]:
    """The distinct words of a normalised name, without stop words."""
    return frozenset(normalized.split()) - STOP_WORDS


def compare_names(first: str, second: str) -> NameMatch | None:
    """Whether two names are similar enough to be reviewed as a possible match."""
    a, b = normalize_name(first), normalize_name(second)
    return compare_normalized(a, name_words(a), b, name_words(b))


def compare_normalized(
    a: str, words_a: frozenset[str], b: str, words_b: frozenset[str]
) -> NameMatch | None:
    """``compare_names`` for names already normalised, so a name is normalised once no
    matter how many others it is compared with."""
    if not a or not b:
        return None
    if a == b:
        return NameMatch(
            MatchStrength.STRONG,
            f'Both names normalise to "{a}" (case, punctuation and legal forms ignored).',
        )
    if words_a == words_b:
        return NameMatch(
            MatchStrength.WEAK, f'"{a}" and "{b}" have the same words in another order.'
        )
    if len(words_a) > len(words_b):
        a, b, words_a, words_b = b, a, words_b, words_a
    distinctive = [word for word in words_a if len(word) >= 5]
    if words_a and words_a < words_b and (len(words_a) >= 2 or distinctive):
        return NameMatch(MatchStrength.WEAK, f'Every word of "{a}" also appears in "{b}".')
    return None


# --- Identifier checks -----------------------------------------------------------------------

_ALPHA2 = re.compile(r"^[A-Z]{2}$")
_ALPHA3 = re.compile(r"^[A-Z]{3}$")


def iso_alpha2_is_valid(code: str) -> bool:
    """Format only (two capital letters): RUMIN holds no copy of the ISO 3166 list."""
    return bool(_ALPHA2.match(code))


def iso_alpha3_is_valid(code: str) -> bool:
    """Format only (three capital letters)."""
    return bool(_ALPHA3.match(code))


__all__ = [
    "LEGAL_FORMS",
    "STOP_WORDS",
    "MatchStrength",
    "NameMatch",
    "compare_names",
    "currency_is_valid",
    "isin_is_valid",
    "iso_alpha2_is_valid",
    "iso_alpha3_is_valid",
    "mic_is_valid",
    "name_tokens",
    "normalize_name",
]
