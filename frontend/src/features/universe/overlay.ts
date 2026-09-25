/**
 * A stored scenario execution, laid over the knowledge graph.
 *
 * Only what the execution recorded is shown; nothing is inferred from the graph:
 *
 * - **Changed**: the variables the scenario changed, with the stated sizes (hypothetical
 *   inputs, from the execution's plan).
 * - **Simulated entity**: the company whose figures the models simulated.
 * - **Propagated**: relationships a model rule carried the change along, with the rule, its
 *   coefficient and lag (the pathway's `transmission` links).
 * - **Cited**: relationships that decided which models apply and carry no values (the
 *   pathway's `cited` links).
 * - **Not simulated**: relationships the graph states around the changed variables that no
 *   included model simulates (the pathway's `unmodelled` list, with the reason).
 * - **Results**: the simulated lines (baseline, change, percent change), from the stored
 *   results — under the scenario's changes and entered figures, not a forecast.
 *
 * A graph relationship is never treated as an impact: only the propagated ones carried a
 * value, and only because a model rule declared them.
 */
import { typeFromKey } from "@/features/graph/encoding";
import type { LabPathway, ScenarioExecution, ScenarioResults } from "@/types/api";

export type OverlayNodeRole = "changed" | "entity" | "modelled" | "context";
export type OverlayEdgeRole = "propagated" | "cited" | "unmodelled";

export interface OverlayModel {
  id: string;
  title: string;
  version: string;
}

export interface OverlayEdge {
  /** The graph edge key. */
  id: string;
  role: OverlayEdgeRole;
  /** Graph node keys of its ends (null when an end is not a graph node). */
  source: string | null;
  target: string | null;
  label: string;
  rule: string | null;
  coefficient: string | null;
  lagMonths: number | null;
  model: OverlayModel | null;
  reason: string | null;
  evidenceStatus: string | null;
}

export interface OverlayChange {
  key: string;
  variableId: string;
  name: string;
  changeType: string;
  value: string;
  unit: string;
  modelled: boolean;
}

export interface OverlayLine {
  id: string;
  label: string;
  baseline: string;
  scenario: string;
  change: string;
  percentChange: string | null;
}

export interface ScenarioOverlay {
  executionId: string;
  scenarioId: string;
  scenarioName: string;
  version: number;
  status: string;
  finishedAt: string | null;
  buildId: number | null;
  freshness: string | null;
  entity: { key: string; name: string; nature: string } | null;
  changes: OverlayChange[];
  models: OverlayModel[];
  nodes: Map<string, OverlayNodeRole>;
  edges: Map<string, OverlayEdge>;
  lines: OverlayLine[];
  currency: string | null;
  horizonMonths: number | null;
  note: string;
}

const NODE_RANK: Record<OverlayNodeRole, number> = {
  changed: 4,
  entity: 3,
  modelled: 2,
  context: 1,
};
const EDGE_RANK: Record<OverlayEdgeRole, number> = { propagated: 3, cited: 2, unmodelled: 1 };

/**
 * The graph node a pathway node stands for: a change or a model's variable is the variable's
 * node; context nodes are graph keys already. Model outputs, lines and metrics are not graph
 * nodes (null).
 */
export function graphKey(pathwayNodeId: string): string | null {
  let key: string | null = null;
  if (pathwayNodeId.startsWith("change:")) {
    key = `variable:${pathwayNodeId.slice("change:".length).toLowerCase()}`;
  } else if (pathwayNodeId.includes(":variable:")) {
    key = `variable:${pathwayNodeId.split(":variable:")[1]?.toLowerCase() ?? ""}`;
  } else {
    key = pathwayNodeId;
  }
  return typeFromKey(key) ? key : null;
}

interface PlanShape {
  graph?: { build_id?: number | null; freshness?: string | null } | null;
  entity?: { key?: string; name?: string; nature?: string } | null;
  changes?: Array<{
    variable_id: string;
    name: string;
    change_type: string;
    value: string;
    unit: string;
    modelled?: boolean;
  }>;
  models?: Array<{
    model_id: string;
    title?: string;
    name?: string;
    version: string;
    status?: string;
  }>;
}

