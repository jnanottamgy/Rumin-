/**
 * The inputs of a model, grouped by the kind of knowledge they are. Values are typed as
 * text and sent exactly as typed; the API checks them and answers with one message per
 * field, shown beside the field and in a summary that links to it.
 */
import { type FormEvent, type ReactNode, useId } from "react";
import { Button } from "@/components/Button";
import { formatExact } from "@/lib/decimal";
import type {
  GraphNodeSearchResult,
  SimulationInputDefinition,
  SimulationModelDetail,
} from "@/types/api";
import {
  CATEGORY_TEXT,
  type FieldIssue,
  type FieldState,
  type FormState,
  fieldId,
  type InputCategory,
  inputsByCategory,
  issuesByField,
  rangeText,
} from "./form";
import { KnowledgeGlyph, type KnowledgeKind } from "./knowledge";
import styles from "./Simulation.module.css";

const CATEGORY_GLYPH: Record<InputCategory, KnowledgeKind> = {
  scenario_input: "scenario_input",
  market_baseline: "user_input",
  company_input: "user_input",
  assumption: "assumption",
  setting: "setting",
};

function unitSuffix(input: SimulationInputDefinition, currency: string): string | null {
  if (input.kind === "quantity" || input.kind === "graph_node" || input.kind === "currency") {
    return null;
  }
  const label = input.unit_label ?? "";
  return label.replace("reporting currency", currency || "reporting currency") || null;
}

function Field({
  input,
  field,
  issues,
  currency,
  airlines,
  onChange,
}: {
  input: SimulationInputDefinition;
  field: FieldState;
  issues: FieldIssue[];
  currency: string;
  airlines: GraphNodeSearchResult[] | null;
  onChange: (next: FieldState) => void;
}) {
  const id = fieldId(input.id);
  const helpId = `${id}-help`;
  const errorId = `${id}-errors`;
  const errors = issues;
  const range = rangeText(input);
  const source = input.sources[0];
  const suffix = unitSuffix(input, currency);
  const describedBy = [helpId, errors.length ? errorId : null].filter(Boolean).join(" ");
  const invalid = errors.length > 0;

  let control: ReactNode;
  if (input.kind === "graph_node") {
    control = (
      <select
        id={id}
        value={field.value}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        onChange={(event) => onChange({ ...field, value: event.target.value })}
      >
        <option value="">None: use the figures only</option>
        {(airlines ?? []).map((node) => (
          <option key={node.id} value={node.id}>
            {node.name}
            {node.nature !== "real" ? ` (${node.nature})` : ""}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <input
        id={id}
        type="text"
        inputMode={input.kind === "currency" ? "text" : "decimal"}
        autoComplete="off"
        spellCheck={false}
        maxLength={input.kind === "currency" ? 3 : 40}
        value={field.stored ? "" : field.value}
        disabled={field.stored}
        placeholder={input.default ?? (input.kind === "currency" ? "INR" : "")}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        aria-required={input.required || undefined}
        onChange={(event) => onChange({ ...field, value: event.target.value })}
      />
    );
  }

  return (
    <div className={styles.field} data-invalid={invalid || undefined}>
      <label htmlFor={id} className={styles.fieldLabel}>
        {input.label}
        {!input.required && input.default === null && (
          <span className={styles.optional}>optional</span>
        )}
      </label>
      {source && (
        <div
          className={styles.sourceChoice}
          role="radiogroup"
          aria-label={`${input.label}: source`}
        >
          <label>
            <input
              type="radio"
              name={`${id}-source`}
              checked={!field.stored}
              onChange={() => onChange({ ...field, stored: false })}
            />
            Enter a value
          </label>
          <label data-disabled={!source.available || undefined}>
            <input
              type="radio"
              name={`${id}-source`}
              checked={field.stored}
              disabled={!source.available}
              onChange={() => onChange({ ...field, stored: true })}
            />
            {source.available && source.latest_value
              ? `Use the stored ${source.latest_period} value, ${formatExact(source.latest_value)} ${source.unit}`
              : "Use a stored value (none stored yet)"}
          </label>
        </div>
      )}
      <div className={styles.control}>
        {control}
        {input.kind === "quantity" && (
          <select
            aria-label={`${input.label}: unit`}
            value={field.unit ?? ""}
            onChange={(event) => onChange({ ...field, unit: event.target.value })}
          >
            {input.units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.label}
              </option>
            ))}
          </select>
        )}
        {suffix && <span className={styles.suffix}>{suffix}</span>}
      </div>
      {errors.length > 0 && (
        <ul id={errorId} className={styles.fieldErrors}>
          {errors.map((issue) => (
            <li key={`${issue.code}-${issue.message}`}>{issue.message}</li>
          ))}
        </ul>
      )}
      <div id={helpId} className={styles.fieldHelp}>
        <p>{input.description}</p>
        {(range || input.default !== null) && (
          <p className={styles.fieldMeta}>
            {input.default !== null && <>Default {formatExact(input.default)}. </>}
            {range && <>Allowed {range}.</>}
          </p>
        )}
        {source && <p className={styles.fieldMeta}>{source.caveat}</p>}
        {input.rationale && input.category === "assumption" && (
          <p className={styles.fieldMeta}>{input.rationale}</p>
        )}
      </div>
    </div>
  );
}

