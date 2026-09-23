/** Formatting helpers. All user-facing numbers and dates go through these. */

const FREQUENCY: Record<string, string> = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  annual: "Annual",
  irregular: "Irregular (policy decisions)",
};

export function formatFrequency(value: string): string {
  return FREQUENCY[value] ?? value;
}

const integer = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });

export function formatCount(value: number): string {
  return integer.format(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateFormat.format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTimeFormat.format(date);
}

const changeNumber = new Intl.NumberFormat("en", {
  maximumFractionDigits: 4,
  signDisplay: "exceptZero",
});

/** "+30 %", "−0.25 percentage points", "+12.5 USD per barrel". */
export function formatChange(value: number, unitLabel: string): string {
  const number = changeNumber.format(value).replace("-", "−");
  return unitLabel === "%" ? `${number}%` : `${number} ${unitLabel}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A period label from the API ("2023", "2023-Q1", "2023-03") for reading: "Q1 2023". */
export function formatPeriod(label: string): string {
  const quarter = /^(\d{4})-Q([1-4])$/.exec(label);
  if (quarter) return `Q${quarter[2]} ${quarter[1]}`;
  const month = /^(\d{4})-(\d{2})$/.exec(label);
  if (month) return `${MONTHS[Number(month[2]) - 1] ?? month[2]} ${month[1]}`;
  return label;
}

/** A calendar date ("2026-09-21") without time-zone shifts: "21 Sep 2026". */
export function formatCalendarDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1] ?? match[2]} ${match[1]}`;
}

export function formatBytes(count: number): string {
  if (count < 1024) return `${formatCount(count)} bytes`;
  if (count < 1024 * 1024) return `${(count / 1024).toFixed(1)} KB`;
  return `${(count / (1024 * 1024)).toFixed(1)} MB`;
}
