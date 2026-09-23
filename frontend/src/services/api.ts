/**
 * Typed endpoint functions — the only place the frontend knows API paths.
 * UI components call these (usually through `useApiResource`), never `fetch` directly.
 */

import { validateNetwork } from "@/features/network/model";
import { apiRequest, type RequestOptions } from "@/lib/apiClient";
import type {
  DatasetPage,
  EconomicSeriesDetail,
  EconomicSeriesPage,
  EconomicVariablePage,
  HealthResponse,
  IngestionJobDetail,
  IngestionJobPage,
  InstrumentDetail,
  InstrumentPage,
  NetworkResponse,
  ObservationPage,
  PriceBarPage,
  Provider,
  QualityIssuePage,
  QualityRule,
  ReadinessResponse,
  Scenario,
  ScenarioInput,
  ScenarioPage,
  SourceCapture,
  SystemStatus,
} from "@/types/api";

type Options = Pick<RequestOptions, "signal" | "baseUrl">;
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
    replace: (id: string, input: ScenarioInput, options?: Options) =>
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
export type { NetworkResponse };
