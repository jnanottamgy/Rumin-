/**
 * The advanced analyses' forms as data: what each row holds, the starting point offered for a
 * distribution, the requests the forms send, and how their values are written.
 *
 * Numbers stay exact decimal strings; the arithmetic for a starting point is exact
 * (`lib/decimal`). The browser checks only that numbers are plain decimals and in order —
 * the backend checks every range, precision and model rule and says why when it refuses.
 */
import {
  addDecimals,
  compareDecimals,
  formatRounded,
  multiplyDecimals,
  roundDecimal,
} from "@/lib/decimal";
import type {
  AnalysisMetric,
  AnalysisTarget,
  DistributionInput,
  JointSensitivityRequest,
  LabSensitivityRequest,
  MonteCarloRequest,
} from "@/types/api";
import { compactMoney, metricChange, metricValue, unitShort } from "./format";

export type DistributionKind = "uniform" | "triangular" | "discrete";

export interface QuantityDraft {
  target: string;
  kind: DistributionKind;
  low: string;
  mode: string;
  high: string;
  /** Discrete values and weights, comma-separated as typed. */
  values: string;
  weights: string;
}

export interface MonteCarloDraft {
  metric: string;
  draws: string;
  seed: string;
  threshold: string;
  quantities: QuantityDraft[];
}

export interface AxisDraft {
  target: string;
  /** Comma-separated values; empty for the model's default variation. */
  values: string;
}

const PLAIN = /^-?\d+(\.\d+)?$/;
const MAX_SEED = 2 ** 53 - 1;

export function isPlainNumber(text: string): boolean {
  return PLAIN.test(text.trim());
}

