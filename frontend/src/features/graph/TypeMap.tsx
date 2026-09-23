/**
 * The explorer's starting view: an aggregate map of the graph — one mark per node *type*,
 * one band per pair of types with the number of relationships between them.
 *
 * It is deliberately drawn unlike the entity canvas (wide pale bands with counts, not
 * thin lines) and labelled as an aggregate, because a band between "Companies" and
 * "Countries" means "12 domiciled-in relationships between some companies and some
 * countries", never that every company is linked to every country.
 */
import { type KeyboardEvent, useMemo, useState } from "react";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import type { GraphNodeType, GraphTypeMapLink, GraphTypeMapNode } from "@/types/api";
import { NODE_TYPE_ENCODING } from "./encoding";
import { GlyphMark } from "./GraphGlyph";
import type { Point } from "./layout";
import styles from "./TypeMap.module.css";

const UNIT = 170;

/** A fixed schema-like arrangement: what affects what on top, reference data below. */
export const TYPE_POSITION: Record<GraphNodeType, Point> = {
  economic_variable: { x: 0, y: 0 },
  company: { x: 1, y: 0 },
  industry: { x: 2, y: 0 },
  sector: { x: 3, y: 0 },
  data_series: { x: 0, y: 1 },
  country: { x: 1, y: 1 },
  currency: { x: 2, y: 1 },
  instrument: { x: 1.5, y: 1.9 },
  market: { x: 2.5, y: 1.9 },
};

export interface TypeLinkGroup {
  key: string;
  source: GraphNodeType;
  target: GraphNodeType;
  count: number;
  items: GraphTypeMapLink[];
}

/** One band per ordered pair of types, summing the relationship types between them. */
export function groupTypeLinks(links: readonly GraphTypeMapLink[]): TypeLinkGroup[] {
  const groups = new Map<string, TypeLinkGroup>();
  for (const link of links) {
    const key = `${link.source_type}>${link.target_type}`;
    const group = groups.get(key);
    if (group) {
      group.count += link.count;
      group.items.push(link);
    } else {
      groups.set(key, {
        key,
        source: link.source_type,
        target: link.target_type,
        count: link.count,
        items: [link],
      });
    }
  }
  for (const group of groups.values()) group.items.sort((a, b) => b.count - a.count);
  return [...groups.values()].sort((a, b) => b.count - a.count);
}

const markRadius = (count: number) => 11 + 3 * Math.sqrt(count);
const bandWidth = (count: number) => Math.min(14, 2.5 + 2.2 * Math.sqrt(count));

function place(type: GraphNodeType): Point {
  const { x, y } = TYPE_POSITION[type];
  return { x: x * UNIT, y: y * UNIT };
}

interface BandGeometry {
  d: string;
  label: Point;
}

function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const t = Math.max(
    0,
    Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy || 1)),
  );
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

function bandGeometry(
  group: TypeLinkGroup,
  present: ReadonlyMap<GraphNodeType, number>,
): BandGeometry {
  const a = place(group.source);
  const b = place(group.target);
  const ra = markRadius(present.get(group.source) ?? 1);
  const rb = markRadius(present.get(group.target) ?? 1);
  const below = TYPE_POSITION[group.source].y > 0.5;

  if (group.source === group.target) {
    // A loop: relationships between two entities of the same type.
    const sign = below ? 1 : -1;
    const lift = ra + 44;
    const start = { x: a.x - ra * 0.55, y: a.y + sign * ra * 0.8 };
    const end = { x: a.x + ra * 0.55, y: a.y + sign * ra * 0.8 };
    return {
      d: `M${start.x} ${start.y} C${a.x - 40} ${a.y + sign * lift} ${a.x + 40} ${a.y + sign * lift} ${end.x} ${end.y}`,
      label: { x: a.x, y: a.y + sign * (lift - 6) },
    };
  }

  // Bow the band sideways when a straight one would run through another type's mark.
  const blocked = [...present.keys()].some(
    (type) =>
      type !== group.source &&
      type !== group.target &&
      distanceToSegment(place(type), a, b) < markRadius(present.get(type) ?? 1) + 10,
  );
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const normal = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length };
  const flip = (below ? normal.y < 0 : normal.y > 0) ? -1 : 1;
  const bend = blocked ? length * 0.58 * flip : 0;
  const control = {
    x: (a.x + b.x) / 2 + normal.x * bend,
    y: (a.y + b.y) / 2 + normal.y * bend,
  };
  const unit = (from: Point, to: Point) => {
    const size = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    return { x: (to.x - from.x) / size, y: (to.y - from.y) / size };
  };
  const u1 = unit(a, control);
  const u2 = unit(control, b);
  const p1 = { x: a.x + u1.x * (ra + 3), y: a.y + u1.y * (ra + 3) };
  const p2 = { x: b.x - u2.x * (rb + 7), y: b.y - u2.y * (rb + 7) };
  return {
    d: bend
      ? `M${p1.x} ${p1.y} Q${control.x} ${control.y} ${p2.x} ${p2.y}`
      : `M${p1.x} ${p1.y} L${p2.x} ${p2.y}`,
    label: {
      x: 0.25 * a.x + 0.5 * control.x + 0.25 * b.x,
      y: 0.25 * a.y + 0.5 * control.y + 0.25 * b.y,
    },
  };
}

