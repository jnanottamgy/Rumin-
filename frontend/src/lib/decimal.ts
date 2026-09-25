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

// --- Exact arithmetic on decimal strings (form starting points; never results) ----------------

interface Scaled {
  digits: bigint;
  scale: number;
}

function scaled(value: string): Scaled | null {
  const parts = parse(value);
  if (!parts) return null;
  const digits = BigInt(`${parts.integer}${parts.fraction}` || "0");
  return { digits: parts.negative ? -digits : digits, scale: parts.fraction.length };
}

function toText({ digits, scale }: Scaled): string {
  const negative = digits < 0n;
  const text = (negative ? -digits : digits).toString().padStart(scale + 1, "0");
  const integer = scale ? text.slice(0, -scale) : text;
  const fraction = scale ? text.slice(-scale).replace(/0+$/, "") : "";
  const isZero = /^0*$/.test(integer) && fraction === "";
  return `${negative && !isZero ? "-" : ""}${integer}${fraction ? `.${fraction}` : ""}`;
}

function aligned(a: Scaled, b: Scaled): [bigint, bigint, number] {
  const scale = Math.max(a.scale, b.scale);
  return [
    a.digits * 10n ** BigInt(scale - a.scale),
    b.digits * 10n ** BigInt(scale - b.scale),
    scale,
  ];
}

/** a + b, exactly: "0.1" + "0.2" → "0.3". Null when either is not a plain decimal. */
export function addDecimals(a: string, b: string): string | null {
  const x = scaled(a);
  const y = scaled(b);
  if (!x || !y) return null;
  const [left, right, scale] = aligned(x, y);
  return toText({ digits: left + right, scale });
}

/** a × b, exactly: "80" × "0.95" → "76". */
export function multiplyDecimals(a: string, b: string): string | null {
  const x = scaled(a);
  const y = scaled(b);
  if (!x || !y) return null;
  return toText({ digits: x.digits * y.digits, scale: x.scale + y.scale });
}

/** −1, 0 or 1 as a is below, equal to or above b; null when either is not a plain decimal. */
export function compareDecimals(a: string, b: string): -1 | 0 | 1 | null {
  const x = scaled(a);
  const y = scaled(b);
  if (!x || !y) return null;
  const [left, right] = aligned(x, y);
  return left < right ? -1 : left > right ? 1 : 0;
}

/** Rounded to `places` decimals, half away from zero, without grouping: "1.005" → "1.01". */
export function roundDecimal(value: string, places: number): string | null {
  const x = scaled(value);
  if (!x) return null;
  if (x.scale <= places) return toText(x);
  const drop = 10n ** BigInt(x.scale - places);
  const negative = x.digits < 0n;
  const magnitude = negative ? -x.digits : x.digits;
  let kept = magnitude / drop;
  if ((magnitude % drop) * 2n >= drop) kept += 1n;
  return toText({ digits: negative ? -kept : kept, scale: places });
}
