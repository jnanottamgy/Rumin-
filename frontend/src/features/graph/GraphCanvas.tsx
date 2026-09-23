/**
 * The knowledge-graph canvas: draws a derived view (see `view.ts`) at the positions a
 * layout gives it, with pan, zoom, selection, hover and keyboard access.
 *
 * It holds no financial logic and no relationships of its own — every node and line is
 * one the API returned. Selecting a node highlights it and its lines and dims the rest;
 * selecting a line highlights it and its two ends. The table view is its accessible twin.
 */
import {
  type CSSProperties,
  type KeyboardEvent,
  memo,
  type Ref,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTheme } from "@/app/theme";
import { edgeGeometry } from "@/features/network/geometry";
import { type Transform, toScreen, usePanZoom } from "@/features/network/panZoom";
import { useElementSize } from "@/hooks/useElementSize";
import { cx } from "@/lib/cx";
import { plural } from "@/lib/format";
import type { GraphEdgeSummary } from "@/types/api";
import {
  DATA_STATUS_LABEL,
  EVIDENCE_ENCODING,
  edgeWidth,
  isHollow,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
  nodeRadius,
  typeLabel,
} from "./encoding";
import styles from "./GraphCanvas.module.css";
import { GlyphMark } from "./GraphGlyph";
import type { Bounds, GraphLayout, Point } from "./layout";
import { useAnimatedPositions } from "./useAnimatedPositions";
import type { Selection } from "./useGraphExplorer";
import { type GraphView, incidentTo, type ViewNode } from "./view";

export interface GraphCanvasHandle {
  fitView: () => void;
  centerOn: (id: string) => void;
}

export interface GraphCanvasProps {
  view: GraphView;
  layout: GraphLayout;
  selection: Selection | null;
  /** Nodes whose expansion is loading. */
  busyIds?: ReadonlySet<string>;
  /** Nodes whose neighbours are shown (the focus and expanded nodes). */
  expandedIds?: ReadonlySet<string>;
  /** Path mode: the target, labelled like the focus. */
  targetId?: string | null;
  onSelect: (selection: Selection | null) => void;
  onExpand?: (id: string) => void;
  /** "all": every label when there is room; "focus": only what is in focus (phones). */
  labels?: "all" | "focus";
  ariaLabel: string;
  className?: string;
  ref?: Ref<GraphCanvasHandle>;
}

type NodeState = "selected" | "neighbor" | "dimmed" | "default";
type EdgeState = "selected" | "active" | "hover" | "dimmed" | "default";

/** Beyond this many nodes, only nodes near the focus or in focus are labelled. */
const LABEL_ALL_LIMIT = 45;

export function truncateLabel(text: string, max = 28): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

/** Connections of a node that the view does not show (filters, limits or not expanded). */
export function hiddenConnections(node: ViewNode): number {
  return Math.max(0, node.degree - node.shownDegree);
}

function nodeLabel(node: ViewNode): string {
  const nature =
    node.nature === "real" ? "" : `, ${NATURE_ENCODING[node.nature].short.toLowerCase()}`;
  const hidden = hiddenConnections(node);
  return `${node.name}, ${typeLabel(node.type).toLowerCase()}${nature}, ${plural(
    node.degree,
    "connection",
  )}${hidden ? `, ${hidden} not shown` : ""}`;
}

/** Parallel edges between the same two nodes bow apart instead of overlapping. */
function edgeBends(edges: Iterable<GraphEdgeSummary>): Map<string, number> {
  const groups = new Map<string, string[]>();
  for (const edge of edges) {
    const pair =
      edge.source < edge.target ? `${edge.source}|${edge.target}` : `${edge.target}|${edge.source}`;
    const list = groups.get(pair);
    if (list) list.push(edge.id);
    else groups.set(pair, [edge.id]);
  }
  const bends = new Map<string, number>();
  for (const ids of groups.values()) {
    ids.forEach((id, index) => {
      bends.set(id, ids.length === 1 ? 0 : (index - (ids.length - 1) / 2) * 26);
    });
  }
  return bends;
}

interface LabelPlacement {
  x: number;
  y: number;
  anchor: "start" | "middle" | "end";
  rotate: number;
}

