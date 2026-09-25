/**
 * The scenario's controls: the changes (direction and magnitude, with sliders), the
 * company and its figures, the timing, the models with their own inputs and assumptions,
 * the constraints and the stress cases.
 *
 * Every field shows the problem the API reports for it — the plan's errors and warnings
 * use the same field paths — so the browser never re-implements a validation rule. The
 * only checks made here are that required fields are not empty.
 */
import { type Dispatch, type ReactNode, useId, useState } from "react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { KnowledgeGlyph } from "@/features/simulation/knowledge";
import { useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { graphApi, simulationApi } from "@/services/api";
import type {
  ChangeType,
  EconomicVariable,
  ModelPlan,
  ScenarioPlan,
  SimulationInputDefinition,
} from "@/types/api";
import {
  type DraftAction,
  type DraftChange,
  type DraftStress,
  type LabDraft,
  MAX_CHANGES,
  MAX_STRESS,
  type ModelMode,
} from "./draft";
import { MODEL_STATUS_LABEL } from "./format";
import styles from "./ScenarioLab.module.css";

/**
 * "needed" is a required value not entered yet, before the user has tried to save or
 * execute: shown as a neutral note rather than an error.
 */
export type MessageSeverity = "error" | "warning" | "needed";
export type FieldMessages = Record<string, { message: string; severity: MessageSeverity }[]>;

/** The id of a field's input element, for focusing it from an error summary. */
export function fieldId(path: string): string {
  return `lab-field-${path.replace(/[^a-zA-Z0-9]+/g, "-")}`;
}

function Messages({ messages }: { messages?: FieldMessages[string] }) {
  if (!messages?.length) return null;
  return (
    <ul className={styles.fieldMessages}>
      {messages.map((item) => (
        <li key={item.message} data-severity={item.severity}>
          <Icon
            name={
              item.severity === "error" ? "alert" : item.severity === "needed" ? "circle" : "info"
            }
            size={12}
          />
          {item.message}
        </li>
      ))}
    </ul>
  );
}

function Field({
  path,
  label,
  hint,
  messages,
  showMessages = true,
  children,
}: {
  path: string;
  label: ReactNode;
  hint?: ReactNode;
  messages: FieldMessages;
  /** False when the caller shows the field's messages elsewhere, e.g. under a row. */
  showMessages?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={styles.field}>
      <label htmlFor={fieldId(path)} className={styles.fieldLabel}>
        {label}
      </label>
      {children}
      {hint && <p className={styles.fieldHint}>{hint}</p>}
      {showMessages && <Messages messages={messages[path]} />}
    </div>
  );
}

/** Words only a screen reader hears, telling repeated rows' fields apart ("Name of stress
 * case 2"); the visible label stays short. */
function ofRow(words: string): ReactNode {
  return <span className="visually-hidden"> {words}</span>;
}

function invalid(messages: FieldMessages, path: string): boolean {
  return messages[path]?.some((item) => item.severity === "error") ?? false;
}

function Section({
  title,
  summary,
  defaultOpen = true,
  children,
}: {
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className={styles.builderSection}>
      <h3 className={styles.builderHeading}>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? "chevronDown" : "chevronRight"} size={12} />
          {title}
          {summary && <span className={styles.builderSummary}>{summary}</span>}
        </button>
      </h3>
      <div id={id} hidden={!open} className={styles.builderBody}>
        {children}
      </div>
    </section>
  );
}

// --- Changes -------------------------------------------------------------------------------------

/** The range a rule allows, in the Rise/Fall terms the controls use. */
function allowedRange(rule: EconomicVariable["scenario_rules"][number]): string {
  const unit = rule.unit_label === "percentage points" ? "pp" : rule.unit_label;
  const amount = (value: number) => `${Math.abs(value).toLocaleString("en-GB")} ${unit}`;
  if (rule.minimum < 0 && rule.maximum > 0) {
    const fall = rule.minimum_exclusive
      ? `a fall of less than ${amount(rule.minimum)}`
      : `a fall of up to ${amount(rule.minimum)}`;
    return `Allowed: ${fall} or a rise of up to ${amount(rule.maximum)}.`;
  }
  return `Allowed: from ${rule.minimum} to ${rule.maximum} ${unit}.`;
}

