/**
 * Controls for Financial Intelligence.
 *
 * - **Thresholds**: the configurable thresholds, from the API's own specification (label,
 *   unit, range, default and the reason for the default). Overrides live in the URL, so a
 *   view with its thresholds can be linked; the backend validates them and every problem is
 *   shown beside its field.
 * - **Subjects**: the workspace, then each company and industry with what the graph states
 *   about it and its latest simulated headline.
 */
import { type FormEvent, useEffect, useId, useState } from "react";
import { NavLink, useNavigate } from "react-router";
import { Button } from "@/components/Button";
import { ApiError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import type { ThresholdOverrides } from "@/services/api";
import type { IntelligenceEntityList, IntelligenceEntitySummary, ThresholdSpec } from "@/types/api";
import { entityPath, money, percent } from "./format";
import styles from "./Intelligence.module.css";

export const THRESHOLD_NAMES = [
  "relative_change_percent",
  "point_change",
  "price_move_percent",
  "anomaly_score",
  "trend_significance",
  "volatility_high_percentile",
  "dependency_share_percent",
  "min_history",
  "window",
] as const;

export function thresholdsFrom(params: URLSearchParams): ThresholdOverrides {
  const found: Record<string, string> = {};
  for (const name of THRESHOLD_NAMES) {
    const value = params.get(name);
    if (value) found[name] = value;
  }
  return found;
}

export function thresholdKey(thresholds: ThresholdOverrides): string {
  return THRESHOLD_NAMES.map((name) => thresholds[name] ?? "").join("|");
}

/** Field problems from a 422 response, by threshold name. */
export function thresholdProblems(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.status !== 422) return {};
  const found: Record<string, string> = {};
  for (const detail of error.details) {
    const name = (detail.field ?? "").replace(/^thresholds\./, "");
    if (name) found[name] = detail.message;
  }
  return found;
}

function defined(overrides: ThresholdOverrides): Record<string, string> {
  const found: Record<string, string> = {};
  for (const [name, value] of Object.entries(overrides)) if (value) found[name] = value;
  return found;
}

export function ThresholdsPanel({
  specs,
  current,
  problems,
  onApply,
}: {
  specs: readonly ThresholdSpec[];
  current: ThresholdOverrides;
  problems: Record<string, string>;
  onApply: (next: ThresholdOverrides) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => defined(current));
  const base = useId();
  const changed = Object.values(current).filter(Boolean).length;

  useEffect(() => setValues(defined(current)), [current]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    for (const [name, value] of Object.entries(values)) {
      if (value.trim()) next[name] = value.trim();
    }
    onApply(next);
  }

  return (
    <details className={styles.thresholds} open={Object.keys(problems).length > 0 || undefined}>
      <summary>
        Thresholds
        <span className={styles.muted}>
          {changed ? ` ${changed} changed from the defaults` : " defaults"}
        </span>
      </summary>
      <form onSubmit={submit} className={styles.thresholdForm} noValidate>
        <p className={styles.muted}>
          A threshold decides what is reported, not what matters: lower one to see more.
        </p>
        <div className={styles.thresholdFields}>
          {specs.map((spec) => {
            const id = `${base}-${spec.name}`;
            const problem = problems[spec.name];
            return (
              <div key={spec.name} className={cx(styles.field, problem && styles.fieldInvalid)}>
                <label htmlFor={id}>{spec.label}</label>
                {spec.choices ? (
                  <select
                    id={id}
                    value={values[spec.name] ?? spec.default ?? ""}
                    onChange={(event) => setValues({ ...values, [spec.name]: event.target.value })}
                  >
                    {spec.choices.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    inputMode="decimal"
                    value={values[spec.name] ?? ""}
                    placeholder={spec.default || "by frequency"}
                    aria-invalid={problem ? true : undefined}
                    aria-describedby={`${id}-hint`}
                    onChange={(event) => setValues({ ...values, [spec.name]: event.target.value })}
                  />
                )}
                <p id={`${id}-hint`} className={problem ? styles.fieldError : styles.fieldHint}>
                  {problem ??
                    `${spec.unit.replaceAll("_", " ")}${
                      spec.minimum ? `, ${spec.minimum} to ${spec.maximum}` : ""
                    }`}
                </p>
              </div>
            );
          })}
        </div>
        <div className={styles.formActions}>
          <Button type="submit" size="sm" variant="primary">
            Apply
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setValues({});
              onApply({});
            }}
          >
            Use the defaults
          </Button>
        </div>
      </form>
    </details>
  );
}

