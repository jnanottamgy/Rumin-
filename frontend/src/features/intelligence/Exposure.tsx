/**
 * Exposure as the knowledge graph states it — which variables reach an entity, through
 * which validated relationships — never how much.
 *
 * - The **matrix** (workspace): companies × variables. A cell names the channels (C costs,
 *   R revenue, F financing costs); its border says how the variable reaches the company
 *   (solid: directly; dashed: through its industry; dotted: only upstream, through another
 *   variable). It is a table, so every cell also reads as text.
 * - The **paths** (one entity): each path as a line of hops, each hop drawn with the
 *   evidence pattern of its relationship, with the models able to simulate it.
 */
import { Link } from "react-router";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { cx } from "@/lib/cx";
import type {
  ExposureMap,
  ExposureMatrix,
  ExposureMatrixCell,
  ExposurePath,
  IntelligenceEdge,
  IntelligenceNode,
} from "@/types/api";
import { CHANNEL, CHANNEL_LETTER, DIRECTNESS, entityPath } from "./format";
import styles from "./Intelligence.module.css";

const GROUP: Record<string, string> = {
  commodity: "Commodities",
  exchange_rate: "Exchange rates",
  monetary_policy: "Interest rates",
  inflation: "Inflation",
};
const GROUP_ORDER = ["Commodities", "Exchange rates", "Interest rates", "Inflation", "Other"];

function groupOf(node: IntelligenceNode): string {
  const category = node.attributes.category;
  return (typeof category === "string" && GROUP[category]) || "Other";
}

function closest(directness: readonly string[]): string {
  if (directness.includes("direct")) return "direct";
  if (directness.includes("via_industry")) return "via_industry";
  return "upstream";
}

function cellText(cell: ExposureMatrixCell, company: string, variable: string): string {
  const channels = cell.channels.map((item) => CHANNEL[item]?.toLowerCase() ?? item).join(" and ");
  const how = cell.directness.map((item) => DIRECTNESS[item]?.toLowerCase() ?? item).join(", ");
  const models = cell.models.length
    ? `simulatable by ${cell.models.join(", ")}`
    : "no registered model";
  return `${variable} reaches the ${channels} of ${company}: ${how}; ${cell.paths} ${
    cell.paths === 1 ? "path" : "paths"
  }; weakest evidence ${EVIDENCE_ENCODING[cell.evidence_status].label.toLowerCase()}; ${models}.`;
}

