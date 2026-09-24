"""The grounding check: figures must be found in the evidence their sentence cites, at the
precision displayed; interpretation and general paragraphs carry no figures; phrasing rules
hold. Pure unit tests over hand-made evidence (no database)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analyst.answer import (
    Column,
    NoticeBlock,
    TableBlock,
    TableRow,
    text,
)
from app.analyst.evidence import Evidence, EvidenceLedger, Knowledge, SourceRef, exact
from app.analyst.grounding import check, figures, literals, sentences

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
D = Decimal


def ledger() -> list[Evidence]:
    book = EvidenceLedger()
    book.add(
        tool="compare_periods",
        call=1,
        kind=Knowledge.OBSERVED,
        title="Official exchange rate: 2020–2025",
        source=SourceRef(kind="series", id="wb-ind-pa-nus-fcrf", label="Exchange rate"),
        retrieved_at=NOW,
        period="2020–2025",
        values={"2020": "74.1", "2025": "92.1", "change": "24.2914979757085020242914979757085"},
    )
    book.add(
        tool="get_execution",
        call=2,
        kind=Knowledge.SIMULATED,
        title="Execution of 'Oil on Aerisca' (version 2)",
        detail="The fare recovery will lag, the model assumes.",
        source=SourceRef(kind="execution", id="x-1", label="Oil on Aerisca"),
        retrieved_at=NOW,
        models=["airline_fuel_cost 1.1.0"],
        values={"operating_profit.change": "-6325000", "cost": "12450000", "version": 2},
    )
    return book.items


def test_exact_decimal_text() -> None:
    assert exact(D("84.2000")) == "84.2"
    assert exact(D("-0.0")) == "0"
    assert exact(D("1E+3")) == "1000"
    assert exact(None) is None


def test_ledger_keeps_one_record_per_source_and_adds_values() -> None:
    book = EvidenceLedger()
    source = SourceRef(kind="series", id="s", label="S")
    first = book.add(
        tool="a",
        call=1,
        kind=Knowledge.OBSERVED,
        title="S",
        source=source,
        retrieved_at=NOW,
        values={"2020": "1"},
    )
    again = book.add(
        tool="b",
        call=2,
        kind=Knowledge.OBSERVED,
        title="S",
        source=source,
        retrieved_at=NOW,
        values={"2021": "2", "2020": "999"},
    )
    assert first == again == "E1"
    item = book.get("E1")
    assert item is not None and item.values == {"2020": "1", "2021": "2"}
    other = book.add(
        tool="c", call=3, kind=Knowledge.SIMULATED, title="S", source=source, retrieved_at=NOW
    )
    assert other == "E2"  # the same record as a different kind of knowledge is separate


@pytest.mark.parametrize(
    ("written", "value", "quantum", "kind", "signed"),
    [
        ("24.29 %", "24.29", "0.01", "percent", False),
        ("−6,325,000", "-6325000", "1", "number", True),
        ("+1.8 pp", "1.8", "0.1", "points", True),
        ("50 bps", "0.5", "0.01", "points", False),
        ("₹1.25 crore", "12500000", "100000", "number", False),
        ("1,24,50,000", "12450000", "1", "number", False),
        ("3.5 lakh", "350000", "10000", "number", False),
        ("12.45 million", "12450000", "10000", "number", False),
        ("2025", "2025", "1", "year", False),
    ],
)
def test_figures_are_read_with_their_precision(
    written: str, value: str, quantum: str, kind: str, signed: bool
) -> None:
    (found,) = figures(f"It is {written} here.")
    assert (found.value, found.quantum, found.kind, found.signed) == (
        D(value),
        D(quantum),
        kind,
        signed,
    )


def test_identifiers_citations_and_times_are_not_figures() -> None:
    assert figures("See wb-ind-pa-nus-fcrf and var_usd_inr [E12] at 2026-09-24T10:00:00Z.") == []
    assert literals("model airline_fuel_cost 1.1.0 on 2026-09-24T10:00:00Z") == [
        "1.1.0",
        "2026-09-24",
    ]


def test_sentences_keep_a_trailing_citation_with_their_sentence() -> None:
    assert sentences("It rose 24.29 %. [E1] E.g. the U.S. series is stored.") == [
        "It rose 24.29 %. [E1]",
        "E.g. the U.S. series is stored.",
    ]


@pytest.mark.parametrize(
    "sentence",
    [
        "The rate rose 24.29 % between 2020 and 2025 [E1].",
        "The rate rose 24.3 % [E1].",
        "It moved from 74.1 to 92.1 [E1].",
        "Operating profit fell by 6,325,000 INR [E2].",
        "Operating profit changed by −6,325,000 INR [E2].",
        "Costs rose by ₹1.245 crore [E2].",
        "Costs rose by 1,24,50,000 [E2].",
        "In version 2 of the scenario [E2], the model airline_fuel_cost 1.1.0 was used [E2].",
    ],
)
def test_supported_figures_pass(sentence: str) -> None:
    result = check("Headline", [text("answer", sentence)], ledger())
    assert result.passed, result.problems


@pytest.mark.parametrize(
    ("sentence", "reason"),
    [
        ("The rate rose 24.28 % [E1].", "Not found"),  # wrong at the precision shown
        ("The rate rose 25 % [E1].", "Not found"),
        ("Operating profit changed by +6,325,000 INR [E2].", "Not found"),  # wrong sign
        ("The rate rose 24.29 % [E2].", "Not found"),  # right figure, wrong citation
        ("The rate rose 24.29 %.", "without a citation"),
        ("It rose in 2019 [E1].", "Not found"),  # a year no cited record mentions
        ("It rose 24.29 % [E9].", "does not exist"),
        ("Model 2.0.0 was used [E2].", "date or version"),
        ("Costs will rise [E2].", "Phrasing"),
        ("The shock caused the loss [E2].", "Phrasing"),
    ],
)
def test_unsupported_figures_and_phrasing_fail(sentence: str, reason: str) -> None:
    result = check("Headline", [text("answer", sentence)], ledger())
    assert not result.passed
    assert any(reason in problem.reason for problem in result.problems), result.problems


def test_interpretation_and_general_paragraphs_may_not_hold_figures() -> None:
    for role in ("interpretation", "general"):
        failing = check("H", [text(role, "About 24 % of this matters.")], ledger())
        assert not failing.passed
        assert "may not contain figures" in failing.problems[0].reason
        assert check("H", [text(role, "Jet fuel is refined from crude oil.")], ledger()).passed


def test_a_quotation_of_a_cited_record_is_not_the_answer_speaking() -> None:
    quoted = "The record says “The fare recovery will lag, the model assumes.” [E2]"
    assert check("H", [text("detail", quoted)], ledger()).passed
    invented = "The record says “Fares will rise.” [E2]"
    assert not check("H", [text("detail", invented)], ledger()).passed


def test_the_headline_may_use_any_evidence_of_the_answer() -> None:
    assert check("Up 24.29 % from 2020 to 2025", [], ledger()).passed
    failing = check("Up 30 %", [], ledger())
    assert not failing.passed
    assert failing.problems[0].block is None
    assert "any evidence of the answer" in failing.problems[0].reason


def test_notices_and_tables_must_cite_existing_evidence() -> None:
    table = TableBlock(
        title="T",
        columns=[Column(key="a", label="A")],
        rows=[TableRow(cells={"a": "x"}, citations=["E7"])],
    )
    result = check("H", [table], ledger())
    assert not result.passed and "E7" in result.problems[0].reason
    good = NoticeBlock(
        kind="assumption", title="Read as", text="Read as 24.29 %.", citations=["E1"]
    )
    assert check("H", [good], ledger()).passed
    bare = NoticeBlock(kind="assumption", title="Read as", text="Read as 24.29 %.")
    assert not check("H", [bare], ledger()).passed
