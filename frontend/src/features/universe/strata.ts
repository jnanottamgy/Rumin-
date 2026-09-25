/**
 * The universe's strata: each kind of node sits on a horizontal layer, so height says what a
 * node *is* — never how large or important it is.
 *
 * The order follows the Financial Universe's columns (Phase 1), turned upright: drivers at
 * the top, then industries, companies and, at the base, the places they are domiciled and
 * the currencies those places use. The data RUMIN holds values for sits above the drivers
 * it measures. An assumed effect therefore reads downwards: a variable affects an industry's
 * or a company's costs.
 *
 * Kind is also given by shape, in every panel and in the list view: position is never the
 * only channel.
 */
import type { GraphNodeType } from "@/types/api";

export type StratumId = "data" | "drivers" | "industries" | "companies" | "places";

export interface Stratum {
  id: StratumId;
  label: string;
  description: string;
  /** Height in strata, top (2) to base (−2). */
  level: number;
  types: readonly GraphNodeType[];
}

export const STRATA: readonly Stratum[] = [
  {
    id: "data",
    label: "Data",
    description: "Series, instruments and markets RUMIN stores or describes values for",
    level: 2,
    types: ["data_series", "instrument", "market"],
  },
  {
    id: "drivers",
    label: "Drivers",
    description: "Economic variables",
    level: 1,
    types: ["economic_variable"],
  },
  {
    id: "industries",
    label: "Industries",
    description: "Sectors and industries",
    level: 0,
    types: ["sector", "industry"],
  },
  {
    id: "companies",
    label: "Companies",
    description: "Companies",
    level: -1,
    types: ["company"],
  },
  {
    id: "places",
    label: "Places",
    description: "Countries and currencies",
    level: -2,
    types: ["country", "currency"],
  },
];

/** World units between two strata. */
export const STRATUM_GAP = 70;

const BY_TYPE = new Map<GraphNodeType, Stratum>(
  STRATA.flatMap((stratum) => stratum.types.map((type) => [type, stratum] as const)),
);

export function stratumOf(type: GraphNodeType): Stratum {
  const found = BY_TYPE.get(type);
  if (!found) throw new Error(`No stratum for node type ${type}`);
  return found;
}

/** The height of a node of this type. */
export function heightOf(type: GraphNodeType): number {
  return stratumOf(type).level * STRATUM_GAP;
}
