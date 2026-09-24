"""Fixtures for the Analyst tests: RUMIN's reference database for questions.

The curated sample network built into a knowledge graph, the SYNTHETIC exchange-rate and
inflation histories (``tests/intelligence_support.py``) and one executed scenario on Aerisca
Airways with HYPOTHETICAL company figures (``tests/scenario_support.py``). Import the
fixtures into a test module to use them.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.intelligence_support import store_synthetic_history
from tests.scenario_support import reference

API = "/api/v1"


def execute(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    scenario = client.post(f"{API}/scenarios", json=body or reference())
    assert scenario.status_code == 201, scenario.text
    execution = client.post(f"{API}/scenarios/{scenario.json()['id']}/executions", json={})
    assert execution.status_code == 202, execution.text
    found: dict[str, Any] = execution.json()
    assert found["status"] == "completed"
    return found


@pytest.fixture
def analyst_db(built_graph: Session, client: TestClient) -> Iterator[TestClient]:
    """A client on the reference database: graph, SYNTHETIC history, one execution."""
    store_synthetic_history(built_graph)
    execute(client)
    yield client
