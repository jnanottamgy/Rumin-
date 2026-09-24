/**
 * The scenario being edited, and its conversion to and from the API's scenario body.
 *
 * The draft mirrors the API's structure field for field, so an error the API reports at
 * `models.fx_exposure.inputs.annual_usd_costs` or `shocks[1].value` lands on the field
 * that caused it. Numbers stay strings while they are edited: nothing is parsed, rounded
 * or computed here — the backend validates and calculates everything.
 */
import type {
  ChangeType,
  EconomicVariable,
  ModelSettingsInput,
  Scenario,
  ScenarioInput,
  ScenarioUpdate,
  SimulationInputValue,
} from "@/types/api";

export type ModelMode = "auto" | "include" | "exclude";
export type Direction = 1 | -1;

export interface DraftChange {
  key: string;
  variableId: string;
  changeType: ChangeType;
  direction: Direction;
  /** The size of the change, without its sign ("20", "0.5"). */
  magnitude: string;
  note: string;
}

export interface DraftValue {
  value: string;
  unit: string;
  source: "user" | "stored_observation";
  seriesId: string;
}

export interface DraftModel {
  mode: ModelMode;
  inputs: Record<string, DraftValue>;
  assumptions: Record<string, string>;
}

export interface DraftStress {
  key: string;
  name: string;
  kind: "scale" | "values";
  scale: string;
  changes: Record<string, string>;
}

export interface LabDraft {
  name: string;
  description: string;
  templateId: string | null;
  note: string;
  changes: DraftChange[];
  entity: string | null;
  startMonth: string;
  durationMonths: string;
  horizonMonths: string;
  reportingCurrency: string;
  annualRevenue: string;
  annualOperatingCosts: string;
  fxRate: DraftValue;
  models: Record<string, DraftModel>;
  evidence: "any" | "evidence_backed";
  storedMarketData: boolean;
  stress: DraftStress[];
}

export const MAX_CHANGES = 10;
export const MAX_STRESS = 5;

let sequence = 0;
/** A stable key for list items that have no identity of their own. */
export function nextKey(prefix: string): string {
  sequence += 1;
  return `${prefix}-${sequence}`;
}

const text = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

function emptyValue(): DraftValue {
  return { value: "", unit: "", source: "user", seriesId: "" };
}

function valueFromApi(value: SimulationInputValue | null | undefined): DraftValue {
  if (!value) return emptyValue();
  return {
    value: text(value.value),
    unit: text(value.unit),
    source: value.source === "stored_observation" ? "stored_observation" : "user",
    seriesId: text(value.series_id),
  };
}

function changeFromApi(shock: {
  variable_id: string;
  change_type: ChangeType;
  value: string | number;
  note?: string;
}): DraftChange {
  const raw = text(shock.value).trim();
  const negative = raw.startsWith("-");
  return {
    key: nextKey("change"),
    variableId: shock.variable_id,
    changeType: shock.change_type,
    direction: negative ? -1 : 1,
    magnitude: negative ? raw.slice(1) : raw.replace(/^\+/, ""),
    note: shock.note ?? "",
  };
}

export function emptyDraft(): LabDraft {
  return {
    name: "",
    description: "",
    templateId: null,
    note: "",
    changes: [
      {
        key: nextKey("change"),
        variableId: "",
        changeType: "percent_change",
        direction: 1,
        magnitude: "",
        note: "",
      },
    ],
    entity: null,
    startMonth: "1",
    durationMonths: "0",
    horizonMonths: "12",
    reportingCurrency: "",
    annualRevenue: "",
    annualOperatingCosts: "",
    fxRate: emptyValue(),
    models: {},
    evidence: "any",
    storedMarketData: false,
    stress: [],
  };
}

/** A draft from a scenario body (a template's starting point, or a copy of a version). */
export function draftFromInput(input: ScenarioInput): LabDraft {
  const timing = input.timing;
  const company = input.company;
  return {
    name: input.name,
    description: input.description ?? "",
    templateId: input.template_id ?? null,
    note: "",
    changes: input.shocks.map(changeFromApi),
    entity: input.entity ?? null,
    startMonth: text(timing?.start_month ?? 1),
    durationMonths: text(timing?.duration_months ?? 0),
    horizonMonths: text(timing?.horizon_months ?? 12),
    reportingCurrency: text(company?.reporting_currency),
    annualRevenue: text(company?.annual_revenue),
    annualOperatingCosts: text(company?.annual_operating_costs),
    fxRate: valueFromApi(input.markets?.fx_rate),
    models: Object.fromEntries(
      Object.entries(input.models ?? {}).map(([id, settings]) => [
        id,
        {
          mode: settings.mode,
          inputs: Object.fromEntries(
            Object.entries(settings.inputs ?? {}).map(([name, value]) => [
              name,
              valueFromApi(value),
            ]),
          ),
          assumptions: Object.fromEntries(
            Object.entries(settings.assumptions ?? {}).map(([name, value]) => [name, text(value)]),
          ),
        },
      ]),
    ),
    evidence: input.constraints?.evidence ?? "any",
    storedMarketData: input.constraints?.stored_market_data ?? false,
    stress: (input.stress_cases ?? []).map((item) => ({
      key: nextKey("stress"),
      name: item.name,
      kind: item.scale !== null && item.scale !== undefined ? "scale" : "values",
      scale: text(item.scale),
      changes: Object.fromEntries(
        Object.entries(item.changes ?? {}).map(([name, value]) => [name, text(value)]),
      ),
    })),
  };
}