export function TypeMap({
  nodes,
  links,
  selectedType,
  onPickType,
}: {
  nodes: readonly GraphTypeMapNode[];
  links: readonly GraphTypeMapLink[];
  selectedType: GraphNodeType | null;
  onPickType: (type: GraphNodeType) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const present = useMemo(
    () => new Map(nodes.filter((node) => node.count > 0).map((node) => [node.type, node.count])),
    [nodes],
  );
  const groups = useMemo(
    () =>
      groupTypeLinks(links).filter(
        (group) => present.has(group.source) && present.has(group.target),
      ),
    [links, present],
  );

  const points = [...present.keys()].map(place);
  const pad = 110;
  const minX = Math.min(...points.map((p) => p.x)) - pad;
  const maxX = Math.max(...points.map((p) => p.x)) + pad;
  const minY = Math.min(...points.map((p) => p.y)) - pad;
  const maxY = Math.max(...points.map((p) => p.y)) + pad;
  const hoveredGroup = groups.find((group) => group.key === hovered) ?? null;

  const onKey = (event: KeyboardEvent<SVGGElement>, type: GraphNodeType) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onPickType(type);
    }
  };

  return (
    <figure className={styles.figure}>
      {/* biome-ignore lint/a11y/useSemanticElements: an SVG figure has no semantic HTML equivalent; "group" names the set of type buttons. */}
      <svg
        className={styles.svg}
        viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
        role="group"
        aria-label="Type map: an aggregate of the graph. Each mark is a kind of node, with how many there are; each band counts the relationships between two kinds. Choose a kind to list its nodes."
      >
        <defs>
          <marker
            id="rumin-typemap-arrow"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="9"
            markerHeight="9"
            markerUnits="userSpaceOnUse"
            orient="auto"
          >
            <path d="M0 1 L9 5 L0 9 Z" className={styles.arrow} />
          </marker>
        </defs>
        <g>
          {groups.map((group) => {
            const geometry = bandGeometry(group, present);
            return (
              <g
                key={group.key}
                className={styles.band}
                data-state={hovered === group.key ? "hover" : undefined}
                onPointerEnter={() => setHovered(group.key)}
                onPointerLeave={() => setHovered(null)}
              >
                <path
                  d={geometry.d}
                  className={styles.bandPath}
                  strokeWidth={bandWidth(group.count)}
                />
                <path
                  d={geometry.d}
                  className={styles.bandCore}
                  markerEnd="url(#rumin-typemap-arrow)"
                />
                <g transform={`translate(${geometry.label.x} ${geometry.label.y})`}>
                  <rect
                    className={styles.countPill}
                    x={-(String(group.count).length * 4 + 7)}
                    y={-9}
                    width={String(group.count).length * 8 + 14}
                    height={18}
                    rx={9}
                  />
                  <text className={styles.count} textAnchor="middle" dy="0.34em">
                    {formatCount(group.count)}
                  </text>
                </g>
              </g>
            );
          })}
        </g>
        <g>
          {[...present.entries()].map(([type, count]) => {
            const point = place(type);
            const encoding = NODE_TYPE_ENCODING[type];
            const r = markRadius(count);
            const selected = type === selectedType;
            return (
              // biome-ignore lint/a11y/useSemanticElements: SVG has no <button>; role + key handling make the mark operable.
              <g
                key={type}
                className={cx(styles.type, selected && styles.selected)}
                transform={`translate(${point.x} ${point.y})`}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                aria-label={`${encoding.plural}: ${formatCount(count)}. List them.`}
                onClick={() => onPickType(type)}
                onKeyDown={(event) => onKey(event, type)}
              >
                <circle className={styles.hit} r={r + 14} />
                <circle className={styles.halo} r={r + 6} />
                <GlyphMark
                  shape={encoding.shape}
                  r={r}
                  hollow={encoding.hollow}
                  className={styles.mark}
                />
                <text className={styles.typeLabel} y={r + 20} textAnchor="middle">
                  {encoding.plural}
                </text>
                <text className={styles.typeCount} y={r + 36} textAnchor="middle">
                  {formatCount(count)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <figcaption className={styles.caption} aria-live="polite">
        {hoveredGroup ? (
          <>
            <strong>
              {NODE_TYPE_ENCODING[hoveredGroup.source].plural} →{" "}
              {NODE_TYPE_ENCODING[hoveredGroup.target].plural}
            </strong>
            {": "}
            {hoveredGroup.items
              .map((item) => `${item.label} (${formatCount(item.count)})`)
              .join(" · ")}
          </>
        ) : (
          <>
            <strong>Aggregate view.</strong> Marks are kinds of node; each band counts relationships
            between two kinds (hover for their types). A band does not link every entity of one kind
            to every entity of the other. Choose a kind to list its nodes.
          </>
        )}
      </figcaption>
    </figure>
  );
}
