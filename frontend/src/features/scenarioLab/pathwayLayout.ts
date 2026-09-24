/**
 * Layout of the impact pathway: pure geometry, unit-tested without rendering.
 *
 * Four columns, left to right: the scenario's changes → the variables each model moved →
 * the model's line items → the Lab's lines, with the metrics under them. Every model has a
 * horizontal lane holding its variables and line items, so a model's part of the pathway
 * reads as one band and can be collapsed to a single node. The graph context a model cites
 * (the relationships that made it apply) is not drawn as a step, because no value travels
 * along it: each lane carries its cited links, which the canvas lists in the lane header.
 * Changes, lines and metrics sit outside the lanes, each placed as close as possible to
 * the average height of what it connects to, without overlapping.
 */
import type { LabPathway, LabPathwayLink, LabPathwayNode } from "@/types/api";

export const NODE_HEIGHT = 54;
export const ROW = 64;
const TOP = 30;
/** Title row, plus a second row when the lane cites graph context. */
const LANE_TITLE = 24;
const LANE_CONTEXT = 18;
const LANE_PAD = 8;
const LANE_INSET = 12;
const LANE_GAP = 14;
/** Room above the metrics for their sub-heading. */
const METRICS_GAP = 26;
/** Horizontal room between columns, for the links. */
const MIN_GAP = 44;
const MAX_GAP = 120;
/** Room right of the last column for links between its own nodes. */
const RIGHT = 40;
const MIN_NODE = 120;
const MAX_NODE = 200;

export type ColumnId = "change" | "variable" | "driver" | "outcome";

const COLUMN_LABEL: Record<ColumnId, string> = {
  change: "Changes",
  variable: "Variables moved",
  driver: "Line items",
  outcome: "Lines",
};

const LINE_ORDER = [
  "line:revenue",
  "line:operating_costs",
  "line:operating_profit",
  "line:interest_expense",
  "line:profit_before_tax",
];

export interface Column {
  id: ColumnId;
  label: string;
  x: number;
  width: number;
}

export interface PlacedNode {
  id: string;
  node: LabPathwayNode | null;
  /** Set for a collapsed model: the node stands for the whole lane. */
  group: string | null;
  collapsed: boolean;
  column: ColumnId;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedLink {
  id: string;
  source: string;
  target: string;
  links: LabPathwayLink[];
  path: string;
  mid: { x: number; y: number };
  /** Both ends in one column: drawn as an arc outside its right edge. */
  arc: boolean;
}

export interface Lane {
  id: string;
  title: string;
  version: string;
  collapsed: boolean;
  /** The graph relationships the model cites: why it applies. No value travels along them. */
  context: LabPathwayLink[];
  y: number;
  height: number;
  x: number;
  width: number;
}

export interface Heading {
  text: string;
  x: number;
  y: number;
}

export interface PathwayLayout {
  width: number;
  height: number;
  columns: Column[];
  /** Sub-headings inside a column (the metrics under the lines). */
  headings: Heading[];
  lanes: Lane[];
  nodes: PlacedNode[];
  links: PlacedLink[];
}

/** The column a node is drawn in, or null for graph context, which is not drawn as a step. */
export function columnOf(node: LabPathwayNode): ColumnId | null {
  switch (node.kind) {
    case "change":
    case "variable":
    case "driver":
      return node.kind;
    case "line":
    case "metric":
      return "outcome";
    default:
      return null;
  }
}

/** Positions for `items` near their wanted tops, at least `ROW` apart, within bounds. */
function spread(
  wanted: { id: string; y: number }[],
  top: number,
  bottom: number,
): Map<string, number> {
  const sorted = [...wanted].sort((a, b) => a.y - b.y);
  const placed: { id: string; y: number }[] = [];
  for (const item of sorted) {
    const previous = placed[placed.length - 1];
    placed.push({ id: item.id, y: previous ? Math.max(item.y, previous.y + ROW) : item.y });
  }
  // Shift everything back inside the bounds when the sweep pushed past the bottom.
  const last = placed[placed.length - 1];
  const overflow = last ? last.y + NODE_HEIGHT - bottom : 0;
  if (overflow > 0) {
    for (let index = placed.length - 1; index >= 0; index -= 1) {
      const item = placed[index];
      const next = placed[index + 1];
      if (!item) continue;
      const limit = next ? next.y - ROW : bottom - NODE_HEIGHT;
      item.y = Math.min(item.y, limit);
    }
  }
  const first = placed[0];
  if (first && first.y < top) {
    const shift = top - first.y;
    for (const item of placed) item.y += shift;
  }
  return new Map(placed.map((item) => [item.id, item.y]));
}

function curve(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  maxBulge: number,
): { path: string; mid: { x: number; y: number } } {
  if (x2 > x1 + 4) {
    const dx = Math.max(24, (x2 - x1) * 0.45);
    return {
      path: `M${x1} ${y1}C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`,
      mid: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 },
    };
  }
  // Same column: an arc outside the right edge, wider the further apart the ends are, so
  // arcs between nearer nodes nest inside the others.
  const bulge = Math.min(maxBulge, Math.max(12, Math.abs(y2 - y1) * 0.3));
  return {
    path: `M${x1} ${y1}C${x1 + bulge} ${y1} ${x2 + bulge} ${y2} ${x2} ${y2}`,
    mid: { x: Math.max(x1, x2) + bulge * 0.75, y: (y1 + y2) / 2 },
  };
}

