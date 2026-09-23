/**
 * The Graph Explorer's state: what the reader asked to see, its history, and the server's
 * answers. What is drawn is derived from these (see `view.ts`), so going back, resetting
 * or changing a filter can never leave the canvas out of step with the data.
 *
 * A *snapshot* is small — mode, focus, depth, the nodes expanded (in order), the selection
 * and the path query — so history is a plain list of snapshots: Back and Forward restore
 * exactly what was on screen, and every answer is cached, so they cost no requests.
 * Filters and the visible-node limit are view settings rather than history.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type GraphFilterQuery, graphApi } from "@/services/api";
import type {
  EvidenceStatus,
  GraphDirection,
  GraphEdgeType,
  GraphNeighborhood,
  GraphNodeType,
  GraphPaths,
} from "@/types/api";
import { type Answer, buildPathView, buildView, type GraphView } from "./view";

export type ExplorerMode = "map" | "explore" | "paths";

export interface Selection {
  kind: "node" | "edge";
  id: string;
}

export interface PathQuery {
  from: string;
  to: string;
  maxDepth: number;
  limit: number;
}

export interface ExplorerSnapshot {
  mode: ExplorerMode;
  focus: string | null;
  depth: number;
  expansions: readonly string[];
  selection: Selection | null;
  path: PathQuery | null;
}

export interface ExplorerFilters {
  /** Empty lists mean "no filter". */
  nodeTypes: readonly GraphNodeType[];
  edgeTypes: readonly GraphEdgeType[];
  evidenceStatuses: readonly EvidenceStatus[];
  includeIllustrative: boolean;
  direction: GraphDirection;
}

export const DEFAULT_FILTERS: ExplorerFilters = {
  nodeTypes: [],
  edgeTypes: [],
  evidenceStatuses: [],
  includeIllustrative: true,
  direction: "any",
};

/** Visible-node limits the reader can choose; the API's own cap is 200 per request. */
export const NODE_LIMITS = [50, 100, 150] as const;
export type NodeLimit = (typeof NODE_LIMITS)[number];
export const DEFAULT_NODE_LIMIT: NodeLimit = 100;
/** Nodes asked for when expanding one node (its direct neighbours). */
export const EXPANSION_MAX_NODES = 40;
export const MAX_DEPTH = 3;
export const DEFAULT_PATH_QUERY = { maxDepth: 4, limit: 3 } as const;
const HISTORY_LIMIT = 60;
const ANSWER_LIMIT = 300;

export function initialSnapshot(
  focus: string | null,
  path: Pick<PathQuery, "from" | "to"> | null = null,
): ExplorerSnapshot {
  if (path) {
    return {
      mode: "paths",
      focus,
      depth: 1,
      expansions: [],
      selection: null,
      path: { ...DEFAULT_PATH_QUERY, ...path },
    };
  }
  return {
    mode: focus ? "explore" : "map",
    focus,
    depth: 1,
    expansions: [],
    selection: focus ? { kind: "node", id: focus } : null,
    path: null,
  };
}

function sameSnapshot(a: ExplorerSnapshot, b: ExplorerSnapshot): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export interface History {
  entries: readonly ExplorerSnapshot[];
  index: number;
}

/** Record a new snapshot: forward entries are dropped, repeats ignored, length capped. */
export function pushHistory(history: History, next: ExplorerSnapshot): History {
  const current = history.entries[history.index];
  if (current && sameSnapshot(current, next)) return history;
  const entries = [...history.entries.slice(0, history.index + 1), next].slice(-HISTORY_LIMIT);
  return { entries, index: entries.length - 1 };
}

export function toQuery(filters: ExplorerFilters, withNodeTypes = true): GraphFilterQuery {
  return {
    nodeTypes: withNodeTypes ? filters.nodeTypes : [],
    edgeTypes: filters.edgeTypes,
    evidenceStatuses: filters.evidenceStatuses,
    includeIllustrative: filters.includeIllustrative,
    direction: filters.direction,
  };
}

function filterKey(filters: ExplorerFilters, withNodeTypes = true): string {
  return JSON.stringify([
    withNodeTypes ? [...filters.nodeTypes].sort() : [],
    [...filters.edgeTypes].sort(),
    [...filters.evidenceStatuses].sort(),
    filters.includeIllustrative,
    filters.direction,
  ]);
}

export function isFiltered(filters: ExplorerFilters): boolean {
  return filterKey(filters) !== filterKey(DEFAULT_FILTERS);
}

export const neighborhoodKey = (
  id: string,
  depth: number,
  maxNodes: number,
  filters: ExplorerFilters,
) => `n|${id}|${depth}|${maxNodes}|${filterKey(filters)}`;

export const pathKey = (query: PathQuery, filters: ExplorerFilters) =>
  `p|${query.from}|${query.to}|${query.maxDepth}|${query.limit}|${filterKey(filters, false)}`;

