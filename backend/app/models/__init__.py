"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.dataset import Dataset
from app.models.entity import Company, Country, EconomicVariable, Entity, Industry
from app.models.ingestion import DataQualityIssue, IngestionJob, IngestionJobItem, SourceCapture
from app.models.market import Instrument, PriceBar
from app.models.provider import DataProvider
from app.models.relationship import Relationship
from app.models.scenario import Scenario, ScenarioShock
from app.models.series import EconomicObservation, EconomicSeries

__all__ = [
    "Company",
    "Country",
    "DataProvider",
    "DataQualityIssue",
    "Dataset",
    "EconomicObservation",
    "EconomicSeries",
    "EconomicVariable",
    "Entity",
    "Industry",
    "IngestionJob",
    "IngestionJobItem",
    "Instrument",
    "PriceBar",
    "Relationship",
    "Scenario",
    "ScenarioShock",
    "SourceCapture",
]
