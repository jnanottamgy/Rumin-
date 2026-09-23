/**
 * Exact decimal strings from the API ("-1234.567") — formatted without floating point.
 *
 * The API sends data values as strings so no digit is lost. These helpers keep it that
 * way for display: grouping and rounding work on the digits themselves (with BigInt),
 * never through a JavaScript number. `toNumber` exists only for plotting, where a
 * pixel position does not need more than double precision.
 */

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
const MINUS = "−";

interface Parts {
  negative: boolean;
  integer: string;
  fraction: string;
}

function parse(value: string): Parts | null {
  const match = DECIMAL.exec(value.trim());
  if (!match) return null;
  const [, sign = "", integer = "0", fraction = ""] = match;
  return { negative: sign === "-", integer, fraction };
}

function group(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function render({ negative, integer, fraction }: Parts): string {
  const isZero = /^0*$/.test(integer) && /^0*$/.test(fraction);
  const sign = negative && !isZero ? MINUS : "";
  const trimmed = integer.replace(/^0+(?=\d)/, "");
  return `${sign}${group(trimmed)}${fraction ? `.${fraction}` : ""}`;
}

export function isDecimalString(value: string): boolean {
  return parse(value) !== null;
}

/** Every digit, grouped: "1234567.891" → "1,234,567.891"; "-0.5" → "−0.5". */
export function formatExact(value: string): string {
  const parts = parse(value);
  return parts ? render(parts) : value;
}

/**
 * Rounded for display to at most `decimals` places, half away from zero, grouped.
 * Trailing zeros are not added: "5.1" stays "5.1".
 */
export function formatRounded(value: string, decimals: number): string {
  const parts = parse(value);
  if (!parts) return value;
  if (parts.fraction.length <= decimals) return render(parts);
  const kept = parts.fraction.slice(0, decimals);
  const next = parts.fraction.charAt(decimals);
  let digits = BigInt(`${parts.integer}${kept}`);
  if (next >= "5") digits += 1n;
  const text = digits.toString().padStart(decimals + 1, "0");
  const integer = decimals ? text.slice(0, -decimals) : text;
  const fraction = decimals ? text.slice(-decimals).replace(/0+$/, "") : "";
  return render({ negative: parts.negative, integer, fraction });
}

/** The number of digits after the decimal point, as published. */
export function decimalPlaces(value: string): number {
  return parse(value)?.fraction.length ?? 0;
}

/** For plotting and scales only; never for display or comparison of stored values. */
export function toNumber(value: string): number {
  return Number(value);
}
