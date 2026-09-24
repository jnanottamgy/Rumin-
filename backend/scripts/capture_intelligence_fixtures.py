"""Capture the Financial Intelligence frontend test fixtures from a real backend.

Usage (from ``backend/``)::

    uv run python scripts/capture_intelligence_fixtures.py [WORK_DIR]

It migrates a fresh SQLite database in WORK_DIR (default: a temporary directory), loads the
illustrative sample dataset and the series catalogue (definitions only), builds the
knowledge graph, then drives the API in-process:

1. the methods, and the workspace before anything is simulated;
2. the backend tests' REFERENCE scenario — "oil, rupee and rates" on the fictional Aerisca
   Airways with HYPOTHETICAL round figures (``tests/scenario_support.py``) — executed; then
   the overview, the entity list, Aerisca's dossier and brief, an industry's dossier, a
   rejected threshold and a stored analysis;
3. SYNTHETIC exchange-rate and inflation histories (``tests/intelligence_support.py``) stored
   through the real ingestion pipeline from a scripted response, and the views that read
   them. Those files are named ``synthetic-*``: their values are test values, not World
   Bank data, whatever dataset they are filed under.

Every response is written to ``frontend/tests/fixtures/intelligence/`` as it came back
(then laid out by the frontend's formatter, when it is installed): nothing is edited by
hand. Nothing here is market data or any company's accounts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND.parent / "frontend" / "tests" / "fixtures" / "intelligence"
API = "/api/v1"
AERISCA = "company:co_aerisca_airways"
AIR_TRANSPORT = "industry:ind_air_transport"


def prepare_database(work: Path) -> str:
    database = work / "fixtures.db"
    database.unlink(missing_ok=True)
    url = f"sqlite:///{database}"
    environment = {**os.environ, "RUMIN_DATABASE_URL": url}
    for command in (
        ["alembic", "upgrade", "head"],
        ["python", "-m", "app.db.seed"],
        ["python", "-m", "app.ingestion", "catalog"],
        ["python", "-m", "app.graph", "build"],
    ):
        subprocess.run(  # noqa: S603 - fixed commands, no user input
            ["uv", "run", "--frozen", *command],  # noqa: S607
            check=True,
            env=environment,
            cwd=BACKEND,
            capture_output=True,
        )
    return url


def save(name: str, data: Any) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    (OUT / f"{name}.json").write_text(text, encoding="utf-8")
    print(f"{name}.json  {len(text):>8} bytes")


def main() -> None:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="rumin-"))
    work.mkdir(parents=True, exist_ok=True)
    url = prepare_database(work)

    sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
    from fastapi.testclient import TestClient
    from scenario_support import REFERENCE

    from app.core.config import Settings
    from app.db.session import create_db_engine, create_session_factory
    from app.main import create_app
    from app.services.graph import clear_freshness_cache
    from tests.intelligence_support import FX_SERIES, store_synthetic_history

    def ok(response: Any, expected: int = 200) -> Any:
        if response.status_code != expected:
            raise SystemExit(
                f"{response.request.method} {response.request.url}: "
                f"{response.status_code} {response.text[:2000]}"
            )
        return response.json()

    OUT.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=url,
        log_level="WARNING",
        scenario_execution_mode="inline",
    )
    with TestClient(create_app(settings)) as client:
        save("methods", ok(client.get(f"{API}/intelligence/methods")))
        save("overview-unsimulated", ok(client.get(f"{API}/intelligence/overview")))

        scenario = ok(client.post(f"{API}/scenarios", json=REFERENCE), 201)
        ok(client.post(f"{API}/scenarios/{scenario['id']}/executions", json={}), 202)

        save("overview", ok(client.get(f"{API}/intelligence/overview")))
        save("entities", ok(client.get(f"{API}/intelligence/entities")))
        save("entity", ok(client.get(f"{API}/intelligence/entities/{AERISCA}")))
        save("brief", ok(client.get(f"{API}/intelligence/entities/{AERISCA}/brief")))
        save("industry", ok(client.get(f"{API}/intelligence/entities/{AIR_TRANSPORT}")))
        save(
            "threshold-error",
            ok(
                client.get(f"{API}/intelligence/overview", params={"relative_change_percent": "0"}),
                422,
            ),
        )
        stored = ok(
            client.post(
                f"{API}/intelligence/analyses",
                json={"scope": "entity", "entity": AERISCA, "label": "Before the data arrived"},
            ),
            201,
        )
        save("analysis", stored)

        # SYNTHETIC values through the real pipeline (see the module docstring).
        engine = create_db_engine(url)
        with create_session_factory(engine)() as session:
            store_synthetic_history(session)
        engine.dispose()
        clear_freshness_cache()

        save("synthetic-overview", ok(client.get(f"{API}/intelligence/overview")))
        save("synthetic-entity", ok(client.get(f"{API}/intelligence/entities/{AERISCA}")))
        save("synthetic-series", ok(client.get(f"{API}/intelligence/series/{FX_SERIES}")))
        save(
            "synthetic-analysis-stale",
            ok(client.get(f"{API}/intelligence/analyses/{stored['id']}")),
        )
        save("analyses", ok(client.get(f"{API}/intelligence/analyses")))

    frontend = BACKEND.parent / "frontend"
    if (frontend / "node_modules").is_dir():
        subprocess.run(  # noqa: S603 - fixed command, no user input
            ["npx", "--no-install", "biome", "format", "--write", str(OUT)],  # noqa: S607
            check=True,
            cwd=frontend,
            capture_output=True,
        )


if __name__ == "__main__":
    main()
