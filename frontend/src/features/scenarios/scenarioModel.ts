/**
 * Scenario Lab state and rules — pure functions, no React.
 *
 * The editor keeps raw text for numbers (what the user typed) and converts only when
 * saving, so "−" or "12." mid-typing never gets rewritten under the cursor.
 *
 * Validation mirrors the backend using the limits the API publishes on each variable
 * (`scenario_rules`), so the form and the server agree. The server stays authoritative:
 * its 422 responses are mapped back onto the same fields.
 */
import type { ApiError } from "@/lib/apiClient";
import { formatChange } from "@/lib/format";
import type {
  ChangeRule,
  ChangeType,
  EconomicVariable,
  Scenario,
  ScenarioInput,
} from "@/types/api";

export const MAX_SHOCKS = 10;
export const NAME_MAX = 120;
export const DESCRIPTION_MAX = 2000;
export const NOTE_MAX = 500;
export const MAX_DECIMALS = 4;

export interface ShockDraft {
  key: string;
  variableId: string;
  changeType: ChangeType | "";
  value: string;
  note: string;
}

export interface ScenarioDraft {
  id: string | null;
  name: string;
  description: string;
  shocks: ShockDraft[];
}

/** Field keys: "name", "description", "shocks", "form", or `shocks.<key>.<field>`. */
export type FieldErrors = Record<string, string>;

export interface EditorState {
  draft: ScenarioDraft;
  /** The last saved version, to tell whether there are unsaved changes. */
  saved: ScenarioDraft | null;
  errors: FieldErrors;
}

let sequence = 0;
const nextKey = () => {
  sequence += 1;
  return `shock-${sequence}`;
};

export function emptyShock(): ShockDraft {
  return { key: nextKey(), variableId: "", changeType: "", value: "", note: "" };
}

export function emptyDraft(): ScenarioDraft {
  return { id: null, name: "", description: "", shocks: [emptyShock()] };
}

export function draftFromScenario(scenario: Scenario): ScenarioDraft {
  return {
    id: scenario.id,
    name: scenario.name,
    description: scenario.description,
    shocks: scenario.shocks.map((shock) => ({
      key: nextKey(),
      variableId: shock.variable_id,
      changeType: shock.change_type,
      value: String(shock.value),
      note: shock.note,
    })),
  };
}

/** The worked example from the product brief: Brent crude +30 %. Clearly an example. */
export function exampleDraft(): ScenarioDraft {
  return {
    id: null,
    name: "Oil price shock (example)",
    description:
      "Example scenario: the Brent crude oil price rises 30 %. Inputs only — nothing is simulated.",
    shocks: [
      {
        key: nextKey(),
        variableId: "var_brent_crude",
        changeType: "percent_change",
        value: "30",
        note: "",
      },
    ],
  };
}

export const initialEditorState = (draft: ScenarioDraft = emptyDraft()): EditorState => ({
  draft,
  saved: draft.id ? draft : null,
  errors: {},
});

export type EditorAction =
  | { type: "load"; draft: ScenarioDraft }
  | { type: "setName"; value: string }
  | { type: "setDescription"; value: string }
  | { type: "addShock" }
  | { type: "removeShock"; key: string }
  | { type: "updateShock"; key: string; patch: Partial<Omit<ShockDraft, "key">> }
  | { type: "setErrors"; errors: FieldErrors }
  | { type: "saved"; draft: ScenarioDraft };

