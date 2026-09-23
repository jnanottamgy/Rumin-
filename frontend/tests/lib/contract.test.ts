import { describe, expect, it } from "vitest";
import {
  networkFixture,
  scenarioFixture,
  scenarioPageFixture,
  systemFixture,
  variablesFixture,
} from "../fixtures";
import { contractViolations } from "../integration/contract";

describe("the unit-test fixtures follow the committed OpenAPI contract", () => {
  it.each([
    ["NetworkResponse", networkFixture()],
    ["EconomicVariablePage", variablesFixture()],
    ["SystemStatus", systemFixture()],
    ["ScenarioRead", scenarioFixture()],
    ["ScenarioPage", scenarioPageFixture([scenarioFixture()])],
  ])("%s", (schema, fixture) => {
    expect(contractViolations(schema, fixture)).toEqual([]);
  });
});

describe("contractViolations", () => {
  it("reports missing fields, wrong types and values outside an enum", () => {
    const scenario: Record<string, unknown> = { ...scenarioFixture(), status: "simulated" };
    delete scenario.name;
    scenario.shocks = [{ ...scenarioFixture().shocks[0], value: "30" }];

    expect(contractViolations("ScenarioRead", scenario)).toEqual(
      expect.arrayContaining([
        "$.name: required but missing",
        expect.stringMatching(/^\$\.status: "simulated" is not one of/),
        "$.shocks[0].value: expected a number",
      ]),
    );
  });

  it("checks nested unions such as the entity inside a network node", () => {
    const network = networkFixture();
    const node = network.nodes[0];
    if (!node) throw new Error("fixture has no nodes");
    (node.entity as unknown as Record<string, unknown>).kind = "planet";
    expect(contractViolations("NetworkResponse", network)).toEqual([
      "$.nodes[0].entity: matches none of the allowed shapes",
    ]);
  });
});
