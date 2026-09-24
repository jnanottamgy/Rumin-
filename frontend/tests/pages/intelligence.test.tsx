/**
 * Financial Intelligence, through the real route table, against a fake API answering with
 * fixtures captured from a running backend (`tests/fixtures/intelligence.ts`): the sample
 * network, the REFERENCE scenario on the fictional Aerisca Airways with HYPOTHETICAL figures,
 * and — in `synthetic-*` fixtures only — SYNTHETIC stored values.
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AERISCA, intelligenceFixtures, STORED_ID } from "../fixtures/intelligence";
import { errorReply, mockApi, unreachable } from "../utils/api";
import { renderRoute } from "../utils/render";

const ENTITY_PATH = `/api/v1/intelligence/entities/${encodeURIComponent(AERISCA)}`;
const DOSSIER = `/intelligence/${encodeURIComponent(AERISCA)}`;

function dossierRoutes(entity = intelligenceFixtures.entity()) {
  return {
    [ENTITY_PATH]: { body: entity },
    [`${ENTITY_PATH}/brief`]: { body: intelligenceFixtures.brief() },
  };
}

/** The workspace, once its analysis and its subjects have arrived. */
async function openWorkspace() {
  await screen.findByRole("heading", { level: 1, name: "Financial intelligence" });
  await screen.findByRole("list", { name: "Findings: Simulations" });
  await within(screen.getByRole("navigation", { name: "Subjects" })).findByRole("link", {
    name: /Aerisca Airways/,
  });
}

/** An entity's dossier, once its analysis has arrived. */
async function openDossier() {
  await screen.findByRole("heading", { level: 1, name: "Aerisca Airways" });
  await screen.findByRole("tablist", { name: "Dossier" });
}

