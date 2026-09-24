/**
 * Sources and the brief.
 *
 * - **Sources**: everything a dossier read — the graph build, the datasets (with licence and
 *   attribution), every relationship with its evidence status and stated rationale, and the
 *   executions and model runs with their hashes — so any finding can be checked.
 * - **Brief**: the structured object a future AI Analyst would receive. It is shown as data,
 *   with its narration rules, and can be downloaded; every number in it is computed by RUMIN.
 */
import { useMemo } from "react";
import { Button } from "@/components/Button";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import type { EntityAnalysis, IntelligenceBrief, IntelligenceEdge } from "@/types/api";
import { GradeLine } from "./Evidence";
import { GRADE, GRADE_ORDER } from "./format";
import styles from "./Intelligence.module.css";

function edgesOf(analysis: EntityAnalysis): IntelligenceEdge[] {
  const found = new Map<string, IntelligenceEdge>();
  for (const path of analysis.exposure.paths)
    for (const edge of path.edges) found.set(edge.key, edge);
  for (const item of analysis.exposure.counterparties) found.set(item.edge.key, item.edge);
  for (const item of analysis.exposure.context)
    for (const edge of item.edges) found.set(edge.key, edge);
  for (const item of analysis.exposure.series) found.set(item.edge.key, item.edge);
  return [...found.values()];
}

