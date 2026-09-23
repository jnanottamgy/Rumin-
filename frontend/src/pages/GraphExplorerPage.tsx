/**
 * The Knowledge Graph explorer. It starts on an aggregate map of the graph; from there the
 * reader searches or picks a node, explores its neighbourhood on a radial layout, expands
 * neighbours step by step, filters by type and evidence, inspects the evidence behind any
 * line, and finds paths between two nodes.
 *
 * Everything drawn comes from the read-only graph API; the page only arranges it. The
 * graph is built from the command line (`python -m app.graph build`).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { Command, Notice } from "@/features/data/DataNature";
import { EdgePanel } from "@/features/graph/EdgePanel";
import { typeFromKey } from "@/features/graph/encoding";
import { GraphCanvas, type GraphCanvasHandle } from "@/features/graph/GraphCanvas";
import { GraphFilters } from "@/features/graph/GraphFilters";
import { GraphLegend } from "@/features/graph/GraphLegend";
import { GraphSearch } from "@/features/graph/GraphSearch";
import { GraphTable } from "@/features/graph/GraphTable";
import { columnLayout, radialLayout } from "@/features/graph/layout";
import { NodePanel } from "@/features/graph/NodePanel";
import { OverviewPanel, TypeNodeList } from "@/features/graph/OverviewPanel";
import { PathFinder, type PickedNode } from "@/features/graph/PathFinder";
import { TypeMap } from "@/features/graph/TypeMap";
import {
  type ExplorerSnapshot,
  type GraphExplorer,
  initialSnapshot,
  isFiltered,
  MAX_DEPTH,
  NODE_LIMITS,
  type NodeLimit,
  useGraphExplorer,
} from "@/features/graph/useGraphExplorer";
import { useApiResource } from "@/hooks/useApiResource";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { formatCount, plural } from "@/lib/format";
import { graphApi } from "@/services/api";
import type { GraphNodeType, GraphOverview, GraphTypes } from "@/types/api";
import styles from "./GraphExplorerPage.module.css";

type StageView = "graph" | "table";

const validKey = (value: string | null) => (value && typeFromKey(value) ? value : null);

/** The first snapshot, from the URL: `?focus=<key>` or `?from=<key>&to=<key>`. */
function snapshotFromUrl(params: URLSearchParams): ExplorerSnapshot {
  const from = validKey(params.get("from"));
  const to = validKey(params.get("to"));
  if (from && to) return initialSnapshot(null, { from, to });
  return initialSnapshot(validKey(params.get("focus")));
}

function ModeSwitch({ explorer }: { explorer: GraphExplorer }) {
  const { snapshot } = explorer;
  return (
    <fieldset className={styles.segmented}>
      <legend className="visually-hidden">Mode</legend>
      <button type="button" aria-pressed={snapshot.mode === "map"} onClick={explorer.openMap}>
        <Icon name="grid" size={14} />
        Map
      </button>
      <button
        type="button"
        aria-pressed={snapshot.mode === "explore"}
        disabled={!snapshot.focus}
        title={snapshot.focus ? undefined : "Search for a node or pick one from the map first."}
        onClick={() => snapshot.focus && explorer.focusOn(snapshot.focus)}
      >
        <Icon name="graph" size={14} />
        Explore
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

function StageSwitch({ view, onChange }: { view: StageView; onChange: (view: StageView) => void }) {
  return (
    <fieldset className={styles.segmented}>
      <legend className="visually-hidden">Show as</legend>
      {(["graph", "table"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={view === option}
          onClick={() => onChange(option)}
        >
          <Icon name={option === "graph" ? "graph" : "table"} size={14} />
          {option === "graph" ? "Graph" : "Table"}
        </button>
      ))}
    </fieldset>
  );
}

function ViewNotices({ explorer }: { explorer: GraphExplorer }) {
  const { view } = explorer;
  if (!view || explorer.snapshot.mode !== "explore") return null;
  const failed = view.expansions.filter((item) => item.status === "failed");
  const skipped = view.expansions.filter((item) => item.status === "skipped");
  const truncatedTypes = Object.entries(view.unexploredByType)
    .map(([type, count]) => `${formatCount(count)} ${type.replace("_", " ")}`)
    .join(", ");
  const centre = view.nodes.get(view.focus)?.name ?? "the focus";
  return (
    <div className={styles.notices}>
      {view.edges.size === 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {isFiltered(explorer.filters)
            ? `No relationships around ${centre} match the current filters.`
            : `${centre} has no recorded relationships in the graph.`}
          {isFiltered(explorer.filters) && (
            <button type="button" className={styles.linkButton} onClick={explorer.resetFilters}>
              Reset filters
            </button>
          )}
        </p>
      )}
      {view.focusTruncated && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          The node limit cut this neighbourhood short
          {truncatedTypes ? ` (left out: ${truncatedTypes})` : ""}. Raise the limit, lower the depth
          or add filters.
        </p>
      )}
      {view.hiddenByLimit > 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {plural(view.hiddenByLimit, "node")} not drawn: the view is capped at {explorer.nodeLimit}{" "}
          nodes.
        </p>
      )}
      {skipped.length > 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {plural(skipped.length, "expanded node")} hidden by the current filters.
        </p>
      )}
      {failed.length > 0 && (
        <p className={styles.notice} data-tone="critical" role="alert">
          <Icon name="alert" size={14} />
          {failed.length === 1 ? "An expansion" : `${failed.length} expansions`} could not be
          loaded.
          <button type="button" className={styles.linkButton} onClick={explorer.retry}>
            Try again
          </button>
        </p>
      )}
    </div>
  );
}