describe("Financial intelligence — the workspace", () => {
  it("groups the findings and opens each into the evidence it rests on", async () => {
    mockApi();
    const user = userEvent.setup();
    renderRoute("/intelligence");
    await openWorkspace();

    expect(screen.getByText("12 of 12")).toBeInTheDocument();
    const simulations = screen.getByRole("list", { name: "Findings: Simulations" });
    const finding = within(simulations).getByRole("button", {
      name: /Profit before tax −6,700,000 INR \(−17\.63 %\)/,
    });
    expect(within(finding).getByText("Simulated")).toBeInTheDocument();
    expect(finding).toHaveAttribute("aria-expanded", "false");

    await user.click(finding);

    expect(finding).toHaveAttribute("aria-expanded", "true");
    const chain = screen.getByRole("list", { name: "Evidence chain" });
    expect(within(chain).getByText("Sets the grade")).toBeInTheDocument();
    expect(within(chain).getAllByText("Simulation").length).toBeGreaterThan(0);
    const block = chain.closest("div") as HTMLElement;
    expect(within(block).getByText(/Rests on stored model outputs/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Simulated under the scenario's changes, figures and assumptions: not a forecast.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What to investigate next" })).toBeInTheDocument();
  });

  it("filters by kind of knowledge and by evidence grade, never ranking findings", async () => {
    mockApi();
    const user = userEvent.setup();
    renderRoute("/intelligence");
    await openWorkspace();

    expect(screen.getByRole("radio", { name: /Observed data/ })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Coverage/ }));
    expect(screen.getByRole("list", { name: "Findings: Coverage" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Findings: Simulations" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /^All/ }));
    await user.selectOptions(screen.getByLabelText("Evidence at least"), "simulated");
    expect(screen.getByRole("list", { name: "Findings: Simulations" })).toBeInTheDocument();
    // Shared drivers rest on relationships recorded as model assumptions: weaker than simulated.
    expect(
      screen.queryByRole("list", { name: "Findings: Relationships and exposure" }),
    ).not.toBeInTheDocument();
  });

  it("reads the exposure map as text, cell by cell", async () => {
    mockApi();
    renderRoute("/intelligence");
    await openWorkspace();

    const matrix = screen.getByRole("table", {
      name: /Which economic variables reach which companies/,
    });
    expect(
      within(matrix).getByText(
        "Brent crude oil price reaches the costs of Aerisca Airways: upstream; 1 path; weakest evidence model assumption; simulatable by airline_fuel_cost.",
      ),
    ).toBeInTheDocument();
    expect(within(matrix).getByRole("link", { name: "Aerisca Airways" })).toHaveAttribute(
      "href",
      DOSSIER,
    );
    expect(screen.getByText(/No series or instrument has two or more stored values/)).toBeVisible();
    const impacts = screen.getByRole("heading", { name: "Simulated impacts" }).closest("section");
    expect(
      within(impacts as HTMLElement).getByText("−6,700,000 INR (−17.63 %)"),
    ).toBeInTheDocument();
  });

  it("puts thresholds in the request and shows a refusal beside its field", async () => {
    const api = mockApi({
      "/api/v1/intelligence/overview": (request) =>
        request.query.includes("relative_change_percent=0")
          ? { status: 422, body: intelligenceFixtures.thresholdError() }
          : { body: intelligenceFixtures.overview() },
    });
    const user = userEvent.setup();
    const { router } = renderRoute("/intelligence");
    await openWorkspace();

    await user.click(screen.getByText("Thresholds"));
    const field = screen.getByLabelText("Change in a level or exchange rate");
    await user.type(field, "0");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      await screen.findByText(
        "Change in a level or exchange rate must be between 0.1 and 100 (percent).",
      ),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe("?relative_change_percent=0");
    expect(
      api.requests.some(
        (request) =>
          request.path === "/api/v1/intelligence/overview" &&
          request.query === "?relative_change_percent=0",
      ),
    ).toBe(true);
    expect(screen.getByLabelText("Change in a level or exchange rate")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("reports an unreachable API with a retry", async () => {
    mockApi({ "/api/v1/intelligence/overview": unreachable });
    renderRoute("/intelligence");
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("Financial intelligence — an entity", () => {
  it("opens from the subjects and describes the entity without inventing anything", async () => {
    mockApi(dossierRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/intelligence");
    await openWorkspace();

    const subjects = screen.getByRole("navigation", { name: "Subjects" });
    await user.click(within(subjects).getByRole("link", { name: /Aerisca Airways/ }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Aerisca Airways" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(DOSSIER);
    expect(
      screen.getByText(
        "A company in Air transport, based in India; fictional, from RUMIN's sample network.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Findings (16)" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("shows exposure paths with the relationships and models behind them", async () => {
    mockApi(dossierRoutes());
    const user = userEvent.setup();
    renderRoute(DOSSIER);
    await openDossier();

    await user.click(screen.getByRole("tab", { name: "Exposure" }));

    const upstream = screen.getByRole("region", { name: "Upstream" });
    expect(within(upstream).getByText("U.S. effective federal funds rate")).toBeInTheDocument();
    expect(within(upstream).getByText("No registered model simulates it")).toBeInTheDocument();
    expect(screen.getAllByText("Supplied by")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Context, not exposure" })).toBeInTheDocument();
    expect(screen.getByText(/None of these exposures is evidence-backed/)).toBeInTheDocument();
  });

  it("shows the drivers as stored contributions, labelled as simulated", async () => {
    mockApi(dossierRoutes());
    const user = userEvent.setup();
    renderRoute(`${DOSSIER}?view=drivers`);
    await openDossier();

    expect(screen.getByText("Simulated, not a forecast")).toBeInTheDocument();
    expect(
      screen.getByText(/Floating-rate interest: the knowledge graph does not state this exposure/),
    ).toBeInTheDocument();
    const profit = screen.getByRole("table", { name: /^Profit before tax −6,700,000 INR/ });
    const brent = within(profit).getByRole("row", { name: /Brent crude oil price/ });
    expect(within(brent).getByText("−5,637,500 INR")).toBeInTheDocument();
    expect(within(brent).getByText("84.14 % of it")).toBeInTheDocument();
    expect(screen.getByText("−281,875 INR per 1 %")).toBeInTheDocument();
    expect(screen.getByText("300,000,000 INR per year")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Signals" }));
    const dependency = screen.getByRole("article", { name: "Dependency" });
    expect(within(dependency).getByText("Concentrated")).toBeInTheDocument();
  });

  it("lists every source and prepares the brief for a future analyst", async () => {
    mockApi(dossierRoutes());
    const user = userEvent.setup();
    renderRoute(`${DOSSIER}?view=sources`);
    await openDossier();

    expect(screen.getByRole("heading", { name: /Relationships read \(\d+\)/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Execution and model runs" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Brief" }));
    expect(
      await screen.findByRole("button", { name: "Download the brief (JSON)" }),
    ).toBeInTheDocument();
    const rules = screen.getByRole("region", { name: "Narration rules" });
    expect(within(rules).getByText(/never compute, extrapolate or round them/)).toBeInTheDocument();
  });

  it("keeps observed values and the model interpretation apart (synthetic values)", async () => {
    mockApi(dossierRoutes(intelligenceFixtures.syntheticEntity()));
    const user = userEvent.setup();
    renderRoute(DOSSIER);
    await openDossier();

    const observed = screen.getByRole("list", { name: "Findings: Observed data" });
    expect(within(observed).getByRole("button", { name: /rose 9\.38 %/ })).toHaveTextContent(
      "Observed",
    );
    const simulations = screen.getByRole("list", { name: "Findings: Simulations" });
    expect(
      within(simulations).getByRole("button", { name: /latest change, through/ }),
    ).toHaveTextContent("Model interpretation");

    await user.click(screen.getByRole("tab", { name: "History" }));
    expect(screen.getByRole("region", { name: "Observed data" })).toBeInTheDocument();
    const interpretation = screen.getByRole("region", { name: "Model interpretation" });
    expect(
      within(interpretation).getByText("Model interpretation, computed on request"),
    ).toBeInTheDocument();
    expect(
      within(interpretation).getByText("Not stored, not an observation, not a forecast"),
    ).toBeInTheDocument();
  });

  it("refuses a subject that is not an entity with the API's words", async () => {
    mockApi({
      "/api/v1/intelligence/entities/variable%3Avar_usd_inr": errorReply(
        422,
        "validation_error",
        "'variable:var_usd_inr' is an economic variable: intelligence is computed for companies and industries.",
      ),
    });
    renderRoute(`/intelligence/${encodeURIComponent("variable:var_usd_inr")}`);
    expect(await screen.findByRole("alert")).toHaveTextContent(/is an economic variable/);
  });
});

describe("Financial intelligence — stored analyses", () => {
  it("stores an analysis and later says what changed since", async () => {
    const api = mockApi({
      ...dossierRoutes(),
      "POST /api/v1/intelligence/analyses": { status: 201, body: intelligenceFixtures.analysis() },
      [`/api/v1/intelligence/analyses/${STORED_ID}`]: {
        body: intelligenceFixtures.syntheticStale(),
      },
    });
    const user = userEvent.setup();
    const { router } = renderRoute(DOSSIER);
    await openDossier();

    await user.click(screen.getByRole("button", { name: "Store this analysis" }));

    const link = await screen.findByRole("link", { name: "Open the stored analysis" });
    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: "/api/v1/intelligence/analyses",
        query: "",
        body: { scope: "entity", entity: AERISCA, thresholds: null, evidence: "any", label: null },
      },
    ]);

    await user.click(link);
    expect(router.state.location.pathname).toBe(`/intelligence/analyses/${STORED_ID}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Aerisca Airways, as stored" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Stale. Since it was stored, stored values changed.",
    );
    expect(screen.getByRole("link", { name: "The analysis now" })).toHaveAttribute("href", DOSSIER);
  });
});

describe("Overview dashboard — latest findings", () => {
  it("shows the first findings with their grade and links to the rest", async () => {
    mockApi();
    renderRoute("/dashboard");

    const latest = await screen.findByRole("list", { name: "Latest findings" });
    expect(within(latest).getAllByRole("listitem")).toHaveLength(4);
    expect(within(latest).getByText(/Profit before tax −6,700,000 INR/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /All 9 findings, with their evidence/ }),
    ).toHaveAttribute("href", "/intelligence");
  });
});
