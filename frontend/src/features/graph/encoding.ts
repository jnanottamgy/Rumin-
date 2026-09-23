/**
 * Visual encoding of the knowledge graph — the one place that decides what marks mean.
 *
 * - **Node type → shape**, in neutral ink. Nine types on one canvas are too many for hue,
 *   and shape survives colour-blindness, greyscale print and forced-colours mode. The four
 *   types the Financial Universe already shows keep its shapes (company dot, industry ring,
 *   variable diamond, country square).
 * - **Nature → outer ring**: dashed for fictional records (the sample network), dotted for
 *   sample data, none for real records.
 * - **Data availability → fill** (series and instruments): filled when values are stored,
 *   hollow when only the definition exists.
 * - **Evidence status → line pattern**: solid (evidence-backed), dashes (analyst-created),
 *   dash-dot (model assumption) or dots (unverified). Never colour.
 * - **Direction → arrowhead**; **category → weight** (economic relationships are heavier).
 * - **Sky blue means emphasis only**: the selection and what it connects to.
 */
import type {
  EvidenceStatus,
  GraphEdgeSummary,
  GraphNodeSummary,
  GraphNodeType,
  NodeNature,
} from "@/types/api";

export type GlyphShape =
  | "dot"
  | "ring"
  | "diamond"
  | "square"
  | "hexagon"
  | "target"
  | "pill"
  | "triangle"
  | "invertedTriangle";

export interface NodeTypeEncoding {
  label: string;
  plural: string;
  shape: GlyphShape;
  /** Hollow shapes are outlined; data-bearing types switch between the two (see `isHollow`). */
  hollow: boolean;
  baseRadius: number;
}

export const NODE_TYPE_ENCODING: Record<GraphNodeType, NodeTypeEncoding> = {
  economic_variable: {
    label: "Economic variable",
    plural: "Economic variables",
    shape: "diamond",
    hollow: false,
    baseRadius: 6,
  },
  company: { label: "Company", plural: "Companies", shape: "dot", hollow: false, baseRadius: 4.5 },
  industry: {
    label: "Industry",
    plural: "Industries",
    shape: "ring",
    hollow: true,
    baseRadius: 6.5,
  },
  sector: { label: "Sector", plural: "Sectors", shape: "hexagon", hollow: true, baseRadius: 7 },
  country: {
    label: "Country",
    plural: "Countries",
    shape: "square",
    hollow: true,
    baseRadius: 6.5,
  },
  currency: {
    label: "Currency",
    plural: "Currencies",
    shape: "target",
    hollow: true,
    baseRadius: 6,
  },
  data_series: {
    label: "Data series",
    plural: "Data series",
    shape: "pill",
    hollow: false,
    baseRadius: 5,
  },
  instrument: {
    label: "Instrument",
    plural: "Instruments",
    shape: "triangle",
    hollow: false,
    baseRadius: 6,
  },
  market: {
    label: "Market",
    plural: "Markets",
    shape: "invertedTriangle",
    hollow: true,
    baseRadius: 6.5,
  },
};

/** Display order: the order the API lists types in. */
export const NODE_TYPE_ORDER: readonly GraphNodeType[] = [
  "country",
  "currency",
  "sector",
  "industry",
  "company",
  "economic_variable",
  "data_series",
  "instrument",
  "market",
];

const TYPE_RANK = new Map(NODE_TYPE_ORDER.map((type, index) => [type, index]));

/** Node keys start with a type prefix (`company:…`, `series:…`); see the API docs. */
const KEY_PREFIX_TYPE: Record<string, GraphNodeType> = {
  country: "country",
  currency: "currency",
  sector: "sector",
  industry: "industry",
  company: "company",
  variable: "economic_variable",
  series: "data_series",
  instrument: "instrument",
  market: "market",
};

export const NODE_KEY_PATTERN =
  /^(country|currency|sector|industry|company|variable|series|instrument|market):[a-z0-9][a-z0-9_.-]{0,95}$/;

/**
 * A link to the explorer focused on a record's node, or null when the record id cannot
 * form a node key. Keys are `<prefix>:<record id in lower case>`, as the build makes them.
 */
export function graphHref(
  prefix: "country" | "industry" | "company" | "variable" | "series" | "instrument",
  recordId: string,
): string | null {
  const key = `${prefix}:${recordId.toLowerCase()}`;
  return NODE_KEY_PATTERN.test(key) ? `/graph?focus=${encodeURIComponent(key)}` : null;
}

/** The node type a key names, or null when the key is not a valid node key. */
export function typeFromKey(key: string): GraphNodeType | null {
  if (!NODE_KEY_PATTERN.test(key)) return null;
  return KEY_PREFIX_TYPE[key.slice(0, key.indexOf(":"))] ?? null;
}

export function typeRank(type: GraphNodeType): number {
  return TYPE_RANK.get(type) ?? NODE_TYPE_ORDER.length;
}

/** Series and instruments are drawn hollow when only their definition is stored. */
export function isHollow(node: Pick<GraphNodeSummary, "type" | "data_status">): boolean {
  if (node.data_status === "definition_only") return true;
  if (node.data_status === "values_stored") return false;
  return NODE_TYPE_ENCODING[node.type].hollow;
}

/** Size grows gently with connectedness (square root), so hubs stay readable. */
export function nodeRadius(type: GraphNodeType, degree: number): number {
  return NODE_TYPE_ENCODING[type].baseRadius + 0.9 * Math.sqrt(Math.max(0, Math.min(degree, 64)));
}

const round = (value: number) => Math.round(value * 100) / 100;

