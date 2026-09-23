/**
 * The Simulation preview, through the real route table, against a fake API answering
 * with fixtures captured from a running backend (hypothetical example inputs).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { RUN_ID, simulationFixtures, simulationPath } from "../fixtures/simulation";
import { errorReply, mockApi, type RecordedRequest, type Route } from "../utils/api";
import { matchingMediaQueries } from "../utils/browser";
import { renderRoute } from "../utils/render";

/** Every endpoint the page uses, answered from the fixtures. */
function simulationRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  let analyses = [] as ReturnType<typeof simulationFixtures.sensitivity>[];
  return {
    [simulationPath.models]: { body: simulationFixtures.models() },
    [simulationPath.model]: { body: simulationFixtures.model() },
    [simulationPath.airlines]: { body: simulationFixtures.airlines() },
    [simulationPath.runs]: { body: simulationFixtures.runs() },
    [`POST ${simulationPath.validate}`]: (request: RecordedRequest) => {
      const inputs = (request.body as { inputs: Record<string, { value?: string }> }).inputs;
      return {
        body:
          inputs.hedge_ratio?.value === "150"
            ? simulationFixtures.validateInvalid()
            : simulationFixtures.validateValid(),
      };
    },
    [`POST ${simulationPath.runs}`]: { status: 201, body: simulationFixtures.run() },
    [simulationPath.run(RUN_ID)]: { body: simulationFixtures.run() },
    [simulationPath.explanation(RUN_ID)]: { body: simulationFixtures.explanation() },
    [simulationPath.provenance(RUN_ID)]: { body: simulationFixtures.provenance() },
    [`POST ${simulationPath.verify(RUN_ID)}`]: { body: simulationFixtures.verify() },
    [simulationPath.sensitivity(RUN_ID)]: () => ({ body: { items: analyses } }),
    [`POST ${simulationPath.sensitivity(RUN_ID)}`]: () => {
      analyses = [simulationFixtures.sensitivity()];
      return { status: 201, body: analyses[0] };
    },
    ...overrides,
  };
}

async function openNew() {
  const view = renderRoute("/simulation");
  await screen.findByRole("heading", { level: 2, name: "Airline fuel-cost shock" });
  return view;
}

async function openRun() {
  const view = renderRoute(`/simulation/runs/${RUN_ID}`);
  await screen.findByRole("heading", { level: 2, name: "Example: crude +10 %" });
  return view;
}

