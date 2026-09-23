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
import { useElementSize } from "@/hooks/useElementSize";
import { cx } from "@/lib/cx";
import {
  describeEffect,
  EVIDENCE_LABEL,
  KIND_ENCODING,
  nodeRadius,
  POLARITY_SYMBOL,
  STRENGTH_LABEL,
  STRENGTH_WIDTH,
  shapePath,
} from "./encoding";
import { geometryFor } from "./geometry";
import type { Bounds, Layout } from "./layout";
import {
  type GraphEdge,
  type GraphModel,
  type GraphNode,
  neighborhood,
  type Subgraph,
} from "./model";
import styles from "./NetworkCanvas.module.css";
import { fitTransform, toScreen, usePanZoom } from "./panZoom";

export interface NetworkCanvasHandle {
  centerOn: (id: string) => void;
  fitToView: () => void;
}

export interface NetworkCanvasProps {
  model: GraphModel;
  layout: Layout;
  visible: Subgraph;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** "explore": pan, zoom and keyboard shortcuts. "preview": fixed framing, click to select. */
  mode?: "explore" | "preview";
  /**
   * "all" labels every node; "structure" labels the outer columns (variables and
   * countries), which never collide, and everything else only when in focus;
   * "focus" labels only the selected/hovered node and its neighbours; "selected" labels
   * only the selected node (phones, where the details panel lists the neighbours).
   */
  labels?: "all" | "structure" | "focus" | "selected";
  ariaLabel: string;
  className?: string;
  ref?: Ref<NetworkCanvasHandle>;
}

type NodeState = "selected" | "neighbor" | "dimmed" | "default";
type EdgeState = "active" | "hover" | "dimmed" | "default";

/** Room reserved around the layout for labels, in layout units. */
const LABEL_ALLOWANCE = 96;

export function wrapLabel(text: string, max = 22): string[] {
  if (text.length <= max) return [text];
  let first = "";
  for (const word of text.split(" ")) {
    const next = first ? `${first} ${word}` : word;
    if (next.length > max) break;
    first = next;
  }
  if (!first) return [`${text.slice(0, max - 1)}…`];
  let rest = text.slice(first.length).trim();
  if (rest.length > max) rest = `${rest.slice(0, max - 1).trimEnd()}…`;
  return [first, rest];
}

interface LayerEvents {
  select: (id: string) => void;
  keyDown: (event: KeyboardEvent<SVGGElement>, id: string) => void;
  hoverNode: (id: string | null) => void;
  focusNode: (id: string | null) => void;
  hoverEdge: (id: string | null) => void;
}

interface LayerProps {
  model: GraphModel;
  layout: Layout;
  visible: Subgraph;
  focus: Subgraph | null;
  selectedId: string | null;
  hoveredNodeId: string | null;
  labels: "all" | "structure" | "focus" | "selected";
  interactiveEdges: boolean;
  markerId: string;
  centreX: number;
  /** 1/zoom, quantised: keeps each node's hit area at least 24px wide on screen. */
  hitScale: number;
  events: LayerEvents;
}

