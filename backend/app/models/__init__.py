"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.dataset import Dataset
from app.models.entity import Company, Country, EconomicVariable, Entity, Industry
from app.models.graph import (
    GraphBuild,
    GraphEdge,
    GraphEdgeEvidence,
    GraphIssue,
    GraphNode,
    GraphNodeIdentifier,
    GraphResolutionDecision,
)
from app.models.ingestion import DataQualityIssue, IngestionJob, IngestionJobItem, SourceCapture
from app.models.market import Instrument, PriceBar
from app.models.provider import DataProvider
from app.models.relationship import Relationship
from app.models.scenario import Scenario, ScenarioShock
from app.models.series import EconomicObservation, EconomicSeries
from app.models.simulation import (
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
)

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
    "GraphBuild",
    "GraphEdge",
    "GraphEdgeEvidence",
    "GraphIssue",
    "GraphNode",
    "GraphNodeIdentifier",
    "GraphResolutionDecision",
    "Industry",
    "IngestionJob",
    "IngestionJobItem",
    "Instrument",
    "PriceBar",
    "Relationship",
    "Scenario",
    "ScenarioShock",
    "SimulationModelVersion",
    "SimulationRun",
    "SimulationRunStep",
    "SimulationSensitivityAnalysis",
    "SourceCapture",
]
