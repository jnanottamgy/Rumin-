/**
 * Words for the AI Analyst: the kinds of knowledge evidence can be, statuses, and the
 * citation syntax answers use ([E1], [E1, E4]). Nothing here computes a figure: answers
 * arrive with their figures already written, and tables carry exact decimals from the API.
 */
import type { AnalystAnswer, AnalystEvidence, AnalystKnowledge } from "@/types/api";

export const KNOWLEDGE: Record<AnalystKnowledge, { label: string; note: string }> = {
  observed: { label: "Observed", note: "A stored observation from a cited dataset." },
  record: { label: "RUMIN record", note: "RUMIN's own catalogue, graph or registry." },
  relationship: {
    label: "Relationship",
    note: "A knowledge-graph relationship; its evidence status says what supports it.",
  },
  finding: { label: "Finding", note: "A Financial Intelligence finding, with its grade." },
  user_input: { label: "Entered by a person", note: "Figures typed in the Scenario Lab." },
  assumption: { label: "Assumption", note: "A model assumption or a stated default." },
  simulated: {
    label: "Simulated",
    note: "A stored execution: holds only under its changes, figures and assumptions.",
  },
  preview: { label: "Preview, not stored", note: "Computed on request by the models." },
};

export const STATUS: Record<AnalystAnswer["status"], string> = {
  answered: "Answered",
  partial: "Partly answered",
  no_data: "RUMIN holds no data for this",
  clarification: "Needs a choice",
  declined: "Declined",
  unsupported: "Outside RUMIN's records",
  failed: "Could not be answered",
};

export const STATUS_TONE: Record<AnalystAnswer["status"], "neutral" | "caution" | "quiet"> = {
  answered: "neutral",
  partial: "caution",
  no_data: "caution",
  clarification: "quiet",
  declined: "quiet",
  unsupported: "quiet",
  failed: "caution",
};

export const EVIDENCE_STATUS: Record<string, string> = {
  evidence_backed: "Evidence-backed",
  analyst_created: "Analyst-created",
  model_assumption: "Model assumption",
  unverified: "Unverified",
};

export const TOOL_LABEL: Record<string, string> = {
  search_records: "Search records",
  get_entity_dossier: "Company or industry dossier",
  get_exposure: "Exposure paths",
  get_variable_reach: "Variable reach",
  find_paths: "Graph paths",
  get_relationship: "One relationship",
  get_series: "Stored series",
  compare_periods: "Compare two periods",
  list_changes: "What changed",
  get_findings: "Findings",
  list_scenarios: "Stored scenarios",
  get_execution: "Stored execution",
  explain_line: "Explain a line",
  preview_scenario: "Scenario preview (not stored)",
  list_models: "Models",
  list_templates: "Templates",
  get_data_coverage: "Data coverage",
};

/** A piece of text split into plain runs and citations. */
export type Segment = { kind: "text"; text: string } | { kind: "cite"; ids: string[] };

const CITATION = /\[(E\d+(?:\s*,\s*E\d+)*)\]/g;

export function segments(text: string): Segment[] {
  const found: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > last) found.push({ kind: "text", text: text.slice(last, start) });
    found.push({
      kind: "cite",
      ids: (match[1] ?? "").split(",").map((id) => id.trim()),
    });
    last = start + match[0].length;
  }
  if (last < text.length) found.push({ kind: "text", text: text.slice(last) });
  return found;
}

/** Evidence ids an answer cites, in order of first citation (text, then displays). */
export function citedOrder(answer: AnalystAnswer): string[] {
  const order: string[] = [];
  const add = (ids: readonly string[] | undefined) => {
    for (const id of ids ?? []) if (!order.includes(id)) order.push(id);
  };
  for (const block of answer.blocks) {
    if (block.type === "text" || block.type === "notice") {
      for (const part of segments(block.text)) if (part.kind === "cite") add(part.ids);
    }
    add(block.type === "clarification" ? [] : block.citations);
    if (block.type === "table") for (const row of block.rows) add(row.citations);
    if (block.type === "paths") for (const path of block.paths) add(path.citations);
    if (block.type === "scenario") for (const line of block.lines ?? []) add(line.citations);
  }
  const known = new Set(answer.evidence.map((item) => item.id));
  return order.filter((id) => known.has(id));
}

export function evidenceById(answer: AnalystAnswer): Map<string, AnalystEvidence> {
  return new Map(answer.evidence.map((item) => [item.id, item]));
}

/** Milliseconds as "17 ms" or "1.2 s". */
export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

// --- Figures, written as the Analyst's paragraphs write them -------------------------------
// The paragraphs are written by the API (app/intelligence/fmt.py): half-even rounding and a
// fixed number of places. A card's table uses the same rules, so "+3.60 %" in a sentence is
// "+3.60 %" in the table beside it. Only digits are handled here; nothing is computed.

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
const MINUS = "−";

/** `value` rounded half-even to `places` decimals, grouped, with a typographic minus. */
export function fixed(value: string | null | undefined, places: number): string | null {
  const match = value == null ? null : DECIMAL.exec(value.trim());
  if (!match) return null;
  const [, sign = "", integer = "0", fraction = ""] = match;
  const rest = fraction.slice(places);
  let digits = BigInt(`${integer}${fraction.slice(0, places).padEnd(places, "0")}`);
  const first = rest.charAt(0);
  const beyond = /[1-9]/.test(rest.slice(1));
  if (first > "5" || (first === "5" && (beyond || digits % 2n === 1n))) digits += 1n;
  const text = digits.toString().padStart(places + 1, "0");
  const whole = (places ? text.slice(0, -places) : text).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const negative = sign === "-" && digits !== 0n;
  return `${negative ? MINUS : ""}${whole}${places ? `.${text.slice(-places)}` : ""}`;
}

function withSign(text: string): string {
  return text.startsWith(MINUS) || /^0(\.0+)?$/.test(text) ? text : `+${text}`;
}

/** "+3.60 %", as the paragraphs write a percentage. */
export function percentText(value: string | null | undefined, sign = true): string {
  const text = fixed(value, 2);
  if (text === null) return "—";
  return `${sign ? withSign(text) : text} %`;
}

/** "+3,500,000 INR": whole units when integral or from a thousand up, else two places. */
export function moneyText(
  value: string | null | undefined,
  currency: string,
  sign = false,
): string {
  const match = value == null ? null : DECIMAL.exec(value.trim());
  if (!match) return "—";
  const [, , integer = "0", fraction = ""] = match;
  const whole = /^0*$/.test(fraction) || integer.replace(/^0+/, "").length >= 4;
  const text = fixed(value, whole ? 0 : 2) ?? "—";
  return `${sign ? withSign(text) : text}${currency ? ` ${currency}` : ""}`;
}
