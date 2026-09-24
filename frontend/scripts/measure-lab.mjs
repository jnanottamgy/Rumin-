/**
 * Times the Scenario Lab's pure work in the browser — laying out the impact pathway and
 * following a step's chain — on the pathway the backend computed for the reference
 * scenario (tests/fixtures/lab/pathway.json), and on a SYNTHETIC one with its three model
 * lanes repeated three times (nine lanes: more than the five models RUMIN registers). It
 * loads the real modules through Vite, so nothing extra is installed.
 *
 *   node scripts/measure-lab.mjs
 *
 * The numbers describe the machine they ran on (see docs/scenario-lab/performance.md).
 */
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
  logLevel: "error",
});
const { layoutPathway, chainOf } = await server.ssrLoadModule(
  "/src/features/scenarioLab/pathwayLayout.ts",
);
const reference = JSON.parse(
  readFileSync(new URL("../tests/fixtures/lab/pathway.json", import.meta.url), "utf8"),
);

/** The reference pathway with every model lane repeated `copies` times (renamed). */
function repeated(pathway, copies) {
  const rename = (id, copy) =>
    id.startsWith("line:") ||
    id.startsWith("metric:") ||
    id.startsWith("change:") ||
    !id.includes(":")
      ? id
      : `${id}#${copy}`;
  const nodes = [];
  const links = [];
  const groups = [];
  for (let copy = 0; copy < copies; copy += 1) {
    for (const node of pathway.nodes) {
      if (node.group === null && copy > 0) continue;
      nodes.push({
        ...node,
        id: node.group ? rename(node.id, copy) : node.id,
        group: node.group ? `${node.group}#${copy}` : null,
      });
    }
    for (const link of pathway.links) {
      if (!link.group && copy > 0) continue;
      const source = pathway.nodes.find((node) => node.id === link.source);
      const target = pathway.nodes.find((node) => node.id === link.target);
      links.push({
        ...link,
        id: `${link.id}#${copy}`,
        source: source?.group ? rename(link.source, copy) : link.source,
        target: target?.group ? rename(link.target, copy) : link.target,
        group: link.group ? `${link.group}#${copy}` : null,
      });
    }
    for (const group of pathway.groups) {
      groups.push({
        ...group,
        id: `${group.id}#${copy}`,
        title: `${group.title} ${copy + 1}`,
        nodes: group.nodes.map((id) => rename(id, copy)),
      });
    }
  }
  return { ...pathway, nodes, links, groups };
}

function median(action, runs = 200) {
  action();
  const times = [];
  for (let index = 0; index < runs; index += 1) {
    const start = performance.now();
    action();
    times.push(performance.now() - start);
  }
  times.sort((a, b) => a - b);
  return times[Math.floor(times.length / 2)];
}

console.log(
  "| Pathway | Nodes / links | Layout (ms) | Layout, one lane collapsed (ms) | Chain of a step (ms) |",
);
console.log("|---|---|---|---|---|");
for (const [label, pathway] of [
  ["Reference (3 models)", reference],
  ["SYNTHETIC (9 lanes)", repeated(reference, 3)],
]) {
  const layout = layoutPathway(pathway, { width: 900 });
  const step = layout.nodes.find((node) => node.node?.kind === "variable")?.id;
  const layoutMs = median(() => layoutPathway(pathway, { width: 900 }));
  const collapsedMs = median(() =>
    layoutPathway(pathway, { width: 900, collapsed: new Set([pathway.groups[0].id]) }),
  );
  const chainMs = median(() => chainOf(layout, step));
  console.log(
    `| ${label} | ${pathway.nodes.length} / ${pathway.links.length} | ${layoutMs.toFixed(3)} | ${collapsedMs.toFixed(3)} | ${chainMs.toFixed(3)} |`,
  );
}
await server.close();
