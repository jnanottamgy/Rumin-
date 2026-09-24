"""A live check of the Anthropic provider against the real API.

Runs only when ``RUMIN_ANTHROPIC_API_KEY`` and ``RUMIN_ANALYST_MODEL`` are set (it spends
tokens), and is skipped otherwise — including in CI. It asks a few questions of the
evaluation set and requires every answer shown to pass the grounding check, whether the
model's draft passed it or the grounded composer replaced it.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.analyst import evaluation
from app.core.config import Settings
from app.services.analyst import AnalystRuntime
from tests.analyst_support import analyst_db  # noqa: F401 - a fixture

LIVE = bool(os.environ.get("RUMIN_ANTHROPIC_API_KEY") and os.environ.get("RUMIN_ANALYST_MODEL"))

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE, reason="RUMIN_ANTHROPIC_API_KEY and RUMIN_ANALYST_MODEL unset"),
]


def test_live_answers_pass_the_grounding_check(
    analyst_db: TestClient,  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(analyst_provider="anthropic")
    provider = AnalystRuntime(settings, session_factory).provider()
    assert provider.name == "anthropic"
    cases = tuple(
        case for case in evaluation.CASES if case.id in ("reach", "period_change", "results")
    )
    scored = evaluation.run(session_factory, provider=provider, cases=cases)
    for item in scored:
        assert item.status is not None
        assert "did not pass the grounding check" not in item.problems, item.problems