/** Server answers, cached by request; a failed answer stays failed until retried. */
function useAnswers() {
  const store = useRef(new Map<string, Answer<unknown>>());
  const [version, setVersion] = useState(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const settle = useCallback((key: string, answer: Answer<unknown>) => {
    store.current.set(key, answer);
    if (mounted.current) setVersion((value) => value + 1);
  }, []);

  const ensure = useCallback(
    (key: string, load: () => Promise<unknown>) => {
      if (store.current.has(key)) return;
      store.current.set(key, { status: "pending" });
      while (store.current.size > ANSWER_LIMIT) {
        const oldest = store.current.keys().next().value;
        if (oldest === undefined || oldest === key) break;
        store.current.delete(oldest);
      }
      load().then(
        (data) => settle(key, { status: "ready", data }),
        (error: unknown) => settle(key, { status: "failed", error }),
      );
    },
    [settle],
  );

  const read = useCallback(
    <T>(key: string | null): Answer<T> | null =>
      key ? ((store.current.get(key) as Answer<T> | undefined) ?? { status: "pending" }) : null,
    [],
  );

  const retry = useCallback((keys: readonly string[]) => {
    for (const key of keys) {
      if (store.current.get(key)?.status === "failed") store.current.delete(key);
    }
    setVersion((value) => value + 1);
  }, []);

  return { ensure, read, retry, version };
}

export interface ExplorerView {
  /** What to draw, or null before the first answer. */
  view: GraphView | null;
  /** The answer for the current focus or path query is still on its way. */
  pending: boolean;
  /** The current focus or path query failed. */
  error: unknown;
  /** The path answer, in path mode. */
  paths: GraphPaths | null;
}

export function useGraphExplorer(initial: ExplorerSnapshot) {
  // Only the first value counts: after that, history is the source of truth.
  const [start] = useState(initial);
  const [history, setHistory] = useState<History>(() => ({ entries: [start], index: 0 }));
  const snapshot = history.entries[history.index] ?? start;
  const [filters, setFilters] = useState<ExplorerFilters>(DEFAULT_FILTERS);
  const [nodeLimit, setNodeLimit] = useState<NodeLimit>(DEFAULT_NODE_LIMIT);
  const answers = useAnswers();
  const { ensure, read } = answers;
  // Bumped by `retry`, so the effect below asks again for answers that failed.
  const [attempt, setAttempt] = useState(0);

  const push = useCallback(
    (update: (current: ExplorerSnapshot) => ExplorerSnapshot) =>
      setHistory((previous) => {
        const current = previous.entries[previous.index] ?? start;
        return pushHistory(previous, update(current));
      }),
    [start],
  );

  // --- Requests ---------------------------------------------------------------------------
  const focusKey =
    snapshot.mode === "explore" && snapshot.focus
      ? neighborhoodKey(snapshot.focus, snapshot.depth, nodeLimit, filters)
      : null;
  const expansionKeys = useMemo(
    () =>
      snapshot.mode === "explore"
        ? snapshot.expansions.map((id) => ({
            id,
            key: neighborhoodKey(id, 1, EXPANSION_MAX_NODES, filters),
          }))
        : [],
    [snapshot.mode, snapshot.expansions, filters],
  );
  const currentPathKey =
    snapshot.mode === "paths" && snapshot.path ? pathKey(snapshot.path, filters) : null;

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` re-runs the requests after a retry.
  useEffect(() => {
    if (focusKey && snapshot.focus) {
      const focus = snapshot.focus;
      ensure(focusKey, () =>
        graphApi.neighborhood(focus, snapshot.depth, nodeLimit, toQuery(filters)),
      );
    }
    for (const { id, key } of expansionKeys) {
      ensure(key, () => graphApi.neighborhood(id, 1, EXPANSION_MAX_NODES, toQuery(filters)));
    }
    if (currentPathKey && snapshot.path) {
      const { from, to, maxDepth, limit } = snapshot.path;
      ensure(currentPathKey, () =>
        graphApi.paths(from, to, maxDepth, limit, toQuery(filters, false)),
      );
    }
  }, [
    ensure,
    focusKey,
    expansionKeys,
    currentPathKey,
    snapshot.focus,
    snapshot.depth,
    snapshot.path,
    nodeLimit,
    filters,
    attempt,
  ]);

  // --- The derived view -------------------------------------------------------------------
  const lastView = useRef<GraphView | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `answers.version` marks new answers in the store.
  const derived = useMemo<ExplorerView>(() => {
    if (snapshot.mode === "paths") {
      const answer = read<GraphPaths>(currentPathKey);
      if (answer?.status === "ready") {
        return {
          view: buildPathView(answer.data),
          pending: false,
          error: null,
          paths: answer.data,
        };
      }
      return {
        view: null,
        pending: answer?.status === "pending",
        error: answer?.status === "failed" ? answer.error : null,
        paths: null,
      };
    }
    const focusAnswer = read<GraphNeighborhood>(focusKey);
    if (!focusAnswer) return { view: null, pending: false, error: null, paths: null };
    if (focusAnswer.status === "ready") {
      const view = buildView(
        focusAnswer.data,
        expansionKeys.map(({ id, key }) => ({
          id,
          answer: read<GraphNeighborhood>(key) ?? { status: "pending" },
        })),
        nodeLimit,
      );
      return { view, pending: false, error: null, paths: null };
    }
    // While the new focus loads, keep the previous picture on screen.
    return {
      view: lastView.current,
      pending: focusAnswer.status === "pending",
      error: focusAnswer.status === "failed" ? focusAnswer.error : null,
      paths: null,
    };
  }, [snapshot.mode, focusKey, currentPathKey, expansionKeys, nodeLimit, read, answers.version]);
  useEffect(() => {
    if (derived.view && snapshot.mode === "explore") lastView.current = derived.view;
  }, [derived.view, snapshot.mode]);

  // --- Actions ----------------------------------------------------------------------------
  const focusOn = useCallback(
    (id: string) =>
      push((current) => ({
        ...current,
        mode: "explore",
        focus: id,
        expansions: [],
        selection: { kind: "node", id },
        path: null,
      })),
    [push],
  );

  const select = useCallback(
    (selection: Selection | null) => push((current) => ({ ...current, selection })),
    [push],
  );

  const expand = useCallback(
    (id: string) =>
      push((current) =>
        current.mode !== "explore" || id === current.focus || current.expansions.includes(id)
          ? { ...current, selection: { kind: "node", id } }
          : {
              ...current,
              expansions: [...current.expansions, id],
              selection: { kind: "node", id },
            },
      ),
    [push],
  );

  /** Remove an expansion, and any made from nodes that only it had brought into view. */
  const collapse = useCallback(
    (id: string) =>
      push((current) => {
        const remaining = current.expansions.filter((item) => item !== id);
        const focusAnswer = read<GraphNeighborhood>(
          current.focus ? neighborhoodKey(current.focus, current.depth, nodeLimit, filters) : null,
        );
        let expansions = remaining;
        if (focusAnswer?.status === "ready") {
          const pruned = buildView(
            focusAnswer.data,
            remaining.map((item) => ({
              id: item,
              answer: read<GraphNeighborhood>(
                neighborhoodKey(item, 1, EXPANSION_MAX_NODES, filters),
              ) ?? { status: "pending" },
            })),
            nodeLimit,
          );
          const kept = new Set(
            pruned.expansions.filter((item) => item.status !== "skipped").map((item) => item.id),
          );
          expansions = remaining.filter((item) => kept.has(item));
        }
        return { ...current, expansions, selection: { kind: "node", id } };
      }),
    [push, read, nodeLimit, filters],
  );

  const setDepth = useCallback(
    (depth: number) =>
      push((current) => ({ ...current, depth: Math.min(MAX_DEPTH, Math.max(1, depth)) })),
    [push],
  );

  const reset = useCallback(
    () =>
      push((current) => ({
        ...current,
        depth: 1,
        expansions: [],
        selection: current.focus ? { kind: "node", id: current.focus } : null,
      })),
    [push],
  );

  const openMap = useCallback(
    () => push((current) => ({ ...current, mode: "map", selection: null })),
    [push],
  );

  const openPaths = useCallback(
    (query: PathQuery | null) =>
      push((current) => ({ ...current, mode: "paths", path: query, selection: null })),
    [push],
  );

  const back = useCallback(
    () => setHistory((previous) => ({ ...previous, index: Math.max(0, previous.index - 1) })),
    [],
  );
  const forward = useCallback(
    () =>
      setHistory((previous) => ({
        ...previous,
        index: Math.min(previous.entries.length - 1, previous.index + 1),
      })),
    [],
  );

  const forget = answers.retry;
  const retry = useCallback(() => {
    forget([
      ...(focusKey ? [focusKey] : []),
      ...expansionKeys.map((item) => item.key),
      ...(currentPathKey ? [currentPathKey] : []),
    ]);
    setAttempt((value) => value + 1);
  }, [forget, focusKey, expansionKeys, currentPathKey]);

  return {
    snapshot,
    ...derived,
    filters,
    setFilters,
    resetFilters: useCallback(() => setFilters(DEFAULT_FILTERS), []),
    nodeLimit,
    setNodeLimit,
    focusOn,
    select,
    expand,
    collapse,
    setDepth,
    reset,
    openMap,
    openPaths,
    back,
    forward,
    canGoBack: history.index > 0,
    canGoForward: history.index < history.entries.length - 1,
    retry,
  };
}

export type GraphExplorer = ReturnType<typeof useGraphExplorer>;
