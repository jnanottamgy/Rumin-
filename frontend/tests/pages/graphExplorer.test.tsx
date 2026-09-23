/**
 * The Knowledge Graph explorer, rendered through the real route table against a fake API
 * that answers with fixtures captured from a running backend.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { GraphNeighborhood } from "@/types/api";
import {
  AERISCA,
  AIR_TRANSPORT,
  BRENT,
  DELTRIN,
  graphFixtures,
  graphPath,
  USD_INR_EDGE,
} from "../fixtures/graph";
import { errorReply, mockApi, type RecordedRequest, type Route } from "../utils/api";
import { matchingMediaQueries } from "../utils/browser";
import { renderRoute } from "../utils/render";

/** Every read the explorer makes, answered from the fixtures. */
function graphRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  return {
    [graphPath.overview]: { body: graphFixtures.overview() },
    [graphPath.types]: { body: graphFixtures.types() },
    [graphPath.nodes]: (request: RecordedRequest) => {
      const query = new URLSearchParams(request.query);
      if (query.get("q")) return { body: graphFixtures.searchAeri() };
      if (query.get("type") === "industry") return { body: graphFixtures.industries() };
      return { body: graphFixtures.mostConnected() };
    },
    [graphPath.neighborhood(DELTRIN)]: { body: graphFixtures.neighborhoodDeltrin() },
    [graphPath.neighborhood(AERISCA)]: { body: graphFixtures.neighborhoodAerisca() },
    [graphPath.node(DELTRIN)]: { body: graphFixtures.nodeDeltrin() },
    [graphPath.node(AERISCA)]: { body: graphFixtures.nodeAerisca() },
    [graphPath.edge(USD_INR_EDGE)]: { body: graphFixtures.edgeUsdInrDeltrin() },
    [graphPath.paths]: (request: RecordedRequest) => {
      const query = new URLSearchParams(request.query);
      return {
        body:
          query.get("max_depth") === "1"
            ? graphFixtures.pathsNone()
            : graphFixtures.pathsAeriscaBrent(),
      };
    },
    ...overrides,
  };
}

const drawnNodes = (root: HTMLElement) =>
  [...root.querySelectorAll<SVGGElement>("g[data-node-id]")].map((element) => ({
    id: element.dataset.nodeId ?? "",
    state: element.dataset.state,
    nature: element.dataset.nature,
  }));

const drawnEdges = (root: HTMLElement) =>
  [...root.querySelectorAll<SVGPathElement>("path[data-edge-id]")].map((element) => ({
    id: element.dataset.edgeId ?? "",
    state: element.dataset.state,
    evidence: element.dataset.evidence,
  }));

const requestsTo = (requests: RecordedRequest[], path: string) =>
  requests.filter((request) => request.path === path);

const canvas = () => screen.findByRole("group", { name: /^Knowledge graph:/ });

async function openFocused(focus = DELTRIN) {
  const view = renderRoute(`/graph?focus=${encodeURIComponent(focus)}`);
  await canvas();
  await waitFor(() => expect(view.container.querySelector("g[data-node-id]")).not.toBeNull());
  return view;
}