const NetworkLayer = memo(function NetworkLayer({
  model,
  layout,
  visible,
  focus,
  selectedId,
  hoveredNodeId,
  labels,
  interactiveEdges,
  markerId,
  centreX,
  hitScale,
  events,
}: LayerProps) {
  const nodeState = (id: string): NodeState => {
    if (!focus) return "default";
    if (id === selectedId) return "selected";
    return focus.nodeIds.has(id) ? "neighbor" : "dimmed";
  };
  const edgeState = (edge: GraphEdge): EdgeState => {
    if (focus) return focus.edgeIds.has(edge.id) ? "active" : "dimmed";
    if (hoveredNodeId && (edge.source === hoveredNodeId || edge.target === hoveredNodeId)) {
      return "hover";
    }
    return "default";
  };
  const radius = (node: GraphNode) => nodeRadius(node.kind, node.degree);

  return (
    <>
      <g className={styles.edges}>
        {model.edges.map((edge) => {
          if (!visible.edgeIds.has(edge.id)) return null;
          const geometry = geometryFor(edge, model, layout);
          if (!geometry) return null;
          const state = edgeState(edge);
          const width = edge.data.category === "economic" ? STRENGTH_WIDTH[edge.data.strength] : 1;
          const marker = state === "active" ? "active" : state === "dimmed" ? "dimmed" : "default";
          return (
            <g key={edge.id}>
              <path
                d={geometry.d}
                className={styles.edge}
                data-category={edge.category}
                data-state={state}
                data-edge-id={edge.id}
                strokeWidth={state === "active" ? width + 0.6 : width}
                markerEnd={edge.directed ? `url(#${markerId}-${marker})` : undefined}
              />
              {interactiveEdges && (
                <path
                  d={geometry.d}
                  className={styles.edgeHit}
                  onPointerEnter={() => events.hoverEdge(edge.id)}
                  onPointerLeave={() => events.hoverEdge(null)}
                />
              )}
            </g>
          );
        })}
      </g>
      <g className={styles.nodes}>
        {model.nodes.map((node) => {
          if (!visible.nodeIds.has(node.id)) return null;
          const position = layout.positions.get(node.id);
          if (!position) return null;
          const state = nodeState(node.id);
          const encoding = KIND_ENCODING[node.kind];
          const r = radius(node);
          const inFocus = state === "selected" || state === "neighbor" || node.id === hoveredNodeId;
          const showLabel =
            labels === "all" ||
            state === "selected" ||
            (labels !== "selected" && inFocus) ||
            (labels === "structure" &&
              (node.kind === "economic_variable" || node.kind === "country"));
          // Labels point outwards, away from the dense middle of the layered layout.
          const labelLeft = layout.orientation === "horizontal" && position.x < centreX;
          const lines = wrapLabel(node.label);
          return (
            // biome-ignore lint/a11y/useSemanticElements: SVG has no <button>; role + key handling make the node operable.
            <g
              key={node.id}
              className={styles.node}
              data-kind={node.kind}
              data-state={state}
              data-node-id={node.id}
              transform={`translate(${position.x} ${position.y})`}
              role="button"
              tabIndex={0}
              aria-pressed={state === "selected"}
              aria-label={`${node.label}, ${encoding.label.toLowerCase()}, ${node.degree} connection${
                node.degree === 1 ? "" : "s"
              }`}
              onClick={() => events.select(node.id)}
              onKeyDown={(event) => events.keyDown(event, node.id)}
              onPointerEnter={() => events.hoverNode(node.id)}
              onPointerLeave={() => events.hoverNode(null)}
              onFocus={() => events.focusNode(node.id)}
              onBlur={() => events.focusNode(null)}
            >
              <circle className={styles.hit} r={Math.max(r + 6, 12 * hitScale)} />
              <circle className={styles.halo} r={r + 5} />
              {encoding.shape === "dot" || encoding.shape === "ring" ? (
                <circle
                  className={cx(styles.mark, encoding.shape === "ring" && styles.hollow)}
                  r={r}
                />
              ) : (
                <path
                  className={cx(styles.mark, encoding.shape === "square" && styles.hollow)}
                  d={shapePath(encoding.shape, r)}
                />
              )}
              {showLabel && (
                <text
                  className={styles.label}
                  textAnchor={labelLeft ? "end" : "start"}
                  x={labelLeft ? -(r + 6) : r + 6}
                  y={lines.length > 1 ? -2 : 4}
                >
                  {lines.map((line, index) => (
                    <tspan
                      key={line}
                      x={labelLeft ? -(r + 6) : r + 6}
                      dy={index === 0 ? 0 : "1.15em"}
                    >
                      {line}
                    </tspan>
                  ))}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </>
  );
});

export function NetworkCanvas({
  model,
  layout,
  visible,
  selectedId,
  onSelect,
  mode = "explore",
  labels = "all",
  ariaLabel,
  className,
  ref,
}: NetworkCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const { width, height } = useElementSize(containerRef);
  const markerId = `rumin-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const userMoved = useRef(false);
  const explore = mode === "explore";

  const { transform, setTransform, zoomBy, wasDragged, isPanning, handlers } = usePanZoom({
    svgRef,
    enabled: explore,
    onUserTransform: () => {
      userMoved.current = true;
    },
  });

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);

  // Frame the layout plus room for labels (outward in columns, to the right in rows).
  const framedBounds = useMemo<Bounds>(
    () =>
      layout.orientation === "horizontal"
        ? {
            minX: layout.bounds.minX - LABEL_ALLOWANCE,
            maxX: layout.bounds.maxX + LABEL_ALLOWANCE,
            minY: layout.bounds.minY - 16,
            maxY: layout.bounds.maxY + 16,
          }
        : {
            minX: layout.bounds.minX - 16,
            maxX: layout.bounds.maxX + LABEL_ALLOWANCE / 2,
            minY: layout.bounds.minY - 24,
            maxY: layout.bounds.maxY + 24,
          },
    [layout],
  );
  const centreX = (layout.bounds.minX + layout.bounds.maxX) / 2;

  const fitToView = useCallback(() => {
    if (!width || !height) return;
    userMoved.current = false;
    setTransform(fitTransform(framedBounds, width, height, 24, explore ? 1.5 : 1.25));
  }, [width, height, framedBounds, explore, setTransform]);

  // Frame the graph whenever the viewport or layout changes — unless the reader has
  // already panned or zoomed, in which case their view is respected.
  useEffect(() => {
    if (!userMoved.current) fitToView();
  }, [fitToView]);

  const centerOn = useCallback(
    (id: string) => {
      const point = layout.positions.get(id);
      if (!point || !width || !height) return;
      userMoved.current = true;
      setTransform((current) => {
        const k = Math.max(current.k, 1.1);
        return { k, x: width / 2 - point.x * k, y: height / 2 - point.y * k };
      });
    },
    [layout, width, height, setTransform],
  );

  useImperativeHandle(ref, () => ({ centerOn, fitToView }), [centerOn, fitToView]);

  const focus = useMemo(
    () =>
      selectedId && visible.nodeIds.has(selectedId)
        ? neighborhood(model, selectedId, visible)
        : null,
    [model, selectedId, visible],
  );

  const events = useMemo<LayerEvents>(
    () => ({
      select: (id) => {
        if (wasDragged()) return;
        onSelect(id);
      },
      keyDown: (event, id) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(id);
        }
      },
      hoverNode: setHoveredNodeId,
      focusNode: setFocusedNodeId,
      hoverEdge: setHoveredEdgeId,
    }),
    [onSelect, wasDragged],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && selectedId) {
      onSelect(null);
      return;
    }
    if (!explore) return;
    if (event.key === "+" || event.key === "=") zoomBy(1.25);
    else if (event.key === "-" || event.key === "_") zoomBy(0.8);
    else if (event.key === "0") fitToView();
  };

  const tooltipNodeId = hoveredNodeId ?? focusedNodeId;
  const tooltip = useMemo(() => {
    if (tooltipNodeId) {
      const node = model.nodeById.get(tooltipNodeId);
      const point = layout.positions.get(tooltipNodeId);
      if (!node || !point) return null;
      return { kind: "node" as const, node, point: toScreen(transform, point) };
    }
    if (hoveredEdgeId) {
      const edge = model.edgeById.get(hoveredEdgeId);
      const geometry = edge && geometryFor(edge, model, layout);
      if (!edge || !geometry) return null;
      return { kind: "edge" as const, edge, point: toScreen(transform, geometry.mid) };
    }
    return null;
  }, [tooltipNodeId, hoveredEdgeId, model, layout, transform]);

  const layerStyle = { "--label-scale": 1 / transform.k } as CSSProperties;

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: keyboard shortcuts for the canvas; nodes are the focusable controls.
    <div
      ref={containerRef}
      className={cx(styles.root, !explore && styles.preview, className)}
      onKeyDown={onKeyDown}
    >
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
          <NetworkLayer
            model={model}
            layout={layout}
            visible={visible}
            focus={focus}
            selectedId={selectedId}
            hoveredNodeId={hoveredNodeId}
            labels={labels}
            interactiveEdges={explore}
            markerId={markerId}
            centreX={centreX}
            hitScale={Math.max(1, Math.round(4 / transform.k) / 4)}
            events={events}
          />
        </g>
      </svg>

      {tooltip && (
        <div
          className={styles.tooltip}
          aria-hidden="true"
          // Narrow canvases get a fixed read-out bar instead of a floating tooltip.
          data-align={width < 560 ? "bar" : tooltip.point.x > width - 260 ? "left" : "right"}
          style={width < 560 ? undefined : { left: tooltip.point.x, top: tooltip.point.y }}
        >
          {tooltip.kind === "node" ? (
            <NodeTooltip node={tooltip.node} />
          ) : (
            <EdgeTooltip edge={tooltip.edge} model={model} />
          )}
        </div>
      )}

      {explore && (
        <div className={styles.controls}>
          <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in">
            +
          </button>
          <button type="button" onClick={() => zoomBy(0.8)} aria-label="Zoom out">
            −
          </button>
          <button type="button" onClick={fitToView} aria-label="Fit network to view">
            Fit
          </button>
        </div>
      )}
    </div>
  );
}

function NodeTooltip({ node }: { node: GraphNode }) {
  return (
    <>
      <strong className={styles.tooltipTitle}>{node.label}</strong>
      <span className={styles.tooltipMeta}>
        {KIND_ENCODING[node.kind].label} · {node.degree} connection{node.degree === 1 ? "" : "s"}
        {node.entity.is_fictional ? " · Fictional" : ""}
      </span>
    </>
  );
}

function EdgeTooltip({ edge, model }: { edge: GraphEdge; model: GraphModel }) {
  const source = model.nodeById.get(edge.source)?.label ?? edge.source;
  const target = model.nodeById.get(edge.target)?.label ?? edge.target;
  const label = model.types.get(edge.type)?.label ?? edge.type;
  const data = edge.data;
  const effect =
    data.category === "economic" ? describeEffect(data.type, data.polarity, source, target) : null;
  return (
    <>
      <strong className={styles.tooltipTitle}>
        {source} <span className={styles.tooltipVerb}>{label}</span> {target}
      </strong>
      {data.category === "economic" ? (
        <span className={styles.tooltipMeta}>
          {STRENGTH_LABEL[data.strength]}
          {data.polarity !== "not_applicable"
            ? ` · ${POLARITY_SYMBOL[data.polarity]} ${data.polarity}`
            : ""}
          {` · ${EVIDENCE_LABEL[data.evidence_level]}`}
        </span>
      ) : (
        <span className={styles.tooltipMeta}>Structural link, derived from the entity record</span>
      )}
      {effect && <span className={styles.tooltipNote}>{effect}</span>}
    </>
  );
}
