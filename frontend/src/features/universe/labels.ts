/**
 * Which names to write on the canvas, and where.
 *
 * Labels are placed greedily by priority — the strata's names, then the selection, the node
 * under the pointer, the focus and an overlay's nodes, then the selection's neighbours, then
 * the most connected nodes (a legibility choice when space runs out, not a claim that they
 * matter more). A name starts just beyond its node's edge, on the right if it fits and on
 * the left otherwise. It is left out when it would overlap a name already placed, cover
 * another node, or leave the canvas — except that names at or above the `essential`
 * priority (the host passes the selection, the pointer, the focus and an overlay's nodes)
 * may also sit just above or below the node's middle, and cover other nodes when there is
 * no free place, so they are named whenever a place is clear of other names.
 * The strata's names are shifted inside the canvas rather than left out. Every name stays
 * readable in the side panel and the list view.
 */

export type Side = "right" | "left";

export interface LabelCandidate {
  id: string;
  text: string;
  /** The anchor on screen: the node's centre, or a stratum guide's edge. */
  x: number;
  y: number;
  /** In front of the camera and inside the view. */
  visible: boolean;
  priority: number;
  /** Distance from the camera: nearer labels win ties. */
  depth: number;
  /** The node's radius on screen, in pixels: the name starts just beyond it. */
  radius?: number;
  /** The sides the name may take, in order (default: right, then left). */
  sides?: readonly Side[];
  /** Shift the name inside the canvas instead of leaving it out. */
  clamp?: boolean;
  /** Average character width, for names set wider than the default (tracked capitals). */
  charWidth?: number;
}

/** A node's disc on screen, which names of other nodes keep clear of. */
export interface Obstacle {
  id: string;
  x: number;
  y: number;
  r: number;
}

export interface PlacedLabel {
  id: string;
  text: string;
  /** Where the name's box starts: its left edge on the right side, its right edge on the left. */
  x: number;
  /** The name's centre line. */
  y: number;
  side: Side;
}

export interface LabelOptions {
  max?: number;
  charWidth?: number;
  lineHeight?: number;
  /** The gap between a node's edge and its name. */
  gap?: number;
  obstacles?: readonly Obstacle[];
  /** From this priority up, a name may cover other nodes when no side is free. */
  essential?: number;
}

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const overlaps = (a: Box, b: Box) =>
  a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

function covers(box: Box, circle: Obstacle): boolean {
  const x = Math.max(box.left, Math.min(circle.x, box.right));
  const y = Math.max(box.top, Math.min(circle.y, box.bottom));
  return Math.hypot(circle.x - x, circle.y - y) < circle.r;
}

const CELL = 48;

/** The obstacles bucketed by screen cell, so a box is checked only against its neighbours. */
function obstacleGrid(obstacles: readonly Obstacle[]) {
  const cells = new Map<string, Obstacle[]>();
  for (const obstacle of obstacles) {
    for (
      let cx = Math.floor((obstacle.x - obstacle.r) / CELL);
      cx <= Math.floor((obstacle.x + obstacle.r) / CELL);
      cx += 1
    ) {
      for (
        let cy = Math.floor((obstacle.y - obstacle.r) / CELL);
        cy <= Math.floor((obstacle.y + obstacle.r) / CELL);
        cy += 1
      ) {
        const key = `${cx},${cy}`;
        const list = cells.get(key);
        if (list) list.push(obstacle);
        else cells.set(key, [obstacle]);
      }
    }
  }
  return (box: Box, except: string): boolean => {
    for (let cx = Math.floor(box.left / CELL); cx <= Math.floor(box.right / CELL); cx += 1) {
      for (let cy = Math.floor(box.top / CELL); cy <= Math.floor(box.bottom / CELL); cy += 1) {
        for (const obstacle of cells.get(`${cx},${cy}`) ?? []) {
          if (obstacle.id !== except && covers(box, obstacle)) return true;
        }
      }
    }
    return false;
  };
}

export function placeLabels(
  candidates: readonly LabelCandidate[],
  width: number,
  height: number,
  {
    max = 36,
    charWidth = 6.4,
    lineHeight = 16,
    gap = 5,
    obstacles = [],
    essential = 900,
  }: LabelOptions = {},
): PlacedLabel[] {
  const ordered = candidates
    .filter((candidate) => candidate.visible && candidate.text)
    .sort(
      (a, b) =>
        b.priority - a.priority || a.depth - b.depth || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
    );
  const placed: PlacedLabel[] = [];
  const boxes: Box[] = [];
  const blocked = obstacleGrid(obstacles);
  for (const candidate of ordered) {
    if (placed.length >= max) break;
    const textWidth = Math.min(candidate.text.length, 40) * (candidate.charWidth ?? charWidth) + 8;
    const offset = (candidate.radius ?? 0) + gap;
    const isEssential = candidate.priority >= essential;
    // An essential name may also sit just above or below its node's middle.
    const shifts = isEssential ? [0, -lineHeight, lineHeight] : [0];
    const options = shifts.flatMap((shift) =>
      (candidate.sides ?? ["right", "left"]).map((side) => {
        let left = side === "right" ? candidate.x + offset : candidate.x - offset - textWidth;
        if (candidate.clamp) left = Math.max(0, Math.min(left, width - textWidth));
        const top = candidate.y + shift - lineHeight / 2;
        return { side, box: { left, right: left + textWidth, top, bottom: top + lineHeight } };
      }),
    );
    const inside = ({ box }: { box: Box }) =>
      box.left >= 0 && box.right <= width && box.top >= 0 && box.bottom <= height;
    const free = ({ box }: { box: Box }) => !boxes.some((taken) => overlaps(box, taken));
    const clear = ({ box }: { box: Box }) => !blocked(box, candidate.id);
    const choice =
      options.find((option) => inside(option) && free(option) && clear(option)) ??
      (isEssential ? options.find((option) => inside(option) && free(option)) : undefined);
    if (!choice) continue;
    boxes.push(choice.box);
    placed.push({
      id: candidate.id,
      text: candidate.text,
      x: choice.side === "right" ? choice.box.left : choice.box.right,
      y: (choice.box.top + choice.box.bottom) / 2,
      side: choice.side,
    });
  }
  return placed;
}
