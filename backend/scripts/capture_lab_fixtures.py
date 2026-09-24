"""Capture the Scenario Lab's frontend test fixtures from a real backend.

Usage (from ``backend/``)::

    uv run python scripts/capture_lab_fixtures.py [WORK_DIR]

It migrates a fresh SQLite database in WORK_DIR (default: a temporary directory), loads the
illustrative sample dataset, builds the knowledge graph, then drives the API in-process:

1. the templates, and the airline template as the Lab opens it (no figures entered yet);
2. the backend tests' REFERENCE scenario — "oil, rupee and rates" on the fictional Aerisca
   Airways with HYPOTHETICAL round figures (see ``tests/scenario_support.py``) — with the
   definitions of the models it includes, saved and executed, with its results, pathway,
   explanation, a sensitivity analysis and a reproducibility check;
3. a second scenario (Brent alone) executed and compared with the first.

Every response is written to ``frontend/tests/fixtures/lab/`` as it came back: nothing is
edited by hand. Nothing here is market data or any company's accounts.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND.parent / "frontend" / "tests" / "fixtures" / "lab"
API = "/api/v1"


def prepare_database(work: Path) -> str:
    database = work / "fixtures.db"
    database.unlink(missing_ok=True)
    url = f"sqlite:///{database}"
    environment = {**os.environ, "RUMIN_DATABASE_URL": url}
    for command in (
        ["alembic", "upgrade", "head"],
        ["python", "-m", "app.db.seed"],
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
    print(f"{name}.json  {len(text):>7} bytes")


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
        save("templates", ok(client.get(f"{API}/scenario-templates")))
        save("template", ok(client.get(f"{API}/scenario-templates/crude_oil_airline")))

        # The airline template as the Lab opens it: its change and company, no figures yet.
        opened = {
            "name": "Crude oil shock on an airline",
            "template_id": "crude_oil_airline",
            "shocks": [
                {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": "20"}
            ],
            "entity": "company:co_aerisca_airways",
        }
        save("preview-needs-figures", ok(client.post(f"{API}/scenarios/preview", json=opened)))

        # The full preview of REFERENCE is large and not stored: the tests assemble it from
        # the execution's plan, results and pathway, and check it against the contract.
        preview = ok(client.post(f"{API}/scenarios/preview", json=REFERENCE))
        assert preview["stored"] is False and preview["results"] is not None  # noqa: S101

        # The definitions of the models the reference scenario includes: the builder
        # renders each one's own inputs and assumptions from them.
        included = [
            model["model_id"]
            for model in preview["plan"]["models"]
            if model["status"] == "included"
        ]
        save(
            "models",
            {model: ok(client.get(f"{API}/simulation-models/{model}")) for model in included},
        )

        scenario = ok(client.post(f"{API}/scenarios", json=REFERENCE), 201)
        execution = ok(client.post(f"{API}/scenarios/{scenario['id']}/executions", json={}), 202)
        path = f"{API}/scenario-executions/{execution['id']}"
        save("execution", ok(client.get(path)))
        save("results", ok(client.get(f"{path}/results")))
        save("pathway", ok(client.get(f"{path}/pathways")))
        explanation = client.get(f"{path}/explanation", params={"target": "profit_before_tax"})
        save("explanation", ok(explanation))
        analysis = client.post(f"{path}/sensitivity", json={"metric": None, "inputs": []})
        save("sensitivity", ok(analysis, 201))
        save("verification", ok(client.post(f"{path}/verify")))

        # A second scenario, Brent alone, to compare with.
        alone = copy.deepcopy(REFERENCE)
        alone["name"] = "Oil alone on Aerisca"
        alone["shocks"] = alone["shocks"][:1]
        for model in ("floating_rate_interest", "fx_exposure"):
            alone["models"].pop(model)
        other = ok(client.post(f"{API}/scenarios", json=alone), 201)
        other_execution = ok(client.post(f"{API}/scenarios/{other['id']}/executions", json={}), 202)
        compared = client.get(
            f"{API}/scenario-comparisons",
            params=[("execution_id", execution["id"]), ("execution_id", other_execution["id"])],
        )
        save("comparison", ok(compared))

        save("scenario", ok(client.get(f"{API}/scenarios/{scenario['id']}")))
        save("scenarios", ok(client.get(f"{API}/scenarios")))
        save("executions", ok(client.get(f"{API}/scenarios/{scenario['id']}/executions")))


if __name__ == "__main__":
    main()