const CHANNEL_WORD: Record<string, string> = {
  costs: "costs",
  revenue: "revenue",
  financing: "financing",
};

function channels(item: IntelligenceEntitySummary): string {
  const words = ["costs", "revenue", "financing"]
    .filter((channel) => item.by_channel[channel])
    .map((channel) => CHANNEL_WORD[channel] ?? channel);
  return words.length > 1
    ? `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`
    : (words[0] ?? "");
}

function SubjectLink({ item }: { item: IntelligenceEntitySummary }) {
  const impact = item.latest_impact;
  return (
    <li>
      <NavLink
        to={entityPath(item.entity.key)}
        className={({ isActive }) => cx(styles.subject, isActive && styles.subjectActive)}
      >
        <span className={styles.subjectName}>{item.entity.name}</span>
        <span className={styles.subjectMeta}>
          {item.paths === 0
            ? "No stated exposure"
            : `${item.variables} ${item.variables === 1 ? "variable" : "variables"}; ${channels(item)}`}
        </span>
        {impact && (
          <span className={cx(styles.subjectImpact, "tabular")}>
            {impact.label}: {money(impact.change, impact.currency, true)} (
            {percent(impact.percent_change)}), simulated
          </span>
        )}
      </NavLink>
    </li>
  );
}

export function SubjectRail({ entities }: { entities: IntelligenceEntityList | undefined }) {
  const companies = entities?.items.filter((item) => item.entity.node_type === "company") ?? [];
  const industries = entities?.items.filter((item) => item.entity.node_type === "industry") ?? [];
  return (
    <nav className={styles.rail} aria-label="Subjects">
      <NavLink
        to="/intelligence"
        end
        className={({ isActive }) =>
          cx(styles.subject, styles.workspace, isActive && styles.subjectActive)
        }
      >
        <span className={styles.subjectName}>Workspace</span>
        <span className={styles.subjectMeta}>Every finding, the exposure map, coverage</span>
      </NavLink>
      {companies.length > 0 && (
        <>
          <h2 className={styles.railHeading}>Companies</h2>
          <ul className={styles.subjects}>
            {companies.map((item) => (
              <SubjectLink key={item.entity.key} item={item} />
            ))}
          </ul>
        </>
      )}
      {industries.length > 0 && (
        <details className={styles.railFold}>
          <summary className={styles.railHeading}>Industries ({industries.length})</summary>
          <ul className={styles.subjects}>
            {industries.map((item) => (
              <SubjectLink key={item.entity.key} item={item} />
            ))}
          </ul>
        </details>
      )}
    </nav>
  );
}

/** Small screens: the same subjects as a compact picker. */
export function SubjectPicker({
  entities,
  current,
}: {
  entities: IntelligenceEntityList | undefined;
  current: string | undefined;
}) {
  const navigate = useNavigate();
  const id = useId();
  const companies = entities?.items.filter((item) => item.entity.node_type === "company") ?? [];
  const industries = entities?.items.filter((item) => item.entity.node_type === "industry") ?? [];
  return (
    <div className={styles.picker}>
      <label htmlFor={id}>Subject</label>
      <select
        id={id}
        value={current ?? ""}
        onChange={(event) =>
          navigate(event.target.value ? entityPath(event.target.value) : "/intelligence")
        }
      >
        <option value="">Workspace</option>
        {companies.length > 0 && (
          <optgroup label="Companies">
            {companies.map((item) => (
              <option key={item.entity.key} value={item.entity.key}>
                {item.entity.name}
              </option>
            ))}
          </optgroup>
        )}
        {industries.length > 0 && (
          <optgroup label="Industries">
            {industries.map((item) => (
              <option key={item.entity.key} value={item.entity.key}>
                {item.entity.name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </div>
  );
}
