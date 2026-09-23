"""The ingestion command line: exit codes, refusals and what it prints. Provider responses
are SYNTHETIC and scripted; no test touches the network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import JobStatus, JobTargetKind
from app.ingestion import jobs
from app.ingestion.cli import main
from app.ingestion.http import HttpResponse
from app.ingestion.providers.base import EconomicSeriesSource
from app.ingestion.providers.worldbank import WorldBankProvider
from app.models import EconomicObservation, IngestionJob
from tests.conftest import make_settings
from tests.fakes import ScriptedTransport, make_client, response, wb_indicator, wb_page, wb_record
from tests.test_ingestion_pipeline import START, Clock, synthetic_catalog
from tests.test_price_import import CSV, MANIFEST

Factory = Callable[[str, Settings], EconomicSeriesSource | None]


@pytest.fixture
def settings(database_url: str) -> Settings:
    return make_settings(database_url)


@pytest.fixture
def catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(synthetic_catalog("s-cpi", "s-gdp").model_dump_json(), encoding="utf-8")
    return path


def worldbank(*steps: HttpResponse) -> tuple[Factory, ScriptedTransport]:
    transport = ScriptedTransport(list(steps))
    client, _ = make_client(transport)
    provider = WorldBankProvider(client, clock=Clock())
    return (lambda provider_id, _: provider if provider_id == "worldbank" else None), transport


def data(code: str) -> HttpResponse:
    return response(
        wb_page([wb_record("2021", "5.1", code=code), wb_record("2020", "4.9", code=code)])
    )


def run_cli(settings: Settings, *argv: str, factory: Factory | None = None) -> int:
    if factory is None:
        factory, _ = worldbank()
    return main(list(argv), settings=settings, economic_sources=factory, clock=Clock())


def test_a_full_run_exits_zero_and_reports_the_job(
    ingestion_session: Session,
    settings: Settings,
    catalog_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, transport = worldbank(
        data("FP.CPI.TOTL.ZG"),
        response(wb_indicator("FP.CPI.TOTL.ZG")),
        data("NY.GDP.MKTP.KD.ZG"),
        response(wb_indicator("NY.GDP.MKTP.KD.ZG")),
    )
    code = run_cli(settings, "run", "test-wdi", "--catalog", str(catalog_file), factory=factory)
    out = capsys.readouterr().out

    assert code == 0
    assert "Status: completed" in out
    assert "Attribution: Synthetic attribution (licence: CC BY 4.0)" in out
    # The default range runs from the catalogue's start to the current period.
    assert "date=2019:2026" in transport.requests[0][0]
    assert len(ingestion_session.scalars(select(EconomicObservation)).all()) == 4

    job = ingestion_session.scalars(select(IngestionJob)).one()
    assert main(["jobs"], settings=settings) == 0
    assert str(job.id) in capsys.readouterr().out
    assert main(["job", str(job.id)], settings=settings) == 0
    assert "s-cpi" in capsys.readouterr().out


def test_a_partial_failure_exits_three(
    ingestion_session: Session, settings: Settings, catalog_file: Path
) -> None:
    factory, _ = worldbank(
        data("FP.CPI.TOTL.ZG"),
        response(wb_indicator("FP.CPI.TOTL.ZG")),
        response("unavailable", status=503),
        response("unavailable", status=503),
        response("unavailable", status=503),
        response("unavailable", status=503),
    )
    code = run_cli(settings, "run", "test-wdi", "--catalog", str(catalog_file), factory=factory)
    assert code == 3
    job = ingestion_session.scalars(select(IngestionJob)).one()
    assert job.status is JobStatus.PARTIALLY_FAILED


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["run", "no-such-dataset"], "Unknown dataset 'no-such-dataset'"),
        (["run", "test-wdi", "--series", "s-nope"], "Not series of test-wdi: s-nope"),
        (["run", "test-wdi", "--start", "2022", "--end", "2020"], "is after the end"),
        (["run", "test-wdi", "--end", "2031"], "is in the future"),
        (["run", "test-wdi", "--start", "2020Q1"], "is a quarterly period"),
    ],
)
def test_bad_input_is_refused_before_anything_runs(
    ingestion_session: Session,
    settings: Settings,
    catalog_file: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    assert run_cli(settings, *argv, "--catalog", str(catalog_file)) == 2
    assert message in capsys.readouterr().err
    assert ingestion_session.scalars(select(IngestionJob)).all() == []


def test_a_second_run_is_refused_while_one_is_running(
    ingestion_session: Session,
    settings: Settings,
    catalog_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = ingestion_session
    assert run_cli(settings, "catalog", "--file", str(catalog_file)) == 0
    job = jobs.create_job(
        session, provider_id="worldbank", dataset_id="test-wdi", parameters={}, now=START
    )
    jobs.add_item(session, job, target_kind=JobTargetKind.ECONOMIC_SERIES, label="s-cpi")
    jobs.start_job(job, START)
    session.commit()

    assert run_cli(settings, "run", "test-wdi", "--catalog", str(catalog_file)) == 2
    assert "is still running" in capsys.readouterr().err


def test_price_import_from_the_command_line(
    ingestion_session: Session,
    settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
    prices = tmp_path / "prices.csv"
    prices.write_text(CSV, encoding="utf-8")

    argv = ["import-prices", "--manifest", str(manifest), "--file", str(prices)]
    assert run_cli(settings, *argv) == 0
    assert "Status: completed" in capsys.readouterr().out

    manifest.write_text("{}", encoding="utf-8")
    assert run_cli(settings, *argv) == 2
    assert "is not a valid price manifest" in capsys.readouterr().err


def test_catalog_check_and_template_need_no_database(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalog", "--check"]) == 0
    assert main(["manifest-template"]) == 0
    template = capsys.readouterr().out.split("\n", 1)[1]
    assert json.loads(template)["adjustment"] == "unadjusted"


def test_a_database_without_the_schema_is_explained(
    fresh_sqlite_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["jobs"], settings=make_settings(fresh_sqlite_url)) == 2
    assert "make migrate" in capsys.readouterr().err


def test_an_invalid_job_id_is_refused(settings: Settings) -> None:
    assert main(["job", "not-a-uuid"], settings=settings) == 2