const SLIDER: Record<string, { max: number; step: number }> = {
  "%": { max: 100, step: 1 },
  "percentage points": { max: 5, step: 0.25 },
};

function ChangeRow({
  change,
  index,
  variables,
  dispatch,
  messages,
  removable,
}: {
  change: DraftChange;
  index: number;
  variables: EconomicVariable[];
  dispatch: Dispatch<DraftAction>;
  messages: FieldMessages;
  removable: boolean;
}) {
  const variable = variables.find((item) => item.id === change.variableId);
  const rules = variable?.scenario_rules ?? [];
  const rule = rules.find((item) => item.change_type === change.changeType) ?? rules[0];
  const unit = rule?.unit_label ?? "";
  const slider = SLIDER[unit];
  const base = `shocks[${index}]`;
  const numeric = Number(change.magnitude);
  const set = (patch: Partial<DraftChange>) => dispatch({ type: "change", key: change.key, patch });

  return (
    <li className={styles.changeRow}>
      <div className={styles.changeHeader}>
        <KnowledgeGlyph kind="scenario_input" />
        <span className={styles.changeIndex}>Change {index + 1}</span>
        {removable && (
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => dispatch({ type: "removeChange", key: change.key })}
            aria-label={`Remove change ${index + 1}`}
          >
            <Icon name="trash" size={13} />
          </button>
        )}
      </div>
      <Field
        path={`${base}.variable_id`}
        label={<>Variable{ofRow(`of change ${index + 1}`)}</>}
        messages={messages}
      >
        <select
          id={fieldId(`${base}.variable_id`)}
          value={change.variableId}
          aria-invalid={invalid(messages, `${base}.variable_id`)}
          onChange={(event) => {
            const next = variables.find((item) => item.id === event.target.value);
            const allowed = next?.scenario_rules.map((item) => item.change_type) ?? [];
            set({
              variableId: event.target.value,
              changeType: allowed.includes(change.changeType)
                ? change.changeType
                : ((allowed[0] ?? "percent_change") as ChangeType),
            });
          }}
        >
          <option value="">Choose a variable…</option>
          {variables.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      {rules.length > 1 && (
        <fieldset className={styles.segmented}>
          <legend className="visually-hidden">Kind of change</legend>
          {rules.map((item) => (
            <button
              key={item.change_type}
              type="button"
              aria-pressed={change.changeType === item.change_type}
              onClick={() => set({ changeType: item.change_type })}
            >
              {item.change_type === "percent_change" ? "Percent" : `In ${item.unit_label}`}
            </button>
          ))}
        </fieldset>
      )}
      <div className={styles.magnitude}>
        <fieldset className={styles.segmented}>
          <legend className="visually-hidden">Direction</legend>
          <button
            type="button"
            aria-pressed={change.direction === 1}
            onClick={() => set({ direction: 1 })}
          >
            <Icon name="arrowUp" size={12} /> Rise
          </button>
          <button
            type="button"
            aria-pressed={change.direction === -1}
            onClick={() => set({ direction: -1 })}
          >
            <Icon name="arrowDown" size={12} /> Fall
          </button>
        </fieldset>
        <Field
          path={`${base}.value`}
          label={<span className="visually-hidden">Magnitude</span>}
          messages={messages}
          showMessages={false}
        >
          <span className={styles.unitInput}>
            <input
              id={fieldId(`${base}.value`)}
              inputMode="decimal"
              value={change.magnitude}
              aria-invalid={invalid(messages, `${base}.value`)}
              aria-label={`Magnitude of change ${index + 1}`}
              onChange={(event) => set({ magnitude: event.target.value.replace(/^[-+]/, "") })}
            />
            <span>{unit === "percentage points" ? "pp" : unit}</span>
          </span>
        </Field>
      </div>
      {slider && (
        <input
          type="range"
          className={styles.slider}
          min={0}
          max={slider.max}
          step={slider.step}
          value={Number.isFinite(numeric) ? Math.min(numeric, slider.max) : 0}
          aria-label={`Magnitude of change ${index + 1} (slider)`}
          aria-valuetext={`${change.direction < 0 ? "−" : "+"}${change.magnitude || 0} ${unit}`}
          onChange={(event) => set({ magnitude: event.target.value })}
        />
      )}
      {rule && (
        <p className={styles.fieldHint}>
          {rule.change_type === "absolute_change" && variable?.value_kind === "rate"
            ? `Rates change in percentage points. ${allowedRange(rule)}`
            : allowedRange(rule)}
        </p>
      )}
      <Messages messages={messages[`${base}.value`]} />
      <Messages messages={messages[base]} />
    </li>
  );
}

