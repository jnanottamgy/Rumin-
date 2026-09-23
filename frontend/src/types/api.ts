/**
 * Friendly names for the API contract.
 *
 * The source of truth is `api.generated.ts`, generated from docs/api/openapi.json
 * (`npm run generate:api`). Never edit the generated file by hand; alias from it here.
 */
import type { components } from "./api.generated";

type Schemas = components["schemas"];

export type EntityKind = Schemas["EntityKind"];
export type CompanyEntity = Schemas["CompanyRead"];
export type IndustryEntity = Schemas["IndustryRead"];
export type CountryEntity = Schemas["CountryRead"];
export type EconomicVariable = Schemas["EconomicVariableRead"];
export type Entity = CompanyEntity | IndustryEntity | CountryEntity | EconomicVariable;
export type ChangeRule = Schemas["ChangeRuleRead"];
export type ChangeType = Schemas["ChangeType"];

export type RelationshipType = Schemas["RelationshipType"];
export type StructuralLinkType = Schemas["StructuralLinkType"];
export type EdgeType = RelationshipType | StructuralLinkType;
export type Relationship = Schemas["RelationshipRead"];
export type StructuralLink = Schemas["StructuralLinkRead"];
export type NetworkEdge = Relationship | StructuralLink;
export type RelationshipTypeInfo = Schemas["RelationshipTypeRead"];
export type Polarity = Schemas["Polarity"];
export type Strength = Schemas["Strength"];
export type EvidenceLevel = Schemas["EvidenceLevel"];

export type NetworkNode = Schemas["NetworkNode"];
export type NetworkResponse = Schemas["NetworkResponse"];
export type DatasetSummary = Schemas["DatasetSummary"];

export type Scenario = Schemas["ScenarioRead"];
export type ScenarioInput = Schemas["ScenarioInput"];
export type ShockInput = Schemas["ShockInput"];
export type ScenarioPage = Schemas["ScenarioPage"];
export type EconomicVariablePage = Schemas["EconomicVariablePage"];

