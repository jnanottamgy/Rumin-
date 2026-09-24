"""Measure the Scenario Lab's API on the illustrative sample network.

Usage (from ``backend/``)::

    uv run python scripts/benchmark_lab.py                    # SQLite in a temporary directory
    uv run python scripts/benchmark_lab.py --runs 9
    uv run python scripts/benchmark_lab.py --postgres postgresql+psycopg://user:pass@localhost/x

It migrates a fresh database, loads the sample dataset, builds the knowledge graph and then
times, in-process, what the Lab's pages ask for: the plan and the live preview, saving,
executing (inline, so the whole execution is inside the request), reading the results,
pathway and explanation, a default sensitivity analysis, a comparison and a
reproducibility check — for the backend tests' REFERENCE scenario (three models, three
changes, 12 months, two stress cases) and a LARGE one (the same over 36 months with five
stress cases). Each figure is the median of ``--runs`` runs after one warm-up. It then
starts the background runner (thread mode) and times executions from the request to the
final state, as a browser polling the API sees them.

The company figures are the reference case's HYPOTHETICAL round numbers. The numbers this
prints describe the machine it ran on, nothing more. ``--postgres`` **wipes** the database
it is given (it drops the ``public`` schema): point it at a scratch database only.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
API = "/api/v1"


def prepare(url: str) -> None:
    if url.startswith("postgresql"):
        from sqlalchemy import create_engine, text

        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        engine.dispose()
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


def median_ms(action: Callable[[], Any], runs: int) -> tuple[float, Any]:
    result = action()  # warm-up
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        result = action()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--postgres", help="a scratch PostgreSQL URL (wiped)")
    options = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="rumin-lab-bench-"))
    url = options.postgres or f"sqlite:///{work / 'bench.db'}"
    prepare(url)

    sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
    from fastapi.testclient import TestClient
    from scenario_support import REFERENCE

    from app.core.config import Settings
    from app.main import create_app

    large = copy.deepcopy(REFERENCE)
    large["name"] = "Large"
    large["timing"] = {"start_month": 1, "duration_months": 0, "horizon_months": 36}
    large["stress_cases"] = [
        {"name": f"× {scale}", "scale": scale} for scale in ("0.25", "0.5", "1.5", "2", "3")
    ]

    def ok(response: Any, expected: int = 200) -> Any:
        if response.status_code != expected:
            raise SystemExit(f"{response.request.url}: {response.status_code} {response.text}")
        return response.json()

    def settings(mode: str) -> Settings:
        return Settings(
            _env_file=None,
            environment="test",
            database_url=url,
            log_level="WARNING",
            scenario_execution_mode=mode,
        )

    rows: list[tuple[str, str, str]] = []
    sizes: dict[str, int] = {}
    with TestClient(create_app(settings("inline"))) as client:
        for label, body in (("reference", REFERENCE), ("large", large)):
            counter = iter(range(1_000_000))

            def create(body: dict[str, Any] = body, counter: Any = counter) -> Any:
                named = {**body, "name": f"{body['name']} {next(counter)}"}
                return ok(client.post(f"{API}/scenarios", json=named), 201)

            plan, _ = median_ms(
                lambda b=body: ok(client.post(f"{API}/scenarios/plan", json=b)), options.runs
            )
            preview, previewed = median_ms(
                lambda b=body: ok(client.post(f"{API}/scenarios/preview", json=b)), options.runs
            )
            save, _ = median_ms(create, options.runs)
            scenario = create()

            def execute(scenario_id: str = scenario["id"]) -> Any:
                return ok(client.post(f"{API}/scenarios/{scenario_id}/executions", json={}), 202)

            executed_ms, execution = median_ms(execute, options.runs)
            path = f"{API}/scenario-executions/{execution['id']}"
            results_ms, results = median_ms(
                lambda p=path: ok(client.get(f"{p}/results")), options.runs
            )
            pathway_ms, pathway = median_ms(
                lambda p=path: ok(client.get(f"{p}/pathways")), options.runs
            )
            explain_ms, explanation = median_ms(
                lambda p=path: ok(
                    client.get(f"{p}/explanation", params={"target": "profit_before_tax"})
                ),
                options.runs,
            )
            sensitivity_ms, analysis = median_ms(
                lambda p=path: ok(
                    client.post(f"{p}/sensitivity", json={"metric": None, "inputs": []}), 201
                ),
                options.runs,
            )
            verify_ms, verification = median_ms(
                lambda p=path: ok(client.post(f"{p}/verify")), options.runs
            )
            assert verification["reproduced"]  # noqa: S101
            other = execute()
            compare_ms, _ = median_ms(
                lambda e=execution, o=other: ok(
                    client.get(
                        f"{API}/scenario-comparisons",
                        params=[("execution_id", e["id"]), ("execution_id", o["id"])],
                    )
                ),
                options.runs,
            )
            stages = {stage["stage"]: stage for stage in ok(client.get(path))["stages"]}
            rows += [
                (label, "Plan (`POST /scenarios/plan`)", f"{plan:.1f}"),
                (label, "Live preview (`POST /scenarios/preview`)", f"{preview:.1f}"),
                (label, "Save a scenario (a new scenario and its version 1)", f"{save:.1f}"),
                (
                    label,
                    "Execute, inline: the whole execution in the request",
                    f"{executed_ms:.1f}",
                ),
                (label, "Results", f"{results_ms:.1f}"),
                (label, "Pathway", f"{pathway_ms:.1f}"),
                (label, "Explanation of profit before tax", f"{explain_ms:.1f}"),
                (
                    label,
                    f"Default sensitivity analysis ({analysis['evaluations']} evaluations)",
                    f"{sensitivity_ms:.1f}",
                ),
                (
                    label,
                    "Reproducibility check (re-execute and compare hashes)",
                    f"{verify_ms:.1f}",
                ),
                (label, "Compare two executions", f"{compare_ms:.1f}"),
            ]
            for stage in ("validating", "simulating", "propagating", "aggregating"):
                entry = stages.get(stage)
                if entry and entry["finished_at"]:
                    started = entry["started_at"]
                    finished = entry["finished_at"]
                    elapsed = (
                        datetime.fromisoformat(finished) - datetime.fromisoformat(started)
                    ).total_seconds() * 1000
                    rows.append((label, f"… stage {stage} (as stored)", f"{elapsed:.1f}"))
            for name, payload in (
                ("preview", previewed),
                ("execution", ok(client.get(path))),
                ("results", results),
                ("pathway", pathway),
                ("explanation", explanation),
            ):
                sizes[f"{label} {name}"] = len(json.dumps(payload, separators=(",", ":")))

    # The background runner: request → final state, as a polling browser sees it.
    with TestClient(create_app(settings("thread"))) as client:
        scenario = ok(client.post(f"{API}/scenarios", json={**REFERENCE, "name": "Threaded"}), 201)
        waits = []
        for _ in range(options.runs + 1):
            start = time.perf_counter()
            execution = ok(
                client.post(f"{API}/scenarios/{scenario['id']}/executions", json={}), 202
            )
            first = execution["status"]
            while execution["status"] not in ("completed", "failed", "cancelled"):
                time.sleep(0.005)
                execution = ok(client.get(f"{API}/scenario-executions/{execution['id']}"))
            waits.append(((time.perf_counter() - start) * 1000, first, execution["status"]))
        waits = waits[1:]
        rows.append(
            (
                "reference",
                f"Background execution, request → {waits[0][2]} (first answer: {waits[0][1]})",
                f"{statistics.median(wait for wait, _, _ in waits):.1f}",
            )
        )

    database = "PostgreSQL" if options.postgres else "SQLite"
    print(f"## {database} — median of {options.runs} runs (ms)\n")
    print("| Scenario | Measure | ms |\n|---|---|---|")
    for label, measure, value in rows:
        print(f"| {label} | {measure} | {value} |")
    print("\n| Payload | bytes (compact JSON) |\n|---|---|")
    for name, size in sizes.items():
        print(f"| {name} | {size:,} |")


if __name__ == "__main__":
    main()
