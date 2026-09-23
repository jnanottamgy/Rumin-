/** The form is built from the model definition and sends exactly what was typed. */
import { describe, expect, it } from "vitest";
import { withExample } from "@/features/simulation/examples";
import {
  emptyForm,
  formFromRun,
  inputsByCategory,
  issuesByField,
  issuesFromDetails,
  rangeText,
  toRequestInputs,
} from "@/features/simulation/form";
import { simulationFixtures } from "../fixtures/simulation";

describe("simulation form", () => {
  const model = simulationFixtures.model();

  it("groups the inputs by the kind of knowledge they are", () => {
    expect(inputsByCategory(model).map((group) => group.category)).toEqual([
      "scenario_input",
      "market_baseline",
      "company_input",
      "assumption",
      "setting",
    ]);
  });

  it("starts empty, with the first unit of each quantity chosen", () => {
    const form = emptyForm(model);
    expect(form.crude_oil_change).toEqual({ value: "", unit: null, stored: false });
    expect(form.jet_fuel_price?.unit).toBe("usd_per_us_gallon");
    expect(toRequestInputs(model, form)).toEqual({}); // nothing typed: nothing sent
  });

  it("sends typed values as exact strings, with units, and leaves defaults out", () => {
    const form = emptyForm(model);
    form.crude_oil_change = { value: " 10.25 ", unit: null, stored: false };
    form.jet_fuel_price = { value: "2.35", unit: "usd_per_us_barrel", stored: false };
    form.fx_rate = { value: "", unit: null, stored: true };
    expect(toRequestInputs(model, form)).toEqual({
      crude_oil_change: { value: "10.25" },
      jet_fuel_price: { value: "2.35", unit: "usd_per_us_barrel" },
      fx_rate: { source: "stored_observation", series_id: "wb-ind-pa-nus-fcrf" },
    });
  });

  it("rebuilds a stored run's inputs, keeping defaults as defaults", () => {
    const form = formFromRun(model, simulationFixtures.run());
    expect(form.crude_oil_change?.value).toBe("10");
    expect(form.jet_fuel_price).toEqual({ value: "750", unit: "usd_per_kilolitre", stored: false });
    expect(form.crude_pass_through?.value).toBe(""); // was the model default
    expect(toRequestInputs(model, form)).toMatchObject({ hedge_ratio: { value: "50" } });
  });

  it("fills the hypothetical example and nothing else", () => {
    const example = withExample(model.id, emptyForm(model));
    expect(example?.annual_revenue?.value).toBe("300000000");
    expect(example?.crude_pass_through?.value).toBe("");
    expect(withExample("unknown_model", emptyForm(model))).toBeNull();
  });

  it("maps the API's error details onto fields", () => {
    const issues = issuesFromDetails([
      {
        field: "inputs.hedge_ratio",
        message: "Hedge ratio must be at most 100 %.",
        type: "input_range",
      },
      { field: "inputs", message: "The calculation failed.", type: "numerical_limit" },
      { field: "model_id", message: "Unknown.", type: null },
    ]);
    expect(issues.map((issue) => [issue.field, issue.code])).toEqual([
      ["hedge_ratio", "input_range"],
      [null, "numerical_limit"],
      ["model_id", "invalid"],
    ]);
    expect(Object.keys(issuesByField(issues))).toEqual(["hedge_ratio", "", "model_id"]);
  });

  it("states each input's allowed range", () => {
    const input = (id: string) => {
      const found = model.inputs.find((item) => item.id === id);
      if (!found) throw new Error(`No input ${id}`);
      return found;
    };
    expect(rangeText(input("crude_oil_change"))).toBe("above −100 %, up to 1,000 %");
    expect(rangeText(input("horizon_months"))).toBe("from 1 months, up to 36 months");
  });
});
