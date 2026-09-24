/**
 * The draft being edited and its conversion to and from the API's scenario body: nothing is
 * parsed, rounded or filled in — values travel as the user typed them.
 */
import { describe, expect, it } from "vitest";
import {
  draftFromScenario,
  draftReducer,
  emptyDraft,
  type LabDraft,
  MAX_CHANGES,
  MAX_STRESS,
  missingBasics,
  sameScenario,
  toInput,
  toUpdate,
} from "@/features/scenarioLab/draft";
import { labFixtures } from "../fixtures/lab";

function saved(): LabDraft {
  return draftFromScenario(labFixtures.scenario());
}

describe("draft conversions", () => {
  it("reads a saved scenario into a draft and writes the same scenario back", () => {
    const scenario = labFixtures.scenario();
    const draft = saved();

    expect(draft.name).toBe("Oil, rupee and rates on Aerisca");
    expect(
      draft.changes.map((change) => [change.variableId, change.direction, change.magnitude]),
    ).toEqual([
      ["var_brent_crude", 1, "20"],
      ["var_usd_inr", 1, "5"],
      ["var_rbi_repo_rate", 1, "0.5"],
    ]);
    expect(draft.entity).toBe("company:co_aerisca_airways");

    const input = toInput(draft);
    expect(input.shocks.map((shock) => shock.value)).toEqual(["20", "5", "0.5"]);
    expect(input.company).toEqual(scenario.spec.company);
    expect(input.timing).toEqual(scenario.spec.timing);
    expect(input.entity).toBe(scenario.spec.entity);
    expect(input.constraints).toEqual(scenario.spec.constraints);
    expect(input.models?.airline_fuel_cost?.assumptions).toEqual(
      scenario.spec.models.airline_fuel_cost?.assumptions,
    );
    expect(input.stress_cases?.map((item) => [item.name, item.scale])).toEqual([
      ["Half", "0.5"],
      ["Double", "2"],
    ]);
  });

  it("keeps a fall as a negative value and never rounds what was typed", () => {
    const draft = emptyDraft();
    const [first] = draft.changes;
    if (!first) throw new Error("an empty draft has one change");
    const edited = draftReducer(draft, {
      type: "change",
      key: first.key,
      patch: { variableId: "var_usd_inr", direction: -1, magnitude: " 2.125000 " },
    });
    expect(toInput(edited).shocks[0]?.value).toBe("-2.125000");
  });

  it("leaves empty figures out instead of filling them in", () => {
    const draft = emptyDraft();
    const input = toInput(draft);
    expect(input.company).toEqual({
      reporting_currency: null,
      annual_revenue: null,
      annual_operating_costs: null,
    });
    expect(input.markets?.fx_rate).toBeNull();
    expect(input.models).toEqual({});
  });

  it("sends a stored exchange rate by its series, not by a value", () => {
    const draft = draftReducer(emptyDraft(), {
      type: "fx",
      patch: { source: "stored_observation", seriesId: "wb-ind-pa-nus-fcrf", value: "83" },
    });
    expect(toInput(draft).markets?.fx_rate).toEqual({
      value: null,
      unit: null,
      source: "stored_observation",
      series_id: "wb-ind-pa-nus-fcrf",
    });
  });

  it("sends a timing that is not a whole number as typed, for the API to report", () => {
    const draft = draftReducer(emptyDraft(), { type: "set", field: "startMonth", value: "1.5" });
    expect(Number.isNaN(toInput(draft).timing?.start_month)).toBe(true);
  });

  it("an update names the version it was edited from", () => {
    expect(toUpdate(saved(), 3).base_version).toBe(3);
  });

  it("knows whether an edit changes what would be saved", () => {
    const draft = saved();
    expect(sameScenario(draft, saved())).toBe(true);
    const renamed = draftReducer(draft, { type: "set", field: "note", value: "why" });
    expect(sameScenario(draft, renamed)).toBe(true); // a version note is not the scenario
    const [first] = draft.changes;
    if (!first) throw new Error("the saved scenario has changes");
    const bigger = draftReducer(draft, {
      type: "change",
      key: first.key,
      patch: { magnitude: "25" },
    });
    expect(sameScenario(draft, bigger)).toBe(false);
  });
});