function withoutErrors(errors: FieldErrors, predicate: (key: string) => boolean): FieldErrors {
  return Object.fromEntries(Object.entries(errors).filter(([key]) => !predicate(key)));
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "load":
      return initialEditorState(action.draft);
    case "setName":
      return {
        ...state,
        draft: { ...state.draft, name: action.value },
        errors: withoutErrors(state.errors, (key) => key === "name" || key === "form"),
      };
    case "setDescription":
      return {
        ...state,
        draft: { ...state.draft, description: action.value },
        errors: withoutErrors(state.errors, (key) => key === "description"),
      };
    case "addShock":
      if (state.draft.shocks.length >= MAX_SHOCKS) return state;
      return {
        ...state,
        draft: { ...state.draft, shocks: [...state.draft.shocks, emptyShock()] },
        errors: withoutErrors(state.errors, (key) => key === "shocks"),
      };
    case "removeShock":
      return {
        ...state,
        draft: {
          ...state.draft,
          shocks: state.draft.shocks.filter((shock) => shock.key !== action.key),
        },
        errors: withoutErrors(state.errors, (key) => key.startsWith(`shocks.${action.key}.`)),
      };
    case "updateShock": {
      const changed = Object.keys(action.patch);
      return {
        ...state,
        draft: {
          ...state.draft,
          shocks: state.draft.shocks.map((shock) =>
            shock.key === action.key ? { ...shock, ...action.patch } : shock,
          ),
        },
        errors: withoutErrors(
          state.errors,
          (key) =>
            changed.some((field) => key === `shocks.${action.key}.${field}`) ||
            // Changing the variable can resolve duplicate/limit errors on the value.
            (changed.includes("variableId") && key.startsWith(`shocks.${action.key}.`)),
        ),
      };
    }
    case "setErrors":
      return { ...state, errors: action.errors };
    case "saved":
      return initialEditorState(action.draft);
  }
}

function comparable(draft: ScenarioDraft) {
  return JSON.stringify({
    name: draft.name.trim(),
    description: draft.description.trim(),
    shocks: draft.shocks.map(({ variableId, changeType, value, note }) => ({
      variableId,
      changeType,
      value: value.trim(),
      note: note.trim(),
    })),
  });
}

export function isDirty(state: EditorState): boolean {
  if (!state.saved) {
    const { name, description, shocks } = state.draft;
    return Boolean(
      name.trim() ||
        description.trim() ||
        shocks.some((shock) => shock.variableId || shock.value.trim() || shock.note.trim()),
    );
  }
  return comparable(state.draft) !== comparable(state.saved);
}

// --- Validation -----------------------------------------------------------------------------

// Deliberately matches control characters: they are rejected in names (the API does too).
// biome-ignore lint/suspicious/noControlCharactersInRegex: detecting them is the point
const CONTROL_CHARACTERS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const NUMBER = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

export const shockField = (key: string, field: keyof Omit<ShockDraft, "key">) =>
  `shocks.${key}.${field}`;

export function ruleFor(variable: EconomicVariable | undefined, changeType: ChangeType | "") {
  return variable?.scenario_rules.find((rule) => rule.change_type === changeType);
}

