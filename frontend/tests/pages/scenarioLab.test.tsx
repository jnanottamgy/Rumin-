/**
 * The Scenario Lab, through the real route table, against a fake API answering with
 * fixtures captured from a running backend (the reference scenario's HYPOTHETICAL figures;
 * see `fixtures/lab.ts`).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { EXECUTION_ID, labFixtures, SCENARIO_ID } from "../fixtures/lab";
import { simulationFixtures } from "../fixtures/simulation";
import { errorReply, mockApi, type RecordedRequest, type Route, unreachable } from "../utils/api";
import { renderRoute } from "../utils/render";

const execution = (id: string) => `/api/v1/scenario-executions/${id}`;
const PREVIEW = "POST /api/v1/scenarios/preview";

/** Every endpoint the Lab uses, answered from the fixtures. */
function labRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  let analyses = [] as ReturnType<typeof labFixtures.sensitivity>[];
  const models = Object.entries(labFixtures.models()).map(
    ([id, model]) => [`/api/v1/simulation-models/${id}`, { body: model }] as const,
  );
  return {
    "/api/v1/scenario-templates": { body: labFixtures.templates() },
    "/api/v1/scenario-templates/crude_oil_airline": { body: labFixtures.template() },
    "/api/v1/scenarios": { body: labFixtures.scenarios() },
    [`/api/v1/scenarios/${SCENARIO_ID}`]: { body: labFixtures.scenario() },
    [`/api/v1/scenarios/${SCENARIO_ID}/executions`]: { body: labFixtures.executions() },
    [PREVIEW]: { body: labFixtures.preview() },
    [execution(EXECUTION_ID)]: { body: labFixtures.execution() },
    [`${execution(EXECUTION_ID)}/results`]: { body: labFixtures.results() },
    [`${execution(EXECUTION_ID)}/pathways`]: { body: labFixtures.pathway() },
    [`${execution(EXECUTION_ID)}/explanation`]: { body: labFixtures.explanation() },
    [`${execution(EXECUTION_ID)}/sensitivity`]: () => ({ body: { items: analyses } }),
    [`POST ${execution(EXECUTION_ID)}/sensitivity`]: () => {
      analyses = [labFixtures.sensitivity()];
      return { status: 201, body: analyses[0] };
    },
    [`POST ${execution(EXECUTION_ID)}/verify`]: { body: labFixtures.verification() },
    "/api/v1/scenario-comparisons": { body: labFixtures.comparison() },
    "/api/v1/graph/nodes": { body: simulationFixtures.airlines() },
    ...Object.fromEntries(models),
    ...overrides,
  };
}

async function openSaved(path = `/scenarios/${SCENARIO_ID}`) {
  const view = renderRoute(path);
  await screen.findByText(/^Showing stored execution · v1/);
  await screen.findByRole("tablist", { name: "Scenario views" });
  return view;
}

const results = () => within(screen.getByRole("complementary", { name: "Results" }));
const inspector = () => within(screen.getByRole("complementary", { name: "Pathway details" }));

