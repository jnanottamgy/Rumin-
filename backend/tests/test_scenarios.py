from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

URL = "/api/v1/scenarios"


def oil_shock(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Oil price shock",
        "description": "Brent crude rises sharply.",
        "shocks": [
            {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": 30}
        ],
    }
    payload.update(overrides)
    return payload


def error_fields(response: Any) -> list[str | None]:
    return [detail["field"] for detail in response.json()["error"]["details"]]


# --- Happy paths -----------------------------------------------------------------------


def test_creates_a_draft_scenario_without_results(client: TestClient) -> None:
    response = client.post(URL, json=oil_shock())

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"{URL}/{body['id']}"
    assert body["name"] == "Oil price shock"
    assert body["status"] == "draft"
    assert body["latest_run"] is None  # nothing has been simulated
    assert body["shocks"] == [
        {
            "variable_id": "var_brent_crude",
            "change_type": "percent_change",
            "value": 30.0,
            "note": "",
            "epistemic_category": "scenario_input",
        }
    ]


def test_reads_back_and_lists_scenarios(client: TestClient) -> None:
    created = client.post(URL, json=oil_shock()).json()

    fetched = client.get(f"{URL}/{created['id']}")
    listing = client.get(URL).json()

    assert fetched.status_code == 200
    assert fetched.json() == created
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == created["id"]


def test_trims_whitespace_in_names(client: TestClient) -> None:
    body = client.post(URL, json=oil_shock(name="   Oil shock   ")).json()

    assert body["name"] == "Oil shock"


def test_replaces_a_scenario_including_its_inputs(client: TestClient) -> None:
    created = client.post(URL, json=oil_shock()).json()
    replacement = oil_shock(
        name="Oil and rupee shock",
        shocks=[
            # Same variable as before, with a new value: must not trip the unique constraint.
            {"variable_id": "var_brent_crude", "change_type": "absolute_change", "value": 12.5},
            {"variable_id": "var_usd_inr", "change_type": "percent_change", "value": 5},
        ],
    )

    response = client.put(f"{URL}/{created['id']}", json=replacement)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Oil and rupee shock"
    assert [(s["variable_id"], s["value"]) for s in body["shocks"]] == [
        ("var_brent_crude", 12.5),
        ("var_usd_inr", 5.0),
    ]
    assert body["updated_at"] > created["updated_at"]
    assert body["created_at"] == created["created_at"]


def test_deletes_a_scenario(client: TestClient) -> None:
    created = client.post(URL, json=oil_shock()).json()

    deleted = client.delete(f"{URL}/{created['id']}")
    fetched = client.get(f"{URL}/{created['id']}")

    assert deleted.status_code == 204
    assert fetched.status_code == 404
    assert fetched.json()["error"]["code"] == "not_found"


def test_rate_variables_accept_percentage_point_changes(client: TestClient) -> None:
    payload = oil_shock(
        shocks=[
            {"variable_id": "var_rbi_repo_rate", "change_type": "absolute_change", "value": 0.25}
        ]
    )

    response = client.post(URL, json=payload)

    assert response.status_code == 201


# --- Missing resources --------------------------------------------------------------------


def test_unknown_scenario_is_not_found(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert client.get(f"{URL}/{missing}").status_code == 404
    assert client.put(f"{URL}/{missing}", json=oil_shock()).status_code == 404
    assert client.delete(f"{URL}/{missing}").status_code == 404


def test_malformed_scenario_id_is_a_validation_error(client: TestClient) -> None:
    response = client.get(f"{URL}/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "path"


# --- Shape validation (Pydantic) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "    "}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"name": "Oil\x00shock"}, "name"),
        ({"description": "d" * 2001}, "description"),
        ({"shocks": []}, "shocks"),
        (
            {
                "shocks": [
                    {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": 1}
                ]
                * 11
            },
            "shocks",
        ),
        (
            {"shocks": [{"variable_id": "var_brent_crude", "change_type": "double", "value": 1}]},
            "shocks[0].change_type",
        ),
        (
            {
                "shocks": [
                    {
                        "variable_id": "var_brent_crude",
                        "change_type": "percent_change",
                        "value": "lots",
                    }
                ]
            },
            "shocks[0].value",
        ),
        (
            {"shocks": [{"variable_id": "Brent!", "change_type": "percent_change", "value": 1}]},
            "shocks[0].variable_id",
        ),
        ({"shocks": [{"change_type": "percent_change", "value": 1}]}, "shocks[0].variable_id"),
        ({"status": "completed"}, "status"),
    ],
)
def test_rejects_malformed_payloads(
    client: TestClient, overrides: dict[str, Any], field: str
) -> None:
    response = client.post(URL, json=oil_shock(**overrides))

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert field in error_fields(response)


def test_rejects_non_finite_numbers(client: TestClient) -> None:
    # json.dumps would refuse NaN, so the raw body is sent explicitly.
    body = (
        '{"name": "NaN", "shocks": [{"variable_id": "var_brent_crude", '
        '"change_type": "percent_change", "value": NaN}]}'
    )

    response = client.post(URL, content=body, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert "shocks[0].value" in error_fields(response)


def test_rejects_invalid_json(client: TestClient) -> None:
    response = client.post(URL, content="{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["message"] == "Request body is not valid JSON."


def test_requires_a_json_content_type(client: TestClient) -> None:
    # Without Content-Type, a browser can send the request cross-site without a CORS
    # preflight; FastAPI's strict content-type check refuses to parse it as JSON.
    response = client.post(URL, content='{"name": "x"}', headers={"Content-Type": ""})

    assert response.status_code == 422


# --- Domain validation (needs the database) --------------------------------------------------


def test_rejects_unknown_variables(client: TestClient) -> None:
    payload = oil_shock(
        shocks=[{"variable_id": "var_unobtainium", "change_type": "percent_change", "value": 5}]
    )

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    detail = response.json()["error"]["details"][0]
    assert detail == {
        "location": "body",
        "field": "shocks[0].variable_id",
        "message": "Unknown economic variable 'var_unobtainium'.",
        "type": "unknown_variable",
    }


def test_rejects_entities_that_are_not_variables(client: TestClient) -> None:
    payload = oil_shock(
        shocks=[{"variable_id": "co_aerisca_airways", "change_type": "percent_change", "value": 5}]
    )

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert error_fields(response) == ["shocks[0].variable_id"]


def test_rejects_duplicate_variables(client: TestClient) -> None:
    shock = {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": 5}

    response = client.post(URL, json=oil_shock(shocks=[shock, shock]))

    assert response.status_code == 422
    assert error_fields(response) == ["shocks[1].variable_id"]


def test_rejects_percentage_changes_to_rates(client: TestClient) -> None:
    payload = oil_shock(
        shocks=[{"variable_id": "var_rbi_repo_rate", "change_type": "percent_change", "value": 10}]
    )

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert error_fields(response) == ["shocks[0].change_type"]


@pytest.mark.parametrize(
    ("variable_id", "change_type", "value"),
    [
        ("var_brent_crude", "percent_change", -100),  # a price cannot fall by 100 %
        ("var_brent_crude", "percent_change", 1000.5),
        ("var_brent_crude", "percent_change", 0),
        ("var_brent_crude", "percent_change", 12.34567),  # more than 4 decimal places
        ("var_rbi_repo_rate", "absolute_change", 30),  # beyond ±25 percentage points
    ],
)
def test_rejects_values_outside_the_rules(
    client: TestClient, variable_id: str, change_type: str, value: float
) -> None:
    payload = oil_shock(
        shocks=[{"variable_id": variable_id, "change_type": change_type, "value": value}]
    )

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert error_fields(response) == ["shocks[0].value"]


def test_reports_every_invalid_input_at_once(client: TestClient) -> None:
    payload = oil_shock(
        shocks=[
            {"variable_id": "var_unobtainium", "change_type": "percent_change", "value": 5},
            {"variable_id": "var_rbi_repo_rate", "change_type": "percent_change", "value": 5},
        ]
    )

    response = client.post(URL, json=payload)

    assert error_fields(response) == ["shocks[0].variable_id", "shocks[1].change_type"]


def test_invalid_update_leaves_the_scenario_unchanged(client: TestClient) -> None:
    created = client.post(URL, json=oil_shock()).json()
    bad = oil_shock(
        name="Should not be saved",
        shocks=[{"variable_id": "var_unobtainium", "change_type": "percent_change", "value": 5}],
    )

    response = client.put(f"{URL}/{created['id']}", json=bad)

    assert response.status_code == 422
    assert client.get(f"{URL}/{created['id']}").json() == created


# --- Request size limit --------------------------------------------------------------------


def test_rejects_oversized_bodies_by_content_length(client: TestClient) -> None:
    response = client.post(
        URL,
        content=b"x" * (64 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_rejects_oversized_chunked_bodies(client: TestClient) -> None:
    def chunks() -> Any:
        for _ in range(80):
            yield b"x" * 1024

    # A generator body is sent with chunked transfer encoding (no Content-Length).
    response = client.post(URL, content=chunks(), headers={"Content-Type": "application/json"})

    assert response.status_code == 413