// --- Company -------------------------------------------------------------------------------------

function CompanyPicker({
  draft,
  dispatch,
  plan,
  messages,
}: {
  draft: LabDraft;
  dispatch: Dispatch<DraftAction>;
  plan: ScenarioPlan | null;
  messages: FieldMessages;
}) {
  const companies = useApiResource("lab:companies", () =>
    graphApi.search({ types: ["company"], sort: "name", limit: 100 }),
  );
  const tied = new Map(
    (plan?.affected?.entities ?? []).map((entry) => [
      entry.entity.key,
      entry.exposures.some((exposure) => exposure.models.length > 0),
    ]),
  );
  const options = companies.status === "success" ? companies.data.items : [];
  const covered = options.filter((item) => tied.get(item.id) === true);
  const others = options.filter((item) => tied.get(item.id) !== true);
  return (
    <Field
      path="entity"
      label="Company in the knowledge graph"
      hint="Optional. The graph's stated exposures decide which models apply by default; your figures decide the amounts."
      messages={messages}
    >
      <select
        id={fieldId("entity")}
        value={draft.entity ?? ""}
        aria-invalid={invalid(messages, "entity")}
        onChange={(event) =>
          dispatch({ type: "set", field: "entity", value: event.target.value || null })
        }
      >
        <option value="">No company — figures only</option>
        {covered.length > 0 && (
          <optgroup label="A model covers its stated exposure">
            {covered.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </optgroup>
        )}
        <optgroup label={covered.length ? "Other companies" : "Companies"}>
          {others.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </optgroup>
      </select>
    </Field>
  );
}

function TextField({
  path,
  label,
  value,
  onChange,
  messages,
  hint,
  inputMode = "decimal",
  suffix,
}: {
  path: string;
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  messages: FieldMessages;
  hint?: string;
  inputMode?: "decimal" | "numeric" | "text";
  suffix?: string;
}) {
  return (
    <Field path={path} label={label} hint={hint} messages={messages}>
      <span className={styles.unitInput}>
        <input
          id={fieldId(path)}
          inputMode={inputMode}
          value={value}
          aria-invalid={invalid(messages, path)}
          onChange={(event) => onChange(event.target.value)}
        />
        {suffix && <span>{suffix}</span>}
      </span>
    </Field>
  );
}

// --- Models --------------------------------------------------------------------------------------

const SHARED = new Set([
  "entity",
  "reporting_currency",
  "annual_revenue",
  "annual_operating_costs",
  "fx_rate",
]);

function ModelInputs({
  model,
  draft,
  dispatch,
  messages,
}: {
  model: ModelPlan;
  draft: LabDraft;
  dispatch: Dispatch<DraftAction>;
  messages: FieldMessages;
}) {
  const definition = useApiResource(`lab:model:${model.model_id}`, () =>
    simulationApi.model(model.model_id),
  );
  if (definition.status === "loading")
    return <p className={styles.fieldHint}>Loading the model's inputs…</p>;
  if (definition.status === "error") {
    return (
      <p className={styles.fieldHint}>
        The model's inputs could not be loaded ({describeError(definition.error)}).{" "}
        <button type="button" className={styles.linkButton} onClick={definition.reload}>
          Try again
        </button>
      </p>
    );
  }
  const settings = draft.models[model.model_id];
  const own = definition.data.inputs.filter(
    (item) =>
      (item.category === "company_input" || item.category === "market_baseline") &&
      !SHARED.has(item.id),
  );
  const assumptions = definition.data.inputs.filter((item) => item.category === "assumption");
  const inputField = (item: SimulationInputDefinition) => {
    const path = `models.${model.model_id}.inputs.${item.id}`;
    const value = settings?.inputs[item.id];
    return (
      <Field
        key={item.id}
        path={path}
        label={item.label}
        hint={item.description}
        messages={messages}
      >
        <span className={styles.unitInput}>
          <input
            id={fieldId(path)}
            inputMode="decimal"
            value={value?.value ?? ""}
            aria-invalid={invalid(messages, path)}
            onChange={(event) =>
              dispatch({
                type: "modelInput",
                model: model.model_id,
                input: item.id,
                patch: {
                  value: event.target.value,
                  unit: value?.unit || (item.units[0]?.id ?? ""),
                },
              })
            }
          />
          {item.units.length > 0 ? (
            <select
              aria-label={`${item.label} unit`}
              value={value?.unit || (item.units[0]?.id ?? "")}
              onChange={(event) =>
                dispatch({
                  type: "modelInput",
                  model: model.model_id,
                  input: item.id,
                  patch: { unit: event.target.value },
                })
              }
            >
              {item.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.label}
                </option>
              ))}
            </select>
          ) : (
            <span>
              {item.unit_label?.replace(
                "reporting currency",
                draft.reportingCurrency || "currency",
              )}
            </span>
          )}
        </span>
      </Field>
    );
  };
  return (
    <div className={styles.modelInputs}>
      {own.length > 0 && (
        <>
          <p className={styles.subheading}>
            <KnowledgeGlyph kind="user_input" /> Your figures for this model
          </p>
          {own.map(inputField)}
        </>
      )}
      {assumptions.length > 0 && (
        <details className={styles.assumptions}>
          <summary>
            <KnowledgeGlyph kind="assumption" /> Assumptions ({assumptions.length}) — defaults apply
            when left empty
          </summary>
          {assumptions.map((item) => {
            const path = `models.${model.model_id}.assumptions.${item.id}`;
            return (
              <Field
                key={item.id}
                path={path}
                label={item.label}
                hint={item.rationale ?? item.description}
                messages={messages}
              >
                <span className={styles.unitInput}>
                  <input
                    id={fieldId(path)}
                    inputMode="decimal"
                    placeholder={item.default ? `default ${item.default}` : undefined}
                    value={settings?.assumptions[item.id] ?? ""}
                    aria-invalid={invalid(messages, path)}
                    onChange={(event) =>
                      dispatch({
                        type: "modelAssumption",
                        model: model.model_id,
                        input: item.id,
                        value: event.target.value,
                      })
                    }
                  />
                  <span>{item.unit_label}</span>
                </span>
              </Field>
            );
          })}
        </details>
      )}
    </div>
  );
}

