/**
 * Layout of a model's input-to-output pathway: a layered drawing, read top to bottom.
 *
 * 1. **Layers by distance to the result.** A node's layer is set by the longest path from
 *    it to a final output, so every node sits as close as possible to what it feeds
 *    (inputs appear just above the variable they change, not all in the first row).
 * 2. **Placeholder points** carry any link that skips a layer, so it runs beside the
 *    nodes of that layer instead of through them.
 * 3. **Ordering** within a layer by the average position of neighbours (a few sweeps
 *    down and up), which keeps crossings low.
 *
 * Pure: the same pathway and width always give the same drawing.
 */

export interface PathwayNodeInput {
  id: string;
}

export interface PathwayLinkInput {
  source: string;
  target: string;
}

export interface LaidNode<N> {
  node: N;
  layer: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface LaidLink<L> {
  link: L;
  layer: number;
  points: Point[];
}

export interface PathwayLayout<N, L> {
  nodes: LaidNode<N>[];
  links: LaidLink<L>[];
  width: number;
  height: number;
  layers: number;
  /** False when even the narrowest nodes do not fit the width: show the list instead. */
  fits: boolean;
}

export interface LayoutOptions {
  width: number;
  nodeWidth?: number;
  minNodeWidth?: number;
  nodeHeight?: number;
  columnGap?: number;
  rowGap?: number;
  placeholderWidth?: number;
}

interface Slot {
  id: string;
  real: boolean;
}

const SWEEPS = 4;

function distancesToSinks(ids: string[], outgoing: Map<string, string[]>): Map<string, number> {
  const distance = new Map<string, number>();
  const visiting = new Set<string>();
  const visit = (id: string): number => {
    const known = distance.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0; // a cycle: the pathway should be acyclic; never loop
    visiting.add(id);
    let longest = 0;
    for (const target of outgoing.get(id) ?? []) longest = Math.max(longest, visit(target) + 1);
    visiting.delete(id);
    distance.set(id, longest);
    return longest;
  };
  for (const id of ids) visit(id);
  return distance;
}

export function layoutPathway<N extends PathwayNodeInput, L extends PathwayLinkInput>(
  nodes: readonly N[],
  links: readonly L[],
  options: LayoutOptions,
): PathwayLayout<N, L> {
  const {
    width,
    nodeWidth = 184,
    minNodeWidth = 144,
    nodeHeight = 72,
    columnGap = 20,
    rowGap = 52,
    placeholderWidth = 12,
  } = options;
  const known = new Map(nodes.map((node) => [node.id, node]));
  const usable = links.filter((link) => known.has(link.source) && known.has(link.target));
  const ids = nodes.map((node) => node.id);
  const outgoing = new Map<string, string[]>();
  for (const link of usable) {
    outgoing.set(link.source, [...(outgoing.get(link.source) ?? []), link.target]);
  }

  const distance = distancesToSinks(ids, outgoing);
  const deepest = Math.max(0, ...distance.values());
  const layerOf = new Map(ids.map((id) => [id, deepest - (distance.get(id) ?? 0)]));
  const layerCount = deepest + 1;

  // Rows of slots: real nodes in definition order, then placeholders for long links.
  const rows: Slot[][] = Array.from({ length: layerCount }, () => []);
  for (const id of ids) rows[layerOf.get(id) ?? 0]?.push({ id, real: true });
  const chains = usable.map((link, index) => {
    const from = layerOf.get(link.source) ?? 0;
    const to = layerOf.get(link.target) ?? 0;
    const chain = [link.source];
    for (let layer = from + 1; layer < to; layer += 1) {
      const id = `placeholder:${index}:${layer}`;
      rows[layer]?.push({ id, real: false });
      chain.push(id);
    }
    chain.push(link.target);
    return chain;
  });

  // Neighbours across adjacent layers (through placeholders), for ordering.
  const above = new Map<string, string[]>();
  const below = new Map<string, string[]>();
  for (const chain of chains) {
    for (let index = 1; index < chain.length; index += 1) {
      const upper = chain[index - 1] as string;
      const lower = chain[index] as string;
      below.set(upper, [...(below.get(upper) ?? []), lower]);
      above.set(lower, [...(above.get(lower) ?? []), upper]);
    }
  }
  const position = new Map<string, number>();
  const index = () => {
    for (const row of rows) {
      row.forEach((slot, place) => {
        position.set(slot.id, place);
      });
    }
  };
  index();
  const reorder = (row: Slot[], neighbours: Map<string, string[]>) => {
    const keyed = row.map((slot, place) => {
      const around = neighbours.get(slot.id) ?? [];
      const mean =
        around.length > 0
          ? around.reduce((sum, id) => sum + (position.get(id) ?? 0), 0) / around.length
          : place;
      return { slot, mean, place };
    });
    keyed.sort((a, b) => a.mean - b.mean || a.place - b.place);
    row.splice(0, row.length, ...keyed.map((entry) => entry.slot));
  };
  for (let sweep = 0; sweep < SWEEPS; sweep += 1) {
    for (let layer = 1; layer < layerCount; layer += 1) {
      reorder(rows[layer] as Slot[], above);
      index();
    }
    for (let layer = layerCount - 2; layer >= 0; layer -= 1) {
      reorder(rows[layer] as Slot[], below);
      index();
    }
  }

  // Widths: shrink nodes to fit, down to the minimum.
  const rowWidth = (row: Slot[], w: number) =>
    row.reduce((sum, slot) => sum + (slot.real ? w : placeholderWidth), 0) +
    Math.max(0, row.length - 1) * columnGap;
  const widest = (w: number) => Math.max(0, ...rows.map((row) => rowWidth(row, w)));
  let chosen = nodeWidth;
  while (chosen > minNodeWidth && widest(chosen) > width) chosen -= 4;
  const layoutWidth = Math.max(widest(chosen), 1);
  const fits = widest(chosen) <= width;

  const centres = new Map<string, Point>();
  const laidNodes: LaidNode<N>[] = [];
  rows.forEach((row, layer) => {
    const y = layer * (nodeHeight + rowGap);
    let x = (Math.max(width, layoutWidth) - rowWidth(row, chosen)) / 2;
    for (const slot of row) {
      const slotWidth = slot.real ? chosen : placeholderWidth;
      centres.set(slot.id, { x: x + slotWidth / 2, y });
      if (slot.real) {
        const node = known.get(slot.id);
        if (node) laidNodes.push({ node, layer, x, y, width: chosen, height: nodeHeight });
      }
      x += slotWidth + columnGap;
    }
  });

  const laidLinks: LaidLink<L>[] = usable.map((link, linkIndex) => {
    const chain = chains[linkIndex] ?? [];
    const points: Point[] = [];
    chain.forEach((id, place) => {
      const centre = centres.get(id);
      if (!centre) return;
      if (place === 0) points.push({ x: centre.x, y: centre.y + nodeHeight });
      else if (place === chain.length - 1) points.push({ x: centre.x, y: centre.y });
      else {
        points.push({ x: centre.x, y: centre.y });
        points.push({ x: centre.x, y: centre.y + nodeHeight });
      }
    });
    return { link, layer: layerOf.get(link.source) ?? 0, points };
  });

  return {
    nodes: laidNodes,
    links: laidLinks,
    width: Math.max(width, layoutWidth),
    height: layerCount * nodeHeight + (layerCount - 1) * rowGap,
    layers: layerCount,
    fits,
  };
}

/** A smooth path through `points`: vertical tangents at every point, like a flow. */
export function smoothPath(points: readonly Point[]): string {
  const [first, ...rest] = points;
  if (!first) return "";
  let d = `M${first.x.toFixed(1)} ${first.y.toFixed(1)}`;
  let previous = first;
  for (const point of rest) {
    if (point.x === previous.x) {
      d += ` L${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    } else {
      const middle = (previous.y + point.y) / 2;
      d +=
        ` C${previous.x.toFixed(1)} ${middle.toFixed(1)}` +
        ` ${point.x.toFixed(1)} ${middle.toFixed(1)}` +
        ` ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    }
    previous = point;
  }
  return d;
}
