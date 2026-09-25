/**
 * The 3D universe, rendered through the real route table against a fake API that answers
 * with fixtures captured from a running backend (`backend/scripts/capture_universe_fixtures.py`).
 *
 * jsdom has no WebGL. Most tests replace the renderer module with a stand-in that records
 * what it was asked to draw and projects points with a plain top-down camera, so a node can
 * be clicked where it is; the fallback tests report no WebGL, or lose the context.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphOverview, ScenarioExecution } from "@/types/api";
import { graphPath } from "../fixtures/graph";
import { COMPANY, universeFixtures, VARIABLE } from "../fixtures/universe";
import { errorReply, mockApi, type RecordedRequest, type Route } from "../utils/api";
import { matchingMediaQueries } from "../utils/browser";
import { renderRoute } from "../utils/render";
import type { StandInRenderer } from "../utils/universe";

const stand = vi.hoisted(() => ({
  webgl: true,
  renderers: [] as StandInRenderer[],
}));

vi.mock("@/features/universe/webgl", () => ({ webglAvailable: () => stand.webgl }));
vi.mock("@/features/universe/renderer", async () => {
  const { StandInRenderer } = await import("../utils/universe");
  return {
    createRenderer: (canvas: HTMLCanvasElement, events: { onContextLost: () => void }) => {
      const renderer = new StandInRenderer(canvas, events);
      stand.renderers.push(renderer);
      return renderer;
    },
  };
});

const EXECUTION = universeFixtures.execution().id;
const executionPath = `/api/v1/scenario-executions/${EXECUTION}`;
const TRANSMISSION = universeFixtures.edgeTransmission().id;

/** Every read the universe makes, answered from the fixtures. */
function universeRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  return {
    [graphPath.overview]: { body: universeFixtures.overview() },
    [graphPath.types]: { body: universeFixtures.types() },
    [graphPath.nodes]: (request: RecordedRequest) => {
      const query = new URLSearchParams(request.query);
      const q = query.get("q")?.toLowerCase();
      const page = universeFixtures.nodes();
      if (!q) return { body: page };
      // The API's search, narrowed from the captured page by name (a test stand-in).
      const items = page.items
        .filter((node) => node.name.toLowerCase().includes(q))
        .map((node) => ({ ...node, match: "name" }));
      return { body: { ...page, items, total: items.length } };
    },
    "/api/v1/graph/edges": { body: universeFixtures.edges() },
    [graphPath.node(COMPANY)]: { body: universeFixtures.nodeCompany() },
    [graphPath.node(VARIABLE)]: { body: universeFixtures.nodeVariable() },
    [graphPath.neighborhood(COMPANY)]: { body: universeFixtures.neighborhoodCompany() },
    [graphPath.neighborhood(VARIABLE)]: { body: universeFixtures.neighborhoodVariable() },
    [graphPath.edge(TRANSMISSION)]: { body: universeFixtures.edgeTransmission() },
    [graphPath.paths]: { body: universeFixtures.paths() },
    "/api/v1/scenarios": { body: universeFixtures.scenarios() },
    [executionPath]: { body: universeFixtures.execution() },
    [`${executionPath}/pathways`]: { body: universeFixtures.pathways() },
    [`${executionPath}/results`]: { body: universeFixtures.results() },
    ...overrides,
  };
}

const renderer = () => {
  const last = stand.renderers.at(-1);
  if (!last) throw new Error("No renderer was created.");
  return last;
};

const application = () => screen.findByRole("application", { name: /^3D knowledge graph:/ });

async function drawnWith(count: number) {
  await application();
  await waitFor(() => expect(renderer().scene?.nodes.length).toBe(count));
  await waitFor(() => expect(renderer().frames).toBeGreaterThan(0));
  return renderer();
}

function click(canvas: Element, x: number, y: number) {
  fireEvent.pointerDown(canvas, { pointerId: 1, clientX: x, clientY: y, button: 0 });
  fireEvent.pointerUp(canvas, { pointerId: 1, clientX: x, clientY: y, button: 0 });
}

const canvasElement = () => document.querySelector("canvas") as HTMLCanvasElement;

beforeEach(() => {
  stand.webgl = true;
  stand.renderers.length = 0;
  matchingMediaQueries.add("(prefers-reduced-motion: reduce)");
});