const STATUS_TONE: Record<string, "good" | "neutral" | "outline" | "warning" | "critical"> = {
  included: "good",
  available: "outline",
  excluded: "neutral",
  blocked: "warning",
  not_applicable: "outline",
};

function ModelRow({
  model,
  draft,
  dispatch,
  messages,
}: {
  model: ModelPlan;
  draft: LabDraft;
  dispatch: Dispatch<DraftAction>;
  messages: FieldMessages;
}) {
  const mode = draft.models[model.model_id]?.mode ?? "auto";
  const relevant = model.status === "included" || model.status === "blocked" || mode === "include";
  const errors = model.issues.filter((issue) => issue.severity === "error");
  return (
    <li className={styles.modelRow} data-status={model.status}>
      <div className={styles.modelRowHeader}>
        <p className={styles.modelTitle}>{model.title}</p>
        <Badge tone={STATUS_TONE[model.status] ?? "outline"}>
          {MODEL_STATUS_LABEL[model.status]}
        </Badge>
      </div>
      <p className={styles.modelCovers}>{model.covers}</p>
      <ul className={styles.reasons}>
        {model.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <fieldset className={styles.segmented}>
        <legend className="visually-hidden">Use of {model.title}</legend>
        {(["auto", "include", "exclude"] as ModelMode[]).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={mode === option}
            onClick={() => dispatch({ type: "modelMode", model: model.model_id, mode: option })}
          >
            {option === "auto" ? "Auto" : option === "include" ? "Include" : "Exclude"}
          </button>
        ))}
      </fieldset>
      {errors.length > 0 && (
        <p className={styles.modelBlocked}>
          <Icon name="alert" size={12} />{" "}
          {errors.length === 1 ? "1 problem" : `${errors.length} problems`} to resolve below
        </p>
      )}
      {relevant && (
        <ModelInputs model={model} draft={draft} dispatch={dispatch} messages={messages} />
      )}
    </li>
  );
}