export function ExposureMatrixTable({ matrix }: { matrix: ExposureMatrix }) {
  const cells = new Map(matrix.cells.map((cell) => [`${cell.company}|${cell.variable}`, cell]));
  const variables = [...matrix.variables].sort(
    (a, b) =>
      GROUP_ORDER.indexOf(groupOf(a)) - GROUP_ORDER.indexOf(groupOf(b)) ||
      a.name.localeCompare(b.name),
  );
  const groups = GROUP_ORDER.map((name) => ({
    name,
    count: variables.filter((variable) => groupOf(variable) === name).length,
  })).filter((group) => group.count > 0);

  if (!matrix.companies.length || !variables.length) {
    return <p className={styles.emptyLine}>The graph states no exposure yet.</p>;
  }
  return (
    <div className={styles.matrixFrame}>
      <table className={styles.matrix}>
        <caption className="visually-hidden">
          Which economic variables reach which companies, as the knowledge graph states it
        </caption>
        <thead>
          <tr>
            <td />
            {groups.map((group) => (
              <th key={group.name} scope="colgroup" colSpan={group.count}>
                {group.name}
              </th>
            ))}
          </tr>
          <tr>
            <th scope="col" className={styles.matrixCorner}>
              Company
            </th>
            {variables.map((variable) => (
              <th key={variable.key} scope="col" className={styles.matrixVariable}>
                <span>{variable.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.companies.map((company) => (
            <tr key={company.key}>
              <th scope="row">
                <Link to={entityPath(company.key)}>{company.name}</Link>
              </th>
              {variables.map((variable) => {
                const cell = cells.get(`${company.key}|${variable.key}`);
                if (!cell) {
                  return (
                    <td key={variable.key} className={styles.matrixEmpty}>
                      <span className="visually-hidden">Not stated</span>
                    </td>
                  );
                }
                const text = cellText(cell, company.name, variable.name);
                return (
                  <td key={variable.key} title={text}>
                    <span
                      className={cx(styles.cellMark, styles[`reach_${closest(cell.directness)}`])}
                      aria-hidden="true"
                    >
                      {cell.channels.map((item) => CHANNEL_LETTER[item] ?? item).join("")}
                    </span>
                    <span className="visually-hidden">{text}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className={styles.matrixKey} aria-label="Key">
        <li>
          <span className={styles.keyLetters}>C R F</span> costs, revenue, financing costs
        </li>
        <li>
          <span className={cx(styles.cellMark, styles.reach_direct)}>C</span> directly
        </li>
        <li>
          <span className={cx(styles.cellMark, styles.reach_via_industry)}>C</span> through its
          industry
        </li>
        <li>
          <span className={cx(styles.cellMark, styles.reach_upstream)}>C</span> only upstream,
          through another variable
        </li>
      </ul>
    </div>
  );
}

// --- One entity's paths ------------------------------------------------------------------------

function Hop({ edge }: { edge: IntelligenceEdge }) {
  const encoding = EVIDENCE_ENCODING[edge.evidence_status];
  return (
    <span className={styles.hop} title={`${edge.label}: ${encoding.label}`}>
      <svg width="34" height="10" viewBox="0 0 34 10" aria-hidden="true" focusable="false">
        <line
          x1="1"
          y1="5"
          x2="27"
          y2="5"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeDasharray={encoding.dash ?? undefined}
          strokeLinecap={encoding.linecap}
        />
        <path d="M27 1.5 32.5 5 27 8.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <span className="visually-hidden">
        {edge.label} ({encoding.label.toLowerCase()})
      </span>
    </span>
  );
}

function PathRow({ path, entity }: { path: ExposurePath; entity: IntelligenceNode }) {
  const influences = path.edges.filter((edge) => edge.edge_type === "influences");
  const affect = path.edges.find((edge) => edge.edge_type.startsWith("affects_"));
  const membership = path.edges.find((edge) => edge.edge_type === "in_industry");
  return (
    <li className={styles.path}>
      <p className={styles.pathLine}>
        {path.hops.map((node, index) => {
          const incoming = index > 0 ? influences[index - 1] : undefined;
          return (
            <span key={node.key} className={styles.pathPart}>
              {incoming && <Hop edge={incoming} />}
              <span className={cx(styles.node, index === path.hops.length - 1 && styles.nodeKey)}>
                {node.name}
              </span>
            </span>
          );
        })}
        {affect && <Hop edge={affect} />}
        {path.industry && (
          <span className={styles.pathPart}>
            <span className={styles.node}>{path.industry.name}</span>
            {membership && <Hop edge={membership} />}
          </span>
        )}
        <span className={cx(styles.node, styles.nodeEntity)}>{entity.name}</span>
      </p>
      <p className={styles.pathMeta}>
        <span className={styles.channel}>{CHANNEL[path.channel] ?? path.channel}</span>
        <span>{DIRECTNESS[path.directness]}</span>
        <span>Weakest link: {EVIDENCE_ENCODING[path.evidence_status].label.toLowerCase()}</span>
        <span>
          {path.models.length
            ? `Simulatable by ${path.models.join(", ")}`
            : "No registered model simulates it"}
        </span>
      </p>
    </li>
  );
}

export function ExposurePaths({ exposure }: { exposure: ExposureMap }) {
  const order = ["direct", "via_industry", "upstream"];
  const groups = order
    .map((kind) => ({ kind, paths: exposure.paths.filter((path) => path.directness === kind) }))
    .filter((group) => group.paths.length > 0);
  return (
    <div className={styles.exposure}>
      {groups.length === 0 ? (
        <p className={styles.emptyLine}>
          {exposure.removed_by_filter > 0
            ? `No path remains: the filter removed ${exposure.removed_by_filter}, because none rests on evidence-backed relationships only.`
            : `The knowledge graph states no exposure of ${exposure.entity.name}.`}
        </p>
      ) : (
        groups.map((group) => (
          <section key={group.kind} aria-label={DIRECTNESS[group.kind]}>
            <h4 className={styles.detailTitle}>
              {DIRECTNESS[group.kind]}
              <span className={cx(styles.muted, "tabular")}> {group.paths.length}</span>
            </h4>
            <ul className={styles.paths}>
              {group.paths.map((path) => (
                <PathRow
                  key={path.edges.map((edge) => edge.key).join("|")}
                  path={path}
                  entity={exposure.entity}
                />
              ))}
            </ul>
          </section>
        ))
      )}
      <ul className={styles.plainList}>
        {exposure.notes.map((note) => (
          <li key={note} className={styles.muted}>
            {note}
          </li>
        ))}
      </ul>
    </div>
  );
}

const ROLE: Record<string, string> = {
  supplier: "Supplied by",
  customer: "Supplies",
  lender: "Borrows from",
  borrower: "Lends to",
};

const CONTEXT: Record<string, string> = {
  industry: "Industry",
  sector: "Sector",
  country: "Country",
  currency: "Currency",
  competitor: "Competitor",
};

export function Relations({ exposure }: { exposure: ExposureMap }) {
  return (
    <div className={styles.relations}>
      <section aria-label="Supply and credit">
        <h4 className={styles.detailTitle}>Supply and credit</h4>
        {exposure.counterparties.length === 0 ? (
          <p className={styles.muted}>None recorded.</p>
        ) : (
          <ul className={styles.plainList}>
            {exposure.counterparties.map((item) => (
              <li key={item.edge.key}>
                <span className={styles.muted}>{ROLE[item.role]}</span>{" "}
                {item.level === "industry" ? (
                  <span>{item.counterparty.name} (industry)</span>
                ) : (
                  <Link to={entityPath(item.counterparty.key)}>{item.counterparty.name}</Link>
                )}
                <span className={styles.caveat}>{item.edge.caveat}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Context">
        <h4 className={styles.detailTitle}>Context, not exposure</h4>
        <ul className={styles.plainList}>
          {exposure.context.map((item) => (
            <li key={`${item.kind}:${item.node.key}`}>
              <span className={styles.muted}>{CONTEXT[item.kind] ?? item.kind}</span>{" "}
              {item.kind === "competitor" || item.kind === "industry" ? (
                <Link to={entityPath(item.node.key)}>{item.node.name}</Link>
              ) : (
                item.node.name
              )}
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Measured by">
        <h4 className={styles.detailTitle}>Series that measure these variables</h4>
        {exposure.series.length === 0 ? (
          <p className={styles.muted}>No catalogued series is recorded as a related measure.</p>
        ) : (
          <ul className={styles.plainList}>
            {exposure.series.map((item) => (
              <li key={item.series_key}>
                {item.info ? (
                  <Link to={`/data/series/${encodeURIComponent(item.info.series_id)}`}>
                    {item.info.name}
                  </Link>
                ) : (
                  item.series_key
                )}{" "}
                <span className={styles.muted}>
                  {item.info && item.info.observation_count > 0
                    ? `${item.info.observation_count} stored values`
                    : "no values stored"}
                </span>
                {item.edge.stated_difference && (
                  <span className={styles.caveat}>{item.edge.stated_difference}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {exposure.flagged.length > 0 && (
        <section aria-label="Flagged relationships">
          <h4 className={styles.detailTitle}>Flagged by the build, not used</h4>
          <ul className={styles.plainList}>
            {exposure.flagged.map((edge) => (
              <li key={edge.key}>
                {edge.label}: {edge.source} → {edge.target}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