export function SimulationForm({
  model,
  form,
  label,
  issues,
  busy,
  airlines,
  onChange,
  onLabelChange,
  onValidate,
  onRun,
  onExample,
  onClear,
}: {
  model: SimulationModelDetail;
  form: FormState;
  label: string;
  issues: FieldIssue[];
  busy: "validating" | "running" | null;
  airlines: GraphNodeSearchResult[] | null;
  onChange: (id: string, next: FieldState) => void;
  onLabelChange: (value: string) => void;
  onValidate: () => void;
  onRun: () => void;
  onExample: (() => void) | null;
  onClear: () => void;
}) {
  const byField = issuesByField(issues);
  const errors = issues;
  const currency = form.reporting_currency?.value.trim().toUpperCase() ?? "";
  const labelId = useId();
  const summaryId = useId();
  const assumptionsOpen = model.inputs.some(
    (input) =>
      input.category === "assumption" &&
      ((form[input.id]?.value ?? "") !== "" || (byField[input.id]?.length ?? 0) > 0),
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onRun();
  }

  return (
    <form className={styles.form} onSubmit={submit} noValidate aria-describedby={summaryId}>
      <div id={summaryId} aria-live="polite">
        {errors.length > 0 && (
          <div className={styles.errorSummary} role="alert">
            <p>
              {errors.length === 1
                ? "One input needs attention"
                : `${errors.length} inputs need attention`}
            </p>
            <ul>
              {errors.map((issue) => (
                <li key={`${issue.field}-${issue.code}-${issue.message}`}>
                  {issue.field && form[issue.field] ? (
                    <a
                      href={`#${fieldId(issue.field)}`}
                      onClick={(event) => {
                        const target = document.getElementById(fieldId(issue.field ?? ""));
                        if (!target) return;
                        event.preventDefault();
                        target.focus();
                        target.scrollIntoView?.({ block: "center" });
                      }}
                    >
                      {issue.message}
                    </a>
                  ) : (
                    issue.message
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {inputsByCategory(model).map(({ category, inputs }) => {
        const fields = inputs.map((input) => (
          <Field
            key={input.id}
            input={input}
            field={form[input.id] ?? { value: "", unit: null, stored: false }}
            issues={byField[input.id] ?? []}
            currency={currency}
            airlines={airlines}
            onChange={(next) => onChange(input.id, next)}
          />
        ));
        const legend = (
          <>
            <KnowledgeGlyph kind={CATEGORY_GLYPH[category]} />
            {CATEGORY_TEXT[category].title}
          </>
        );
        if (category === "assumption") {
          return (
            <details key={category} className={styles.fieldset} open={assumptionsOpen}>
              <summary className={`${styles.legend} ${styles.summary}`}>
                {legend}
                <span className={styles.legendNote}>{inputs.length} parameters with defaults</span>
              </summary>
              <p className={styles.fieldsetNote}>{CATEGORY_TEXT[category].note}</p>
              {fields}
            </details>
          );
        }
        return (
          <fieldset key={category} className={styles.fieldset}>
            <legend className={styles.legend}>{legend}</legend>
            <p className={styles.fieldsetNote}>{CATEGORY_TEXT[category].note}</p>
            {fields}
          </fieldset>
        );
      })}

      <div className={styles.field}>
        <label htmlFor={labelId} className={styles.fieldLabel}>
          Name this run <span className={styles.optional}>optional</span>
        </label>
        <div className={styles.control}>
          <input
            id={labelId}
            type="text"
            maxLength={120}
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
          />
        </div>
      </div>

      <div className={styles.formActions}>
        <Button variant="primary" type="submit" disabled={busy !== null}>
          {busy === "running" ? "Running…" : "Run simulation"}
        </Button>
        <Button onClick={onValidate} disabled={busy !== null}>
          {busy === "validating" ? "Checking…" : "Check inputs"}
        </Button>
      </div>
      <div className={styles.formSecondary}>
        {onExample && (
          <Button variant="ghost" size="sm" onClick={onExample} disabled={busy !== null}>
            Fill a hypothetical example
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onClear} disabled={busy !== null}>
          Clear the form
        </Button>
      </div>
    </form>
  );
}
