/**
 * The blocks of an answer. Paragraphs carry their citations inline; tables, stored series,
 * relationship paths and scenario cards were built by RUMIN from tool results, so their
 * figures come straight from a service. Interpretation and general-knowledge paragraphs are
 * labelled as such. A scenario card opens its draft in the Scenario Lab: the Analyst never
 * saves or executes a scenario.
 */
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { type ChartPoint, dateTime, nextPeriodFollows } from "@/features/data/chartMath";
import { TimeSeriesChart } from "@/features/data/TimeSeriesChart";
import { typeFromKey } from "@/features/graph/encoding";
import { percent, signed, stored } from "@/features/intelligence/format";
import { cx } from "@/lib/cx";
import { formatPeriod } from "@/lib/format";
import type {
  AnalystBlock,
  AnalystClarificationBlock,
  AnalystEvidence,
  AnalystNoticeBlock,
  AnalystPathsBlock,
  AnalystScenarioBlock,
  AnalystSeriesBlock,
  AnalystTableBlock,
  AnalystTextBlock,
  ScenarioInput,
} from "@/types/api";
import styles from "./Analyst.module.css";
import { Citations, type Highlight } from "./Evidence";
import { EVIDENCE_STATUS, internalLink, moneyText, percentText, segments } from "./format";

export interface BlockContext {
  evidence: Map<string, AnalystEvidence>;
  highlight: Highlight;
  prefix: string;
  onAsk: (question: string) => void;
  disabled: boolean;
  headline?: string; // the answer's headline, not repeated by a block
}

export function CitedText({ text, context }: { text: string; context: BlockContext }) {
  return (
    <>
      {segments(text).map((part, index) =>
        part.kind === "text" ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: the text never reorders
          <span key={index}>{part.text}</span>
        ) : (
          <Citations
            // biome-ignore lint/suspicious/noArrayIndexKey: the text never reorders
            key={index}
            ids={part.ids}
            evidence={context.evidence}
            highlight={context.highlight}
            prefix={context.prefix}
          />
        ),
      )}
    </>
  );
}

const ROLE_LABEL: Partial<Record<AnalystTextBlock["role"], string>> = {
  interpretation: "Interpretation — a reading of the evidence, not a stored fact",
  general: "General knowledge — not from RUMIN's records",
};

function TextView({ block, context }: { block: AnalystTextBlock; context: BlockContext }) {
  const label = ROLE_LABEL[block.role];
  if (block.role === "policy") {
    return (
      <p className={styles.policy}>
        <Icon name="info" size={14} />
        <span>{block.text}</span>
      </p>
    );
  }
  return (
    <div className={cx(styles.text, styles[`role_${block.role}`])}>
      {label && <p className={styles.roleLabel}>{label}</p>}
      <p>
        <CitedText text={block.text} context={context} />
      </p>
    </div>
  );
}

