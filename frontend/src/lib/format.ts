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
