/**
 * The 3D universe's canvas: the React host of the renderer.
 *
 * It lays the graph out (`layout3d`), decides the marks (`scene.ts`), and owns the camera,
 * the pointer, the keyboard, the names written on the canvas and the tooltip. The renderer
 * itself — and Three.js with it — is imported only when the canvas mounts, and only when
 * the browser has WebGL 2; otherwise the host reports that it is unavailable and the page
 * shows the list instead.
 *
 * It renders on demand: after a change, after a camera movement, and on each frame of a
 * fly-to — never in an idle loop. Under reduced motion the camera jumps instead of flying.
 */
import {
  forwardRef,
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTheme } from "@/app/theme";
import { EVIDENCE_ENCODING, NATURE_ENCODING, typeLabel } from "@/features/graph/encoding";
import { useElementSize } from "@/hooks/useElementSize";
import type { GraphEdgeSummary, GraphNodeSummary } from "@/types/api";
import {
  DEFAULT_PHI,
  DEFAULT_THETA,
  easeOut,
  fitDistance,
  frameAll,
  interpolate,
  type Orbit,
  pan,
  rotate,
  zoom,
} from "./camera";
import { keyAction, nearestInDirection } from "./keyboard";
import { type LabelCandidate, placeLabels } from "./labels";
import { enclosing, layout3d, type Vec3 } from "./layout3d";
import type {
  Palette,
  Projected,
  RendererFactory,
  RendererInfo,
  StratumGuide,
  UniverseRenderer,
} from "./rendererTypes";
import {
  activeSet,
  buildScene,
  labelPriority,
  type SceneOverlay,
  type SceneSelection,
} from "./scene";
import { STRATA, STRATUM_GAP, stratumOf } from "./strata";
import styles from "./UniverseCanvas.module.css";
import { webglAvailable } from "./webgl";

export interface UniverseCanvasHandle {
  resetView: () => void;
  flyTo: (id: string) => void;
}

export type Unavailable = "webgl" | "context-lost" | "failed";

export interface RenderStats extends RendererInfo {
  /** Milliseconds the last frame took to prepare and submit (CPU). */
  frameMs: number;
}

export interface UniverseCanvasProps {
  nodes: readonly GraphNodeSummary[];
  edges: readonly GraphEdgeSummary[];
  /** For new nodes, the node that brought each into view (they start beside it). */
  anchors?: ReadonlyMap<string, string>;
  focus: string | null;
  selection: SceneSelection | null;
  overlay: SceneOverlay | null;
  label: string;
  describedBy?: string;
  onSelect: (selection: SceneSelection | null) => void;
  onActivate: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onUnavailable: (reason: Unavailable) => void;
  onStats?: (stats: RenderStats) => void;
  /** How to load the renderer (tests pass a stand-in). */
  loadRenderer?: () => Promise<RendererFactory>;
  /** Whether WebGL 2 is available (tests override it). */
  canRender?: () => boolean;
}

const loadThree = () => import("./renderer").then((module) => module.createRenderer);
const FLY_MS = 480;
const DRAG_THRESHOLD = 4;
const MAX_REMEMBERED = 6000;
const MAX_LABELS = 36;
/** The strata's names are placed before any node's. */
const STRATUM_PRIORITY = 10_000;
/**
 * From this label priority up (the selection, the pointer, the focus and an overlay's
 * nodes: see `labelPriority`), a name may cover other nodes when no side is free.
 */
const ESSENTIAL_LABEL = 800;

function readPalette(element: HTMLElement | null): Palette {
  const style = element ? getComputedStyle(element) : null;
  const get = (name: string, fallback: string) => style?.getPropertyValue(name).trim() || fallback;
  return {
    background: get("--color-surface", "#fbfaf6"),
    ink: get("--viz-node", "#2a2b2e"),
    hollow: get("--viz-node-hollow", "#fbfaf6"),
    structural: get("--viz-edge-structural", "#b3aea1"),
    economic: get("--viz-edge-economic", "#8a867c"),
    dimmed: get("--viz-dimmed", "#d3cec3"),
    accent: get("--color-accent", "#3a87cc"),
    guide: get("--color-line", "#dad5c9"),
  };
}