function TableView({ block, context }: { block: AnalystTableBlock; context: BlockContext }) {
  const cites = block.rows.some((row) => (row.citations ?? []).length > 0);
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <caption>
          {block.title}
          {block.total ? ` (the first ${block.rows.length} of ${block.total})` : ""}
        </caption>
        <thead>
          <tr>
            {block.columns.map((column) => (
              <th key={column.key} scope="col" className={cx(column.align === "end" && styles.end)}>
                {column.label}
              </th>
            ))}
            {cites && (
              <th scope="col" className={styles.end}>
                Source
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: rows are fixed once answered
            <tr key={rowIndex}>
              {block.columns.map((column, columnIndex) => {
                const value = row.cells[column.key] ?? "—";
                if (columnIndex === 0) {
                  return (
                    <th key={column.key} scope="row">
                      {internalLink(row.link) ? <Link to={row.link}>{value}</Link> : value}
                    </th>
                  );
                }
                return (
                  <td
                    key={column.key}
                    className={cx(column.align === "end" && cx(styles.end, "tabular"))}
                  >
                    {value}
                  </td>
                );
              })}
              {cites && (
                <td className={styles.end}>
                  <Citations
                    ids={row.citations ?? []}
                    evidence={context.evidence}
                    highlight={context.highlight}
                    prefix={context.prefix}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {block.note && <p className={styles.caption}>{block.note}</p>}
    </div>
  );
}

function SeriesView({ block, context }: { block: AnalystSeriesBlock; context: BlockContext }) {
  const points: ChartPoint[] = block.points.map((point) => ({
    key: point.period,
    time: dateTime(point.start),
    value: Number(point.value),
    flagged: false,
  }));
  return (
    <figure className={styles.figure}>
      <figcaption className={styles.figureHead}>
        {internalLink(block.link) ? <Link to={block.link}>{block.title}</Link> : block.title}
        <span className={styles.muted}>
          {" "}
          {block.unit}, {block.frequency}
        </span>{" "}
        <Citations
          ids={block.citations ?? []}
          evidence={context.evidence}
          highlight={context.highlight}
          prefix={context.prefix}
        />
      </figcaption>
      {points.length > 1 ? (
        <TimeSeriesChart
          points={points}
          label={block.title}
          unit={block.unit}
          contiguous={nextPeriodFollows(block.frequency)}
          describe={(index) => {
            const point = block.points[index];
            return point
              ? {
                  title: `${formatPeriod(point.period)}, ${block.unit}`,
                  value: stored(point.value),
                  notes: [],
                }
              : { title: "", value: "", notes: [] };
          }}
          endLabel={(index) => stored(block.points[index]?.value)}
        />
      ) : (
        <p className={styles.muted}>Only one stored value in this range.</p>
      )}
      <details className={styles.tableToggle}>
        <summary>Values as a table</summary>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Period</th>
              <th scope="col" className={styles.end}>
                Value ({block.unit})
              </th>
            </tr>
          </thead>
          <tbody>
            {block.points.map((point) => (
              <tr key={point.period}>
                <th scope="row">{formatPeriod(point.period)}</th>
                <td className={cx(styles.end, "tabular")}>{stored(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      {block.note && <p className={styles.caption}>{block.note}</p>}
    </figure>
  );
}

const DIRECTNESS: Record<string, string> = {
  direct: "Directly",
  via_industry: "Through its industry",
  upstream: "Upstream, through another variable",
};

/** The 3D universe's paths view between a path's two ends, when both are graph nodes. */
function universePaths(path: AnalystPathsBlock["paths"][number]): string | null {
  const from = path.steps[0]?.key;
  const to = path.steps[path.steps.length - 1]?.key;
  if (!from || !to || from === to || !typeFromKey(from) || !typeFromKey(to)) return null;
  return `/universe/3d?${new URLSearchParams({ from, to }).toString()}`;
}

function PathsView({ block, context }: { block: AnalystPathsBlock; context: BlockContext }) {
  return (
    <section className={styles.paths} aria-label={block.title}>
      <p className={styles.blockTitle}>
        {block.title}
        {block.total > block.paths.length ? ` (${block.paths.length} of ${block.total})` : ""}
      </p>
      <ol className={styles.pathList}>
        {block.paths.map((path) => (
          <li key={path.steps.map((step) => step.key).join(">")} className={styles.path}>
            <p className={styles.chain}>
              {path.steps.map((step, stepIndex) => (
                // A path never passes the same record twice.
                <span key={step.key} className={styles.step}>
                  {stepIndex > 0 && (
                    <span className={styles.link}>
                      {path.links[stepIndex - 1]?.label ?? "linked to"}
                    </span>
                  )}
                  {internalLink(step.link) ? (
                    <Link to={step.link} className={styles.node}>
                      {step.name}
                    </Link>
                  ) : (
                    <span className={styles.node}>{step.name}</span>
                  )}
                </span>
              ))}
            </p>
            <p className={styles.pathFacts}>
              {path.channel && <span>Channel: {path.channel}</span>}
              {path.directness && <span>{DIRECTNESS[path.directness] ?? path.directness}</span>}
              {path.evidence_status && (
                <span>
                  Weakest evidence: {EVIDENCE_STATUS[path.evidence_status] ?? path.evidence_status}
                </span>
              )}
              {(path.models ?? []).length > 0 ? (
                <span>
                  Models: <span className="mono">{path.models?.join(", ")}</span>
                </span>
              ) : (
                path.channel && <span>No model simulates it</span>
              )}
              <Citations
                ids={path.citations ?? []}
                evidence={context.evidence}
                highlight={context.highlight}
                prefix={context.prefix}
              />
              {universePaths(path) && (
                <Link to={universePaths(path) as string}>Shortest paths between them in 3D</Link>
              )}
            </p>
          </li>
        ))}
      </ol>
      {block.note && <p className={styles.caption}>{block.note}</p>}
    </section>
  );
}

const SCENARIO_STATUS: Record<AnalystScenarioBlock["status"], string> = {
  stored: "Stored execution",
  preview: "Preview, computed now and not stored",
  plan: "Plan: the models need figures first",
};

function ScenarioView({ block, context }: { block: AnalystScenarioBlock; context: BlockContext }) {
  const navigate = useNavigate();
  const lines = block.lines ?? [];
  const open = () =>
    navigate("/scenarios/new", {
      state: {
        draft: block.draft as unknown as ScenarioInput,
        notice:
          "Opened from the AI Analyst. Nothing is saved until you save it; enter or check the figures before executing.",
      },
    });
  return (
    <section
      className={cx(styles.scenario, styles[`scenario_${block.status}`])}
      aria-label={block.title}
    >
      <header className={styles.scenarioHead}>
        <p className={styles.scenarioStatus}>{SCENARIO_STATUS[block.status]}</p>
        <p className={styles.blockTitle}>{block.title}</p>
        {block.entity && (
          <p className={styles.muted}>
            For{" "}
            {internalLink(block.entity.link) ? (
              <Link to={block.entity.link}>{block.entity.name}</Link>
            ) : (
              block.entity.name
            )}
            {block.horizon_months ? `, over ${block.horizon_months} months` : ""}
          </p>
        )}
      </header>
      {block.changes.length > 0 && (
        <ul className={styles.changes}>
          {block.changes.map((change) => (
            <li key={change.variable_id}>
              <span>{change.name}</span>{" "}
              <span className="tabular">
                {change.change_type === "percent_change"
                  ? percent(change.value)
                  : `${signed(stored(change.value), change.value)} ${change.unit}`}
              </span>
              {change.modelled === false && (
                <span className={styles.muted}> (no model responds)</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {lines.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col" className={styles.end}>
                  Baseline
                </th>
                <th scope="col" className={styles.end}>
                  Change
                </th>
                <th scope="col" className={styles.end}>
                  Change, %
                </th>
                <th scope="col" className={styles.end}>
                  Source
                </th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <tr key={line.id}>
                  <th scope="row">{line.label}</th>
                  <td className={cx(styles.end, "tabular")}>
                    {moneyText(line.baseline, line.currency)}
                  </td>
                  <td className={cx(styles.end, "tabular")}>
                    {moneyText(line.change, line.currency, true)}
                  </td>
                  <td className={cx(styles.end, "tabular")}>{percentText(line.percent_change)}</td>
                  <td className={styles.end}>
                    <Citations
                      ids={line.citations ?? []}
                      evidence={context.evidence}
                      highlight={context.highlight}
                      prefix={context.prefix}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(block.missing ?? []).length > 0 && (
        <div className={styles.missing}>
          <p>Figures a person must enter first:</p>
          <ul>
            {[...new Set(block.missing)].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {(block.models ?? []).length > 0 && (
        <p className={styles.muted}>
          Models: <span className="mono">{block.models?.join(", ")}</span>
        </p>
      )}
      {[...new Set(block.notes ?? [])].map((note) => (
        <p key={note} className={styles.caption}>
          {note}
        </p>
      ))}
      <div className={styles.scenarioActions}>
        {block.draft && (
          <Button size="sm" variant="primary" onClick={open}>
            Open in the Scenario Lab
          </Button>
        )}
        {block.status === "stored" && internalLink(block.link) && (
          <Link to={block.link} className={styles.textLink}>
            Open the stored execution
          </Link>
        )}
        <Citations
          ids={block.citations ?? []}
          evidence={context.evidence}
          highlight={context.highlight}
          prefix={context.prefix}
        />
      </div>
    </section>
  );
}

const NOTICE_LABEL: Record<AnalystNoticeBlock["kind"], string> = {
  missing_data: "Missing data",
  assumption: "Assumption",
  limitation: "Limitation",
  conflict: "Conflicting sources",
  policy: "Policy",
  not_stored: "Not stored",
  illustrative: "Illustrative",
  fallback: "Fallback",
};

function NoticeView({ block, context }: { block: AnalystNoticeBlock; context: BlockContext }) {
  return (
    <aside className={cx(styles.notice, styles[`notice_${block.kind}`])}>
      <p className={styles.noticeHead}>
        {!block.title.toLowerCase().startsWith(NOTICE_LABEL[block.kind].toLowerCase()) && (
          <span className={styles.noticeKind}>{NOTICE_LABEL[block.kind]} </span>
        )}
        {block.title}
      </p>
      <p>
        <CitedText text={block.text} context={context} />{" "}
        <Citations
          ids={block.citations ?? []}
          evidence={context.evidence}
          highlight={context.highlight}
          prefix={context.prefix}
        />
      </p>
    </aside>
  );
}

function ClarificationView({
  block,
  context,
}: {
  block: AnalystClarificationBlock;
  context: BlockContext;
}) {
  return (
    <div className={styles.clarify}>
      {block.question !== context.headline && <p>{block.question}</p>}
      <div className={styles.options}>
        {block.options.map((option) => (
          <Button
            key={option.question}
            size="sm"
            disabled={context.disabled}
            onClick={() => context.onAsk(option.question)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

export function BlockView({ block, context }: { block: AnalystBlock; context: BlockContext }) {
  switch (block.type) {
    case "text":
      return <TextView block={block} context={context} />;
    case "table":
      return <TableView block={block} context={context} />;
    case "series":
      return <SeriesView block={block} context={context} />;
    case "paths":
      return <PathsView block={block} context={context} />;
    case "scenario":
      return <ScenarioView block={block} context={context} />;
    case "notice":
      return <NoticeView block={block} context={context} />;
    case "clarification":
      return <ClarificationView block={block} context={context} />;
    default:
      return null;
  }
}