export function SourcesView({ analysis }: { analysis: EntityAnalysis }) {
  const edges = useMemo(() => edgesOf(analysis), [analysis]);
  const names = useMemo(() => {
    const found = new Map<string, string>([[analysis.entity.key, analysis.entity.name]]);
    for (const path of analysis.exposure.paths) {
      for (const node of path.hops) found.set(node.key, node.name);
      if (path.industry) found.set(path.industry.key, path.industry.name);
    }
    for (const item of analysis.exposure.counterparties) {
      found.set(item.counterparty.key, item.counterparty.name);
    }
    for (const item of analysis.exposure.context) found.set(item.node.key, item.node.name);
    return found;
  }, [analysis]);
  const datasets = new Map(
    analysis.series.map((item) => [item.subject.dataset.id, item.subject.dataset]),
  );
  const build = analysis.build;
  return (
    <div className={styles.sourcesView}>
      <section aria-label="Knowledge graph">
        <h3 className={styles.sectionTitle}>Knowledge graph</h3>
        <p>
          {build.id ? `Build #${build.id}` : "No build"}
          {build.finished_at && `, finished ${formatDateTime(build.finished_at)}`}.{" "}
          <span className={styles.muted}>{build.message}</span>
        </p>
      </section>
      <section aria-label="Relationships">
        <h3 className={styles.sectionTitle}>Relationships read ({edges.length})</h3>
        <div className={styles.tableFrame}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Relationship</th>
                <th scope="col">Evidence</th>
                <th scope="col">Stated reason and caveat</th>
              </tr>
            </thead>
            <tbody>
              {edges.map((edge) => {
                const encoding = EVIDENCE_ENCODING[edge.evidence_status];
                return (
                  <tr key={edge.key}>
                    <th scope="row">
                      {names.get(edge.source) ?? edge.source} {edge.label}{" "}
                      {names.get(edge.target) ?? edge.target}
                      <span className={cx(styles.muted, styles.hash)}> {edge.key}</span>
                    </th>
                    <td>
                      <span className={styles.status}>
                        <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
                          <line
                            x1="1"
                            y1="4"
                            x2="21"
                            y2="4"
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeDasharray={encoding.dash ?? undefined}
                            strokeLinecap={encoding.linecap}
                          />
                        </svg>
                        {encoding.label}
                      </span>
                      {edge.is_illustrative && <span className={styles.muted}> illustrative</span>}
                    </td>
                    <td>
                      {edge.rationale && <p>{edge.rationale}</p>}
                      <p className={styles.muted}>{edge.caveat}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-label="Datasets">
        <h3 className={styles.sectionTitle}>Datasets</h3>
        {datasets.size === 0 ? (
          <p className={styles.emptyLine}>No stored values were read.</p>
        ) : (
          <ul className={styles.plainList}>
            {[...datasets.values()].map((dataset) => (
              <li key={dataset.id}>
                {dataset.name} <span className={styles.muted}>{dataset.version}</span>,{" "}
                {dataset.license}
                {dataset.attribution && <p className={styles.muted}>{dataset.attribution}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
      {analysis.drivers && (
        <section aria-label="Executions and runs">
          <h3 className={styles.sectionTitle}>Execution and model runs</h3>
          <table className={styles.table}>
            <tbody>
              <tr>
                <th scope="row">Execution</th>
                <td className={cx("tabular", styles.hash)}>{analysis.drivers.execution.id}</td>
              </tr>
              <tr>
                <th scope="row">Inputs hash</th>
                <td className={cx("tabular", styles.hash)}>
                  {analysis.drivers.execution.inputs_hash ?? "—"}
                </td>
              </tr>
              <tr>
                <th scope="row">Result hash</th>
                <td className={cx("tabular", styles.hash)}>
                  {analysis.drivers.execution.result_hash ?? "—"}
                </td>
              </tr>
              {analysis.drivers.models.map((model) => (
                <tr key={model.run_id}>
                  <th scope="row">
                    {model.name} {model.version}
                  </th>
                  <td className={cx("tabular", styles.hash)}>
                    run {model.run_id}, definition {model.definition_hash.slice(0, 16)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section aria-label="Thresholds">
        <h3 className={styles.sectionTitle}>Thresholds used</h3>
        <table className={styles.facts}>
          <tbody>
            {Object.entries(analysis.thresholds).map(([name, value]) => (
              <tr key={name}>
                <th scope="row">{name.replaceAll("_", " ")}</th>
                <td className="tabular">{value ?? "by frequency"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export function BriefView({ brief }: { brief: IntelligenceBrief }) {
  const text = useMemo(() => JSON.stringify(brief, null, 2), [brief]);
  const grades = GRADE_ORDER.map((grade) => ({
    grade,
    count: brief.evidence.filter((item) => item.grade === grade).length,
  })).filter((item) => item.count > 0);

  function download() {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rumin-brief-${brief.entity.key.replace(":", "-")}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={styles.brief}>
      <p className={styles.lede}>
        What a future AI Analyst would receive about {brief.entity.name}: findings as data, each
        with its evidence and grade, and rules for narrating them. It computes nothing and adds
        nothing; the analyst would only put it into words.
      </p>
      <dl className={styles.readings}>
        <div>
          <dt>Observations</dt>
          <dd className="tabular">{brief.observations.length}</dd>
        </div>
        <div>
          <dt>Exposure paths</dt>
          <dd className="tabular">{brief.exposures.length}</dd>
        </div>
        <div>
          <dt>Relationships</dt>
          <dd className="tabular">{brief.relationships.length}</dd>
        </div>
        <div>
          <dt>Statements with evidence</dt>
          <dd className="tabular">{brief.evidence.length}</dd>
        </div>
      </dl>
      <ul className={styles.gradeCounts} aria-label="Statements by evidence grade">
        {grades.map((item) => (
          <li key={item.grade}>
            <GradeLine grade={item.grade} />
            {GRADE[item.grade].label}
            <span className="tabular"> {item.count}</span>
          </li>
        ))}
      </ul>
      <section aria-label="Narration rules">
        <h4 className={styles.detailTitle}>Rules for narrating it</h4>
        <ol className={styles.plainList}>
          {brief.narration_rules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ol>
      </section>
      <div className={styles.briefActions}>
        <Button size="sm" onClick={download}>
          Download the brief (JSON)
        </Button>
        <span className={styles.muted}>Format {brief.format}</span>
      </div>
      <details className={styles.fold}>
        <summary>Show the brief as data</summary>
        <pre className={styles.json}>{text}</pre>
      </details>
    </div>
  );
}
