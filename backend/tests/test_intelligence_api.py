"""Financial intelligence end to end, on the real database (SQLite or PostgreSQL): exposure
from validated relationships, drivers from stored contributions, detected changes, model
interpretations, insights with their evidence chains, briefs, thresholds and stored
analyses. Company figures are HYPOTHETICAL (``tests/scenario_support.py``); stored values
are SYNTHETIC (``tests/intelligence_support.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.graph.store import GraphReader
from app.intelligence.engine import latest_executions
from app.intelligence.exposure import (
    WORKSPACE_LIMIT,
    entity_exposure,
    paths_for,
    variable_reach,
)
from app.intelligence.graphview import AFFECTS, listed_companies, load_workspace, members
from app.intelligence.model import GRADE_STRENGTH, Grade
from app.models import GraphEdge, IntelligenceAnalysis, ScenarioExecution, SimulationRun
from app.openapi_export import build_openapi
from app.simulation.definitions import sha256
from tests.intelligence_support import FX_SERIES, store_synthetic_history
from tests.scenario_support import AERISCA, reference

API = "/api/v1"
D = Decimal
NOT_FORECAST = "Simulated under the scenario's changes, figures and assumptions: not a forecast."
FORBIDDEN = (" will ", "caused", "guarantee", "recommend", "should buy", "should sell")


@pytest.fixture
def intel(built_graph: Session, client: TestClient) -> Iterator[TestClient]:
    """A client on a database with a built knowledge graph (and no stored values)."""
    yield client


@pytest.fixture
def with_history(built_graph: Session, intel: TestClient) -> Iterator[TestClient]:
    """The same, with the SYNTHETIC exchange-rate and inflation histories stored."""
    store_synthetic_history(built_graph)
    yield intel


@pytest.fixture(autouse=True)
def _no_stored_analyses(session_factory: sessionmaker[Session]) -> Iterator[None]:
    yield
    with session_factory() as session:
        session.execute(delete(IntelligenceAnalysis))
        session.commit()


def get(client: TestClient, path: str, expect: int = 200, **params: Any) -> Any:
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == expect, response.text
    return response.json()


def post(client: TestClient, path: str, payload: Any, expect: int) -> Any:
    response = client.post(f"{API}{path}", json=payload)
    assert response.status_code == expect, response.text
    return response.json()


def execute(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    scenario = post(client, "/scenarios", body or reference(), 201)
    execution: dict[str, Any] = post(client, f"/scenarios/{scenario['id']}/executions", {}, 202)
    assert execution["status"] == "completed"
    return execution


def details(error: dict[str, Any]) -> list[tuple[str | None, str | None, str | None]]:
    return [(d["location"], d["field"], d["type"]) for d in error["error"]["details"]]


def by_rule(insights: list[dict[str, Any]], rule: str) -> list[dict[str, Any]]:
    return [item for item in insights if item["rule"] == rule]


def assert_grounded(insight: dict[str, Any]) -> None:
    """The integrity every insight must meet."""
    chain = insight["chain"]
    assert chain, insight["id"]
    grades = []
    for step in chain:
        if step["basis"] == "relationship":
            grades.append(
                {
                    "evidence_backed": "documented",
                    "analyst_created": "curated",
                    "model_assumption": "assumed",
                    "unverified": "unverified",
                }[step["evidence_status"]]
            )
        elif step["basis"] == "simulation":
            grades.append("simulated")
        elif step["basis"] in ("observation", "calculation", "record"):
            grades.append("observed")
    weakest = min(grades, key=lambda grade: GRADE_STRENGTH[Grade(grade)])
    assert insight["evidence"]["grade"] == weakest, insight["id"]
    simulated = any(step["basis"] == "simulation" for step in chain)
    assert insight["evidence"]["conditional_on_simulation"] is simulated
    if simulated:
        assert NOT_FORECAST in insight["limitations"] or "not a forecast" in " ".join(
            insight["limitations"]
        )
    text = f" {insight['headline']} {insight['statement']} ".lower()
    for word in FORBIDDEN:
        assert word not in text, (word, insight["statement"])


# --- Exposure ----------------------------------------------------------------------------------


def test_exposure_comes_from_validated_relationships_only(intel: TestClient) -> None:
    exposure = get(intel, f"/intelligence/entities/{AERISCA}/exposure")

    assert sorted(
        (
            p["origin"]["key"],
            p["variable"]["key"],
            p["channel"],
            p["directness"],
            tuple(p["models"]),
        )
        for p in exposure["paths"]
    ) == [
        (
            "variable:var_brent_crude",
            "variable:var_jet_fuel",
            "costs",
            "upstream",
            ("airline_fuel_cost",),
        ),
        (
            "variable:var_jet_fuel",
            "variable:var_jet_fuel",
            "costs",
            "via_industry",
            ("airline_fuel_cost",),
        ),
        ("variable:var_us_fed_funds", "variable:var_usd_inr", "costs", "upstream", ()),
        ("variable:var_usd_inr", "variable:var_usd_inr", "costs", "direct", ("fx_exposure",)),
    ]
    assert all(e["quality_status"] == "validated" for p in exposure["paths"] for e in p["edges"])
    assert {
        (c["role"], c["counterparty"]["key"], c["level"]) for c in exposure["counterparties"]
    } == {
        ("supplier", "company:co_deltrin_refining", "company"),
        ("lender", "company:co_anvaya_bank", "company"),
        ("supplier", "industry:ind_petroleum_refining", "industry"),
    }
    # A competitor, the industry, sector, country and currency are context, never exposure.
    kinds = {(link["kind"], link["node"]["key"]) for link in exposure["context"]}
    assert ("competitor", "company:co_skyvara_air") in kinds
    assert ("industry", "industry:ind_air_transport") in kinds
    assert exposure["summary"]["by_evidence"] == {"model_assumption": 4}

    strict = get(intel, f"/intelligence/entities/{AERISCA}/exposure", evidence="evidence_backed")
    assert strict["paths"] == [] and strict["removed_by_filter"] == 4


def test_the_workspace_states_each_listed_company_exposure_in_full(built_graph: Session) -> None:
    """The workspace is bounded by companies, never by edges: every company it lists has
    exactly the paths its own analysis finds, including when the listing is cut short."""
    build = GraphReader(built_graph).latest_build()
    assert build is not None
    for limit in (3, WORKSPACE_LIMIT):
        graph = load_workspace(built_graph, build.id, limit=limit)
        membership = members(graph)
        companies = [key for key, node in graph.nodes.items() if node.node_type == "company"]
        listed = [key for key in companies if key in membership or graph.by_target(key, *AFFECTS)]
        assert graph.truncated is (limit == 3)
        assert listed
        for key in listed:
            shown = paths_for(graph, key, membership.get(key, []))
            own = entity_exposure(built_graph, key, build.id).paths
            assert [[e.key for e in p.edges] for p in shown] == [
                [e.key for e in p.edges] for p in own
            ], key


def test_a_variable_lists_the_companies_it_reaches(intel: TestClient) -> None:
    reach = get(intel, "/intelligence/variables/variable:var_usd_inr/exposure")

    companies = [item["company"]["key"] for item in reach["companies"]]
    assert AERISCA in companies and len(companies) == reach["total"] == 7
    assert reach["truncated"] is False
    assert "never how much" in reach["note"]


def test_a_variable_is_followed_through_the_whole_graph(built_graph: Session) -> None:
    """The reach of a variable is found by walking downstream from it, not by searching the
    workspace's listing: a short listing reports the total, and every company listed has the
    paths through the variable that its own analysis finds."""
    build = GraphReader(built_graph).latest_build()
    assert build is not None
    first_three, _ = listed_companies(built_graph, limit=3)
    for variable in ("variable:var_usd_inr", "variable:var_brent_crude"):
        full = variable_reach(built_graph, build.id, variable)
        short = variable_reach(built_graph, build.id, variable, limit=2)

        # Found beyond what a short workspace listing would show.
        assert {company.key for company, _ in full.companies} - set(first_three)

        assert not full.truncated and full.total == len(full.companies) > 2
        assert short.truncated and short.total == full.total and len(short.companies) == 2
        assert [c.key for c, _ in short.companies] == [c.key for c, _ in full.companies][:2]
        names = [c.name for c, _ in full.companies]
        assert names == sorted(names)
        for company, paths in full.companies:
            own = [
                p
                for p in entity_exposure(built_graph, company.key, build.id).paths
                if variable in p.variable_keys
            ]
            assert [[e.key for e in p.edges] for p in paths] == [
                [e.key for e in p.edges] for p in own
            ], (variable, company.key)


# --- Drivers -----------------------------------------------------------------------------------


def test_drivers_are_the_stored_contributions(intel: TestClient) -> None:
    execution = execute(intel)

    found = get(intel, f"/intelligence/entities/{AERISCA}/drivers")

    drivers = found["drivers"]
    assert (
        drivers["execution"]["id"] == execution["id"] and drivers["headline"] == "profit_before_tax"
    )
    line = next(item for item in drivers["lines"] if item["id"] == "profit_before_tax")
    contributions = {c["variable_id"]: c for c in line["contributions"]}
    assert {key: D(c["value"]) for key, c in contributions.items()} == {
        "var_brent_crude": D(-5_637_500),
        "var_usd_inr": D(-687_500),
        "var_rbi_repo_rate": D(-375_000),
    }
    assert sum(D(c["value"]) for c in line["contributions"]) == D(line["change"]) == D(-6_700_000)
    assert D(line["residual"]) == 0
    assert D(contributions["var_brent_crude"]["share_of_change"]) == D("84.1417910448")
    assert D(contributions["var_brent_crude"]["per_unit"]) == D(-281_875)
    assert contributions["var_rbi_repo_rate"]["per_unit_label"] == "1 percentage point"
    assert [(u["model_id"], u["variable_ids"]) for u in drivers["unstated"]] == [
        ("floating_rate_interest", ["var_rbi_repo_rate"])
    ]
    assert "Cash flow" in drivers["not_modelled"]
    assert {f["label"] for f in drivers["figures"]} >= {"Annual fuel consumption"}
    assert found["previous"] is None


def test_an_entity_without_executions_has_no_drivers(intel: TestClient) -> None:
    found = get(intel, "/intelligence/entities/company:co_skyvara_air/drivers")

    assert found["drivers"] is None and found["executions"] == []
    assert "No completed execution" in found["note"]


def test_next_steps_are_gathered_once_and_name_what_to_check(intel: TestClient) -> None:
    execute(intel)

    dossier = get(intel, f"/intelligence/entities/{AERISCA}")

    gathered = dossier["next_steps"]
    assert [step["action"] for step in gathered].count("run_sensitivity") == 1
    edges = {e["key"]: e for p in dossier["exposure"]["paths"] for e in p["edges"]}
    evidence = [step for step in gathered if step["action"] == "find_evidence"]
    assert len(evidence) == 4  # one per variable reaching Aerisca
    for step in evidence:
        assert step["target"]["kind"] == "graph_edge"
        assert edges[step["target"]["id"]]["evidence_status"] == "model_assumption"
        assert f"“{step['target']['label']}”" in step["text"]


# --- The dossier -------------------------------------------------------------------------------


def test_every_insight_rests_on_an_evidence_chain(
    intel: TestClient, session_factory: sessionmaker[Session]
) -> None:
    execute(intel)

    dossier = get(intel, f"/intelligence/entities/{AERISCA}")

    insights = dossier["insights"]
    rules = {item["rule"] for item in insights}
    assert {"S01", "S02", "S03", "E01", "E02", "E03", "C01"} <= rules
    for insight in insights:
        assert_grounded(insight)
    (impact,) = by_rule(insights, "S01")
    assert impact["evidence"]["grade"] == "assumed"  # it rests on assumed relationships
    assert {f["label"]: f["value"] for f in impact["facts"]}["Profit before tax: change"] == (
        "-6700000"
    )
    assert any("rests on your figures alone" in note for note in impact["limitations"])
    (coverage,) = by_rule(insights, "C01")
    assert "also simulates RBI policy repo rate" in coverage["statement"]
    assert all(item["evidence"]["grade"] == "assumed" for item in by_rule(insights, "E01"))
    (dependency,) = by_rule(insights, "E02")
    assert dependency["statement"].startswith(
        "Jet fuel price (U.S. Gulf Coast) and USD/INR exchange rate each lie on 2 of"
    )
    order = [item["kind"] for item in insights]
    assert order.index("impact") < order.index("exposure") < order.index("coverage")
    assert sum(dossier["grades"].values()) == len(insights)

    # Provenance: every record an insight cites exists.
    refs = [ref for item in insights for step in item["chain"] for ref in step["refs"]]
    with session_factory() as session:
        edges = {r["id"] for r in refs if r["kind"] == "graph_edge"}
        assert edges and edges <= set(session.scalars(select(GraphEdge.id)).all())
        executions = {r["id"] for r in refs if r["kind"] == "execution"}
        stored = {str(item) for item in session.scalars(select(ScenarioExecution.id)).all()}
        assert executions and executions <= stored
        runs = {r["id"] for r in refs if r["kind"] == "run"}
        assert runs and runs <= {str(item) for item in session.scalars(select(SimulationRun.id))}


def test_an_industry_can_be_analysed(intel: TestClient) -> None:
    dossier = get(intel, "/intelligence/entities/industry:ind_air_transport")

    assert dossier["entity"]["node_type"] == "industry" and dossier["drivers"] is None
    assert {item["rule"] for item in dossier["insights"]} >= {"E01", "C01"}
    assert [s["id"] for s in dossier["signals"]] == ["exposure_breadth", "dependency"]


def test_unknown_or_unsuitable_subjects_are_refused(intel: TestClient) -> None:
    assert get(intel, "/intelligence/entities/company:co_missing", 404)["error"]["code"] == (
        "not_found"
    )
    refused = get(intel, "/intelligence/entities/variable:var_usd_inr", 422)
    assert details(refused) == [("path", "entity_key", "not_an_entity")]
    assert "an economic variable" in refused["error"]["message"]
    wrong = get(intel, f"/intelligence/variables/{AERISCA}/exposure", 422)
    assert details(wrong) == [("path", "variable_key", "not_a_variable")]
    get(intel, "/intelligence/entities/not-a-key", 422)
    get(intel, "/intelligence/series/wb-missing-series", 404)
    get(intel, "/intelligence/instruments/xnse-missing", 404)


# --- Observed data -----------------------------------------------------------------------------


def test_observed_changes_are_detected_against_thresholds(with_history: TestClient) -> None:
    changes = get(with_history, "/intelligence/changes")

    observed = {
        (item["subject"]["id"], item["change"]["later"]["label"]): item
        for item in changes["observed"]
    }
    fx = observed[(FX_SERIES, "2025")]
    assert fx["change"]["value"] == "9.3824228029" and fx["latest"] is True
    assert fx["change"]["earlier"]["value"] == "84.2"  # the revised value, not 83.7
    assert fx["threshold_name"] == "relative_change_percent" and fx["threshold"] == "5"
    cpi = observed[("wb-ind-fp-cpi-totl-zg", "2025")]
    assert cpi["change"]["value"] == "-1.8" and cpi["subject"]["change_unit"] == (
        "percentage_points"
    )
    (revision,) = changes["revisions"]
    assert (revision["revision"]["previous"], revision["revision"]["revised"]) == ("83.7", "84.2")
    assert revision["revision"]["change"] == "0.5973715651"
    assert any("not observations" in note for note in changes["notes"])

    strict = get(with_history, "/intelligence/changes", relative_change_percent="10")
    assert (FX_SERIES, "2025") not in {
        (i["subject"]["id"], i["change"]["later"]["label"]) for i in strict["observed"]
    }


def test_a_series_is_analysed_with_its_signals(with_history: TestClient) -> None:
    found = get(with_history, f"/intelligence/series/{FX_SERIES}")

    analysis = found["analysis"]
    assert analysis["points_total"] == 16 and analysis["latest"]["value"] == "9.3824228029"
    assert analysis["trend"]["direction"] == "rising" and analysis["trend"]["slope"] == "4.2"
    assert (analysis["trend"]["first"], analysis["trend"]["last"]) == ("2021", "2025")
    assert [s["id"] for s in analysis["signals"]] == ["trend", "volatility", "anomaly"]
    assert found["variable"]["key"] == "variable:var_usd_inr" and len(found["reached"]) == 7
    rules = {item["rule"]: item for item in found["insights"]}
    assert {"D01", "D02", "D04", "D06"} <= set(rules)
    for insight in found["insights"]:
        assert_grounded(insight)
    assert rules["D01"]["evidence"]["grade"] == "observed"
    assert rules["D01"]["headline"].endswith("rose 9.38 %")
    assert "does not say the change affected them" in rules["D02"]["statement"]
    assert rules["D02"]["evidence"]["grade"] == "assumed"
    assert "+4.2 INR per USD per year" in rules["D04"]["statement"]


def test_an_observed_change_is_interpreted_through_the_stored_scenario(
    with_history: TestClient,
) -> None:
    execute(with_history)

    dossier = get(with_history, f"/intelligence/entities/{AERISCA}")

    (interpretation,) = dossier["interpretations"]
    assert interpretation["observed"]["value"] == "9.3824228029"
    assert interpretation["applied"] == "9.3824" and interpretation["variable_id"] == "var_usd_inr"
    (insight,) = by_rule(dossier["insights"], "S06")
    assert insight["kind"] == "interpretation" and insight["evidence"]["conditional_on_simulation"]
    assert "model interpretation computed on request" in insight["statement"]
    assert_grounded(insight)
    # The observed change itself stays an observation, graded apart.
    (observed,) = by_rule(dossier["insights"], "D01")
    assert observed["evidence"]["grade"] == "observed"
    assert not observed["evidence"]["conditional_on_simulation"]

    # The interpretation is exactly what the Lab computes for that change alone.
    body = reference(
        shocks=[{"variable_id": "var_usd_inr", "change_type": "percent_change", "value": "9.3824"}],
        stress_cases=[],
    )
    preview = post(with_history, "/scenarios/preview", body, 200)
    expected = {line["id"]: line["change"] for line in preview["results"]["lines"]}
    assert {line["id"]: line["change"] for line in interpretation["lines"]} == expected


# --- Workspace, insights and thresholds ---------------------------------------------------------


def test_the_overview_says_what_the_data_cannot_support(intel: TestClient) -> None:
    overview = get(intel, "/intelligence/overview")

    assert overview["coverage"]["observations"] == 0 and overview["impacts"] == []
    (data,) = by_rule(overview["insights"], "C02")
    assert data["statement"].startswith("No series or instrument has two or more stored values")
    shared = by_rule(overview["insights"], "X01")
    assert {item["subject"]["id"] for item in shared} >= {"variable:var_brent_crude"}
    for insight in overview["insights"]:
        assert_grounded(insight)
    cells = {(c["company"], c["variable"]): c for c in overview["exposure"]["cells"]}
    assert cells[(AERISCA, "variable:var_jet_fuel")]["directness"] == ["upstream", "via_industry"]


def test_the_overview_leads_with_new_observations_and_simulations(with_history: TestClient) -> None:
    execute(with_history)

    overview = get(with_history, "/intelligence/overview")

    kinds = [item["kind"] for item in overview["insights"]]
    assert kinds.index("change") < kinds.index("impact") < kinds.index("cross_entity")
    (impact,) = overview["impacts"]
    assert impact["line"] == "profit_before_tax" and impact["change"] == "-6700000"
    fx = next(s for s in overview["series"] if s["subject"]["id"] == FX_SERIES)
    assert fx["latest_detected"] and fx["trend"] == "rising" and fx["revisions"] == 1


def test_a_finding_reads_the_same_in_the_workspace_and_the_dossier(
    with_history: TestClient,
) -> None:
    execute(with_history)

    workspace = {
        item["id"]: item for item in get(with_history, "/intelligence/overview")["insights"]
    }
    dossier = {
        item["id"]: item
        for item in get(with_history, f"/intelligence/entities/{AERISCA}")["insights"]
    }

    shared = workspace.keys() & dossier.keys()
    assert {workspace[key]["rule"] for key in shared} >= {"D01", "D04", "D06", "S01"}
    for key in shared:
        assert workspace[key] == dossier[key], workspace[key]["rule"]
    (impact,) = (dossier[key] for key in shared if dossier[key]["rule"] == "S01")
    assert impact["evidence"]["grade"] == "assumed"  # the models apply through assumed edges
    assert {step["basis"] for step in impact["chain"]} >= {"relationship", "simulation"}


def test_insights_can_be_filtered(intel: TestClient) -> None:
    execute(intel)

    per_unit = get(intel, "/intelligence/insights", entity=AERISCA, rule="S03")
    strong = get(intel, "/intelligence/insights", entity=AERISCA, grade="simulated")
    kinds = get(intel, "/intelligence/insights", kind="cross_entity")

    assert per_unit["total"] == 3 and per_unit["scope"] == "entity"
    assert {item["evidence"]["grade"] for item in strong["items"]} <= {
        "observed",
        "documented",
        "curated",
        "simulated",
    }
    assert strong["total"] > 0 and kinds["total"] == len(kinds["items"]) > 0
    assert {item["kind"] for item in kinds["items"]} == {"cross_entity"}
    get(intel, "/intelligence/insights", 422, kind="prediction")
    get(intel, "/intelligence/insights", 422, grade="certain")


def test_thresholds_are_validated_with_their_fields(intel: TestClient) -> None:
    low = get(intel, "/intelligence/overview", 422, relative_change_percent="0")
    level = get(intel, "/intelligence/changes", 422, trend_significance="0.2")
    words = get(intel, "/intelligence/overview", 422, window="five")

    assert details(low) == [("query", "relative_change_percent", "invalid_threshold")]
    assert "between 0.1 and 100" in low["error"]["details"][0]["message"]
    assert details(level) == [("query", "trend_significance", "invalid_threshold")]
    assert details(words)[0][:2] == ("query", "window")
    used = get(intel, "/intelligence/overview", dependency_share_percent="75")["thresholds"]
    assert used["dependency_share_percent"] == "75"


def test_entities_are_listed_with_their_latest_impact(intel: TestClient) -> None:
    execute(intel)

    listed = get(intel, "/intelligence/entities")
    industries = get(intel, "/intelligence/entities", kind="industry")

    aerisca = next(item for item in listed["items"] if item["entity"]["key"] == AERISCA)
    assert aerisca["paths"] == 4 and aerisca["variables"] == 4
    assert aerisca["latest_impact"]["change"] == "-6700000"
    assert aerisca["weakest_evidence"] == "model_assumption"
    assert {item["entity"]["node_type"] for item in industries["items"]} == {"industry"}
    assert listed["total"] == len(listed["items"]) > industries["total"]


def test_each_company_keeps_its_own_latest_execution(
    intel: TestClient, session_factory: sessionmaker[Session]
) -> None:
    execute(intel)
    latest = execute(intel)

    with session_factory() as session:
        found = latest_executions(session, [AERISCA, "company:co_anvaya_bank"])
        everyone = latest_executions(session)
        assert {key: str(row.id) for key, row in found.items()} == {AERISCA: latest["id"]}
        assert {key: str(row.id) for key, row in everyone.items()} == {AERISCA: latest["id"]}
        assert latest_executions(session, ["company:co_anvaya_bank"]) == {}
        assert latest_executions(session, []) == {}
    impact = get(intel, "/intelligence/overview")["impacts"][0]
    assert impact["execution"]["id"] == latest["id"]


def test_the_brief_carries_evidence_and_rules_not_prose(intel: TestClient) -> None:
    execute(intel)

    brief = get(intel, f"/intelligence/entities/{AERISCA}/brief")
    dossier = get(intel, f"/intelligence/entities/{AERISCA}")

    assert brief["format"] == "rumin.intelligence.brief/1"
    assert [item["insight_id"] for item in brief["evidence"]] == [
        item["id"] for item in dossier["insights"]
    ]
    assert all(item["chain"] for item in brief["evidence"])
    assert brief["simulation_results"]["evidence_grade"] == "simulated"
    assert brief["drivers"]["headline"] == "profit_before_tax"
    assert any("never compute" in rule for rule in brief["narration_rules"])
    assert {edge["key"] for edge in brief["relationships"]} >= {
        e["key"] for p in dossier["exposure"]["paths"] for e in p["edges"]
    }
    assert brief["figures_entered"] and brief["assumptions"] and brief["limitations"]


def test_methods_document_every_rule_signal_and_threshold(intel: TestClient) -> None:
    methods = get(intel, "/intelligence/methods")

    assert [m["id"] for m in methods["modules"]] == [
        "change_detection",
        "series_signals",
        "exposure",
        "drivers",
        "interpretation",
        "insights",
    ]
    assert {s["id"] for s in methods["signals"]} == {
        "exposure_breadth",
        "dependency",
        "scenario_sensitivity",
        "trend",
        "volatility",
        "anomaly",
    }
    assert all(s["definition"] and s["method"] and s["limitations"] for s in methods["signals"])
    assert len({r["id"] for r in methods["rules"]}) == len(methods["rules"]) == 19
    assert methods["defaults"]["relative_change_percent"] == "5"
    assert next(g["id"] for g in methods["grades"]) == "observed"


# --- Stored analyses ----------------------------------------------------------------------------


def test_a_stored_analysis_keeps_what_it_read_and_knows_when_it_is_stale(
    intel: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = intel.post(
        f"{API}/intelligence/analyses",
        json={"scope": "entity", "entity": AERISCA, "label": "Before the scenario"},
    )

    assert response.status_code == 201, response.text
    stored = response.json()
    assert response.headers["Location"] == f"/api/v1/intelligence/analyses/{stored['id']}"
    assert stored["freshness"]["status"] == "current" and stored["label"] == "Before the scenario"
    assert stored["entity"]["entity"]["key"] == AERISCA and stored["workspace"] is None
    with session_factory() as session:
        row = session.get(IntelligenceAnalysis, uuid.UUID(stored["id"]))
        assert row is not None
        assert row.result_hash == sha256(row.result) and row.inputs_hash == sha256(row.inputs)

    execute(intel)
    later = get(intel, f"/intelligence/analyses/{stored['id']}")

    assert later["freshness"]["status"] == "stale" and later["freshness"]["changed"] == [
        "executions"
    ]
    assert later["result_hash"] == stored["result_hash"]  # the snapshot itself never changes
    assert later["entity"]["drivers"] is None


def test_stored_analyses_are_listed_and_never_rewritten(intel: TestClient) -> None:
    first = post(intel, "/intelligence/analyses", {"scope": "workspace"}, 201)
    second = post(
        intel,
        "/intelligence/analyses",
        {"scope": "workspace", "thresholds": {"relative_change_percent": "3"}},
        201,
    )
    third = post(intel, "/intelligence/analyses", {"scope": "entity", "entity": AERISCA}, 201)

    listed = get(intel, "/intelligence/analyses")
    assert [item["id"] for item in listed["items"]] == [third["id"], second["id"], first["id"]]
    assert get(intel, "/intelligence/analyses", scope="workspace")["total"] == 2
    assert get(intel, "/intelligence/analyses", entity=AERISCA)["total"] == 1
    assert second["thresholds"]["relative_change_percent"] == "3"
    assert first["subject_key"] is None and first["workspace"]["coverage"]["companies"] == 12
    get(intel, f"/intelligence/analyses/{uuid.uuid4()}", 404)

    paths = build_openapi()["paths"]
    for path, methods in paths.items():
        if path.startswith("/api/v1/intelligence"):
            allowed = {"get", "post"} if path == "/api/v1/intelligence/analyses" else {"get"}
            assert set(methods) <= allowed | {"parameters"}, path
    assert intel.delete(f"{API}/intelligence/analyses/{first['id']}").status_code == 405


def test_invalid_analysis_requests_store_nothing(
    intel: TestClient, session_factory: sessionmaker[Session]
) -> None:
    bad = post(
        intel,
        "/intelligence/analyses",
        {"scope": "workspace", "thresholds": {"relative_change_percent": "-3", "bogus": 1}},
        422,
    )
    missing = post(intel, "/intelligence/analyses", {"scope": "entity"}, 422)
    extra = post(intel, "/intelligence/analyses", {"scope": "workspace", "entity": AERISCA}, 422)
    unknown = post(
        intel, "/intelligence/analyses", {"scope": "entity", "entity": "company:co_missing"}, 404
    )

    assert details(bad) == [
        ("body", "thresholds.relative_change_percent", "invalid_threshold"),
        ("body", "thresholds.bogus", "invalid_threshold"),
    ]
    assert "needs `entity`" in missing["error"]["details"][0]["message"]
    assert "takes no `entity`" in extra["error"]["details"][0]["message"]
    assert unknown["error"]["code"] == "not_found"
    with session_factory() as session:
        assert session.scalars(select(IntelligenceAnalysis)).first() is None


# --- Without a graph -----------------------------------------------------------------------------


def test_without_a_graph_nothing_is_invented(graph_session: Session, client: TestClient) -> None:
    overview = get(client, "/intelligence/overview")

    assert overview["build"]["freshness"] == "not_built"
    assert overview["coverage"]["companies"] == 0
    assert [item["rule"] for item in overview["insights"]] == ["C02"]
    assert get(client, "/intelligence/entities")["total"] == 0
    get(client, f"/intelligence/entities/{AERISCA}", 404)


def test_the_system_reports_financial_intelligence(client: TestClient) -> None:
    capabilities = {c["id"]: c for c in get(client, "/system")["capabilities"]}

    assert capabilities["financial_intelligence"]["available"] is True
    assert capabilities["financial_intelligence"]["planned_phase"] == 6
    assert capabilities["ai_analyst"]["available"] is False