describe("Scenario Lab — home", () => {
  it("offers templates built on implemented models, says which are not offered, and lists the library", async () => {
    mockApi(labRoutes());
    renderRoute("/scenarios");

    expect(
      await screen.findByRole("heading", { level: 1, name: "What happens if something changes?" }),
    ).toBeInTheDocument();

    const airline = (await screen.findByRole("heading", { name: "Crude oil shock on an airline" }))
      .parentElement as HTMLElement;
    // Names and units come from the variables the API publishes.
    expect(within(airline).getByText("Brent crude oil price +20 %")).toBeInTheDocument();
    expect(within(airline).getByText("Airline fuel cost v1.1.0")).toBeInTheDocument();
    expect(within(airline).getByRole("link", { name: /Start from this template/ })).toHaveAttribute(
      "href",
      "/scenarios/new?template=crude_oil_airline",
    );
    const rates = screen.getByRole("heading", { name: "Policy-rate rise" })
      .parentElement as HTMLElement;
    expect(within(rates).getByText("RBI policy repo rate +1.5 pp")).toBeInTheDocument();

    const notOffered = screen.getByRole("list", { name: "Templates not offered" });
    expect(within(notOffered).getByText("Demand shock.")).toBeInTheDocument();
    expect(
      within(notOffered).getByText(/No registered model simulates volumes/),
    ).toBeInTheDocument();

    const saved = await screen.findByRole("link", { name: "Oil, rupee and rates on Aerisca" });
    expect(saved).toHaveAttribute("href", `/scenarios/${SCENARIO_ID}`);
    const row = saved.closest("tr") as HTMLElement;
    expect(
      within(row).getByText(
        "Brent crude oil price +20 % · USD/INR exchange rate +5 % · RBI policy repo rate +0.5 pp",
      ),
    ).toBeInTheDocument();
    expect(within(row).getByText(/Profit before tax: −6\.7 M INR/)).toBeInTheDocument();
  });

  it("compares the latest executions of two saved scenarios side by side, without ranking them", async () => {
    const api = mockApi(labRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/scenarios");
    await screen.findByRole("link", { name: "Oil, rupee and rates on Aerisca" });

    const compare = screen.getByRole("button", { name: /^Compare\s+executions$/ });
    expect(compare).toBeDisabled();
    const scenarios = labFixtures.scenarios().items;
    for (const scenario of scenarios) {
      await user.click(
        screen.getByRole("checkbox", { name: `Compare the latest execution of ${scenario.name}` }),
      );
    }
    await user.click(screen.getByRole("button", { name: "Compare 2 executions" }));

    expect(router.state.location.pathname).toBe("/scenarios/compare");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Compare executions" }),
    ).toBeInTheDocument();
    const pbt = (await screen.findByRole("rowheader", { name: "Profit before tax" })).closest(
      "tr",
    ) as HTMLElement;
    expect(within(pbt).getByText(/^−6\.7 M/)).toBeInTheDocument();
    // Oil alone includes no interest model: its profit before tax is not modelled, not zero.
    expect(within(pbt).getByText("Not modelled")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is ranked or recommended/)).toBeInTheDocument();

    const request = api.requests.find((item) => item.path === "/api/v1/scenario-comparisons");
    const ids = new URLSearchParams(request?.query).getAll("execution_id");
    expect(ids.sort()).toEqual(
      scenarios.map((scenario) => scenario.latest_execution?.id as string).sort(),
    );
  });
});

