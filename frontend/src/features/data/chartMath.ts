/**
 * The arithmetic behind the time-series chart: scales, "nice" ticks and line segments.
 * Pure functions, so every rule (especially "never draw across a missing value") is
 * unit-tested without rendering anything.
 */

export interface ChartPoint {
  /** Stable identity (period label or trade date). */
  key: string;
  /** Milliseconds since the epoch (UTC) of the period start or trade date. */
  time: number;
  /** Null when no value exists for the period: drawn as a gap, never interpolated. */
  value: number | null;
  flagged: boolean;
}

export type Scale = (value: number) => number;

export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  if (span === 0) return () => (r0 + r1) / 2;
  return (value) => r0 + ((value - d0) / span) * (r1 - r0);
}

function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const nice =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * power;
}

/** Round-number ticks covering [min, max], and the extended domain they define. */
export function niceTicks(
  min: number,
  max: number,
  count = 5,
): { ticks: number[]; domain: [number, number] } {
  let low = min;
  let high = max;
  if (low === high) {
    const pad = low === 0 ? 1 : Math.abs(low) * 0.1;
    low -= pad;
    high += pad;
  }
  const step = niceStep(high - low, count);
  const start = Math.floor(low / step) * step;
  const end = Math.ceil(high / step) * step;
  const ticks: number[] = [];
  // Rounding each tick avoids 0.30000000000000004 in labels.
  const decimals = Math.max(0, -Math.floor(Math.log10(step)) + 1);
  for (let value = start; value <= end + step / 2; value += step) {
    ticks.push(Number(value.toFixed(decimals)));
  }
  return { ticks, domain: [start, end] };
}

/**
 * Runs of consecutive points that both have values. A missing value, or a period absent
 * from the data (`contiguous` returns false), ends a run: the chart shows a gap.
 */
export function segments(
  points: readonly ChartPoint[],
  contiguous: (previous: ChartPoint, next: ChartPoint) => boolean,
): ChartPoint[][] {
  const runs: ChartPoint[][] = [];
  let current: ChartPoint[] = [];
  let previous: ChartPoint | null = null;
  for (const point of points) {
    const breaks = point.value === null || (previous !== null && !contiguous(previous, point));
    if (breaks && current.length) {
      runs.push(current);
      current = [];
    }
    if (point.value !== null) current.push(point);
    previous = point;
  }
  if (current.length) runs.push(current);
  return runs;
}

/** Index of the point closest in time (points sorted by time). */
export function nearestIndex(points: readonly ChartPoint[], time: number): number {
  if (points.length === 0) return -1;
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((points[middle]?.time ?? 0) < time) low = middle + 1;
    else high = middle;
  }
  const after = points[low];
  const before = points[low - 1];
  if (before && after && time - before.time <= after.time - time) return low - 1;
  return low;
}

const DAY = 86_400_000;

function utc(year: number, month = 0, day = 1): number {
  return Date.UTC(year, month, day);
}

export interface TimeTick {
  time: number;
  label: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Calendar-aligned ticks (years, then months, then days) that fit `maxTicks`. */
export function timeTicks(start: number, end: number, maxTicks: number): TimeTick[] {
  const limit = Math.max(2, maxTicks);
  const first = new Date(start);
  const last = new Date(end);
  const years = last.getUTCFullYear() - first.getUTCFullYear();
  if (years >= 2) {
    const step = [1, 2, 5, 10, 20, 25, 50, 100].find((s) => years / s < limit) ?? 100;
    const ticks: TimeTick[] = [];
    const firstYear = Math.ceil(first.getUTCFullYear() / step) * step;
    for (let year = firstYear; utc(year) <= end; year += step) {
      if (utc(year) >= start) ticks.push({ time: utc(year), label: String(year) });
    }
    return ticks;
  }
  const months = years * 12 + last.getUTCMonth() - first.getUTCMonth();
  if (months >= 2) {
    const step = [1, 2, 3, 6].find((s) => months / s < limit) ?? 6;
    const ticks: TimeTick[] = [];
    let year = first.getUTCFullYear();
    let month = first.getUTCMonth();
    while (utc(year, month) <= end) {
      const time = utc(year, month);
      if (time >= start && month % step === 0) {
        ticks.push({ time, label: `${MONTHS[month]} ${year}` });
      }
      month += 1;
      if (month === 12) {
        month = 0;
        year += 1;
      }
    }
    return ticks;
  }
  const days = Math.round((end - start) / DAY);
  const step = [1, 2, 7, 14].find((s) => days / s < limit) ?? 14;
  const ticks: TimeTick[] = [];
  for (let time = start; time <= end; time += step * DAY) {
    const date = new Date(time);
    ticks.push({ time, label: `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}` });
  }
  return ticks;
}

/** Milliseconds of a calendar date ("2023-01-01") in UTC. */
export function dateTime(iso: string): number {
  const [year = "0", month = "1", day = "1"] = iso.split("-");
  return utc(Number(year), Number(month) - 1, Number(day));
}

/** Whether `next` is the period straight after `previous` (annual, quarterly or monthly). */
export function nextPeriodFollows(frequency: string) {
  const monthsPerPeriod = frequency === "annual" ? 12 : frequency === "quarterly" ? 3 : 1;
  return (previous: ChartPoint, next: ChartPoint): boolean => {
    const a = new Date(previous.time);
    const b = new Date(next.time);
    const months =
      (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth();
    return months === monthsPerPeriod;
  };
}

/** Trading days are contiguous unless more than `maxDays` separate them. */
export function withinDays(maxDays: number) {
  return (previous: ChartPoint, next: ChartPoint): boolean =>
    next.time - previous.time <= maxDays * DAY;
}
