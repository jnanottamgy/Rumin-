import { describe, expect, it } from "vitest";
import {
  EVIDENCE_ENCODING,
  EVIDENCE_ORDER,
  glyphPath,
  graphHref,
  isHollow,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
  NODE_TYPE_ORDER,
  nodeRadius,
  typeFromKey,
} from "@/features/graph/encoding";
import { toggleInSelection } from "@/features/graph/GraphFilters";
import {
  DEFAULT_FILTERS,
  type ExplorerSnapshot,
  type History,
  initialSnapshot,
  isFiltered,
  neighborhoodKey,
  pushHistory,
} from "@/features/graph/useGraphExplorer";
import { graphFixtures } from "../fixtures/graph";

describe("visual encoding", () => {
  it("gives every node type the API knows a distinct shape", () => {
    const types = graphFixtures.types().node_types.map((item) => item.type);
    expect([...NODE_TYPE_ORDER].sort()).toEqual([...types].sort());
    const shapes = types.map((type) => NODE_TYPE_ENCODING[type].shape);
    expect(new Set(shapes).size).toBe(types.length);
  });

  it("tells evidence statuses apart by line pattern, not colour", () => {
    const statuses = graphFixtures.types().evidence_statuses.map((item) => item.status);
    expect([...EVIDENCE_ORDER].sort()).toEqual([...statuses].sort());
    const patterns = EVIDENCE_ORDER.map((status) => EVIDENCE_ENCODING[status].dash ?? "solid");
    expect(new Set(patterns).size).toBe(EVIDENCE_ORDER.length);
    expect(EVIDENCE_ENCODING.evidence_backed.dash).toBeNull();
  });

  it("marks fictional and sample records with different rings, and real ones with none", () => {
    expect(NATURE_ENCODING.real.ringDash).toBeNull();
    expect(NATURE_ENCODING.fictional.ringDash).toBeTruthy();
    expect(NATURE_ENCODING.sample.ringDash).toBeTruthy();
    expect(NATURE_ENCODING.fictional.ringDash).not.toBe(NATURE_ENCODING.sample.ringDash);
  });

  it("draws series hollow when only their definition is stored", () => {
    expect(isHollow({ type: "data_series", data_status: "definition_only" })).toBe(true);
    expect(isHollow({ type: "data_series", data_status: "values_stored" })).toBe(false);
    expect(isHollow({ type: "company", data_status: "not_applicable" })).toBe(false);
    expect(isHollow({ type: "industry", data_status: "not_applicable" })).toBe(true);
  });

  it("returns a closed path for every polygon shape and none for circles", () => {
    for (const type of NODE_TYPE_ORDER) {
      const { shape } = NODE_TYPE_ENCODING[type];
      const path = glyphPath(shape, 6);
      if (shape === "dot" || shape === "ring" || shape === "target") expect(path).toBeNull();
      else expect(path, shape).toMatch(/Z$/);
    }
  });

  it("grows nodes gently with degree, with a ceiling", () => {
    expect(nodeRadius("company", 4)).toBeGreaterThan(nodeRadius("company", 1));
    expect(nodeRadius("company", 1000)).toBe(nodeRadius("company", 64));
  });
});

describe("node keys and links", () => {
  it("reads the type from a key and rejects anything that is not a node key", () => {
    expect(typeFromKey("company:co_deltrin_refining")).toBe("company");
    expect(typeFromKey("variable:var_usd_inr")).toBe("economic_variable");
    expect(typeFromKey("series:wb-ind-ny-gdp-mktp-cd")).toBe("data_series");
    expect(typeFromKey("Company:X")).toBeNull();
    expect(typeFromKey("company:")).toBeNull();
    expect(typeFromKey("planet:mars")).toBeNull();
    expect(typeFromKey("company:a b")).toBeNull();
  });

  it("builds explorer links the way the build forms keys (lower case)", () => {
    expect(graphHref("company", "co_deltrin_refining")).toBe(
      "/graph?focus=company%3Aco_deltrin_refining",
    );
    expect(graphHref("instrument", "INS_ABC")).toBe("/graph?focus=instrument%3Ains_abc");
    expect(graphHref("series", "bad id")).toBeNull();
  });
});

describe("filters", () => {
  const all = ["a", "b", "c"] as const;

  it("treats an empty selection as everything", () => {
    expect(toggleInSelection([], all, "b")).toEqual(["a", "c"]);
    expect(toggleInSelection(["a", "c"], all, "b")).toEqual([]);
    expect(toggleInSelection(["a"], all, "c")).toEqual(["a", "c"]);
  });

  it("never lets the last value be turned off", () => {
    expect(toggleInSelection(["a"], all, "a")).toEqual(["a"]);
  });

  it("knows when a filter is on", () => {
    expect(isFiltered(DEFAULT_FILTERS)).toBe(false);
    expect(isFiltered({ ...DEFAULT_FILTERS, includeIllustrative: false })).toBe(true);
    expect(isFiltered({ ...DEFAULT_FILTERS, evidenceStatuses: ["evidence_backed"] })).toBe(true);
  });

  it("caches answers per request: filter order does not matter, filter content does", () => {
    const one = neighborhoodKey("company:x", 1, 100, {
      ...DEFAULT_FILTERS,
      evidenceStatuses: ["evidence_backed", "analyst_created"],
    });
    const two = neighborhoodKey("company:x", 1, 100, {
      ...DEFAULT_FILTERS,
      evidenceStatuses: ["analyst_created", "evidence_backed"],
    });
    expect(one).toBe(two);
    expect(neighborhoodKey("company:x", 2, 100, DEFAULT_FILTERS)).not.toBe(
      neighborhoodKey("company:x", 1, 100, DEFAULT_FILTERS),
    );
  });
});

describe("history", () => {
  const start = initialSnapshot("company:a");
  const step = (focus: string): ExplorerSnapshot => ({
    ...start,
    focus,
    selection: { kind: "node", id: focus },
  });

  it("records new views, ignores repeats and drops the forward branch", () => {
    let history: History = { entries: [start], index: 0 };
    history = pushHistory(history, step("company:b"));
    history = pushHistory(history, step("company:b"));
    expect(history.entries).toHaveLength(2);
    history = { ...history, index: 0 };
    history = pushHistory(history, step("company:c"));
    expect(history.entries.map((entry) => entry.focus)).toEqual(["company:a", "company:c"]);
    expect(history.index).toBe(1);
  });

  it("keeps a bounded history", () => {
    let history: History = { entries: [start], index: 0 };
    for (let index = 0; index < 100; index += 1) {
      history = pushHistory(history, step(`company:n${index}`));
    }
    expect(history.entries.length).toBeLessThanOrEqual(60);
    expect(history.entries.at(-1)?.focus).toBe("company:n99");
  });

  it("starts on the map without a focus, and in path mode from a path link", () => {
    expect(initialSnapshot(null).mode).toBe("map");
    expect(initialSnapshot("company:a")).toMatchObject({
      mode: "explore",
      selection: { kind: "node", id: "company:a" },
    });
    expect(initialSnapshot(null, { from: "company:a", to: "company:b" })).toMatchObject({
      mode: "paths",
      path: { from: "company:a", to: "company:b", maxDepth: 4, limit: 3 },
    });
  });
});
