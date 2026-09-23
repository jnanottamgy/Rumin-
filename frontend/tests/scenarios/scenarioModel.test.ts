import { describe, expect, it } from "vitest";
import {
  checkValue,
  describeShock,
  draftFromScenario,
  type EditorState,
  editorReducer,
  emptyDraft,
  emptyShock,
  errorsFromApi,
  exampleDraft,
  initialEditorState,
  isDirty,
  MAX_SHOCKS,
  parseChange,
  ruleFor,
  type ScenarioDraft,
  shockField,
  toPayload,
  validateDraft,
} from "@/features/scenarios/scenarioModel";
import { ApiError } from "@/lib/apiClient";
import type { ChangeRule } from "@/types/api";
import { scenarioFixture, variableFixture, variablesFixture } from "../fixtures";

const variables = new Map(variablesFixture().items.map((variable) => [variable.id, variable]));
const brent = variableFixture("var_brent_crude");
const repoRate = variableFixture("var_rbi_repo_rate");

function rule(variableId: string, changeType: ChangeRule["change_type"]): ChangeRule {
  const found = ruleFor(variableFixture(variableId), changeType);
  if (!found) throw new Error(`No ${changeType} rule for ${variableId}`);
  return found;
}

function draft(shocks: Partial<ScenarioDraft["shocks"][number]>[], name = "Oil shock") {
  return {
    ...emptyDraft(),
    name,
    shocks: shocks.map((shock) => ({ ...emptyShock(), ...shock })),
  };
}

describe("parseChange", () => {
  it.each([
    ["30", 30],
    ["+12.5", 12.5],
    ["-0.25", -0.25],
    ["−0.25", -0.25], // typographic minus, as people paste it
    [" .5 ", 0.5],
  ])("reads %j as %d", (raw, expected) => {
    expect(parseChange(raw)).toBe(expected);
  });

  it.each(["", "abc", "1e3", "1,000", "12.5%", "--1", "Infinity"])("rejects %j", (raw) => {
    expect(parseChange(raw)).toBeNull();
  });
});

describe("checkValue uses the rules the API publishes", () => {
  const percent = rule("var_brent_crude", "percent_change");
  const points = rule("var_rbi_repo_rate", "absolute_change");

  it("describes the published limits", () => {
    expect(percent).toMatchObject({ minimum: -100, minimum_exclusive: true, maximum: 1000 });
    expect(points).toMatchObject({ minimum: -25, maximum: 25, unit_label: "percentage points" });
    // Rates can only change in percentage points: a percent of a percent is ambiguous.
    expect(ruleFor(repoRate, "percent_change")).toBeUndefined();
  });

  it("accepts values inside the limits", () => {
    for (const value of ["30", "-99.9999", "1000"]) expect(checkValue(value, percent)).toBeNull();
    for (const value of ["0.25", "-25", "25"]) expect(checkValue(value, points)).toBeNull();
  });

  it("rejects empty, zero, non-numeric, out-of-range and over-precise values", () => {
    expect(checkValue("", percent)).toBe("Enter the size of the change.");
    expect(checkValue("0", percent)).toBe("A change of zero has no effect.");
    expect(checkValue("thirty", percent)).toMatch(/Enter a number/);
    expect(checkValue("-100", percent)).toBe("Must be greater than −100%.");
    expect(checkValue("1000.5", percent)).toBe("Must be at most +1,000%.");
    expect(checkValue("-25.01", points)).toBe("Must be at least −25 percentage points.");
    expect(checkValue("1.23456", percent)).toBe("Use at most 4 decimal places.");
  });
});

describe("validateDraft", () => {
  it("accepts a complete draft", () => {
    const valid = draft([
      { variableId: "var_brent_crude", changeType: "percent_change", value: "30" },
      { variableId: "var_rbi_repo_rate", changeType: "absolute_change", value: "0.5" },
    ]);
    expect(validateDraft(valid, variables)).toEqual({});
  });

  it("requires a name and rejects control characters", () => {
    const shocks = [
      { variableId: "var_brent_crude", changeType: "percent_change" as const, value: "30" },
    ];
    expect(validateDraft(draft(shocks, "  "), variables)).toEqual({
      name: "Give the scenario a name.",
    });
    expect(validateDraft(draft(shocks, "Oil\u0007"), variables)).toEqual({
      name: "Remove control characters.",
    });
  });

  it("keys each problem to the input that has it", () => {
    const bad = draft([
      { variableId: "" },
      { variableId: "var_unknown" },
      { variableId: "var_brent_crude", changeType: "", value: "30" },
      { variableId: "var_rbi_repo_rate", changeType: "absolute_change", value: "40" },
    ]);
    const [none, unknown, noType, tooBig] = bad.shocks;
    expect(validateDraft(bad, variables)).toEqual({
      [shockField(none?.key ?? "", "variableId")]: "Choose a variable.",
      [shockField(unknown?.key ?? "", "variableId")]: "This variable is not in the dataset.",
      [shockField(noType?.key ?? "", "changeType")]: "Choose how the variable changes.",
      [shockField(tooBig?.key ?? "", "value")]: "Must be at most +25 percentage points.",
    });
  });

  it("rejects the same variable twice", () => {
    const twice = draft([
      { variableId: "var_brent_crude", changeType: "percent_change", value: "30" },
      { variableId: "var_brent_crude", changeType: "percent_change", value: "10" },
    ]);
    const second = twice.shocks[1]?.key ?? "";
    expect(validateDraft(twice, variables)).toEqual({
      [shockField(second, "variableId")]: expect.stringMatching(/already changed above/),
    });
  });

  it("requires at least one input", () => {
    expect(validateDraft({ ...draft([]), shocks: [] }, variables)).toEqual({
      shocks: "Add at least one input.",
    });
  });
});

