/**
 * The input-to-output pathway of a run: how each scenario change travels through the
 * model's variables to the results. The one relationship taken from the knowledge graph
 * is drawn with its evidence pattern and links to the graph explorer; every other link is
 * one of the model's equations.
 *
 * When a new run arrives the change travels down the chain once — a pulse along each
 * link, layer by layer. Nothing moves when the reader asks for reduced motion.
 */
import { useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useTheme } from "@/app/theme";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { TypeGlyph } from "@/features/graph/GraphGlyph";
import { useElementSize } from "@/hooks/useElementSize";
import { cx } from "@/lib/cx";
import { formatExact } from "@/lib/decimal";
import type {
  EvidenceStatus,
  SimulationGraphEdge,
  SimulationPathwayEdge,
  SimulationPathwayNode,
} from "@/types/api";
import { formatInputValue, formatMoneyCompact, formatRatioPercent, isZero } from "./format";
import { KnowledgeGlyph, knowledgeOf } from "./knowledge";
import { layoutPathway, smoothPath } from "./pathwayLayout";
import styles from "./Simulation.module.css";

const CURRENCY_UNIT = /^[A-Z]{3}(?: per (?:year|month))?$/;

const BEFORE_RUN: Record<SimulationPathwayNode["kind"], string> = {
  input: "You set this",
  variable: "Graph variable",
  output: "Calculated by the model",
};

export function nodeValue(node: SimulationPathwayNode, hasValues = true): string {
  if (!hasValues) return BEFORE_RUN[node.kind];
  if (node.value === null) return node.kind === "variable" ? "Unchanged" : "Not set";
  if (node.kind === "variable") {
    return isZero(node.value) ? "Unchanged" : formatRatioPercent(node.value, 1, true);
  }
  if (node.kind === "input") return formatInputValue(node.value, node.unit ?? "");
  const unit = node.unit ?? "";
  const currency = CURRENCY_UNIT.test(unit) ? unit.slice(0, 3) : null;
  return currency ? formatMoneyCompact(node.value, currency, true) : `${node.value} ${unit}`;
}

function lagText(lag: string | null): string {
  if (lag === null || isZero(lag)) return "no lag";
  return lag === "1" ? "1-month lag" : `${formatExact(lag)}-month lag`;
}

export function edgeText(link: SimulationPathwayEdge): string {
  if (link.coefficient === null && link.lag_months === null) {
    return link.rule ? "graph relationship, β and lag from the assumptions" : "";
  }
  const parts = [];
  if (link.coefficient !== null) parts.push(`β = ${formatExact(link.coefficient)}`);
  if (link.rule) parts.push(lagText(link.lag_months));
  return parts.join(", ");
}

function graphLink(edge: SimulationGraphEdge): string {
  const query = new URLSearchParams({ from: edge.source, to: edge.target });
  return `/graph?${query.toString()}`;
}

function evidence(edge: SimulationGraphEdge | null): EvidenceStatus | null {
  const status = edge?.evidence_status;
  return status && status in EVIDENCE_ENCODING ? (status as EvidenceStatus) : null;
}

