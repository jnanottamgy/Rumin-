/**
 * The impact pathway: how each change travelled to each line, as the engine computed it.
 *
 * Links are drawn by what they are, never by what they suggest: a sky line is a
 * knowledge-graph relationship the engine propagated along (its coefficient and lag are on
 * the node it reaches); an ink line is applied or computed by a model's equations; a
 * hairline is the Lab adding items into lines. The graph context a model cites — the
 * stated relationships that made it apply — carries no value, so it is not drawn as a step:
 * it is listed in the model's lane header. What the graph states but no model simulates is
 * listed under the diagram, apart.
 *
 * Selecting a node or link highlights its chain and opens the inspector. During a replay
 * of the simulated months, each node shows its value in that month and stays dim until
 * the month its change first reaches it. Every value shown was computed by the backend.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { KnowledgeGlyph, type KnowledgeKind } from "@/features/simulation/knowledge";
import { useElementSize } from "@/hooks/useElementSize";
import { cx } from "@/lib/cx";
import { formatExact } from "@/lib/decimal";
import type { EvidenceStatus, LabPathway, LabPathwayLink, LabPathwayNode } from "@/types/api";
import { EVIDENCE_LABEL, nodeValue, SIMULATION_LABEL } from "./format";
import {
  chainOf,
  type Lane,
  layoutPathway,
  NODE_HEIGHT,
  type PlacedLink,
  type PlacedNode,
} from "./pathwayLayout";
import styles from "./ScenarioLab.module.css";

type Selection =
  | { kind: "node"; id: string }
  | { kind: "link"; id: string }
  | { kind: "context"; id: string }
  | null;

/** How the pathway names its steps: the plain label, and one that says where it sits. */
interface Names {
  label: (id: string) => string;
  describe: (id: string) => string;
}

const KIND_LABEL: Record<LabPathwayNode["kind"], string> = {
  change: "Scenario change",
  variable: "Variable moved by a model",
  context: "Graph context (cited)",
  driver: "Model line item",
  line: "Lab line",
  metric: "Lab metric",
};

const LINK_LABEL: Record<LabPathwayLink["kind"], string> = {
  applies: "Your change, entering the model",
  transmission: "Propagated along a graph relationship",
  equation: "Model equation",
  aggregation: "Added into a line by the Lab",
  cited: "Cited graph context — carries no value",
};

/** A cited relationship as the sentence the graph states. */
function statement(link: LabPathwayLink, names: Names): string {
  return `${names.label(link.source)} ${link.label} ${names.label(link.target)}`;
}

/** The coefficient and lag of the relationship a variable was propagated along. */
function transmissionChip(link: LabPathwayLink): string {
  const coefficient = link.coefficient === null ? "" : `β ${formatExact(link.coefficient)}`;
  const lag = link.lag_months === null ? "" : `lag ${link.lag_months}`;
  return [coefficient, lag].filter(Boolean).join(" · ");
}

function knowledgeKind(node: LabPathwayNode): KnowledgeKind | null {
  if (node.knowledge === "scenario_input") return "scenario_input";
  if (node.knowledge === "simulated") return "simulated";
  return null;
}

/**
 * The node's value in `month` (1-based), or its horizon total when month is null. A step
 * with no monthly series (a metric, computed over the horizon) has no value in a month.
 */
function valueAt(node: LabPathwayNode, month: number | null): string | null {
  if (month === null) return node.value;
  if (!node.monthly) return node.kind === "change" ? node.value : null;
  return node.monthly[month - 1] ?? null;
}

function reached(node: PlacedNode, month: number | null): boolean {
  if (month === null || !node.node) return true;
  if (node.node.kind === "metric") return false;
  const first = node.node.first_month;
  return first !== null && first <= month;
}

function graphHref(link: LabPathwayLink): string | null {
  if (!link.edge) return null;
  const [source, target] = [link.source, link.target].map((end) =>
    end.includes(":variable:") ? end.slice(end.indexOf(":variable:") + 1) : end,
  );
  return `/graph?${new URLSearchParams({ from: source ?? "", to: target ?? "" }).toString()}`;
}

function evidenceOf(link: LabPathwayLink): EvidenceStatus | null {
  const status = link.edge?.evidence_status;
  return status && status in EVIDENCE_ENCODING ? (status as EvidenceStatus) : null;
}