function polygon(points: readonly (readonly [number, number])[]): string {
  return `${points.map(([x, y], index) => `${index ? "L" : "M"}${round(x)} ${round(y)}`).join(" ")} Z`;
}

/**
 * SVG path for a glyph of "radius" r centred on the origin. Circles (dot, ring, target)
 * are drawn with <circle>, so they return null.
 */
export function glyphPath(shape: GlyphShape, r: number): string | null {
  switch (shape) {
    case "diamond": {
      const d = r * 1.25;
      return polygon([
        [0, -d],
        [d, 0],
        [0, d],
        [-d, 0],
      ]);
    }
    case "square": {
      const s = r * 0.9;
      return polygon([
        [-s, -s],
        [s, -s],
        [s, s],
        [-s, s],
      ]);
    }
    case "hexagon":
      return polygon(
        Array.from({ length: 6 }, (_, index) => {
          const angle = (Math.PI / 3) * index;
          return [Math.cos(angle) * r * 1.05, Math.sin(angle) * r * 1.05] as const;
        }),
      );
    case "pill": {
      const w = r * 1.35;
      const h = r * 0.72;
      return `M${round(-w + h)} ${round(-h)} H${round(w - h)} A${round(h)} ${round(h)} 0 0 1 ${round(w - h)} ${round(h)} H${round(-w + h)} A${round(h)} ${round(h)} 0 0 1 ${round(-w + h)} ${round(-h)} Z`;
    }
    case "triangle": {
      const t = r * 1.2;
      return polygon([
        [0, -t],
        [t * 0.95, t * 0.65],
        [-t * 0.95, t * 0.65],
      ]);
    }
    case "invertedTriangle": {
      const t = r * 1.2;
      return polygon([
        [0, t],
        [-t * 0.95, -t * 0.65],
        [t * 0.95, -t * 0.65],
      ]);
    }
    default:
      return null;
  }
}

// --- Nature --------------------------------------------------------------------------------

export interface NatureEncoding {
  label: string;
  short: string;
  /** Outer ring dash pattern; null: no ring (real records). */
  ringDash: string | null;
  description: string;
}

export const NATURE_ENCODING: Record<NodeNature, NatureEncoding> = {
  real: {
    label: "Real record",
    short: "Real",
    ringDash: null,
    description: "Describes something that exists, from reference data or a provider catalogue.",
  },
  fictional: {
    label: "Fictional",
    short: "Fictional",
    ringDash: "3 2.2",
    description: "Part of the fictional sample network. It says nothing about the real world.",
  },
  sample: {
    label: "Sample data",
    short: "Sample",
    ringDash: "0.1 2.6",
    description: "Built from sample (synthetic) data shipped for demonstrations and tests.",
  },
};

// --- Evidence status --------------------------------------------------------------------------

export interface EvidenceEncoding {
  label: string;
  /** SVG stroke-dasharray; null: solid. */
  dash: string | null;
  linecap: "round" | "butt";
  /** One line for legends and tooltips; the API supplies the full definition. */
  summary: string;
}

export const EVIDENCE_ENCODING: Record<EvidenceStatus, EvidenceEncoding> = {
  evidence_backed: {
    label: "Evidence-backed",
    dash: null,
    linecap: "round",
    summary: "Stated by a cited source record or a published classification.",
  },
  analyst_created: {
    label: "Analyst-created",
    dash: "7 3.5",
    linecap: "butt",
    summary: "Recorded by a curator in the reference data; not independently verified.",
  },
  model_assumption: {
    label: "Model assumption",
    dash: "6 2.5 1.2 2.5",
    linecap: "butt",
    summary: "An assumed relationship with a written rationale; not an empirical finding.",
  },
  unverified: {
    label: "Unverified",
    dash: "0.1 3.4",
    linecap: "round",
    summary: "Declared by an importer or file manifest; RUMIN has not checked it.",
  },
};

export const EVIDENCE_ORDER: readonly EvidenceStatus[] = [
  "evidence_backed",
  "analyst_created",
  "model_assumption",
  "unverified",
];

/** Economic relationships are drawn heavier than structural links. */
export function edgeWidth(edge: Pick<GraphEdgeSummary, "category">): number {
  return edge.category === "economic" ? 1.6 : 1.1;
}

// --- Words ----------------------------------------------------------------------------------

export function typeLabel(type: GraphNodeType): string {
  return NODE_TYPE_ENCODING[type].label;
}

export function pluralLabel(type: GraphNodeType, count: number): string {
  const { label, plural } = NODE_TYPE_ENCODING[type];
  return count === 1 ? label.toLowerCase() : plural.toLowerCase();
}

export const DATA_STATUS_LABEL: Record<GraphNodeSummary["data_status"], string | null> = {
  values_stored: "Values stored",
  definition_only: "Definition only — no values stored",
  not_applicable: null,
};

export const POLARITY_TEXT: Record<string, string> = {
  positive: "Assumed positive (↑ raises the target measure)",
  negative: "Assumed negative (↑ lowers the target measure)",
  mixed: "Assumed mixed (either direction, depending on circumstances)",
  not_applicable: "Not applicable",
};

export const STRENGTH_TEXT: Record<string, string> = {
  weak: "Weak (ordinal, illustrative — not measured)",
  moderate: "Moderate (ordinal, illustrative — not measured)",
  strong: "Strong (ordinal, illustrative — not measured)",
};

/** "Aerisca Airways — operates in → Air transport" (arrow only for directed edges). */
export function edgeSentence(sourceName: string, edge: GraphEdgeSummary, targetName: string) {
  return `${sourceName} — ${edge.label} ${edge.directed ? "→" : "↔"} ${targetName}`;
}
