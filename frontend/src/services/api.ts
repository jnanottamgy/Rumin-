/**
 * Typed endpoint functions — the only place the frontend knows API paths.
 * UI components call these (usually through `useApiResource`), never `fetch` directly.
 */

import { validateNetwork } from "@/features/network/model";
import { apiRequest, type RequestOptions } from "@/lib/apiClient";
import type {
  Account,
  AccountCreateRequest,
  AccountList,
  AccountUpdateRequest,
  AnalysisRequest,
  AnalysisTargets,
  AnalysisVerification,
  AnalystCapabilities,
  AnalystSession,
  AnalystSessionPage,
  AnalystTurn,
  AuditEventList,
  CurrentSession,
  DatasetPage,
  EconomicSeriesDetail,
  EconomicSeriesPage,
  EconomicVariablePage,
  EntityAnalysis,
  EvidenceStatus,
  ExecutionVerification,
  ExposureMap,
  GraphBuildDetail,
  GraphBuildPage,
  GraphComponents,
  GraphDirection,
  GraphEdgeDetail,
  GraphEdgePage,
  GraphEdgeType,
  GraphNeighborhood,
  GraphNodeDetail,
  GraphNodeSearchPage,
  GraphNodeType,
  GraphOverview,
  GraphPaths,
  GraphTypes,
  HealthResponse,
  IngestionJobDetail,
  IngestionJobPage,
  InsightList,
  InstrumentDetail,
  InstrumentIntelligence,
  InstrumentPage,
  IntelligenceBrief,
  IntelligenceChanges,
  IntelligenceDrivers,
  IntelligenceEntityList,
  IntelligenceMethods,
  IntelligenceOverview,
  IntelligenceSignalList,
  LabExplanation,
  LabPathway,
  LabSensitivity,
  LabSensitivityList,
  LabSensitivityRequest,
  LoginRequest,
  ModelVerification,
  NetworkResponse,
  ObservationPage,
  PasswordChangeRequest,
  PriceBarPage,
  Provider,
  QualityIssuePage,
  QualityRule,
  ReadinessResponse,
  Scenario,
  ScenarioAnalysis,
  ScenarioAnalysisList,
  ScenarioAnalysisRequest,
  ScenarioComparison,
  ScenarioExecution,
  ScenarioExecutionPage,
  ScenarioInput,
  ScenarioPage,
  ScenarioPlan,
  ScenarioPreview,
  ScenarioResults,
  ScenarioTemplate,
  ScenarioTemplateList,
  ScenarioUpdate,
  ScenarioVersion,
  SensitivityAnalysis,
  SensitivityAnalysisList,
  SensitivityRequest,
  SeriesIntelligence,
  SimulationExplanation,
  SimulationModelDetail,
  SimulationModelSummary,
  SimulationProvenance,
  SimulationRequest,
  SimulationRun,
  SimulationRunPage,
  SimulationRunRequest,
  SimulationValidation,
  SimulationVerification,
  SourceCapture,
  StoredAnalysis,
  StoredAnalysisPage,
  SystemStatus,
  VariableExposure,
} from "@/types/api";

type Options = Pick<RequestOptions, "signal" | "baseUrl" | "headers">;
type QueryValue = string | number | boolean | null | undefined;