export function buildOverlay(
  execution: ScenarioExecution,
  pathway: LabPathway,
  results: ScenarioResults | null,
): ScenarioOverlay {
  const plan = (execution.plan ?? {}) as PlanShape;
  const nodes = new Map<string, OverlayNodeRole>();
  const mark = (key: string | null, role: OverlayNodeRole) => {
    if (!key) return;
    const current = nodes.get(key);
    if (!current || NODE_RANK[role] > NODE_RANK[current]) nodes.set(key, role);
  };

  const changes: OverlayChange[] = (plan.changes ?? []).map((change) => ({
    key: `variable:${change.variable_id.toLowerCase()}`,
    variableId: change.variable_id,
    name: change.name,
    changeType: change.change_type,
    value: change.value,
    unit: change.unit,
    modelled: Boolean(change.modelled),
  }));
  for (const change of changes) mark(change.key, "changed");

  const entity =
    plan.entity?.key && typeFromKey(plan.entity.key)
      ? {
          key: plan.entity.key,
          name: plan.entity.name ?? plan.entity.key,
          nature: plan.entity.nature ?? "real",
        }
      : null;
  if (entity) mark(entity.key, "entity");

  const groupOf = new Map<string, OverlayModel>();
  for (const group of pathway.groups) {
    const model = { id: group.id, title: group.title, version: group.version };
    for (const node of group.nodes) groupOf.set(node, model);
  }
  for (const node of pathway.nodes) {
    if (node.kind === "variable") mark(graphKey(node.id), "modelled");
    else if (node.kind === "context") mark(graphKey(node.id), "context");
  }

  const edges = new Map<string, OverlayEdge>();
  const add = (edge: OverlayEdge) => {
    const current = edges.get(edge.id);
    if (!current || EDGE_RANK[edge.role] > EDGE_RANK[current.role]) edges.set(edge.id, edge);
  };
  for (const link of pathway.links) {
    if (!link.edge || (link.kind !== "transmission" && link.kind !== "cited")) continue;
    add({
      id: link.edge.edge_key,
      role: link.kind === "transmission" ? "propagated" : "cited",
      source: graphKey(link.source),
      target: graphKey(link.target),
      label: link.edge.relationship,
      rule: link.rule ?? null,
      coefficient: link.coefficient ?? null,
      lagMonths: link.lag_months ?? null,
      model: groupOf.get(link.source) ?? groupOf.get(link.target) ?? null,
      reason: null,
      evidenceStatus: link.edge.evidence_status,
    });
  }
  for (const item of pathway.unmodelled) {
    add({
      id: item.edge_key,
      role: "unmodelled",
      source: typeFromKey(item.source) ? item.source : null,
      target: typeFromKey(item.target) ? item.target : null,
      label: item.relationship,
      rule: null,
      coefficient: null,
      lagMonths: null,
      model: null,
      reason: item.reason,
      evidenceStatus: item.evidence_status,
    });
  }

  const models: OverlayModel[] = (plan.models ?? [])
    .filter((model) => (model.status ?? "included") === "included")
    .map((model) => ({
      id: model.model_id,
      title: model.title ?? model.name ?? model.model_id,
      version: model.version,
    }));

  return {
    executionId: execution.id,
    scenarioId: execution.scenario_id,
    scenarioName: execution.scenario_name,
    version: execution.version,
    status: execution.status,
    finishedAt: execution.finished_at ?? null,
    buildId: plan.graph?.build_id ?? null,
    freshness: plan.graph?.freshness ?? null,
    entity,
    changes,
    models,
    nodes,
    edges,
    lines: (results?.lines ?? []).map((line) => ({
      id: line.id,
      label: line.label,
      baseline: line.baseline,
      scenario: line.scenario,
      change: line.change,
      percentChange: line.percent_change ?? null,
    })),
    currency: results?.currency ?? null,
    horizonMonths: results?.horizon_months ?? null,
    note: pathway.note,
  };
}

/** Every graph node the overlay mentions: marked nodes and the ends of its edges. */
export function overlayNodeKeys(overlay: ScenarioOverlay): string[] {
  const keys = new Set(overlay.nodes.keys());
  for (const edge of overlay.edges.values()) {
    if (edge.source) keys.add(edge.source);
    if (edge.target) keys.add(edge.target);
  }
  return [...keys].sort();
}

export const NODE_ROLE_LABEL: Record<OverlayNodeRole, string> = {
  changed: "Changed in the scenario",
  entity: "Simulated entity",
  modelled: "A model's variable",
  context: "Context for the models",
};

export const EDGE_ROLE_LABEL: Record<OverlayEdgeRole, string> = {
  propagated: "Propagated by a model rule",
  cited: "Cited: decided which models apply; carries no values",
  unmodelled: "Stated in the graph; no included model simulates it",
};
