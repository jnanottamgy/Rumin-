/**
 * Times the 3D universe's pure work — the layout (first, and an expansion of 10 % more
 * nodes), the scene model and the placement of names — on SYNTHETIC graphs of increasing
 * size: random nodes of every kind and random edges, with no financial meaning. It loads the
 * real modules through Vite, so nothing extra is installed; rendering is measured in a
 * browser instead (docs/universe/performance.md).
 *
 *   node scripts/measure-universe.mjs
 *
 * The numbers describe the machine they ran on.
 */
import { performance } from "node:perf_hooks";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
  logLevel: "error",
});
const { layout3d } = await server.ssrLoadModule("/src/features/universe/layout3d.ts");
const { buildScene, labelPriority } = await server.ssrLoadModule("/src/features/universe/scene.ts");
const { placeLabels } = await server.ssrLoadModule("/src/features/universe/labels.ts");
const { applyFilters, universeView } = await server.ssrLoadModule(
  "/src/features/universe/universeView.ts",
);
const { DEFAULT_FILTERS } = await server.ssrLoadModule("/src/features/graph/useGraphExplorer.ts");

const KINDS = [
  ["company", 0.3],
  ["industry", 0.12],
  ["sector", 0.05],
  ["country", 0.05],
  ["currency", 0.04],
  ["economic_variable", 0.14],
  ["data_series", 0.3],
];
const STATUSES = ["evidence_backed", "analyst_created", "model_assumption", "unverified"];

function random(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** SYNTHETIC: `n` nodes of every kind and `m` random edges. */
function synthetic(n, m) {
  const next = random(n * 31 + m);
  const nodes = [];
  for (let i = 0; i < n; i += 1) {
    let r = next();
    let type = KINDS[0][0];
    for (const [kind, share] of KINDS) {
      if (r < share) {
        type = kind;
        break;
      }
      r -= share;
    }
    nodes.push({
      id: `${type}:syn_${i}`,
      type,
      name: `SYNTHETIC ${type} ${i}`,
      subtitle: "Synthetic",
      nature: next() < 0.3 ? "fictional" : "real",
      quality_status: "validated",
      degree: 0,
      primary_identifier: null,
      data_status: type === "data_series" ? "definition_only" : "not_applicable",
    });
  }
  const edges = [];
  for (let j = 0; j < m; j += 1) {
    const a = Math.floor(next() * n);
    const b = (a + 1 + Math.floor(next() * (n - 1))) % n;
    edges.push({
      id: `e-syn-${j}`,
      type: "affects_costs",
      category: next() < 0.6 ? "economic" : "structural",
      source: nodes[a].id,
      target: nodes[b].id,
      directed: true,
      label: "affects",
      description: "",
      evidence_status: STATUSES[Math.floor(next() * 4)],
      is_illustrative: true,
      quality_status: "validated",
      valid_from: null,
      valid_to: null,
      historical: false,
      qualifiers: {},
    });
    nodes[a].degree += 1;
    nodes[b].degree += 1;
  }
  return { nodes, edges };
}

const layoutInput = (nodes, edges) => [
  nodes.map((node) => ({ id: node.id, type: node.type })),
  edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    category: edge.category,
  })),
];

function time(run, repeat) {
  const samples = [];
  let result;
  for (let i = 0; i < repeat; i += 1) {
    const start = performance.now();
    result = run();
    samples.push(performance.now() - start);
  }
  samples.sort((a, b) => a - b);
  return { ms: samples[Math.floor(samples.length / 2)], result };
}

const rows = [];
for (const [n, m, repeat] of [
  [50, 100, 9],
  [500, 2500, 5],
  [2000, 8000, 3],
]) {
  const { nodes, edges } = synthetic(n, m);
  const first = time(() => layout3d(...layoutInput(nodes, edges), {}), repeat);
  const layout = first.result;
  // An expansion: 10 % new nodes, each linked to an existing one, the rest kept in place.
  const added = Array.from({ length: Math.round(n * 0.1) }, (_, i) => ({
    id: `company:syn_new_${i}`,
    type: "company",
  }));
  const links = added.map((node, i) => ({
    id: `e-new-${i}`,
    source: nodes[i % n].id,
    target: node.id,
    category: "structural",
  }));
  const [baseNodes, baseEdges] = layoutInput(nodes, edges);
  const grow = time(
    () =>
      layout3d([...baseNodes, ...added], [...baseEdges, ...links], {
        previous: layout.positions,
        anchors: new Map(links.map((link) => [link.target, link.source])),
      }),
    repeat,
  );
  const scene = time(
    () =>
      buildScene({
        nodes,
        edges,
        positions: layout.positions,
        focus: null,
        selection: { kind: "node", id: nodes[0].id },
        hover: null,
        overlay: null,
      }),
    repeat,
  );
  // Names, on a plain top view scaled into a 1,000 × 640 canvas.
  const xs = [...layout.positions.values()].map((p) => p.x);
  const zs = [...layout.positions.values()].map((p) => p.z);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs), 1);
  const scale = 600 / span;
  const project = (p) => ({
    x: 500 + (p.x - (Math.max(...xs) + Math.min(...xs)) / 2) * scale,
    y: 320 + (p.z - (Math.max(...zs) + Math.min(...zs)) / 2) * scale,
  });
  const projected = scene.result.nodes.map((node) => ({
    node,
    point: project(node.position),
    r: node.size * scale * 1.2,
  }));
  const labels = time(
    () =>
      placeLabels(
        projected.map(({ node, point, r }) => ({
          id: node.id,
          text: node.name,
          x: point.x,
          y: point.y,
          visible: true,
          priority: labelPriority(node, node.degree ?? 0, null, new Set()),
          depth: 0,
          radius: r,
        })),
        1000,
        640,
        {
          obstacles: projected.map(({ node, point, r }) => ({
            id: node.id,
            x: point.x,
            y: point.y,
            r,
          })),
          essential: 800,
        },
      ),
    repeat,
  );
  // A filter change in Universe mode: filter the whole build and derive the view again.
  const filter = time(() => {
    const kept = applyFilters(nodes, edges, { ...DEFAULT_FILTERS, includeIllustrative: false });
    return universeView(kept.nodes, kept.edges, null);
  }, repeat);
  rows.push({
    graph: `${n} nodes / ${m} edges`,
    "first layout (ms)": first.ms.toFixed(0),
    "expansion +10 % (ms)": grow.ms.toFixed(0),
    "scene (ms)": scene.ms.toFixed(1),
    "filter (ms)": filter.ms.toFixed(1),
    "names (ms)": labels.ms.toFixed(1),
    "names placed": labels.result.length,
  });
}
console.table(rows);
await server.close();
