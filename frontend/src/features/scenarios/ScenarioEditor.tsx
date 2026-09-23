import type { Dispatch } from "react";
import { Button } from "@/components/Button";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { formatChange } from "@/lib/format";
import type { ChangeType, EconomicVariable } from "@/types/api";
import styles from "./ScenarioEditor.module.css";
import {
  CHANGE_TYPE_LABEL,
  DESCRIPTION_MAX,
  describeShock,
  type EditorAction,
  type EditorState,
  MAX_SHOCKS,
  NAME_MAX,
  ruleFor,
  type ShockDraft,
  shockField,
} from "./scenarioModel";

const CATEGORY_LABEL: Record<EconomicVariable["category"], string> = {
  commodity: "Commodities",
  monetary_policy: "Monetary policy",
  exchange_rate: "Exchange rates",
  inflation: "Inflation",
};

export const fieldId = (key: string) => `scenario-field-${key.replace(/\./g, "-")}`;

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={`${id}-error`} className={styles.fieldError}>
      <Icon name="alert" size={12} /> {message}
    </p>
  );
}

function ShockRow({
  shock,
  index,
  variables,
  errors,
  dispatch,
  canRemove,
}: {
  shock: ShockDraft;
  index: number;
  variables: EconomicVariable[];
  errors: EditorState["errors"];
  dispatch: Dispatch<EditorAction>;
  canRemove: boolean;
}) {
  const variable = variables.find((candidate) => candidate.id === shock.variableId);
  const rules = variable?.scenario_rules ?? [];
  const rule = ruleFor(variable, shock.changeType);
  const ids = {
    variable: fieldId(shockField(shock.key, "variableId")),
    changeType: fieldId(shockField(shock.key, "changeType")),
    value: fieldId(shockField(shock.key, "value")),
    note: fieldId(shockField(shock.key, "note")),
  };
  const error = (field: "variableId" | "changeType" | "value" | "note") =>
    errors[shockField(shock.key, field)];
  const categories = [...new Set(variables.map((candidate) => candidate.category))];

  return (
    <li className={styles.shock}>
      <div className={styles.shockHeader}>
        <p className={styles.shockIndex}>Input {index + 1}</p>
        <EpistemicBadge category="scenario_input" />
        {canRemove && (
          <button
            type="button"
            className={styles.remove}
            onClick={() => dispatch({ type: "removeShock", key: shock.key })}
            aria-label={`Remove input ${index + 1}`}
          >
            <Icon name="trash" size={14} />
          </button>
        )}
      </div>

      <div className={styles.field}>
        <label htmlFor={ids.variable}>Economic variable</label>
        <select
          id={ids.variable}
          value={shock.variableId}
          aria-invalid={Boolean(error("variableId"))}
          aria-describedby={error("variableId") ? `${ids.variable}-error` : undefined}
          onChange={(event) => {
            const next = variables.find((candidate) => candidate.id === event.target.value);
            dispatch({
              type: "updateShock",
              key: shock.key,
              // Start from the first kind of change the variable allows.
              patch: {
                variableId: event.target.value,
                changeType: next?.scenario_rules[0]?.change_type ?? "",
              },
            });
          }}
        >
          <option value="">Choose a variable…</option>
          {categories.map((category) => (
            <optgroup key={category} label={CATEGORY_LABEL[category]}>
              {variables
                .filter((candidate) => candidate.category === category)
                .map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name} ({candidate.unit})
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        <FieldError id={ids.variable} message={error("variableId")} />
      </div>

      {variable && (
        <>
          <fieldset
            className={styles.field}
            aria-invalid={Boolean(error("changeType"))}
            aria-describedby={error("changeType") ? `${ids.changeType}-error` : undefined}
          >
            <legend>Kind of change</legend>
            <div className={styles.segmented}>
              {rules.map((candidate, ruleIndex) => (
                <label key={candidate.change_type}>
                  <input
                    id={ruleIndex === 0 ? ids.changeType : undefined}
                    type="radio"
                    name={`${shock.key}-change-type`}
                    value={candidate.change_type}
                    checked={shock.changeType === candidate.change_type}
                    onChange={() =>
                      dispatch({
                        type: "updateShock",
                        key: shock.key,
                        patch: { changeType: candidate.change_type as ChangeType },
                      })
                    }
                  />
                  <span>{CHANGE_TYPE_LABEL[candidate.change_type]}</span>
                </label>
              ))}
            </div>
            {variable.value_kind === "rate" && (
              <p className={styles.hint}>
                Rates change in percentage points: a percentage of a percentage is ambiguous.
              </p>
            )}
            <FieldError id={ids.changeType} message={error("changeType")} />
          </fieldset>

          <div className={styles.field}>
            <label htmlFor={ids.value}>Change</label>
            <div className={styles.valueInput}>
              <input
                id={ids.value}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                placeholder={shock.changeType === "percent_change" ? "e.g. 30" : "e.g. 0.25"}
                value={shock.value}
                aria-invalid={Boolean(error("value"))}
                aria-describedby={`${ids.value}-hint${error("value") ? ` ${ids.value}-error` : ""}`}
                onChange={(event) =>
                  dispatch({
                    type: "updateShock",
                    key: shock.key,
                    patch: { value: event.target.value },
                  })
                }
              />
              <span className={styles.unit}>{rule?.unit_label ?? ""}</span>
            </div>
            {rule && (
              <p id={`${ids.value}-hint`} className={styles.hint}>
                Allowed: {rule.minimum_exclusive ? "more than" : "from"}{" "}
                {formatChange(rule.minimum, rule.unit_label)} to{" "}
                {formatChange(rule.maximum, rule.unit_label)}, up to 4 decimal places.
              </p>
            )}
            <FieldError id={ids.value} message={error("value")} />
          </div>

          <div className={styles.field}>
            <label htmlFor={ids.note}>
              Note <span className={styles.optional}>(optional)</span>
            </label>
            <input
              id={ids.note}
              type="text"
              value={shock.note}
              maxLength={500}
              aria-invalid={Boolean(error("note"))}
              onChange={(event) =>
                dispatch({
                  type: "updateShock",
                  key: shock.key,
                  patch: { note: event.target.value },
                })
              }
            />
            <FieldError id={ids.note} message={error("note")} />
          </div>

          <p className={styles.preview}>{describeShock(shock, variable)}</p>
        </>
      )}
    </li>
  );
}

export function ScenarioEditor({
  state,
  dispatch,
  variables,
}: {
  state: EditorState;
  dispatch: Dispatch<EditorAction>;
  variables: EconomicVariable[];
}) {
  const { draft, errors } = state;
  const nameId = fieldId("name");
  const descriptionId = fieldId("description");

  return (
    <div className={styles.editor}>
      <div className={styles.field}>
        <label htmlFor={nameId}>Scenario name</label>
        <input
          id={nameId}
          type="text"
          value={draft.name}
          maxLength={NAME_MAX + 20}
          placeholder="e.g. Oil price shock"
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errors.name ? `${nameId}-error` : undefined}
          onChange={(event) => dispatch({ type: "setName", value: event.target.value })}
        />
        <FieldError id={nameId} message={errors.name} />
      </div>

      <div className={styles.field}>
        <label htmlFor={descriptionId}>
          Description <span className={styles.optional}>(optional)</span>
        </label>
        <textarea
          id={descriptionId}
          rows={2}
          value={draft.description}
          maxLength={DESCRIPTION_MAX + 50}
          placeholder="What question is this scenario meant to explore?"
          aria-invalid={Boolean(errors.description)}
          onChange={(event) => dispatch({ type: "setDescription", value: event.target.value })}
        />
        <FieldError id={descriptionId} message={errors.description} />
      </div>

      <div className={styles.inputsHeader}>
        <h3>Scenario inputs</h3>
        <p className={styles.hint}>The variables you change. Up to {MAX_SHOCKS} per scenario.</p>
      </div>
      <FieldError id={fieldId("shocks")} message={errors.shocks} />
      <ol className={styles.shocks}>
        {draft.shocks.map((shock, index) => (
          <ShockRow
            key={shock.key}
            shock={shock}
            index={index}
            variables={variables}
            errors={errors}
            dispatch={dispatch}
            canRemove={draft.shocks.length > 1}
          />
        ))}
      </ol>
      <Button
        size="sm"
        icon={<Icon name="plus" size={14} />}
        onClick={() => dispatch({ type: "addShock" })}
        disabled={draft.shocks.length >= MAX_SHOCKS}
      >
        Add input
      </Button>
    </div>
  );
}
