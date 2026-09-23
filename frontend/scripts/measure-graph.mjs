/**
 * Times the Graph Explorer's pure work per view change — merging server answers into a
 * view (buildView) and laying it out (radialLayout) — on SYNTHETIC views of increasing
 * size. It loads the real modules through Vite, so nothing extra is installed.
 *
 *   node scripts/measure-graph.mjs
 *
 * The numbers describe the machine they ran on (see docs/graph/performance.md).
 */
import { performance } from "node:perf_hooks";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
  logLevel: "error",
});
const { buildView } = await server.ssrLoadModule("/src/features/graph/view.ts");
const { radialLayout } = await server.ssrLoadModule("/src/features/graph/layout.ts");

/** A synthetic neighbourhood: `n` nodes around a centre, about 2.5 edges per node. */
function neighbourhood(n) {
  const node = (index, depth) => ({
    id: `company:syn_${index}`,
    type: "company",
    name: `Synthetic Company ${index}`,
    subtitle: "Synthetic",
    nature: "fictional",
    quality_status: "validated",
    degree: 3,
    primary_identifier: null,
    data_status: "not_applicable",
    depth,
  });
  const edge = (source, target) => ({
    id: `e-${source}-${target}`,
    type: "supplies_to",
    category: "economic",
    source: `company:syn_${source}`,
    target: `company:syn_${target}`,
    directed: true,
    label: "supplies",
    description: "",
    evidence_status: "model_assumption",
    is_illustrative: true,
    quality_status: "validated",
    valid_from: null,
    valid_to: null,
    historical: false,
    qualifiers: {},
  });
  const nodes = [node(0, 0)];
  const edges = [];
  for (let index = 1; index < n; index += 1) {
    nodes.push(node(index, index < 12 ? 1 : 2));
    edges.push(edge(index < 12 ? 0 : (index % 11) + 1, index));
    edges.push(edge(index, (index * 7) % n || 1));
    if (index % 2) edges.push(edge((index * 13) % n || 2, index));
  }
  return {
    center: nodes[0],
    depth: 2,
    nodes,
    edges,
    truncated: false,
    unexplored_count: 0,
    unexplored_by_type: {},
    limits: { max_depth: 3, max_nodes: n },
    queries: 3,
  };
}

function median(action, runs = 200) {
  for (let i = 0; i < 20; i += 1) action();
  const samples = [];
  for (let i = 0; i < runs; i += 1) {
    const start = performance.now();
    action();
    samples.push(performance.now() - start);
  }
  samples.sort((a, b) => a - b);
  return samples[Math.floor(samples.length / 2)];
}

console.log("| View size | Edges | buildView (ms) | radialLayout (ms) |");
console.log("|---|---|---|---|");
for (const size of [50, 100, 150, 200, 1000]) {
  const answer = neighbourhood(size);
  const view = buildView(answer, [], size);
  const merge = median(() => buildView(answer, [], size));
  const layout = median(() => radialLayout(view));
  console.log(`| ${size} | ${answer.edges.length} | ${merge.toFixed(3)} | ${layout.toFixed(3)} |`);
}
await server.close();
