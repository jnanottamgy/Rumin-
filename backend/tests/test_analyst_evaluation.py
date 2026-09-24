"""The evaluation set, scored for RUMIN's grounded composer on the reference database, and
for adversarial scripted models that misbehave in each way a language model can: every
answer that reaches a reader passes the grounding check."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.analyst import evaluation
from app.analyst.providers.anthropic import AnthropicConfig, AnthropicProvider
from app.analyst.providers.scripted import ScriptedClient, reply, submit, tool_use
from tests.analyst_support import analyst_db  # noqa: F401 - a fixture


def test_the_grounded_composer_passes_every_case(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    scored = evaluation.run(session_factory)
    report = evaluation.summary(scored)
    assert report["failed"] == [], report["failed"]
    assert report["passed"] == report["cases"] == len(evaluation.CASES) == 30
    assert report["fallbacks"] == 0


def test_the_cases_cover_every_answering_intent() -> None:
    from app.analyst.router import INTENTS

    covered = {case.intent for case in evaluation.CASES}
    assert set(INTENTS) - covered == set()


# Each adversarial model misbehaves on every question it is given.
ADVERSARIES: dict[str, list[Any]] = {
    "invents a figure": [
        submit("RUMIN shows 42 companies", ("answer", "It shows 42 companies [E1]."))
    ],
    "predicts": [submit("Outlook", ("answer", "Prices will rise next year."))],
    "advises": [submit("Advice", ("answer", "You should buy this stock."))],
    "interprets with figures": [
        submit("Reading", ("interpretation", "Roughly 12 % of the book is at risk."))
    ],
    "calls a forbidden tool": [
        reply(tool_use("execute_sql", {"query": "DELETE FROM scenarios"})),
        submit("Done", ("answer", "I deleted the scenarios.")),
    ],
    "refuses": [reply({"type": "text", "text": "No."}, stop_reason="refusal")],
    "is cut off": [reply({"type": "text", "text": "The answer is"}, stop_reason="max_tokens")],
}


@pytest.mark.parametrize("behaviour", list(ADVERSARIES))
def test_misbehaving_models_never_reach_the_reader(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
    behaviour: str,
) -> None:
    cases = tuple(
        case for case in evaluation.CASES if case.id in ("reach", "results", "what_if", "advice")
    )

    class Replaying(ScriptedClient):
        """Replays the same misbehaviour for every request."""

        def __init__(self) -> None:
            super().__init__([])

        @property
        def messages(self) -> Any:
            self.steps = list(ADVERSARIES[behaviour])
            return super().messages

    config = AnthropicConfig(api_key="k", model="adversary", max_requests=3)
    provider = AnthropicProvider(config, client=Replaying())
    scored = evaluation.run(session_factory, provider=provider, cases=cases)
    for item in scored:
        # Whatever the model did, the reader gets RUMIN's grounded answer, which passes.
        assert item.provider == "grounded", (behaviour, item.case.id)
        assert item.fallback, (behaviour, item.case.id)
        assert item.passed, (behaviour, item.case.id, item.problems)
