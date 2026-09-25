/**
 * The 3D Financial Universe: RUMIN's knowledge graph in three dimensions.
 *
 * It is a view over the same read-only graph API as the 2D explorer, with the same
 * exploration state (`useGraphExplorer`: focus, depth, expansions, selection, paths,
 * filters, history) and the same panels:
 *
 * - **Universe**: the whole current build, when it is small enough to draw at once
 *   (`useWholeGraph`); a larger build starts from a node instead.
 * - **Neighbourhood**: a focus and its neighbours, grown one expansion at a time.
 * - **Paths**: the shortest paths between two nodes.
 * - A **scenario overlay** on any of them: what a stored execution changed, simulated,
 *   propagated, cited and left out (`?execution=<id>`).
 *
 * The list view is the canvas's twin and its fallback: without WebGL, after a lost context,
 * or by choice. Nothing here computes a financial figure; the overlay's figures are the
 * stored execution's.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { Command, Notice } from "@/features/data/DataNature";
import { EdgePanel } from "@/features/graph/EdgePanel";
import { NATURE_ENCODING, typeFromKey, typeLabel } from "@/features/graph/encoding";
import { GraphFilters } from "@/features/graph/GraphFilters";
import { GraphSearch } from "@/features/graph/GraphSearch";
import { GraphTable } from "@/features/graph/GraphTable";
import { NodePanel } from "@/features/graph/NodePanel";
import { PathFinder, type PickedNode } from "@/features/graph/PathFinder";
import {
  type ExplorerSnapshot,
  type GraphExplorer,
  initialSnapshot,
  isFiltered,
  MAX_DEPTH,
  NODE_LIMITS,
  type NodeLimit,
  type Selection,
  useGraphExplorer,
} from "@/features/graph/useGraphExplorer";
import { ViewNotices } from "@/features/graph/ViewNotices";
import type { GraphView } from "@/features/graph/view";
import { overlayNodeKeys } from "@/features/universe/overlay";
import type { SceneOverlay } from "@/features/universe/scene";
import {
  type RenderStats,
  type Unavailable,
  UniverseCanvas,
  type UniverseCanvasHandle,
} from "@/features/universe/UniverseCanvas";
import {
  OverlayError,
  OverlayLoading,
  OverlayPanel,
  OverlayPicker,
  UniverseLegend,
} from "@/features/universe/UniversePanels";
import { applyFilters, universeView } from "@/features/universe/universeView";
import {
  UNIVERSE_BUDGET,
  useScenarioOverlay,
  useWholeGraph,
} from "@/features/universe/useUniverseData";
import { useApiResource } from "@/hooks/useApiResource";
import { formatCount, plural } from "@/lib/format";
import { graphApi } from "@/services/api";
import type { GraphNodeType, GraphOverview, GraphTypes } from "@/types/api";
import styles from "./UniverseSpacePage.module.css";

type Stage = "3d" | "list";
const STAGE_KEY = "rumin.universe.stage";

function readStage(): Stage {
  try {
    return window.localStorage.getItem(STAGE_KEY) === "list" ? "list" : "3d";
  } catch {
    return "3d";
  }
}

function writeStage(stage: Stage) {
  try {
    window.localStorage.setItem(STAGE_KEY, stage);
  } catch {
    // Not remembered; the choice still applies now.
  }
}

const validKey = (value: string | null) => (value && typeFromKey(value) ? value : null);

function snapshotFromUrl(params: URLSearchParams): ExplorerSnapshot {
  const from = validKey(params.get("from"));
  const to = validKey(params.get("to"));
  if (from && to) return initialSnapshot(null, { from, to });
  return initialSnapshot(validKey(params.get("focus")));
}

const UNAVAILABLE_TEXT: Record<Unavailable, string> = {
  webgl:
    "This browser cannot draw the 3D view (it needs WebGL 2), so the universe is shown as a list.",
  "context-lost":
    "The graphics context was lost (the browser or the device reclaimed it), so the universe is shown as a list.",
  failed: "The 3D view could not start, so the universe is shown as a list.",
};

function ModeSwitch({ explorer }: { explorer: GraphExplorer }) {
  const { snapshot } = explorer;
  return (
    <fieldset className={styles.segmented}>
      <legend className="visually-hidden">What to show</legend>
      <button type="button" aria-pressed={snapshot.mode === "map"} onClick={explorer.openMap}>
        <Icon name="layers" size={14} />
        Universe
      </button>
      <button
        type="button"
        aria-pressed={snapshot.mode === "explore"}
        disabled={!snapshot.focus && !(snapshot.selection?.kind === "node")}
        title={
          snapshot.focus || snapshot.selection?.kind === "node"
            ? undefined
            : "Search for a node or select one first."
        }
        onClick={() => {
          const id =
            snapshot.focus ?? (snapshot.selection?.kind === "node" ? snapshot.selection.id : null);
          if (id) explorer.focusOn(id);
        }}
      >
        <Icon name="graph" size={14} />
        Neighbourhood
      </button>
      <button
        type="button"
        aria-pressed={snapshot.mode === "paths"}
        onClick={() => explorer.openPaths(snapshot.path)}
      >
        <Icon name="arrowRight" size={14} />
        Paths
      </button>
    </fieldset>
  );
}

function StageSwitch({ stage, onChange }: { stage: Stage; onChange: (stage: Stage) => void }) {
  return (
    <fieldset className={styles.segmented}>
      <legend className="visually-hidden">Show as</legend>
      <button type="button" aria-pressed={stage === "3d"} onClick={() => onChange("3d")}>
        <Icon name="graph" size={14} />
        3D
      </button>
      <button type="button" aria-pressed={stage === "list"} onClick={() => onChange("list")}>
        <Icon name="table" size={14} />
        List
      </button>
    </fieldset>
  );
}

function ControlsHelp({ id }: { id: string }) {
  return (
    <details className={styles.help}>
      <summary>
        <Icon name="info" size={14} />
        Moving around
      </summary>
      <div id={id} className={styles.helpBody}>
        <p>
          <strong>Pointer:</strong> drag to turn the universe, right-drag or Shift-drag to move it,
          scroll or pinch to zoom, click a node or a line to inspect it, double-click a node to
          bring it to the centre.
        </p>
        <p>
          <strong>Keyboard</strong> (select the view first): arrow keys move the selection to the
          nearest node in that direction; Enter brings it to the centre; E shows its neighbours and
          C hides them; Shift with an arrow turns the view; + and − zoom; R resets the view; Escape
          clears the selection.
        </p>
        <p>
          Lost? <strong>Reset view</strong> frames everything again, and <strong>Back</strong>{" "}
          returns to what was on screen before.
        </p>
      </div>
    </details>
  );
}

interface Shown {
  view: GraphView | null;
  pending: boolean;
  error: unknown;
}

function Universe({
  overview,
  types,
  initial,
}: {
  overview: GraphOverview;
  types: GraphTypes;
  initial: ExplorerSnapshot;
}) {
  const explorer = useGraphExplorer(initial);
  const { snapshot } = explorer;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const executionId = searchParams.get("execution");
  const whole = useWholeGraph(overview);
  const overlayState = useScenarioOverlay(executionId);
  const [stage, setStageState] = useState<Stage>(readStage);
  const [unavailable, setUnavailable] = useState<Unavailable | null>(null);
  const [pathFrom, setPathFrom] = useState<PickedNode | null>(null);
  const [stats, setStats] = useState<RenderStats | null>(null);
  const canvasRef = useRef<UniverseCanvasHandle>(null);
  const helpId = useId();
  const setStage = (next: Stage) => {
    setStageState(next);
    writeStage(next);
  };
  const shownStage: Stage = unavailable ? "list" : stage;

  // Mirror what is shown in the URL, so a view can be linked to and shared.
  useEffect(() => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams();
        const execution = current.get("execution");
        if (snapshot.mode === "explore" && snapshot.focus) next.set("focus", snapshot.focus);
        if (snapshot.mode === "paths" && snapshot.path) {
          next.set("from", snapshot.path.from);
          next.set("to", snapshot.path.to);
        }
        if (execution) next.set("execution", execution);
        return next;
      },
      { replace: true },
    );
  }, [snapshot.mode, snapshot.focus, snapshot.path, setSearchParams]);

  const setExecution = (id: string | null) =>
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (id) next.set("execution", id);
        else next.delete("execution");
        return next;
      },
      { replace: false },
    );

  // What to draw: the whole build (universe), or the explorer's view.
  const filtered = useMemo(
    () =>
      whole.status === "ready" ? applyFilters(whole.nodes, whole.edges, explorer.filters) : null,
    [whole, explorer.filters],
  );
  const selectedNode = snapshot.selection?.kind === "node" ? snapshot.selection.id : null;
  const shown: Shown = useMemo(() => {
    if (snapshot.mode === "map") {
      if (!filtered) return { view: null, pending: whole.status === "loading", error: null };
      return {
        view: universeView(filtered.nodes, filtered.edges, selectedNode),
        pending: false,
        error: null,
      };
    }
    return { view: explorer.view, pending: explorer.pending, error: explorer.error };
  }, [
    snapshot.mode,
    filtered,
    whole.status,
    selectedNode,
    explorer.view,
    explorer.pending,
    explorer.error,
  ]);
  // While the next view loads, the previous one stays on screen (and the canvas keeps the
  // keyboard focus): the status line says it is loading, not what the old view showed.
  const [held, setHeld] = useState<GraphView | null>(null);
  useEffect(() => {
    if (shown.view) setHeld(shown.view);
  }, [shown.view]);
  const holding = !shown.view && shown.pending && held !== null && !shown.error;
  const view = shown.view ?? (holding ? held : null);

  const nodes = useMemo(() => (view ? [...view.nodes.values()] : []), [view]);
  const edges = useMemo(() => (view ? [...view.edges.values()] : []), [view]);
  const anchors = useMemo(
    () => new Map(nodes.map((node) => [node.id, node.origin] as const)),
    [nodes],
  );

  const overlay = overlayState.status === "ready" ? overlayState.overlay : null;
  const sceneOverlay: SceneOverlay | null = useMemo(
    () => (overlay ? { nodes: overlay.nodes, edges: overlay.edges } : null),
    [overlay],
  );
  const names = useMemo(() => {
    const map = new Map<string, string>();
    if (whole.status === "ready") for (const node of whole.nodes) map.set(node.id, node.name);
    for (const node of nodes) map.set(node.id, node.name);
    return map;
  }, [whole, nodes]);
  const missing = useMemo(() => {
    if (!overlay) return 0;
    const present = new Set(nodes.map((node) => node.id));
    return overlayNodeKeys(overlay).filter((key) => !present.has(key)).length;
  }, [overlay, nodes]);

  const busyIds = useMemo(
    () =>
      new Set(
        explorer.view?.expansions
          .filter((item) => item.status === "pending")
          .map((item) => item.id),
      ),
    [explorer.view],
  );
  const expandedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!explorer.view || snapshot.mode !== "explore") return ids;
    ids.add(explorer.view.focus);
    for (const item of explorer.view.expansions) if (item.status === "applied") ids.add(item.id);
    return ids;
  }, [explorer.view, snapshot.mode]);

  const nodeTypes = useMemo(
    () => overview.type_map.filter((item) => item.count > 0),
    [overview.type_map],
  );
  const edgeCounts = (overview.metrics.edges_by_type ?? {}) as Record<string, number>;
  const select = explorer.select;
  const onSelect = useCallback((next: Selection | null) => select(next), [select]);
  const selection = snapshot.selection;

  // A polite, text-only account of what the canvas shows and what is selected.
  const selectedSummary = (() => {
    if (!selection || !view) return "";
    if (selection.kind === "node") {
      const node = view.nodes.get(selection.id);
      return node
        ? `Selected: ${node.name}, ${typeLabel(node.type).toLowerCase()}, ${NATURE_ENCODING[node.nature].short.toLowerCase()}, ${plural(node.shownDegree, "relationship")} shown.`
        : "";
    }
    const edge = view.edges.get(selection.id);
    if (!edge) return "";
    const name = (id: string) => view.nodes.get(id)?.name ?? id;
    return `Selected: ${name(edge.source)} ${edge.label} ${name(edge.target)}.`;
  })();
  const statusText = (() => {
    if (!view) return "";
    if (holding) return "Loading the next view; the previous one is shown until it arrives";
    const counts = `${plural(view.nodes.size, "node")} · ${plural(view.edges.size, "relationship")}`;
    if (snapshot.mode === "map")
      return `${counts}: the whole build${isFiltered(explorer.filters) ? ", filtered" : ""}`;
    if (snapshot.mode === "paths") return `${counts} on the paths found`;
    const centre = view.nodes.get(view.focus)?.name ?? "the focus";
    return `${counts} within ${plural(snapshot.depth, "hop")} of ${centre}${
      expandedIds.size > 1 ? `, plus ${plural(expandedIds.size - 1, "expanded node")}` : ""
    }`;
  })();

  const askAnalyst = (name: string) =>
    navigate("/analyst", { state: { draftQuestion: `What does RUMIN know about ${name}?` } });

  const universeActions = (id: string) => {
    const node = view?.nodes.get(id);
    if (!node) return null;
    const intelligence = node.type === "company" || node.type === "industry";
    return (
      <div className={styles.universeActions}>
        {shownStage === "3d" && (
          <Button size="sm" variant="ghost" onClick={() => canvasRef.current?.flyTo(id)}>
            Centre the view on it
          </Button>
        )}
        <Link className={styles.inlineLink} to={`/graph?focus=${encodeURIComponent(id)}`}>
          Open in the 2D explorer
        </Link>
        {intelligence && (
          <Link className={styles.inlineLink} to={`/intelligence/${encodeURIComponent(id)}`}>
            Open in Financial Intelligence
          </Link>
        )}
        <button type="button" className={styles.linkButton} onClick={() => askAnalyst(node.name)}>
          Ask the Analyst about it
        </button>
      </div>
    );
  };

  const details = (() => {
    if (selection?.kind === "node") {
      return (
        <>
          {universeActions(selection.id)}
          <NodePanel
            key={selection.id}
            nodeId={selection.id}
            view={view}
            isFocus={snapshot.mode === "explore" && selection.id === snapshot.focus}
            isExpanded={expandedIds.has(selection.id)}
            busy={busyIds.has(selection.id)}
            actions={{
              onSelect,
              onFocus: explorer.focusOn,
              onExpand: snapshot.mode === "explore" ? explorer.expand : undefined,
              onCollapse: explorer.collapse,
              onFindPath: (node) => {
                setPathFrom(node);
                explorer.openPaths(null);
              },
              onClose: () => select(null),
            }}
          />
        </>
      );
    }
    if (selection?.kind === "edge") {
      return (
        <EdgePanel
          key={selection.id}
          edgeId={selection.id}
          onSelect={onSelect}
          onClose={() => select(null)}
        />
      );
    }
    if (overlayState.status === "loading") return <OverlayLoading />;
    if (overlayState.status === "error") {
      return <OverlayError error={overlayState.error} onRetry={overlayState.retry} />;
    }
    if (overlayState.status === "not-completed") {
      return overlayState.final ? (
        <div className={styles.hint}>
          <p className={styles.hintTitle}>No overlay</p>
          <p>
            The execution of “{overlayState.name}” is {overlayState.state}: it has no results to lay
            over the graph. The Scenario Lab says why.
          </p>
        </div>
      ) : (
        <div className={styles.hint}>
          <p className={styles.hintTitle}>No overlay yet</p>
          <p>
            The execution of “{overlayState.name}” is {overlayState.state}: only a completed
            execution's results can be laid over the graph. It is read again as the server suggests,
            and the overlay appears when it completes.
          </p>
          <p>
            <button type="button" className={styles.linkButton} onClick={overlayState.recheck}>
              Check now
            </button>
          </p>
        </div>
      );
    }
    if (overlay) {
      return (
        <OverlayPanel
          overlay={overlay}
          names={names}
          missing={missing}
          currentBuild={overview.build?.id ?? null}
          onSelect={onSelect}
          onShowAll={snapshot.mode !== "map" && whole.status === "ready" ? explorer.openMap : null}
          onClear={() => setExecution(null)}
        />
      );
    }
    if (snapshot.mode === "paths") {
      return (
        <PathFinder
          key={`${JSON.stringify(snapshot.path)}|${pathFrom?.id ?? ""}`}
          query={snapshot.path}
          initialFrom={snapshot.path ? null : pathFrom}
          answer={explorer.paths}
          pending={explorer.pending}
          error={explorer.error}
          onSubmit={(query) => explorer.openPaths(query)}
          onRetry={explorer.retry}
          onSelect={onSelect}
        />
      );
    }
    return (
      <div className={styles.hint}>
        <p className={styles.hintTitle}>Select a node or a line</p>
        <p>
          A node's panel shows its identifiers, where it comes from and what it is linked to; a
          line's panel shows the evidence behind it and what it does not mean.
        </p>
        <p className={styles.hintNote}>
          {overview.build
            ? `Graph build #${overview.build.id}: ${plural(overview.build.node_count, "node")} and ${plural(overview.build.edge_count, "relationship")}. `
            : ""}
          Every record here is from RUMIN's knowledge graph; the sample companies are fictional.
        </p>
      </div>
    );
  })();

  const stageBody = (() => {
    if (snapshot.mode === "map" && whole.status === "too-large") {
      return (
        <div className={styles.stageMessage}>
          <EmptyState title="The graph is too large to draw at once">
            It holds {formatCount(whole.nodes)} nodes and {formatCount(whole.edges)} relationships;
            the universe draws at most {formatCount(UNIVERSE_BUDGET.nodes)} nodes and{" "}
            {formatCount(UNIVERSE_BUDGET.edges)} relationships at once. Search for a record to start
            from its neighbourhood.
          </EmptyState>
          <GraphSearch onPick={(item) => explorer.focusOn(item.id)} label="Start from" />
        </div>
      );
    }
    if (snapshot.mode === "map" && whole.status === "not-built") {
      return (
        <div className={styles.stageMessage}>
          <EmptyState title="The current build holds no nodes">
            There is nothing to draw yet. Load the reference data and rebuild the graph (
            <Command>python -m app.graph build</Command> in <span className="mono">backend/</span>
            ), then reload this page.
          </EmptyState>
        </div>
      );
    }
    if (snapshot.mode === "map" && whole.status === "error") {
      return (
        <div className={styles.stageMessage}>
          <ErrorState
            error={whole.error}
            title="The universe could not be loaded"
            onRetry={whole.retry}
          />
        </div>
      );
    }
    if (shown.error && snapshot.mode !== "paths") {
      return (
        <div className={styles.stageMessage}>
          <ErrorState
            error={shown.error}
            title="This part of the graph could not be loaded"
            onRetry={explorer.retry}
          />
          <Button size="sm" variant="ghost" onClick={explorer.openMap}>
            Back to the universe
          </Button>
        </div>
      );
    }
    if (!view) {
      if (snapshot.mode === "map" && filtered && filtered.nodes.length === 0) {
        return (
          <div className={styles.stageMessage}>
            <EmptyState title="No records match the filters">
              The build holds {plural(whole.status === "ready" ? whole.nodes.length : 0, "node")},
              but none of them passes the current filters.
            </EmptyState>
            <Button size="sm" variant="secondary" onClick={explorer.resetFilters}>
              Reset filters
            </Button>
          </div>
        );
      }
      if (snapshot.mode === "paths" && !shown.pending) {
        return (
          <div className={styles.stageMessage}>
            <EmptyState title="No paths shown yet">
              Choose two nodes in the panel to see how RUMIN's records connect them.
            </EmptyState>
          </div>
        );
      }
      return (
        <div className={styles.stageMessage}>
          <LoadingState label="Loading the universe…" lines={4} />
        </div>
      );
    }
    if (shownStage === "list") {
      return (
        <GraphTable
          view={view}
          selection={selection}
          onSelect={onSelect}
          hopsLabel={
            snapshot.mode === "paths"
              ? "Position on path"
              : snapshot.mode === "map"
                ? `Hops from ${view.nodes.get(view.focus)?.name ?? "the centre"}`
                : "Hops from centre"
          }
        />
      );
    }
    return (
      <UniverseCanvas
        ref={canvasRef}
        nodes={nodes}
        edges={edges}
        anchors={anchors}
        focus={snapshot.mode === "explore" ? snapshot.focus : null}
        selection={selection}
        overlay={sceneOverlay}
        label={`3D knowledge graph: ${statusText}.`}
        describedBy={helpId}
        onSelect={onSelect}
        onActivate={(id) =>
          snapshot.mode === "explore" ? explorer.focusOn(id) : canvasRef.current?.flyTo(id)
        }
        onExpand={(id) =>
          snapshot.mode === "explore" ? explorer.expand(id) : explorer.focusOn(id)
        }
        onCollapse={explorer.collapse}
        onUnavailable={setUnavailable}
        onStats={setStats}
      />
    );
  })();

  const presentTypes = useMemo(
    () => [...new Set(nodes.map((node) => node.type))] as GraphNodeType[],
    [nodes],
  );

  return (
    <div className={styles.universe}>
      <div className={styles.controls}>
        <GraphSearch
          onPick={(item) => {
            if (snapshot.mode === "map" && view?.nodes.has(item.id)) {
              select({ kind: "node", id: item.id });
              canvasRef.current?.flyTo(item.id);
            } else {
              explorer.focusOn(item.id);
            }
          }}
        />
        <GraphFilters
          filters={explorer.filters}
          onChange={explorer.setFilters}
          nodeTypes={nodeTypes}
          edgeTypes={types.edge_types}
          edgeCounts={edgeCounts}
          showNodeTypes={snapshot.mode !== "paths"}
        />
        <OverlayPicker executionId={executionId} onChange={setExecution} />
      </div>
      {unavailable && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {UNAVAILABLE_TEXT[unavailable]}
          {unavailable === "context-lost" && (
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => setUnavailable(null)}
            >
              Try the 3D view again
            </button>
          )}
        </p>
      )}
      {whole.status === "ready" && whole.truncated && snapshot.mode === "map" && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          The build grew past what the universe draws at once while it was read: only part of it is
          shown. Search for a record to explore from it.
        </p>
      )}
      <div className={styles.workspace}>
        <div className={styles.stage}>
          <div className={styles.toolbar}>
            <ModeSwitch explorer={explorer} />
            <div className={styles.history}>
              <button
                type="button"
                className={styles.iconButton}
                onClick={explorer.back}
                disabled={!explorer.canGoBack}
                aria-label="Back to the previous view"
                title="Back"
              >
                <Icon name="arrowLeft" size={14} />
              </button>
              <button
                type="button"
                className={styles.iconButton}
                onClick={explorer.forward}
                disabled={!explorer.canGoForward}
                aria-label="Forward to the next view"
                title="Forward"
              >
                <Icon name="arrowRight" size={14} />
              </button>
            </div>
            {snapshot.mode === "explore" && (
              <>
                <label className={styles.select}>
                  Depth
                  <select
                    value={snapshot.depth}
                    onChange={(event) => explorer.setDepth(Number(event.target.value))}
                  >
                    {Array.from({ length: MAX_DEPTH }, (_, index) => index + 1).map((depth) => (
                      <option key={depth} value={depth}>
                        {depth} {depth === 1 ? "hop" : "hops"}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={styles.select}>
                  Show at most
                  <select
                    value={explorer.nodeLimit}
                    onChange={(event) =>
                      explorer.setNodeLimit(Number(event.target.value) as NodeLimit)
                    }
                  >
                    {NODE_LIMITS.map((limit) => (
                      <option key={limit} value={limit}>
                        {limit} nodes
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <div className={styles.toolbarEnd}>
              {shownStage === "3d" && view && (
                <button
                  type="button"
                  className={styles.linkButton}
                  title="Frame everything again (R). Back returns to earlier views."
                  onClick={() => canvasRef.current?.resetView()}
                >
                  Reset view
                </button>
              )}
              <StageSwitch
                stage={shownStage}
                onChange={(next) => {
                  if (next === "3d") setUnavailable(null);
                  setStage(next);
                }}
              />
            </div>
          </div>
          {view && (
            <p className={styles.status} aria-live="polite">
              {statusText}
              {shown.pending && <span className={styles.loading}> · Loading…</span>}
              {overlay && ` · overlay: ${overlay.scenarioName}`}
            </p>
          )}
          {snapshot.mode === "map" &&
            whole.status === "ready" &&
            filtered &&
            filtered.nodes.length > 0 &&
            isFiltered(explorer.filters) && (
              <p className={styles.filterNotice} role="status">
                <Icon name="info" size={14} />
                Filters are on: {formatCount(filtered.nodes.length)} of{" "}
                {plural(whole.nodes.length, "node")} and {formatCount(filtered.edges.length)} of{" "}
                {plural(whole.edges.length, "relationship")} shown.
              </p>
            )}
          <ViewNotices explorer={explorer} />
          <p className="visually-hidden" aria-live="polite">
            {selectedSummary}
          </p>
          <div className={styles.stageBody}>{stageBody}</div>
          <ControlsHelp id={helpId} />
          <UniverseLegend types={presentTypes} />
        </div>
        <aside
          className={styles.details}
          aria-label={
            selection
              ? selection.kind === "node"
                ? "Selected node"
                : "Selected relationship"
              : overlay
                ? "Scenario overlay"
                : snapshot.mode === "paths"
                  ? "Path finder"
                  : "Details"
          }
        >
          {details}
          {stats && shownStage === "3d" && (
            <p className={styles.stats}>
              Rendered on demand · {stats.calls} draw calls · {formatCount(stats.triangles)}{" "}
              triangles · last frame {stats.frameMs.toFixed(1)} ms
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

export function UniverseSpacePage() {
  const overview = useApiResource("graph-overview", () => graphApi.overview());
  const types = useApiResource("graph-types", () => graphApi.types());
  const [searchParams] = useSearchParams();
  const [initial] = useState(() => snapshotFromUrl(searchParams));
  const build = overview.data?.build;
  const explorerLink = (() => {
    const query = new URLSearchParams();
    for (const key of ["focus", "from", "to"]) {
      const value = searchParams.get(key);
      if (value) query.set(key, value);
    }
    const text = query.toString();
    return text ? `/graph?${text}` : "/graph";
  })();

  return (
    <div className={styles.page}>
      <PageHeader
        compact
        eyebrow="Financial Universe · 3D"
        title="The knowledge graph in three dimensions"
        meta={
          overview.data && (
            <>
              {build && (
                <Badge tone="outline">
                  Build #{build.id} · {plural(build.node_count, "node")} ·{" "}
                  {plural(build.edge_count, "edge")}
                </Badge>
              )}
              {overview.data.freshness.status === "current" && (
                <Badge tone="good" title={overview.data.freshness.message}>
                  Up to date with its sources
                </Badge>
              )}
              <Badge tone="outline" title="The graph connects the records RUMIN holds.">
                Not a map of the whole economy
              </Badge>
              <Link className={styles.headerLink} to="/universe">
                The 2D network
              </Link>
              <Link className={styles.headerLink} to={explorerLink}>
                Open in the 2D explorer
              </Link>
            </>
          )
        }
      />
      {(overview.status === "loading" || types.status === "loading") && (
        <LoadingState label="Loading the knowledge graph…" lines={5} />
      )}
      {overview.status === "error" && (
        <ErrorState
          error={overview.error}
          title="The knowledge graph could not be loaded"
          onRetry={overview.reload}
        />
      )}
      {types.status === "error" && overview.status !== "error" && (
        <ErrorState
          error={types.error}
          title="The graph's vocabulary could not be loaded"
          onRetry={types.reload}
        />
      )}
      {overview.data && types.data && !overview.data.build && (
        <EmptyState title="The knowledge graph has not been built yet">
          <p>
            Build it from the stored reference data and series catalogue, in{" "}
            <span className="mono">backend/</span>:
          </p>
          <p>
            <Command>python -m app.graph build</Command>
          </p>
          <p>Then reload this page. (Or run make graph from the repository root.)</p>
        </EmptyState>
      )}
      {overview.data && types.data && overview.data.build && (
        <>
          {overview.data.freshness.status === "stale" && (
            <Notice tone="warning" title="The graph is older than its sources">
              {overview.data.freshness.message} Rebuild it with{" "}
              <Command>python -m app.graph build</Command> in <span className="mono">backend/</span>
              .
            </Notice>
          )}
          <Universe overview={overview.data} types={types.data} initial={initial} />
        </>
      )}
    </div>
  );
}
