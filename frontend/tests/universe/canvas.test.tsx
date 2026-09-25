/**
 * The 3D universe's canvas host with a stand-in renderer (jsdom has no WebGL): picking with
 * the pointer, hover, drag, wheel, the keyboard, names on the canvas, the camera, rendering
 * on demand, and the renderer's lifetime — creation, a lost context, failure and disposal.
 *
 * The graph is a slice of the captured knowledge graph: Brent crude oil and the first three
 * industries it is stated to affect (land transport, petroleum refining, oil and gas
 * extraction) — illustrative relationships of the sample dataset.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/app/theme";
import type { RendererFactory } from "@/features/universe/rendererTypes";
import type { SceneSelection } from "@/features/universe/scene";
import {
  type RenderStats,
  UniverseCanvas,
  type UniverseCanvasHandle,
  type UniverseCanvasProps,
} from "@/features/universe/UniverseCanvas";
import type { GraphEdgeSummary, GraphNodeSummary } from "@/types/api";
import { universeFixtures } from "../fixtures/universe";
import { matchingMediaQueries } from "../utils/browser";
import { StandInRenderer } from "../utils/universe";

const BRENT = "variable:var_brent_crude";
const LAND = "industry:ind_land_transport";

function slice() {
  const all = universeFixtures.edges().items;
  const nodes = universeFixtures.nodes().items;
  const brentEdges = all.filter((edge) => edge.source === BRENT).slice(0, 3);
  const ids = new Set(brentEdges.flatMap((edge) => [edge.source, edge.target]));
  const kept: GraphNodeSummary[] = nodes.filter((node) => ids.has(node.id));
  return { nodes: kept, edges: brentEdges as GraphEdgeSummary[] };
}

interface Harness {
  renderer: () => StandInRenderer;
  handle: React.RefObject<UniverseCanvasHandle | null>;
  calls: {
    select: (SceneSelection | null)[];
    activate: string[];
    expand: string[];
    collapse: string[];
    unavailable: string[];
    stats: RenderStats[];
  };
  surface: () => HTMLElement;
  canvas: () => HTMLCanvasElement;
  rerender: (props: Partial<UniverseCanvasProps>) => void;
  unmount: () => void;
  factory: ReturnType<typeof vi.fn>;
}

function setup(
  overrides: Partial<UniverseCanvasProps> = {},
  options: { canRender?: boolean; failCreate?: boolean; failLoad?: boolean } = {},
): Harness {
  const created: StandInRenderer[] = [];
  const factory = vi.fn<RendererFactory>((canvas, events) => {
    if (options.failCreate) throw new Error("No WebGL context");
    const renderer = new StandInRenderer(canvas, events);
    created.push(renderer);
    return renderer;
  });
  const calls: Harness["calls"] = {
    select: [],
    activate: [],
    expand: [],
    collapse: [],
    unavailable: [],
    stats: [],
  };
  const handle = createRef<UniverseCanvasHandle>();
  const { nodes, edges } = slice();
  const props: UniverseCanvasProps = {
    nodes,
    edges,
    focus: null,
    selection: null,
    overlay: null,
    label: "3D knowledge graph: a slice.",
    onSelect: (selection) => calls.select.push(selection),
    onActivate: (id) => calls.activate.push(id),
    onExpand: (id) => calls.expand.push(id),
    onCollapse: (id) => calls.collapse.push(id),
    onUnavailable: (reason) => calls.unavailable.push(reason),
    onStats: (stats) => calls.stats.push(stats),
    loadRenderer: () =>
      options.failLoad ? Promise.reject(new Error("chunk failed")) : Promise.resolve(factory),
    canRender: () => options.canRender ?? true,
    ...overrides,
  };
  const view = render(
    <ThemeProvider>
      <UniverseCanvas ref={handle} {...props} />
    </ThemeProvider>,
  );
  return {
    renderer: () => {
      const last = created.at(-1);
      if (!last) throw new Error("No renderer was created.");
      return last;
    },
    handle,
    calls,
    surface: () => screen.getByRole("application"),
    canvas: () => view.container.querySelector("canvas") as HTMLCanvasElement,
    rerender: (next) =>
      view.rerender(
        <ThemeProvider>
          <UniverseCanvas ref={handle} {...props} {...next} />
        </ThemeProvider>,
      ),
    unmount: view.unmount,
    factory,
  };
}

async function drawn(harness: Harness) {
  await waitFor(() => expect(harness.renderer().frames).toBeGreaterThan(0));
  return harness.renderer();
}

function click(canvas: HTMLCanvasElement, x: number, y: number) {
  fireEvent.pointerDown(canvas, { pointerId: 1, clientX: x, clientY: y, button: 0 });
  fireEvent.pointerUp(canvas, { pointerId: 1, clientX: x, clientY: y, button: 0 });
}

beforeEach(() => {
  matchingMediaQueries.add("(prefers-reduced-motion: reduce)");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the canvas host", () => {
  it("draws the graph it is given, once, framed, and reports what the frame cost", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const { nodes, edges } = slice();
    expect(renderer.scene?.nodes.map((node) => node.id).sort()).toEqual(
      nodes.map((node) => node.id).sort(),
    );
    expect(renderer.scene?.edges.map((edge) => edge.id).sort()).toEqual(
      edges.map((edge) => edge.id).sort(),
    );
    expect(renderer.size).toMatchObject({ width: 960, height: 640 });
    for (const node of nodes) expect(renderer.at(node.id).visible).toBe(true);
    // One strata guide per level present: the variable's and the industries'.
    expect(renderer.guides.map((guide) => guide.level).sort()).toEqual([0, 1]);
    expect(harness.surface()).toHaveAccessibleName("3D knowledge graph: a slice.");
    expect(harness.calls.stats.at(-1)).toMatchObject({ calls: 7, triangles: 1234 });

    // Rendered on demand: no frames while nothing changes.
    const frames = renderer.frames;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(renderer.frames).toBe(frames);
  });

  it("writes the names beside their nodes, and the strata's names, without overlaps", async () => {
    const harness = setup();
    await drawn(harness);
    const layer = harness.canvas().parentElement?.nextElementSibling as HTMLElement;
    expect(layer).toHaveAttribute("aria-hidden", "true");
    const texts = [...layer.children].map((element) => element.textContent);
    for (const node of slice().nodes) expect(texts).toContain(node.name);
    expect(texts).toContain("Drivers");
    expect(texts).toContain("Industries");
  });

  it("selects the node under the pointer, then the line, then nothing", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const brent = renderer.at(BRENT);
    click(harness.canvas(), brent.x + 3, brent.y - 2);
    expect(harness.calls.select.at(-1)).toEqual({ kind: "node", id: BRENT });

    const edge = renderer.edge(slice().edges.find((item) => item.target === LAND)?.id ?? "");
    const a = renderer.project(edge.from);
    const b = renderer.project(edge.to);
    click(harness.canvas(), (a.x + b.x) / 2, (a.y + b.y) / 2);
    expect(harness.calls.select.at(-1)).toEqual({ kind: "edge", id: edge.id });

    click(harness.canvas(), 4, 4);
    expect(harness.calls.select.at(-1)).toBeNull();
  });

  it("names what is under the pointer, and double-click brings a node to the centre", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const land = renderer.at(LAND);
    fireEvent.pointerMove(harness.canvas(), { pointerId: 1, clientX: land.x, clientY: land.y });
    const detail = await screen.findByText("Industry · Real");
    expect(detail.previousElementSibling).toHaveTextContent("Land transport");
    fireEvent.pointerLeave(harness.canvas());
    await waitFor(() => expect(screen.queryByText("Industry · Real")).toBeNull());

    fireEvent.doubleClick(harness.canvas(), { clientX: land.x, clientY: land.y });
    expect(harness.calls.activate).toEqual([LAND]);
  });

  it("turns the view on a drag, without selecting anything, and zooms on the wheel", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const before = renderer.orbit;
    const start = renderer.at(BRENT);
    fireEvent.pointerDown(harness.canvas(), {
      pointerId: 1,
      clientX: start.x,
      clientY: start.y,
      button: 0,
    });
    fireEvent.pointerMove(harness.canvas(), {
      pointerId: 1,
      clientX: start.x + 60,
      clientY: start.y + 10,
    });
    fireEvent.pointerUp(harness.canvas(), {
      pointerId: 1,
      clientX: start.x + 60,
      clientY: start.y + 10,
    });
    await waitFor(() => expect(renderer.orbit?.theta).not.toBe(before?.theta));
    expect(harness.calls.select).toEqual([]);

    const radius = renderer.orbit?.radius ?? 0;
    fireEvent.wheel(harness.canvas(), { deltaY: 200 });
    await waitFor(() => expect(renderer.orbit?.radius).toBeGreaterThan(radius));
  });

  it("is operated from the keyboard", async () => {
    const harness = setup({ selection: { kind: "node", id: BRENT } });
    const renderer = await drawn(harness);
    const surface = harness.surface();
    expect(surface).toHaveAttribute("tabindex", "0");
    expect(surface).toHaveAttribute("aria-roledescription", "3D knowledge graph");

    // Arrows move the selection to the nearest node on screen in that direction.
    const from = renderer.at(BRENT);
    const others = slice()
      .nodes.filter((node) => node.id !== BRENT)
      .map((node) => ({ id: node.id, ...renderer.at(node.id) }));
    const direction = others.some((point) => point.x > from.x) ? "ArrowRight" : "ArrowLeft";
    fireEvent.keyDown(surface, { key: direction });
    const moved = harness.calls.select.at(-1);
    expect(moved?.kind).toBe("node");
    const target = others.find((point) => point.id === moved?.id);
    expect(target).toBeDefined();
    if (direction === "ArrowRight") expect(target?.x).toBeGreaterThan(from.x);
    else expect(target?.x).toBeLessThan(from.x);

    fireEvent.keyDown(surface, { key: "Enter" });
    fireEvent.keyDown(surface, { key: "e" });
    fireEvent.keyDown(surface, { key: "c" });
    expect(harness.calls.activate).toEqual([BRENT]);
    expect(harness.calls.expand).toEqual([BRENT]);
    expect(harness.calls.collapse).toEqual([BRENT]);

    const theta = renderer.orbit?.theta ?? 0;
    fireEvent.keyDown(surface, { key: "ArrowLeft", shiftKey: true });
    await waitFor(() => expect(renderer.orbit?.theta).not.toBe(theta));
    const radius = renderer.orbit?.radius ?? 0;
    fireEvent.keyDown(surface, { key: "+" });
    await waitFor(() => expect(renderer.orbit?.radius).toBeLessThan(radius));
    fireEvent.keyDown(surface, { key: "r" });
    await waitFor(() => expect(renderer.orbit?.radius).toBeGreaterThan(radius * 0.9));

    fireEvent.keyDown(surface, { key: "Escape" });
    expect(harness.calls.select.at(-1)).toBeNull();
    // Modified keys belong to the browser.
    const count = harness.calls.select.length;
    fireEvent.keyDown(surface, { key: "ArrowRight", ctrlKey: true });
    expect(harness.calls.select.length).toBe(count);
  });

  it("jumps to a node under reduced motion, and flies there otherwise", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const land = renderer.node(LAND).position;
    act(() => harness.handle.current?.flyTo(LAND));
    await waitFor(() => expect(renderer.orbit?.target).toEqual(land));
    const jump = renderer.orbits.length;
    harness.unmount();

    matchingMediaQueries.delete("(prefers-reduced-motion: reduce)");
    const flying = setup();
    const second = await drawn(flying);
    const before = second.orbits.length;
    act(() => flying.handle.current?.flyTo(LAND));
    await waitFor(() => expect(second.orbit?.target).toEqual(second.node(LAND).position), {
      timeout: 2000,
    });
    // A flight takes several frames; a jump, one.
    expect(second.orbits.length - before).toBeGreaterThan(2);
    expect(jump).toBeGreaterThan(0);
  });

  it("draws the latest scene's names when the graph changes during a flight", async () => {
    matchingMediaQueries.delete("(prefers-reduced-motion: reduce)");
    const { nodes, edges } = slice();
    const harness = setup({
      nodes: nodes.filter((node) => node.id !== LAND),
      edges: edges.filter((edge) => edge.target !== LAND),
    });
    const renderer = await drawn(harness);
    act(() => harness.handle.current?.flyTo(BRENT));
    // The graph grows while the camera is still flying.
    harness.rerender({ nodes, edges, anchors: new Map([[LAND, BRENT]]) });
    await waitFor(() => expect(renderer.orbit?.target).toEqual(renderer.node(BRENT).position), {
      timeout: 2000,
    });
    const layer = harness.canvas().parentElement?.nextElementSibling as HTMLElement;
    await waitFor(() =>
      expect([...layer.children].map((element) => element.textContent)).toContain("Land transport"),
    );
    // Picking uses the same frame's positions.
    const land = renderer.at(LAND);
    click(harness.canvas(), land.x, land.y);
    expect(harness.calls.select.at(-1)).toEqual({ kind: "node", id: LAND });
  });

  it("turns the view on a one-finger drag after a mouse has hovered", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    const start = renderer.at(BRENT);
    // A mouse moves over the canvas without pressing: it is not a touch.
    fireEvent.pointerMove(harness.canvas(), { pointerId: 1, clientX: 10, clientY: 10 });
    const before = renderer.orbit;
    fireEvent.pointerDown(harness.canvas(), {
      pointerId: 2,
      clientX: start.x,
      clientY: start.y,
      button: 0,
    });
    fireEvent.pointerMove(harness.canvas(), {
      pointerId: 2,
      clientX: start.x + 60,
      clientY: start.y,
    });
    fireEvent.pointerUp(harness.canvas(), {
      pointerId: 2,
      clientX: start.x + 60,
      clientY: start.y,
    });
    await waitFor(() => expect(renderer.orbit?.theta).not.toBe(before?.theta));
    expect(renderer.orbit?.radius).toBe(before?.radius);
  });

  it("emphasises the selection and dims the rest", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    harness.rerender({ selection: { kind: "node", id: LAND } });
    await waitFor(() => expect(renderer.node(LAND).selected).toBe(true));
    expect(renderer.node(LAND).tone).toBe("emphasis");
    expect(renderer.node(BRENT).tone).toBe("emphasis");
    const unrelated = renderer.scene?.nodes.find((node) => node.id !== LAND && node.id !== BRENT);
    expect(unrelated?.tone).toBe("dimmed");
  });

  it("disposes the renderer when it unmounts", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    harness.unmount();
    expect(renderer.disposed).toBe(true);
  });

  it("reports a lost context, a missing WebGL and a renderer that fails", async () => {
    const harness = setup();
    const renderer = await drawn(harness);
    act(() => renderer.loseContext());
    expect(harness.calls.unavailable).toEqual(["context-lost"]);
    harness.unmount();

    const noWebgl = setup({}, { canRender: false });
    expect(noWebgl.calls.unavailable).toEqual(["webgl"]);
    expect(noWebgl.factory).not.toHaveBeenCalled();
    noWebgl.unmount();

    const failing = setup({}, { failCreate: true });
    await waitFor(() => expect(failing.calls.unavailable).toEqual(["failed"]));
    failing.unmount();

    const unloadable = setup({}, { failLoad: true });
    await waitFor(() => expect(unloadable.calls.unavailable).toEqual(["failed"]));
  });

  it("keeps a node where it was when the graph grows", async () => {
    const { nodes, edges } = slice();
    const first = nodes.filter((node) => node.id !== LAND);
    const harness = setup({
      nodes: first,
      edges: edges.filter((edge) => edge.target !== LAND),
    });
    const renderer = await drawn(harness);
    const before = renderer.node(BRENT).position;
    harness.rerender({ nodes, edges, anchors: new Map([[LAND, BRENT]]) });
    await waitFor(() => expect(renderer.scene?.nodes.some((node) => node.id === LAND)).toBe(true));
    expect(renderer.node(BRENT).position).toEqual(before);
  });
});
