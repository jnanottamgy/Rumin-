"""Capture the 3D universe's frontend test fixtures from a real backend.

Usage (from ``backend/``)::

    uv run python scripts/capture_universe_fixtures.py [WORK_DIR]

It migrates a fresh SQLite database in WORK_DIR (default: a temporary directory), loads the
illustrative sample dataset and the series catalogue (definitions only), builds the
knowledge graph, and executes the backend tests' REFERENCE scenario on the fictional
Aerisca Airways with HYPOTHETICAL round figures (``tests/scenario_support.py``). Then it
reads, through the API, what the 3D universe reads:

1. the graph's overview and vocabulary, and every node and edge of the build (one page
   each: the sample graph is far below the page limit);
2. a node's and an edge's details, a neighbourhood, and the paths between two nodes;
3. the scenarios with their latest executions, and the reference execution with its
   modelled pathway and its results.

Every response is written to ``frontend/tests/fixtures/universe/`` as it came back (then
laid out by the frontend's formatter, when it is installed): nothing is edited by hand.
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
OUT = BACKEND.parent / "frontend" / "tests" / "fixtures" / "universe"
API = "/api/v1"
COMPANY = "company:co_aerisca_airways"
VARIABLE = "variable:var_brent_crude"


def prepare_database(work: Path) -> str:
    database = work / "universe.db"
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
    from app.main import create_app

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
        scenario = ok(client.post(f"{API}/scenarios", json=REFERENCE), 201)
        execution = ok(client.post(f"{API}/scenarios/{scenario['id']}/executions", json={}), 202)

        overview = ok(client.get(f"{API}/graph/overview"))
        save("overview", overview)
        save("types", ok(client.get(f"{API}/graph/types")))
        nodes = ok(client.get(f"{API}/graph/nodes", params={"limit": 500}))
        edges = ok(client.get(f"{API}/graph/edges", params={"limit": 500}))
        if nodes["total"] > len(nodes["items"]) or edges["total"] > len(edges["items"]):
            raise SystemExit("The sample graph no longer fits one page; capture more pages.")
        save("nodes", nodes)
        save("edges", edges)
        save("node-company", ok(client.get(f"{API}/graph/nodes/{COMPANY}")))
        save("node-variable", ok(client.get(f"{API}/graph/nodes/{VARIABLE}")))
        save(
            "neighborhood-company",
            ok(
                client.get(
                    f"{API}/graph/nodes/{COMPANY}/neighborhood",
                    params={"depth": 1, "max_nodes": 100},
                )
            ),
        )
        save(
            "neighborhood-variable",
            ok(
                client.get(
                    f"{API}/graph/nodes/{VARIABLE}/neighborhood",
                    params={"depth": 1, "max_nodes": 40},
                )
            ),
        )
        save(
            "paths",
            ok(client.get(f"{API}/graph/paths", params={"from": COMPANY, "to": VARIABLE})),
        )

        executed = ok(client.get(f"{API}/scenario-executions/{execution['id']}"))
        save("execution", executed)
        pathway = ok(client.get(f"{API}/scenario-executions/{execution['id']}/pathways"))
        save("pathways", pathway)
        save("results", ok(client.get(f"{API}/scenario-executions/{execution['id']}/results")))
        save("scenarios", ok(client.get(f"{API}/scenarios")))
        transmission = next(
            link["edge"]["edge_key"]
            for link in pathway["links"]
            if link["kind"] == "transmission" and link.get("edge")
        )
        save("edge-transmission", ok(client.get(f"{API}/graph/edges/{transmission}")))

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