describe("Simulation preview", () => {
  it("opens on the model: how a change travels, the labels and the assumptions", async () => {
    mockApi(
      simulationRoutes({
        [simulationPath.runs]: { body: { items: [], total: 0, limit: 10, offset: 0 } },
      }),
    );
    const { container } = await openNew();

    expect(screen.getByRole("heading", { level: 1, name: "Simulation" })).toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toHaveValue("airline_fuel_cost");
    expect(
      screen.getByText(/The knowledge graph \(build #4\) confirms the relationships/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "How a change travels through this model" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("[data-node-id]")).toHaveLength(10);
    expect(screen.getAllByText("Historical data").length).toBeGreaterThan(0);
    expect(screen.getByText(/Everything the model does not include stays at its baseline/));
    expect(await screen.findByText("No stored runs yet")).toBeInTheDocument();
  });

  it("checks inputs on the server and shows each problem beside its field", async () => {
    const api = mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openNew();

    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.click(screen.getByText("Assumptions", { selector: "summary *, summary" }));
    await user.clear(screen.getByLabelText("Hedge ratio"));
    await user.type(screen.getByLabelText("Hedge ratio"), "150");
    await user.clear(screen.getByLabelText("Annual revenue"));
    await user.click(screen.getByRole("button", { name: "Check inputs" }));

    const summary = await screen.findByRole("alert");
    expect(within(summary).getByText("2 inputs need attention")).toBeInTheDocument();
    const link = within(summary).getByRole("link", { name: "Hedge ratio must be at most 100 %." });
    expect(link).toHaveAttribute("href", "#simulation-input-hedge_ratio");
    expect(screen.getByLabelText("Hedge ratio")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Annual revenue")).toHaveAttribute("aria-invalid", "true");

    const [check] = api.writes();
    expect(check?.path).toBe(simulationPath.validate);
    expect(check?.body).toMatchObject({
      model_id: "airline_fuel_cost",
      inputs: {
        crude_oil_change: { value: "10" },
        jet_fuel_price: { value: "750", unit: "usd_per_kilolitre" },
        hedge_ratio: { value: "150" },
      },
    });
    const sent = check?.body as { inputs: Record<string, unknown> } | undefined;
    expect(sent?.inputs).not.toHaveProperty("annual_revenue");
  });

  it("says when the inputs are valid, with the engine's notes", async () => {
    mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openNew();

    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.click(screen.getByRole("button", { name: "Check inputs" }));

    expect(await screen.findByText("The inputs are valid")).toBeInTheDocument();
    expect(screen.getByText(/Rule T1 follows a relationship the knowledge graph records/));
    expect(screen.getByText(/Hypothetical figures, not data/)).toBeInTheDocument();
  });

  it("runs the model and opens the stored run with its headline results", async () => {
    const api = mockApi(simulationRoutes());
    const user = userEvent.setup();
    const { router } = await openNew();

    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.type(screen.getByLabelText(/Name this run/), "Example: crude +10 %");
    await user.click(screen.getByRole("button", { name: "Run simulation" }));

    await screen.findByRole("heading", { level: 2, name: "Example: crude +10 %" });
    expect(router.state.location.pathname).toBe(`/simulation/runs/${RUN_ID}`);
    const [run] = api.writes();
    expect(run?.body).toMatchObject({ label: "Example: crude +10 %" });

    // Headline figures, exactly as the engine returned them (rounded for display).
    expect(screen.getByText("−3,550,000")).toBeInTheDocument();
    expect(screen.getByText("+5,250,000")).toBeInTheDocument();
    expect(screen.getByText("−1.27")).toBeInTheDocument();
    expect(screen.getByText(/not a forecast and not investment advice/)).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Baseline and scenario" });
    const profit = within(table).getByRole("row", { name: /Operating profit/ });
    expect(within(profit).getByText("50,000,000 INR")).toBeInTheDocument();
    expect(within(profit).getByText("46,450,000 INR")).toBeInTheDocument();

    // The bridge closes: each step and the total, as text.
    const bridge = screen.getByRole("table", { name: /Bridge from the fuel-cost change/ });
    expect(within(bridge).getByText("+750,000 INR")).toBeInTheDocument();
    expect(within(bridge).getByText("+1,700,000 INR")).toBeInTheDocument();

    // Month by month, readable from the keyboard.
    const months = screen.getByRole("slider", { name: "Monthly results" });
    months.focus();
    await user.keyboard("{Home}");
    expect(months.getAttribute("aria-valuetext")).toMatch(
      /^Month 1: .*Scenario fuel cost 5,250,000 INR per month/,
    );
    expect(api.writes().every((request) => request.method === "POST")).toBe(true);
  });

  it("shows why a refused run was refused", async () => {
    mockApi(
      simulationRoutes({
        [`POST ${simulationPath.runs}`]: {
          status: 422,
          body: simulationFixtures.runRefused(),
        },
      }),
    );
    const user = userEvent.setup();
    const { router } = await openNew();

    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.click(screen.getByRole("button", { name: "Run simulation" }));

    expect(await screen.findByText("2 inputs need attention")).toBeInTheDocument();
    expect(screen.getByLabelText("Annual revenue")).toHaveAttribute("aria-invalid", "true");
    expect(router.state.location.pathname).toBe("/simulation");
  });

  it("loads a stored run's inputs into the form so it can be varied", async () => {
    mockApi(simulationRoutes());
    await openRun();

    expect(screen.getByLabelText("Crude oil price change")).toHaveValue("10");
    expect(screen.getByLabelText("Annual revenue")).toHaveValue("300000000");
    expect(screen.getByLabelText("Crude-to-jet-fuel elasticity (β)")).toHaveValue(""); // default
    const current = await screen.findByRole("row", { current: true });
    expect(within(current).getByRole("link")).toHaveAttribute("href", `/simulation/runs/${RUN_ID}`);
  });

  it("draws the pathway with the graph relationship it used", async () => {
    mockApi(simulationRoutes());
    const { container } = await openRun();

    await waitFor(() => expect(container.querySelector("[data-rule='T1']")).not.toBeNull());
    const tag = screen.getByRole("link", { name: "Knowledge-graph relationship: β = 1, no lag" });
    expect(tag).toHaveAttribute(
      "href",
      "/graph?from=variable%3Avar_brent_crude&to=variable%3Avar_jet_fuel",
    );
    const fuel = container.querySelector("[data-node-id='output:fuel_cost_change']");
    expect(fuel?.textContent).toContain("+5.25 million INR");
    // Opened, not freshly run: nothing moves.
    expect(container.querySelector("animateMotion")).toBeNull();

    await userEvent.setup().click(screen.getByRole("button", { name: "List" }));
    expect(screen.getByText(/Open in the graph/)).toBeInTheDocument();
  });

  it("animates a new run's pathway once, and never under reduced motion", async () => {
    mockApi(simulationRoutes());
    const user = userEvent.setup();
    const { container, unmount } = await openNew();
    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.click(screen.getByRole("button", { name: "Run simulation" }));
    await waitFor(() => expect(container.querySelector("animateMotion")).not.toBeNull());
    unmount();

    matchingMediaQueries.add("(prefers-reduced-motion: reduce)");
    mockApi(simulationRoutes());
    const reduced = await openNew();
    await user.click(screen.getByRole("button", { name: "Fill a hypothetical example" }));
    await user.click(screen.getByRole("button", { name: "Run simulation" }));
    await waitFor(() => expect(reduced.container.querySelector("[data-rule='T1']")).not.toBeNull());
    expect(reduced.container.querySelector("animateMotion")).toBeNull();
  });

  it("explains the calculation step by step, month by month", async () => {
    mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openRun();

    await user.click(screen.getByRole("tab", { name: "Calculation" }));
    const steps = await screen.findByRole("table", { name: /Calculation steps for the whole run/ });
    expect(
      within(steps).getByText(/Change in operating profit over the horizon/),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Steps for"), "4");
    const month = screen.getByRole("table", { name: "Calculation steps for month 4" });
    const equations = within(month)
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent?.split(" ")[0]);
    expect(equations).toEqual(["E6", "E7", "E9", "E10", "E11", "E12", "E13"]);
    expect(screen.getByRole("heading", { name: "Fare recovery" })).toBeInTheDocument();
  });

  it("shows provenance and checks reproducibility on the server", async () => {
    const api = mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openRun();

    await user.click(screen.getByRole("tab", { name: "Provenance" }));
    expect(await screen.findByText("None: the calculation is deterministic")).toBeInTheDocument();
    expect(screen.getByText("Build #4, current at the time")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "e-ea305310288a3f88" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Check reproducibility" }));
    expect(await screen.findByText("Reproduced exactly")).toBeInTheDocument();
    expect(api.writes().map((request) => request.path)).toEqual([simulationPath.verify(RUN_ID)]);
  });

  it("labels every input by the kind of knowledge it is", async () => {
    mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openRun();

    await user.click(screen.getByRole("tab", { name: "Inputs and assumptions" }));
    const inputs = await screen.findByRole("table", { name: "Inputs used by this run" });
    const row = (label: string) => within(inputs).getByRole("row", { name: new RegExp(label) });
    expect(within(row("Crude oil price change")).getByText("Scenario change")).toBeInTheDocument();
    expect(within(row("Annual revenue")).getByText("Your figure")).toBeInTheDocument();
    expect(within(row("Hedge ratio")).getByText("Assumption")).toBeInTheDocument();
    expect(within(row("Horizon")).getByText("Model default")).toBeInTheDocument();
    expect(await screen.findAllByText("Changed from the default")).not.toHaveLength(0);
  });

  it("runs a sensitivity analysis and ranks the inputs by their effect", async () => {
    const api = mockApi(simulationRoutes());
    const user = userEvent.setup();
    await openRun();

    await user.click(screen.getByRole("tab", { name: "Sensitivity" }));
    expect(await screen.findByText("No analysis for this result yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run the analysis" }));

    const tornado = await screen.findByRole("table", {
      name: /Sensitivity of Change in operating profit/,
    });
    const rows = within(tornado).getAllByRole("rowheader");
    expect(rows[0]?.textContent).toMatch(/^Crude oil price change/);
    expect(rows).toHaveLength(7);
    expect(api.writes()[0]?.body).toEqual({ metric: "operating_profit_change", inputs: [] });
  });

  it("explains a run that cannot be opened", async () => {
    mockApi(
      simulationRoutes({
        [simulationPath.run(RUN_ID)]: errorReply(404, "not_found", "No simulation run."),
      }),
    );
    renderRoute(`/simulation/runs/${RUN_ID}`);
    expect(await screen.findByText("This run could not be opened")).toBeInTheDocument();
    expect(screen.getByText("No simulation run.")).toBeInTheDocument();
  });
});
