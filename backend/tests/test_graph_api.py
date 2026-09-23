"""The knowledge-graph API: search, nodes, neighbourhoods, edges, paths, builds, limits."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.graph.build import run_build
from app.ingestion.catalog import DEFAULT_CATALOG_PATH, read_catalog, sync_catalog
from app.ingestion.registry import PROFILES
from app.models import Company
from app.services import graph as graph_service
from tests.test_price_import import CSV, do_import, manifest, write

API = "/api/v1/graph"
AERISCA = "company:co_aerisca_airways"


@pytest.fixture
def built(graph_session: Session) -> Iterator[Session]:
    """The reference network plus the World Bank catalogue, built into a graph."""
    sync_catalog(graph_session, read_catalog(DEFAULT_CATALOG_PATH, PROFILES), PROFILES)
    graph_session.commit()
    run_build(graph_session)
    yield graph_session


def get(client: TestClient, path: str, expect: int = 200, **params: Any) -> Any:
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == expect, response.text
    return response.json()


def find_paths(
    client: TestClient, source: str, target: str, expect: int = 200, **params: Any
) -> Any:
    response = client.get(f"{API}/paths", params={"from": source, "to": target, **params})
    assert response.status_code == expect, response.text
    return response.json()


# --- Overview and vocabulary ---------------------------------------------------------------------


def test_overview_before_any_build(graph_session: Session, client: TestClient) -> None:
    body = get(client, "/overview")
    assert body["build"] is None and body["type_map"] == []
    assert body["freshness"]["status"] == "not_built"
    assert "make graph" in body["freshness"]["message"]
    get(client, f"/nodes/{AERISCA}", expect=404)


def test_overview_matches_the_graph(built: Session, client: TestClient) -> None:
    body = get(client, "/overview")
    assert body["freshness"]["status"] == "current"
    counts = {item["type"]: item["count"] for item in body["type_map"]}
    assert counts == {
        "country": 3,
        "currency": 3,
        "sector": 6,
        "industry": 8,
        "company": 12,
        "economic_variable": 7,
        "data_series": 11,
    }
    assert sum(link["count"] for link in body["type_links"]) == body["build"]["edge_count"] == 97
    assert body["metrics"]["components"]["count"] == 1
    assert {item["id"] for item in body["metric_definitions"]} >= {"density", "components"}
    assert any("not a map of the complete economy" in note for note in body["notes"])


def test_overview_notices_changed_sources(built: Session, client: TestClient) -> None:
    company = built.get_one(Company, "co_kovalent_digital")
    original = company.name
    try:
        company.name = "Kovalent Digital (renamed)"
        built.commit()
        assert get(client, "/overview")["freshness"]["status"] == "stale"
    finally:
        company.name = original
        built.commit()


def test_freshness_is_cached_briefly(
    built: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert get(client, "/overview")["freshness"]["status"] == "current"
    company = built.get_one(Company, "co_kovalent_digital")
    original = company.name
    try:
        company.name = "Kovalent Digital (renamed)"
        built.commit()
        # Within the cache window the earlier answer stands...
        assert get(client, "/overview")["freshness"]["status"] == "current"
        # ...and it is checked again once the window has passed.
        monkeypatch.setattr(graph_service, "FRESHNESS_TTL_SECONDS", 0.0)
        assert get(client, "/overview")["freshness"]["status"] == "stale"
    finally:
        company.name = original
        built.commit()


def test_types_describe_the_vocabulary(client: TestClient) -> None:
    body = get(client, "/types")
    assert len(body["node_types"]) == 9 and len(body["edge_types"]) == 18
    statuses = {item["status"] for item in body["evidence_statuses"]}
    assert statuses == {"evidence_backed", "analyst_created", "model_assumption", "unverified"}
    assert all(item["caveat"] for item in body["edge_types"])
    assert len(body["construction_rules"]) == 21 and len(body["validation_rules"]) == 26


# --- Search ------------------------------------------------------------------------------------


def test_search_is_partial_and_case_insensitive(built: Session, client: TestClient) -> None:
    items = get(client, "/nodes", q="AERIS")["items"]
    assert [item["id"] for item in items] == [AERISCA]
    assert items[0]["match"] == "name" and items[0]["nature"] == "fictional"


def test_an_exact_identifier_comes_first(built: Session, client: TestClient) -> None:
    items = get(client, "/nodes", q="ind")["items"]
    assert items[0]["id"] == "country:cty_in" and items[0]["match"] == "identifier"
    items = get(client, "/nodes", q="51")["items"]
    assert items[0]["id"] == "industry:ind_air_transport"
    assert items[0]["primary_identifier"]["value"] == "51"


def test_search_filters(built: Session, client: TestClient) -> None:
    airlines = get(client, "/nodes", type="company", related_to="industry:ind_air_transport")[
        "items"
    ]
    assert sorted(item["name"] for item in airlines) == ["Aerisca Airways", "Skyvara Air"]
    fictional = get(client, "/nodes", nature="fictional", limit=100)
    assert fictional["total"] == 12 and {item["type"] for item in fictional["items"]} == {"company"}
    both = get(client, "/nodes", type=["country", "currency"], limit=100)
    assert both["total"] == 6
    assert get(client, "/nodes", q="no such thing")["items"] == []


def test_ambiguous_names_are_marked(built: Session, client: TestClient, tmp_path: Path) -> None:
    spec = manifest(instrument__name="Aerisca Airways")
    do_import(built, write(tmp_path, CSV), spec)
    run_build(built)
    items = get(client, "/nodes", q="Aerisca Airways")["items"]
    assert {item["type"] for item in items} == {"company", "instrument"}
    assert all(item["ambiguous"] for item in items)
    instrument = get(client, "/nodes/instrument:xnse-testco")
    assert instrument["data_status"] == "values_stored" and instrument["data"]["value_count"] == 2
    assert any(issue["rule"] == "possible_issuer" for issue in instrument["issues"])


# --- Nodes -------------------------------------------------------------------------------------


def test_node_detail(built: Session, client: TestClient) -> None:
    body = get(client, f"/nodes/{AERISCA}")
    assert body["subtitle"] == "Fictional company · Air transport · India"
    assert body["sources"][0]["table"] == "companies"
    kinds = {(item["kind"], item["variable"]["id"]) for item in body["exposures"]}
    assert kinds == {
        ("direct", "variable:var_usd_inr"),
        ("via_industry", "variable:var_jet_fuel"),
    }
    via = next(item for item in body["exposures"] if item["kind"] == "via_industry")
    assert via["via"]["id"] == "industry:ind_air_transport"
    assert "not for Aerisca Airways" in via["explanation"]
    assert sum(item["count"] for item in body["relationships"]) == body["degree"]


def test_country_detail_shows_how_it_was_resolved(built: Session, client: TestClient) -> None:
    body = get(client, "/nodes/country:cty_in")
    identifiers = {(item["scheme"], item["value"]) for item in body["identifiers"]}
    assert identifiers == {("iso3166_alpha2", "IN"), ("iso3166_alpha3", "IND")}
    assert body["resolution"] and all(
        item["outcome"] == "identifier_attached" for item in body["resolution"]
    )
    assert body["exposures"] is None


def test_series_node_reports_live_data_availability(built: Session, client: TestClient) -> None:
    body = get(client, "/nodes/series:wb-ind-fp-cpi-totl-zg")
    assert body["data_status"] == "definition_only"  # nothing retrieved in tests
    assert body["data"]["value_count"] == 0 and body["data"]["kind"] == "series"


def test_unknown_and_invalid_node_keys(built: Session, client: TestClient) -> None:
    get(client, "/nodes/company:nope", expect=404)
    get(client, "/nodes/DROP TABLE", expect=422)
    get(client, "/nodes/weird:thing", expect=422)


# --- Neighbourhoods ----------------------------------------------------------------------------


def test_neighborhood_by_depth(built: Session, client: TestClient) -> None:
    one = get(client, f"/nodes/{AERISCA}/neighborhood")
    two = get(client, f"/nodes/{AERISCA}/neighborhood", depth=2)
    assert one["center"]["id"] == AERISCA
    assert len(two["nodes"]) > len(one["nodes"]) > 1
    assert one["queries"] == 2 and two["queries"] == 3  # one per level, plus one
    for body in (one, two):
        ids = {node["id"] for node in body["nodes"]}
        assert all(edge["source"] in ids and edge["target"] in ids for edge in body["edges"])
        assert max(node["depth"] for node in body["nodes"]) == body["depth"]


def test_neighborhood_limit_is_reported(built: Session, client: TestClient) -> None:
    body = get(client, "/nodes/country:cty_in/neighborhood", max_nodes=3)
    assert len(body["nodes"]) == 3
    assert body["truncated"] and body["unexplored_count"] > 0
    assert sum(body["unexplored_by_type"].values()) == body["unexplored_count"]


def test_neighborhood_filters(built: Session, client: TestClient) -> None:
    structural = get(client, f"/nodes/{AERISCA}/neighborhood", edge_type=["in_industry"])
    assert {edge["type"] for edge in structural["edges"]} == {"in_industry"}
    real_only = get(client, "/nodes/country:cty_in/neighborhood", include_illustrative=False)
    assert real_only["edges"] and not any(edge["is_illustrative"] for edge in real_only["edges"])
    assert not any(node["type"] == "company" for node in real_only["nodes"])
    backed = get(client, "/nodes/country:cty_in/neighborhood", evidence_status=["evidence_backed"])
    assert {edge["evidence_status"] for edge in backed["edges"]} == {"evidence_backed"}
    only_series = get(client, "/nodes/country:cty_in/neighborhood", node_type=["data_series"])
    assert {node["type"] for node in only_series["nodes"]} == {"country", "data_series"}
    # Direction decides which nodes are reached; every edge among them is then shown.
    brent = "variable:var_brent_crude"
    outgoing = get(client, f"/nodes/{brent}/neighborhood", direction="out")
    reached = {node["id"] for node in outgoing["nodes"] if node["depth"] == 1}
    assert reached == {edge["target"] for edge in outgoing["edges"] if edge["source"] == brent}
    incoming = get(client, f"/nodes/{brent}/neighborhood", direction="in")
    assert [node["id"] for node in incoming["nodes"]] == [brent]  # nothing points at Brent


# --- Edges -------------------------------------------------------------------------------------


def test_edges_list_filters(built: Session, client: TestClient) -> None:
    assert get(client, "/edges", type="covers")["total"] == 11
    assert get(client, "/edges", evidence_status="model_assumption")["total"] == 41
    assert get(client, "/edges", illustrative=False, limit=500)["total"] == 97 - 65
    touching = get(client, "/edges", node=AERISCA)["items"]
    assert touching and all(AERISCA in (edge["source"], edge["target"]) for edge in touching)


def test_an_edge_explains_why_it_exists(built: Session, client: TestClient) -> None:
    (edge,) = get(client, "/edges", type="in_sector", node="industry:ind_air_transport")["items"]
    body = get(client, f"/edges/{edge['id']}")
    assert body["evidence_status"] == "evidence_backed" and not body["is_illustrative"]
    (evidence,) = body["evidence"]
    assert evidence["rule"] == "R05 industry_sector" and evidence["derivation"] == "derived"
    assert "ISIC" in evidence["citation"] and evidence["rule_description"]
    assert body["explanation"].startswith(
        "Air transport — belongs to → Transportation and storage."
    )
    assert body["caveat"] and body["evidence_status_definition"]

    (assumed,) = get(client, "/edges", type="influences", node="variable:var_brent_crude", limit=1)[
        "items"
    ]
    detail = get(client, f"/edges/{assumed['id']}")
    assert detail["is_illustrative"] and detail["qualifiers"]["strength"]
    assert "Illustrative" in detail["explanation"]
    assert "not evidence of causation" in detail["caveat"]


def test_unknown_and_invalid_edges(built: Session, client: TestClient) -> None:
    get(client, "/edges/e-0000000000000000", expect=404)
    get(client, "/edges/not-an-edge", expect=422)


# --- Paths and components ----------------------------------------------------------------------


def test_paths(built: Session, client: TestClient) -> None:
    body = find_paths(client, AERISCA, "country:cty_us")
    assert body["found"] and body["length"] >= 2
    assert "not an influence" in body["note"]
    edges = {edge["id"]: edge for edge in body["edges"]}
    for path in body["paths"]:
        assert path["length"] == body["length"] == len(path["edges"])
        assert path["nodes"][0] == AERISCA and path["nodes"][-1] == "country:cty_us"
        for (a, b), key in zip(pairwise(path["nodes"]), path["edges"], strict=True):
            assert {edges[key]["source"], edges[key]["target"]} == {a, b}


def test_path_bounds_and_direction(built: Session, client: TestClient) -> None:
    near = find_paths(client, AERISCA, "country:cty_us", max_depth=1)
    assert not near["found"] and near["paths"] == []
    against = find_paths(client, AERISCA, "variable:var_brent_crude", direction="out")
    assert not against["found"]  # assumed effects point from variables to companies
    along = find_paths(client, "variable:var_brent_crude", AERISCA, direction="out", max_depth=6)
    assert along["found"]
    same = find_paths(client, AERISCA, AERISCA)
    assert same["length"] == 0
    find_paths(client, AERISCA, "country:cty_zz", expect=404)


def test_components(built: Session, client: TestClient) -> None:
    body = get(client, "/components")
    assert body["count"] == 1 and body["components"][0]["size"] == 50
    assert "not mean" in body["note"]


# --- Builds, issues, limits, read-only ---------------------------------------------------------


def test_builds_and_issues(built: Session, client: TestClient) -> None:
    page = get(client, "/builds")
    assert page["total"] == 1
    build = get(client, f"/builds/{page['items'][0]['id']}")
    assert build["status"] == "completed" and build["nodes"]["processed"] == 50
    assert {item["outcome"] for item in build["decisions"]} == {"linked", "identifier_attached"}
    assert get(client, "/issues")["total"] == 0
    get(client, "/builds/999999", expect=404)


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (f"/nodes/{AERISCA}/neighborhood", {"depth": 4}),
        (f"/nodes/{AERISCA}/neighborhood", {"max_nodes": 201}),
        (f"/nodes/{AERISCA}/neighborhood", {"direction": "sideways"}),
        (f"/nodes/{AERISCA}/neighborhood", {"edge_type": "owns"}),
        ("/paths", {"from": AERISCA, "to": "country:cty_us", "max_depth": 7}),
        ("/paths", {"from": AERISCA, "to": "country:cty_us", "limit": 11}),
        ("/paths", {"from": AERISCA}),
        ("/nodes", {"q": "x" * 101}),
        ("/nodes", {"type": ["company"] * 10}),
        ("/nodes", {"related_to": "Robert'); DROP TABLE graph_nodes;--"}),
        ("/issues", {"rule": "*"}),
    ],
)
def test_limits_and_validation(
    built: Session, client: TestClient, path: str, params: dict[str, Any]
) -> None:
    body = get(client, path, expect=422, **params)
    assert body["error"]["code"] == "validation_error"


def test_the_graph_api_is_read_only(client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        response = client.request(method, f"{API}/nodes")
        assert response.status_code == 405


def test_system_reports_the_graph_capabilities(client: TestClient) -> None:
    capabilities = {
        item["id"]: item for item in client.get("/api/v1/system").json()["capabilities"]
    }
    assert capabilities["knowledge_graph"]["available"] is True
    assert capabilities["graph_analytics"]["available"] is True
