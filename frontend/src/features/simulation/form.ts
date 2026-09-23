/**
 * The simulation form: built from a model's definition, never hard-coded, so a new model
 * version brings its own inputs. The form only collects text; every check that matters
 * (types, units, ranges, currencies, consistency) is done by the API, which answers with
 * one message per field.
 */
import { formatExact } from "@/lib/decimal";
import type {
  SimulationInputDefinition,
  SimulationInputValue,
  SimulationIssue,
  SimulationModelDetail,
  SimulationRun,
} from "@/types/api";

export type InputCategory = SimulationInputDefinition["category"];

export interface FieldState {
  /** Exactly what the reader typed; empty means "use the model's default". */
  value: string;
  /** For quantities: the chosen unit. */
  unit: string | null;
  /** Take the latest stored observation instead of a typed value. */
  stored: boolean;
}

export type FormState = Record<string, FieldState>;

export const CATEGORY_ORDER: readonly InputCategory[] = [
  "scenario_input",
  "market_baseline",
  "company_input",
  "assumption",
  "setting",
];

export const CATEGORY_TEXT: Record<InputCategory, { title: string; note: string }> = {
  scenario_input: {
    title: "Scenario changes",
    note: "The changes to explore, as a percentage of today's level.",
  },
  market_baseline: {
    title: "Market baseline",
    note: "Prices at the start. Enter them, or use a value RUMIN stores where one exists.",
  },
  company_input: {
    title: "The airline",
    note: "The company's own figures. The model uses exactly what you enter.",
  },
  assumption: {
    title: "Assumptions",
    note: "Each has a stated default. Change one only when you have a reason to.",
  },
  setting: { title: "Horizon", note: "How many months the calculation covers." },
};

export function inputsByCategory(
  model: SimulationModelDetail,
): { category: InputCategory; inputs: SimulationInputDefinition[] }[] {
  return CATEGORY_ORDER.map((category) => ({
    category,
    inputs: model.inputs.filter((input) => input.category === category),
  })).filter((group) => group.inputs.length > 0);
}

function emptyField(input: SimulationInputDefinition): FieldState {
  return { value: "", unit: input.units[0]?.id ?? null, stored: false };
}

/** A blank form: required inputs empty, optional ones on their defaults. */
export function emptyForm(model: SimulationModelDetail): FormState {
  return Object.fromEntries(model.inputs.map((input) => [input.id, emptyField(input)]));
}

/** The form that reproduces a stored run's inputs (defaults stay defaults). */
export function formFromRun(model: SimulationModelDetail, run: SimulationRun): FormState {
  const form = emptyForm(model);
  for (const entry of run.inputs) {
    const field = form[entry.id];
    if (!field) continue;
    if (entry.source === "stored_observation") {
      form[entry.id] = { ...field, stored: true };
    } else if (entry.source === "user") {
      const input = model.inputs.find((item) => item.id === entry.id);
      const unit =
        input && input.units.length > 0 && entry.unit ? entry.unit : (field.unit ?? null);
      form[entry.id] = { value: entry.value ?? "", unit, stored: false };
    }
  }
  return form;
}

/**
 * The request body's `inputs`: typed values as exact strings, the chosen unit for
 * quantities, a stored-observation choice, and nothing for inputs left on their default.
 */
export function toRequestInputs(
  model: SimulationModelDetail,
  form: FormState,
): Record<string, SimulationInputValue> {
  const inputs: Record<string, SimulationInputValue> = {};
  for (const input of model.inputs) {
    const field = form[input.id];
    if (!field) continue;
    if (field.stored && input.sources.length > 0) {
      inputs[input.id] = { source: "stored_observation", series_id: input.sources[0]?.series_id };
      continue;
    }
    const value = field.value.trim();
    if (value === "") continue;
    inputs[input.id] =
      input.kind === "quantity" ? { value, unit: field.unit ?? undefined } : { value };
  }
  return inputs;
}

export interface FieldIssue {
  field: string | null;
  message: string;
  code: string;
}

/** Issues from a validation report, or from the details of a refused run. */
export function issuesFromDetails(
  details: { field?: string | null; message: string; type?: string | null }[],
): FieldIssue[] {
  return details.map((detail) => ({
    field: detail.field?.startsWith("inputs.")
      ? detail.field.slice("inputs.".length)
      : detail.field === "inputs"
        ? null
        : (detail.field ?? null),
    message: detail.message,
    code: detail.type ?? "invalid",
  }));
}

export function issuesFromReport(issues: SimulationIssue[]): FieldIssue[] {
  return issues.map((issue) => ({ field: issue.field, message: issue.message, code: issue.code }));
}

export function issuesByField(issues: FieldIssue[]): Record<string, FieldIssue[]> {
  const grouped: Record<string, FieldIssue[]> = {};
  for (const issue of issues) {
    const key = issue.field ?? "";
    grouped[key] = [...(grouped[key] ?? []), issue];
  }
  return grouped;
}

/** The DOM id of an input's control, so error summaries can link to it. */
export function fieldId(inputId: string): string {
  return `simulation-input-${inputId}`;
}

/** "at least 0 %", "between 0 and 36 months": the allowed range, as the API states it. */
export function rangeText(input: SimulationInputDefinition): string | null {
  const unit =
    input.unit === "percent" || input.unit === "percent_change"
      ? " %"
      : input.unit === "months"
        ? " months"
        : "";
  const low = input.minimum;
  const high = input.maximum;
  const lowText =
    low === null || low === undefined
      ? null
      : `${input.minimum_exclusive ? "above" : "from"} ${formatExact(low)}${unit}`;
  const highText =
    high === null || high === undefined
      ? null
      : `${input.maximum_exclusive ? "below" : "up to"} ${formatExact(high)}${unit}`;
  if (lowText && highText) return `${lowText}, ${highText}`;
  return lowText ?? highText;
}
