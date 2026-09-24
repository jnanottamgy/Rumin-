"""Measure Financial Intelligence's API on the sample network and on larger SYNTHETIC ones.

Usage (from ``backend/``)::

    uv run python scripts/benchmark_intelligence.py                   # sample, 1000, 5000
    uv run python scripts/benchmark_intelligence.py --sizes sample,20000 --runs 7

For ``sample`` it migrates a fresh SQLite database, loads the illustrative dataset and the
series catalogue, builds the knowledge graph and executes the backend tests' REFERENCE
scenario (HYPOTHETICAL figures). For a number N it loads the SYNTHETIC benchmark network
of ``benchmark_graph.py`` with N fictional companies (no executions, no stored values) and
builds its graph. It then times, in-process through the API, what the Financial
Intelligence pages ask for: the overview, the entity list, a company's dossier and brief,
its exposure, the detected changes, storing an analysis and reading it back (which checks
its freshness). Each figure is the median of ``--runs`` runs after one warm-up.

The numbers this prints describe the machine it ran on, nothing more.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
API = "/api/v1"


def run(command: list[str], url: str) -> None:
    subprocess.run(  # noqa: S603 - fixed commands, no user input
        ["uv", "run", "--frozen", *command],  # noqa: S607
        check=True,
        env={**os.environ, "RUMIN_DATABASE_URL": url},
        cwd=BACKEND,
        capture_output=True,
    )


def prepare_sample(work: Path) -> str:
    url = f"sqlite:///{work / 'intelligence-sample.db'}"
    for command in (
        ["alembic", "upgrade", "head"],
        ["python", "-m", "app.db.seed"],
        ["python", "-m", "app.ingestion", "catalog"],
        ["python", "-m", "app.graph", "build"],
    ):
        run(command, url)
    return url


def prepare_synthetic(work: Path, companies: int) -> str:
    sys.path.insert(0, str(BACKEND / "scripts"))
    from benchmark_graph import synthetic_dataset

    dataset = work / f"synthetic-{companies}.json"
    dataset.write_text(json.dumps(synthetic_dataset(companies)), encoding="utf-8")
    url = f"sqlite:///{work / f'intelligence-{companies}.db'}"
    run(["alembic", "upgrade", "head"], url)
    run(["python", "-m", "app.db.seed", "--file", str(dataset)], url)
    run(["python", "-m", "app.graph", "build"], url)
    return url


def median_ms(action: Callable[[], object], runs: int) -> float:
    action()  # warm-up
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def measure(url: str, runs: int, *, sample: bool) -> dict[str, str]:
    sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=url,
        log_level="WARNING",
        scenario_execution_mode="inline",
    )
    results: dict[str, str] = {}
    with TestClient(create_app(settings)) as client:

        def get(path: str, **params: Any) -> Any:
            response = client.get(f"{API}{path}", params=params)
            if response.status_code != 200:
                raise SystemExit(f"GET {path}: {response.status_code} {response.text[:500]}")
            return response.json()

        if sample:
            from scenario_support import REFERENCE

            scenario = client.post(f"{API}/scenarios", json=REFERENCE).json()
            client.post(f"{API}/scenarios/{scenario['id']}/executions", json={})
            company = "company:co_aerisca_airways"
        else:
            listed = get("/intelligence/entities", kind="company")["items"]
            company = max(listed, key=lambda item: item["paths"])["entity"]["key"]

        overview = get("/intelligence/overview")
        results["companies (listed / total)"] = (
            f"{len(overview['exposure']['companies'])} / {overview['coverage']['companies']}"
            + (" (truncated)" if overview["coverage"]["truncated"] else "")
        )
        results["exposure paths (listed)"] = str(overview["coverage"]["exposure_paths"])
        results["findings (workspace)"] = str(len(overview["insights"]))
        results["overview (ms)"] = f"{median_ms(lambda: get('/intelligence/overview'), runs):.1f}"
        entities = get("/intelligence/entities")
        results["entity list (ms)"] = (
            f"{median_ms(lambda: get('/intelligence/entities'), runs):.1f} "
            f"({entities['total']} entities)"
        )
        dossier = get(f"/intelligence/entities/{company}")
        results["dossier (ms)"] = (
            f"{median_ms(lambda: get(f'/intelligence/entities/{company}'), runs):.1f} "
            f"({len(dossier['exposure']['paths'])} paths, {len(dossier['insights'])} findings)"
        )
        results["brief (ms)"] = (
            f"{median_ms(lambda: get(f'/intelligence/entities/{company}/brief'), runs):.1f}"
        )
        results["exposure only (ms)"] = (
            f"{median_ms(lambda: get(f'/intelligence/entities/{company}/exposure'), runs):.1f}"
        )
        results["changes (ms)"] = f"{median_ms(lambda: get('/intelligence/changes'), runs):.1f}"

        def store() -> Any:
            response = client.post(
                f"{API}/intelligence/analyses", json={"scope": "entity", "entity": company}
            )
            return response.json()

        stored_path = f"/intelligence/analyses/{store()['id']}"
        results["store an analysis (ms)"] = f"{median_ms(store, runs):.1f}"
        results["read it back, with freshness (ms)"] = (
            f"{median_ms(lambda: get(stored_path), runs):.1f}"
        )
        size = len(client.get(f"{API}/intelligence/entities/{company}").content)
        results["dossier size (KB, uncompressed)"] = f"{size / 1024:.0f}"
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", default="sample,1000,5000", help="'sample' or companies.")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="rumin-intelligence-"))
    table: dict[str, dict[str, str]] = {}
    for size in args.sizes.split(","):
        sample = size == "sample"
        url = prepare_sample(work) if sample else prepare_synthetic(work, int(size))
        table[size] = measure(url, args.runs, sample=sample)
        print(f"{size}: done", file=sys.stderr)
    rows = list(next(iter(table.values())).keys())
    sizes = list(table)
    print("| Measure | " + " | ".join(sizes) + " |")
    print("|---|" + "---|" * len(sizes))
    for row in rows:
        print(f"| {row} | " + " | ".join(table[size].get(row, "") for size in sizes) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
