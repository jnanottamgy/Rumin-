/**
 * Edge geometry shared by every network renderer (interactive canvas and landing figure).
 */
import { nodeRadius } from "./encoding";
import type { Layout, Point } from "./layout";
import type { GraphEdge, GraphModel } from "./model";

export interface EdgeGeometry {
  d: string;
  mid: Point;
}

/**
 * Geometry of one edge. Edges between columns are straight; edges within a column
 * (e.g. company → company) would run through the nodes between their ends, so they
 * are drawn as arcs that bow sideways. `bend` is the arc's sideways offset (0 = straight).
 * Both ends are trimmed along the curve's tangent so arrowheads stop at the node edge.
 */
export function edgeGeometry(
  source: Point,
  target: Point,
  rs: number,
  rt: number,
  directed: boolean,
  bend: number,
  axis: "x" | "y" = "x",
): EdgeGeometry {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const length = Math.hypot(dx, dy) || 1;
  // Unit normal oriented towards +axis, so a positive bend always bows the same way
  // (right for columns, down for rows) whichever way the edge points.
  const normal = { x: -dy / length, y: dx / length };
  const flip = (axis === "x" ? normal.x : normal.y) < 0 ? -1 : 1;
  const control = {
    x: (source.x + target.x) / 2 + flip * normal.x * bend,
    y: (source.y + target.y) / 2 + flip * normal.y * bend,
  };
  const unit = (x: number, y: number) => {
    const size = Math.hypot(x, y) || 1;
    return { x: x / size, y: y / size };
  };
  const startTangent = unit(control.x - source.x, control.y - source.y);
  const endTangent = unit(target.x - control.x, target.y - control.y);
  const startGap = rs + 1.5;
  const endGap = rt + (directed ? 4 : 1.5);
  const x1 = source.x + startTangent.x * startGap;
  const y1 = source.y + startTangent.y * startGap;
  const x2 = target.x - endTangent.x * endGap;
  const y2 = target.y - endTangent.y * endGap;
  const round = (value: number) => Math.round(value * 10) / 10;
  const d =
    bend === 0
      ? `M${round(x1)} ${round(y1)} L${round(x2)} ${round(y2)}`
      : `M${round(x1)} ${round(y1)} Q${round(control.x)} ${round(control.y)} ${round(x2)} ${round(y2)}`;
  // Point at t = 0.5 on the (quadratic) curve, used to anchor the edge tooltip.
  const mid = {
    x: 0.25 * source.x + 0.5 * control.x + 0.25 * target.x,
    y: 0.25 * source.y + 0.5 * control.y + 0.25 * target.y,
  };
  return { d, mid };
}

/**
 * Same-column edges bow inwards — towards the centre of the layout — because labels
 * point outwards; this keeps arcs and labels on opposite sides of each column.
 */
function bendFor(edge: GraphEdge, model: GraphModel, layout: Layout, source: Point, target: Point) {
  const sourceKind = model.nodeById.get(edge.source)?.kind;
  if (!sourceKind || sourceKind !== model.nodeById.get(edge.target)?.kind) return 0;
  const vertical = layout.orientation === "vertical";
  const span = vertical ? Math.abs(target.x - source.x) : Math.abs(target.y - source.y);
  const size = Math.min(110, Math.max(20, span * 0.3));
  const [low, high] = vertical
    ? [layout.bounds.minY, layout.bounds.maxY]
    : [layout.bounds.minX, layout.bounds.maxX];
  const across = vertical ? (source.y + target.y) / 2 : (source.x + target.x) / 2;
  return across < (low + high) / 2 ? size : -size;
}

export function geometryFor(
  edge: GraphEdge,
  model: GraphModel,
  layout: Layout,
): EdgeGeometry | null {
  const source = layout.positions.get(edge.source);
  const target = layout.positions.get(edge.target);
  const sourceNode = model.nodeById.get(edge.source);
  const targetNode = model.nodeById.get(edge.target);
  if (!source || !target || !sourceNode || !targetNode) return null;
  return edgeGeometry(
    source,
    target,
    nodeRadius(sourceNode.kind, sourceNode.degree),
    nodeRadius(targetNode.kind, targetNode.degree),
    edge.directed,
    bendFor(edge, model, layout, source, target),
    layout.orientation === "vertical" ? "y" : "x",
  );
}