export function PathwayDiagram({
  nodes,
  links,
  animationKey,
  title = "How the change travels",
}: {
  nodes: SimulationPathwayNode[];
  links: SimulationPathwayEdge[];
  /** A new key replays the reveal (e.g. the run id); null never animates. */
  animationKey: string | null;
  title?: string;
}) {
  const { reducedMotion } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(containerRef, { width: 720, height: 0 });
  const [view, setView] = useState<"diagram" | "list">("diagram");
  const headingId = useId();
  const markerId = useId().replace(/:/g, "");

  const layout = useMemo(
    () => layoutPathway(nodes, links, { width: Math.max(width, 1) }),
    [nodes, links, width],
  );
  const names = new Map(nodes.map((node) => [node.id, node]));
  const animate = animationKey !== null && !reducedMotion;
  const graphStatus = links.map((link) => evidence(link.edge)).find((status) => status) ?? null;
  const hasValues = nodes.some((node) => node.value !== null);
  const showDiagram = view === "diagram" && layout.fits;

  return (
    <figure className={styles.pathway} aria-labelledby={headingId}>
      <div className={styles.figureHeader}>
        <h3 id={headingId} className={styles.figureTitle}>
          {title}
        </h3>
        <fieldset className={styles.toggle}>
          <legend className="visually-hidden">Pathway view</legend>
          <button
            type="button"
            aria-pressed={view === "diagram"}
            onClick={() => setView("diagram")}
            disabled={!layout.fits}
          >
            Diagram
          </button>
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
            List
          </button>
        </fieldset>
      </div>

      <div ref={containerRef} className={styles.pathwayMeasure}>
        {showDiagram ? (
          <div
            key={animationKey ?? "static"}
            className={styles.pathwayCanvas}
            style={{ height: layout.height + 8, width: layout.width }}
            data-animate={animate ? "true" : undefined}
          >
            <svg
              className={styles.pathwayLinks}
              width={layout.width}
              height={layout.height + 8}
              aria-hidden="true"
              focusable="false"
            >
              <defs>
                <marker
                  id={`arrow-${markerId}`}
                  viewBox="0 0 8 8"
                  refX="7"
                  refY="4"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M0 0.8 7 4 0 7.2Z" className={styles.arrowHead} />
                </marker>
              </defs>
              {layout.links.map(({ link, layer, points }) => {
                const d = smoothPath(points);
                const status = evidence(link.edge);
                const encoding = status ? EVIDENCE_ENCODING[status] : null;
                return (
                  <g key={`${link.source}->${link.target}`} style={{ "--layer": layer } as never}>
                    <path
                      d={d}
                      className={cx(styles.pathLink, link.rule && styles.pathLinkGraph)}
                      data-rule={link.rule ?? undefined}
                      strokeDasharray={encoding?.dash ?? undefined}
                      strokeLinecap={encoding?.linecap ?? "round"}
                      markerEnd={`url(#arrow-${markerId})`}
                    >
                      <title>
                        {`${names.get(link.source)?.label ?? link.source} ${link.label} ${
                          names.get(link.target)?.label ?? link.target
                        }${link.equations.length ? ` (${link.equations.join(", ")})` : ""}`}
                      </title>
                    </path>
                    {animate && (
                      <circle r="3.5" className={styles.pulse} opacity="0">
                        <animateMotion
                          path={d}
                          dur="0.75s"
                          begin={`${0.2 + layer * 0.34}s`}
                          fill="freeze"
                        />
                        <animate
                          attributeName="opacity"
                          values="0;1;1;0"
                          keyTimes="0;0.15;0.8;1"
                          dur="0.75s"
                          begin={`${0.2 + layer * 0.34}s`}
                          fill="freeze"
                        />
                      </circle>
                    )}
                  </g>
                );
              })}
            </svg>

            {layout.nodes.map(({ node, layer, x, y, width: w, height }) => (
              <div
                key={node.id}
                className={styles.pathNode}
                data-kind={node.kind}
                data-node-id={node.id}
                style={{ left: x, top: y, width: w, height, "--layer": layer } as never}
              >
                <span className={styles.pathNodeLabel}>
                  {node.kind === "variable" ? (
                    <TypeGlyph type="economic_variable" size={11} />
                  ) : (
                    <KnowledgeGlyph kind={knowledgeOf(node.knowledge)} />
                  )}
                  {node.label}
                </span>
                <span className={styles.pathNodeValue}>{nodeValue(node, hasValues)}</span>
              </div>
            ))}

            {layout.links
              .filter(({ link }) => link.edge)
              .map(({ link, points }) => {
                const edge = link.edge as SimulationGraphEdge;
                const start = points[0];
                const end = points[points.length - 1];
                if (!start || !end) return null;
                return (
                  <Link
                    key={`tag-${link.source}-${link.target}`}
                    to={graphLink(edge)}
                    className={styles.edgeTag}
                    style={{ left: (start.x + end.x) / 2 + 10, top: (start.y + end.y) / 2 - 11 }}
                    title={`${EVIDENCE_ENCODING[evidence(edge) ?? "unverified"].label}: ${edge.description}`}
                  >
                    <span className="visually-hidden">Knowledge-graph relationship:</span>{" "}
                    {edgeText(link)}
                  </Link>
                );
              })}
          </div>
        ) : (
          <ol className={styles.pathList}>
            {links.map((link) => {
              const source = names.get(link.source);
              const target = names.get(link.target);
              return (
                <li key={`${link.source}->${link.target}`}>
                  <span className={styles.pathListEnd}>
                    <strong>{source?.label ?? link.source}</strong>
                    {source && hasValues && <span> ({nodeValue(source)})</span>}
                  </span>{" "}
                  <span className={styles.pathListVerb}>{link.label}</span>{" "}
                  <span className={styles.pathListEnd}>
                    <strong>{target?.label ?? link.target}</strong>
                    {target && hasValues && <span> ({nodeValue(target)})</span>}
                  </span>
                  {link.edge && (
                    <span className={styles.pathListNote}>
                      Knowledge-graph relationship ({edgeText(link)};{" "}
                      {EVIDENCE_ENCODING[evidence(link.edge) ?? "unverified"].label.toLowerCase()}
                      ). <Link to={graphLink(link.edge)}>Open in the graph</Link>
                    </span>
                  )}
                  {link.equations.length > 0 && (
                    <span className={styles.pathListNote}>
                      Equations {link.equations.join(", ")}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <figcaption className={styles.figureCaption}>
        {graphStatus ? (
          <>
            Solid lines are the model's equations. The{" "}
            <svg width="28" height="8" aria-hidden="true" focusable="false">
              <path
                d="M1 4H27"
                className={cx(styles.pathLink, styles.pathLinkGraph)}
                strokeDasharray={EVIDENCE_ENCODING[graphStatus].dash ?? undefined}
                strokeLinecap={EVIDENCE_ENCODING[graphStatus].linecap}
              />
            </svg>{" "}
            line is a relationship the knowledge graph confirms (
            {EVIDENCE_ENCODING[graphStatus].label.toLowerCase()}); a shock travels only along
            relationships like it.
          </>
        ) : (
          <>
            Lines are the model's equations. No knowledge-graph relationship was needed: none of the
            changes travels along one.
          </>
        )}{" "}
        {hasValues ? "Values are the run's results, rounded for display." : null}
      </figcaption>
    </figure>
  );
}