// --- Stress cases --------------------------------------------------------------------------------

function StressRow({
  item,
  index,
  draft,
  variables,
  dispatch,
  messages,
}: {
  item: DraftStress;
  index: number;
  draft: LabDraft;
  variables: EconomicVariable[];
  dispatch: Dispatch<DraftAction>;
  messages: FieldMessages;
}) {
  const base = `stress_cases[${index}]`;
  const set = (patch: Partial<DraftStress>) => dispatch({ type: "stress", key: item.key, patch });
  return (
    <li className={styles.stressRow}>
      <div className={styles.changeHeader}>
        <span className={styles.changeIndex}>Stress case {index + 1}</span>
        <button
          type="button"
          className={styles.iconButton}
          onClick={() => dispatch({ type: "removeStress", key: item.key })}
          aria-label={`Remove stress case ${index + 1}`}
        >
          <Icon name="trash" size={13} />
        </button>
      </div>
      <TextField
        path={`${base}.name`}
        label={<>Name{ofRow(`of stress case ${index + 1}`)}</>}
        value={item.name}
        inputMode="text"
        onChange={(value) => set({ name: value })}
        messages={messages}
      />
      <fieldset className={styles.segmented}>
        <legend className="visually-hidden">How the case is set</legend>
        <button
          type="button"
          aria-pressed={item.kind === "scale"}
          onClick={() => set({ kind: "scale" })}
        >
          A multiple of every change
        </button>
        <button
          type="button"
          aria-pressed={item.kind === "values"}
          onClick={() => set({ kind: "values" })}
        >
          Explicit values
        </button>
      </fieldset>
      {item.kind === "scale" ? (
        <TextField
          path={`${base}.scale`}
          label={<>Multiple{ofRow(`for stress case ${index + 1}`)}</>}
          value={item.scale}
          onChange={(value) => set({ scale: value })}
          messages={messages}
          suffix="×"
          hint="0.5 halves every change; 2 doubles it."
        />
      ) : (
        draft.changes
          .filter((change) => change.variableId)
          .map((change) => {
            const variable = variables.find((entry) => entry.id === change.variableId);
            const path = `${base}.changes.${change.variableId}`;
            return (
              <TextField
                key={change.key}
                path={path}
                label={
                  <>
                    {variable?.name ?? change.variableId}
                    {ofRow(`in stress case ${index + 1}`)}
                  </>
                }
                value={item.changes[change.variableId] ?? ""}
                onChange={(value) =>
                  dispatch({
                    type: "stressChange",
                    key: item.key,
                    variable: change.variableId,
                    value,
                  })
                }
                messages={messages}
                suffix={
                  change.changeType === "percent_change"
                    ? "%"
                    : variable?.value_kind === "rate"
                      ? "pp"
                      : variable?.unit
                }
                hint="Signed: −10 for a fall. Empty keeps the scenario's value."
              />
            );
          })
      )}
      <Messages messages={messages[base]} />
    </li>
  );
}

