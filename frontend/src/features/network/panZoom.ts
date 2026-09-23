/**
 * Pan and zoom for the network canvas: mouse drag, wheel / trackpad pinch, and
 * two-finger touch pinch. The maths lives in small pure functions (tested); the hook
 * wires them to pointer events.
 *
 * Pointer capture starts only once a pointer has moved past a small threshold, so an
 * ordinary click still reaches the node under it; `wasDragged()` lets click handlers
 * ignore the click that ends a drag.
 */
import { type RefObject, useCallback, useEffect, useRef, useState } from "react";
import type { Bounds, Point } from "./layout";

export interface Transform {
  x: number;
  y: number;
  k: number;
}

export const IDENTITY: Transform = { x: 0, y: 0, k: 1 };
export const MIN_SCALE = 0.3;
export const MAX_SCALE = 4;
const DRAG_THRESHOLD = 4;

export function clampScale(k: number, min = MIN_SCALE, max = MAX_SCALE): number {
  return Math.min(max, Math.max(min, k));
}

/** Zoom by `factor`, keeping the screen point `at` fixed. */
export function zoomAt(t: Transform, factor: number, at: Point, min = MIN_SCALE, max = MAX_SCALE) {
  const k = clampScale(t.k * factor, min, max);
  const ratio = k / t.k;
  return { k, x: at.x - (at.x - t.x) * ratio, y: at.y - (at.y - t.y) * ratio };
}

/** The transform that fits `bounds` into a width × height viewport with padding. */
export function fitTransform(
  bounds: Bounds,
  width: number,
  height: number,
  padding = 48,
  maxScale = 1.6,
): Transform {
  const contentWidth = Math.max(1, bounds.maxX - bounds.minX);
  const contentHeight = Math.max(1, bounds.maxY - bounds.minY);
  const k = clampScale(
    Math.min(
      (width - padding * 2) / contentWidth,
      (height - padding * 2) / contentHeight,
      maxScale,
    ),
    0.05,
  );
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { k, x: width / 2 - cx * k, y: height / 2 - cy * k };
}

export function toScreen(t: Transform, point: Point): Point {
  return { x: point.x * t.k + t.x, y: point.y * t.k + t.y };
}

interface Gesture {
  start: Transform;
  origin: Point;
  distance: number | null;
  midpoint: Point | null;
}

export interface PanZoomOptions {
  svgRef: RefObject<SVGSVGElement | null>;
  enabled: boolean;
  onUserTransform?: () => void;
}

export function usePanZoom({ svgRef, enabled, onUserTransform }: PanZoomOptions) {
  const [transform, setTransform] = useState<Transform>(IDENTITY);
  const [isPanning, setIsPanning] = useState(false);
  const transformRef = useRef(transform);
  transformRef.current = transform;
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<Gesture | null>(null);
  const dragged = useRef(false);
  const onUserTransformRef = useRef(onUserTransform);
  onUserTransformRef.current = onUserTransform;

  const localPoint = useCallback(
    (clientX: number, clientY: number): Point => {
      const rect = svgRef.current?.getBoundingClientRect();
      return { x: clientX - (rect?.left ?? 0), y: clientY - (rect?.top ?? 0) };
    },
    [svgRef],
  );

  const beginGesture = useCallback(() => {
    const points = [...pointers.current.values()];
    const [a, b] = points;
    gesture.current = {
      start: transformRef.current,
      origin: a ?? { x: 0, y: 0 },
      distance: a && b ? Math.hypot(b.x - a.x, b.y - a.y) : null,
      midpoint: a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : null,
    };
  }, []);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!enabled || (event.pointerType === "mouse" && event.button !== 0)) return;
      pointers.current.set(event.pointerId, localPoint(event.clientX, event.clientY));
      dragged.current = false;
      beginGesture();
    },
    [enabled, localPoint, beginGesture],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!pointers.current.has(event.pointerId) || !gesture.current) return;
      pointers.current.set(event.pointerId, localPoint(event.clientX, event.clientY));
      const g = gesture.current;
      const points = [...pointers.current.values()];

      if (points.length >= 2 && g.distance && g.midpoint) {
        const [a, b] = points as [Point, Point];
        const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        const zoomed = zoomAt(g.start, Math.hypot(b.x - a.x, b.y - a.y) / g.distance, g.midpoint);
        dragged.current = true;
        setTransform({
          ...zoomed,
          x: zoomed.x + midpoint.x - g.midpoint.x,
          y: zoomed.y + midpoint.y - g.midpoint.y,
        });
        onUserTransformRef.current?.();
        return;
      }

      const current = points[0];
      if (!current) return;
      const dx = current.x - g.origin.x;
      const dy = current.y - g.origin.y;
      if (!dragged.current && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      if (!dragged.current) {
        dragged.current = true;
        setIsPanning(true);
        svgRef.current?.setPointerCapture?.(event.pointerId);
      }
      setTransform({ ...g.start, x: g.start.x + dx, y: g.start.y + dy });
      onUserTransformRef.current?.();
    },
    [localPoint, svgRef],
  );

  const onPointerEnd = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!pointers.current.delete(event.pointerId)) return;
      if (svgRef.current?.hasPointerCapture?.(event.pointerId)) {
        svgRef.current.releasePointerCapture(event.pointerId);
      }
      if (pointers.current.size > 0) beginGesture();
      else {
        gesture.current = null;
        setIsPanning(false);
      }
    },
    [svgRef, beginGesture],
  );

  // Wheel listeners must be non-passive to prevent page scrolling, so they are attached
  // manually (React registers wheel handlers as passive).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !enabled) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 0.05 : 0.0015;
      const factor = Math.exp(-event.deltaY * unit * (event.ctrlKey ? 2 : 1));
      setTransform((t) => zoomAt(t, factor, localPoint(event.clientX, event.clientY)));
      onUserTransformRef.current?.();
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [svgRef, enabled, localPoint]);

  const zoomBy = useCallback(
    (factor: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      const center = { x: (rect?.width ?? 0) / 2, y: (rect?.height ?? 0) / 2 };
      setTransform((t) => zoomAt(t, factor, center));
      onUserTransformRef.current?.();
    },
    [svgRef],
  );

  const wasDragged = useCallback(() => dragged.current, []);

  return {
    transform,
    setTransform,
    zoomBy,
    wasDragged,
    isPanning,
    handlers: enabled
      ? {
          onPointerDown,
          onPointerMove,
          onPointerUp: onPointerEnd,
          onPointerCancel: onPointerEnd,
        }
      : {},
  };
}
