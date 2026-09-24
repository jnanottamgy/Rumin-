/**
 * The findings ledger: every insight as a ruled row — headline, grade, period — that opens
 * into what it rests on (the evidence chain), its values, assumptions, limitations, next
 * steps and sources. Rows are grouped by what kind of knowledge they report: observed data
 * first, then simulations, relationships and coverage. No finding is ranked or scored.
 */
import { useId, useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "@/components/Icon";
import { cx } from "@/lib/cx";
import { formatRounded, isDecimalString } from "@/lib/decimal";
import type { EvidenceGrade, Insight, InsightFact } from "@/types/api";
import { EvidenceChain, GradeMark, RefLinks } from "./Evidence";
import {
  GRADE,
  GRADE_ORDER,
  GROUPS,
  groupOf,
  KIND,
  type KindGroup,
  NEXT_STEP,
  refHref,
} from "./format";
import styles from "./Intelligence.module.css";

function factValue(fact: InsightFact): string {
  if (fact.value === null) return "—";
  if (!isDecimalString(fact.value)) return fact.value;
  const unit =
    fact.unit === "percentage_points" ? "pp" : fact.unit === "percent" ? "%" : (fact.unit ?? "");
  const places = unit === "%" || unit === "pp" ? 4 : 6;
  return `${formatRounded(fact.value, places)}${unit && unit !== "count" ? ` ${unit}` : ""}`;
}

const FACT_BASIS: Record<string, string> = {
  observation: "Observed",
  calculation: "Calculated",
  relationship: "Graph",
  record: "Record",
  simulation: "Simulated",
  assumption: "Entered or assumed",
  threshold: "Threshold",
};

function Details({
  insight,
  scenarios,
}: {
  insight: Insight;
  scenarios?: ReadonlyMap<string, string>;
}) {
  return (
    <div className={styles.findingDetails}>
      <p className={styles.statement}>{insight.statement}</p>
      <div className={styles.detailGrid}>
        <section aria-label="Evidence" className={styles.detailMain}>
          <h4 className={styles.detailTitle}>What it rests on</h4>
          <EvidenceChain chain={insight.chain} evidence={insight.evidence} scenarios={scenarios} />
        </section>
        <div className={styles.detailSide}>
          {insight.facts.length > 0 && (
            <section aria-label="Values">
              <h4 className={styles.detailTitle}>Values</h4>
              <table className={styles.facts}>
                <tbody>
                  {insight.facts.map((fact, index) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: facts are ordered and fixed
                    <tr key={index}>
                      <th scope="row">{fact.label}</th>
                      <td className="tabular">{factValue(fact)}</td>
                      <td className={styles.factBasis}>{FACT_BASIS[fact.basis] ?? fact.basis}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {insight.models.length > 0 && (
            <section aria-label="Models">
              <h4 className={styles.detailTitle}>Model and scenario</h4>
              <ul className={styles.plainList}>
                {insight.models.map((model) => (
                  <li key={`${model.kind}:${model.id}`}>
                    {model.label}
                    {model.models.length > 0 && (
                      <span className={styles.muted}> ({model.models.join(", ")})</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section aria-label="Period">
            <h4 className={styles.detailTitle}>Period</h4>
            <p>{insight.period.label}</p>
          </section>
        </div>
      </div>
      {insight.assumptions.length > 0 && (
        <details className={styles.fold}>
          <summary>Assumptions ({insight.assumptions.length})</summary>
          <ul className={styles.plainList}>
            {insight.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </details>
      )}
      {insight.limitations.length > 0 && (
        <section aria-label="Limitations" className={styles.limitations}>
          <h4 className={styles.detailTitle}>Limitations</h4>
          <ul className={styles.plainList}>
            {insight.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      {insight.next_steps.length > 0 && (
        <section aria-label="Next steps">
          <h4 className={styles.detailTitle}>What to investigate next</h4>
          <ul className={styles.nextSteps}>
            {insight.next_steps.map((step) => {
              const href = step.target ? refHref(step.target, scenarios) : null;
              return (
                <li key={`${step.action}:${step.text}`}>
                  <span className={styles.nextAction}>{NEXT_STEP[step.action] ?? step.action}</span>
                  <span>
                    {step.text}
                    {href && (
                      <>
                        {" "}
                        <Link to={href}>
                          Open
                          <Icon name="arrowRight" size={12} />
                        </Link>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      <section aria-label="Sources" className={styles.sources}>
        <h4 className={styles.detailTitle}>Sources</h4>
        <RefLinks refs={insight.sources} scenarios={scenarios} />
        <p className={styles.muted}>
          Rule {insight.rule}: {insight.rule_title}. Finding {insight.id}.
        </p>
      </section>
    </div>
  );
}

function Finding({
  insight,
  open,
  onToggle,
  scenarios,
}: {
  insight: Insight;
  open: boolean;
  onToggle: () => void;
  scenarios?: ReadonlyMap<string, string>;
}) {
  const panel = useId();
  return (
    <li className={cx(styles.finding, open && styles.findingOpen)}>
      <button
        type="button"
        className={styles.findingHead}
        aria-expanded={open}
        aria-controls={panel}
        onClick={onToggle}
      >
        <span className={styles.findingGrade}>
          <GradeMark grade={insight.evidence.grade} compact />
        </span>
        <span className={styles.findingText}>
          <span className={styles.findingKind}>{KIND[insight.kind] ?? insight.kind}</span>
          <span className={styles.headline}>{insight.headline}</span>
        </span>
        <span className={styles.findingMeta}>
          <span>{insight.period.label}</span>
          <span className={styles.chainCount}>
            {insight.chain.length} {insight.chain.length === 1 ? "link" : "links"}
          </span>
        </span>
        <Icon
          name="chevronDown"
          size={14}
          className={cx(styles.chevron, open && styles.chevronOpen)}
        />
      </button>
      {open && (
        <div id={panel} className={styles.findingBody}>
          <Details insight={insight} scenarios={scenarios} />
        </div>
      )}
    </li>
  );
}

export function Ledger({
  insights,
  scenarios,
  label = "Findings",
  emptyText = "No finding meets these filters.",
  initialOpen,
}: {
  insights: readonly Insight[];
  scenarios?: ReadonlyMap<string, string>;
  label?: string;
  emptyText?: string;
  initialOpen?: string;
}) {
  const [group, setGroup] = useState<KindGroup | "all">("all");
  const [floor, setFloor] = useState<EvidenceGrade | "any">("any");
  const [open, setOpen] = useState<ReadonlySet<string>>(
    () => new Set(initialOpen ? [initialOpen] : []),
  );
  const floorId = useId();

  const counts = useMemo(() => {
    const found: Record<string, number> = {};
    for (const insight of insights) {
      const id = groupOf(insight.kind);
      found[id] = (found[id] ?? 0) + 1;
    }
    return found;
  }, [insights]);

  const shown = useMemo(() => {
    const limit = floor === "any" ? GRADE_ORDER.length : GRADE_ORDER.indexOf(floor) + 1;
    const allowed = new Set(GRADE_ORDER.slice(0, limit));
    return insights.filter(
      (insight) =>
        (group === "all" || groupOf(insight.kind) === group) && allowed.has(insight.evidence.grade),
    );
  }, [insights, group, floor]);

  const sections = GROUPS.map((item) => ({
    ...item,
    insights: shown.filter((insight) => groupOf(insight.kind) === item.id),
  })).filter((item) => item.insights.length > 0);

  function toggle(id: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className={styles.ledger}>
      <div className={styles.ledgerControls}>
        <fieldset className={styles.segmented}>
          <legend className="visually-hidden">Show</legend>
          {[{ id: "all" as const, label: "All" }, ...GROUPS].map((item) => {
            const count = item.id === "all" ? insights.length : (counts[item.id] ?? 0);
            return (
              <label key={item.id} className={cx(group === item.id && styles.segmentOn)}>
                <input
                  type="radio"
                  name={`${floorId}-group`}
                  value={item.id}
                  checked={group === item.id}
                  disabled={item.id !== "all" && count === 0}
                  onChange={() => setGroup(item.id)}
                />
                {item.label}
                <span className={cx(styles.segmentCount, "tabular")}>{count}</span>
              </label>
            );
          })}
        </fieldset>
        <div className={styles.inlineField}>
          <label htmlFor={floorId}>Evidence at least</label>
          <select
            id={floorId}
            value={floor}
            onChange={(event) => setFloor(event.target.value as EvidenceGrade | "any")}
          >
            <option value="any">Any grade</option>
            {GRADE_ORDER.slice(0, -1).map((grade) => (
              <option key={grade} value={grade}>
                {GRADE[grade].label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {sections.length === 0 ? (
        <p className={styles.emptyLine}>{emptyText}</p>
      ) : (
        sections.map((section) => (
          <section key={section.id} className={styles.ledgerSection} aria-label={section.label}>
            <h3 className={styles.ledgerHeading}>
              {section.label}
              <span className={cx(styles.muted, "tabular")}> {section.insights.length}</span>
            </h3>
            <ul className={styles.findings} aria-label={`${label}: ${section.label}`}>
              {section.insights.map((insight) => (
                <Finding
                  key={insight.id}
                  insight={insight}
                  open={open.has(insight.id)}
                  onToggle={() => toggle(insight.id)}
                  scenarios={scenarios}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