// --- The builder ---------------------------------------------------------------------------------

export function Builder({
  draft,
  dispatch,
  variables,
  plan,
  messages,
}: {
  draft: LabDraft;
  dispatch: Dispatch<DraftAction>;
  variables: EconomicVariable[];
  plan: ScenarioPlan | null;
  messages: FieldMessages;
}) {
  const included = plan?.models.filter((model) => model.status === "included").length ?? 0;
  return (
    <div className={styles.builder}>
      <Section title="Scenario">
        <TextField
          path="name"
          label="Name"
          inputMode="text"
          value={draft.name}
          onChange={(value) => dispatch({ type: "set", field: "name", value })}
          messages={messages}
        />
        <Field path="description" label="Description" messages={messages}>
          <textarea
            id={fieldId("description")}
            rows={2}
            value={draft.description}
            aria-invalid={invalid(messages, "description")}
            onChange={(event) =>
              dispatch({ type: "set", field: "description", value: event.target.value })
            }
          />
        </Field>
      </Section>

      <Section title="Changes" summary={`${draft.changes.length} of ${MAX_CHANGES}`}>
        <ul className={styles.changeList}>
          {draft.changes.map((change, index) => (
            <ChangeRow
              key={change.key}
              change={change}
              index={index}
              variables={variables}
              dispatch={dispatch}
              messages={messages}
              removable={draft.changes.length > 1}
            />
          ))}
        </ul>
        <Button
          size="sm"
          variant="ghost"
          icon={<Icon name="plus" size={14} />}
          disabled={draft.changes.length >= MAX_CHANGES}
          onClick={() => dispatch({ type: "addChange" })}
        >
          Add a change
        </Button>
      </Section>

      <Section title="Company and figures">
        <CompanyPicker draft={draft} dispatch={dispatch} plan={plan} messages={messages} />
        <TextField
          path="company.reporting_currency"
          label="Reporting currency"
          inputMode="text"
          value={draft.reportingCurrency}
          onChange={(value) =>
            dispatch({
              type: "set",
              field: "reportingCurrency",
              value: value.toUpperCase().slice(0, 3),
            })
          }
          messages={messages}
          hint="ISO 4217 code, e.g. INR. Nothing is converted between currencies."
        />
        <TextField
          path="company.annual_revenue"
          label="Annual revenue"
          value={draft.annualRevenue}
          onChange={(value) => dispatch({ type: "set", field: "annualRevenue", value })}
          messages={messages}
          suffix={`${draft.reportingCurrency || "currency"} / year`}
        />
        <TextField
          path="company.annual_operating_costs"
          label="Annual operating costs"
          value={draft.annualOperatingCosts}
          onChange={(value) => dispatch({ type: "set", field: "annualOperatingCosts", value })}
          messages={messages}
          suffix={`${draft.reportingCurrency || "currency"} / year`}
        />
        <Field
          path="markets.fx_rate"
          label="Exchange rate"
          hint="Reporting currency per US dollar, used by every model that converts dollars."
          messages={messages}
        >
          <fieldset className={styles.segmented}>
            <legend className="visually-hidden">Source of the exchange rate</legend>
            <button
              type="button"
              aria-pressed={draft.fxRate.source === "user"}
              onClick={() => dispatch({ type: "fx", patch: { source: "user" } })}
            >
              Enter a value
            </button>
            <button
              type="button"
              aria-pressed={draft.fxRate.source === "stored_observation"}
              onClick={() =>
                dispatch({
                  type: "fx",
                  patch: { source: "stored_observation", seriesId: "wb-ind-pa-nus-fcrf" },
                })
              }
            >
              Stored World Bank value
            </button>
          </fieldset>
          {draft.fxRate.source === "user" ? (
            <span className={styles.unitInput}>
              <input
                id={fieldId("markets.fx_rate")}
                inputMode="decimal"
                value={draft.fxRate.value}
                aria-invalid={invalid(messages, "markets.fx_rate")}
                onChange={(event) => dispatch({ type: "fx", patch: { value: event.target.value } })}
              />
              <span>{draft.reportingCurrency || "currency"} per USD</span>
            </span>
          ) : (
            <p className={styles.fieldHint} id={fieldId("markets.fx_rate")}>
              <KnowledgeGlyph kind="historical_data" /> The latest stored annual average of the
              World Bank's official exchange rate. The run records its period and licence.
            </p>
          )}
        </Field>
      </Section>

      <Section title="Timing">
        <div className={styles.fieldRow}>
          <TextField
            path="timing.start_month"
            label="Starts in month"
            inputMode="numeric"
            value={draft.startMonth}
            onChange={(value) => dispatch({ type: "set", field: "startMonth", value })}
            messages={messages}
          />
          <TextField
            path="timing.duration_months"
            label="Lasts (months)"
            inputMode="numeric"
            value={draft.durationMonths}
            onChange={(value) => dispatch({ type: "set", field: "durationMonths", value })}
            messages={messages}
            hint="0 = to the end"
          />
          <TextField
            path="timing.horizon_months"
            label="Horizon"
            inputMode="numeric"
            value={draft.horizonMonths}
            onChange={(value) => dispatch({ type: "set", field: "horizonMonths", value })}
            messages={messages}
            suffix="months"
          />
        </div>
      </Section>

      <Section title="Models" summary={plan ? `${included} included` : undefined}>
        {plan === null ? (
          <p className={styles.fieldHint}>The models appear once the scenario has a change.</p>
        ) : (
          <ul className={styles.modelList}>
            {plan.models.map((model) => (
              <ModelRow
                key={model.model_id}
                model={model}
                draft={draft}
                dispatch={dispatch}
                messages={messages}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Constraints" defaultOpen={false}>
        <fieldset className={styles.radioGroup}>
          <legend className={styles.fieldLabel}>Relationships the scenario may rely on</legend>
          {(
            [
              ["any", "Any validated relationship in the graph"],
              ["evidence_backed", "Evidence-backed relationships only"],
            ] as const
          ).map(([value, label]) => (
            <label key={value}>
              <input
                type="radio"
                name="evidence"
                checked={draft.evidence === value}
                onChange={() => dispatch({ type: "set", field: "evidence", value })}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={draft.storedMarketData}
            onChange={(event) =>
              dispatch({ type: "set", field: "storedMarketData", value: event.target.checked })
            }
          />
          Market baselines must be stored data, not typed values
        </label>
        <Messages messages={messages["constraints.evidence"]} />
      </Section>

      <Section
        title="Stress cases"
        summary={`${draft.stress.length} of ${MAX_STRESS}`}
        defaultOpen={draft.stress.length > 0}
      >
        <p className={styles.fieldHint}>
          Other magnitudes of the same changes, evaluated with the same models and assumptions. A
          case outside the rules is refused, never clipped.
        </p>
        <ul className={styles.stressList}>
          {draft.stress.map((item, index) => (
            <StressRow
              key={item.key}
              item={item}
              index={index}
              draft={draft}
              variables={variables}
              dispatch={dispatch}
              messages={messages}
            />
          ))}
        </ul>
        <Button
          size="sm"
          variant="ghost"
          icon={<Icon name="plus" size={14} />}
          disabled={draft.stress.length >= MAX_STRESS}
          onClick={() => dispatch({ type: "addStress" })}
        >
          Add a stress case
        </Button>
      </Section>

      <Section title="Version note" defaultOpen={false}>
        <TextField
          path="note"
          label="What this version changes"
          inputMode="text"
          value={draft.note}
          onChange={(value) => dispatch({ type: "set", field: "note", value })}
          messages={messages}
        />
      </Section>
    </div>
  );
}