describe("the draft reducer", () => {
  it("adds and removes changes up to the limit", () => {
    let draft = emptyDraft();
    for (let index = 0; index < MAX_CHANGES + 3; index += 1) {
      draft = draftReducer(draft, { type: "addChange" });
    }
    expect(draft.changes).toHaveLength(MAX_CHANGES);
    const last = draft.changes.at(-1);
    if (!last) throw new Error("changes were added");
    draft = draftReducer(draft, { type: "removeChange", key: last.key });
    expect(draft.changes).toHaveLength(MAX_CHANGES - 1);
  });

  it("edits a model's mode, inputs and assumptions without touching the others", () => {
    let draft = saved();
    draft = draftReducer(draft, {
      type: "modelMode",
      model: "crude_linked_costs",
      mode: "exclude",
    });
    draft = draftReducer(draft, {
      type: "modelAssumption",
      model: "airline_fuel_cost",
      input: "hedge_ratio",
      value: "60",
    });
    draft = draftReducer(draft, {
      type: "modelInput",
      model: "fx_exposure",
      input: "annual_usd_costs",
      patch: { value: "250000" },
    });
    const input = toInput(draft);
    expect(input.models?.crude_linked_costs?.mode).toBe("exclude");
    expect(input.models?.airline_fuel_cost?.assumptions?.hedge_ratio).toBe("60");
    expect(input.models?.airline_fuel_cost?.assumptions?.fare_pass_through).toBe("50");
    expect(input.models?.fx_exposure?.inputs?.annual_usd_costs?.value).toBe("250000");
    expect(input.models?.fx_exposure?.inputs?.annual_usd_revenue?.value).toBe("500000");
  });

  it("builds stress cases by scale or by values, up to the limit", () => {
    let draft = emptyDraft();
    for (let index = 0; index < MAX_STRESS + 2; index += 1) {
      draft = draftReducer(draft, { type: "addStress" });
    }
    expect(draft.stress).toHaveLength(MAX_STRESS);
    const [first, second] = draft.stress;
    if (!first || !second) throw new Error("stress cases were added");
    draft = draftReducer(draft, {
      type: "stress",
      key: first.key,
      patch: { name: " Severe ", scale: "2" },
    });
    draft = draftReducer(draft, {
      type: "stress",
      key: second.key,
      patch: { name: "Mild", kind: "values" },
    });
    draft = draftReducer(draft, {
      type: "stressChange",
      key: second.key,
      variable: "var_brent_crude",
      value: "7.5",
    });
    draft = draftReducer(draft, {
      type: "stressChange",
      key: second.key,
      variable: "var_usd_inr",
      value: " ",
    });
    const [severe, mild] = toInput(draft).stress_cases ?? [];
    expect(severe).toEqual({ name: "Severe", scale: "2", changes: {} });
    expect(mild).toEqual({ name: "Mild", scale: null, changes: { var_brent_crude: "7.5" } });
  });
});

describe("the browser's own checks", () => {
  it("only asks for what must be there — never a domain rule", () => {
    expect(missingBasics(emptyDraft())).toEqual({
      name: "Give the scenario a name.",
      "shocks[0].variable_id": "Choose a variable.",
      "shocks[0].value": "Enter the size of the change.",
    });
    // A fall of 150 % is for the API to refuse, not the browser.
    const [first] = saved().changes;
    if (!first) throw new Error("the saved scenario has changes");
    const extreme = draftReducer(saved(), {
      type: "change",
      key: first.key,
      patch: { direction: -1, magnitude: "150" },
    });
    expect(missingBasics(extreme)).toEqual({});
  });
});
