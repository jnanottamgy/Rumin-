import { describe, expect, it } from "vitest";
import {
  networkFixture,
  scenarioFixture,
  scenarioPageFixture,
  systemFixture,
  variablesFixture,
} from "../fixtures";
import { intelligenceFixtures } from "../fixtures/intelligence";
import { labFixtures } from "../fixtures/lab";
import { simulationFixtures } from "../fixtures/simulation";
import { contractViolations } from "../integration/contract";

describe("the unit-test fixtures follow the committed OpenAPI contract", () => {
  it.each([
    ["NetworkResponse", networkFixture()],
    ["EconomicVariablePage", variablesFixture()],
    ["SystemStatus", systemFixture()],
    ["ScenarioRead", scenarioFixture()],
    ["ScenarioPage", scenarioPageFixture()],
  ])("%s", (schema, fixture) => {
    expect(contractViolations(schema, fixture)).toEqual([]);
  });
});

describe("the Scenario Lab fixtures follow the committed OpenAPI contract", () => {
  it.each([
    ["TemplateList", labFixtures.templates()],
    ["TemplateRead", labFixtures.template()],
    ["ScenarioRead", labFixtures.scenario()],
    ["ScenarioPage", labFixtures.scenarios()],
    ["ExecutionRead", labFixtures.execution()],
    ["ExecutionPage", labFixtures.executions()],
    ["ResultsRead", labFixtures.results()],
    ["LabPathwayRead", labFixtures.pathway()],
    ["LabExplanationRead", labFixtures.explanation()],
    ["LabSensitivityRead", labFixtures.sensitivity()],
    ["LabSensitivityList", labFixtures.sensitivityList()],
    ["AnalysisTargetsRead", labFixtures.analysisTargets()],
    ["ScenarioAnalysisRead", labFixtures.monteCarlo()],
    ["ScenarioAnalysisRead", labFixtures.joint()],
    ["ScenarioAnalysisList", labFixtures.analyses()],
    ["AnalysisVerificationRead", labFixtures.analysisVerification()],
    ...Object.values(labFixtures.modelVerification()).map(
      (register) => ["ModelVerificationRead", register] as [string, unknown],
    ),
    ["ExecutionVerificationRead", labFixtures.verification()],
    ["ComparisonRead", labFixtures.comparison()],
    ["PreviewRead", labFixtures.previewNeedsFigures()],
    ["PreviewRead", labFixtures.preview()],
  ])("%s", (schema, fixture) => {
    expect(contractViolations(schema, fixture)).toEqual([]);
  });

  it("SimulationModelDetail (the included models)", () => {
    const models = Object.values(labFixtures.models());
    expect(models.map((model) => model.id)).toEqual([
      "airline_fuel_cost",
      "fx_exposure",
      "floating_rate_interest",
    ]);
    for (const model of models) {
      expect(contractViolations("SimulationModelDetail", model)).toEqual([]);
    }
  });
});

describe("the simulation fixtures follow the committed OpenAPI contract", () => {
  it.each([
    ["SimulationModelDetail", simulationFixtures.model()],
    ["ValidationReport", simulationFixtures.validateValid()],
    ["ValidationReport", simulationFixtures.validateInvalid()],
    ["SimulationRunRead", simulationFixtures.run()],
    ["ExplanationRead", simulationFixtures.explanation()],
    ["ProvenanceRead", simulationFixtures.provenance()],
    ["VerificationRead", simulationFixtures.verify()],
    ["SensitivityAnalysisRead", simulationFixtures.sensitivity()],
    ["Page_SimulationRunSummary_", simulationFixtures.runs()],
    ["Page_NodeSearchResult_", simulationFixtures.airlines()],
  ])("%s", (schema, fixture) => {
    expect(contractViolations(schema, fixture)).toEqual([]);
  });

  it("SimulationModelSummary (the model list)", () => {
    const models = simulationFixtures.models();
    expect(models.length).toBeGreaterThan(0);
    for (const model of models) {
      expect(contractViolations("SimulationModelSummary", model)).toEqual([]);
    }
  });
});

describe("contractViolations", () => {
  it("reports missing fields, wrong types and values outside an enum", () => {
    const execution: Record<string, unknown> = {
      ...labFixtures.execution(),
      status: "exploded",
      version: "one",
    };
    delete execution.scenario_name;

    expect(contractViolations("ExecutionRead", execution)).toEqual(
      expect.arrayContaining([
        "$.scenario_name: required but missing",
        expect.stringMatching(/^\$\.status: "exploded" is not one of/),
        "$.version: expected an integer",
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

describe("the Financial Intelligence fixtures follow the committed OpenAPI contract", () => {
  it.each([
    ["MethodsRead", intelligenceFixtures.methods()],
    ["OverviewRead", intelligenceFixtures.overview()],
    ["OverviewRead", intelligenceFixtures.overviewUnsimulated()],
    ["OverviewRead", intelligenceFixtures.syntheticOverview()],
    ["EntityListRead", intelligenceFixtures.entities()],
    ["EntityAnalysisRead", intelligenceFixtures.entity()],
    ["EntityAnalysisRead", intelligenceFixtures.industry()],
    ["EntityAnalysisRead", intelligenceFixtures.syntheticEntity()],
    ["BriefRead", intelligenceFixtures.brief()],
    ["SeriesIntelligenceRead", intelligenceFixtures.syntheticSeries()],
    ["AnalysisRead", intelligenceFixtures.analysis()],
    ["AnalysisRead", intelligenceFixtures.syntheticStale()],
    ["Page_AnalysisSummaryRead_", intelligenceFixtures.analyses()],
    ["ErrorResponse", intelligenceFixtures.thresholdError()],
  ])("%s", (schema, fixture) => {
    expect(contractViolations(schema, fixture)).toEqual([]);
  });
});
