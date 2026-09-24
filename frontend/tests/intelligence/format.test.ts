import { describe, expect, it } from "vitest";
import {
  change,
  entityPath,
  GRADE_ORDER,
  groupOf,
  money,
  percent,
  refHref,
  refLabel,
  stored,
} from "@/features/intelligence/format";

describe("Financial intelligence formatting", () => {
  it("rounds for display only, from the exact decimal strings", () => {
    expect(money("-6700000", "INR", true)).toBe("−6,700,000 INR");
    expect(money("375000", "INR", true)).toBe("+375,000 INR");
    expect(money("12.345", "USD")).toBe("12.35 USD");
    expect(money(null, "INR")).toBe("—");
    expect(percent("-17.6315789474")).toBe("−17.63 %");
    expect(percent("5", false)).toBe("5 %");
    expect(change("9.3824228029", "percent")).toBe("+9.38 %");
    expect(change("-1.8", "percentage_points")).toBe("−1.8 pp");
    expect(stored("84.2")).toBe("84.2");
    expect(stored("1234567.891")).toBe("1,234,567.891");
    expect(stored("not a number")).toBe("—");
  });

  it("orders grades strongest first and groups kinds of finding", () => {
    expect(GRADE_ORDER[0]).toBe("observed");
    expect(GRADE_ORDER.at(-1)).toBe("unverified");
    expect(groupOf("change")).toBe("observed");
    expect(groupOf("interpretation")).toBe("simulated");
    expect(groupOf("cross_entity")).toBe("relationships");
    expect(groupOf("coverage")).toBe("coverage");
  });

  it("links a cited record to the view that shows it, when there is one", () => {
    const scenarios = new Map([["exec-1", "scen-1"]]);
    expect(entityPath("company:co_aerisca_airways")).toBe(
      "/intelligence/company%3Aco_aerisca_airways",
    );
    expect(refHref({ kind: "graph_node", id: "variable:var_usd_inr", label: null })).toBe(
      "/graph?focus=variable%3Avar_usd_inr",
    );
    expect(refHref({ kind: "graph_node", id: "industry:ind_air_transport", label: null })).toBe(
      "/intelligence/industry%3Aind_air_transport",
    );
    expect(refHref({ kind: "series", id: "wb-ind-pa-nus-fcrf", label: null })).toBe(
      "/data/series/wb-ind-pa-nus-fcrf",
    );
    expect(refHref({ kind: "execution", id: "exec-1", label: null }, scenarios)).toBe(
      "/scenarios/scen-1?execution=exec-1",
    );
    expect(refHref({ kind: "execution", id: "exec-2", label: null }, scenarios)).toBeNull();
    expect(refHref({ kind: "threshold", id: "anomaly_score", label: null })).toBeNull();
    expect(refLabel({ kind: "graph_edge", id: "e-2afc04ee80f0699e", label: "long text" })).toBe(
      "Relationship e-2afc04ee80f0699e",
    );
    expect(refLabel({ kind: "observation", id: "29", label: "2024" })).toBe(
      "Observation 2024 (record 29)",
    );
  });
});
