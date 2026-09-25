/**
 * What the 3D universe reads, besides what the explorer already reads.
 *
 * - **The whole build**, only when it is small: at most `UNIVERSE_BUDGET` nodes and edges,
 *   read one page at a time (500 per page, so at most six requests). A larger build is
 *   never loaded whole: the page starts from a node and grows by neighbourhoods instead.
 * - **A scenario overlay**: a stored execution, its modelled pathway and its results, all
 *   read-only.
 */
import { useEffect, useMemo } from "react";
import { isFinal } from "@/features/scenarioLab/format";
import { useApiResource } from "@/hooks/useApiResource";
import type { RequestOptions } from "@/lib/apiClient";
import { graphApi, labApi, MAX_PAGE } from "@/services/api";
import type { GraphEdgeSummary, GraphNodeSummary, GraphOverview } from "@/types/api";
import { buildOverlay, type ScenarioOverlay } from "./overlay";

export const UNIVERSE_BUDGET = { nodes: 500, edges: 2500 } as const;

export type WholeGraph =
  | { status: "loading" }
  | { status: "not-built" }
  | { status: "too-large"; nodes: number; edges: number }
  | {
      status: "ready";
      nodes: GraphNodeSummary[];
      edges: GraphEdgeSummary[];
      /** The build grew past the budget while it was read: only the first pages are shown. */
      truncated: boolean;
    }
  | { status: "error"; error: unknown; retry: () => void };

type Loaded =
  | { kind: "not-built" }
  | { kind: "too-large"; nodes: number; edges: number }
  | { kind: "ready"; nodes: GraphNodeSummary[]; edges: GraphEdgeSummary[]; truncated: boolean };

export function withinBudget(nodes: number, edges: number): boolean {
  return nodes <= UNIVERSE_BUDGET.nodes && edges <= UNIVERSE_BUDGET.edges;
}

/**
 * Every node and edge of the current build, one page at a time, stopping at the budget
 * (`truncated` then says so). Callers check the build's counts against the budget first.
 */
export async function readWholeGraph(
  options?: Pick<RequestOptions, "signal" | "baseUrl">,
): Promise<{
  nodes: GraphNodeSummary[];
  edges: GraphEdgeSummary[];
  truncated: boolean;
}> {
  const nodes: GraphNodeSummary[] = [];
  let truncated = false;
  for (let offset = 0; ; offset += MAX_PAGE) {
    const page = await graphApi.nodePage(offset, options);
    nodes.push(...page.items);
    if (nodes.length >= page.total || page.items.length === 0) break;
    if (nodes.length >= UNIVERSE_BUDGET.nodes) {
      truncated = true;
      break;
    }
  }
  const edges: GraphEdgeSummary[] = [];
  for (let offset = 0; ; offset += MAX_PAGE) {
    const page = await graphApi.edgePage(offset, options);
    edges.push(...page.items);
    if (edges.length >= page.total || page.items.length === 0) break;
    if (edges.length >= UNIVERSE_BUDGET.edges) {
      truncated = true;
      break;
    }
  }
  return { nodes, edges, truncated };
}

export function useWholeGraph(overview: GraphOverview | undefined): WholeGraph {
  const build = overview?.build ?? null;
  const nodeCount = build?.node_count ?? 0;
  const edgeCount = build?.edge_count ?? 0;
  const key = overview
    ? `universe-graph:${build?.id ?? "none"}:${nodeCount}:${edgeCount}`
    : "universe-graph:pending";
  const resource = useApiResource<Loaded | null>(key, async () => {
    if (!overview) return null;
    if (!build || nodeCount === 0) return { kind: "not-built" };
    if (!withinBudget(nodeCount, edgeCount)) {
      return { kind: "too-large", nodes: nodeCount, edges: edgeCount };
    }
    return { kind: "ready", ...(await readWholeGraph()) };
  });
  const { status, data, error, reload } = resource;
  // One object per state, so what is derived from it is not recomputed on every render.
  return useMemo((): WholeGraph => {
    if (status === "error") return { status: "error", error, retry: reload };
    if (status === "loading" || !data) return { status: "loading" };
    if (data.kind === "not-built") return { status: "not-built" };
    if (data.kind === "too-large") {
      return { status: "too-large", nodes: data.nodes, edges: data.edges };
    }
    return { status: "ready", nodes: data.nodes, edges: data.edges, truncated: data.truncated };
  }, [status, data, error, reload]);
}

export type OverlayState =
  | { status: "none" }
  | { status: "loading" }
  | { status: "ready"; overlay: ScenarioOverlay }
  | {
      status: "not-completed";
      name: string;
      state: string;
      /** Failed or cancelled: it will never have results to lay over. */
      final: boolean;
      recheck: () => void;
    }
  | { status: "error"; error: unknown; retry: () => void };

/** Bounds on how often a running execution is read again (the server suggests the interval). */
const RECHECK_MS = { min: 250, max: 5000, fallback: 1000 } as const;

export function useScenarioOverlay(executionId: string | null): OverlayState {
  type Loaded =
    | { kind: "pending"; name: string; state: string; final: boolean; pollAfter: number }
    | { kind: "ready"; overlay: ScenarioOverlay }
    | null;
  const resource = useApiResource<Loaded>(`universe-overlay:${executionId ?? "none"}`, async () => {
    if (!executionId) return null;
    const execution = await labApi.execution(executionId);
    if (execution.status !== "completed") {
      return {
        kind: "pending",
        name: execution.scenario_name,
        state: execution.status,
        final: isFinal(execution.status),
        pollAfter: execution.poll_after_ms ?? RECHECK_MS.fallback,
      };
    }
    const [pathway, results] = await Promise.all([
      labApi.pathways(executionId),
      labApi.results(executionId),
    ]);
    return { kind: "ready", overlay: buildOverlay(execution, pathway, results) };
  });
  const { status, data, error, reload } = resource;
  // A running execution is read again at the server's interval until it is final, so the
  // overlay appears when it completes (and a cached "running" answer is never the last word).
  useEffect(() => {
    if (status !== "success" || data?.kind !== "pending" || data.final) return;
    const wait = Math.min(RECHECK_MS.max, Math.max(RECHECK_MS.min, data.pollAfter));
    const timer = window.setTimeout(reload, wait);
    return () => window.clearTimeout(timer);
  }, [status, data, reload]);
  return useMemo((): OverlayState => {
    if (!executionId) return { status: "none" };
    if (status === "error") return { status: "error", error, retry: reload };
    if (status === "loading" || !data) return { status: "loading" };
    if (data.kind === "pending") {
      return {
        status: "not-completed",
        name: data.name,
        state: data.state,
        final: data.final,
        recheck: reload,
      };
    }
    return { status: "ready", overlay: data.overlay };
  }, [executionId, status, data, error, reload]);
}
