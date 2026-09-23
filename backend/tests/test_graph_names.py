"""Name normalisation for entity resolution — and the false matches it must not make."""

from __future__ import annotations

import pytest

from app.graph.names import (
    MatchStrength,
    compare_names,
    iso_alpha2_is_valid,
    iso_alpha3_is_valid,
    normalize_name,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("The Deltrin Refining Co. Pvt. Ltd.", "deltrin refining"),
        ("DELTRIN REFINING LIMITED", "deltrin refining"),
        ("Solvane Réfining", "solvane refining"),
        ("A & B Holdings Inc", "a and b holdings"),
        ("Kovalent Intl.", "kovalent international"),
        ("  Anvaya   Bank  ", "anvaya bank"),
        # A name that *is* a legal form keeps its word rather than becoming empty.
        ("Company", "company"),
        ("The", "the"),
    ],
)
def test_normalize_name(name: str, expected: str) -> None:
    assert normalize_name(name) == expected


def test_legal_forms_are_removed_only_at_the_end() -> None:
    # "Company" in the middle of a name is part of the name.
    assert normalize_name("Company Secretaries Group Ltd") == "company secretaries group"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("ABC Holdings Ltd", "ABC Holdings Limited"),
        ("Kovalent Intl", "Kovalent International Pvt Ltd"),
        ("SOLVANE RÉFINING", "Solvane Refining"),
    ],
)
def test_strong_candidates(first: str, second: str) -> None:
    match = compare_names(first, second)
    assert match is not None and match.strength is MatchStrength.STRONG


@pytest.mark.parametrize(
    ("first", "second"),
    [
        # A subsidiary contains its parent's name: a different entity, noted for review.
        ("Tata Steel", "Tata Steel Europe"),
        ("Deltrin", "Deltrin Refining"),
        ("Bank of Anvaya", "Anvaya Bank"),
    ],
)
def test_weak_candidates(first: str, second: str) -> None:
    match = compare_names(first, second)
    assert match is not None and match.strength is MatchStrength.WEAK


@pytest.mark.parametrize(
    ("first", "second"),
    [
        # Sharing a generic word is not a candidate.
        ("Deltrin Refining", "Solvane Refining"),
        ("Anvaya Bank", "Brookvane Bank"),
        ("Bank", "Anvaya Bank"),
        ("Air", "Skyvara Air"),
        ("Orvane Petroleum", "Tessaline Energy"),
        ("", "Anvaya Bank"),
    ],
)
def test_no_candidate(first: str, second: str) -> None:
    assert compare_names(first, second) is None


def test_country_code_formats() -> None:
    assert iso_alpha2_is_valid("IN") and not iso_alpha2_is_valid("IND")
    assert not iso_alpha2_is_valid("in")
    assert iso_alpha3_is_valid("IND") and not iso_alpha3_is_valid("IN")
