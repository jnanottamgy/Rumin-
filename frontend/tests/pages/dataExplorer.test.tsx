import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failed, synthetic } from "../fixtures/data";
import { mockApi } from "../utils/api";
import { renderRoute } from "../utils/render";

const statValue = (label: string) =>
  screen.getByText(label, { selector: "dt" }).nextElementSibling?.textContent;

function mockFailedWorkspace() {
  return mockApi({
    "/api/v1/system": { body: failed.system() },
    "/api/v1/economic-series": { body: failed.series() },
    "/api/v1/instruments": { body: failed.instruments() },
    "/api/v1/datasets": { body: failed.datasets() },
    "/api/v1/ingestion-jobs": { body: failed.jobs() },
  });
}

function mockSyntheticWorkspace() {
  return mockApi({
    "/api/v1/system": { body: synthetic.system() },
    "/api/v1/economic-series": { body: synthetic.series() },
    "/api/v1/instruments": { body: synthetic.instruments() },
    "/api/v1/datasets": { body: synthetic.datasets() },
    "/api/v1/ingestion-jobs": { body: synthetic.jobs() },
  });
}

describe("Data Explorer", () => {
  it("says plainly that a failed retrieval left no data, and how to retry", async () => {
    mockFailedWorkspace();
    renderRoute("/data");

    expect(
      await screen.findByText("The last retrieval failed — no values are stored yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/0 of 11 series retrieved \(3 failed, 8 skipped\)/),
    ).toBeInTheDocument();
    expect(screen.getByText("python -m app.ingestion run worldbank-wdi")).toBeInTheDocument();
    expect(statValue("Series with values")).toBe("0");
    expect(screen.getByText("of 11 in the catalogue")).toBeInTheDocument();
    expect(statValue("Observations stored")).toBe("0");

    const table = screen.getByRole("table", { name: /Latest values are rounded/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(11);
    const inflation = within(table)
      .getByRole("link", { name: "Inflation, consumer prices (annual %) — India" })
      .closest("tr");
    expect(inflation).not.toBeNull();
    expect(within(inflation as HTMLElement).getByText("Failed")).toBeInTheDocument();
    expect(within(inflation as HTMLElement).getByText("No values")).toBeInTheDocument();
    expect(within(table).getAllByText("Skipped")).toHaveLength(8);
  });

  it("explains that no prices ship with RUMIN and how to import licensed files", async () => {
    mockFailedWorkspace();
    renderRoute("/data");
    expect(await screen.findByText("No price files imported")).toBeInTheDocument();
    expect(screen.getByText(/RUMIN ships no price data/)).toBeInTheDocument();
    expect(screen.getByText("python -m app.ingestion manifest-template")).toBeInTheDocument();
  });

  it("lists datasets with their licence and attribution, and the ingestion runs", async () => {
    mockFailedWorkspace();
    renderRoute("/data");
    const licence = await screen.findByRole("link", { name: /CC BY 4\.0/ });
    expect(licence).toHaveAttribute("href", "https://creativecommons.org/licenses/by/4.0/");
    expect(licence).toHaveAttribute("target", "_blank");
    expect(
      screen.getByText(/The World Bank: World Development Indicators\. The original source/),
    ).toBeInTheDocument();
    expect(screen.getByText("Illustrative sample")).toBeInTheDocument(); // the curated network

    const runs = screen.getByRole("heading", { name: "Recent ingestion runs" }).closest("section");
    const runRows = within(runs as HTMLElement)
      .getAllByRole("row")
      .slice(1);
    expect(runRows).toHaveLength(2);
    expect(within(runRows[0] as HTMLElement).getByText("Failed")).toBeInTheDocument();
    expect(within(runRows[0] as HTMLElement).getByText("0 of 11")).toBeInTheDocument();
  });

  it("shows stored series with their latest value and filters them", async () => {
    mockSyntheticWorkspace();
    const user = userEvent.setup();
    renderRoute("/data");

    const table = await screen.findByRole("table", { name: /Latest values are rounded/ });
    expect(within(table).getByText("2.92")).toBeInTheDocument(); // rounded for the list
    expect(within(table).getByText("3,700,000,000,000")).toBeInTheDocument();
    expect(within(table).getAllByText("1990–2024")).toHaveLength(2);
    expect(statValue("Observations stored")).toBe("69");
    expect(statValue("Flagged for review")).toBe("2");
    expect(
      screen.queryByText("The last retrieval failed — no values are stored yet"),
    ).not.toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Search" }), "series b");
    expect(within(table).getAllByRole("row")).toHaveLength(2); // header + one match
    expect(screen.getByText("1 of 2 series")).toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Search" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Country" }), "IND");
    await user.click(screen.getByRole("checkbox", { name: "Only series with values" }));
    expect(screen.getByText("2 series")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search" }), "no such series");
    expect(within(table).getByText("No series match these filters.")).toBeInTheDocument();
  });

  it("links an imported instrument to its price page", async () => {
    mockSyntheticWorkspace();
    renderRoute("/data");
    const link = await screen.findByRole("link", { name: "SYNTHETIC Co (not a real company)" });
    expect(link).toHaveAttribute("href", "/data/instruments/demo-synthetic-co");
    const row = link.closest("tr") as HTMLElement;
    expect(within(row).getByText("XNSE:SYNTH")).toBeInTheDocument();
    expect(within(row).getByText("136")).toBeInTheDocument();
  });
});
