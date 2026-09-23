/**
 * What to put where, decided from a model's own definition — which outputs lead, which
 * monthly series are the scenario and its baseline — so the page needs no per-model code.
 * Selection only: every value shown is the API's.
 */
import type {
  SimulationModelDetail,
  SimulationMonthlySeries,
  SimulationOutput,
  SimulationPathwayEdge,
  SimulationPathwayNode,
  SimulationRun,
} from "@/types/api";

export interface Headline {
  hero: SimulationOutput | null;
  tiles: SimulationOutput[];
}

/** The bridge total (or the first headline output) leads; other headline outputs follow. */
export function headline(run: SimulationRun, model: SimulationModelDetail): Headline {
  const byId = new Map(run.outputs.map((output) => [output.id, output]));
  const heroId = model.bridge_total ?? model.headline_outputs[0] ?? null;
  const hero = heroId ? (byId.get(heroId) ?? null) : null;
  const tiles = model.headline_outputs
    .filter((id) => id !== heroId)
    .map((id) => byId.get(id))
    .filter((output): output is SimulationOutput => output !== undefined);
  return { hero, tiles };
}

export interface ComparisonRow {
  label: string;
  baseline: SimulationOutput;
  scenario: SimulationOutput;
  change: SimulationOutput | null;
}

/**
 * Baseline-and-scenario pairs the model reports as outputs: `baseline_x` beside
 * `scenario_x`, with `x_change` when the model states the difference itself.
 */
export function comparisons(run: SimulationRun): ComparisonRow[] {
  const byId = new Map(run.outputs.map((output) => [output.id, output]));
  const rows: ComparisonRow[] = [];
  for (const output of run.outputs) {
    if (!output.id.startsWith("baseline_")) continue;
    const name = output.id.slice("baseline_".length);
    const scenario = byId.get(`scenario_${name}`);
    if (!scenario) continue;
    const label = scenario.label.replace(/^Scenario /, "");
    rows.push({
      label: label.charAt(0).toUpperCase() + label.slice(1),
      baseline: output,
      scenario,
      change: byId.get(`${name}_change`) ?? null,
    });
  }
  return rows;
}

export interface MonthlyPlan {
  scenario: SimulationMonthlySeries;
  baseline: SimulationMonthlySeries;
  change: SimulationMonthlySeries;
}

/** The monthly `scenario_x` and `baseline_x` lines, and the bridge total as columns. */
export function monthlyPlan(run: SimulationRun, model: SimulationModelDetail): MonthlyPlan | null {
  const byId = new Map(run.monthly.map((series) => [series.id, series]));
  const scenario = run.monthly.find((series) => series.id.startsWith("scenario_"));
  const baseline = scenario
    ? byId.get(`baseline_${scenario.id.slice("scenario_".length)}`)
    : undefined;
  const change = model.bridge_total ? byId.get(model.bridge_total) : undefined;
  if (!scenario || !baseline || !change) return null;
  return {
    scenario: { ...scenario, label: "Scenario" },
    baseline: { ...baseline, label: "Baseline" },
    change,
  };
}

/** The pathway drawn from a model's definition, before any run (no values yet). */
export function definitionPathway(model: SimulationModelDetail): {
  nodes: SimulationPathwayNode[];
  links: SimulationPathwayEdge[];
} {
  const inputs = new Map(model.inputs.map((input) => [input.id, input]));
  const outputs = new Map(model.outputs.map((output) => [output.id, output]));
  const rules = new Map(model.transmission_rules.map((rule) => [rule.id, rule]));
  const variableNames = new Map<string, string>();
  for (const input of model.inputs) {
    if (input.variable && input.variable_name)
      variableNames.set(input.variable, input.variable_name);
  }
  for (const rule of model.transmission_rules) {
    if (rule.source_name) variableNames.set(rule.source, rule.source_name);
    if (rule.target_name) variableNames.set(rule.target, rule.target_name);
  }

  const nodes = new Map<string, SimulationPathwayNode>();
  const add = (end: string) => {
    if (nodes.has(end)) return;
    const [kind, name = ""] = end.startsWith("input:")
      ? ["input", end.slice(6)]
      : end.startsWith("output:")
        ? ["output", end.slice(7)]
        : ["variable", end];
    if (kind === "input") {
      const input = inputs.get(name);
      nodes.set(end, {
        id: end,
        kind: "input",
        label: input?.label ?? name,
        value: null,
        unit: input?.unit_label ?? null,
        knowledge:
          input?.category === "scenario_input"
            ? "scenario_input"
            : input?.category === "assumption"
              ? "assumption"
              : "user_input",
      });
    } else if (kind === "output") {
      const output = outputs.get(name);
      nodes.set(end, {
        id: end,
        kind: "output",
        label: output?.label ?? name,
        value: null,
        unit: null,
        knowledge: output?.kind === "simulated" ? "simulated_output" : "derived",
      });
    } else {
      nodes.set(end, {
        id: end,
        kind: "variable",
        label: variableNames.get(end) ?? end,
        value: null,
        unit: "relative change",
        knowledge: "derived",
      });
    }
  };
  const links: SimulationPathwayEdge[] = model.pathway.map((link) => {
    add(link.source);
    add(link.target);
    const rule = link.rule ? rules.get(link.rule) : undefined;
    return {
      source: link.source,
      target: link.target,
      label: link.label,
      equations: link.equations,
      rule: link.rule,
      edge: rule?.graph_edge ?? null,
      coefficient: null,
      lag_months: null,
    };
  });
  return { nodes: [...nodes.values()], links };
}