function placeLabel(
  node: ViewNode,
  point: Point,
  angle: number | null | undefined,
  layout: GraphLayout,
  isCentre: boolean,
): LabelPlacement {
  const r = nodeRadius(node.type, node.degree);
  if (isCentre || layout.kind === "columns") {
    return { x: 0, y: r + 15, anchor: "middle", rotate: 0 };
  }
  if (angle !== null && angle !== undefined) {
    // Written along the radius, reading outwards; flipped on the left so it is never upside down.
    const degrees = (angle * 180) / Math.PI;
    const left = Math.cos(angle) < 0;
    return {
      x: left ? -(r + 5) : r + 5,
      y: 0,
      anchor: left ? "end" : "start",
      rotate: left ? degrees + 180 : degrees,
    };
  }
  const theta = Math.atan2(point.y, point.x);
  const cos = Math.cos(theta);
  if (Math.abs(cos) < 0.34) {
    const below = Math.sin(theta) > 0;
    return { x: 0, y: below ? r + 15 : -(r + 8), anchor: "middle", rotate: 0 };
  }
  return { x: cos > 0 ? r + 6 : -(r + 6), y: 0, anchor: cos > 0 ? "start" : "end", rotate: 0 };
}

interface LayerEvents {
  select: (selection: Selection) => void;
  expand: (id: string) => void;
  hoverNode: (id: string | null) => void;
  hoverEdge: (id: string | null) => void;
}

interface LayerProps {
  view: GraphView;
  layout: GraphLayout;
  positions: ReadonlyMap<string, Point>;
  selection: Selection | null;
  emphasis: { nodeIds: Set<string>; edgeIds: Set<string> } | null;
  hoveredNodeId: string | null;
  busyIds: ReadonlySet<string>;
  expandedIds: ReadonlySet<string>;
  targetId: string | null;
  labels: "all" | "focus";
  markerId: string;
  hitScale: number;
  events: LayerEvents;
}

