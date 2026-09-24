"""Helpers for the intelligence tests.

Every stored value here is SYNTHETIC: chosen so that changes, trends and revisions can be
worked out by hand. The values are stored through the real ingestion pipeline (a scripted
World Bank response), exactly as retrieved data would be, so the analysis reads them the
way it reads real observations. They are not real exchange rates or inflation figures.

Exchange rate (INR per USD, annual): 2021–2025 are 73.9, 78.6, 82.6, 83.7 → revised to 84.2,
92.1. The latest change is (92.1 − 84.2) / 84.2 × 100 = 9.3824228029 %; the least-squares
slope of 2021–2025 (73.9, 78.6, 82.6, 84.2, 92.1) is 42 / 10 = 4.2 a year.
Inflation (%, annual): 2024 → 2025 is 4.9 → 3.1, a change of −1.8 percentage points.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domain.enums import JobStatus
from app.ingestion.economic import run_economic_ingestion
from app.ingestion.providers.worldbank import WorldBankProvider
from app.models import Dataset, EconomicSeries
from tests.fakes import ScriptedTransport, make_client, response, wb_indicator, wb_page, wb_record
from tests.test_ingestion_pipeline import Clock

FX_SERIES = "wb-ind-pa-nus-fcrf"
CPI_SERIES = "wb-ind-fp-cpi-totl-zg"

FX_VALUES = [
    (2010, "45.7"),
    (2011, "46.6"),
    (2012, "53.4"),
    (2013, "58.6"),
    (2014, "61.0"),
    (2015, "64.2"),
    (2016, "67.2"),
    (2017, "65.1"),
    (2018, "68.4"),
    (2019, "70.4"),
    (2020, "74.1"),
    (2021, "73.9"),
    (2022, "78.6"),
    (2023, "82.6"),
    (2024, "83.7"),
    (2025, "92.1"),
]
FX_REVISED_2024 = "84.2"
CPI_VALUES = [
    (2014, "6.7"),
    (2015, "4.9"),
    (2016, "4.9"),
    (2017, "3.3"),
    (2018, "3.9"),
    (2019, "3.7"),
    (2020, "6.6"),
    (2021, "5.1"),
    (2022, "6.7"),
    (2023, "5.6"),
    (2024, "4.9"),
    (2025, "3.1"),
]


def ingest(
    session: Session, series_id: str, code: str, values: list[tuple[int, str]], clock: Clock
) -> None:
    """Store SYNTHETIC ``values`` for ``series_id`` through the ingestion pipeline."""
    transport = ScriptedTransport(
        [
            response(wb_page([wb_record(str(year), value, code=code) for year, value in values])),
            response(wb_indicator(code)),
        ]
    )
    http, _ = make_client(transport)
    job = run_economic_ingestion(
        session,
        WorldBankProvider(http, clock=clock),
        dataset=session.get_one(Dataset, "worldbank-wdi"),
        series=[session.get_one(EconomicSeries, series_id)],
        start={series_id: str(values[0][0])},
        end={series_id: str(values[-1][0])},
        parameters={"test": True},
        today=date(2026, 9, 24),
        http=http,
        clock=clock,
    )
    assert job.status is JobStatus.COMPLETED


def store_synthetic_history(session: Session) -> None:
    """The SYNTHETIC exchange-rate and inflation histories, with 2024's rate revised."""
    clock = Clock()
    ingest(session, FX_SERIES, "PA.NUS.FCRF", FX_VALUES, clock)
    ingest(session, CPI_SERIES, "FP.CPI.TOTL.ZG", CPI_VALUES, clock)
    revised = [(year, FX_REVISED_2024 if year == 2024 else value) for year, value in FX_VALUES]
    ingest(session, FX_SERIES, "PA.NUS.FCRF", revised, clock)
    session.commit()