export type SystemStatus = Schemas["SystemStatus"];
export type Capability = Schemas["Capability"];
export type HealthResponse = Schemas["HealthResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];

export type ErrorDetail = Schemas["ErrorDetail"];
export type ErrorResponse = Schemas["ErrorResponse"];

// Phase 2: provider data, ingestion and data quality.
export type DataStatus = Schemas["DataStatus"];
export type Provider = Schemas["ProviderRead"];
export type Dataset = Schemas["DatasetRead"];
export type DatasetPage = Schemas["DatasetPage"];
export type DatasetRef = Schemas["DatasetRef"];
export type DatasetKind = Schemas["DatasetKind"];
export type JobRef = Schemas["JobRef"];
export type Frequency = Schemas["Frequency"];
export type MeasureType = Schemas["MeasureType"];
export type EconomicSeries = Schemas["SeriesRead"];
export type EconomicSeriesPage = Schemas["SeriesPage"];
export type EconomicSeriesDetail = Schemas["SeriesDetail"];
export type LatestObservation = Schemas["LatestObservation"];
export type SeriesRef = Schemas["SeriesRef"];
export type InstrumentRef = Schemas["InstrumentRef"];
export type Observation = Schemas["ObservationRead"];
export type ObservationPage = Schemas["ObservationPage"];
export type ObservationStatus = Schemas["ObservationStatus"];
export type QualityStatus = Schemas["QualityStatus"];
export type Instrument = Schemas["InstrumentRead"];
export type InstrumentPage = Schemas["InstrumentPage"];
export type InstrumentDetail = Schemas["InstrumentDetail"];
export type PriceBar = Schemas["PriceBarRead"];
export type PriceBarPage = Schemas["PriceBarPage"];
export type IngestionJob = Schemas["JobRead"];
export type IngestionJobPage = Schemas["JobPage"];
export type IngestionJobDetail = Schemas["JobDetail"];
export type IngestionJobItem = Schemas["JobItemRead"];
export type JobStatus = Schemas["JobStatus"];
export type JobItemStatus = Schemas["JobItemStatus"];
export type SourceCapture = Schemas["CaptureRead"];
export type QualityIssue = Schemas["IssueRead"];
export type QualityIssuePage = Schemas["IssuePage"];
export type QualityRule = Schemas["RuleRead"];
export type IssueOutcome = Schemas["IssueOutcome"];
export type IssueSeverity = Schemas["IssueSeverity"];

// Phase 3: the knowledge graph.
export type GraphNodeType = Schemas["GraphNodeType"];
export type GraphEdgeType = Schemas["GraphEdgeType"];
export type EvidenceStatus = Schemas["EvidenceStatus"];
export type NodeNature = Schemas["NodeNature"];
export type GraphDirection = Schemas["Direction"];
export type GraphNodeSummary = Schemas["GraphNodeSummary"];
export type GraphNeighbor = Schemas["NeighborNode"];
export type GraphNodeSearchResult = Schemas["NodeSearchResult"];
export type GraphNodeSearchPage = Schemas["Page_NodeSearchResult_"];
export type GraphNodeDetail = Schemas["GraphNodeDetail"];
export type GraphEdgeSummary = Schemas["GraphEdgeSummary"];
export type GraphEdgeDetail = Schemas["GraphEdgeDetail"];
export type GraphEdgePage = Schemas["Page_GraphEdgeSummary_"];
export type GraphEvidence = Schemas["EvidenceRead"];
export type GraphExposure = Schemas["ExposureRead"];
export type GraphIdentifier = Schemas["IdentifierRead"];
export type GraphNeighborhood = Schemas["NeighborhoodResponse"];
export type GraphPaths = Schemas["PathsResponse"];
export type GraphPath = Schemas["PathRead"];
export type GraphOverview = Schemas["GraphOverview"];
export type GraphTypeMapNode = Schemas["TypeMapNode"];
export type GraphTypeMapLink = Schemas["TypeMapLink"];
export type GraphTypes = Schemas["GraphTypesResponse"];
export type GraphEdgeTypeInfo = Schemas["EdgeTypeRead"];
export type GraphNodeTypeInfo = Schemas["NodeTypeRead"];
export type GraphEvidenceStatusInfo = Schemas["EvidenceStatusRead"];
export type GraphBuildSummary = Schemas["GraphBuildSummary"];
export type GraphBuildPage = Schemas["Page_GraphBuildSummary_"];
export type GraphBuildDetail = Schemas["GraphBuildDetail"];
export type GraphIssue = Schemas["GraphIssueRead"];
export type GraphComponents = Schemas["ComponentsResponse"];

// Phase 4: the simulation engine.
export type SimulationModelSummary = Schemas["SimulationModelSummary"];
export type SimulationModelDetail = Schemas["SimulationModelDetail"];
export type SimulationInputDefinition = Schemas["InputDefinitionRead"];
export type SimulationObservationSource = Schemas["ObservationSourceRead"];
export type SimulationEquation = Schemas["EquationRead"];
export type SimulationOutputDefinition = Schemas["OutputDefinitionRead"];
export type SimulationTransmissionRule = Schemas["TransmissionRuleRead"];
export type SimulationGraphEdge = Schemas["GraphEdgeRead"];
export type SimulationStatement = Schemas["StatementRead"];
export type SimulationPathwayLink = Schemas["PathwayLinkRead"];
export type SimulationInputValue = Schemas["SimulationInputValue"];
export type SimulationRequest = Schemas["SimulationRequest"];
export type SimulationRunRequest = Schemas["SimulationRunRequest"];
export type SimulationIssue = Schemas["SimulationIssueRead"];
export type SimulationObservation = Schemas["SimulationObservationRead"];
export type SimulationResolvedInput = Schemas["ResolvedInputRead"];
export type SimulationGraphSnapshot = Schemas["GraphSnapshotRead"];
export type SimulationValidation = Schemas["ValidationReport"];
export type SimulationOutput = Schemas["OutputRead"];
export type SimulationMonthlySeries = Schemas["MonthlySeriesRead"];
export type SimulationContribution = Schemas["ContributionRead"];
export type SimulationBridge = Schemas["BridgeRead"];
export type SimulationRun = Schemas["SimulationRunRead"];
export type SimulationRunSummary = Schemas["SimulationRunSummary"];
export type SimulationRunPage = Schemas["Page_SimulationRunSummary_"];
export type SimulationExplanation = Schemas["ExplanationRead"];
export type SimulationStep = Schemas["StepRead"];
export type SimulationEquationUse = Schemas["EquationUseRead"];
export type SimulationPathway = Schemas["PathwayRead"];
export type SimulationPathwayNode = Schemas["PathwayNodeRead"];
export type SimulationPathwayEdge = Schemas["PathwayEdgeRead"];
export type SimulationParameter = Schemas["ParameterRead"];
export type SimulationProvenance = Schemas["ProvenanceRead"];
export type SimulationTransmissionPath = Schemas["TransmissionPathRead"];
export type SimulationVerification = Schemas["VerificationRead"];
export type SensitivityRequest = Schemas["SensitivityRequest"];
export type SensitivityAnalysis = Schemas["SensitivityAnalysisRead"];
export type SensitivityAnalysisList = Schemas["SensitivityAnalysisList"];
export type SensitivityItem = Schemas["SensitivityItemRead"];
export type SensitivityPoint = Schemas["SensitivityPointRead"];
