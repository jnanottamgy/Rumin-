/**
 * Display formatting for simulation values.
 *
 * The API sends every number as an exact decimal string. Formatting here only moves the
 * decimal point, rounds for display and groups digits — on the digits themselves, never
 * through a JavaScript number — so what is shown is the value the engine computed, rounded
 * as stated. No figure is calculated in the browser.
 */
import { formatExact, formatRounded, isDecimalString } from "@/lib/decimal";

const MINUS = "−";
const CURRENCY_UNIT = /^([A-Z]{3})(?: per (year|month))?$/;

function isNegative(value: string): boolean {
  return value.trim().startsWith("-") && !/^-?0*(\.0*)?$/.test(value.trim());
}

function isZero(value: string): boolean {
  return /^-?0*(\.0*)?$/.test(value.trim());
}

/**
 * `value` × 10^places as a decimal string, exactly: "0.0417419951" → "4.17419951" for
 * places = 2. Used to show ratios as percentages.
 */
export function shiftDecimal(value: string, places: number): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const [, sign = "", integer = "0", fraction = ""] = match;
  const digits = `${integer}${fraction}`;
  const point = integer.length + places;
  const padded = point > digits.length ? digits.padEnd(point, "0") : digits;
  const head = point <= 0 ? "0" : padded.slice(0, point);
  const tail = point <= 0 ? `${"0".repeat(-point)}${padded}` : padded.slice(point);
  const trimmedHead = head.replace(/^0+(?=\d)/, "");
  const trimmedTail = tail.replace(/0+$/, "");
  return `${sign}${trimmedHead}${trimmedTail ? `.${trimmedTail}` : ""}`;
}

/** "+" for positive values, "−" for negative ones, nothing for zero. */
export function withSign(formatted: string, value: string): string {
  if (isZero(value)) return formatted.replace(MINUS, "");
  return isNegative(value) || formatted.startsWith(MINUS) ? formatted : `+${formatted}`;
}

/** A money amount rounded to `decimals` places: "−40,598.79 INR". */
export function formatMoney(
  value: string,
  currency: string,
  { decimals = 2, signed = false }: { decimals?: number; signed?: boolean } = {},
): string {
  const text = formatRounded(value, decimals);
  return `${signed ? withSign(text, value) : text} ${currency}`.trim();
}

/** A compact money amount for tight labels: "−40.6 thousand INR", "−3.55 million INR". */
export function formatMoneyCompact(value: string, currency: string, signed = false): string {
  const match = /^-?(\d+)/.exec(value.trim());
  const digits = match?.[1]?.replace(/^0+/, "") ?? "";
  const scales: [number, string][] = [
    [12, "trillion"],
    [9, "billion"],
    [6, "million"],
    [3, "thousand"],
  ];
  for (const [power, word] of scales) {
    if (digits.length > power) {
      const scaled = shiftDecimal(value, -power);
      const text = formatRounded(scaled, 2);
      return `${signed ? withSign(text, value) : text} ${word} ${currency}`.trim();
    }
  }
  return formatMoney(value, currency, { decimals: 0, signed });
}

/** A ratio as a percentage: "0.2" → "20 %"; `signed` adds "+" to increases. */
export function formatRatioPercent(value: string, decimals = 2, signed = false): string {
  const text = formatRounded(shiftDecimal(value, 2), decimals);
  return `${signed ? withSign(text, value) : text} %`;
}

/**
 * A model output or step value in its unit. Units come from the model definition
 * ("INR", "INR per year", "ratio", "ratio_points", "price_relative", …).
 */
export function formatUnitValue(
  value: string | null | undefined,
  unit: string,
  { signed = false, exact = false }: { signed?: boolean; exact?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (!isDecimalString(value)) return value;
  const currency = CURRENCY_UNIT.exec(unit);
  if (currency) {
    const text = exact ? formatExact(value) : formatRounded(value, 2);
    return `${signed ? withSign(text, value) : text} ${unit}`;
  }
  if (unit === "ratio") return formatRatioPercent(value, exact ? 8 : 2, signed);
  if (unit === "ratio_points") {
    const text = formatRounded(shiftDecimal(value, 2), exact ? 8 : 2);
    return `${signed ? withSign(text, value) : text} percentage points`;
  }
  if (unit === "price_relative") return `${formatRounded(value, exact ? 10 : 4)} × baseline`;
  const text = exact ? formatExact(value) : formatRounded(value, 4);
  const shown = signed ? withSign(text, value) : text;
  return unit ? `${shown} ${unit}` : shown;
}

/**
 * `formatUnitValue` split into the figure and its unit, so a large number can be set
 * apart from a smaller unit label: { number: "−3,550,000", unit: "INR" }.
 */
export function formatParts(
  value: string,
  unit: string,
  options: { signed?: boolean } = {},
): { number: string; unit: string } {
  const text = formatUnitValue(value, unit, options);
  const currency = CURRENCY_UNIT.exec(unit);
  const suffix = currency
    ? unit
    : unit === "ratio"
      ? "%"
      : unit === "ratio_points"
        ? "percentage points"
        : unit === "price_relative"
          ? "× baseline"
          : unit;
  return suffix && text.endsWith(` ${suffix}`)
    ? { number: text.slice(0, -suffix.length - 1), unit: suffix }
    : { number: text, unit: "" };
}

/** An input as entered, with its unit label: "10 % change", "750 USD per kilolitre". */
export function formatInputValue(value: string | null | undefined, unitLabel: string): string {
  if (value === null || value === undefined || value === "") return "Not set";
  const text = isDecimalString(value) ? formatExact(value) : value;
  if (!unitLabel || unitLabel === "knowledge-graph node" || unitLabel === "ISO 4217 code") {
    return text;
  }
  return `${text} ${unitLabel}`;
}

/** The first 12 characters of a hash, for display next to a copyable full value. */
export function shortHash(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 12) : "—";
}

export { isNegative, isZero };
