import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { buildGraphModel, neighborhood } from "@/features/network/model";
import { networkFixture } from "../fixtures";
import { mockApi, unreachable } from "../utils/api";
import { matchingMediaQueries } from "../utils/browser";
import { renderRoute } from "../utils/render";

const model = buildGraphModel(networkFixture());
const SELECTED = "co_deltrin_refining";

const drawnNodes = (root: HTMLElement) =>
  [...root.querySelectorAll<SVGGElement>("g[data-node-id]")].map((element) => ({
    id: element.dataset.nodeId ?? "",
    state: element.dataset.state,
  }));

const drawnEdges = (root: HTMLElement) =>
  [...root.querySelectorAll<SVGPathElement>("path[data-edge-id]")].map((element) => ({
    id: element.dataset.edgeId ?? "",
    state: element.dataset.state,
  }));

async function openUniverse(path = "/universe") {
  const view = renderRoute(path);
  await screen.findByRole("group", { name: /^Financial network: 30 entities and 71 links/ });
  return view;
}

describe("Financial Universe", () => {
  it("draws exactly the entities and links the API returns", async () => {
    mockApi();
    const { container } = await openUniverse();

    const nodes = drawnNodes(container);
    expect(nodes.map((node) => node.id).sort()).toEqual(model.nodes.map((n) => n.id).sort());
    const edges = drawnEdges(container);
    expect(edges.map((edge) => edge.id).sort()).toEqual(model.edges.map((e) => e.id).sort());

    // Every drawn link connects two drawn entities.
    const drawn = new Set(nodes.map((node) => node.id));
    for (const { id } of edges) {
      const edge = model.edgeById.get(id);
      expect(edge && drawn.has(edge.source) && drawn.has(edge.target), id).toBe(true);
    }
    expect(screen.getByText(/Showing 30 of 30 entities · 71 of 71 links/)).toBeInTheDocument();
    expect(screen.getByText(/Illustrative dataset · v1\.0\.0/)).toBeInTheDocument();
  });

  it("highlights a selected entity's connections, dims the rest, and resets", async () => {
    mockApi();
    const user = userEvent.setup();
    const { container, router } = await openUniverse();
    const hood = neighborhood(model, SELECTED);

    await user.click(
      screen.getByRole("button", { name: /^Deltrin Refining, company, 8 connections/ }),
    );

    for (const node of drawnNodes(container)) {
      const expected =
        node.id === SELECTED ? "selected" : hood.nodeIds.has(node.id) ? "neighbor" : "dimmed";
      expect(node.state, node.id).toBe(expected);
    }
    for (const edge of drawnEdges(container)) {
      expect(edge.state, edge.id).toBe(hood.edgeIds.has(edge.id) ? "active" : "dimmed");
    }

    // The details panel describes the selection, and the URL can be shared.
    const details = screen.getByRole("complementary", { name: "Selected entity" });
    expect(
      within(details).getByRole("heading", { level: 2, name: "Deltrin Refining" }),
    ).toBeInTheDocument();
    expect(within(details).getByText("Fictional")).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?focus=${SELECTED}`);

    await user.keyboard("{Escape}");
    expect(drawnNodes(container).every((node) => node.state === "default")).toBe(true);
    expect(within(details).getByText("Select an entity")).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
  });

  it("clears the selection from the details panel", async () => {
    mockApi();
    const user = userEvent.setup();
    const { container } = await openUniverse(`/universe?focus=${SELECTED}`);
    expect(container.querySelector(`[data-node-id="${SELECTED}"]`)).toHaveAttribute(
      "data-state",
      "selected",
    );

    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(drawnNodes(container).every((node) => node.state === "default")).toBe(true);
  });

  it("selects an entity from the keyboard", async () => {
    mockApi();
    const user = userEvent.setup();
    await openUniverse();
    const india = screen.getByRole("button", { name: /^India, country/ });

    india.focus();
    await user.keyboard("{Enter}");
    expect(india).toHaveAttribute("data-state", "selected");
    expect(india).toHaveAttribute("aria-pressed", "true");
  });

  it("finds an entity by name", async () => {
    mockApi();
    const user = userEvent.setup();
    await openUniverse();

    await user.type(screen.getByRole("combobox", { name: "Find an entity" }), "anvaya");
    await user.click(screen.getByRole("option", { name: /Anvaya Bank/ }));
    expect(screen.getByRole("button", { name: /^Anvaya Bank, company/ })).toHaveAttribute(
      "data-state",
      "selected",
    );
  });

  it("filters entity kinds without leaving links in empty space", async () => {
    mockApi();
    const user = userEvent.setup();
    const { container } = await openUniverse();

    await user.click(screen.getByRole("button", { name: /^Companies/ }));
    expect(screen.getByRole("button", { name: /^Companies/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    const nodes = drawnNodes(container);
    expect(nodes).toHaveLength(18);
    expect(container.querySelector('g[data-kind="company"]')).toBeNull();
    const drawn = new Set(nodes.map((node) => node.id));
    for (const { id } of drawnEdges(container)) {
      const edge = model.edgeById.get(id);
      expect(edge && drawn.has(edge.source) && drawn.has(edge.target), id).toBe(true);
    }
    expect(screen.getByText(/Showing 18 of 30 entities/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(drawnNodes(container)).toHaveLength(30);
    expect(screen.queryByRole("button", { name: "Reset filters" })).toBeNull();
  });

  it("drops a selection that a filter hides", async () => {
    mockApi();
    const user = userEvent.setup();
    const { container } = await openUniverse(`/universe?focus=${SELECTED}`);

    await user.click(screen.getByRole("button", { name: /^Companies/ }));
    expect(drawnNodes(container).every((node) => node.state === "default")).toBe(true);
    expect(screen.getByText("Select an entity")).toBeInTheDocument();
  });

  it("offers the same data as tables", async () => {
    mockApi();
    const user = userEvent.setup();
    await openUniverse();

    await user.click(screen.getByRole("button", { name: "Table" }));
    const [entities, relationships] = screen.getAllByRole("table");
    if (!entities || !relationships) throw new Error("expected two tables");
    expect(within(entities).getAllByRole("rowheader")).toHaveLength(30);
    expect(within(relationships).getAllByRole("row")).toHaveLength(71 + 1); // + header
    expect(screen.getByRole("heading", { name: "Relationships (71)" })).toBeInTheDocument();

    // Selecting a row narrows the relationships to that entity.
    await user.click(within(entities).getByRole("button", { name: "Deltrin Refining" }));
    expect(
      screen.getByRole("heading", { name: "Relationships (8) touching Deltrin Refining" }),
    ).toBeInTheDocument();
  });

  it("labels only the selection on phones, in a portrait layout", async () => {
    matchingMediaQueries.add("(max-width: 40rem)");
    mockApi();
    const user = userEvent.setup();
    const { container } = await openUniverse();
    expect(container.querySelectorAll("g[data-node-id] text")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /^India, country/ }));
    const labels = [...container.querySelectorAll("g[data-node-id] text")];
    expect(labels.map((label) => label.textContent)).toEqual(["India"]);
  });

  it("refuses to draw an inconsistent network", async () => {
    const broken = networkFixture();
    const edge = broken.edges[0];
    if (!edge) throw new Error("fixture has no edges");
    edge.target_id = "co_missing";
    mockApi({ "/api/v1/network": { body: broken } });
    const { container } = renderRoute("/universe");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This data could not be loaded");
    expect(alert).toHaveTextContent(`Edge "${edge.id}" points to unknown node "co_missing"`);
    expect(container.querySelector("[data-node-id]")).toBeNull();
  });

  it("explains an unreachable API and recovers on retry", async () => {
    const api = mockApi({ "/api/v1/network": unreachable });
    const user = userEvent.setup();
    renderRoute("/universe");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the RUMIN API");
    expect(alert).toHaveTextContent(/Start the backend/);

    api.setRoute("/api/v1/network", { body: networkFixture() });
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("group", { name: /^Financial network: 30 entities/ }),
    ).toBeInTheDocument();
  });
});
