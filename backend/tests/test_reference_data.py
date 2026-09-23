from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

EXPECTED_COUNTS = {"company": 12, "industry": 8, "country": 3, "economic_variable": 7}


def test_lists_every_entity_ordered_by_name(client: TestClient) -> None:
    body = client.get("/api/v1/entities").json()

    assert body["total"] == sum(EXPECTED_COUNTS.values())
    names = [item["name"] for item in body["items"]]
    assert names == sorted(names)
    assert body["limit"] == 100 and body["offset"] == 0


@pytest.mark.parametrize(("kind", "count"), EXPECTED_COUNTS.items())
def test_filters_entities_by_kind(client: TestClient, kind: str, count: int) -> None:
    body = client.get("/api/v1/entities", params={"kind": kind}).json()

    assert body["total"] == count
    assert {item["kind"] for item in body["items"]} == {kind}


def test_paginates_entities(client: TestClient) -> None:
    everything = client.get("/api/v1/entities").json()["items"]
    page = client.get("/api/v1/entities", params={"limit": 5, "offset": 5}).json()

    assert [item["id"] for item in page["items"]] == [item["id"] for item in everything[5:10]]
    assert page["total"] == len(everything)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_rejects_out_of_range_pagination(client: TestClient, params: dict[str, int]) -> None:
    response = client.get("/api/v1/entities", params=params)

    assert response.status_code == 422
    detail = response.json()["error"]["details"][0]
    assert detail["location"] == "query"
    assert detail["field"] == next(iter(params))


def test_rejects_unknown_entity_kind(client: TestClient) -> None:
    response = client.get("/api/v1/entities", params={"kind": "planet"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_gets_a_company_with_its_classification(client: TestClient) -> None:
    body = client.get("/api/v1/entities/co_aerisca_airways").json()

    assert body["kind"] == "company"
    assert body["industry_id"] == "ind_air_transport"
    assert body["country_id"] == "cty_in"
    assert body["is_fictional"] is True
    assert body["dataset_id"] == "rumin-sample"


def test_unknown_entity_returns_not_found_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/entities/co_does_not_exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert "co_does_not_exist" in error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_malformed_entity_id_is_rejected_before_querying(client: TestClient) -> None:
    response = client.get("/api/v1/entities/DROP TABLE entities")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "path"


def test_industries_carry_isic_classification(client: TestClient) -> None:
    items = client.get("/api/v1/industries").json()["items"]

    assert len(items) == EXPECTED_COUNTS["industry"]
    for industry in items:
        assert industry["classification_system"] == "ISIC Rev. 4"
        assert industry["classification_code"].isdigit()
        assert industry["reference"]


def test_variables_expose_their_scenario_rules(client: TestClient) -> None:
    items = {v["id"]: v for v in client.get("/api/v1/variables").json()["items"]}

    assert len(items) == EXPECTED_COUNTS["economic_variable"]
    brent = items["var_brent_crude"]
    assert brent["unit"] == "USD per barrel"
    assert {rule["change_type"] for rule in brent["scenario_rules"]} == {
        "percent_change",
        "absolute_change",
    }
    # Rates only accept changes in percentage points.
    repo = items["var_rbi_repo_rate"]
    assert [rule["change_type"] for rule in repo["scenario_rules"]] == ["absolute_change"]
    assert repo["scenario_rules"][0]["unit_label"] == "percentage points"


def test_lists_relationships_as_labelled_assumptions(client: TestClient) -> None:
    body = client.get("/api/v1/relationships", params={"limit": 500}).json()

    assert body["total"] == 41
    for rel in body["items"]:
        assert rel["category"] == "economic"
        assert rel["evidence_level"] == "illustrative"
        assert rel["epistemic_category"] == "assumption"
        assert rel["rationale"]


def test_filters_relationships_by_type_and_entity(client: TestClient) -> None:
    by_type = client.get("/api/v1/relationships", params={"type": "lends_to"}).json()
    by_entity = client.get("/api/v1/relationships", params={"entity_id": "var_usd_inr"}).json()

    assert by_type["total"] == 6
    assert {rel["type"] for rel in by_type["items"]} == {"lends_to"}
    assert by_entity["total"] > 0
    for rel in by_entity["items"]:
        assert "var_usd_inr" in (rel["source_id"], rel["target_id"])


def test_relationship_type_registry_covers_economic_and_structural_types(
    client: TestClient,
) -> None:
    types = {t["type"]: t for t in client.get("/api/v1/relationship-types").json()}

    assert len(types) == 10
    assert types["competes_with"]["directed"] is False
    assert types["affects_costs"]["has_polarity"] is True
    assert types["in_industry"]["category"] == "structural"
    assert {"source_kind": "economic_variable", "target_kind": "company"} in types["affects_costs"][
        "allowed_pairs"
    ]