/** The latest version of a saved scenario as a draft. */
export function draftFromScenario(scenario: Scenario): LabDraft {
  const spec = scenario.spec;
  return draftFromInput({
    name: scenario.name,
    description: scenario.description,
    template_id: scenario.template_id,
    note: "",
    shocks: scenario.shocks.map((shock) => ({
      variable_id: shock.variable_id,
      change_type: shock.change_type,
      value: shock.value,
      note: shock.note,
    })),
    entity: spec.entity,
    timing: spec.timing,
    company: spec.company,
    markets: spec.markets,
    models: Object.fromEntries(
      Object.entries(spec.models).map(([id, settings]) => [
        id,
        {
          mode: settings.mode,
          inputs: Object.fromEntries(
            Object.entries(settings.inputs).map(([name, value]) => [name, value]),
          ),
          assumptions: settings.assumptions,
        },
      ]),
    ),
    constraints: spec.constraints,
    stress_cases: spec.stress_cases.map((item) => ({
      name: item.name,
      scale: item.scale,
      changes: item.changes,
    })),
  });
}

const orNull = (value: string): string | null => (value.trim() === "" ? null : value.trim());

function valueToApi(value: DraftValue): SimulationInputValue | null {
  if (value.source === "stored_observation") {
    return {
      value: null,
      unit: null,
      source: "stored_observation",
      series_id: orNull(value.seriesId),
    };
  }
  if (value.value.trim() === "") return null;
  return { value: value.value.trim(), unit: orNull(value.unit), source: null, series_id: null };
}

function integer(value: string, fallback: number): number {
  const trimmed = value.trim();
  // A value that is not a whole number is sent as it is typed (as NaN would be lost), so
  // the API reports it at its field instead of the browser guessing.
  return /^\d+$/.test(trimmed) ? Number(trimmed) : trimmed === "" ? fallback : Number.NaN;
}

/** The API body for this draft. Empty figures are left out, never filled in. */
export function toInput(draft: LabDraft): ScenarioInput {
  const models: Record<string, ModelSettingsInput> = {};
  for (const [id, settings] of Object.entries(draft.models)) {
    const inputs: Record<string, SimulationInputValue> = {};
    for (const [name, value] of Object.entries(settings.inputs)) {
      const converted = valueToApi(value);
      if (converted) inputs[name] = converted;
    }
    const assumptions: Record<string, string> = {};
    for (const [name, value] of Object.entries(settings.assumptions)) {
      if (value.trim() !== "") assumptions[name] = value.trim();
    }
    models[id] = { mode: settings.mode, inputs, assumptions };
  }
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    template_id: draft.templateId,
    note: draft.note.trim(),
    shocks: draft.changes.map((change) => {
      const magnitude = change.magnitude.trim();
      return {
        variable_id: change.variableId,
        change_type: change.changeType,
        value: change.direction < 0 && magnitude !== "" ? `-${magnitude}` : magnitude,
        note: change.note.trim(),
      };
    }),
    entity: draft.entity,
    timing: {
      start_month: integer(draft.startMonth, 1),
      duration_months: integer(draft.durationMonths, 0),
      horizon_months: integer(draft.horizonMonths, 12),
    },
    company: {
      reporting_currency: orNull(draft.reportingCurrency.toUpperCase()),
      annual_revenue: orNull(draft.annualRevenue),
      annual_operating_costs: orNull(draft.annualOperatingCosts),
    },
    markets: { fx_rate: valueToApi(draft.fxRate) },
    models,
    constraints: { evidence: draft.evidence, stored_market_data: draft.storedMarketData },
    stress_cases: draft.stress.map((item) =>
      item.kind === "scale"
        ? { name: item.name.trim(), scale: item.scale.trim(), changes: {} }
        : {
            name: item.name.trim(),
            scale: null,
            changes: Object.fromEntries(
              Object.entries(item.changes).filter(([, value]) => value.trim() !== ""),
            ),
          },
    ),
  };
}