describe("the 3D universe", () => {
  it("draws the whole build from the graph's own pages and says what it shows", async () => {
    const api = mockApi(universeRoutes());
    renderRoute("/universe/3d");

    const drawn = await drawnWith(50);
    expect(drawn.scene?.edges).toHaveLength(97);
    expect(
      await screen.findByText("50 nodes · 97 relationships: the whole build"),
    ).toBeInTheDocument();
    expect(await application()).toHaveAccessibleName(
      "3D knowledge graph: 50 nodes · 97 relationships: the whole build.",
    );
    const nodePages = api.requests.filter((request) => request.path === graphPath.nodes);
    expect(nodePages.map((request) => new URLSearchParams(request.query).toString())).toEqual([
      "limit=500&offset=0&sort=name",
    ]);
    const edgePages = api.requests.filter((request) => request.path === "/api/v1/graph/edges");
    expect(edgePages.map((request) => new URLSearchParams(request.query).toString())).toEqual([
      "limit=500&offset=0",
    ]);
    // Height says what a node is: every company is on the companies' stratum, below the
    // drivers.
    const company = drawn.node(COMPANY).position.y;
    const variable = drawn.node(VARIABLE).position.y;
    expect(variable).toBeGreaterThan(company);
    expect(screen.getByText("Build #1 · 50 nodes · 97 edges")).toBeInTheDocument();
    expect(screen.getByText("Not a map of the whole economy")).toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });

  it("inspects a node picked on the canvas, with where it comes from, and clears it", async () => {
    mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute("/universe/3d");
    const drawn = await drawnWith(50);

    const point = drawn.at(COMPANY);
    click(canvasElement(), point.x, point.y);
    const panel = await screen.findByRole("complementary", { name: "Selected node" });
    expect(
      await within(panel).findByRole("heading", { name: "Aerisca Airways" }),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("region", { name: "Where it comes from" })).toBeVisible();
    expect(within(panel).getByRole("link", { name: "Open in the 2D explorer" })).toHaveAttribute(
      "href",
      `/graph?focus=${encodeURIComponent(COMPANY)}`,
    );
    expect(
      within(panel).getByRole("link", { name: "Open in Financial Intelligence" }),
    ).toHaveAttribute("href", `/intelligence/${encodeURIComponent(COMPANY)}`);
    await waitFor(() => expect(drawn.node(COMPANY).selected).toBe(true));
    expect(screen.getByText(/^Selected: Aerisca Airways, company, fictional/)).toBeInTheDocument();

    // Escape, from the canvas, clears the selection.
    await user.click(await application());
    fireEvent.keyDown(await application(), { key: "Escape" });
    await waitFor(() =>
      expect(screen.getByRole("complementary", { name: "Details" })).toBeInTheDocument(),
    );
    expect(screen.getByText("Select a node or a line")).toBeInTheDocument();
  });

  it("moves the selection with the arrow keys and centres it with Enter", async () => {
    mockApi(universeRoutes());
    const { router } = renderRoute("/universe/3d");
    const drawn = await drawnWith(50);
    click(canvasElement(), drawn.at(COMPANY).x, drawn.at(COMPANY).y);
    await waitFor(() => expect(drawn.node(COMPANY).selected).toBe(true));

    const from = drawn.at(COMPANY);
    fireEvent.keyDown(await application(), { key: "ArrowUp" });
    await waitFor(() => expect(drawn.node(COMPANY).selected).toBe(false));
    const selected = drawn.scene?.nodes.find((node) => node.selected);
    expect(selected).toBeDefined();
    expect(drawn.at(selected?.id ?? "").y).toBeLessThan(from.y);

    // Enter brings it to the centre: in the whole universe, the camera moves to it.
    fireEvent.keyDown(await application(), { key: "Enter" });
    await waitFor(() =>
      expect(drawn.orbit?.target).toEqual(drawn.node(selected?.id ?? "").position),
    );
    // E opens its neighbourhood.
    fireEvent.keyDown(await application(), { key: "e" });
    await waitFor(() =>
      expect(router.state.location.search).toBe(`?focus=${encodeURIComponent(selected?.id ?? "")}`),
    );
  });

  it("keeps the canvas, and the keyboard focus, while the next view loads", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockApi(
      universeRoutes({
        [graphPath.neighborhood(COMPANY)]: async () => {
          await gate;
          return { body: universeFixtures.neighborhoodCompany() };
        },
      }),
    );
    renderRoute("/universe/3d");
    const drawn = await drawnWith(50);
    click(canvasElement(), drawn.at(COMPANY).x, drawn.at(COMPANY).y);
    await waitFor(() => expect(drawn.node(COMPANY).selected).toBe(true));
    const canvas = await application();
    canvas.focus();
    fireEvent.keyDown(canvas, { key: "e" });
    // The previous view stays on screen, and says the next one is loading.
    expect(
      await screen.findByText(/^Loading the next view; the previous one is shown/),
    ).toBeInTheDocument();
    expect(document.activeElement).toBe(canvas);
    expect(renderer().scene?.nodes).toHaveLength(50);
    release();
    const neighbourhood = universeFixtures.neighborhoodCompany();
    await waitFor(() => expect(renderer().scene?.nodes).toHaveLength(neighbourhood.nodes.length));
    expect(document.activeElement).toBe(canvas);
    expect(stand.renderers).toHaveLength(1);
    // The camera went to the new focus once it was laid out.
    await waitFor(() =>
      expect(renderer().orbit?.target).toEqual(renderer().node(COMPANY).position),
    );
  });

  it("shows the evidence behind a relationship chosen in the overlay", async () => {
    const api = mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute(`/universe/3d?execution=${EXECUTION}`);
    await drawnWith(50);
    const overlay = await screen.findByRole("region", { name: "Scenario overlay" });
    // The one relationship a model propagated along: Brent crude oil to jet fuel.
    await user.click(within(overlay).getByRole("button", { name: /^Brent.*jet fuel/i }));
    const panel = await screen.findByRole("complementary", { name: "Selected relationship" });
    expect(
      await within(panel).findByRole("region", { name: "Why this connection exists" }),
    ).toBeVisible();
    expect(api.requests.some((request) => request.path === graphPath.edge(TRANSMISSION))).toBe(
      true,
    );
    await waitFor(() => expect(renderer().edge(TRANSMISSION).selected).toBe(true));
  });

  it("lays a stored execution over the graph, with its inputs, pathway and results", async () => {
    const api = mockApi(universeRoutes());
    renderRoute(`/universe/3d?execution=${EXECUTION}`);
    const drawn = await drawnWith(50);
    const overlay = await screen.findByRole("region", { name: "Scenario overlay" });

    expect(
      within(overlay).getByRole("heading", { name: "Oil, rupee and rates on Aerisca" }),
    ).toBeVisible();
    expect(within(overlay).getByText("Simulated")).toBeVisible();
    expect(within(overlay).getByText("Fictional company")).toBeVisible();
    expect(within(overlay).getByText("Not a forecast")).toBeVisible();
    expect(within(overlay).getByText("+20 %")).toBeVisible();
    expect(within(overlay).getByText("+5 %")).toBeVisible();
    expect(within(overlay).getByText("+0.5 percentage points")).toBeVisible();
    expect(within(overlay).getByText("Propagated by a model rule (1)")).toBeVisible();
    expect(
      within(overlay).getByText("Cited: decided which models apply; carries no values (3)"),
    ).toBeVisible();
    expect(
      within(overlay).getByText("Stated in the graph; no included model simulates it (11)"),
    ).toBeInTheDocument();
    expect(within(overlay).getByText(/Rule T1 · coefficient 1 · lag 1 month/)).toBeVisible();
    const results = within(overlay).getByRole("table");
    expect(within(results).getByRole("row", { name: /Operating profit/ })).toHaveTextContent(
      "50,000,000 INR−6,325,000 INR−12.65 %",
    );
    expect(within(overlay).getByRole("link", { name: /Open the execution/ })).toHaveAttribute(
      "href",
      `/scenarios/${universeFixtures.execution().scenario_id}?execution=${EXECUTION}`,
    );
    expect(screen.getByRole("combobox", { name: "Scenario overlay" })).toHaveValue(EXECUTION);

    // On the canvas: the modelled pathway in emphasis, what no model uses dimmed.
    await waitFor(() => expect(drawn.edge(TRANSMISSION).role).toBe("propagated"));
    expect(drawn.edge(TRANSMISSION).tone).toBe("emphasis");
    expect(drawn.node(COMPANY).role).toBe("entity");
    expect(drawn.node(VARIABLE).role).toBe("changed");
    expect(drawn.scene?.edges.find((edge) => edge.role === "unmodelled")?.tone).toBe("dimmed");

    // Read-only: the execution, its pathway and its results, and nothing written.
    for (const path of [executionPath, `${executionPath}/pathways`, `${executionPath}/results`]) {
      expect(api.requests.some((request) => request.path === path)).toBe(true);
    }
    expect(api.writes()).toEqual([]);
  });

  it("puts the overlay picked in the URL, and clearing it takes it away", async () => {
    mockApi(universeRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/universe/3d");
    await drawnWith(50);
    const picker = screen.getByRole("combobox", { name: "Scenario overlay" });
    await waitFor(() => expect(picker).toBeEnabled());
    await user.selectOptions(picker, "Oil, rupee and rates on Aerisca · version 1");
    await waitFor(() => expect(router.state.location.search).toBe(`?execution=${EXECUTION}`));
    const overlay = await screen.findByRole("region", { name: "Scenario overlay" });
    await user.click(within(overlay).getByRole("button", { name: "Clear the overlay" }));
    await waitFor(() => expect(router.state.location.search).toBe(""));
    await waitFor(() => expect(renderer().edge(TRANSMISSION).role).toBeNull());
  });

  it("waits for a running execution, reading it again until it completes", async () => {
    const running: ScenarioExecution = {
      ...universeFixtures.execution(),
      status: "simulating",
      poll_after_ms: 250,
    };
    let reads = 0;
    const api = mockApi(
      universeRoutes({
        [executionPath]: () => {
          reads += 1;
          return { body: reads < 3 ? running : universeFixtures.execution() };
        },
      }),
    );
    renderRoute(`/universe/3d?execution=${EXECUTION}`);
    await drawnWith(50);
    expect(await screen.findByText("No overlay yet")).toBeInTheDocument();
    expect(screen.getByText(/is simulating: only a completed execution/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check now" })).toBeInTheDocument();
    expect(api.requests.some((request) => request.path.endsWith("/results"))).toBe(false);
    expect(renderer().scene?.edges.every((edge) => edge.role === null)).toBe(true);
    // Read again at the server's interval; the overlay appears once it has completed.
    expect(await screen.findByRole("region", { name: "Scenario overlay" })).toBeVisible();
    expect(reads).toBe(3);
    await waitFor(() => expect(renderer().edge(TRANSMISSION).role).toBe("propagated"));
  });

  it("says a failed execution has nothing to lay over, and does not read it again", async () => {
    const failed: ScenarioExecution = {
      ...universeFixtures.execution(),
      status: "failed",
      poll_after_ms: null,
    };
    const api = mockApi(universeRoutes({ [executionPath]: { body: failed } }));
    renderRoute(`/universe/3d?execution=${EXECUTION}`);
    await drawnWith(50);
    expect(await screen.findByText("No overlay")).toBeInTheDocument();
    expect(screen.getByText(/is failed: it has no results to lay over/)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(api.requests.filter((request) => request.path === executionPath)).toHaveLength(1);
  });

  it("says when the overlay cannot be loaded, and retries", async () => {
    const api = mockApi(
      universeRoutes({
        [executionPath]: errorReply(503, "unavailable", "The database is not reachable."),
      }),
    );
    const user = userEvent.setup();
    renderRoute(`/universe/3d?execution=${EXECUTION}`);
    await drawnWith(50);
    expect(await screen.findByText("The scenario overlay could not be loaded")).toBeVisible();
    api.setRoute(executionPath, { body: universeFixtures.execution() });
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByRole("region", { name: "Scenario overlay" })).toBeVisible();
  });

  it("opens a node's neighbourhood from the URL and goes back to the universe", async () => {
    const api = mockApi(universeRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute(`/universe/3d?focus=${encodeURIComponent(COMPANY)}`);
    const neighbourhood = universeFixtures.neighborhoodCompany();
    await drawnWith(neighbourhood.nodes.length);
    expect(api.requests.some((request) => request.path === graphPath.neighborhood(COMPANY))).toBe(
      true,
    );
    expect(await screen.findByText(/within 1 hop of Aerisca Airways/)).toBeInTheDocument();
    expect(renderer().node(COMPANY).focus).toBe(true);

    await user.click(screen.getByRole("button", { name: "Universe" }));
    await waitFor(() => expect(renderer().scene?.nodes.length).toBe(50));
    expect(router.state.location.search).toBe("");
    await user.click(screen.getByRole("button", { name: "Back to the previous view" }));
    await waitFor(() =>
      expect(router.state.location.search).toBe(`?focus=${encodeURIComponent(COMPANY)}`),
    );
  });

  it("says when an expansion could not be loaded, and retries it", async () => {
    const AIR = "industry:ind_air_transport";
    const api = mockApi(
      universeRoutes({
        [graphPath.neighborhood(AIR)]: errorReply(
          503,
          "unavailable",
          "The database is not reachable.",
        ),
      }),
    );
    const user = userEvent.setup();
    renderRoute(`/universe/3d?focus=${encodeURIComponent(COMPANY)}`);
    const drawn = await drawnWith(universeFixtures.neighborhoodCompany().nodes.length);
    click(canvasElement(), drawn.at(AIR).x, drawn.at(AIR).y);
    await waitFor(() => expect(drawn.node(AIR).selected).toBe(true));
    fireEvent.keyDown(await application(), { key: "e" });
    const notice = (await screen.findByText(/An expansion could not be loaded/)).closest(
      "p",
    ) as HTMLElement;
    expect(notice).toHaveAttribute("role", "alert");
    api.setRoute(graphPath.neighborhood(AIR), { body: universeFixtures.neighborhoodCompany() });
    await user.click(within(notice).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByText(/An expansion could not be loaded/)).toBeNull());
  });

  it("resets the camera only, keeping what the reader explored", async () => {
    const api = mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute(`/universe/3d?focus=${encodeURIComponent(COMPANY)}`);
    const drawn = await drawnWith(universeFixtures.neighborhoodCompany().nodes.length);
    await user.selectOptions(screen.getByRole("combobox", { name: "Depth" }), "2 hops");
    await waitFor(() =>
      expect(
        api.requests.some(
          (request) =>
            request.path === graphPath.neighborhood(COMPANY) &&
            new URLSearchParams(request.query).get("depth") === "2",
        ),
      ).toBe(true),
    );
    const orbits = drawn.orbits.length;
    await user.click(screen.getByRole("button", { name: "Reset view" }));
    await waitFor(() => expect(renderer().orbits.length).toBeGreaterThan(orbits));
    expect(screen.getByRole("combobox", { name: "Depth" })).toHaveValue("2");
  });

  it("finds the shortest paths between two nodes from the URL", async () => {
    const api = mockApi(universeRoutes());
    renderRoute(
      `/universe/3d?from=${encodeURIComponent(COMPANY)}&to=${encodeURIComponent(VARIABLE)}`,
    );
    const paths = universeFixtures.paths();
    await drawnWith(paths.nodes.length);
    for (const path of paths.paths) {
      for (const id of path.nodes) expect(renderer().node(id)).toBeDefined();
    }
    expect(await screen.findByText(/on the paths found/)).toBeInTheDocument();
    const request = api.requests.find((item) => item.path === graphPath.paths);
    expect(new URLSearchParams(request?.query).get("from")).toBe(COMPANY);
    expect(new URLSearchParams(request?.query).get("to")).toBe(VARIABLE);
  });

  it("says when filters are on, and how much of the build they show", async () => {
    mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute("/universe/3d");
    await drawnWith(50);
    await user.click(screen.getByRole("checkbox", { name: "Include illustrative" }));
    const recorded = universeFixtures.edges().items.filter((edge) => !edge.is_illustrative);
    expect(
      await screen.findByText(
        `Filters are on: 50 of 50 nodes and ${recorded.length} of 97 relationships shown.`,
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(renderer().scene?.edges).toHaveLength(recorded.length));
    expect(screen.getByText(/the whole build, filtered$/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() => expect(renderer().scene?.edges).toHaveLength(97));
    expect(screen.queryByText(/^Filters are on/)).toBeNull();
  });

  it("shows the list instead, and remembers the choice", async () => {
    mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute("/universe/3d");
    await drawnWith(50);
    await user.click(screen.getByRole("button", { name: "List" }));
    expect(await screen.findByRole("table", { name: /Nodes shown/ })).toBeVisible();
    expect(screen.getByRole("table", { name: /Relationships shown/ })).toBeVisible();
    expect(screen.queryByRole("application")).toBeNull();
    expect(stand.renderers.at(-1)?.disposed).toBe(true);
    expect(window.localStorage.getItem("rumin.universe.stage")).toBe("list");
    await user.click(screen.getByRole("button", { name: "3D" }));
    expect(await application()).toBeInTheDocument();
  });

  it("falls back to the list without WebGL, and says why", async () => {
    stand.webgl = false;
    mockApi(universeRoutes());
    renderRoute("/universe/3d");
    expect(
      await screen.findByText(/This browser cannot draw the 3D view \(it needs WebGL 2\)/),
    ).toBeVisible();
    expect(await screen.findByRole("table", { name: /Nodes shown/ })).toBeVisible();
    expect(stand.renderers).toHaveLength(0);
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to the list when the graphics context is lost, and can try again", async () => {
    mockApi(universeRoutes());
    const user = userEvent.setup();
    renderRoute("/universe/3d");
    const first = await drawnWith(50);
    act(() => first.loseContext());
    expect(await screen.findByText(/The graphics context was lost/)).toBeVisible();
    expect(await screen.findByRole("table", { name: /Nodes shown/ })).toBeVisible();
    expect(first.disposed).toBe(true);
    await user.click(screen.getByRole("button", { name: "Try the 3D view again" }));
    await waitFor(() => expect(stand.renderers).toHaveLength(2));
    await drawnWith(50);
  });

  it("does not load a build too large to draw at once, and starts from a search", async () => {
    const large: GraphOverview = universeFixtures.overview();
    if (large.build) {
      large.build.node_count = 12_000;
      large.build.edge_count = 40_000;
    }
    const api = mockApi(universeRoutes({ [graphPath.overview]: { body: large } }));
    renderRoute("/universe/3d");
    expect(await screen.findByText("The graph is too large to draw at once")).toBeVisible();
    expect(screen.getByText(/draws at most 500 nodes and 2,500 relationships/)).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Start from" })).toBeVisible();
    expect(api.requests.some((request) => request.path === "/api/v1/graph/edges")).toBe(false);
  });

  it("says how to build the graph when there is none", async () => {
    const empty: GraphOverview = { ...universeFixtures.overview(), build: null };
    mockApi(universeRoutes({ [graphPath.overview]: { body: empty } }));
    renderRoute("/universe/3d");
    expect(await screen.findByText("The knowledge graph has not been built yet")).toBeVisible();
    expect(screen.getByText("python -m app.graph build")).toBeVisible();
    expect(screen.queryByRole("application")).toBeNull();
  });

  it("says when the whole build cannot be loaded, and retries", async () => {
    const api = mockApi(
      universeRoutes({
        "/api/v1/graph/edges": errorReply(503, "unavailable", "The database is not reachable."),
      }),
    );
    const user = userEvent.setup();
    renderRoute("/universe/3d");
    expect(await screen.findByText("The universe could not be loaded")).toBeVisible();
    api.setRoute("/api/v1/graph/edges", { body: universeFixtures.edges() });
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    await drawnWith(50);
  });

  it("hands a question to the Analyst without sending it", async () => {
    const api = mockApi(universeRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/universe/3d");
    const drawn = await drawnWith(50);
    click(canvasElement(), drawn.at(COMPANY).x, drawn.at(COMPANY).y);
    const panel = await screen.findByRole("complementary", { name: "Selected node" });
    await user.click(within(panel).getByRole("button", { name: "Ask the Analyst about it" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/analyst"));
    expect(await screen.findByRole("textbox", { name: "Your question" })).toHaveValue(
      "What does RUMIN know about Aerisca Airways?",
    );
    expect(api.writes()).toEqual([]);
    // Leaving the universe disposes its renderer.
    expect(drawn.disposed).toBe(true);
  });

  it("is linked from the 2D explorer, keeping what it shows", async () => {
    mockApi(universeRoutes());
    renderRoute(`/graph?focus=${encodeURIComponent(COMPANY)}`);
    expect(await screen.findByRole("link", { name: "Open in 3D" })).toHaveAttribute(
      "href",
      `/universe/3d?focus=${encodeURIComponent(COMPANY)}`,
    );
  });
});