/** "0, 3, 6" → ["0", "3", "6"]; null when any item is not a plain decimal. */
export function parseList(text: string): string[] | null {
  const items = text
    .split(/[,;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.every(isPlainNumber) ? items : null;
}

// --- Starting points ------------------------------------------------------------------------

function step(target: AnalysisTarget): string {
  return target.integer ? "1" : `0.${"0".repeat(Math.max(0, target.max_decimals - 1))}1`;
}

/** The value, moved inside the input's range if it lies outside (a strict bound moves one
 * step in), and rounded to the input's decimals. */
export function clampToRange(value: string, target: AnalysisTarget): string {
  let result = roundDecimal(value, target.integer ? 0 : target.max_decimals) ?? value;
  const unit = step(target);
  if (target.minimum !== null) {
    const floor = target.minimum_exclusive
      ? (addDecimals(target.minimum, unit) ?? target.minimum)
      : target.minimum;
    if ((compareDecimals(result, floor) ?? 0) < 0) result = floor;
  }
  if (target.maximum !== null) {
    const ceiling = target.maximum_exclusive
      ? (addDecimals(target.maximum, `-${unit}`) ?? target.maximum)
      : target.maximum;
    if ((compareDecimals(result, ceiling) ?? 0) > 0) result = ceiling;
  }
  return result;
}

/** The low and high values of the model's default variation around the execution's value. */
export function variationBounds(target: AnalysisTarget): [string, string] | null {
  const variation = target.default_variation;
  if (!variation) return null;
  const base = target.base_value;
  if (variation.mode === "absolute") {
    const low = addDecimals(base, `-${variation.step}`);
    const high = addDecimals(base, variation.step);
    return low && high ? [low, high] : null;
  }
  const fraction = multiplyDecimals(variation.step, "0.01");
  if (!fraction) return null;
  const low = multiplyDecimals(base, addDecimals("1", `-${fraction}`) ?? "1");
  const high = multiplyDecimals(base, addDecimals("1", fraction) ?? "1");
  return low && high ? [low, high] : null;
}

/**
 * A distribution to start from: uniform over the model's default variation (discrete low,
 * as executed and high for whole months), kept inside the input's range. A starting point
 * only — the user's assumption to edit, never an estimate.
 */
export function startingPoint(target: AnalysisTarget): QuantityDraft {
  const bounds = variationBounds(target);
  const base = target.base_value;
  if (target.integer) {
    const around = bounds ?? [addDecimals(base, "-1") ?? base, addDecimals(base, "1") ?? base];
    const values = [
      ...new Set([clampToRange(around[0], target), base, clampToRange(around[1], target)]),
    ];
    return {
      target: target.id,
      kind: "discrete",
      low: "",
      mode: "",
      high: "",
      values: values.join(", "),
      weights: "",
    };
  }
  const [low, high] = bounds
    ? [clampToRange(bounds[0], target), clampToRange(bounds[1], target)]
    : ["", ""];
  // A range that collapses (a relative variation around zero) is left for the user to state.
  const collapsed = low !== "" && (compareDecimals(low, high) ?? 0) >= 0;
  if (collapsed) {
    return {
      target: target.id,
      kind: "uniform",
      low: "",
      mode: base,
      high: "",
      values: "",
      weights: "",
    };
  }
  return { target: target.id, kind: "uniform", low, mode: base, high, values: "", weights: "" };
}

// --- Requests -------------------------------------------------------------------------------

export interface Built<T> {
  request: T | null;
  errors: string[];
}

function distribution(
  draft: QuantityDraft,
  label: string,
  errors: string[],
): DistributionInput | null {
  if (draft.kind === "discrete") {
    const values = parseList(draft.values);
    const weights = draft.weights.trim() ? parseList(draft.weights) : null;
    if (!values || values.length < 2) {
      errors.push(`${label}: give at least two values, separated by commas.`);
      return null;
    }
    if (draft.weights.trim() && (!weights || weights.length !== values.length)) {
      errors.push(`${label}: give one weight per value, or none for equal weights.`);
      return null;
    }
    return weights ? { kind: "discrete", values, weights } : { kind: "discrete", values };
  }
  const low = draft.low.trim();
  const high = draft.high.trim();
  if (!isPlainNumber(low) || !isPlainNumber(high)) {
    errors.push(`${label}: the low and high values must be plain numbers such as 10 or -2.5.`);
    return null;
  }
  if ((compareDecimals(low, high) ?? 0) >= 0) {
    errors.push(`${label}: the low value must be below the high value.`);
    return null;
  }
  if (draft.kind === "uniform") return { kind: "uniform", low, high };
  const mode = draft.mode.trim();
  if (!isPlainNumber(mode)) {
    errors.push(`${label}: the most likely value must be a plain number.`);
    return null;
  }
  if ((compareDecimals(mode, low) ?? 0) < 0 || (compareDecimals(mode, high) ?? 0) > 0) {
    errors.push(`${label}: the most likely value must lie between the low and high values.`);
    return null;
  }
  return { kind: "triangular", low, mode, high };
}

export function monteCarloRequest(
  draft: MonteCarloDraft,
  labels: ReadonlyMap<string, string>,
): Built<MonteCarloRequest> {
  const errors: string[] = [];
  if (draft.quantities.length === 0) errors.push("Give at least one quantity a distribution.");
  const quantities = draft.quantities.flatMap((item) => {
    const shaped = distribution(item, labels.get(item.target) ?? item.target, errors);
    return shaped ? [{ target: item.target, distribution: shaped }] : [];
  });
  const draws = Number(draft.draws);
  if (!/^\d+$/.test(draft.draws.trim()) || draws < 100 || draws > 2000) {
    errors.push("Choose between 100 and 2,000 draws.");
  }
  const seedText = draft.seed.trim();
  const seed = seedText ? Number(seedText) : null;
  if (
    seedText &&
    (!/^\d+$/.test(seedText) || !Number.isSafeInteger(seed) || (seed ?? 0) > MAX_SEED)
  ) {
    errors.push("A seed is a whole number from 0 to 9,007,199,254,740,991, or empty.");
  }
  const threshold = draft.threshold.trim();
  if (threshold && !isPlainNumber(threshold)) errors.push("The threshold must be a plain number.");
  if (errors.length) return { request: null, errors };
  return {
    request: {
      kind: "monte_carlo",
      metric: draft.metric || null,
      draws,
      seed,
      threshold: threshold || null,
      quantities,
    },
    errors,
  };
}

function axis(draft: AxisDraft, label: string, errors: string[]) {
  if (!draft.target) {
    errors.push(`Choose the ${label}.`);
    return null;
  }
  if (!draft.values.trim()) return { target: draft.target, mode: "default" as const, values: [] };
  const values = parseList(draft.values);
  if (!values) {
    errors.push(`The ${label}' values must be plain numbers, separated by commas.`);
    return null;
  }
  if (values.length > 6) {
    errors.push(`At most six values for the ${label} (the execution's own value is added).`);
    return null;
  }
  return { target: draft.target, mode: "values" as const, values };
}

export function jointRequest(
  metric: string,
  rows: AxisDraft,
  columns: AxisDraft,
): Built<JointSensitivityRequest> {
  const errors: string[] = [];
  const row = axis(rows, "rows", errors);
  const column = axis(columns, "columns", errors);
  if (rows.target && rows.target === columns.target)
    errors.push("Choose two different quantities.");
  if (errors.length || !row || !column) return { request: null, errors };
  return {
    request: { kind: "joint_sensitivity", metric: metric || null, rows: row, columns: column },
    errors,
  };
}

type SensitivityInput = NonNullable<LabSensitivityRequest["inputs"]>[number];

export function sensitivityRequest(
  metric: string,
  chosen: readonly AxisDraft[],
  labels: ReadonlyMap<string, string>,
): Built<LabSensitivityRequest> {
  const errors: string[] = [];
  const inputs: SensitivityInput[] = [];
  for (const item of chosen) {
    if (!item.values.trim()) {
      inputs.push({ target: item.target, mode: "default" });
      continue;
    }
    const values = parseList(item.values);
    if (!values || values.length > 7) {
      const label = labels.get(item.target) ?? item.target;
      errors.push(`${label}: give up to seven plain numbers, separated by commas.`);
      continue;
    }
    inputs.push({ target: item.target, mode: "values", values });
  }
  if (errors.length) return { request: null, errors };
  return { request: { metric: metric || null, inputs }, errors };
}

// --- Writing values -------------------------------------------------------------------------

/** The unit a line or metric is written in. */
export function metricUnit(metric: string): "currency" | "ratio" | "times" {
  if (metric === "operating_margin") return "ratio";
  if (metric === "interest_coverage") return "times";
  return "currency";
}

/** A value of the analysed line (its change, money) or metric (margin, coverage). */
export function formatMetric(value: string | null | undefined, metric: string): string {
  if (value === null || value === undefined) return "—";
  const unit = metricUnit(metric);
  return unit === "currency" ? compactMoney(value) : metricValue(value, unit);
}

/** A difference in the analysed line or metric: money, percentage points or times. */
export function formatMetricChange(value: string | null | undefined, metric: string): string {
  if (value === null || value === undefined) return "—";
  const unit = metricUnit(metric);
  return unit === "currency" ? compactMoney(value) : metricChange(value, unit);
}

/** A quantity's value in its unit: "20 %", "0.5 pp", "3 months", "80 INR per USD". */
export function formatQuantity(
  value: string,
  target: Pick<AnalysisTarget, "unit" | "unit_label" | "max_decimals">,
): string {
  const text = formatRounded(value, Math.max(target.max_decimals, 0));
  const short = unitShort(target.unit);
  // A unit with a short form uses it (possibly none, e.g. an elasticity); others their label.
  const unit = short !== (target.unit ?? "") ? short : target.unit_label;
  if (!unit) return text;
  return unit === "%" ? `${text} %` : `${text} ${unit}`;
}

/** A share of draws as a percentage: "0.974" → "97.4 %". */
export function formatShare(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const percent = multiplyDecimals(value, "100");
  return percent === null ? value : `${formatRounded(percent, 1)} %`;
}

/** The metric to analyse by default: profit before tax when interest is modelled. */
export function defaultMetric(metrics: readonly AnalysisMetric[]): string {
  return (
    metrics.find((item) => item.id === "profit_before_tax")?.id ??
    metrics.find((item) => item.id === "operating_profit")?.id ??
    metrics[0]?.id ??
    ""
  );
}