function LinkTitle({ link, names }: { link: LabPathwayLink; names: Names }) {
  if (link.kind === "cited")
    return <p className={styles.inspectorTitle}>{statement(link, names)}</p>;
  // A change enters a model as the same variable: name the model it enters.
  const target =
    link.kind === "applies" && link.group
      ? names.label(`group:${link.group}`)
      : names.label(link.target);
  return (
    <p className={styles.inspectorTitle}>
      {names.label(link.source)}
      <Icon name="arrowRight" size={14} />
      {target}
    </p>
  );
}

function LinkDetails({
  link,
  names,
  caution = true,
}: {
  link: LabPathwayLink;
  names: Names;
  caution?: boolean;
}) {
  const evidence = evidenceOf(link);
  const href = graphHref(link);
  return (
    <div className={styles.inspectorBody}>
      <LinkTitle link={link} names={names} />
      <dl className={styles.facts}>
        <div>
          <dt>Type</dt>
          <dd>{LINK_LABEL[link.kind]}</dd>
        </div>
        <div>
          <dt>Used for simulation</dt>
          <dd>{SIMULATION_LABEL[link.simulation]}</dd>
        </div>
        {link.edge && (
          <>
            <div>
              <dt>Graph relationship</dt>
              <dd>
                {link.edge.relationship}
                {href && (
                  <>
                    {" · "}
                    <Link to={href}>open in the graph</Link>
                  </>
                )}
              </dd>
            </div>
            <div>
              <dt>Evidence status</dt>
              <dd>
                {EVIDENCE_LABEL[link.edge.evidence_status] ?? link.edge.evidence_status}
                {evidence && (
                  <span className={styles.factNote}>{EVIDENCE_ENCODING[evidence].summary}</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Source record</dt>
              <dd className="mono">
                {link.edge.edge_key}
                {link.edge.is_illustrative && (
                  <span className={styles.factNote}>Illustrative sample data.</span>
                )}
              </dd>
            </div>
          </>
        )}
        {link.coefficient !== null && (
          <div>
            <dt>Coefficient (β)</dt>
            <dd className="tabular">{formatExact(link.coefficient)}</dd>
          </div>
        )}
        {link.lag_months !== null && (
          <div>
            <dt>Lag</dt>
            <dd>{link.lag_months === 1 ? "1 month" : `${link.lag_months} months`}</dd>
          </div>
        )}
        {link.window && (
          <div>
            <dt>Months in effect</dt>
            <dd>
              {link.window.first_month ?? "—"}
              {" to "}
              {link.window.last_month ?? "the end of the horizon"}
            </dd>
          </div>
        )}
      </dl>
      {link.equations.length > 0 && (
        <section className={styles.inspectorSection}>
          <h4>Equations</h4>
          <ul className={styles.formulaList}>
            {link.equations.map((equation) => (
              <li key={equation.id}>
                <span className={styles.equationId}>{equation.id}</span>
                <span>
                  {equation.name && <span className={styles.equationName}>{equation.name}</span>}
                  {equation.formula && <code>{equation.formula}</code>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {link.assumptions.length > 0 && (
        <section className={styles.inspectorSection}>
          <h4>Assumptions used</h4>
          <ul className={styles.assumptionList}>
            {link.assumptions.map((item) => (
              <li key={item.id}>
                <KnowledgeGlyph kind="assumption" />
                <span>{item.label}</span>
                <span className="tabular">
                  {item.value === null ? "—" : formatExact(item.value)} {item.unit}
                </span>
                <Badge tone={item.source === "default" ? "outline" : "neutral"}>
                  {item.source === "default" ? "Default" : "Yours"}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
      {link.statements.length > 0 && (
        <section className={styles.inspectorSection}>
          <h4>Stated assumptions</h4>
          <ul className={styles.statementList}>
            {link.statements.map((statement) => (
              <li key={statement.id}>
                <span className={styles.equationId}>{statement.id}</span> {statement.text}
              </li>
            ))}
          </ul>
        </section>
      )}
      {link.kind === "cited" && caution && (
        <p className={styles.caution}>
          A connection in the graph is not evidence of causation. This relationship decided that the
          model applies; no value travels along it.
        </p>
      )}
    </div>
  );
}

function Sparkline({ values }: { values: string[] }) {
  const numbers = values.map(Number);
  const low = Math.min(0, ...numbers);
  const high = Math.max(0, ...numbers);
  const span = high - low || 1;
  const width = 220;
  const height = 44;
  const step = width / Math.max(1, numbers.length);
  const zero = height - ((0 - low) / span) * height;
  return (
    <svg className={styles.sparkline} width={width} height={height} aria-hidden="true">
      <line x1={0} x2={width} y1={zero} y2={zero} className={styles.sparkZero} />
      {numbers.map((value, index) => {
        const y = height - ((value - low) / span) * height;
        return (
          <rect
            // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
            key={index}
            x={index * step + step * 0.2}
            width={Math.max(1, step * 0.6)}
            y={Math.min(y, zero)}
            height={Math.max(1, Math.abs(zero - y))}
            className={styles.sparkBar}
          />
        );
      })}
    </svg>
  );
}

function NodeDetails({
  node,
  lane,
  incoming,
  outgoing,
  names,
  onSelectLink,
}: {
  node: LabPathwayNode;
  lane: Lane | undefined;
  incoming: PlacedLink[];
  outgoing: PlacedLink[];
  names: Names;
  onSelectLink: (id: string) => void;
}) {
  const kind = knowledgeKind(node);
  return (
    <div className={styles.inspectorBody}>
      <p className={styles.inspectorTitle}>{node.label}</p>
      <dl className={styles.facts}>
        <div>
          <dt>What it is</dt>
          <dd>{KIND_LABEL[node.kind]}</dd>
        </div>
        {lane && (
          <div>
            <dt>Model</dt>
            <dd>
              {lane.title} <span className="mono">v{lane.version}</span>
            </dd>
          </div>
        )}
        {node.value !== null && (
          <div>
            <dt>{node.kind === "change" ? "Change" : "Value"}</dt>
            <dd className="tabular">
              {nodeValue(node.value, node.unit)}
              {node.detail && <span className={styles.factNote}>{node.detail}</span>}
            </dd>
          </div>
        )}
        {kind && (
          <div>
            <dt>Knowledge</dt>
            <dd>
              <KnowledgeGlyph kind={kind} />{" "}
              {kind === "simulated"
                ? "Simulated — a result of stated assumptions"
                : "Your scenario change"}
            </dd>
          </div>
        )}
        {node.first_month !== null && node.kind !== "change" && (
          <div>
            <dt>First moves in</dt>
            <dd>Month {node.first_month}</dd>
          </div>
        )}
      </dl>
      {node.monthly && node.kind !== "change" && (
        <section className={styles.inspectorSection}>
          <h4>By simulated month</h4>
          <Sparkline values={node.monthly} />
        </section>
      )}
      {[
        ["Comes from", incoming, "source"],
        ["Leads to", outgoing, "target"],
      ].map(([title, list, end]) =>
        (list as PlacedLink[]).length ? (
          <section key={title as string} className={styles.inspectorSection}>
            <h4>{title as string}</h4>
            <ul className={styles.linkList}>
              {(list as PlacedLink[]).map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => onSelectLink(item.id)}>
                    {names.describe(item[end as "source" | "target"])}
                    <span className={styles.linkKind}>
                      {LINK_LABEL[item.links[0]?.kind ?? "equation"]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </div>
  );
}

export function PathwayCanvas({
  pathway,
  month,
  currency,
}: {
  pathway: LabPathway;
  /** The simulated month being replayed, or null for totals over the horizon. */
  month: number | null;
  currency: string;
}) {
  // The scroll container, not the frame: the frame's minimum width comes from the layout.
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 960, height: 0 });
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [selection, setSelection] = useState<Selection>(null);
  const [view, setView] = useState<"diagram" | "list">("diagram");
  const [showUnmodelled, setShowUnmodelled] = useState(false);

  const layout = useMemo(
    () => layoutPathway(pathway, { width: Math.max(560, width), collapsed }),
    [pathway, width, collapsed],
  );
  const names = useMemo<Names>(() => {
    const nodes = new Map(pathway.nodes.map((node) => [node.id, node]));
    const groups = new Map(pathway.groups.map((group) => [group.id, group.title]));
    const label = (id: string) =>
      id.startsWith("group:") ? (groups.get(id.slice(6)) ?? id) : (nodes.get(id)?.label ?? id);
    const describe = (id: string) => {
      const node = nodes.get(id);
      if (!node) return label(id);
      if (node.kind === "change") return `${node.label} · your change`;
      const group = node.group ? groups.get(node.group) : undefined;
      return group ? `${node.label} · ${group}` : node.label;
    };
    return { label, describe };
  }, [pathway]);
  /** The graph entities a lane cites (an industry, the company), for its header. */
  const contextNames = useMemo(() => {
    const kinds = new Map(pathway.nodes.map((node) => [node.id, node.kind]));
    return (lane: Lane): string[] => {
      const found: string[] = [];
      for (const link of lane.context) {
        for (const end of [link.source, link.target]) {
          const name = names.label(end);
          if (kinds.get(end) === "context" && !found.includes(name)) found.push(name);
        }
      }
      return found;
    };
  }, [pathway, names]);
  const linkById = useMemo(() => new Map(layout.links.map((link) => [link.id, link])), [layout]);
  const nodeById = useMemo(() => new Map(layout.nodes.map((node) => [node.id, node])), [layout]);
  const laneById = useMemo(() => new Map(layout.lanes.map((lane) => [lane.id, lane])), [layout]);
  /** The relationship each variable was propagated along, shown on the variable. */
  const propagated = useMemo(() => {
    const map = new Map<string, LabPathwayLink>();
    for (const link of pathway.links) {
      if (link.kind === "transmission" && !map.has(link.target)) map.set(link.target, link);
    }
    return map;
  }, [pathway]);

  const selectedId = selection?.id ?? null;
  const chain = useMemo(() => {
    if (!selection || selection.kind === "context") return null;
    if (selection.kind === "node") return chainOf(layout, selection.id);
    const link = linkById.get(selection.id);
    if (!link) return null;
    const up = chainOf(layout, link.source, ["up"]);
    const down = chainOf(layout, link.target, ["down"]);
    return {
      nodes: new Set([...up.nodes, ...down.nodes]),
      links: new Set([...up.links, ...down.links, link.id]),
    };
  }, [selection, layout, linkById]);

  const toggleLane = (id: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectedLink = selection?.kind === "link" ? linkById.get(selection.id) : undefined;
  const selectedNode = selection?.kind === "node" ? nodeById.get(selection.id) : undefined;
  const selectedLane = selection?.kind === "context" ? laneById.get(selection.id) : undefined;

  // Escape closes the details wherever focus is: choosing a link inside the details
  // replaces their content, so focus moves to the details panel itself.
  const inspectorRef = useRef<HTMLElement>(null);
  const open = selection !== null;
  useEffect(() => {
    if (!open) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setSelection(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const selectFromDetails = (id: string) => {
    setSelection({ kind: "link", id });
    window.requestAnimationFrame(() => inspectorRef.current?.focus());
  };

  const linkReached = (link: PlacedLink) => {
    const target = nodeById.get(link.target);
    return target ? reached(target, month) : true;
  };

  return (
    <div className={styles.pathway}>
      <div className={styles.pathwayToolbar}>
        <PathwayLegend />
        <fieldset className={styles.segmented}>
          <legend className="visually-hidden">Pathway view</legend>
          <button
            type="button"
            aria-pressed={view === "diagram"}
            onClick={() => setView("diagram")}
          >
            Diagram
          </button>
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
            List
          </button>
        </fieldset>
      </div>

      {view === "diagram" ? (
        <div ref={frameRef} className={styles.pathwayScroll}>
          <div
            className={styles.pathwayFrame}
            style={{ height: layout.height, minWidth: layout.width }}
            data-replaying={month !== null ? "true" : undefined}
          >
            <svg
              className={styles.pathwaySvg}
              width={layout.width}
              height={layout.height}
              aria-hidden="true"
            >
              {layout.columns.map((column) => (
                <text key={column.id} x={column.x} y={16} className={styles.columnLabel}>
                  {column.label.toUpperCase()}
                  {(column.id === "driver" || column.id === "outcome") && currency
                    ? ` · ${currency}`
                    : ""}
                </text>
              ))}
              {layout.headings.map((heading) => (
                <text key={heading.text} x={heading.x} y={heading.y} className={styles.columnLabel}>
                  {heading.text.toUpperCase()}
                </text>
              ))}
              {layout.lanes.map((lane) => (
                <rect
                  key={lane.id}
                  x={lane.x}
                  y={lane.y}
                  width={lane.width}
                  height={lane.height}
                  rx={6}
                  className={styles.lane}
                />
              ))}
              {layout.links.map((link) => {
                const first = link.links[0];
                if (!first) return null;
                const dimmed = (chain !== null && !chain.links.has(link.id)) || !linkReached(link);
                const target = nodeById.get(link.target);
                return (
                  <g key={link.id} data-dimmed={dimmed ? "true" : undefined}>
                    <path
                      d={link.path}
                      className={styles.link}
                      data-kind={first.kind}
                      data-active={first.active ? undefined : "false"}
                      data-selected={selectedId === link.id ? "true" : undefined}
                    />
                    {first.kind === "aggregation" && first.sign === -1 && target && (
                      <text
                        x={link.arc ? link.mid.x + 7 : target.x - 10}
                        y={link.arc ? link.mid.y + 4 : target.y + NODE_HEIGHT / 2 + 4}
                        className={styles.linkSign}
                      >
                        −
                      </text>
                    )}
                  </g>
                );
              })}
              {layout.links.map((link) => (
                // biome-ignore lint/a11y/noStaticElementInteractions: pointer convenience; every link is listed, operable, in a step's details and in the List view.
                <path
                  key={`hit-${link.id}`}
                  d={link.path}
                  className={styles.linkHit}
                  onClick={() => setSelection({ kind: "link", id: link.id })}
                />
              ))}
            </svg>

            {layout.lanes.map((lane) => (
              <div
                key={lane.id}
                className={styles.laneHeader}
                style={{ left: lane.x + 10, top: lane.y + 5, width: lane.width - 20 }}
              >
                <button
                  type="button"
                  className={styles.laneLabel}
                  aria-expanded={!lane.collapsed}
                  onClick={() => toggleLane(lane.id)}
                >
                  <Icon name={lane.collapsed ? "chevronRight" : "chevronDown"} size={12} />
                  <span className={styles.laneTitle}>{lane.title}</span>
                  <span className={styles.laneVersion}>v{lane.version}</span>
                </button>
                {lane.context.length > 0 && (
                  <button
                    type="button"
                    className={styles.laneContext}
                    aria-pressed={selection?.kind === "context" && selection.id === lane.id}
                    title={lane.context.map((link) => statement(link, names)).join("\n")}
                    onClick={() =>
                      setSelection((previous) =>
                        previous?.kind === "context" && previous.id === lane.id
                          ? null
                          : { kind: "context", id: lane.id },
                      )
                    }
                  >
                    <span className={styles.laneContextLead}>Why it applies</span>
                    {contextNames(lane).join(" · ")}
                  </button>
                )}
              </div>
            ))}

            {layout.nodes.map((placed) => {
              const node = placed.node;
              const isReached = reached(placed, month);
              const dimmed = (chain && !chain.nodes.has(placed.id)) || !isReached;
              if (!node) {
                const group = pathway.groups.find((item) => item.id === placed.group);
                return (
                  <button
                    key={placed.id}
                    type="button"
                    className={cx(styles.node, styles.groupNode)}
                    style={{
                      left: placed.x,
                      top: placed.y,
                      width: placed.width,
                      height: NODE_HEIGHT,
                    }}
                    data-dimmed={dimmed ? "true" : undefined}
                    onClick={() => placed.group && toggleLane(placed.group)}
                  >
                    <span className={styles.nodeLabel}>{group?.title ?? placed.group}</span>
                    <span className={styles.nodeMeta}>
                      {group ? `${group.nodes.length} steps collapsed · expand` : "expand"}
                    </span>
                  </button>
                );
              }
              const kind = knowledgeKind(node);
              const value = valueAt(node, month);
              const via = propagated.get(node.id);
              return (
                <button
                  key={placed.id}
                  type="button"
                  className={styles.node}
                  data-kind={node.kind}
                  data-dimmed={dimmed ? "true" : undefined}
                  data-selected={selectedId === placed.id ? "true" : undefined}
                  style={{
                    left: placed.x,
                    top: placed.y,
                    width: placed.width,
                    height: NODE_HEIGHT,
                  }}
                  aria-pressed={selectedId === placed.id}
                  title={names.describe(node.id)}
                  onClick={() =>
                    setSelection((previous) =>
                      previous?.kind === "node" && previous.id === placed.id
                        ? null
                        : { kind: "node", id: placed.id },
                    )
                  }
                >
                  <span className={styles.nodeLabel}>
                    {kind && <KnowledgeGlyph kind={kind} size={10} />}
                    <span className={styles.nodeLabelText}>{node.label}</span>
                  </span>
                  <span className={styles.nodeValueRow}>
                    {value === null && month !== null ? (
                      <span className={styles.nodeMeta}>Horizon only</span>
                    ) : (
                      <span className={styles.nodeValue}>{nodeValue(value, node.unit)}</span>
                    )}
                    {via && <span className={styles.nodeChip}>{transmissionChip(via)}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <PathwayList pathway={pathway} names={names} />
      )}

      {(selectedLink || selectedNode || selectedLane) && (
        <aside
          ref={inspectorRef}
          className={styles.inspector}
          aria-label="Pathway details"
          tabIndex={-1}
        >
          <div className={styles.inspectorHeader}>
            <p className="eyebrow">
              {selectedLink ? "Relationship" : selectedLane ? "Why this model applies" : "Step"}
            </p>
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setSelection(null)}
              aria-label="Close the details"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
          {selectedLink?.links.map((link) => (
            <LinkDetails key={link.id} link={link} names={names} />
          ))}
          {selectedNode?.node && (
            <NodeDetails
              node={selectedNode.node}
              lane={selectedNode.group ? laneById.get(selectedNode.group) : undefined}
              incoming={layout.links.filter((link) => link.target === selectedNode.id)}
              outgoing={layout.links.filter((link) => link.source === selectedNode.id)}
              names={names}
              onSelectLink={selectFromDetails}
            />
          )}
          {selectedLane && (
            <>
              <p className={styles.caution}>
                {selectedLane.title} was included because the knowledge graph states the
                relationships below. They decided that the model applies and carry no value: nothing
                is computed along them, and a connection in the graph is not evidence of causation.
              </p>
              {selectedLane.context.map((link) => (
                <LinkDetails key={link.id} link={link} names={names} caution={false} />
              ))}
            </>
          )}
        </aside>
      )}

      <section className={styles.unmodelled}>
        <button
          type="button"
          className={styles.disclosure}
          aria-expanded={showUnmodelled}
          onClick={() => setShowUnmodelled((value) => !value)}
        >
          <Icon name={showUnmodelled ? "chevronDown" : "chevronRight"} size={12} />
          Stated in the graph, not modelled ({pathway.unmodelled.length})
        </button>
        {showUnmodelled && (
          <>
            <p className={styles.caption}>
              The knowledge graph states these relationships from the changed variables. No included
              model simulates them, so nothing is computed along them — a connection is not evidence
              of causation.
            </p>
            <ul className={styles.unmodelledList}>
              {pathway.unmodelled.map((edge) => (
                <li key={edge.edge_key}>
                  <span>{edge.source_name}</span>
                  <span className={styles.relationship}>{edge.relationship}</span>
                  <span>{edge.target_name}</span>
                  <Badge tone="outline">
                    {EVIDENCE_LABEL[edge.evidence_status] ?? edge.evidence_status}
                  </Badge>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

export function PathwayLegend() {
  const items: [LabPathwayLink["kind"], string][] = [
    ["applies", "Your change"],
    ["transmission", "Graph relationship, propagated"],
    ["equation", "Model equation"],
    ["aggregation", "Added by the Lab"],
  ];
  return (
    <ul className={styles.legend} aria-label="Link types">
      {items.map(([kind, label]) => (
        <li key={kind}>
          <svg width="26" height="8" aria-hidden="true">
            <path d="M1 4H25" className={styles.link} data-kind={kind} />
          </svg>
          {label}
        </li>
      ))}
    </ul>
  );
}

function PathwayList({ pathway, names }: { pathway: LabPathway; names: Names }) {
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <caption className="visually-hidden">Every link of the pathway</caption>
        <thead>
          <tr>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Type</th>
            <th scope="col">Used for simulation</th>
            <th scope="col">Evidence</th>
            <th scope="col">Parameters</th>
          </tr>
        </thead>
        <tbody>
          {pathway.links.map((link) => (
            <tr key={link.id}>
              <td>{names.describe(link.source)}</td>
              <td>{names.describe(link.target)}</td>
              <td>{link.kind === "cited" ? `Cited: ${link.label}` : LINK_LABEL[link.kind]}</td>
              <td>{SIMULATION_LABEL[link.simulation]}</td>
              <td>
                {link.edge
                  ? (EVIDENCE_LABEL[link.edge.evidence_status] ?? link.edge.evidence_status)
                  : "—"}
              </td>
              <td className="tabular">
                {[
                  link.coefficient !== null ? `β ${formatExact(link.coefficient)}` : "",
                  link.lag_months !== null ? `lag ${link.lag_months} months` : "",
                  link.equations.map((equation) => equation.id).join(", "),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
