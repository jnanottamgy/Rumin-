"""Measure the knowledge graph on SYNTHETIC networks of increasing size.

Usage (from ``backend/``)::

    uv run python scripts/benchmark_graph.py                      # SQLite, default sizes
    uv run python scripts/benchmark_graph.py --sizes 100,1000
    uv run python scripts/benchmark_graph.py --postgres postgresql+psycopg://...

For each size (a number of companies) it:

1. writes a SYNTHETIC dataset — companies, industries and variables named "Synthetic …"
   and marked fictional, attached to 20 real countries — and loads it with the real,
   validating seed loader into a fresh database;
2. runs the real graph build, then an unchanged rebuild, and times both;
3. times the read service behind each graph endpoint (median of several runs after one
   warm-up): overview (first request, which checks freshness against every source
   record, and cached), search, node detail, neighbourhoods of a typical company and of
   a hub country at depths 1-3 (200-node cap), shortest paths and components.

Nothing here is real data or a claim about production: the numbers describe the machine
and database the script ran on. Results print as a Markdown table.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401 — registers every table on Base.metadata
from app.db.base import Base
from app.db.seed import load_dataset
from app.graph.algorithms import Direction
from app.graph.assemble import assemble
from app.graph.build import run_build
from app.graph.isic import section_for_division
from app.graph.sources import read_sources
from app.graph.store import SqlAdjacency
from app.schemas.graph import NeighborhoodResponse, NodeSearchPage, PathsResponse
from app.services import graph

# Real ISO 3166-1 alpha-2 codes with their ISO 4217 currencies (reference data).
COUNTRIES = (
    ("IN", "India", "INR"),
    ("US", "United States", "USD"),
    ("AE", "United Arab Emirates", "AED"),
    ("GB", "United Kingdom", "GBP"),
    ("DE", "Germany", "EUR"),
    ("FR", "France", "EUR"),
    ("JP", "Japan", "JPY"),
    ("CN", "China", "CNY"),
    ("BR", "Brazil", "BRL"),
    ("ZA", "South Africa", "ZAR"),
    ("SG", "Singapore", "SGD"),
    ("AU", "Australia", "AUD"),
    ("CA", "Canada", "CAD"),
    ("MX", "Mexico", "MXN"),
    ("KR", "Republic of Korea", "KRW"),
    ("ID", "Indonesia", "IDR"),
    ("SA", "Saudi Arabia", "SAR"),
    ("CH", "Switzerland", "CHF"),
    ("SE", "Sweden", "SEK"),
    ("NG", "Nigeria", "NGN"),
)
ASSUMED_EFFECTS = ("affects_costs", "affects_revenue", "affects_financing")
RUNS = 5


def synthetic_dataset(companies: int, seed: int = 7) -> dict[str, Any]:
    """A valid dataset file of fictional records around real countries and ISIC codes."""
    rng = random.Random(seed)  # noqa: S311 — reproducible test data, not security
    divisions = [f"{n:02d}" for n in range(1, 100) if section_for_division(f"{n:02d}")]
    industry_count = min(len(divisions), max(4, companies // 60))
    variable_count = max(4, companies // 25)

    countries: list[dict[str, Any]] = [
        {
            "id": f"cty_{code.lower()}",
            "name": name,
            "description": f"{name}, from ISO reference data.",
            "iso_alpha2": code,
            "currency_code": currency,
            "reference": f"ISO 3166-1 alpha-2 country code {code}; ISO 4217 code {currency}.",
        }
        for code, name, currency in COUNTRIES
    ]
    industries: list[dict[str, Any]] = [
        {
            "id": f"ind_syn_{index:03d}",
            "name": f"Synthetic industry {index:03d}",
            "description": "SYNTHETIC benchmark industry (not real).",
            "classification_system": "ISIC Rev. 4",
            "classification_code": divisions[index],
            "is_fictional": True,
        }
        for index in range(industry_count)
    ]
    variables: list[dict[str, Any]] = [
        {
            "id": f"var_syn_{index:04d}",
            "name": f"Synthetic variable {index:04d}",
            "description": "SYNTHETIC benchmark variable (not real).",
            "unit": "index",
            "value_kind": "index",
            "frequency": "monthly",
            "category": "inflation",
            "country_id": rng.choice(countries)["id"],
            "is_fictional": True,
        }
        for index in range(variable_count)
    ]
    company_records: list[dict[str, Any]] = [
        {
            "id": f"co_syn_{index:06d}",
            "name": f"Synthetic Company {index:06d}",
            "description": "SYNTHETIC benchmark company (not real).",
            "industry_id": rng.choice(industries)["id"],
            "country_id": rng.choice(countries)["id"],
            "is_fictional": True,
        }
        for index in range(companies)
    ]

    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def relate(kind: str, source: str, target: str, polarity: str = "not_applicable") -> None:
        if source == target or (kind, source, target) in seen:
            return
        seen.add((kind, source, target))
        relationships.append(
            {
                "id": f"rel_syn_{len(relationships):07d}",
                "type": kind,
                "source_id": source,
                "target_id": target,
                "polarity": polarity,
                "strength": rng.choice(("weak", "moderate", "strong")),
                "description": "SYNTHETIC benchmark relationship (not real).",
                "rationale": "Generated for a performance measurement; it means nothing.",
            }
        )

    ids: list[str] = [company["id"] for company in company_records]
    variable_ids: list[str] = [variable["id"] for variable in variables]
    for company in ids:
        for _ in range(2):
            relate("supplies_to", company, rng.choice(ids))
        if rng.random() < 0.1:
            relate("lends_to", company, rng.choice(ids))
        if rng.random() < 0.2:
            other = rng.choice(ids)
            relate("competes_with", min(company, other), max(company, other))
        relate(
            rng.choice(ASSUMED_EFFECTS),
            rng.choice(variable_ids),
            company,
            rng.choice(("positive", "negative")),
        )
    for industry in industries:
        for _ in range(2):
            relate(
                rng.choice(ASSUMED_EFFECTS),
                rng.choice(variable_ids),
                industry["id"],
                rng.choice(("positive", "negative")),
            )
    for variable in variable_ids:
        relate("influences", variable, rng.choice(variable_ids), "positive")

    return {
        "dataset": {
            "id": f"benchmark-synthetic-{companies}",
            "version": "1.0.0",
            "name": f"SYNTHETIC benchmark network ({companies} companies)",
            "description": "Generated by scripts/benchmark_graph.py. Not real data.",
            "is_illustrative": True,
            "provenance_note": "Synthetic: generated for performance measurement only.",
            "license": "None (synthetic test data)",
        },
        "countries": countries,
        "industries": industries,
        "economic_variables": variables,
        "companies": company_records,
        "relationships": relationships,
    }


def median_ms(action: Callable[[], object], runs: int = RUNS) -> float:
    action()  # warm-up
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def measure(size: int, url: str | None, workdir: Path) -> dict[str, str]:
    dataset = workdir / f"synthetic-{size}.json"
    dataset.write_text(json.dumps(synthetic_dataset(size)), encoding="utf-8")
    database = url or f"sqlite:///{workdir / f'bench-{size}.db'}"
    engine = create_engine(database)
    if url:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    results: dict[str, str] = {}

    with factory() as session:
        start = time.perf_counter()
        load_dataset(session, dataset)
        results["load dataset (s)"] = f"{time.perf_counter() - start:.2f}"

        start = time.perf_counter()
        snapshot = read_sources(session)
        read_s = time.perf_counter() - start
        start = time.perf_counter()
        assemble(snapshot, today=date.today())
        results["build: read + assemble (s)"] = f"{read_s:.2f} + {time.perf_counter() - start:.2f}"

        start = time.perf_counter()
        first = run_build(session)
        results["first build (s)"] = f"{time.perf_counter() - start:.2f}"
        results["nodes / edges"] = f"{first.build.node_count:,} / {first.build.edge_count:,}"
        start = time.perf_counter()
        again = run_build(session)
        results["unchanged rebuild (s)"] = f"{time.perf_counter() - start:.2f}"
        results["rebuild changed"] = str(
            again.build.nodes_added
            + again.build.nodes_changed
            + again.build.edges_added
            + again.build.edges_changed
        )

    rng = random.Random(size)  # noqa: S311 — reproducible picks, not security
    company = f"company:co_syn_{rng.randrange(size):06d}"
    other = f"company:co_syn_{rng.randrange(size):06d}"

    with factory() as session:

        def hood(focus: str, depth: int) -> NeighborhoodResponse:
            return graph.neighborhood(
                session,
                focus,
                depth=depth,
                max_nodes=200,
                edge_types=[],
                node_types=[],
                direction=Direction.ANY,
                evidence_statuses=[],
                include_illustrative=True,
            )

        def paths() -> PathsResponse:
            return graph.paths(
                session,
                company,
                other,
                max_depth=6,
                limit=3,
                direction=Direction.ANY,
                edge_types=[],
                evidence_statuses=[],
                include_illustrative=True,
            )

        def search() -> NodeSearchPage:
            return graph.search_nodes(
                session,
                q="company 00004",
                node_types=[],
                related_to=None,
                nature=None,
                sort="name",
                limit=20,
                offset=0,
            )

        def cold_overview() -> object:
            graph.clear_freshness_cache()  # the first request after a build or restart
            return graph.overview(session)

        results["overview, first request (ms)"] = f"{median_ms(cold_overview):.1f}"
        results["overview, cached (ms)"] = f"{median_ms(lambda: graph.overview(session)):.1f}"
        results["search by name (ms)"] = f"{median_ms(search):.1f}"
        results["node detail (ms)"] = f"{median_ms(lambda: graph.get_node(session, company)):.1f}"
        for focus, name in ((company, "company"), ("country:cty_in", "hub country")):
            for depth in (1, 2, 3):
                answer = hood(focus, depth)
                ms = median_ms(lambda f=focus, d=depth: hood(f, d))  # type: ignore[misc]
                results[f"neighbourhood, {name}, depth {depth} (ms)"] = (
                    f"{ms:.1f} ({len(answer.nodes)} nodes, {answer.queries} queries"
                    f"{', truncated' if answer.truncated else ''})"
                )
        found = paths()
        results["shortest paths, 2 companies (ms)"] = (
            f"{median_ms(paths):.1f} (length {found.length}, "
            f"{found.nodes_explored:,} explored{', budget hit' if found.budget_exhausted else ''})"
        )
        ms = median_ms(lambda: graph.components(session, limit=10))
        results["components (ms)"] = f"{ms:.1f}"
        adjacency = SqlAdjacency(session)
        adjacency.incident([company])
        results["incident() round trips per level"] = str(adjacency.queries)
    engine.dispose()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", default="100,1000,5000,20000", help="Companies per run.")
    parser.add_argument(
        "--postgres", default=None, help="A PostgreSQL URL to use instead of SQLite (wiped)."
    )
    args = parser.parse_args(argv)
    sizes = [int(item) for item in args.sizes.split(",") if item]

    table: dict[str, dict[int, str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for size in sizes:
            print(f"measuring {size:,} companies…", file=sys.stderr)
            for label, value in measure(size, args.postgres, Path(tmp)).items():
                table.setdefault(label, {})[size] = value

    engine = "PostgreSQL" if args.postgres else "SQLite"
    print(f"\nKnowledge graph on SYNTHETIC data ({engine}; median of {RUNS} runs)\n")
    print("| Measure | " + " | ".join(f"{size:,} companies" for size in sizes) + " |")
    print("|---|" + "---|" * len(sizes))
    for label, values in table.items():
        print(f"| {label} | " + " | ".join(values.get(size, "") for size in sizes) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
