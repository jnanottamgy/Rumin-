import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ObservationPage } from "@/types/api";
import { failed, synthetic } from "../fixtures/data";
import { errorReply, mockApi } from "../utils/api";
import { renderRoute } from "../utils/render";

function mockSyntheticSeries() {
  return mockApi({
    "/api/v1/economic-series/demo-a": { body: synthetic.seriesDetail() },
    "/api/v1/economic-series/demo-a/observations": (request) => ({
      body: request.query.includes("include_revisions=true")
        ? synthetic.observationsWithRevisions()
        : synthetic.observations(),
    }),
    "/api/v1/data-quality/issues": { body: synthetic.seriesIssues() },
  });
}

describe("Economic series page", () => {
  it("labels the data honestly: historical, a sample, with flagged values", async () => {
    mockSyntheticSeries();
    renderRoute("/data/series/demo-a");

    expect(
      await screen.findByRole("heading", { level: 1, name: "SYNTHETIC series A (% change)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Historical · not live")).toBeInTheDocument();
    const header = screen.getByRole("heading", { level: 1 }).closest("header") as HTMLElement;
    expect(within(header).getByText("Sample data — not real")).toBeInTheDocument();
    expect(screen.getByText("1 flagged for review")).toBeInTheDocument();

    const freshness = screen.getByRole("group", { name: "How current this data is" });
    expect(within(freshness).getByText("2024")).toBeInTheDocument();
    expect(within(freshness).getByText(/as the provider reports it/)).toBeInTheDocument();
  });

  it("reads every value from the chart with the keyboard, gaps included", async () => {
    mockSyntheticSeries();
    const user = userEvent.setup();
    renderRoute("/data/series/demo-a");

    const chart = await screen.findByRole("slider", {
      name: "SYNTHETIC series A (% change): values by period",
    });
    // Before any interaction the chart reports the latest period with a value.
    expect(chart).toHaveAttribute("aria-valuetext", "2024 · % change on previous year: 2.915918.");
    chart.focus();
    await user.keyboard("{Home}");
    expect(chart.getAttribute("aria-valuetext")).toMatch(/^1990 · .*: 8\.470852\.$/);
    await user.keyboard("{End}");
    expect(chart).toHaveAttribute(
      "aria-valuetext",
      "2025 · % change on previous year: No value published.",
    );
    expect(screen.getByText(/No value published — shown as a gap/)).toBeInTheDocument();
    expect(screen.getByText("Flagged for review (stored as reported)")).toBeInTheDocument();
  });

  it("shows the exact published values in the table, and the revision history on request", async () => {
    const api = mockSyntheticSeries();
    const user = userEvent.setup();
    renderRoute("/data/series/demo-a");
    await screen.findByRole("slider");

    await user.click(screen.getByRole("button", { name: "Table" }));
    const table = await screen.findByRole("table", { name: /Every value exactly as the provider/ });
    const flagged = within(table).getByRole("rowheader", { name: "2009" }).closest("tr");
    expect(within(flagged as HTMLElement).getByText("14.250000")).toBeInTheDocument();
    expect(within(flagged as HTMLElement).getByText("Flagged for review")).toBeInTheDocument();
    const gap = within(table).getByRole("rowheader", { name: "2003" }).closest("tr");
    expect(within(gap as HTMLElement).getByText("No value published")).toBeInTheDocument();
    expect(within(table).getAllByRole("rowheader", { name: "2020" })).toHaveLength(1);

    await user.click(screen.getByRole("checkbox", { name: "Show revision history" }));
    const history = await screen.findByRole("table", { name: /Superseded revisions/ });
    expect(api.requests.some((request) => request.query.includes("include_revisions=true"))).toBe(
      true,
    );
    const revisions = within(history).getAllByRole("rowheader", { name: "2020" });
    expect(revisions).toHaveLength(2);
    expect(
      within(revisions[0]?.closest("tr") as HTMLElement).getByText(/superseded/),
    ).toBeInTheDocument();
    expect(
      within(revisions[1]?.closest("tr") as HTMLElement).getByText(/current/),
    ).toBeInTheDocument();
  });

  it("shows the source, licence, review range and quality issues", async () => {
    mockSyntheticSeries();
    renderRoute("/data/series/demo-a");
    const source = (await screen.findByRole("heading", { name: "Source and licence" })).closest(
      "section",
    ) as HTMLElement;
    expect(within(source).getByText("World Bank — Indicators API (v2)")).toBeInTheDocument();
    expect(within(source).getByText("None (synthetic)")).toBeInTheDocument();
    expect(
      within(source).getByText("Synthetic data generated for interface checks"),
    ).toBeInTheDocument();
    expect(within(source).getByText(/−50 to 12/)).toBeInTheDocument();
    expect(within(source).getByText(/RUMIN's assumption, not a fact/)).toBeInTheDocument();

    const quality = screen
      .getByRole("heading", { name: "Data quality" })
      .closest("section") as HTMLElement;
    expect(await within(quality).findByText("Outside review range")).toBeInTheDocument();
    expect(within(quality).getByText("Flagged")).toBeInTheDocument();
    expect(within(quality).getByText(/is outside RUMIN's review range/)).toBeInTheDocument();
  });

  it("explains a failed retrieval instead of showing an empty chart", async () => {
    const detail = failed.seriesDetail();
    const empty: ObservationPage = {
      items: [],
      total: 0,
      limit: 500,
      offset: 0,
      series: {
        id: detail.id,
        name: detail.name,
        unit: detail.unit,
        currency: detail.currency,
        frequency: detail.frequency,
        measure_type: detail.measure_type,
      },
      dataset: detail.dataset,
    };
    mockApi({
      [`/api/v1/economic-series/${detail.id}`]: { body: detail },
      [`/api/v1/economic-series/${detail.id}/observations`]: { body: empty },
      "/api/v1/data-quality/issues": { body: { items: [], total: 0, limit: 100, offset: 0 } },
    });
    renderRoute(`/data/series/${detail.id}`);

    expect(await screen.findByText(/^The last retrieval failed/)).toBeInTheDocument();
    expect(
      screen.getByText(/No values have been retrieved for this series yet\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See what happened" })).toHaveAttribute(
      "href",
      `/data/jobs/${detail.last_job?.id}`,
    );
    expect(screen.getByText("No values retrieved yet")).toBeInTheDocument();
    expect(await screen.findByText("No values stored for this series yet")).toBeInTheDocument();
    expect(
      await screen.findByText(/No values have been checked yet: no retrieval of this series/),
    ).toBeInTheDocument();
    // The related Phase 1 variable is linked, with how the two measures differ.
    expect(screen.getByRole("link", { name: "var_india_cpi_inflation" })).toBeInTheDocument();
    expect(screen.getByText(/not the same measure/)).toBeInTheDocument();
  });

  it("reports a series that does not exist", async () => {
    mockApi({
      "/api/v1/economic-series/nope-series": errorReply(
        404,
        "not_found",
        "No economic series with ID 'nope-series'.",
      ),
    });
    renderRoute("/data/series/nope-series");
    expect(await screen.findByText("This series does not exist")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