/** Parses user input like "30", "+12.5", "−0.25" (typographic minus accepted). */
export function parseChange(raw: string): number | null {
  const text = raw.trim().replace(/[−–]/g, "-");
  if (!NUMBER.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function decimalPlaces(raw: string): number {
  const fraction = raw.trim().split(".")[1];
  return fraction ? fraction.length : 0;
}

export function checkValue(raw: string, rule: ChangeRule): string | null {
  if (!raw.trim()) return "Enter the size of the change.";
  const value = parseChange(raw);
  if (value === null) return "Enter a number, for example 30 or -12.5.";
  if (value === 0) return "A change of zero has no effect.";
  if (rule.minimum_exclusive ? value <= rule.minimum : value < rule.minimum) {
    return `Must be ${rule.minimum_exclusive ? "greater than" : "at least"} ${formatChange(rule.minimum, rule.unit_label)}.`;
  }
  if (value > rule.maximum)
    return `Must be at most ${formatChange(rule.maximum, rule.unit_label)}.`;
  if (decimalPlaces(raw) > MAX_DECIMALS) return `Use at most ${MAX_DECIMALS} decimal places.`;
  return null;
}

export function validateDraft(
  draft: ScenarioDraft,
  variables: ReadonlyMap<string, EconomicVariable>,
): FieldErrors {
  const errors: FieldErrors = {};
  const name = draft.name.trim();
  if (!name) errors.name = "Give the scenario a name.";
  else if (name.length > NAME_MAX) errors.name = `Use at most ${NAME_MAX} characters.`;
  else if (CONTROL_CHARACTERS.test(name)) errors.name = "Remove control characters.";

  if (draft.description.trim().length > DESCRIPTION_MAX) {
    errors.description = `Use at most ${DESCRIPTION_MAX} characters.`;
  }

  if (draft.shocks.length === 0) errors.shocks = "Add at least one input.";
  if (draft.shocks.length > MAX_SHOCKS) errors.shocks = `Use at most ${MAX_SHOCKS} inputs.`;

  const seen = new Set<string>();
  for (const shock of draft.shocks) {
    const variable = variables.get(shock.variableId);
    if (!shock.variableId) {
      errors[shockField(shock.key, "variableId")] = "Choose a variable.";
      continue;
    }
    if (!variable) {
      errors[shockField(shock.key, "variableId")] = "This variable is not in the dataset.";
      continue;
    }
    if (seen.has(shock.variableId)) {
      errors[shockField(shock.key, "variableId")] =
        "This variable is already changed above; combine the two into one input.";
      continue;
    }
    seen.add(shock.variableId);

    const rule = ruleFor(variable, shock.changeType);
    if (!rule) {
      errors[shockField(shock.key, "changeType")] = "Choose how the variable changes.";
      continue;
    }
    const valueError = checkValue(shock.value, rule);
    if (valueError) errors[shockField(shock.key, "value")] = valueError;
    if (shock.note.trim().length > NOTE_MAX) {
      errors[shockField(shock.key, "note")] = `Use at most ${NOTE_MAX} characters.`;
    }
  }
  return errors;
}

export function toPayload(draft: ScenarioDraft): ScenarioInput {
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    shocks: draft.shocks.map((shock) => ({
      variable_id: shock.variableId,
      change_type: shock.changeType as ChangeType,
      value: parseChange(shock.value) ?? Number.NaN,
      note: shock.note.trim(),
    })),
  };
}

const API_FIELDS: Record<string, keyof Omit<ShockDraft, "key">> = {
  variable_id: "variableId",
  change_type: "changeType",
  value: "value",
  note: "note",
};

/** Maps the API's 422 details (e.g. `shocks[1].value`) onto editor field keys. */
export function errorsFromApi(error: ApiError, draft: ScenarioDraft): FieldErrors {
  const errors: FieldErrors = {};
  for (const detail of error.details) {
    const field = detail.field ?? "";
    const shockMatch = /^shocks\[(\d+)\]\.(\w+)$/.exec(field);
    const shock = shockMatch ? draft.shocks[Number(shockMatch[1])] : undefined;
    const shockFieldName = shockMatch ? API_FIELDS[shockMatch[2] ?? ""] : undefined;
    if (shock && shockFieldName) errors[shockField(shock.key, shockFieldName)] = detail.message;
    else if (field === "name" || field === "description" || field === "shocks") {
      errors[field] = detail.message;
    } else errors.form = detail.message;
  }
  if (Object.keys(errors).length === 0) errors.form = error.message;
  return errors;
}

/** One-line reading of an input, e.g. "Brent crude oil price: +30% (relative change)". */
export function describeShock(shock: ShockDraft, variable: EconomicVariable | undefined): string {
  if (!variable) return "No variable chosen yet";
  const rule = ruleFor(variable, shock.changeType);
  const value = parseChange(shock.value);
  if (!rule || value === null) return `${variable.name}: change not set`;
  const kind = shock.changeType === "percent_change" ? "relative change" : "absolute change";
  return `${variable.name}: ${formatChange(value, rule.unit_label)} (${kind})`;
}

export const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  percent_change: "Percent change",
  absolute_change: "Absolute change",
};
