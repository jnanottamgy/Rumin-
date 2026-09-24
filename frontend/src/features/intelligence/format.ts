/**
 * Words and links for Financial Intelligence. Every value arrives from the API as an exact
 * decimal string; these helpers only round for display, group digits and choose words —
 * nothing is calculated in the browser.
 */
import { formatRounded, isDecimalString } from "@/lib/decimal";
import type { EvidenceBasis, EvidenceGrade, IntelligenceRef } from "@/types/api";

const MINUS = "−";

export function signed(text: string, value: string): string {
  if (text.startsWith(MINUS) || /^0(\.0+)?$/.test(text)) return text;
  return value.trim().startsWith("-") ? text : `+${text}`;
}

/** "−6,700,000 INR": whole units from a thousand up, two decimals below. */
export function money(value: string | null | undefined, currency: string, sign = false): string {
  if (!value || !isDecimalString(value)) return "—";
  const digits = /^-?(\d+)/.exec(value.trim())?.[1]?.replace(/^0+/, "") ?? "";
  const text = formatRounded(value, digits.length >= 4 ? 0 : 2);
  return `${sign ? signed(text, value) : text}${currency ? ` ${currency}` : ""}`;
}

/** "−17.63 %" from a value already in percent. */
export function percent(value: string | null | undefined, sign = true): string {
  if (value === null || value === undefined || !isDecimalString(value)) return "—";
  const text = formatRounded(value, 2);
  return `${sign ? signed(text, value) : text} %`;
}

/** A change in its unit: percent or percentage points. */
export function change(value: string | null | undefined, unit: string): string {
  if (value === null || value === undefined || !isDecimalString(value)) return "—";
  const text = signed(formatRounded(value, 2), value);
  return unit === "percent" ? `${text} %` : `${text} pp`;
}

/** A stored value at its own precision, grouped ("84.2", "1,234.5"). */
export function stored(value: string | null | undefined): string {
  if (value === null || value === undefined || !isDecimalString(value)) return "—";
  return formatRounded(value, 6);
}

// --- Evidence ----------------------------------------------------------------------------

export const GRADE_ORDER: readonly EvidenceGrade[] = [
  "observed",
  "documented",
  "curated",
  "simulated",
  "assumed",
  "unverified",
];

export const GRADE: Record<EvidenceGrade, { label: string; dash: string | null; width: number }> = {
  observed: { label: "Observed", dash: null, width: 3 },
  documented: { label: "Documented", dash: null, width: 1.6 },
  curated: { label: "Curated", dash: "7 3.5", width: 1.6 },
  simulated: { label: "Simulated", dash: "2 2", width: 1.6 },
  assumed: { label: "Assumed", dash: "6 2.5 1.2 2.5", width: 1.6 },
  unverified: { label: "Unverified", dash: "0.1 3.4", width: 1.8 },
};

export const BASIS: Record<EvidenceBasis, string> = {
  observation: "Observation",
  calculation: "Calculation",
  relationship: "Relationship",
  record: "Record",
  simulation: "Simulation",
  assumption: "Assumption",
  threshold: "Threshold",
};

export const KIND: Record<string, string> = {
  anomaly: "Unusual change",
  change: "Observed change",
  exposure_change: "Change on an exposure",
  revision: "Data revision",
  trend: "Trend",
  volatility: "Volatility",
  impact: "Simulated impact",
  interpretation: "Model interpretation",
  contribution: "Contributions",
  sensitivity: "Sensitivity",
  scenario_change: "Between executions",
  relationship_change: "Relationship change",
  cross_entity: "Shared driver",
  exposure: "Stated exposure",
  dependency: "Dependency",
  counterparty: "Supply and credit",
  coverage: "Coverage",
};

export type KindGroup = "observed" | "simulated" | "relationships" | "coverage";

