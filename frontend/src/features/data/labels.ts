/**
 * Words for the data layer's states. Every status is shown with a label (and an icon
 * where it is a status), never with colour alone.
 */
import type { StatusTone } from "@/components/StatusIndicator";
import type {
  IssueOutcome,
  JobItemStatus,
  JobStatus,
  MeasureType,
  QualityStatus,
} from "@/types/api";

export const JOB_STATUS: Record<JobStatus, { label: string; tone: StatusTone }> = {
  pending: { label: "Pending", tone: "neutral" },
  running: { label: "Running", tone: "planned" },
  completed: { label: "Completed", tone: "good" },
  completed_with_warnings: { label: "Completed with warnings", tone: "warning" },
  partially_failed: { label: "Partially failed", tone: "warning" },
  failed: { label: "Failed", tone: "critical" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const ITEM_STATUS: Record<JobItemStatus, { label: string; tone: StatusTone }> = {
  pending: { label: "Pending", tone: "neutral" },
  succeeded: { label: "Succeeded", tone: "good" },
  failed: { label: "Failed", tone: "critical" },
  skipped: { label: "Skipped", tone: "neutral" },
};

export const QUALITY: Record<QualityStatus, string> = {
  validated: "Passed checks",
  warning: "Flagged for review",
};

export const OUTCOME: Record<IssueOutcome, { label: string; description: string }> = {
  rejected: {
    label: "Rejected",
    description: "Not stored as data. The record the source sent is kept with the issue.",
  },
  flagged: {
    label: "Flagged",
    description: "Stored exactly as reported and marked for review. Nothing was corrected.",
  },
  noted: { label: "Noted", description: "Informational. Nothing was changed." },
};

export const MEASURE: Record<MeasureType, string> = {
  level: "Level",
  change: "Rate of change",
  rate: "Rate",
  ratio: "Ratio",
  exchange_rate: "Exchange rate",
};

const TEXT: Record<string, string> = {
  nominal: "Nominal (current prices)",
  real: "Real (constant prices)",
  not_applicable: "Not applicable",
  seasonally_adjusted: "Seasonally adjusted",
  not_seasonally_adjusted: "Not seasonally adjusted",
  unadjusted: "Unadjusted (as traded)",
  adjusted: "Adjusted (as supplied in the file)",
  equity: "Equity",
  etf: "Exchange-traded fund",
  index: "Index",
};

export function describeValue(value: string): string {
  return TEXT[value] ?? value.replaceAll("_", " ");
}

const ERROR_CODES: Record<string, string> = {
  provider_unavailable: "The provider could not be reached",
  provider_timeout: "The provider did not respond in time",
  rate_limited: "The provider's rate limit was reached",
  authentication_failed: "The provider refused access",
  invalid_request: "The provider rejected the request",
  malformed_response: "The response could not be understood",
  invalid_file: "The file could not be read",
  all_records_rejected: "Every record failed validation",
  storage_error: "The data could not be stored",
  internal_error: "An unexpected error occurred",
  circuit_open: "Skipped: the provider appeared to be unavailable",
  cancelled: "Cancelled",
  interrupted: "The process stopped before finishing",
};

export function describeErrorCode(code: string | null | undefined): string {
  if (!code) return "";
  return ERROR_CODES[code] ?? code.replaceAll("_", " ");
}

/** Rule codes read as sentences: "outside_review_range" → "Outside review range". */
export function ruleLabel(code: string): string {
  const text = code.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
