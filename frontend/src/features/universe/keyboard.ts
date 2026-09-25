/**
 * Keyboard use of the universe, without a pointer.
 *
 * Arrow keys move the selection to the nearest node in that direction **on the screen**, so
 * the keys follow what the reader sees whichever way the camera faces. Shift with an arrow
 * rotates the view. The other keys: Enter focuses the selection, E expands it, C collapses
 * it, + and − zoom, R (or Home) resets the view, Escape clears the selection.
 */

export type Direction = "left" | "right" | "up" | "down";

export type KeyAction =
  | { type: "move"; direction: Direction }
  | { type: "rotate"; theta: number; phi: number }
  | { type: "zoom"; factor: number }
  | { type: "focus" }
  | { type: "expand" }
  | { type: "collapse" }
  | { type: "reset" }
  | { type: "clear" };

export interface KeyInput {
  key: string;
  shiftKey?: boolean;
  altKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
}

const ARROWS: Record<string, Direction> = {
  ArrowLeft: "left",
  ArrowRight: "right",
  ArrowUp: "up",
  ArrowDown: "down",
};

export const ROTATE_STEP = 0.2;
export const TILT_STEP = 0.12;

/** What a key press asks for, or null for keys the universe leaves to the browser. */
export function keyAction(event: KeyInput): KeyAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  const direction = ARROWS[event.key];
  if (direction) {
    if (!event.shiftKey) return { type: "move", direction };
    if (direction === "left") return { type: "rotate", theta: -ROTATE_STEP, phi: 0 };
    if (direction === "right") return { type: "rotate", theta: ROTATE_STEP, phi: 0 };
    return { type: "rotate", theta: 0, phi: direction === "up" ? -TILT_STEP : TILT_STEP };
  }
  switch (event.key) {
    case "+":
    case "=":
      return { type: "zoom", factor: 0.85 };
    case "-":
    case "_":
      return { type: "zoom", factor: 1 / 0.85 };
    case "Enter":
      return { type: "focus" };
    case "e":
    case "E":
      return { type: "expand" };
    case "c":
    case "C":
      return { type: "collapse" };
    case "r":
    case "R":
    case "Home":
      return { type: "reset" };
    case "Escape":
      return { type: "clear" };
    default:
      return null;
  }
}

export interface ScreenPoint {
  id: string;
  x: number;
  y: number;
  /** In front of the camera and inside the view. */
  visible: boolean;
}

const UNIT: Record<Direction, { x: number; y: number }> = {
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
};

/**
 * The node to move to from `from` in `direction`: the closest one within a cone of about 60°
 * either side, measuring distance along the direction plus twice the distance across it;
 * failing that, the closest one anywhere in that half of the screen.
 */
export function nearestInDirection(
  from: { x: number; y: number },
  points: readonly ScreenPoint[],
  direction: Direction,
  exclude: string | null = null,
): string | null {
  const unit = UNIT[direction];
  let best: { id: string; score: number } | null = null;
  let fallback: { id: string; score: number } | null = null;
  for (const point of points) {
    if (!point.visible || point.id === exclude) continue;
    const dx = point.x - from.x;
    const dy = point.y - from.y;
    const along = dx * unit.x + dy * unit.y;
    if (along <= 1) continue;
    const across = Math.abs(dx * unit.y - dy * unit.x);
    const score = along + 2 * across;
    if (across <= along * 1.75) {
      if (!best || score < best.score || (score === best.score && point.id < best.id)) {
        best = { id: point.id, score };
      }
    } else if (!fallback || score < fallback.score) {
      fallback = { id: point.id, score };
    }
  }
  return best?.id ?? fallback?.id ?? null;
}