const GraphLayer = memo(function GraphLayer({
  view,
  layout,
  positions,
  selection,
  emphasis,
  hoveredNodeId,
  busyIds,
  expandedIds,
  targetId,
  labels,
  markerId,
  hitScale,
  events,
}: LayerProps) {
  const bends = useMemo(() => edgeBends(view.edges.values()), [view.edges]);
  const selectedNode = selection?.kind === "node" ? selection.id : null;
  const selectedEdge = selection?.kind === "edge" ? selection.id : null;

  const nodeState = (id: string): NodeState => {
    if (!emphasis) return "default";
    if (id === selectedNode) return "selected";
    return emphasis.nodeIds.has(id) ? "neighbor" : "dimmed";
  };
  const edgeState = (edge: GraphEdgeSummary): EdgeState => {
    if (edge.id === selectedEdge) return "selected";
    if (emphasis) return emphasis.edgeIds.has(edge.id) ? "active" : "dimmed";
    if (hoveredNodeId && (edge.source === hoveredNodeId || edge.target === hoveredNodeId)) {
      return "hover";
    }
    return "default";
  };

  const edges = [...view.edges.values()].map((edge) => ({ edge, state: edgeState(edge) }));
  // Emphasised lines are drawn last, on top.
  const rank: Record<EdgeState, number> = {
    dimmed: 0,
    default: 1,
    hover: 2,
    active: 3,
    selected: 4,
  };
  edges.sort((a, b) => rank[a.state] - rank[b.state]);
  const labelAll = labels === "all" && view.nodes.size <= LABEL_ALL_LIMIT;

  return (
    <>
      <g className={styles.edges}>
        {edges.map(({ edge, state }) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          const sourceNode = view.nodes.get(edge.source);
          const targetNode = view.nodes.get(edge.target);
          if (!source || !target || !sourceNode || !targetNode) return null;
          const geometry = edgeGeometry(
            source,
            target,
            nodeRadius(sourceNode.type, sourceNode.degree),
            nodeRadius(targetNode.type, targetNode.degree),
            edge.directed,
            bends.get(edge.id) ?? 0,
          );
          const evidence = EVIDENCE_ENCODING[edge.evidence_status];
          const marker =
            state === "selected" || state === "active"
              ? "active"
              : state === "dimmed"
                ? "dimmed"
                : "default";
          const width = edgeWidth(edge);
          return (
            <g key={edge.id}>
              <path
                d={geometry.d}
                className={styles.edge}
                data-edge-id={edge.id}
                data-state={state}
                data-evidence={edge.evidence_status}
                data-historical={edge.historical || undefined}
                strokeWidth={
                  state === "selected" ? width + 1.2 : state === "active" ? width + 0.5 : width
                }
                strokeDasharray={evidence.dash ?? undefined}
                strokeLinecap={evidence.linecap}
                markerEnd={edge.directed ? `url(#${markerId}-${marker})` : undefined}
              />
              {/* biome-ignore lint/a11y/noStaticElementInteractions: pointer convenience; every line is listed, operable, in the details panel and the table view. */}
              <path
                d={geometry.d}
                className={styles.edgeHit}
                onClick={(event) => {
                  event.stopPropagation();
                  events.select({ kind: "edge", id: edge.id });
                }}
                onPointerEnter={() => events.hoverEdge(edge.id)}
                onPointerLeave={() => events.hoverEdge(null)}
              />
            </g>
          );
        })}
      </g>
      <g className={styles.nodes}>
        {view.order.map((id) => {
          const node = view.nodes.get(id);
          const point = positions.get(id);
          if (!node || !point) return null;
          const state = nodeState(id);
          const encoding = NODE_TYPE_ENCODING[node.type];
          const r = nodeRadius(node.type, node.degree);
          const isCentre = id === view.focus || id === targetId;
          const ring = NATURE_ENCODING[node.nature].ringDash;
          const hidden = hiddenConnections(node);
          // Phones ("focus"): only the centre, the selection and the hovered node. Otherwise
          // everything not dimmed in small views, and near or connected nodes in large ones.
          const emphasised = state === "selected" || id === hoveredNodeId || isCentre;
          const showLabel =
            emphasised ||
            (labels === "all" &&
              state !== "dimmed" &&
              (labelAll || state === "neighbor" || node.hops <= 1));
          const label = showLabel
            ? placeLabel(node, point, layout.labelAngle.get(id), layout, isCentre)
            : null;
          return (
            // biome-ignore lint/a11y/useSemanticElements: SVG has no <button>; role + key handling make the node operable.
            <g
              key={id}
              className={styles.node}
              data-node-id={id}
              data-type={node.type}
              data-state={state}
              data-nature={node.nature}
              data-centre={isCentre || undefined}
              transform={`translate(${point.x} ${point.y})`}
              role="button"
              tabIndex={0}
              aria-pressed={state === "selected"}
              aria-busy={busyIds.has(id) || undefined}
              aria-label={nodeLabel(node)}
              onClick={(event) => {
                event.stopPropagation();
                events.select({ kind: "node", id });
              }}
              onDoubleClick={(event) => {
                event.stopPropagation();
                events.expand(id);
              }}
              onKeyDown={(event: KeyboardEvent<SVGGElement>) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  events.select({ kind: "node", id });
                } else if (event.key === "e" || event.key === "E") {
                  event.preventDefault();
                  events.expand(id);
                }
              }}
              onPointerEnter={() => events.hoverNode(id)}
              onPointerLeave={() => events.hoverNode(null)}
              onFocus={() => events.hoverNode(id)}
              onBlur={() => events.hoverNode(null)}
            >
              <circle className={styles.hit} r={Math.max(r + 7, 12 * hitScale)} />
              <circle className={styles.halo} r={r + 6} />
              {isCentre && <circle className={styles.centreRing} r={r + 10} />}
              {ring && <circle className={styles.natureRing} r={r + 3.2} strokeDasharray={ring} />}
              <GlyphMark
                shape={encoding.shape}
                r={r}
                hollow={isHollow(node)}
                className={styles.mark}
              />
              {busyIds.has(id) && <circle className={styles.busy} r={r + 7.5} />}
              {hidden > 0 && !expandedIds.has(id) && (
                <path
                  className={styles.more}
                  d={`M${r + 3} ${-(r + 6)} h6 M${r + 6} ${-(r + 9)} v6`}
                />
              )}
              {label && (
                <text
                  className={styles.label}
                  data-centre={isCentre || undefined}
                  textAnchor={label.anchor}
                  transform={label.rotate ? `rotate(${label.rotate.toFixed(1)})` : undefined}
                  x={label.x}
                  y={label.y}
                  dy={label.y === 0 ? "0.32em" : undefined}
                >
                  {truncateLabel(node.name, label.rotate ? 22 : 28)}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </>
  );
});

interface Padding {
  x: number;
  y: number;
}

/**
 * Screen room kept around the layout for labels. Labels keep a constant on-screen size
 * at any zoom, so their room is in pixels, not layout units.
 */
export function labelPadding(layout: GraphLayout): Padding {
  if (layout.kind === "columns") return { x: 90, y: 34 };
  // Labels written along the radius stick out on every side; horizontal ones sideways.
  const rotated = [...layout.labelAngle.values()].some((angle) => angle !== null);
  return rotated ? { x: 125, y: 125 } : { x: 150, y: 34 };
}

/** The transform that fits `bounds` into the viewport, with separate x and y padding. */
export function fitWithPadding(
  bounds: Bounds,
  width: number,
  height: number,
  padding: Padding,
  maxScale = 1.6,
): Transform {
  const contentWidth = Math.max(1, bounds.maxX - bounds.minX);
  const contentHeight = Math.max(1, bounds.maxY - bounds.minY);
  const k = Math.min(
    maxScale,
    Math.max(
      0.05,
      Math.min(
        Math.max(1, width - padding.x * 2) / contentWidth,
        Math.max(1, height - padding.y * 2) / contentHeight,
      ),
    ),
  );
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { k, x: width / 2 - cx * k, y: height / 2 - cy * k };
}

export function GraphCanvas({
  view,
  layout,
  selection,
  busyIds = new Set(),
  expandedIds = new Set(),
  targetId = null,
  onSelect,
  onExpand,
  labels = "all",
  ariaLabel,
  className,
  ref,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const { width, height } = useElementSize(containerRef);
  const { reducedMotion } = useTheme();
  const markerId = `rumin-graph-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const userMoved = useRef(false);

  const { transform, setTransform, zoomBy, wasDragged, isPanning, handlers } = usePanZoom({
    svgRef,
    enabled: true,
    onUserTransform: () => {
      userMoved.current = true;
    },
  });

  const originOf = useCallback((id: string) => view.nodes.get(id)?.origin, [view]);
  const positions = useAnimatedPositions(layout.positions, originOf, {
    animate: !reducedMotion,
  });

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);

  const padding = useMemo(() => labelPadding(layout), [layout]);

  const fitView = useCallback(() => {
    if (!width || !height) return;
    userMoved.current = false;
    // Narrow canvases keep most of their width for the graph; only a few labels show there.
    const room = { x: Math.min(padding.x, width * 0.2), y: Math.min(padding.y, height * 0.2) };
    setTransform(fitWithPadding(layout.bounds, width, height, room));
  }, [width, height, layout.bounds, padding, setTransform]);

  // Frame the view when it changes — unless the reader has moved it and everything still
  // fits, in which case their view is kept.
  const transformRef = useRef(transform);
  transformRef.current = transform;
  useEffect(() => {
    if (!width || !height) return;
    const t = transformRef.current;
    const topLeft = toScreen(t, { x: layout.bounds.minX, y: layout.bounds.minY });
    const bottomRight = toScreen(t, { x: layout.bounds.maxX, y: layout.bounds.maxY });
    const fits =
      topLeft.x >= 0 && topLeft.y >= 0 && bottomRight.x <= width && bottomRight.y <= height;
    if (!userMoved.current || !fits) fitView();
  }, [layout.bounds, width, height, fitView]);

  const centerOn = useCallback(
    (id: string) => {
      const point = layout.positions.get(id);
      if (!point || !width || !height) return;
      userMoved.current = true;
      setTransform((current) => {
        const k = Math.max(current.k, 1);
        return { k, x: width / 2 - point.x * k, y: height / 2 - point.y * k };
      });
    },
    [layout, width, height, setTransform],
  );

  useImperativeHandle(ref, () => ({ fitView, centerOn }), [fitView, centerOn]);

  const emphasis = useMemo(() => {
    if (!selection) return null;
    if (selection.kind === "node") {
      return view.nodes.has(selection.id) ? incidentTo(view, selection.id) : null;
    }
    const edge = view.edges.get(selection.id);
    return edge
      ? { nodeIds: new Set([edge.source, edge.target]), edgeIds: new Set([edge.id]) }
      : null;
  }, [selection, view]);

  const events = useMemo<LayerEvents>(
    () => ({
      select: (next) => {
        if (!wasDragged()) onSelect(next);
      },
      expand: (id) => onExpand?.(id),
      hoverNode: setHoveredNodeId,
      hoverEdge: setHoveredEdgeId,
    }),
    [onSelect, onExpand, wasDragged],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && selection) {
      onSelect(null);
      return;
    }
    if (event.target instanceof HTMLButtonElement) return;
    if (event.key === "+" || event.key === "=") zoomBy(1.25);
    else if (event.key === "-" || event.key === "_") zoomBy(0.8);
    else if (event.key === "0") fitView();
  };

  const tooltip = useMemo(() => {
    if (hoveredNodeId) {
      const node = view.nodes.get(hoveredNodeId);
      const point = positions.get(hoveredNodeId);
      return node && point
        ? { kind: "node" as const, node, point: toScreen(transform, point) }
        : null;
    }
    if (hoveredEdgeId) {
      const edge = view.edges.get(hoveredEdgeId);
      const a = edge && positions.get(edge.source);
      const b = edge && positions.get(edge.target);
      return edge && a && b
        ? {
            kind: "edge" as const,
            edge,
            point: toScreen(transform, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }),
          }
        : null;
    }
    return null;
  }, [hoveredNodeId, hoveredEdgeId, view, positions, transform]);

  const layerStyle = { "--label-scale": 1 / transform.k } as CSSProperties;

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: keyboard shortcuts for the canvas; nodes are the focusable controls.
    <div ref={containerRef} className={cx(styles.root, className)} onKeyDown={onKeyDown}>
      {/* biome-ignore lint/a11y/useSemanticElements: an SVG canvas has no semantic HTML equivalent; "group" names the set of node buttons. */}
      <svg
        ref={svgRef}
        className={styles.svg}
        viewBox={`0 0 ${Math.max(width, 1)} ${Math.max(height, 1)}`}
        role="group"
        aria-label={ariaLabel}
        data-panning={isPanning}
        {...handlers}
      >
        <defs>
          {(["default", "active", "dimmed"] as const).map((state) => (
            <marker
              key={state}
              id={`${markerId}-${state}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              markerUnits="userSpaceOnUse"
              orient="auto-start-reverse"
            >
              <path d="M0 0.8 L9.5 5 L0 9.2 Z" className={styles[`arrow-${state}`]} />
            </marker>
          ))}
        </defs>
        {/* biome-ignore lint/a11y/noStaticElementInteractions: pointer convenience only — Escape clears the selection from the keyboard. */}
        <rect
          className={styles.backdrop}
          width={Math.max(width, 1)}
          height={Math.max(height, 1)}
          onClick={() => {
            if (!wasDragged()) onSelect(null);
          }}
        />
        <g
          transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}
          style={layerStyle}
        >
          {layout.rings.slice(1).map((radius, index) => (
            <circle
              // biome-ignore lint/suspicious/noArrayIndexKey: one ring per hop count
              key={index}
              className={styles.ring}
              r={radius}
              data-hops={index + 1}
            />
          ))}
          <GraphLayer
            view={view}
            layout={layout}
            positions={positions}
            selection={selection}
            emphasis={emphasis}
            hoveredNodeId={hoveredNodeId}
            busyIds={busyIds}
            expandedIds={expandedIds}
            targetId={targetId}
            labels={labels}
            markerId={markerId}
            hitScale={Math.max(1, Math.round(4 / transform.k) / 4)}
            events={events}
          />
        </g>
      </svg>

      {tooltip && (
        <div
          className={styles.tooltip}
          aria-hidden="true"
          data-align={width < 560 ? "bar" : tooltip.point.x > width - 280 ? "left" : "right"}
          style={width < 560 ? undefined : { left: tooltip.point.x, top: tooltip.point.y }}
        >
          {tooltip.kind === "node" ? (
            <NodeTooltip node={tooltip.node} expanded={expandedIds.has(tooltip.node.id)} />
          ) : (
            <EdgeTooltip edge={tooltip.edge} view={view} />
          )}
        </div>
      )}

      <div className={styles.controls}>
        <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoomBy(0.8)} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={fitView} aria-label="Fit the graph to the view">
          Fit
        </button>
      </div>
    </div>
  );
}