export function toUpdate(draft: LabDraft, baseVersion: number): ScenarioUpdate {
  return { ...toInput(draft), base_version: baseVersion };
}

/** Whether two drafts describe the same scenario (what would be saved). */
export function sameScenario(a: LabDraft, b: LabDraft): boolean {
  const strip = (draft: LabDraft) => ({ ...toInput(draft), note: "" });
  return JSON.stringify(strip(a)) === JSON.stringify(strip(b));
}

/** Problems the browser can see before asking the API — shape only, never domain rules. */
export function missingBasics(draft: LabDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.name.trim()) errors.name = "Give the scenario a name.";
  draft.changes.forEach((change, index) => {
    if (!change.variableId) errors[`shocks[${index}].variable_id`] = "Choose a variable.";
    if (!change.magnitude.trim())
      errors[`shocks[${index}].value`] = "Enter the size of the change.";
  });
  return errors;
}

// --- The reducer -------------------------------------------------------------------------------

export type DraftAction =
  | { type: "load"; draft: LabDraft }
  | { type: "set"; field: keyof LabDraft; value: LabDraft[keyof LabDraft] }
  | { type: "change"; key: string; patch: Partial<DraftChange> }
  | { type: "addChange"; variable?: EconomicVariable }
  | { type: "removeChange"; key: string }
  | { type: "fx"; patch: Partial<DraftValue> }
  | { type: "modelMode"; model: string; mode: ModelMode }
  | { type: "modelInput"; model: string; input: string; patch: Partial<DraftValue> }
  | { type: "modelAssumption"; model: string; input: string; value: string }
  | { type: "addStress" }
  | { type: "stress"; key: string; patch: Partial<DraftStress> }
  | { type: "stressChange"; key: string; variable: string; value: string }
  | { type: "removeStress"; key: string };

function model(draft: LabDraft, id: string): DraftModel {
  return draft.models[id] ?? { mode: "auto", inputs: {}, assumptions: {} };
}

export function draftReducer(draft: LabDraft, action: DraftAction): LabDraft {
  switch (action.type) {
    case "load":
      return action.draft;
    case "set":
      return { ...draft, [action.field]: action.value };
    case "change":
      return {
        ...draft,
        changes: draft.changes.map((change) =>
          change.key === action.key ? { ...change, ...action.patch } : change,
        ),
      };
    case "addChange":
      if (draft.changes.length >= MAX_CHANGES) return draft;
      return {
        ...draft,
        changes: [
          ...draft.changes,
          {
            key: nextKey("change"),
            variableId: action.variable?.id ?? "",
            changeType: "percent_change",
            direction: 1,
            magnitude: "",
            note: "",
          },
        ],
      };
    case "removeChange":
      return { ...draft, changes: draft.changes.filter((change) => change.key !== action.key) };
    case "fx":
      return { ...draft, fxRate: { ...draft.fxRate, ...action.patch } };
    case "modelMode":
      return {
        ...draft,
        models: {
          ...draft.models,
          [action.model]: { ...model(draft, action.model), mode: action.mode },
        },
      };
    case "modelInput": {
      const current = model(draft, action.model);
      const value = current.inputs[action.input] ?? emptyValue();
      return {
        ...draft,
        models: {
          ...draft.models,
          [action.model]: {
            ...current,
            inputs: { ...current.inputs, [action.input]: { ...value, ...action.patch } },
          },
        },
      };
    }
    case "modelAssumption": {
      const current = model(draft, action.model);
      return {
        ...draft,
        models: {
          ...draft.models,
          [action.model]: {
            ...current,
            assumptions: { ...current.assumptions, [action.input]: action.value },
          },
        },
      };
    }
    case "addStress":
      if (draft.stress.length >= MAX_STRESS) return draft;
      return {
        ...draft,
        stress: [
          ...draft.stress,
          { key: nextKey("stress"), name: "", kind: "scale", scale: "", changes: {} },
        ],
      };
    case "stress":
      return {
        ...draft,
        stress: draft.stress.map((item) =>
          item.key === action.key ? { ...item, ...action.patch } : item,
        ),
      };
    case "stressChange":
      return {
        ...draft,
        stress: draft.stress.map((item) =>
          item.key === action.key
            ? { ...item, changes: { ...item.changes, [action.variable]: action.value } }
            : item,
        ),
      };
    case "removeStress":
      return { ...draft, stress: draft.stress.filter((item) => item.key !== action.key) };
  }
}
