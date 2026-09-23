from __future__ import annotations

from collections import Counter
from typing import Any

from alembic import command
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import alembic_config, make_settings


def _network(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/v1/network")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_network_statistics_match_the_sample_dataset(client: TestClient) -> None:
    network = _network(client)

    assert network["stats"] == {
        "node_count": 30,
        "edge_count": 71,
        "economic_edge_count": 41,
        "structural_edge_count": 30,
    }
    assert len(network["nodes"]) == 30
    assert len(network["edges"]) == 71


def test_every_edge_connects_existing_nodes(client: TestClient) -> None:
    network = _network(client)
    node_ids = {node["id"] for node in network["nodes"]}

    for edge in network["edges"]:
        assert edge["source_id"] in node_ids, edge["id"]
        assert edge["target_id"] in node_ids, edge["id"]
    assert len({edge["id"] for edge in network["edges"]}) == len(network["edges"])


def test_structural_links_mirror_entity_attributes(client: TestClient) -> None:
    network = _network(client)
    structural = [e for e in network["edges"] if e["category"] == "structural"]
    links = {(e["type"], e["source_id"]): e["target_id"] for e in structural}

    for node in network["nodes"]:
        entity = node["entity"]
        if entity["kind"] == "company":
            assert links[("in_industry", entity["id"])] == entity["industry_id"]
            assert links[("domiciled_in", entity["id"])] == entity["country_id"]
        elif entity["kind"] == "economic_variable" and entity["country_id"]:
            assert links[("measured_for", entity["id"])] == entity["country_id"]
    assert all(edge["derived_from"] for edge in structural)


def test_degree_counts_every_incident_edge(client: TestClient) -> None:
    network = _network(client)
    expected: Counter[str] = Counter()
    for edge in network["edges"]:
        expected[edge["source_id"]] += 1
        expected[edge["target_id"]] += 1

    for node in network["nodes"]:
        assert node["degree"] == expected[node["id"]], node["id"]


def test_network_labels_its_dataset_as_illustrative(client: TestClient) -> None:
    network = _network(client)

    assert network["dataset"]["is_illustrative"] is True
    assert "fictional" in network["dataset"]["provenance_note"]
    assert len(network["relationship_types"]) == 10


def test_undirected_edges_are_flagged(client: TestClient) -> None:
    network = _network(client)
    competes = [e for e in network["edges"] if e["type"] == "competes_with"]

    assert competes and all(edge["directed"] is False for edge in competes)


def test_network_is_empty_but_valid_without_a_dataset(fresh_sqlite_url: str) -> None:
    command.upgrade(alembic_config(fresh_sqlite_url), "head")

    with TestClient(create_app(make_settings(fresh_sqlite_url))) as client:
        network = _network(client)

    assert network["dataset"] is None
    assert network["nodes"] == [] and network["edges"] == []
    assert network["stats"]["node_count"] == 0