/** "?a=1&b=x" from the defined values only (encoded); "" when there are none. */
export function toQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(name, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const segment = encodeURIComponent;

/** The API's largest page. Economic series are annual, so one page holds a whole series. */
export const MAX_PAGE = 500;

export const api = {
  health: (options?: Options) => apiRequest<HealthResponse>("/health", options),

  readiness: (options?: Options) =>
    apiRequest<ReadinessResponse>("/health/ready", { ...options, acceptStatuses: [503] }),

  system: (options?: Options) => apiRequest<SystemStatus>("/api/v1/system", options),

  /** The network is validated at the boundary: a broken graph never reaches the canvas. */
  network: async (options?: Options) =>
    validateNetwork(await apiRequest<unknown>("/api/v1/network", options)),

  variables: (options?: Options) =>
    apiRequest<EconomicVariablePage>("/api/v1/variables?limit=500", options),

  scenarios: {
    list: (options?: Options) => apiRequest<ScenarioPage>("/api/v1/scenarios?limit=100", options),
    get: (id: string, options?: Options) =>
      apiRequest<Scenario>(`/api/v1/scenarios/${encodeURIComponent(id)}`, options),
    create: (input: ScenarioInput, options?: Options) =>
      apiRequest<Scenario>("/api/v1/scenarios", { ...options, method: "POST", body: input }),
    /** Saves a new version (never overwrites one). */
    replace: (id: string, input: ScenarioUpdate, options?: Options) =>
      apiRequest<Scenario>(`/api/v1/scenarios/${encodeURIComponent(id)}`, {
        ...options,
        method: "PUT",
        body: input,
      }),
    remove: (id: string, options?: Options) =>
      apiRequest<void>(`/api/v1/scenarios/${encodeURIComponent(id)}`, {
        ...options,
        method: "DELETE",
      }),
  },
};

/**
 * The Scenario Lab (Phase 5): versions, plans, previews, executions and everything read
 * from them. Executions and analyses are append-only.
 */
export const labApi = {
  templates: (options?: Options) =>
    apiRequest<ScenarioTemplateList>("/api/v1/scenario-templates", options),

  template: (id: string, options?: Options) =>
    apiRequest<ScenarioTemplate>(`/api/v1/scenario-templates/${segment(id)}`, options),

  plan: (input: ScenarioInput, options?: Options) =>
    apiRequest<ScenarioPlan>("/api/v1/scenarios/plan", { ...options, method: "POST", body: input }),

  preview: (input: ScenarioInput, options?: Options) =>
    apiRequest<ScenarioPreview>("/api/v1/scenarios/preview", {
      ...options,
      method: "POST",
      body: input,
    }),

  version: (id: string, version: number, options?: Options) =>
    apiRequest<ScenarioVersion>(`/api/v1/scenarios/${segment(id)}/versions/${version}`, options),

  restore: (id: string, version: number, options?: Options) =>
    apiRequest<Scenario>(`/api/v1/scenarios/${segment(id)}/versions/${version}/restore`, {
      ...options,
      method: "POST",
    }),

  duplicate: (id: string, name: string | null, options?: Options) =>
    apiRequest<Scenario>(`/api/v1/scenarios/${segment(id)}/duplicate`, {
      ...options,
      method: "POST",
      body: { name, version: null },
    }),

  execute: (id: string, version: number | null, options?: Options) =>
    apiRequest<ScenarioExecution>(`/api/v1/scenarios/${segment(id)}/executions`, {
      ...options,
      method: "POST",
      body: { version },
    }),

  executions: (id: string, options?: Options) =>
    apiRequest<ScenarioExecutionPage>(
      `/api/v1/scenarios/${segment(id)}/executions${toQuery({ limit: 50 })}`,
      options,
    ),

  execution: (id: string, options?: Options) =>
    apiRequest<ScenarioExecution>(`/api/v1/scenario-executions/${segment(id)}`, options),

  results: (id: string, options?: Options) =>
    apiRequest<ScenarioResults>(`/api/v1/scenario-executions/${segment(id)}/results`, options),

  pathways: (id: string, options?: Options) =>
    apiRequest<LabPathway>(`/api/v1/scenario-executions/${segment(id)}/pathways`, options),

  explanation: (id: string, target: string, options?: Options) =>
    apiRequest<LabExplanation>(
      `/api/v1/scenario-executions/${segment(id)}/explanation${toQuery({ target })}`,
      options,
    ),

  cancel: (id: string, options?: Options) =>
    apiRequest<ScenarioExecution>(`/api/v1/scenario-executions/${segment(id)}/cancel`, {
      ...options,
      method: "POST",
    }),

  verify: (id: string, options?: Options) =>
    apiRequest<ExecutionVerification>(`/api/v1/scenario-executions/${segment(id)}/verify`, {
      ...options,
      method: "POST",
    }),

  sensitivity: {
    list: (id: string, options?: Options) =>
      apiRequest<LabSensitivityList>(
        `/api/v1/scenario-executions/${segment(id)}/sensitivity`,
        options,
      ),
    create: (id: string, request: LabSensitivityRequest, options?: Options) =>
      apiRequest<LabSensitivity>(`/api/v1/scenario-executions/${segment(id)}/sensitivity`, {
        ...options,
        method: "POST",
        body: request,
      }),
  },

  analyses: {
    targets: (id: string, options?: Options) =>
      apiRequest<AnalysisTargets>(
        `/api/v1/scenario-executions/${segment(id)}/analysis-targets`,
        options,
      ),
    list: (id: string, options?: Options) =>
      apiRequest<ScenarioAnalysisList>(
        `/api/v1/scenario-executions/${segment(id)}/analyses`,
        options,
      ),
    get: (id: string, analysisId: string, options?: Options) =>
      apiRequest<ScenarioAnalysis>(
        `/api/v1/scenario-executions/${segment(id)}/analyses/${segment(analysisId)}`,
        options,
      ),
    create: (id: string, request: ScenarioAnalysisRequest, options?: Options) =>
      apiRequest<ScenarioAnalysis>(`/api/v1/scenario-executions/${segment(id)}/analyses`, {
        ...options,
        method: "POST",
        body: request,
      }),
    verify: (id: string, analysisId: string, options?: Options) =>
      apiRequest<AnalysisVerification>(
        `/api/v1/scenario-executions/${segment(id)}/analyses/${segment(analysisId)}/verify`,
        { ...options, method: "POST" },
      ),
  },

  compare: (ids: readonly string[], reference: string | null, options?: Options) =>
    apiRequest<ScenarioComparison>(
      `/api/v1/scenario-comparisons${toMultiQuery({ execution_id: ids, reference })}`,
      options,
    ),
};

export interface JobQuery {
  datasetId?: string;
  status?: string;
  limit?: number;
}

export interface IssueQuery {
  jobId?: string;
  seriesId?: string;
  instrumentId?: string;
  outcome?: string;
  limit?: number;
}

/** Phase 2 endpoints: provider data, ingestion history and data quality (read-only). */
export const dataApi = {
  providers: (options?: Options) => apiRequest<Provider[]>("/api/v1/providers", options),

  datasets: (options?: Options) =>
    apiRequest<DatasetPage>(`/api/v1/datasets${toQuery({ limit: 100 })}`, options),

  series: (options?: Options) =>
    apiRequest<EconomicSeriesPage>(
      `/api/v1/economic-series${toQuery({ limit: MAX_PAGE, sort: "name" })}`,
      options,
    ),

  seriesDetail: (id: string, options?: Options) =>
    apiRequest<EconomicSeriesDetail>(`/api/v1/economic-series/${segment(id)}`, options),

  observations: (id: string, includeRevisions: boolean, options?: Options) =>
    apiRequest<ObservationPage>(
      `/api/v1/economic-series/${segment(id)}/observations${toQuery({
        limit: MAX_PAGE,
        include_revisions: includeRevisions || undefined,
      })}`,
      options,
    ),

  instruments: (options?: Options) =>
    apiRequest<InstrumentPage>(`/api/v1/instruments${toQuery({ limit: 100 })}`, options),

  instrument: (id: string, options?: Options) =>
    apiRequest<InstrumentDetail>(`/api/v1/instruments/${segment(id)}`, options),

  prices: (id: string, datasetId: string, offset = 0, options?: Options) =>
    apiRequest<PriceBarPage>(
      `/api/v1/instruments/${segment(id)}/prices${toQuery({
        dataset_id: datasetId,
        limit: MAX_PAGE,
        offset: offset || undefined,
      })}`,
      options,
    ),

  jobs: (query: JobQuery = {}, options?: Options) =>
    apiRequest<IngestionJobPage>(
      `/api/v1/ingestion-jobs${toQuery({
        dataset_id: query.datasetId,
        status: query.status,
        limit: query.limit ?? 20,
      })}`,
      options,
    ),

  job: (id: string, options?: Options) =>
    apiRequest<IngestionJobDetail>(`/api/v1/ingestion-jobs/${segment(id)}`, options),

  issues: (query: IssueQuery = {}, options?: Options) =>
    apiRequest<QualityIssuePage>(
      `/api/v1/data-quality/issues${toQuery({
        job_id: query.jobId,
        series_id: query.seriesId,
        instrument_id: query.instrumentId,
        outcome: query.outcome,
        limit: query.limit ?? 100,
      })}`,
      options,
    ),

  rules: (options?: Options) => apiRequest<QualityRule[]>("/api/v1/data-quality/rules", options),

  capture: (id: number, options?: Options) =>
    apiRequest<SourceCapture>(`/api/v1/source-captures/${id}`, options),
};

export type Api = typeof api;

/**
 * The AI Analyst (Phase 7): conversations and their turns. Asking answers 202 with the
 * queued turn; `turn` is read again until it is final (`poll_after_ms`).
 */
export const analystApi = {
  capabilities: (options?: Options) =>
    apiRequest<AnalystCapabilities>("/api/v1/analyst/capabilities", options),

  sessions: (options?: Options) =>
    apiRequest<AnalystSessionPage>(`/api/v1/analyst/sessions${toQuery({ limit: 100 })}`, options),

  session: (id: string, options?: Options) =>
    apiRequest<AnalystSession>(`/api/v1/analyst/sessions/${segment(id)}`, options),

  create: (title: string | null, options?: Options) =>
    apiRequest<AnalystSession>("/api/v1/analyst/sessions", {
      ...options,
      method: "POST",
      body: title ? { title } : {},
    }),

  rename: (id: string, title: string, options?: Options) =>
    apiRequest<AnalystSession>(`/api/v1/analyst/sessions/${segment(id)}`, {
      ...options,
      method: "PUT",
      body: { title },
    }),

  remove: (id: string, options?: Options) =>
    apiRequest<void>(`/api/v1/analyst/sessions/${segment(id)}`, { ...options, method: "DELETE" }),

  ask: (sessionId: string, question: string, options?: Options) =>
    apiRequest<AnalystTurn>(`/api/v1/analyst/sessions/${segment(sessionId)}/turns`, {
      ...options,
      method: "POST",
      body: { question },
    }),

  turn: (sessionId: string, turnId: string, options?: Options) =>
    apiRequest<AnalystTurn>(
      `/api/v1/analyst/sessions/${segment(sessionId)}/turns/${segment(turnId)}`,
      options,
    ),
};
export type { NetworkResponse };

/** Filters shared by neighbourhood and path queries; empty lists mean "no filter". */
export interface GraphFilterQuery {
  edgeTypes?: readonly GraphEdgeType[];
  nodeTypes?: readonly GraphNodeType[];
  evidenceStatuses?: readonly EvidenceStatus[];
  includeIllustrative?: boolean;
  direction?: GraphDirection;
}

/** "?a=1&t=x&t=y" — like `toQuery`, but list values become repeated parameters. */
export function toMultiQuery(params: Record<string, QueryValue | readonly string[]>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      for (const item of value) search.append(name, item);
    } else if (value !== undefined && value !== null && value !== "") {
      search.set(name, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function filterParams(filters: GraphFilterQuery) {
  return {
    edge_type: filters.edgeTypes ?? [],
    evidence_status: filters.evidenceStatuses ?? [],
    include_illustrative: filters.includeIllustrative === false ? false : undefined,
    direction: filters.direction && filters.direction !== "any" ? filters.direction : undefined,
  };
}

export interface GraphSearchQuery {
  q?: string;
  types?: readonly GraphNodeType[];
  relatedTo?: string;
  sort?: "name" | "-degree";
  limit?: number;
}

/** The knowledge graph (read-only; built from the command line). */
export const graphApi = {
  overview: (options?: Options) => apiRequest<GraphOverview>("/api/v1/graph/overview", options),

  types: (options?: Options) => apiRequest<GraphTypes>("/api/v1/graph/types", options),

  search: (query: GraphSearchQuery, options?: Options) =>
    apiRequest<GraphNodeSearchPage>(
      `/api/v1/graph/nodes${toMultiQuery({
        q: query.q?.trim() || undefined,
        type: query.types ?? [],
        related_to: query.relatedTo,
        sort: query.sort,
        limit: query.limit ?? 20,
      })}`,
      options,
    ),

  node: (id: string, options?: Options) =>
    apiRequest<GraphNodeDetail>(`/api/v1/graph/nodes/${segment(id)}`, options),

  neighborhood: (
    id: string,
    depth: number,
    maxNodes: number,
    filters: GraphFilterQuery = {},
    options?: Options,
  ) =>
    apiRequest<GraphNeighborhood>(
      `/api/v1/graph/nodes/${segment(id)}/neighborhood${toMultiQuery({
        depth,
        max_nodes: maxNodes,
        node_type: filters.nodeTypes ?? [],
        ...filterParams(filters),
      })}`,
      options,
    ),

  edge: (id: string, options?: Options) =>
    apiRequest<GraphEdgeDetail>(`/api/v1/graph/edges/${segment(id)}`, options),

  /** One page of every node of the latest build, by name (the 3D universe reads them all). */
  nodePage: (offset: number, options?: Options) =>
    apiRequest<GraphNodeSearchPage>(
      `/api/v1/graph/nodes${toQuery({ limit: MAX_PAGE, offset, sort: "name" })}`,
      options,
    ),

  /** One page of every current edge. */
  edgePage: (offset: number, options?: Options) =>
    apiRequest<GraphEdgePage>(
      `/api/v1/graph/edges${toQuery({ limit: MAX_PAGE, offset })}`,
      options,
    ),

  paths: (
    source: string,
    target: string,
    maxDepth: number,
    limit: number,
    filters: GraphFilterQuery = {},
    options?: Options,
  ) =>
    apiRequest<GraphPaths>(
      `/api/v1/graph/paths${toMultiQuery({
        from: source,
        to: target,
        max_depth: maxDepth,
        limit,
        ...filterParams(filters),
      })}`,
      options,
    ),

  components: (options?: Options) =>
    apiRequest<GraphComponents>("/api/v1/graph/components", options),

  builds: (options?: Options) =>
    apiRequest<GraphBuildPage>(`/api/v1/graph/builds${toQuery({ limit: 20 })}`, options),

  build: (id: number, options?: Options) =>
    apiRequest<GraphBuildDetail>(`/api/v1/graph/builds/${id}`, options),
};

/**
 * The simulation engine (Phase 4). Runs and sensitivity analyses are append-only: they
 * are created with POST and never replaced or deleted.
 */
export const simulationApi = {
  models: (options?: Options) =>
    apiRequest<SimulationModelSummary[]>("/api/v1/simulation-models", options),

  model: (id: string, options?: Options) =>
    apiRequest<SimulationModelDetail>(`/api/v1/simulation-models/${segment(id)}`, options),

  verification: (id: string, version?: string | null, options?: Options) =>
    apiRequest<ModelVerification>(
      `/api/v1/simulation-models/${segment(id)}/verification${toQuery({ version: version ?? null })}`,
      options,
    ),

  validate: (request: SimulationRequest, options?: Options) =>
    apiRequest<SimulationValidation>("/api/v1/simulations/validate", {
      ...options,
      method: "POST",
      body: request,
    }),

  run: (request: SimulationRunRequest, options?: Options) =>
    apiRequest<SimulationRun>("/api/v1/simulations", { ...options, method: "POST", body: request }),

  runs: (query: { modelId?: string; limit?: number } = {}, options?: Options) =>
    apiRequest<SimulationRunPage>(
      `/api/v1/simulations${toQuery({ model_id: query.modelId, limit: query.limit ?? 10 })}`,
      options,
    ),

  get: (id: string, options?: Options) =>
    apiRequest<SimulationRun>(`/api/v1/simulations/${segment(id)}`, options),

  explanation: (id: string, options?: Options) =>
    apiRequest<SimulationExplanation>(`/api/v1/simulations/${segment(id)}/explanation`, options),

  provenance: (id: string, options?: Options) =>
    apiRequest<SimulationProvenance>(`/api/v1/simulations/${segment(id)}/provenance`, options),

  verify: (id: string, options?: Options) =>
    apiRequest<SimulationVerification>(`/api/v1/simulations/${segment(id)}/verify`, {
      ...options,
      method: "POST",
    }),

  sensitivity: {
    list: (id: string, options?: Options) =>
      apiRequest<SensitivityAnalysisList>(
        `/api/v1/simulations/${segment(id)}/sensitivity`,
        options,
      ),
    create: (id: string, request: SensitivityRequest, options?: Options) =>
      apiRequest<SensitivityAnalysis>(`/api/v1/simulations/${segment(id)}/sensitivity`, {
        ...options,
        method: "POST",
        body: request,
      }),
  },
};

/** Threshold overrides for an intelligence read (GET /intelligence/methods lists them). */
export type ThresholdOverrides = Readonly<Record<string, string | undefined>>;
export type EvidenceFilter = "any" | "evidence_backed";

/**
 * Financial intelligence (Phase 6): findings computed from the stored data, the knowledge
 * graph and stored executions, each with its evidence chain. Reads write nothing; stored
 * analyses are append-only.
 */
export const intelligenceApi = {
  overview: (thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<IntelligenceOverview>(
      `/api/v1/intelligence/overview${toQuery({ ...thresholds })}`,
      options,
    ),

  insights: (
    query: { entity?: string; kind?: string; rule?: string; grade?: string } = {},
    options?: Options,
  ) => apiRequest<InsightList>(`/api/v1/intelligence/insights${toQuery(query)}`, options),

  changes: (thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<IntelligenceChanges>(
      `/api/v1/intelligence/changes${toQuery({ ...thresholds })}`,
      options,
    ),

  methods: (options?: Options) =>
    apiRequest<IntelligenceMethods>("/api/v1/intelligence/methods", options),

  entities: (kind?: "company" | "industry", options?: Options) =>
    apiRequest<IntelligenceEntityList>(
      `/api/v1/intelligence/entities${toQuery({ kind })}`,
      options,
    ),

  entity: (
    key: string,
    thresholds: ThresholdOverrides = {},
    evidence: EvidenceFilter = "any",
    options?: Options,
  ) =>
    apiRequest<EntityAnalysis>(
      `/api/v1/intelligence/entities/${segment(key)}${toQuery({
        ...thresholds,
        evidence: evidence === "any" ? undefined : evidence,
      })}`,
      options,
    ),

  brief: (key: string, thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<IntelligenceBrief>(
      `/api/v1/intelligence/entities/${segment(key)}/brief${toQuery({ ...thresholds })}`,
      options,
    ),

  exposure: (key: string, evidence: EvidenceFilter = "any", options?: Options) =>
    apiRequest<ExposureMap>(
      `/api/v1/intelligence/entities/${segment(key)}/exposure${toQuery({
        evidence: evidence === "any" ? undefined : evidence,
      })}`,
      options,
    ),

  signals: (key: string, thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<IntelligenceSignalList>(
      `/api/v1/intelligence/entities/${segment(key)}/signals${toQuery({ ...thresholds })}`,
      options,
    ),

  drivers: (key: string, options?: Options) =>
    apiRequest<IntelligenceDrivers>(
      `/api/v1/intelligence/entities/${segment(key)}/drivers`,
      options,
    ),

  variableExposure: (key: string, options?: Options) =>
    apiRequest<VariableExposure>(
      `/api/v1/intelligence/variables/${segment(key)}/exposure`,
      options,
    ),

  series: (id: string, thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<SeriesIntelligence>(
      `/api/v1/intelligence/series/${segment(id)}${toQuery({ ...thresholds })}`,
      options,
    ),

  instrument: (id: string, thresholds: ThresholdOverrides = {}, options?: Options) =>
    apiRequest<InstrumentIntelligence>(
      `/api/v1/intelligence/instruments/${segment(id)}${toQuery({ ...thresholds })}`,
      options,
    ),

  analyses: {
    create: (request: AnalysisRequest, options?: Options) =>
      apiRequest<StoredAnalysis>("/api/v1/intelligence/analyses", {
        ...options,
        method: "POST",
        body: request,
      }),
    list: (query: { scope?: string; entity?: string; limit?: number } = {}, options?: Options) =>
      apiRequest<StoredAnalysisPage>(
        `/api/v1/intelligence/analyses${toQuery({ ...query, limit: query.limit ?? 20 })}`,
        options,
      ),
    get: (id: string, options?: Options) =>
      apiRequest<StoredAnalysis>(`/api/v1/intelligence/analyses/${segment(id)}`, options),
  },
};

/**
 * Signing in and out, and one's own password (Phase 10). The session lives in an `HttpOnly`
 * cookie the browser sends by itself; no response carries the token.
 */
export const authApi = {
  /** Who is signed in; 401 (kept quiet) when nobody is. */
  session: (options?: Options) =>
    apiRequest<CurrentSession>("/api/v1/auth/session", { ...options, quietAuth: true }),

  login: (request: LoginRequest, options?: Options) =>
    apiRequest<CurrentSession>("/api/v1/auth/login", {
      ...options,
      method: "POST",
      body: request,
      quietAuth: true,
    }),

  logout: (options?: Options) =>
    apiRequest<void>("/api/v1/auth/logout", { ...options, method: "POST", quietAuth: true }),

  changePassword: (request: PasswordChangeRequest, options?: Options) =>
    apiRequest<CurrentSession>("/api/v1/auth/password", {
      ...options,
      method: "POST",
      body: request,
    }),
};

/** People and the security audit trail: administrators only (Phase 10). */
export const peopleApi = {
  list: (options?: Options) => apiRequest<AccountList>("/api/v1/users", options),

  create: (request: AccountCreateRequest, options?: Options) =>
    apiRequest<Account>("/api/v1/users", { ...options, method: "POST", body: request }),

  update: (id: string, request: AccountUpdateRequest, options?: Options) =>
    apiRequest<Account>(`/api/v1/users/${segment(id)}`, {
      ...options,
      method: "PUT",
      body: request,
    }),

  resetPassword: (id: string, temporaryPassword: string, options?: Options) =>
    apiRequest<Account>(`/api/v1/users/${segment(id)}/password`, {
      ...options,
      method: "POST",
      body: { temporary_password: temporaryPassword },
    }),

  revokeSessions: (id: string, options?: Options) =>
    apiRequest<void>(`/api/v1/users/${segment(id)}/sessions/revoke`, {
      ...options,
      method: "POST",
    }),

  events: (limit = 100, options?: Options) =>
    apiRequest<AuditEventList>(`/api/v1/audit-events${toQuery({ limit })}`, options),
};