function Explorer({
  overview,
  types,
  initial,
}: {
  overview: GraphOverview;
  types: GraphTypes;
  initial: ExplorerSnapshot;
}) {
  const explorer = useGraphExplorer(initial);
  const { snapshot, view } = explorer;
  const portrait = useMediaQuery("(max-width: 40rem)");
  const [stage, setStage] = useState<StageView>("graph");
  const [pickedType, setPickedType] = useState<GraphNodeType | null>(null);
  const [pathFrom, setPathFrom] = useState<PickedNode | null>(null);
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const [, setSearchParams] = useSearchParams();

  // Mirror what is shown in the URL, so a view can be linked to and shared.
  useEffect(() => {
    setSearchParams(
      () => {
        const next = new URLSearchParams();
        if (snapshot.mode === "explore" && snapshot.focus) next.set("focus", snapshot.focus);
        if (snapshot.mode === "paths" && snapshot.path) {
          next.set("from", snapshot.path.from);
          next.set("to", snapshot.path.to);
        }
        return next;
      },
      { replace: true },
    );
  }, [snapshot.mode, snapshot.focus, snapshot.path, setSearchParams]);

  const layout = useMemo(
    () => (view ? (snapshot.mode === "paths" ? columnLayout(view) : radialLayout(view)) : null),
    [view, snapshot.mode],
  );

  const busyIds = useMemo(
    () =>
      new Set(view?.expansions.filter((item) => item.status === "pending").map((item) => item.id)),
    [view],
  );
  const expandedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!view || snapshot.mode !== "explore") return ids;
    ids.add(view.focus);
    for (const item of view.expansions) if (item.status === "applied") ids.add(item.id);
    return ids;
  }, [view, snapshot.mode]);

  const nodeTypes = useMemo(
    () => overview.type_map.filter((item) => item.count > 0),
    [overview.type_map],
  );
  const edgeCounts = (overview.metrics.edges_by_type ?? {}) as Record<string, number>;

  const select = explorer.select;
  const onSelect = useCallback(
    (selection: Parameters<typeof select>[0]) => select(selection),
    [select],
  );

  const focusNode = view && snapshot.focus ? view.nodes.get(snapshot.focus) : undefined;
  const selection = snapshot.selection;

  const statusText = (() => {
    if (!view) return "";
    const counts = `${plural(view.nodes.size, "node")} · ${plural(view.edges.size, "relationship")}`;
    if (snapshot.mode === "paths") return `${counts} on the paths found`;
    return `${counts} within ${plural(snapshot.depth, "hop")} of ${focusNode?.name ?? "the focus"}${
      expandedIds.size > 1 ? `, plus ${plural(expandedIds.size - 1, "expanded node")}` : ""
    }`;
  })();

  const details = (() => {
    if (snapshot.mode === "map") {
      return pickedType ? (
        <TypeNodeList
          type={pickedType}
          onFocus={(id) => explorer.focusOn(id)}
          onClose={() => setPickedType(null)}
        />
      ) : (
        <OverviewPanel overview={overview} onFocus={(id) => explorer.focusOn(id)} />
      );
    }
    if (explorer.error && snapshot.mode === "explore") {
      return (
        <div className={styles.hint}>
          <p className={styles.hintTitle}>Nothing to show here</p>
          <p>The node could not be loaded; see the message beside this panel.</p>
        </div>
      );
    }
    if (selection?.kind === "node") {
      return (
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
          A node's panel shows its identifiers, where it comes from and what it is linked to. A
          line's panel shows the evidence behind it and what it does not mean.
        </p>
        <p className={styles.hintNote}>
          Double-click a node, or select it and press <kbd>E</kbd>, to show its neighbours. The
          distance from the centre is the number of hops from{" "}
          {focusNode ? <strong>{focusNode.name}</strong> : "the focus"}.
        </p>
      </div>
    );
  })();

  const stageBody = (() => {
    if (snapshot.mode === "map") {
      return (
        <div className={styles.mapStage}>
          <TypeMap
            nodes={overview.type_map}
            links={overview.type_links}
            selectedType={pickedType}
            onPickType={setPickedType}
          />
        </div>
      );
    }
    if (explorer.error && !(snapshot.mode === "paths")) {
      return (
        <div className={styles.stageMessage}>
          <ErrorState
            error={explorer.error}
            title="This part of the graph could not be loaded"
            onRetry={explorer.retry}
          />
          <Button size="sm" variant="ghost" onClick={explorer.openMap}>
            Back to the map
          </Button>
        </div>
      );
    }
    if (!view || !layout) {
      if (snapshot.mode === "paths" && !explorer.pending) {
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
          <LoadingState label="Loading the graph…" lines={4} />
        </div>
      );
    }
    if (stage === "table") {
      return (
        <GraphTable
          view={view}
          selection={selection}
          onSelect={onSelect}
          hopsLabel={snapshot.mode === "paths" ? "Position on path" : "Hops from centre"}
        />
      );
    }
    return (
      <>
        <GraphCanvas
          ref={canvasRef}
          view={view}
          layout={layout}
          selection={selection}
          busyIds={busyIds}
          expandedIds={expandedIds}
          targetId={snapshot.mode === "paths" ? (snapshot.path?.to ?? null) : null}
          onSelect={onSelect}
          onExpand={snapshot.mode === "explore" ? explorer.expand : undefined}
          labels={portrait ? "focus" : "all"}
          ariaLabel={`Knowledge graph: ${statusText}. Tab moves between nodes, Enter selects, E shows a node's neighbours, Escape clears the selection. The table view lists the same data.`}
          className={styles.canvas}
        />
        <GraphLegend view={view} radial={layout.kind === "radial"} compact={portrait} />
      </>
    );
  })();

  return (
    <div className={styles.explorer}>
      <div className={styles.controls}>
        <GraphSearch onPick={(item) => explorer.focusOn(item.id)} />
        {snapshot.mode !== "map" && (
          <GraphFilters
            filters={explorer.filters}
            onChange={explorer.setFilters}
            nodeTypes={nodeTypes}
            edgeTypes={types.edge_types}
            edgeCounts={edgeCounts}
            showNodeTypes={snapshot.mode === "explore"}
          />
        )}
      </div>
      <div
        className={styles.workspace}
        data-has-details={
          snapshot.mode === "map" || Boolean(selection) || snapshot.mode === "paths"
        }
      >
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
                <button
                  type="button"
                  className={styles.linkButton}
                  onClick={() => {
                    explorer.reset();
                    canvasRef.current?.fitView();
                  }}
                >
                  Reset view
                </button>
              </>
            )}
            {snapshot.mode !== "map" && (
              <div className={styles.toolbarEnd}>
                <StageSwitch view={stage} onChange={setStage} />
              </div>
            )}
          </div>
          {snapshot.mode !== "map" && view && (
            <p className={styles.status} aria-live="polite">
              {statusText}
              {explorer.pending && <span className={styles.loading}> · Loading…</span>}
            </p>
          )}
          <ViewNotices explorer={explorer} />
          <div className={styles.stageBody}>{stageBody}</div>
        </div>
        <aside
          className={styles.details}
          aria-label={
            snapshot.mode === "map"
              ? "Graph summary"
              : selection
                ? selection.kind === "node"
                  ? "Selected node"
                  : "Selected relationship"
                : snapshot.mode === "paths"
                  ? "Path finder"
                  : "Details"
          }
        >
          {details}
        </aside>
      </div>
    </div>
  );
}

export function GraphExplorerPage() {
  const overview = useApiResource("graph-overview", () => graphApi.overview());
  const types = useApiResource("graph-types", () => graphApi.types());
  const [searchParams] = useSearchParams();
  const [initial] = useState(() => snapshotFromUrl(searchParams));
  const build = overview.data?.build;

  return (
    <div className={styles.page}>
      <PageHeader
        compact
        eyebrow="Knowledge graph"
        title="How RUMIN's records connect"
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
            </>
          )
        }
      />
      {(overview.status === "loading" || types.status === "loading") && (
        <LoadingState label="Loading the knowledge graph…" lines={5} />
      )}
      {overview.status === "error" && (
        <ErrorState error={overview.error} onRetry={overview.reload} />
      )}
      {types.status === "error" && overview.status !== "error" && (
        <ErrorState error={types.error} onRetry={types.reload} />
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
          <Explorer overview={overview.data} types={types.data} initial={initial} />
        </>
      )}
    </div>
  );
}
