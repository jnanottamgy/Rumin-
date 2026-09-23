"""The graph command line: output and exit codes."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.graph.cli import EXIT_FAILED, EXIT_NOT_STARTED, EXIT_OK, main
from app.models import Company
from tests.conftest import make_settings


def run(database_url: str, *argv: str) -> int:
    return main(list(argv), settings=make_settings(database_url))


def test_build_prints_the_validation_report(
    graph_session: Session, database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(database_url, "build") == EXIT_OK
    out = capsys.readouterr().out
    assert "GRAPH VALIDATION REPORT" in out
    assert "Nodes processed: 39" in out and "Edges processed: 82" in out
    assert "Rejected edges: 0" in out


def test_status_says_when_sources_changed(
    graph_session: Session, database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(database_url, "status") == EXIT_OK
    assert "No graph has been built yet" in capsys.readouterr().out
    run(database_url, "build")
    capsys.readouterr()
    run(database_url, "status")
    assert "up to date" in capsys.readouterr().out
    company = graph_session.get_one(Company, "co_skyvara_air")
    original = company.description
    try:
        company.description = "Changed for a test."
        graph_session.commit()
        run(database_url, "status")
        assert "sources have changed" in capsys.readouterr().out
    finally:
        company.description = original
        graph_session.commit()


def test_builds_and_report(
    graph_session: Session, database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run(database_url, "build")
    run(database_url, "build")
    capsys.readouterr()
    assert run(database_url, "builds") == EXIT_OK
    listing = capsys.readouterr().out
    assert "2 of 2 build(s)" in listing
    assert run(database_url, "report") == EXIT_OK
    assert "0 changed" in capsys.readouterr().out
    assert run(database_url, "report", "999") == EXIT_NOT_STARTED


def test_validate_writes_nothing(
    graph_session: Session, database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(database_url, "validate") == EXIT_OK
    assert "dry run" in capsys.readouterr().out
    run(database_url, "builds")
    assert "No graph builds yet" in capsys.readouterr().out


def test_unmigrated_database(fresh_sqlite_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(fresh_sqlite_url, "build") == EXIT_NOT_STARTED
    assert "make migrate" in capsys.readouterr().err


def test_exit_codes_are_distinct() -> None:
    assert len({EXIT_OK, EXIT_FAILED, EXIT_NOT_STARTED}) == 3
