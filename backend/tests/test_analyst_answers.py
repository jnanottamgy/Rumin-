"""How RUMIN's grounded composer words and lays out answers on the reference database: each
fact said once, lines that no model covers named, listings that say when they are capped,
and a declined forecast that still shows what is stored. Every answer passes the grounding
check."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.analyst import composer
from app.analyst.answer import (
    Answer,
    NoticeBlock,
    PathsBlock,
    ScenarioBlock,
    SeriesBlock,
    TableBlock,
    TextBlock,
    text,
)
from app.analyst.context import Focus
from app.analyst.evidence import Knowledge
from app.analyst.orchestrator import Orchestrator, TurnResult
from app.analyst.providers.base import ProviderResult
from app.analyst.providers.grounded import GroundedProvider
from tests.analyst_support import analyst_db  # noqa: F401 - a fixture

AERISCA = "company:co_aerisca_airways"


def ask(
    session_factory: sessionmaker[Session], question: str, focus: Focus | None = None
) -> TurnResult:
    result = Orchestrator(session_factory).answer(question, focus=focus)
    assert result.answer.grounding is not None and result.answer.grounding.passed
    assert result.fallback is None
    return result


def blocks(answer: Answer, kind: type[Any]) -> list[Any]:
    return [block for block in answer.blocks if isinstance(block, kind)]


def test_a_connection_is_drawn_once_and_its_limit_said_once(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    answer = ask(
        session_factory, "How is Aerisca Airways connected to the USD/INR exchange rate?"
    ).answer
    assert answer.headline == "USD/INR exchange rate and Aerisca Airways are 1 relationship apart"
    (paths,) = blocks(answer, PathsBlock)
    assert paths.note is None
    # The chain is drawn by the display, not written out again as a paragraph.
    assert not any("→" in block.text for block in blocks(answer, TextBlock))
    (notice,) = blocks(answer, NoticeBlock)
    assert notice.title == "A connection, not a cause"


def test_a_series_limitation_is_a_notice_not_also_a_caption(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    answer = ask(session_factory, "Show India's official exchange rate since 2015").answer
    (series,) = blocks(answer, SeriesBlock)
    assert series.note is None
    assert [notice.title for notice in blocks(answer, NoticeBlock)] == [
        "Not the same measure as the variable"
    ]


def test_a_preview_names_the_lines_no_model_covers_once(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    answer = ask(session_factory, "What if Brent crude rises 20% for Aerisca Airways?").answer
    (card,) = blocks(answer, ScenarioBlock)
    assert card.status == "preview"
    assert len(card.notes) == len(set(card.notes))
    not_modelled = [note for note in card.notes if note.startswith("Not modelled:")]
    assert not_modelled, card.notes
    assert any("Profit before tax" in note for note in not_modelled)
    # Every line the models did not cover is named in one of the notes.
    assert all(line.label not in " ".join(not_modelled) for line in card.lines)


def test_a_stored_execution_card_explains_what_is_not_modelled(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    answer = ask(session_factory, "What did the latest scenario on Aerisca Airways show?").answer
    (card,) = blocks(answer, ScenarioBlock)
    assert card.status == "stored"
    assert card.notes == [
        "Not modelled: Cash flow. No included model covers these lines, and not modelled is "
        "not the same as unchanged."
    ]
    text = " ".join(block.text for block in blocks(answer, TextBlock))
    assert "The largest contribution to the change in profit before tax comes from" in text
    assert "credit" not in text.lower()


def test_a_declined_forecast_shows_what_is_stored_instead(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    result = ask(session_factory, "What will India's inflation be next year?")
    answer = result.answer
    assert (result.route.intent, answer.status) == ("forecast", "declined")
    assert answer.headline == "RUMIN does not forecast; here is what it has stored"
    assert blocks(answer, TextBlock)[0].role == "policy"
    (series,) = blocks(answer, SeriesBlock)
    assert series.title.startswith("Inflation, consumer prices")
    assert "What if India CPI inflation rises 1 percentage point?" in answer.follow_ups


def test_a_listing_names_what_it_lists_and_says_when_it_is_capped(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = ask(session_factory, "Which companies are in India?").answer
    (table,) = blocks(answer, TableBlock)
    assert table.title == "Companies in India"
    assert answer.headline.endswith("companies in India")
    assert "Records matching" not in table.title

    monkeypatch.setattr(composer, "SEARCH_LIMIT", 3)
    capped = ask(session_factory, "List the companies").answer
    assert capped.headline == "The first 3 companies"
    assert blocks(capped, TextBlock)[0].text.startswith("Listed here: the first 3 companies")


def test_a_bare_figure_after_a_connection_asks_instead_of_guessing(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    focus = Focus(intent="connection", subject=AERISCA, entity=AERISCA)
    result = ask(session_factory, "What about 30%?", focus)
    assert (result.route.intent, result.answer.status) == ("clarify", "clarification")
    assert result.answer.headline == "Which variable should change by 30%?"
    assert result.calls == []


def test_tool_summaries_count_in_words(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    result = ask(session_factory, "What does RUMIN know about Aerisca Airways?")
    (call,) = result.calls
    assert call.output is not None
    assert "1 stored execution," in call.output.summary
    assert "executions" not in call.output.summary


def test_a_grounded_draft_that_fails_the_check_is_withheld_in_part(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RUMIN's own composer is held to the same check as a language model: a sentence with a
    # figure its evidence does not hold is not shown, and the answer says so.
    compose = GroundedProvider.answer

    def with_an_invented_figure(self: GroundedProvider, context: Any) -> ProviderResult:
        result = compose(self, context)
        result.draft.blocks.insert(0, text("answer", "RUMIN holds 4,242 companies [E1]."))
        return result

    monkeypatch.setattr(GroundedProvider, "answer", with_an_invented_figure)
    answer = (
        Orchestrator(session_factory).answer("What does RUMIN know about Aerisca Airways?").answer
    )
    assert answer.grounding is not None and answer.grounding.passed
    assert answer.status == "partial"
    assert answer.headline == "What RUMIN holds on Aerisca Airways"
    assert not any("4,242" in block.text for block in blocks(answer, TextBlock))
    assert blocks(answer, NoticeBlock)[-1].title == "Part of this answer was withheld"
    assert blocks(answer, PathsBlock) and blocks(answer, ScenarioBlock)


def test_a_clarification_may_repeat_the_figure_of_the_question(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    focus = Focus(intent="connection", subject=AERISCA, entity=AERISCA)
    answer = ask(session_factory, "What about 30%?", focus).answer
    (question,) = answer.evidence
    assert (question.kind, question.values) == (Knowledge.USER_INPUT, {"figure.1": "30"})


def test_an_identifier_written_in_an_answer_is_in_its_evidence(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    # "(build 17)" once passed only where the build number happened to equal another count.
    answer = ask(session_factory, "What data does RUMIN hold?").answer
    (coverage,) = [item for item in answer.evidence if item.title == "What RUMIN holds"]
    build = coverage.values["graph_build"]
    assert any(f"(build {build})" in block.text for block in blocks(answer, TextBlock))
    assert answer.status == "answered"