describe("Scenario Lab — a saved scenario", () => {
  it("opens on its stored execution: the headline, baseline against scenario, and what is not modelled", async () => {
    const api = mockApi(labRoutes());
    await openSaved();

    const hero = await results().findByRole("region", { name: "Headline result" });
    expect(hero).toHaveTextContent("Change in profit before tax");
    expect(hero).toHaveTextContent("−6.7 MINR");
    expect(hero).toHaveTextContent("Stored execution");

    const pbt = results()
      .getByRole("rowheader", { name: /Profit before tax/ })
      .closest("tr") as HTMLElement;
    expect(within(pbt).getByText("38 M")).toBeInTheDocument();
    expect(within(pbt).getByText("31.3 M")).toBeInTheDocument();
    expect(pbt).toHaveTextContent("−6.7 M");
    expect(pbt).toHaveTextContent("−17.63 %");
    expect(pbt).toHaveTextContent("reduces profit");
    // Cash flow is never invented.
    expect(results().getByText("Cash flow")).toBeInTheDocument();

    expect(
      screen.getByText(/^Completed in .* · version 1 · stored and reproducible$/),
    ).toBeInTheDocument();
    // A completed execution can be laid over the knowledge graph in the 3D universe.
    expect(screen.getByRole("link", { name: "See it in the 3D universe" })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/universe\/3d\?execution=[\w-]+$/),
    );
    // Reading a saved scenario writes nothing: the only POST is the (unstored) preview.
    await waitFor(() => expect(api.writes().length).toBeGreaterThan(0));
    expect(new Set(api.writes().map((request) => request.path))).toEqual(
      new Set(["/api/v1/scenarios/preview"]),
    );
  });

  it("draws the pathway the engine computed and lists graph context apart, as context", async () => {
    mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();

    // A change, the variable the model moved, its line item and the line it reaches.
    expect(await screen.findByTitle("Brent crude oil price · your change")).toBeInTheDocument();
    expect(
      screen.getByTitle("Jet fuel price (U.S. Gulf Coast) · Airline fuel cost"),
    ).toHaveTextContent("β 1 · lag 1");
    expect(screen.getByTitle("Jet fuel · Airline fuel cost")).toHaveTextContent("+12.45 M");
    expect(screen.getByTitle("Profit before tax")).toHaveTextContent("−6.7 M");
    // Graph context is not a step of the pathway: no value travels along it.
    expect(screen.queryByTitle("Air transport")).toBeNull();

    await user.click(screen.getAllByRole("button", { name: /Why it applies/ })[0] as HTMLElement);
    expect(inspector().getByText("Why this model applies")).toBeInTheDocument();
    expect(inspector().getByText(/not evidence of\s+causation/)).toBeInTheDocument();
    expect(
      inspector().getByText("Jet fuel price (U.S. Gulf Coast) affects costs of Air transport"),
    ).toBeInTheDocument();
    expect(inspector().getByText("Aerisca Airways operates in Air transport")).toBeInTheDocument();

    // A step, then the relationship it came along.
    await user.click(screen.getByTitle("Jet fuel price (U.S. Gulf Coast) · Airline fuel cost"));
    expect(inspector().getByText("Variable moved by a model")).toBeInTheDocument();
    await user.click(
      inspector().getByRole("button", { name: /Brent crude oil price · Airline fuel cost/ }),
    );
    expect(inspector().getByText("Propagated along a graph relationship")).toBeInTheDocument();
    expect(inspector().getByText("Model assumption")).toBeInTheDocument();
    expect(inspector().getByText("1 month")).toBeInTheDocument();
    expect(inspector().getByText(/Illustrative sample data/)).toBeInTheDocument();
    expect(inspector().getByText("E6")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Pathway details" })).toBeNull();

    // What the graph states but no model simulates is listed apart.
    const pathway = labFixtures.pathway();
    await user.click(
      screen.getByRole("button", {
        name: `Stated in the graph, not modelled (${pathway.unmodelled.length})`,
      }),
    );
    expect(screen.getByText(/nothing is computed along them/)).toBeInTheDocument();

    // The same links as a table.
    await user.click(screen.getByRole("button", { name: "List" }));
    const table = screen.getByRole("table", { name: "Every link of the pathway" });
    expect(within(table).getAllByText("Cited: affects costs of").length).toBeGreaterThan(0);
  });

  it("replays the simulated months: each step shows its value in that month", async () => {
    mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();
    await screen.findByTitle("Profit before tax");

    await user.click(screen.getByRole("button", { name: /^M3/ }));
    expect(
      screen.getByText("Month 3 of 12: −655 K profit before tax — simulated"),
    ).toBeInTheDocument();
    expect(screen.getByTitle("Profit before tax")).toHaveTextContent("−655 K");
    // Repo-linked loans reprice in month 4: interest has not moved yet.
    expect(screen.getByTitle("Interest expense")).toHaveAttribute("data-dimmed", "true");
    // Metrics are computed over the horizon: they have no value in a month.
    expect(screen.getByTitle("Operating margin")).toHaveTextContent("Horizon only");

    await user.click(screen.getByRole("button", { name: "Show totals over the horizon" }));
    expect(screen.getByText("Totals over the horizon")).toBeInTheDocument();
    expect(screen.getByTitle("Profit before tax")).toHaveTextContent("−6.7 M");
  });

  it("shows the plan, the months, the stress cases and the explanation from the execution", async () => {
    const api = mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();

    await user.click(screen.getByRole("tab", { name: "Plan" }));
    expect(screen.getByText("Ready to execute")).toBeInTheDocument();
    expect(screen.getByText("Every model, and why")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Months" }));
    const months = screen.getByRole("table", { name: /Change in each line by simulated month/ });
    const third = within(months).getByRole("rowheader", { name: "3" }).closest("tr") as HTMLElement;
    expect(within(third).getAllByText("−655 K")).toHaveLength(2); // operating profit, PBT
    expect(
      within(months).getByText("Month 2: The crude oil change reaches jet fuel (1-month lag)"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Stress" }));
    const stress = screen.getByRole("table", { name: /Change over the horizon in each line/ });
    const half = within(stress)
      .getByRole("rowheader", { name: "Half" })
      .closest("tr") as HTMLElement;
    expect(within(half).getByText("Scaled × 0.5")).toBeInTheDocument();
    expect(within(half).getByText("+10 %")).toBeInTheDocument();
    expect(within(half).getByText("+0.25 pp")).toBeInTheDocument();
    expect(within(half).getByText("−3.28 M")).toBeInTheDocument();
    expect(screen.getByText(/Not ranked/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Explain" }));
    const explain = within(screen.getByRole("tabpanel"));
    expect(await explain.findByText("Contribution of each change")).toBeInTheDocument();
    // The model's own title, its inputs worded as a reader expects them.
    expect(explain.getByText("Airline fuel cost")).toBeInTheDocument();
    expect(explain.getAllByText("to the end of the horizon").length).toBeGreaterThan(0);
    expect(explain.getAllByText("Aerisca Airways").length).toBeGreaterThan(0);
    const asked = api.requests.find((request) => request.path.endsWith("/explanation"));
    expect(asked?.query).toBe("?target=profit_before_tax");
  });

  it("runs a one-at-a-time sensitivity analysis and says it is not a probability", async () => {
    const api = mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();

    await user.click(screen.getByRole("tab", { name: "Sensitivity" }));
    expect(await screen.findByText("No analysis yet for this execution.")).toBeInTheDocument();
    expect(screen.getByText(/no Monte Carlo simulation is run/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run the analysis" }));
    expect(await screen.findByText("Crude oil price change")).toBeInTheDocument();
    expect(screen.getByText(/10 \/ 30 % · base 20 %/)).toBeInTheDocument();
    const posted = api.writes().find((request) => request.path.endsWith("/sensitivity"));
    expect(posted?.body).toEqual({ metric: null, inputs: [] });
  });

  it("verifies that an execution reproduces", async () => {
    mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();

    await user.click(screen.getByRole("tab", { name: "History" }));
    expect(screen.getByText(/1 execution ·/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(
      await screen.findByText(
        /Re-executed from the stored runs and recombined: identical results\./,
      ),
    ).toBeInTheDocument();
  });

  it("previews an edit on the server, marked as a preview, before anything is saved", async () => {
    const api = mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();
    await waitFor(() => expect(api.writes().length).toBe(1));

    const magnitude = screen.getByRole("textbox", { name: "Magnitude of change 1" });
    await user.clear(magnitude);
    await user.type(magnitude, "25");

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save and execute" })).toBeEnabled();
    await waitFor(() => {
      const last = api.writes().at(-1) as RecordedRequest;
      expect((last.body as { shocks: { value: string }[] }).shocks[0]?.value).toBe("25");
    });
    expect(await screen.findByText("Live preview · computed, not stored")).toBeInTheDocument();
    expect(results().getByText("Live preview — not stored")).toBeInTheDocument();
    // Previews are computed, never stored.
    expect(api.writes().every((request) => request.path === "/api/v1/scenarios/preview")).toBe(
      true,
    );
  });

  it("discards unsaved edits and returns to the saved version", async () => {
    const api = mockApi(labRoutes());
    const user = userEvent.setup();
    await openSaved();
    expect(screen.queryByRole("button", { name: "Discard changes" })).toBeNull();

    const magnitude = screen.getByRole("textbox", { name: "Magnitude of change 1" });
    await user.clear(magnitude);
    await user.type(magnitude, "35");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.getByRole("textbox", { name: "Magnitude of change 1" })).toHaveValue("20");
    expect(screen.queryByText("Unsaved changes")).toBeNull();
    expect(screen.getByText("Unsaved changes discarded.")).toBeInTheDocument();
    expect(await screen.findByText(/^Showing stored execution · v1/)).toBeInTheDocument();
    // Nothing was saved: only previews were asked for.
    expect(api.writes().every((request) => request.path === "/api/v1/scenarios/preview")).toBe(
      true,
    );
  });

  it("follows an execution through the stages the server reports until it is final", async () => {
    const NEW_ID = "00000000-0000-4000-8000-000000000001";
    const stored = labFixtures.execution();
    const queued = {
      ...stored,
      id: NEW_ID,
      status: "queued",
      started_at: null,
      finished_at: null,
      duration_ms: null,
      stages: [],
      results_available: false,
      poll_after_ms: 100,
    };
    const polls: string[] = [];
    // The server keeps the execution in "simulating" until the test lets it finish.
    let finished = false;
    const api = mockApi(
      labRoutes({
        [`POST /api/v1/scenarios/${SCENARIO_ID}/executions`]: { status: 202, body: queued },
        [execution(NEW_ID)]: () => {
          polls.push(NEW_ID);
          return finished
            ? { body: { ...stored, id: NEW_ID } }
            : { body: { ...queued, status: "simulating", stages: stored.stages.slice(0, 1) } };
        },
        [`${execution(NEW_ID)}/results`]: {
          body: { ...labFixtures.results(), execution_id: NEW_ID },
        },
        [`${execution(NEW_ID)}/pathways`]: { body: labFixtures.pathway() },
      }),
    );
    const user = userEvent.setup();
    const { router } = await openSaved();

    await user.click(screen.getByRole("button", { name: "Execute" }));
    expect(await screen.findByText("Simulating — as reported by the server")).toBeInTheDocument();
    // Still running: the page keeps asking at the interval the server set.
    await waitFor(() => expect(polls.length).toBeGreaterThan(2));
    finished = true;
    expect(
      await screen.findByText(/^Completed in .* · version 1 · stored and reproducible$/),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?execution=${NEW_ID}`);
    expect(api.writes().some((request) => request.path.endsWith("/executions"))).toBe(true);
    // Final means final: polling stops (checked over more than two polling intervals).
    const seen = polls.length;
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(polls.length).toBe(seen);
  });

  it("says why an execution failed", async () => {
    const failed = {
      ...labFixtures.execution(),
      status: "failed",
      results_available: false,
      error: { code: "timeout", message: "The execution exceeded 20 seconds." },
    };
    mockApi(labRoutes({ [execution(EXECUTION_ID)]: { body: failed } }));
    renderRoute(`/scenarios/${SCENARIO_ID}?execution=${EXECUTION_ID}`);

    expect(
      await screen.findByText("Failed: The execution exceeded 20 seconds."),
    ).toBeInTheDocument();
  });

  it("reports a scenario that does not exist, and an unreachable API", async () => {
    mockApi(
      labRoutes({
        [`/api/v1/scenarios/${SCENARIO_ID}`]: errorReply(404, "not_found", "No such scenario."),
      }),
    );
    const first = renderRoute(`/scenarios/${SCENARIO_ID}`);
    expect(await screen.findByText("This scenario does not exist")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the library" })).toHaveAttribute(
      "href",
      "/scenarios",
    );
    first.unmount();

    mockApi(labRoutes({ [`/api/v1/scenarios/${SCENARIO_ID}`]: unreachable }));
    renderRoute(`/scenarios/${SCENARIO_ID}`);
    expect(await screen.findByText(/Could not reach the RUMIN API/)).toBeInTheDocument();
  });
});

describe("Scenario Lab — starting from a template", () => {
  it("opens an unsaved draft whose missing figures are notes until you try to save", async () => {
    const api = mockApi(
      labRoutes({
        [PREVIEW]: { body: labFixtures.previewNeedsFigures() },
        "POST /api/v1/scenarios": errorReply(
          422,
          "validation_error",
          "The request contains invalid values.",
          [
            {
              location: "body",
              field: "company.reporting_currency",
              message: "Reporting currency is required.",
              type: "missing",
            },
          ],
        ),
      }),
    );
    const user = userEvent.setup();
    renderRoute("/scenarios/new?template=crude_oil_airline");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Crude oil shock on an airline" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    expect(screen.getByText("From template: Crude oil shock on an airline")).toBeInTheDocument();

    // The template's change is sent to the backend for a plan and a preview.
    await waitFor(() => expect(api.writes().length).toBe(1));
    expect(api.writes()[0]?.body).toMatchObject({
      template_id: "crude_oil_airline",
      shocks: [{ variable_id: "var_brent_crude", change_type: "percent_change", value: "20" }],
    });

    const currency = screen.getByLabelText("Reporting currency");
    const note = await screen.findAllByText("Reporting currency is required.");
    expect(note[0]?.closest("li")).toHaveAttribute("data-severity", "needed");
    expect(currency).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByRole("button", { name: "Save and execute" })).toBeDisabled();
    expect(
      screen.getByText("The plan lists what is missing before the scenario can run."),
    ).toBeInTheDocument();
    // Nothing is computed that the models cannot support.
    expect(screen.getByText("The pathway needs a runnable scenario")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save scenario" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Reporting currency")).toHaveAttribute("aria-invalid", "true"),
    );
    const errors = screen.getAllByText("Reporting currency is required.");
    expect(errors.every((item) => item.closest("li")?.dataset.severity === "error")).toBe(true);
  });
});
