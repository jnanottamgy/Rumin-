/**
 * Visual encoding of the network — the one place that decides what marks mean.
 *
 * Entity kinds are four categories on a canvas where any node can sit next to any other,
 * so kind is encoded by SHAPE (dot, ring, diamond, square) in neutral ink rather than by
 * hue. Sky blue is reserved for emphasis: selection, hover, focus and active edges.
 * Relationship types are far too many for colour; they are told apart by line weight
 * (strength), arrowheads (direction), filters, the legend and the tooltip.
 */
import type { EdgeType, EntityKind, EvidenceLevel, Polarity, Strength } from "@/types/api";

export type NodeShape = "dot" | "ring" | "diamond" | "square";

export interface KindEncoding {
  label: string;
  plural: string;
  shape: NodeShape;
  baseRadius: number;
  description: string;
}

export const KIND_ENCODING: Record<EntityKind, KindEncoding> = {
  economic_variable: {
    label: "Economic variable",
    plural: "Economic variables",
    shape: "diamond",
    baseRadius: 6,
    description: "A measurable macroeconomic or market quantity, such as a price or a rate.",
  },
  industry: {
    label: "Industry",
    plural: "Industries",
    shape: "ring",
    baseRadius: 7,
    description: "An ISIC Rev. 4 industry division.",
  },
  company: {
    label: "Company",
    plural: "Companies",
    shape: "dot",
    baseRadius: 4,
    description: "A company. Every company in the sample dataset is fictional.",
  },
  country: {
    label: "Country",
    plural: "Countries",
    shape: "square",
    baseRadius: 6,
    description: "A country, identified by its ISO 3166-1 code.",
  },
};

/** Node size grows with connectedness, on a square-root scale so hubs stay readable. */
export function nodeRadius(kind: EntityKind, degree: number): number {
  return KIND_ENCODING[kind].baseRadius + 1.35 * Math.sqrt(Math.max(0, degree));
}

/** SVG path for a shape of "radius" r, centred on the origin. Circles use <circle>. */
export function shapePath(shape: "diamond" | "square", r: number): string {
  if (shape === "diamond") {
    const d = r * 1.25;
    return `M0 ${-d} L${d} 0 L0 ${d} L${-d} 0 Z`;
  }
  const s = r * 0.9;
  return `M${-s} ${-s} H${s} V${s} H${-s} Z`;
}

export const STRENGTH_WIDTH: Record<Strength, number> = {
  weak: 1,
  moderate: 1.6,
  strong: 2.3,
};

export const STRENGTH_LABEL: Record<Strength, string> = {
  weak: "Weak",
  moderate: "Moderate",
  strong: "Strong",
};

/** Relationships are always modelling assumptions; evidence says how well supported. */
export const EVIDENCE_LABEL: Record<EvidenceLevel, string> = {
  illustrative: "Illustrative assumption",
  documented: "Documented assumption",
  estimated: "Estimated assumption",
  validated: "Validated assumption",
};

export const POLARITY_LABEL: Record<Polarity, string> = {
  positive: "Positive",
  negative: "Negative",
  mixed: "Mixed",
  not_applicable: "Not applicable",
};

export const POLARITY_SYMBOL: Record<Polarity, string> = {
  positive: "↑",
  negative: "↓",
  mixed: "±",
  not_applicable: "",
};

const MEASURE: Partial<Record<EdgeType, (target: string) => string>> = {
  affects_costs: (target) => `the costs of ${target}`,
  affects_revenue: (target) => `the revenue of ${target}`,
  affects_financing: (target) => `the financing costs of ${target}`,
  influences: (target) => target,
};

/**
 * Plain-language reading of an assumed effect, e.g. "An increase in Brent crude oil
 * price is assumed to raise the costs of Refined petroleum products."
 */
export function describeEffect(
  type: EdgeType,
  polarity: Polarity,
  sourceName: string,
  targetName: string,
): string | null {
  const measure = MEASURE[type];
  if (!measure || polarity === "not_applicable") return null;
  const subject = measure(targetName);
  if (polarity === "mixed") {
    return `A change in ${sourceName} is assumed to move ${subject} in either direction, depending on circumstances.`;
  }
  const verb = polarity === "positive" ? "raise" : "lower";
  return `An increase in ${sourceName} is assumed to ${verb} ${subject}.`;
}