function segmentDistance(x: number, y: number, a: Projected, b: Projected): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / length)) : 0;
  return Math.hypot(a.x + dx * t - x, a.y + dy * t - y);
}

interface Drag {
  pointerId: number;
  x: number;
  y: number;
  lastX: number;
  lastY: number;
  moved: boolean;
  pan: boolean;
}

export const UniverseCanvas = forwardRef<UniverseCanvasHandle, UniverseCanvasProps>(
  function UniverseCanvas(props, ref) {
    const {
      nodes,
      edges,
      anchors,
      focus,
      selection,
      overlay,
      label,
      describedBy,
      onSelect,
      onActivate,
      onExpand,
      onCollapse,
      onUnavailable,
      loadRenderer = loadThree,
      canRender = webglAvailable,
    } = props;
    const { reducedMotion, resolvedTheme } = useTheme();
    const stageRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const surfaceRef = useRef<HTMLDivElement>(null);
    const labelsRef = useRef<HTMLDivElement>(null);
    const rendererRef = useRef<UniverseRenderer | null>(null);
    const [ready, setReady] = useState(false);
    const size = useElementSize(stageRef);
    const orbit = useRef<Orbit | null>(null);
    const flight = useRef<{ from: Orbit; to: Orbit; start: number } | null>(null);
    const frame = useRef<number | null>(null);
    const projections = useRef(new Map<string, Projected>());
    const remembered = useRef(new Map<string, Vec3>());
    const drag = useRef<Drag | null>(null);
    const touches = useRef(new Map<number, { x: number; y: number }>());
    const [hover, setHover] = useState<SceneSelection | null>(null);
    const [tip, setTip] = useState<{ x: number; y: number; title: string; detail: string } | null>(
      null,
    );
    const latest = useRef(props);
    latest.current = props;

    // --- Layout: stable as the view grows ---------------------------------------------------
    const nodeKey = nodes.map((node) => node.id).join("|");
    const edgeKey = edges.map((edge) => edge.id).join("|");
    // biome-ignore lint/correctness/useExhaustiveDependencies: the keys stand for the lists.
    const layout = useMemo(
      () =>
        layout3d(
          nodes.map((node) => ({ id: node.id, type: node.type })),
          edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            category: edge.category,
          })),
          { previous: remembered.current, ...(anchors ? { anchors } : {}) },
        ),
      [nodeKey, edgeKey],
    );
    useEffect(() => {
      const merged = new Map(remembered.current);
      for (const [id, point] of layout.positions) merged.set(id, point);
      while (merged.size > MAX_REMEMBERED) {
        const oldest = merged.keys().next().value;
        if (oldest === undefined) break;
        merged.delete(oldest);
      }
      remembered.current = merged;
    }, [layout]);

    const scene = useMemo(
      () =>
        buildScene({
          nodes,
          edges,
          positions: layout.positions,
          focus,
          selection,
          hover,
          overlay,
        }),
      [nodes, edges, layout, focus, selection, hover, overlay],
    );

    const guides = useMemo<StratumGuide[]>(() => {
      const center = layout.center;
      const reach = new Map<number, number>();
      for (const node of nodes) {
        const point = layout.positions.get(node.id);
        if (!point) continue;
        const level = stratumOf(node.type).level;
        const distance = Math.hypot(point.x - center.x, point.z - center.z);
        reach.set(level, Math.max(reach.get(level) ?? 0, distance));
      }
      return [...reach].map(([level, radius]) => ({
        level,
        height: level * STRATUM_GAP,
        radius: radius + 24,
        center,
      }));
    }, [nodes, layout]);

    // --- Drawing ----------------------------------------------------------------------------
    const drawLabels = useCallback(() => {
      const layer = labelsRef.current;
      const renderer = rendererRef.current;
      if (!layer || !renderer) return;
      const box = layer.getBoundingClientRect();
      const width = box.width || size.width;
      const height = box.height || size.height;
      const byId = new Map<string, Projected>();
      for (const node of scene.nodes) byId.set(node.id, renderer.project(node.position));
      projections.current = byId;
      const current = latest.current;
      const active = activeSet(current.selection, edges);
      const neighbours = active?.nodes ?? new Set<string>();
      const degree = new Map(nodes.map((node) => [node.id, node.degree]));
      // A node's disc on screen, with its outline.
      const discs = scene.nodes.flatMap((node) => {
        const point = byId.get(node.id);
        return point?.visible
          ? [{ id: node.id, x: point.x, y: point.y, r: node.size * point.scale * 1.2 }]
          : [];
      });
      const radius = new Map(discs.map((disc) => [disc.id, disc.r]));
      const strata: LabelCandidate[] = guides.flatMap((guide) => {
        const stratum = STRATA.find((item) => item.level === guide.level);
        if (!stratum) return [];
        const anchor = renderer.project({
          x: guide.center.x - guide.radius,
          y: guide.height,
          z: guide.center.z,
        });
        return [
          {
            id: `stratum:${stratum.id}`,
            text: stratum.label,
            x: anchor.x,
            y: anchor.y,
            visible: anchor.visible,
            priority: STRATUM_PRIORITY,
            depth: 0,
            sides: ["left"],
            clamp: true,
            charWidth: 8.4,
          },
        ];
      });
      const placed = placeLabels(
        [
          ...strata,
          ...scene.nodes.map((node) => {
            const point = byId.get(node.id) as Projected;
            return {
              id: node.id,
              text: node.name,
              x: point.x,
              y: point.y,
              visible: point.visible,
              priority: labelPriority(node, degree.get(node.id) ?? 0, hover, neighbours),
              depth: point.depth,
              radius: radius.get(node.id) ?? 0,
            };
          }),
        ],
        width,
        height,
        { obstacles: discs, max: MAX_LABELS + strata.length, essential: ESSENTIAL_LABEL },
      );
      while (layer.children.length < placed.length) layer.append(document.createElement("span"));
      while (layer.children.length > placed.length) layer.lastChild?.remove();
      placed.forEach((item, index) => {
        const element = layer.children[index] as HTMLSpanElement;
        const stratum = item.id.startsWith("stratum:");
        element.textContent = item.text;
        element.className = (stratum ? styles.stratumLabel : styles.label) ?? "";
        element.dataset.side = item.side;
        const y = Math.round(item.y - 8);
        element.style.transform =
          item.side === "right"
            ? `translate(${Math.round(item.x)}px, ${y}px)`
            : `translate(calc(${Math.round(item.x)}px - 100%), ${y}px)`;
      });
    }, [scene, guides, edges, nodes, hover, size.width, size.height]);

    // Every frame calls the latest `draw`, so a frame scheduled before the scene changed (a
    // flight, say) draws the new scene's names and records its positions for picking.
    const drawLatest = useRef<() => void>(() => undefined);
    const nextFrame = useCallback(() => {
      frame.current = requestAnimationFrame(() => drawLatest.current());
    }, []);

    const draw = useCallback(() => {
      frame.current = null;
      const renderer = rendererRef.current;
      if (!renderer || !orbit.current) return;
      const started = performance.now();
      const moving = flight.current;
      if (moving) {
        const t = (started - moving.start) / FLY_MS;
        orbit.current = interpolate(moving.from, moving.to, easeOut(t));
        if (t >= 1) {
          orbit.current = moving.to;
          flight.current = null;
        }
      }
      renderer.setOrbit(orbit.current);
      renderer.render();
      drawLabels();
      latest.current.onStats?.({ ...renderer.info(), frameMs: performance.now() - started });
      if (flight.current) nextFrame();
    }, [drawLabels, nextFrame]);
    drawLatest.current = draw;

    const requestDraw = useCallback(() => {
      if (frame.current === null) nextFrame();
    }, [nextFrame]);

    const moveCamera = useCallback(
      (next: Orbit, animate = true) => {
        if (animate && !reducedMotion && orbit.current) {
          flight.current = { from: orbit.current, to: next, start: performance.now() };
        } else {
          flight.current = null;
          orbit.current = next;
        }
        requestDraw();
      },
      [reducedMotion, requestDraw],
    );

    // --- The renderer's lifetime ------------------------------------------------------------
    // biome-ignore lint/correctness/useExhaustiveDependencies: created once per mount.
    useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      if (!canRender()) {
        onUnavailable("webgl");
        return;
      }
      let disposed = false;
      let instance: UniverseRenderer | null = null;
      loadRenderer().then(
        (factory) => {
          if (disposed) return;
          try {
            instance = factory(canvas, {
              onContextLost: () => latest.current.onUnavailable("context-lost"),
            });
          } catch {
            latest.current.onUnavailable("failed");
            return;
          }
          rendererRef.current = instance;
          setReady(true);
        },
        () => {
          if (!disposed) latest.current.onUnavailable("failed");
        },
      );
      return () => {
        disposed = true;
        if (frame.current !== null) cancelAnimationFrame(frame.current);
        frame.current = null;
        instance?.dispose();
        rendererRef.current = null;
      };
    }, []);

    // Size and pixel ratio.
    useEffect(() => {
      const renderer = rendererRef.current;
      if (!ready || !renderer || !size.width || !size.height) return;
      renderer.resize(size.width, size.height, window.devicePixelRatio || 1);
      requestDraw();
    }, [ready, size.width, size.height, requestDraw]);

    // The scene, and the theme's colours.
    // biome-ignore lint/correctness/useExhaustiveDependencies: `resolvedTheme` re-reads the tokens.
    useEffect(() => {
      const renderer = rendererRef.current;
      if (!ready || !renderer) return;
      renderer.setScene(scene, readPalette(stageRef.current), guides);
      requestDraw();
    }, [ready, scene, guides, resolvedTheme, requestDraw]);

    // The camera: framed once, then moved only when the focus changes or the reader asks.
    const aspect = size.width && size.height ? size.width / size.height : 1.6;
    /** A view of every node and the strata's rings, from the default angles. */
    const overall = useCallback(() => {
      const points = [...layout.positions.values()];
      for (const guide of guides) {
        for (let step = 0; step < 12; step += 1) {
          const angle = (step * Math.PI) / 6;
          points.push({
            x: guide.center.x + guide.radius * Math.cos(angle),
            y: guide.height,
            z: guide.center.z + guide.radius * Math.sin(angle),
          });
        }
      }
      return frameAll(points, aspect, { theta: DEFAULT_THETA, phi: DEFAULT_PHI });
    }, [layout, guides, aspect]);
    const framed = useRef(false);
    useEffect(() => {
      if (!ready || framed.current || !nodes.length || !size.width || !size.height) return;
      framed.current = true;
      orbit.current = overall();
      requestDraw();
    }, [ready, nodes.length, overall, size.width, size.height, requestDraw]);

    const lastFocus = useRef<string | null>(focus);
    useEffect(() => {
      if (!ready || !orbit.current || focus === lastFocus.current) return;
      const point = focus ? layout.positions.get(focus) : null;
      // A new focus not laid out yet (its neighbourhood is loading): wait for it.
      if (focus && !point) return;
      lastFocus.current = focus;
      if (!point) return;
      const around = enclosing(
        new Map(
          [...layout.positions].filter(
            ([, other]) => Math.hypot(other.x - point.x, other.z - point.z) < 400,
          ),
        ),
      );
      moveCamera({
        target: { ...point },
        radius: Math.min(fitDistance(around.radius, aspect), 900),
        theta: orbit.current.theta,
        phi: orbit.current.phi,
      });
    }, [ready, focus, layout, aspect, moveCamera]);

    useImperativeHandle(
      ref,
      () => ({
        resetView: () => moveCamera(overall()),
        flyTo: (id: string) => {
          const point = layout.positions.get(id);
          if (!point || !orbit.current) return;
          moveCamera({
            ...orbit.current,
            target: { ...point },
            radius: Math.min(orbit.current.radius, 320),
          });
        },
      }),
      [layout, overall, moveCamera],
    );

    // --- Picking ----------------------------------------------------------------------------
    const pick = useCallback(
      (x: number, y: number): SceneSelection | null => {
        let best: { id: string; distance: number; depth: number } | null = null;
        for (const node of scene.nodes) {
          const point = projections.current.get(node.id);
          if (!point?.visible) continue;
          const distance = Math.hypot(point.x - x, point.y - y);
          const radius = Math.max(12, node.size * point.scale * 1.25);
          if (distance > radius) continue;
          if (
            !best ||
            distance < best.distance - 1 ||
            (Math.abs(distance - best.distance) <= 1 && point.depth < best.depth)
          ) {
            best = { id: node.id, distance, depth: point.depth };
          }
        }
        if (best) return { kind: "node", id: best.id };
        let nearest: { id: string; distance: number } | null = null;
        for (const edge of scene.edges) {
          const a = projections.current.get(edge.source);
          const b = projections.current.get(edge.target);
          if (!a || !b || (!a.visible && !b.visible)) continue;
          const distance = segmentDistance(x, y, a, b);
          if (
            distance <= Math.max(5, edge.width / 2 + 4) &&
            (!nearest || distance < nearest.distance)
          ) {
            nearest = { id: edge.id, distance };
          }
        }
        return nearest ? { kind: "edge", id: nearest.id } : null;
      },
      [scene],
    );

    const describe = useCallback(
      (target: SceneSelection) => {
        if (target.kind === "node") {
          const node = nodes.find((item) => item.id === target.id);
          if (!node) return null;
          return {
            title: node.name,
            detail: `${typeLabel(node.type)} · ${NATURE_ENCODING[node.nature].short}`,
          };
        }
        const edge = edges.find((item) => item.id === target.id);
        if (!edge) return null;
        const name = (id: string) => nodes.find((node) => node.id === id)?.name ?? id;
        return {
          title: `${name(edge.source)} ${edge.label} ${name(edge.target)}`,
          detail: EVIDENCE_ENCODING[edge.evidence_status].label,
        };
      },
      [nodes, edges],
    );

    // --- Pointer ----------------------------------------------------------------------------
    const local = (event: { clientX: number; clientY: number }) => {
      const box = canvasRef.current?.getBoundingClientRect();
      return { x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) };
    };

    const onPointerDown = (event: PointerEvent<HTMLCanvasElement>) => {
      const point = local(event);
      touches.current.set(event.pointerId, point);
      event.currentTarget.setPointerCapture?.(event.pointerId);
      surfaceRef.current?.focus({ preventScroll: true });
      flight.current = null;
      drag.current = {
        pointerId: event.pointerId,
        x: point.x,
        y: point.y,
        lastX: point.x,
        lastY: point.y,
        moved: false,
        pan: event.button === 2 || event.shiftKey,
      };
    };

    const onPointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
      const point = local(event);
      const height = size.height || 1;
      // Only pressed pointers are tracked (from pointerdown to pointerup): a mouse that merely
      // hovers must not make the next one-finger drag read as a pinch.
      const pressed = touches.current.has(event.pointerId);
      if (pressed && touches.current.size === 2 && orbit.current) {
        const [a, b] = [...touches.current.values()];
        const before = a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
        touches.current.set(event.pointerId, point);
        const [c, d] = [...touches.current.values()];
        const after = c && d ? Math.hypot(c.x - d.x, c.y - d.y) : 0;
        if (before > 0 && after > 0) orbit.current = zoom(orbit.current, before / after);
        if (drag.current) drag.current.moved = true;
        requestDraw();
        return;
      }
      if (pressed) touches.current.set(event.pointerId, point);
      const current = drag.current;
      if (current && current.pointerId === event.pointerId && orbit.current) {
        const dx = point.x - current.lastX;
        const dy = point.y - current.lastY;
        current.lastX = point.x;
        current.lastY = point.y;
        if (Math.hypot(point.x - current.x, point.y - current.y) > DRAG_THRESHOLD) {
          current.moved = true;
        }
        if (!current.moved) return;
        orbit.current = current.pan
          ? pan(orbit.current, dx / height, dy / height)
          : rotate(orbit.current, -dx * 0.008, -dy * 0.006);
        setTip(null);
        requestDraw();
        return;
      }
      const found = pick(point.x, point.y);
      const same =
        (found === null && hover === null) ||
        (found !== null && hover !== null && found.kind === hover.kind && found.id === hover.id);
      if (!same) setHover(found);
      const text = found ? describe(found) : null;
      setTip(text ? { x: point.x, y: point.y, ...text } : null);
    };

    const onPointerUp = (event: PointerEvent<HTMLCanvasElement>) => {
      touches.current.delete(event.pointerId);
      const current = drag.current;
      drag.current = null;
      if (!current || current.moved || current.pointerId !== event.pointerId) return;
      const point = local(event);
      onSelect(pick(point.x, point.y));
    };

    const onPointerLeave = () => {
      setHover(null);
      setTip(null);
    };

    const onDoubleClick = (event: { clientX: number; clientY: number }) => {
      const point = local(event);
      const found = pick(point.x, point.y);
      if (found?.kind === "node") onActivate(found.id);
    };

    // Wheel zoom needs a non-passive listener to keep the page from scrolling.
    useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const onWheel = (event: WheelEvent) => {
        if (!orbit.current) return;
        event.preventDefault();
        flight.current = null;
        orbit.current = zoom(orbit.current, Math.exp(event.deltaY * 0.0015));
        requestDraw();
      };
      canvas.addEventListener("wheel", onWheel, { passive: false });
      return () => canvas.removeEventListener("wheel", onWheel);
    }, [requestDraw]);

    // --- Keyboard ---------------------------------------------------------------------------
    const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
      const action = keyAction(event);
      if (!action || !orbit.current) return;
      event.preventDefault();
      const selected = selection?.kind === "node" ? selection.id : null;
      switch (action.type) {
        case "move": {
          const from = selected ? projections.current.get(selected) : null;
          const origin = from?.visible
            ? from
            : { x: (size.width || 0) / 2, y: (size.height || 0) / 2 };
          const next = nearestInDirection(
            origin,
            [...projections.current].map(([id, point]) => ({
              id,
              x: point.x,
              y: point.y,
              visible: point.visible,
            })),
            action.direction,
            selected,
          );
          if (next) onSelect({ kind: "node", id: next });
          break;
        }
        case "rotate":
          orbit.current = rotate(orbit.current, action.theta, action.phi);
          requestDraw();
          break;
        case "zoom":
          orbit.current = zoom(orbit.current, action.factor);
          requestDraw();
          break;
        case "focus":
          if (selected) onActivate(selected);
          break;
        case "expand":
          if (selected) onExpand(selected);
          break;
        case "collapse":
          if (selected) onCollapse(selected);
          break;
        case "reset":
          moveCamera(overall());
          break;
        case "clear":
          onSelect(null);
          break;
      }
    };

    return (
      <div className={styles.stage} ref={stageRef} data-ready={ready}>
        <div
          ref={surfaceRef}
          className={styles.surface}
          // biome-ignore lint/a11y/noNoninteractiveTabindex: role="application" — the 3D view is operated from the keyboard (arrow keys move the selection); every node and relationship is also in the list view.
          tabIndex={0}
          role="application"
          aria-roledescription="3D knowledge graph"
          aria-label={label}
          aria-describedby={describedBy}
          onKeyDown={onKeyDown}
        >
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onPointerLeave={onPointerLeave}
            onDoubleClick={onDoubleClick}
            onContextMenu={(event) => event.preventDefault()}
          />
        </div>
        <div className={styles.labels} ref={labelsRef} aria-hidden="true" />
        {tip && (
          <div
            className={styles.tooltip}
            style={{
              transform: `translate(${Math.round(tip.x + 14)}px, ${Math.round(tip.y + 14)}px)`,
            }}
            aria-hidden="true"
          >
            <strong>{tip.title}</strong>
            <span>{tip.detail}</span>
          </div>
        )}
        {!ready && <p className={styles.preparing}>Preparing the 3D view…</p>}
      </div>
    );
  },
);