describe("Knowledge Graph explorer", () => {
  it("opens on an aggregate type map, labelled as an aggregate, with the build report", async () => {
    const api = mockApi(graphRoutes());
    renderRoute("/graph");

    const map = await screen.findByRole("group", { name: /^Type map: an aggregate/ });
    expect(within(map).getByRole("button", { name: "Companies: 12. List them." })).toBeVisible();
    expect(within(map).getByRole("button", { name: "Data series: 11. List them." })).toBeVisible();
    expect(screen.getByText(/A band does not link every entity of one kind/)).toBeVisible();

    const summary = screen.getByRole("complementary", { name: "Graph summary" });
    const report = within(summary).getByRole("table");
    expect(within(report).getByRole("row", { name: /Nodes 50 50 0 0/ })).toBeVisible();
    expect(within(report).getByRole("row", { name: /Edges 97 97 0 0/ })).toBeVisible();
    expect(within(summary).getAllByText("What it means").length).toBe(6);
    expect(within(summary).getByText(/not how important it is/)).toBeVisible();
    expect(
      within(summary).getByText(/It is not a map of the complete economy/),
    ).toBeInTheDocument();

    // Nothing is traversed until the reader asks.
    expect(api.requests.some((request) => request.path.endsWith("/neighborhood"))).toBe(false);
    expect(api.writes()).toEqual([]);
  });

  it("lists a node type from the map and explores the node picked", async () => {
    const api = mockApi(graphRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/graph");

    await user.click(await screen.findByRole("button", { name: "Industries: 8. List them." }));
    const list = screen.getByRole("complementary", { name: "Graph summary" });
    expect(await within(list).findByText(/Choose one to explore/)).toBeVisible();
    const typeRequest = requestsTo(api.requests, graphPath.nodes).at(-1);
    expect(new URLSearchParams(typeRequest?.query)).toEqual(
      new URLSearchParams("type=industry&sort=-degree&limit=50"),
    );

    await user.click(within(list).getByRole("button", { name: /Refined petroleum products/ }));
    await waitFor(() =>
      expect(router.state.location.search).toBe("?focus=industry%3Aind_petroleum_refining"),
    );
  });

  it("searches the server and focuses the node picked", async () => {
    const api = mockApi(graphRoutes());
    const user = userEvent.setup();
    const { router, container } = renderRoute("/graph");

    const search = await screen.findByRole("combobox", { name: "Search the graph" });
    await user.type(search, "aeri");
    const option = await screen.findByRole("option", { name: /Aerisca Airways/ });
    expect(option).toHaveTextContent("Fictional company · Air transport · India");
    expect(option).toHaveTextContent("Company");
    const query = new URLSearchParams(requestsTo(api.requests, graphPath.nodes).at(-1)?.query);
    expect(query.get("q")).toBe("aeri");

    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(router.state.location.search).toBe(`?focus=${encodeURIComponent(AERISCA)}`),
    );
    await waitFor(() => expect(drawnNodes(container).length).toBe(7));
    const hood = new URLSearchParams(
      requestsTo(api.requests, graphPath.neighborhood(AERISCA)).at(-1)?.query,
    );
    expect(hood.get("depth")).toBe("1");
    expect(hood.get("max_nodes")).toBe("100");
  });

  it("flags names shared by more than one node and says when nothing matches", async () => {
    const ambiguous = graphFixtures.searchAeri();
    for (const item of ambiguous.items) item.ambiguous = true;
    mockApi(
      graphRoutes({
        [graphPath.nodes]: (request) =>
          new URLSearchParams(request.query).get("q") === "zzz"
            ? { body: { items: [], total: 0, limit: 12, offset: 0 } }
            : { body: ambiguous },
      }),
    );
    const user = userEvent.setup();
    renderRoute("/graph");

    const search = await screen.findByRole("combobox", { name: "Search the graph" });
    await user.type(search, "aeri");
    expect(await screen.findByText("Same name as another node — check the details")).toBeVisible();
    await user.clear(search);
    await user.type(search, "zzz");
    expect(await screen.findByText(/No node matches “zzz”/)).toBeVisible();
  });

  it("draws exactly the nodes and edges the API returns, with evidence and nature", async () => {
    mockApi(graphRoutes());
    const { container } = await openFocused();
    const answer = graphFixtures.neighborhoodDeltrin();

    const nodes = drawnNodes(container);
    expect(nodes.map((node) => node.id).sort()).toEqual(answer.nodes.map((n) => n.id).sort());
    for (const node of answer.nodes) {
      expect(nodes.find((item) => item.id === node.id)?.nature, node.id).toBe(node.nature);
    }
    const edges = drawnEdges(container);
    expect(edges.map((edge) => edge.id).sort()).toEqual(answer.edges.map((e) => e.id).sort());
    for (const edge of answer.edges) {
      expect(edges.find((item) => item.id === edge.id)?.evidence, edge.id).toBe(
        edge.evidence_status,
      );
    }
    expect(
      screen.getByText("9 nodes · 18 relationships within 1 hop of Deltrin Refining"),
    ).toBeVisible();
  });

  it("highlights a selected node's relationships, dims the rest, and shows its details", async () => {
    mockApi(graphRoutes());
    const user = userEvent.setup();
    const { container } = await openFocused();

    await user.click(screen.getByRole("button", { name: /^Aerisca Airways, company, fictional/ }));
    const answer = graphFixtures.neighborhoodDeltrin();
    const incident = answer.edges.filter(
      (edge) => edge.source === AERISCA || edge.target === AERISCA,
    );
    const neighbours = new Set(incident.flatMap((edge) => [edge.source, edge.target]));
    for (const node of drawnNodes(container)) {
      const expected =
        node.id === AERISCA ? "selected" : neighbours.has(node.id) ? "neighbor" : "dimmed";
      expect(node.state, node.id).toBe(expected);
    }
    const active = new Set(incident.map((edge) => edge.id));
    for (const edge of drawnEdges(container)) {
      expect(edge.state, edge.id).toBe(active.has(edge.id) ? "active" : "dimmed");
    }

    const panel = screen.getByRole("complementary", { name: "Selected node" });
    expect(
      await within(panel).findByRole("heading", { level: 2, name: "Aerisca Airways" }),
    ).toBeVisible();
    expect(within(panel).getByText("Fictional")).toBeVisible();

    await user.keyboard("{Escape}");
    expect(drawnNodes(container).every((node) => node.state === "default")).toBe(true);
  });

  it("labels assumed exposures as direct or via the industry, never as measured", async () => {
    mockApi(graphRoutes());
    await openFocused();
    const panel = screen.getByRole("complementary", { name: "Selected node" });

    const exposures = await within(panel).findByRole("region", { name: "Assumed exposures" });
    expect(within(exposures).getByText("Stated for it")).toBeVisible();
    expect(within(exposures).getByText("Stated for its industry")).toBeVisible();
    expect(within(exposures).getByText(/not measured exposures/)).toBeVisible();
    expect(
      within(exposures).getByText(/does not mean every company in it is affected/),
    ).toBeVisible();
    expect(within(panel).getByText(/data coverage, not importance/)).toBeVisible();
  });

  it("expands a neighbour on request, adding only new nodes, and can collapse it", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = mockApi(
      graphRoutes({
        [graphPath.neighborhood(AERISCA)]: async () => {
          await gate;
          return { body: graphFixtures.neighborhoodAerisca() };
        },
      }),
    );
    const user = userEvent.setup();
    const { container } = await openFocused();

    const aerisca = screen.getByRole("button", { name: /^Aerisca Airways, company/ });
    aerisca.focus();
    await user.keyboard("e");
    // While loading, the node says so and nothing is drawn twice.
    await waitFor(() => expect(aerisca).toHaveAttribute("aria-busy", "true"));
    expect(drawnNodes(container)).toHaveLength(9);

    await act(async () => release());
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(10));
    const ids = drawnNodes(container).map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain(AIR_TRANSPORT);
    const request = requestsTo(api.requests, graphPath.neighborhood(AERISCA)).at(-1);
    expect(new URLSearchParams(request?.query).get("max_nodes")).toBe("40");
    expect(screen.getByText(/plus 1 expanded node/)).toBeVisible();

    const panel = screen.getByRole("complementary", { name: "Selected node" });
    await user.click(await within(panel).findByRole("button", { name: "Hide its neighbours" }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(9));
  });

  it("reports a failed expansion and retries it", async () => {
    const api = mockApi(
      graphRoutes({
        [graphPath.neighborhood(AERISCA)]: errorReply(500, "internal_error", "Boom."),
      }),
    );
    const user = userEvent.setup();
    const { container } = await openFocused();

    fireEvent.doubleClick(screen.getByRole("button", { name: /^Aerisca Airways, company/ }));
    const alert = await screen.findByText(/An expansion could not be loaded/);
    expect(drawnNodes(container)).toHaveLength(9);

    api.setRoute(graphPath.neighborhood(AERISCA), { body: graphFixtures.neighborhoodAerisca() });
    await user.click(
      within(alert.closest("p") as HTMLElement).getByRole("button", { name: "Try again" }),
    );
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(10));
  });

  it("goes back and forward through earlier views, and resets", async () => {
    mockApi(graphRoutes());
    const user = userEvent.setup();
    const { container } = await openFocused();

    fireEvent.doubleClick(screen.getByRole("button", { name: /^Aerisca Airways, company/ }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(10));

    await user.click(screen.getByRole("button", { name: "Back to the previous view" }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(9));
    expect(drawnNodes(container).find((node) => node.id === DELTRIN)?.state).toBe("selected");

    await user.click(screen.getByRole("button", { name: "Forward to the next view" }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(10));
    expect(drawnNodes(container).find((node) => node.id === AERISCA)?.state).toBe("selected");

    await user.click(screen.getByRole("button", { name: "Reset view" }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(9));
  });

  it("sends filters to the API and redraws from its answer", async () => {
    const api = mockApi(
      graphRoutes({
        [graphPath.neighborhood(DELTRIN)]: (request) => ({
          body: new URLSearchParams(request.query).getAll("evidence_status").length
            ? graphFixtures.neighborhoodDeltrinRecorded()
            : graphFixtures.neighborhoodDeltrin(),
        }),
      }),
    );
    const user = userEvent.setup();
    const { container } = await openFocused();

    await user.click(screen.getByText("Evidence", { selector: "summary" }));
    await user.click(screen.getByRole("checkbox", { name: /Model assumption/ }));
    await user.click(screen.getByRole("checkbox", { name: /Unverified/ }));

    const recorded: GraphNeighborhood = graphFixtures.neighborhoodDeltrinRecorded();
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(recorded.nodes.length));
    const query = new URLSearchParams(
      requestsTo(api.requests, graphPath.neighborhood(DELTRIN)).at(-1)?.query,
    );
    expect(query.getAll("evidence_status").sort()).toEqual(["analyst_created", "evidence_backed"]);
    expect(drawnEdges(container).every((edge) => edge.evidence === "analyst_created")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() => expect(drawnNodes(container)).toHaveLength(9));
  });

  it("shows why a relationship exists: evidence, rule, status and what it does not mean", async () => {
    mockApi(graphRoutes());
    const user = userEvent.setup();
    await openFocused();

    const panel = screen.getByRole("complementary", { name: "Selected node" });
    const shown = await within(panel).findByRole("region", {
      name: "Relationships shown on the canvas",
    });
    await user.click(
      within(shown).getByRole("button", { name: /USD\/INR exchange rate affects costs of this/ }),
    );

    const edgePanel = await screen.findByRole("complementary", { name: "Selected relationship" });
    const detail = graphFixtures.edgeUsdInrDeltrin();
    expect(await within(edgePanel).findByText(detail.explanation)).toBeVisible();
    expect(within(edgePanel).getAllByText("Model assumption").length).toBeGreaterThan(0);
    expect(within(edgePanel).getByText("Illustrative — sample network")).toBeVisible();
    const evidence = within(edgePanel).getByRole("region", { name: "Evidence records" });
    const record = detail.evidence[0];
    expect(within(evidence).getByText(record?.statement ?? "")).toBeVisible();
    expect(within(evidence).getByText(record?.transformation ?? "")).toBeVisible();
    expect(
      within(evidence).getByText(/None — the record does not cite an outside source/),
    ).toBeVisible();
    expect(within(edgePanel).getByText(detail.caveat)).toBeVisible();
    expect(within(edgePanel).getByText(/No validity period is stated/)).toBeVisible();
    // Strength is ordinal and illustrative; the panel never presents it as measured.
    expect(within(edgePanel).getByText(/not measured/)).toBeVisible();
  });

  it("finds paths, with the caveat that a path is not a causal chain", async () => {
    const api = mockApi(graphRoutes());
    const { container } = renderRoute(
      `/graph?from=${encodeURIComponent(AERISCA)}&to=${encodeURIComponent(BRENT)}`,
    );

    const finder = await screen.findByRole("complementary", { name: "Path finder" });
    expect(await within(finder).findByText(/shortest paths of 3 hops between/)).toBeVisible();
    expect(
      within(finder).getByText(/not an influence, transmission or causal chain/),
    ).toBeVisible();
    const answer = graphFixtures.pathsAeriscaBrent();
    expect(within(finder).getAllByText(/^Path \d$/)).toHaveLength(answer.paths.length);
    const drawn = new Set(drawnNodes(container).map((node) => node.id));
    for (const path of answer.paths)
      for (const id of path.nodes) expect(drawn.has(id), id).toBe(true);
    const query = new URLSearchParams(requestsTo(api.requests, graphPath.paths).at(-1)?.query);
    expect(query.get("from")).toBe(AERISCA);
    expect(query.get("to")).toBe(BRENT);
    // Names replace keys once the answer arrives.
    expect(within(finder).getAllByText("Aerisca Airways").length).toBeGreaterThan(0);
  });

  it("says plainly when no path exists within the limit", async () => {
    mockApi(graphRoutes());
    const user = userEvent.setup();
    renderRoute(`/graph?from=${encodeURIComponent(AERISCA)}&to=${encodeURIComponent(BRENT)}`);
    const finder = await screen.findByRole("complementary", { name: "Path finder" });
    await within(finder).findByText(/shortest paths of 3 hops/);

    await user.selectOptions(within(finder).getByRole("combobox", { name: /Up to/ }), "1");
    await user.click(within(finder).getByRole("button", { name: "Find paths" }));
    const panel = await screen.findByRole("complementary", { name: "Path finder" });
    expect(await within(panel).findByText("No path found")).toBeVisible();
    expect(within(panel).getByText(/not that the two are unrelated in the world/)).toBeVisible();
  });

  it("offers a table with the same nodes and relationships as the canvas", async () => {
    mockApi(graphRoutes());
    const user = userEvent.setup();
    await openFocused();

    await user.click(screen.getByRole("button", { name: "Table" }));
    const answer = graphFixtures.neighborhoodDeltrin();
    const nodes = screen.getByRole("table", { name: /^Nodes shown/ });
    expect(within(nodes).getAllByRole("row")).toHaveLength(answer.nodes.length + 1);
    const edges = screen.getByRole("table", { name: /^Relationships shown/ });
    expect(within(edges).getAllByRole("row")).toHaveLength(answer.edges.length + 1);

    await user.click(within(nodes).getByRole("button", { name: "Aerisca Airways" }));
    expect(within(nodes).getByRole("button", { name: "Aerisca Airways" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await screen.findByRole("heading", { level: 2, name: "Aerisca Airways" })).toBeVisible();
  });

  it("explains how to build the graph when it has not been built", async () => {
    mockApi(graphRoutes({ [graphPath.overview]: { body: graphFixtures.overviewNotBuilt() } }));
    renderRoute("/graph");
    expect(await screen.findByText("The knowledge graph has not been built yet")).toBeVisible();
    expect(screen.getByText("python -m app.graph build")).toBeVisible();
    expect(screen.queryByRole("group", { name: /^Type map/ })).toBeNull();
  });

  it("warns when the graph is older than its sources", async () => {
    mockApi(graphRoutes({ [graphPath.overview]: { body: graphFixtures.overviewStale() } }));
    renderRoute("/graph");
    const title = await screen.findByText("The graph is older than its sources");
    const notice = title.closest("[role=note]") as HTMLElement;
    expect(within(notice).getByText(/The sources changed after build #1/)).toBeVisible();
    expect(within(notice).getByText("python -m app.graph build")).toBeVisible();
  });

  it("shows an error, with a retry, when the API cannot be reached", async () => {
    const api = mockApi(
      graphRoutes({ [graphPath.overview]: () => Promise.reject(new TypeError("Failed to fetch")) }),
    );
    const user = userEvent.setup();
    renderRoute("/graph");
    expect(await screen.findByText(/Could not reach the RUMIN API/)).toBeVisible();

    api.setRoute(graphPath.overview, { body: graphFixtures.overview() });
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("group", { name: /^Type map/ })).toBeVisible();
  });

  it("shows a clear error for a node that is not in the graph", async () => {
    mockApi(
      graphRoutes({
        [graphPath.neighborhood("company:co_gone")]: errorReply(
          404,
          "not_found",
          "No node 'company:co_gone' in the current graph.",
        ),
      }),
    );
    renderRoute("/graph?focus=company%3Aco_gone");
    expect(
      await screen.findByText("No node 'company:co_gone' in the current graph."),
    ).toBeVisible();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Back to the map" })).toBeVisible();
  });

  it("ignores a focus that is not a node key", async () => {
    const api = mockApi(graphRoutes());
    renderRoute("/graph?focus=%3Cscript%3E");
    expect(await screen.findByRole("group", { name: /^Type map/ })).toBeVisible();
    expect(api.requests.some((request) => request.path.includes("script"))).toBe(false);
  });

  it("labels only what is in focus on a phone", async () => {
    matchingMediaQueries.add("(max-width: 40rem)");
    mockApi(graphRoutes());
    const { container } = await openFocused();
    const labelled = [...container.querySelectorAll("g[data-node-id]")].filter((node) =>
      node.querySelector("text"),
    );
    expect(labelled.map((node) => (node as SVGGElement).dataset.nodeId)).toEqual([DELTRIN]);
  });
});