function average(values: number[], fallback: number): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : fallback;
}

export function layoutPathway(
  pathway: LabPathway,
  { width, collapsed = new Set<string>() }: { width: number; collapsed?: ReadonlySet<string> },
): PathwayLayout {
  const present = new Set(pathway.nodes.map(columnOf).filter((id): id is ColumnId => id !== null));
  const order: ColumnId[] = ["change", "variable", "driver", "outcome"];
  const used = order.filter((id) => present.has(id));
  const count = Math.max(1, used.length);
  const nodeWidth = Math.max(
    MIN_NODE,
    Math.min(MAX_NODE, (width - RIGHT - MIN_GAP * (count - 1)) / count),
  );
  // Wide frames: nodes stop growing and the gaps take the rest.
  const gap =
    count > 1
      ? Math.max(MIN_GAP, Math.min(MAX_GAP, (width - RIGHT - nodeWidth * count) / (count - 1)))
      : 0;
  const columns: Column[] = used.map((id, index) => ({
    id,
    label: COLUMN_LABEL[id],
    x: index * (nodeWidth + gap),
    width: nodeWidth,
  }));
  const columnX = new Map(columns.map((column) => [column.id, column.x]));
  const layoutWidth = count * nodeWidth + (count - 1) * gap + RIGHT;

  // Which lane each node sits in: its model.
  const laneOf = new Map<string, string>();
  for (const node of pathway.nodes) {
    if (node.group && (node.kind === "variable" || node.kind === "driver")) {
      laneOf.set(node.id, node.group);
    }
  }

  const placed = new Map<string, PlacedNode>();
  const lanes: Lane[] = [];
  const laneColumns: ColumnId[] = ["variable", "driver"];
  const laneXs = laneColumns
    .map((id) => columnX.get(id))
    .filter((x): x is number => x !== undefined);
  const laneLeft = laneXs.length ? Math.min(...laneXs) : 0;
  const laneRight = laneXs.length ? Math.max(...laneXs) + nodeWidth : nodeWidth;
  let y = TOP;
  for (const group of pathway.groups) {
    const members = pathway.nodes.filter((node) => laneOf.get(node.id) === group.id);
    const context = pathway.links.filter(
      (link) => link.kind === "cited" && link.group === group.id,
    );
    const isCollapsed = collapsed.has(group.id);
    const byColumn = new Map<ColumnId, LabPathwayNode[]>();
    for (const node of members) {
      const column = columnOf(node);
      if (column) byColumn.set(column, [...(byColumn.get(column) ?? []), node]);
    }
    const rows = isCollapsed
      ? 1
      : Math.max(1, ...[...byColumn.values()].map((list) => list.length));
    const header = LANE_TITLE + (context.length ? LANE_CONTEXT : 0);
    const height = header + LANE_PAD * 2 + rows * ROW - (ROW - NODE_HEIGHT);
    const laneTop = y;
    const rowsTop = laneTop + header + LANE_PAD;
    if (isCollapsed) {
      placed.set(`group:${group.id}`, {
        id: `group:${group.id}`,
        node: null,
        group: group.id,
        collapsed: true,
        column: "driver",
        x: laneLeft,
        y: rowsTop,
        width: laneRight - laneLeft,
        height: NODE_HEIGHT,
      });
    } else {
      for (const [column, list] of byColumn) {
        const offset = ((rows - list.length) * ROW) / 2;
        list.forEach((node, index) => {
          placed.set(node.id, {
            id: node.id,
            node,
            group: group.id,
            collapsed: false,
            column,
            x: columnX.get(column) ?? 0,
            y: rowsTop + offset + index * ROW,
            width: nodeWidth,
            height: NODE_HEIGHT,
          });
        });
      }
    }
    lanes.push({
      id: group.id,
      title: group.title,
      version: group.version,
      collapsed: isCollapsed,
      context,
      y: laneTop,
      height,
      x: laneLeft - LANE_INSET,
      width: laneRight - laneLeft + LANE_INSET * 2,
    });
    y += height + LANE_GAP;
  }
  const lanesBottom = Math.max(TOP + NODE_HEIGHT, y - LANE_GAP);

  // Where a node sits for links: itself, or its collapsed lane.
  const anchor = (id: string): string => {
    const lane = laneOf.get(id);
    return lane && collapsed.has(lane) ? `group:${lane}` : id;
  };
  const topOf = (id: string): number | undefined => placed.get(anchor(id))?.y;
  const bottom = lanesBottom;

  // Changes: near the average height of what they feed.
  const changes = pathway.nodes.filter((node) => node.kind === "change");
  const wantedChanges = changes.map((node, index) => {
    const targets = pathway.links
      .filter((link) => link.source === node.id)
      .map((link) => topOf(link.target))
      .filter((value): value is number => value !== undefined);
    return { id: node.id, y: average(targets, TOP + index * ROW) };
  });
  const changeTops = spread(wantedChanges, TOP, Math.max(bottom, TOP + changes.length * ROW));
  for (const node of changes) {
    placed.set(node.id, {
      id: node.id,
      node,
      group: null,
      collapsed: false,
      column: "change",
      x: columnX.get("change") ?? 0,
      y: changeTops.get(node.id) ?? TOP,
      width: nodeWidth,
      height: NODE_HEIGHT,
    });
  }

  // Lines: near the average height of their sources, kept in accounting order.
  const rank = (id: string) => {
    const index = LINE_ORDER.indexOf(id);
    return index === -1 ? LINE_ORDER.length : index;
  };
  const lines = pathway.nodes
    .filter((node) => node.kind === "line")
    .sort((a, b) => rank(a.id) - rank(b.id));
  let floor = Number.NEGATIVE_INFINITY;
  const wantedLines = lines.map((node) => {
    const sources = pathway.links
      .filter((link) => link.target === node.id)
      .map((link) => topOf(link.source))
      .filter((value): value is number => value !== undefined);
    const value = Math.max(average(sources, TOP), floor);
    floor = value + ROW;
    return { id: node.id, y: value };
  });
  const lineTops = spread(wantedLines, TOP, Math.max(bottom, TOP + lines.length * ROW));
  for (const node of lines) {
    placed.set(node.id, {
      id: node.id,
      node,
      group: null,
      collapsed: false,
      column: "outcome",
      x: columnX.get("outcome") ?? 0,
      y: lineTops.get(node.id) ?? TOP,
      width: nodeWidth,
      height: NODE_HEIGHT,
    });
  }

  // Metrics: under the lines they are computed from, with a sub-heading.
  const headings: Heading[] = [];
  const metrics = pathway.nodes.filter((node) => node.kind === "metric");
  if (metrics.length) {
    const lastLine = Math.max(TOP - ROW, ...lines.map((node) => placed.get(node.id)?.y ?? TOP));
    const first = lastLine + ROW + METRICS_GAP;
    headings.push({ text: "Metrics", x: columnX.get("outcome") ?? 0, y: first - 10 });
    metrics.forEach((node, index) => {
      placed.set(node.id, {
        id: node.id,
        node,
        group: null,
        collapsed: false,
        column: "outcome",
        x: columnX.get("outcome") ?? 0,
        y: first + index * ROW,
        width: nodeWidth,
        height: NODE_HEIGHT,
      });
    });
  }

  // Links, re-routed to collapsed lanes; links inside a collapsed lane disappear, and
  // links to graph context, which is not drawn as a step, are left to the lane header.
  const merged = new Map<string, PlacedLink>();
  const lastColumn = used[used.length - 1];
  for (const link of pathway.links) {
    if (link.kind === "cited") continue;
    const source = anchor(link.source);
    const target = anchor(link.target);
    if (source === target) continue;
    const from = placed.get(source);
    const to = placed.get(target);
    if (!from || !to) continue;
    const id = `${source}→${target}`;
    const existing = merged.get(id);
    if (existing) {
      existing.links.push(link);
      continue;
    }
    const arc = from.column === to.column && !from.collapsed && !to.collapsed;
    const x1 = from.x + from.width;
    const y1 = from.y + NODE_HEIGHT / 2;
    const x2 = arc ? to.x + to.width : to.x;
    const y2 = to.y + NODE_HEIGHT / 2;
    // An arc stays in the room right of its column: inside the lane for line items.
    const room =
      from.column === lastColumn ? RIGHT : from.column === "driver" ? LANE_INSET - 2 : gap;
    const { path, mid } = curve(x1, y1, x2, y2, Math.max(12, (room - 4) / 0.75));
    merged.set(id, { id, source, target, links: [link], path, mid, arc });
  }

  const nodes = [...placed.values()];
  const height = Math.max(...nodes.map((node) => node.y + NODE_HEIGHT), lanesBottom) + 24;
  return {
    width: layoutWidth,
    height,
    columns,
    headings,
    lanes,
    nodes,
    links: [...merged.values()],
  };
}

/**
 * The nodes and links upstream and/or downstream of `id`: the chain a step belongs to.
 */
export function chainOf(
  layout: PathwayLayout,
  id: string,
  directions: readonly ("up" | "down")[] = ["up", "down"],
): { nodes: Set<string>; links: Set<string> } {
  const nodes = new Set([id]);
  const links = new Set<string>();
  for (const direction of directions) {
    const frontier = [id];
    while (frontier.length) {
      const current = frontier.pop() as string;
      for (const link of layout.links) {
        const [from, to] =
          direction === "down" ? [link.source, link.target] : [link.target, link.source];
        if (from !== current) continue;
        links.add(link.id);
        if (!nodes.has(to)) {
          nodes.add(to);
          frontier.push(to);
        }
      }
    }
  }
  return { nodes, links };
}
