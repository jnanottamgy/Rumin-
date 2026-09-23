"""The read-only data API: providers, datasets, series, prices, jobs and quality issues.

Data is created through the real pipeline from SYNTHETIC provider responses and a
SYNTHETIC price file (see ``tests/fakes.py`` and ``tests/test_price_import.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ingestion.catalog import sync_catalog
from app.ingestion.registry import PROFILES
from tests.fakes import response, wb_page, wb_record
from tests.test_ingestion_pipeline import SERIES, metadata, page, run, synthetic_catalog
from tests.test_price_import import CSV, do_import, manifest, write

API = "/api/v1"


def get(client: TestClient, path: str, expect: int = 200, **params: Any) -> Any:
    reply = client.get(f"{API}{path}", params=params)
    assert reply.status_code == expect, reply.text
    return reply.json()


@pytest.fixture
def ingested(ingestion_session: Session) -> Session:
    """One clean run of s-cpi (three values) and one run with a flagged and a rejected
    record for s-gdp."""
    run(
        ingestion_session,
        [page(("2022", "6.699801"), ("2021", "5.131407"), ("2020", "6.623437")), metadata()],
    )
    records = [
        wb_record("2022", "250", code="NY.GDP.MKTP.KD.ZG"),
        wb_record("2021", '"n/a"', code="NY.GDP.MKTP.KD.ZG"),
    ]
    run(
        ingestion_session,
        [response(wb_page(records)), metadata("NY.GDP.MKTP.KD.ZG")],
        series_ids=("s-gdp",),
    )
    return ingestion_session


# --- Providers and datasets -----------------------------------------------------------------


def test_providers_are_listed_with_their_terms(client: TestClient, ingested: Session) -> None:
    providers = {p["id"]: p for p in get(client, "/providers")}
    assert set(providers) == {"worldbank", "price-file"}
    worldbank = providers["worldbank"]
    assert worldbank["dataset_count"] == 1
    assert "CC BY 4.0" in worldbank["licensing"]
    assert worldbank["authentication"] == "none"
    assert get(client, "/providers/worldbank")["name"] == worldbank["name"]
    get(client, "/providers/no-such-provider", expect=404)
    get(client, "/providers/Bad Id", expect=422)


def test_datasets_distinguish_curated_sample_data_from_provider_data(
    client: TestClient, ingested: Session
) -> None:
    datasets = {d["id"]: d for d in get(client, "/datasets")["items"]}
    curated, provider = datasets["rumin-sample"], datasets["test-wdi"]
    assert (curated["kind"], curated["is_illustrative"]) == ("curated", True)
    assert (provider["kind"], provider["is_illustrative"]) == ("provider", False)
    assert provider["license"] == "CC BY 4.0"
    assert provider["attribution"] == "Synthetic attribution"
    assert provider["provider_last_updated"] == "2026-07-01"
    assert provider["series_count"] == len(SERIES)
    assert provider["last_job"]["status"] == "completed_with_warnings"  # the second run

    only_provider = get(client, "/datasets", kind="provider")["items"]
    assert [d["id"] for d in only_provider] == ["test-wdi"]
    assert get(client, "/datasets/test-wdi")["id"] == "test-wdi"
    error = get(client, "/datasets/no-such-dataset", expect=404)["error"]
    assert error["code"] == "not_found"


# --- Economic series ------------------------------------------------------------------------


def test_series_list_shows_coverage_and_the_latest_value(
    client: TestClient, ingested: Session
) -> None:
    page_ = get(client, "/economic-series", dataset_id="test-wdi")
    assert page_["total"] == len(SERIES)
    series = {s["id"]: s for s in page_["items"]}
    cpi = series["s-cpi"]
    assert cpi["latest"] == {
        "period_label": "2022",
        "period_start": "2022-01-01",
        "value": "6.699801",  # a decimal string, never a float
        "quality_status": "validated",
    }
    assert (cpi["first_period"], cpi["last_period"]) == ("2020-01-01", "2022-01-01")
    assert cpi["observation_count"] == 3
    assert cpi["unit"] == "% change on previous year"
    assert cpi["plausible_max"] == "200"
    assert cpi["epistemic_category"] == "observation"
    assert series["s-lend"]["latest"] is None
    assert series["s-lend"]["last_ingestion_status"] is None  # never retrieved


def test_series_can_be_filtered_searched_and_sorted(client: TestClient, ingested: Session) -> None:
    with_data = get(client, "/economic-series", has_data="true")["items"]
    assert sorted(s["id"] for s in with_data) == ["s-cpi", "s-gdp"]
    assert get(client, "/economic-series", has_data="false")["total"] == 2
    assert [s["id"] for s in get(client, "/economic-series", q="s-cp")["items"]] == ["s-cpi"]
    assert get(client, "/economic-series", q="100%")["total"] == 0  # wildcards are escaped
    assert get(client, "/economic-series", country_iso3="USA")["total"] == 0
    newest_first = get(client, "/economic-series", sort="-last_period")["items"]
    assert [s["id"] for s in newest_first][:2] == ["s-cpi", "s-gdp"]
    get(client, "/economic-series", expect=422, sort="value")
    get(client, "/economic-series", expect=422, country_iso3="india")


def test_series_detail_carries_licence_quality_and_the_last_job(
    client: TestClient, ingested: Session
) -> None:
    detail = get(client, "/economic-series/s-gdp")
    assert detail["dataset"]["license"] == "CC BY 4.0"
    assert detail["dataset"]["attribution"] == "Synthetic attribution"
    assert detail["provider_name"] == "World Bank — Indicators API (v2)"
    assert detail["flagged_count"] == 1  # 250 is outside the review range
    assert detail["revised_period_count"] == 0
    assert detail["last_job"]["status"] == "completed_with_warnings"
    get(client, "/economic-series/s-none", expect=404)
    get(client, "/economic-series/NOT VALID", expect=422)


def test_observations_come_with_period_units_and_provenance(
    client: TestClient, ingested: Session
) -> None:
    result = get(client, "/economic-series/s-cpi/observations")
    assert result["series"]["unit"] == "% change on previous year"
    assert result["dataset"]["attribution"] == "Synthetic attribution"
    first = result["items"][0]
    assert (first["period_label"], first["period_start"], first["period_end"]) == (
        "2020",
        "2020-01-01",
        "2020-12-31",
    )
    assert (first["value"], first["raw_value"]) == ("6.623437", "6.623437")
    assert first["is_current"] is True and first["revision"] == 1
    assert first["retrieved_at"] and first["capture_id"]

    capture = get(client, f"/source-captures/{first['capture_id']}")
    assert capture["kind"] == "http_response"
    assert len(capture["sha256"]) == 64 and capture["body_stored"] is True
    assert "body" not in capture and "body_gzip" not in capture

    window = get(
        client, "/economic-series/s-cpi/observations", start="2021-01-01", end="2021-12-31"
    )
    assert [o["period_label"] for o in window["items"]] == ["2021"]


def test_revisions_are_hidden_by_default_and_available_on_request(
    client: TestClient, ingestion_session: Session
) -> None:
    run(ingestion_session, [page(("2021", "5.1")), metadata()])
    run(ingestion_session, [page(("2021", "5.3")), metadata()])

    current = get(client, "/economic-series/s-cpi/observations")["items"]
    assert [(o["value"], o["revision"]) for o in current] == [("5.3", 2)]
    history = get(client, "/economic-series/s-cpi/observations", include_revisions="true")
    assert [(o["value"], o["is_current"]) for o in history["items"]] == [
        ("5.1", False),
        ("5.3", True),
    ]
    assert get(client, "/economic-series/s-cpi")["revised_period_count"] == 1


def test_missing_values_are_null_never_zero(client: TestClient, ingestion_session: Session) -> None:
    run(ingestion_session, [page(("2021", None), ("2020", "1.5")), metadata()])
    items = get(client, "/economic-series/s-cpi/observations")["items"]
    assert [(o["period_label"], o["value"], o["status"]) for o in items] == [
        ("2020", "1.5", "reported"),
        ("2021", None, "missing"),
    ]
    reported = get(client, "/economic-series/s-cpi/observations", include_missing="false")
    assert [o["period_label"] for o in reported["items"]] == ["2020"]


# --- Jobs and quality -----------------------------------------------------------------------


def test_jobs_are_listed_newest_first_with_details(client: TestClient, ingested: Session) -> None:
    jobs = get(client, "/ingestion-jobs")["items"]
    assert [job["status"] for job in jobs] == ["completed_with_warnings", "completed"]
    assert get(client, "/ingestion-jobs", status="completed")["total"] == 1

    detail = get(client, f"/ingestion-jobs/{jobs[0]['id']}")
    (item,) = detail["items"]
    assert (item["series_id"], item["records_rejected"], item["status"]) == (
        "s-gdp",
        1,
        "succeeded",
    )
    counts = {(c["rule"], c["outcome"]): c["count"] for c in detail["issue_counts"]}
    assert counts == {("outside_review_range", "flagged"): 1, ("invalid_number", "rejected"): 1}
    assert len(detail["captures"]) == 2  # the data page and the indicator metadata
    get(client, "/ingestion-jobs/not-a-uuid", expect=422)
    get(client, "/ingestion-jobs/00000000-0000-0000-0000-000000000000", expect=404)


def test_rejected_records_are_visible_with_what_the_source_sent(
    client: TestClient, ingested: Session
) -> None:
    rejected = get(client, "/data-quality/issues", outcome="rejected")["items"]
    (issue,) = rejected
    assert issue["rule"] == "invalid_number"
    assert issue["raw_record"]["value"] == "n/a"
    assert issue["review_status"] == "unreviewed"
    flagged = get(client, "/data-quality/issues", series_id="s-gdp", rule="outside_review_range")
    assert flagged["items"][0]["observation_id"] is not None
    get(client, "/data-quality/issues", expect=422, rule="DROP TABLE")


def test_quality_rules_are_published(client: TestClient) -> None:
    rules = {rule["code"]: rule for rule in get(client, "/data-quality/rules")}
    assert rules["outside_review_range"]["outcome"] == "flagged"
    assert rules["precision_exceeded"]["outcome"] == "rejected"
    assert rules["missing_values"]["outcome"] == "noted"


def test_ingestion_cannot_be_started_over_http(client: TestClient) -> None:
    assert client.post(f"{API}/ingestion-jobs", json={}).status_code == 405
    paths = client.get("/openapi.json").json()["paths"]
    for path, operations in paths.items():
        if any(part in path for part in ("ingestion", "data-quality", "economic-series")):
            assert set(operations) == {"get"}, path


# --- Prices ---------------------------------------------------------------------------------


def test_prices_are_served_per_dataset_and_never_blended(
    client: TestClient, ingestion_session: Session, tmp_path: Path
) -> None:
    do_import(ingestion_session, write(tmp_path, CSV))
    instrument = get(client, "/instruments/xnse-testco")
    assert [d["id"] for d in instrument["price_datasets"]] == ["test-prices"]
    assert instrument["price_datasets"][0]["is_illustrative"] is True
    assert get(client, "/instruments", exchange_mic="XNSE")["total"] == 1

    prices = get(client, "/instruments/xnse-testco/prices")
    assert prices["dataset"]["license"] == "Test licence (synthetic)"
    first = prices["items"][0]
    assert (first["trade_date"], first["open"], first["close"], first["volume"]) == (
        "2026-09-21",
        "100.1",
        "100.75",
        1500,
    )
    assert first["adjustment"] == "unadjusted" and first["currency"] == "INR"

    second_source = manifest(dataset__id="test-prices-b", dataset__name="Second source")
    do_import(ingestion_session, write(tmp_path, CSV, "b.csv"), second_source)
    error = get(client, "/instruments/xnse-testco/prices", expect=422)["error"]
    assert "never blended" in error["message"]
    chosen = get(client, "/instruments/xnse-testco/prices", dataset_id="test-prices-b")
    assert chosen["dataset"]["id"] == "test-prices-b"
    get(client, "/instruments/xnse-testco/prices", expect=404, dataset_id="test-wdi")
    get(client, "/instruments/xnse-none", expect=404)


# --- System status --------------------------------------------------------------------------


def test_system_status_counts_the_stored_data(client: TestClient, ingested: Session) -> None:
    status = get(client, "/system")
    assert status["data"] == {
        "provider_datasets": 1,
        "series_total": len(SERIES),
        "series_with_data": 2,
        "observations": 4,
        "instruments": 0,
        "price_bars": 0,
        "flagged_values": 1,
        "last_job": status["data"]["last_job"],
    }
    assert status["data"]["last_job"]["status"] == "completed_with_warnings"
    capabilities = {c["id"]: c for c in status["capabilities"]}
    assert capabilities["historical_observations"]["available"] is True
    assert capabilities["price_file_import"]["available"] is True
    assert capabilities["live_market_data"]["available"] is False
    assert capabilities["ingestion_from_web"]["available"] is False


def test_system_status_without_provider_data(
    client: TestClient, ingestion_session: Session
) -> None:
    sync_catalog(ingestion_session, synthetic_catalog(*SERIES), PROFILES)
    ingestion_session.commit()
    data = get(client, "/system")["data"]
    assert (data["series_total"], data["series_with_data"], data["last_job"]) == (4, 0, None)
