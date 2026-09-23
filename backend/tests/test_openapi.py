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


def test_there_is_no_simulation_endpoint_yet() -> None:
    paths = build_openapi()["paths"]

    assert not any("run" in path or "simulat" in path for path in paths)
