/**
 * Display formatting for Scenario Lab values. Every value arrives from the API as an exact
 * decimal string; these helpers only move the decimal point, round for display and group
 * digits — nothing is calculated in the browser.
 */
import {
  formatMoney,
  formatRatioPercent,
  shiftDecimal,
  withSign,
} from "@/features/simulation/format";
import { formatRounded, isDecimalString } from "@/lib/decimal";

const SCALES: [number, string][] = [
  [12, "T"],
  [9, "B"],
  [6, "M"],
  [3, "K"],
];

/** A short money figure for tight spaces: "−6.33 M", "+375 K", "12.45 M". */
export function compactMoney(value: string | null | undefined, signed = true): string {
  if (!value || !isDecimalString(value)) return "—";
  const digits = /^-?(\d+)/.exec(value.trim())?.[1]?.replace(/^0+/, "") ?? "";
  for (const [power, suffix] of SCALES) {
    if (digits.length > power) {
      const text = formatRounded(shiftDecimal(value, -power), 2);
      return `${signed ? withSign(text, value) : text} ${suffix}`;
    }
  }
  const text = formatRounded(value, 0);
  return signed ? withSign(text, value) : text;
}

/** A money figure in full, rounded to whole units: "−6,325,000 INR". */
export function fullMoney(
  value: string | null | undefined,
  currency: string,
  signed = false,
): string {
  if (!value || !isDecimalString(value)) return "—";
  return formatMoney(value, currency, { decimals: 0, signed });
}

/** A percentage as the API sends it (already in percent): "-12.65" → "−12.65 %". */
export function percentValue(value: string | null | undefined, signed = true): string {
  if (value === null || value === undefined || !isDecimalString(value)) return "—";
  const text = formatRounded(value, 2);
  return `${signed ? withSign(text, value) : text} %`;
}

/** A scenario change as the user set it: "+20 %", "+0.5 pp", "−10 USD per barrel". */
export function changeLabel(value: string, unit: string): string {
  if (!isDecimalString(value)) return value;
  const text = withSign(formatRounded(value, 4), value);
  if (unit === "%") return `${text} %`;
  if (unit === "percentage points") return `${text} pp`;
  return unit ? `${text} ${unit}` : text;
}

/** Short labels for the unit identifiers the models declare (the rest read as they are). */
const UNIT_SHORT: Record<string, string> = {
  percent: "%",
  percent_change: "%",
  percentage_points: "pp",
  "percentage points": "pp",
  elasticity: "",
  months: "months",
  ratio: "",
  times: "×",
};

/** A unit identifier as a reader expects it: "percent_change" → "%", "percentage_points" → "pp". */
export function unitShort(unit: string | null | undefined): string {
  if (!unit) return "";
  return UNIT_SHORT[unit] ?? unit;
}

/** A metric value in its unit: ratios as percentages, coverage as "4.17×". */
export function metricValue(value: string, unit: string): string {
  if (!isDecimalString(value)) return value;
  if (unit === "ratio") return formatRatioPercent(value, 2);
  if (unit === "times") return `${formatRounded(value, 2)}×`;
  return formatRounded(value, 4);
}

/** A metric's change: "−2.44 pp" for a ratio, "−0.64×" for coverage. */
export function metricChange(value: string, unit: string): string {
  if (!isDecimalString(value)) return value;
  if (unit === "ratio_points" || unit === "ratio") {
    const text = formatRounded(shiftDecimal(value, 2), 2);
    return `${withSign(text, value)} pp`;
  }
  if (unit === "times") return `${withSign(formatRounded(value, 2), value)}×`;
  return withSign(formatRounded(value, 4), value);
}

/** A pathway node's value in its unit. */
export function nodeValue(value: string | null, unit: string | null): string {
  if (value === null || !isDecimalString(value)) return "";
  switch (unit) {
    case "currency":
      return compactMoney(value);
    case "ratio":
      return formatRatioPercent(value, 2, true).replace(" %", "%");
    case "percentage_points":
      return `${withSign(formatRounded(value, 2), value)} pp`;
    case "ratio_points":
      return metricChange(value, "ratio_points");
    case "times":
      return metricChange(value, "times");
    case "%":
      return `${withSign(formatRounded(value, 4), value)}%`;
    case "percentage points":
      return `${withSign(formatRounded(value, 4), value)} pp`;
    default:
      return unit ? `${withSign(formatRounded(value, 4), value)} ${unit}` : value;
  }
}

/** Milliseconds as "142 ms" or "1.2 s". */
export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** The time between two ISO timestamps, in milliseconds (never negative). */
export function elapsed(start: string, end: string | null): number | null {
  if (!end) return null;
  const value = Date.parse(end) - Date.parse(start);
  return Number.isFinite(value) ? Math.max(0, value) : null;
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  validating: "Validating",
  simulating: "Simulating",
  propagating: "Propagating",
  aggregating: "Aggregating",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const MODEL_STATUS_LABEL: Record<string, string> = {
  included: "Included",
  available: "Available",
  excluded: "Excluded",
  blocked: "Blocked",
  not_applicable: "Not applicable",
};

export const EVIDENCE_LABEL: Record<string, string> = {
  evidence_backed: "Evidence-backed",
  analyst_created: "Analyst-created",
  model_assumption: "Model assumption",
  unverified: "Unverified",
};

export const SIMULATION_LABEL: Record<string, string> = {
  applied: "Applied by the model",
  propagated: "Propagated along the relationship",
  computed: "Computed by the model's equations",
  aggregated: "Added up by the Lab",
  context_only: "Context only — cited, not used to compute",
};

export function isFinal(status: string): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}