describe("toPayload", () => {
  it("trims text and converts values into the API's shape", () => {
    const payload = toPayload({
      ...draft([
        {
          variableId: "var_brent_crude",
          changeType: "percent_change",
          value: " −12.5 ",
          note: " x ",
        },
      ]),
      name: "  Oil  ",
      description: " Why ",
    });
    expect(payload).toEqual({
      name: "Oil",
      description: "Why",
      shocks: [
        { variable_id: "var_brent_crude", change_type: "percent_change", value: -12.5, note: "x" },
      ],
    });
  });

  it("round-trips a saved scenario", () => {
    const scenario = scenarioFixture();
    expect(toPayload(draftFromScenario(scenario))).toEqual({
      name: scenario.name,
      description: scenario.description,
      shocks: [
        { variable_id: "var_brent_crude", change_type: "percent_change", value: 30, note: "" },
      ],
    });
  });
});

describe("errorsFromApi", () => {
  it("puts the server's validation messages on the matching fields", () => {
    const current = draft([
      { variableId: "var_brent_crude", changeType: "percent_change", value: "-100" },
    ]);
    const error = new ApiError("http", "The scenario inputs are invalid.", {
      status: 422,
      code: "validation_error",
      details: [
        {
          location: "body",
          field: "shocks[0].value",
          message: "The change must be greater than -100 %.",
          type: "invalid_change",
        },
        { location: "body", field: "name", message: "Too long.", type: "string_too_long" },
        { location: "body", field: "unexpected", message: "Extra.", type: "extra_forbidden" },
      ],
    });
    expect(errorsFromApi(error, current)).toEqual({
      [shockField(current.shocks[0]?.key ?? "", "value")]:
        "The change must be greater than -100 %.",
      name: "Too long.",
      form: "Extra.",
    });
  });

  it("falls back to the error's message when there are no field details", () => {
    const error = new ApiError("http", "Scenario not found.", { status: 404 });
    expect(errorsFromApi(error, emptyDraft())).toEqual({ form: "Scenario not found." });
  });
});

describe("editorReducer", () => {
  const start = (): EditorState => initialEditorState(emptyDraft());

  it("adds inputs up to the limit", () => {
    let state = start();
    for (let i = 0; i < MAX_SHOCKS + 3; i += 1) state = editorReducer(state, { type: "addShock" });
    expect(state.draft.shocks).toHaveLength(MAX_SHOCKS);
  });

  it("clears a field's error when the field changes", () => {
    const state = start();
    const key = state.draft.shocks[0]?.key ?? "";
    const withErrors = editorReducer(state, {
      type: "setErrors",
      errors: { name: "Give the scenario a name.", [shockField(key, "value")]: "Bad" },
    });
    const named = editorReducer(withErrors, { type: "setName", value: "Oil" });
    expect(named.errors).toEqual({ [shockField(key, "value")]: "Bad" });
    const fixed = editorReducer(named, { type: "updateShock", key, patch: { value: "30" } });
    expect(fixed.errors).toEqual({});
  });

  it("removes an input together with its errors", () => {
    let state = editorReducer(start(), { type: "addShock" });
    const key = state.draft.shocks[1]?.key ?? "";
    state = editorReducer(state, {
      type: "setErrors",
      errors: { [shockField(key, "value")]: "x" },
    });
    state = editorReducer(state, { type: "removeShock", key });
    expect(state.draft.shocks).toHaveLength(1);
    expect(state.errors).toEqual({});
  });

  it("tracks unsaved changes", () => {
    const blank = start();
    expect(isDirty(blank)).toBe(false);
    expect(isDirty(editorReducer(blank, { type: "setName", value: "Oil" }))).toBe(true);

    const saved = initialEditorState(draftFromScenario(scenarioFixture()));
    expect(isDirty(saved)).toBe(false);
    expect(isDirty(editorReducer(saved, { type: "setDescription", value: "Changed" }))).toBe(true);
    // Whitespace-only edits are not real changes.
    expect(isDirty(editorReducer(saved, { type: "setName", value: "Oil price shock " }))).toBe(
      false,
    );
  });
});

describe("describeShock", () => {
  it("reads an input back in plain words", () => {
    const [shock] = exampleDraft().shocks;
    if (!shock) throw new Error("example has no inputs");
    expect(describeShock(shock, brent)).toBe("Brent crude oil price: +30% (relative change)");
    expect(describeShock({ ...shock, value: "" }, brent)).toBe(
      "Brent crude oil price: change not set",
    );
    expect(describeShock(shock, undefined)).toBe("No variable chosen yet");
  });
});
