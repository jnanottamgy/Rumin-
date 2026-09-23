/**
 * Typed endpoint functions — the only place the frontend knows API paths.
 * UI components call these (usually through `useApiResource`), never `fetch` directly.
 */

import { validateNetwork } from "@/features/network/model";
import { apiRequest, type RequestOptions } from "@/lib/apiClient";
import type {
  EconomicVariablePage,
  HealthResponse,
  NetworkResponse,
  ReadinessResponse,
  Scenario,
  ScenarioInput,
  ScenarioPage,
  SystemStatus,
} from "@/types/api";

type Options = Pick<RequestOptions, "signal" | "baseUrl">;

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

export type Api = typeof api;
export type { NetworkResponse };
