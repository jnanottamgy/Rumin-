"""The committed OpenAPI document is the API contract shared with the frontend."""

from __future__ import annotations

import json

from app.openapi_export import SNAPSHOT_PATH, build_openapi


def test_committed_openapi_snapshot_matches_the_code() -> None:
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert committed == build_openapi(), (
        "The API contract changed. Regenerate it with `python -m app.openapi_export` "
        "and then `npm run generate:api` in frontend/."
    )


def test_errors_are_documented_with_the_shared_envelope() -> None:
    document = build_openapi()
    create = document["paths"]["/api/v1/scenarios"]["post"]["responses"]

    assert create["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert "HTTPValidationError" not in document["components"]["schemas"]


def test_scenario_drafts_still_have_no_run_endpoint() -> None:
    paths = build_openapi()["paths"]

    assert not any(path.startswith("/api/v1/scenarios") and "run" in path for path in paths)


def test_simulation_runs_are_append_only() -> None:
    paths = build_openapi()["paths"]
    simulation = {path: set(methods) for path, methods in paths.items() if "/simulation" in path}

    assert "post" in simulation["/api/v1/simulations"]
    assert "post" in simulation["/api/v1/simulations/validate"]
    assert "post" in simulation["/api/v1/simulations/{run_id}/sensitivity"]
    for methods in simulation.values():
        assert not methods & {"put", "patch", "delete"}


def test_schema_names_are_unique_across_modules() -> None:
    """Two schemas with one name get module-qualified names, renaming existing contract
    types for every client: give each schema a unique name instead."""
    names = build_openapi()["components"]["schemas"]

    assert not [name for name in names if name.startswith("app__")]
