"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.analyst import AnalystSession, AnalystToolCall, AnalystTurn
from app.models.auth import AuditEvent, User, UserSession
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
from app.models.intelligence import IntelligenceAnalysis
from app.models.market import Instrument, PriceBar
from app.models.provider import DataProvider
from app.models.relationship import Relationship
from app.models.scenario import (
    Scenario,
    ScenarioAnalysis,
    ScenarioExecution,
    ScenarioExecutionRun,
    ScenarioSensitivityAnalysis,
    ScenarioShock,
    ScenarioVersion,
)
from app.models.series import EconomicObservation, EconomicSeries
from app.models.simulation import (
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
)

__all__ = [
    "AnalystSession",
    "AnalystToolCall",
    "AnalystTurn",
    "AuditEvent",
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
    "IntelligenceAnalysis",
    "PriceBar",
    "Relationship",
    "Scenario",
    "ScenarioAnalysis",
    "ScenarioExecution",
    "ScenarioExecutionRun",
    "ScenarioSensitivityAnalysis",
    "ScenarioShock",
    "ScenarioVersion",
    "SimulationModelVersion",
    "SimulationRun",
    "SimulationRunStep",
    "SimulationSensitivityAnalysis",
    "SourceCapture",
    "User",
    "UserSession",
]