function NodeTooltip({ node, expanded }: { node: ViewNode; expanded: boolean }) {
  const hidden = hiddenConnections(node);
  const data = DATA_STATUS_LABEL[node.data_status];
  return (
    <>
      <strong className={styles.tooltipTitle}>{node.name}</strong>
      <span className={styles.tooltipMeta}>
        {typeLabel(node.type)}
        {node.nature !== "real" ? ` · ${NATURE_ENCODING[node.nature].label}` : ""}
        {data ? ` · ${data}` : ""}
      </span>
      <span className={styles.tooltipMeta}>
        {plural(node.degree, "connection")}
        {hidden ? ` · ${hidden} not shown` : " · all shown"}
      </span>
      {hidden > 0 && !expanded && (
        <span className={styles.tooltipNote}>Double-click, or select and press E, to expand.</span>
      )}
    </>
  );
}

function EdgeTooltip({ edge, view }: { edge: GraphEdgeSummary; view: GraphView }) {
  const source = view.nodes.get(edge.source)?.name ?? edge.source;
  const target = view.nodes.get(edge.target)?.name ?? edge.target;
  return (
    <>
      <strong className={styles.tooltipTitle}>
        {source} <span className={styles.tooltipVerb}>{edge.label}</span> {target}
      </strong>
      <span className={styles.tooltipMeta}>
        {EVIDENCE_ENCODING[edge.evidence_status].label}
        {edge.is_illustrative ? " · Illustrative" : ""}
        {edge.historical ? " · Historical" : ""}
      </span>
      <span className={styles.tooltipNote}>Click for the evidence behind it.</span>
    </>
  );
}
