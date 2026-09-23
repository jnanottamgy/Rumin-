/**
 * Moves nodes from where they were drawn to where the layout now puts them, so a change
 * can be followed: new nodes grow out of the node that brought them into view, and nodes
 * already on screen glide to their new places. The motion explains the change and lasts
 * under half a second; with reduced motion (the system setting or RUMIN's own preference)
 * positions change at once.
 */
import { useLayoutEffect, useRef, useState } from "react";
import type { Point } from "./layout";

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;

export function interpolate(
  from: ReadonlyMap<string, Point>,
  to: ReadonlyMap<string, Point>,
  t: number,
): Map<string, Point> {
  const result = new Map<string, Point>();
  for (const [id, end] of to) {
    const start = from.get(id) ?? end;
    result.set(id, { x: start.x + (end.x - start.x) * t, y: start.y + (end.y - start.y) * t });
  }
  return result;
}

/** Where each node starts: where it was drawn, else where its origin was drawn. */
export function startPositions(
  displayed: ReadonlyMap<string, Point>,
  target: ReadonlyMap<string, Point>,
  originOf: (id: string) => string | undefined,
): Map<string, Point> {
  const start = new Map<string, Point>();
  for (const [id, end] of target) {
    const origin = originOf(id);
    start.set(
      id,
      displayed.get(id) ??
        (origin ? (displayed.get(origin) ?? target.get(origin)) : undefined) ??
        end,
    );
  }
  return start;
}

export function useAnimatedPositions(
  target: ReadonlyMap<string, Point>,
  originOf: (id: string) => string | undefined,
  { animate, duration = 420 }: { animate: boolean; duration?: number },
): ReadonlyMap<string, Point> {
  const [frame, setFrame] = useState<ReadonlyMap<string, Point>>(target);
  const displayed = useRef<ReadonlyMap<string, Point>>(target);
  const originRef = useRef(originOf);
  originRef.current = originOf;

  useLayoutEffect(() => {
    const canAnimate = animate && typeof window.requestAnimationFrame === "function";
    if (!canAnimate) {
      displayed.current = target;
      setFrame(target);
      return;
    }
    const from = startPositions(displayed.current, target, originRef.current);
    let raf = 0;
    const started = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - started) / duration);
      const next = t >= 1 ? target : interpolate(from, target, easeOutCubic(t));
      displayed.current = next;
      setFrame(next);
      if (t < 1) raf = window.requestAnimationFrame(step);
    };
    // First frame now, so nodes never flash at their final position before moving.
    displayed.current = from;
    setFrame(from);
    raf = window.requestAnimationFrame(step);
    // A new layout (or unmounting) stops the running animation.
    return () => window.cancelAnimationFrame(raf);
  }, [target, animate, duration]);

  return frame;
}