export const GROUPS: readonly { id: KindGroup; label: string; kinds: readonly string[] }[] = [
  {
    id: "observed",
    label: "Observed data",
    kinds: ["anomaly", "change", "exposure_change", "revision", "trend", "volatility"],
  },
  {
    id: "simulated",
    label: "Simulations",
    kinds: ["impact", "interpretation", "contribution", "sensitivity", "scenario_change"],
  },
  {
    id: "relationships",
    label: "Relationships and exposure",
    kinds: ["relationship_change", "cross_entity", "exposure", "dependency", "counterparty"],
  },
  { id: "coverage", label: "Coverage", kinds: ["coverage"] },
];

export function groupOf(kind: string): KindGroup {
  return GROUPS.find((group) => group.kinds.includes(kind))?.id ?? "coverage";
}

export const CHANNEL: Record<string, string> = {
  costs: "Costs",
  revenue: "Revenue",
  financing: "Financing costs",
};

export const CHANNEL_LETTER: Record<string, string> = { costs: "C", revenue: "R", financing: "F" };

export const DIRECTNESS: Record<string, string> = {
  direct: "Direct",
  via_industry: "Through its industry",
  upstream: "Upstream",
};

export const SIGNAL_LEVEL_WORD: Record<string, string> = {
  computed: "Computed",
  insufficient_data: "Not enough data",
  not_applicable: "Not applicable",
};

export const NEXT_STEP: Record<string, string> = {
  run_template: "Simulate",
  run_scenario: "Run a scenario",
  run_sensitivity: "Run a sensitivity analysis",
  ingest_series: "Retrieve data",
  find_evidence: "Find evidence",
  model_gap: "Model gap",
  review_revision: "Review a revision",
};

export const NATURE: Record<string, string> = {
  fictional: "fictional, from RUMIN's sample network",
  real: "a real-world classification",
  sample: "a sample record",
};

// --- Links ---------------------------------------------------------------------------------

export function entityPath(key: string): string {
  return `/intelligence/${encodeURIComponent(key)}`;
}

/** Where a cited record can be opened, when RUMIN has a view of it. */
export function refHref(
  ref: IntelligenceRef,
  scenarios: ReadonlyMap<string, string> = new Map(),
): string | null {
  switch (ref.kind) {
    case "graph_node":
      return ref.id.startsWith("company:") || ref.id.startsWith("industry:")
        ? entityPath(ref.id)
        : `/graph?focus=${encodeURIComponent(ref.id)}`;
    case "series":
      return `/data/series/${encodeURIComponent(ref.id)}`;
    case "instrument":
      return `/data/instruments/${encodeURIComponent(ref.id)}`;
    case "execution": {
      const scenario = scenarios.get(ref.id);
      return scenario
        ? `/scenarios/${encodeURIComponent(scenario)}?execution=${encodeURIComponent(ref.id)}`
        : null;
    }
    case "template":
      return `/scenarios/new?template=${encodeURIComponent(ref.id)}`;
    case "graph_build":
      return "/graph";
    case "catalogue":
      return "/data";
    default:
      return null;
  }
}

const REF_KIND: Record<string, string> = {
  dataset: "Dataset",
  series: "Series",
  observation: "Observation",
  instrument: "Instrument",
  price_bar: "Price",
  graph_build: "Graph build",
  graph_node: "Node",
  graph_edge: "Relationship",
  scenario: "Scenario",
  execution: "Execution",
  run: "Model run",
  sensitivity_analysis: "Sensitivity analysis",
  template: "Template",
  threshold: "Threshold",
  catalogue: "Catalogue",
  calculation: "Calculation",
};

export function refLabel(ref: IntelligenceRef): string {
  const kind = REF_KIND[ref.kind] ?? ref.kind;
  if (ref.kind === "observation" || ref.kind === "price_bar") {
    return `${kind} ${ref.label ?? ""} (record ${ref.id})`.replace("  ", " ");
  }
  if (ref.kind === "run" || ref.kind === "execution") return `${kind} ${ref.id.slice(0, 8)}`;
  if (ref.kind === "graph_edge") return `${kind} ${ref.id}`;
  return ref.label ? `${kind}: ${ref.label}` : `${kind} ${ref.id}`;
}
