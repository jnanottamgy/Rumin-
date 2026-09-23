import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failed, synthetic } from "../fixtures/data";
import { mockApi } from "../utils/api";
import { renderRoute } from "../utils/render";

function mockInstrument(instrument = synthetic.instrument()) {
  return mockApi({
    "/api/v1/instruments/demo-synthetic-co": { body: instrument },
    "/api/v1/instruments/demo-synthetic-co/prices": { body: synthetic.prices() },
    "/api/v1/data-quality/issues": { body: synthetic.instrumentIssues() },
  });
}

describe("Instrument page", () => {
  it("shows imported prices as a sample, with the latest trading day and flags", async () => {
    mockInstrument();
    renderRoute("/data/instruments/demo-synthetic-co");

    expect(
      await screen.findByRole("heading", { level: 1, name: "SYNTHETIC Co (not a real company)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/RUMIN ships no price data and connects to no market feed/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Sample data — not real").length).toBeGreaterThan(0);

    const chart = await screen.findByRole("slider", { name: /closing price: values by period/ });
    expect(chart).toHaveAttribute(
      "aria-valuetext",
      expect.stringMatching(/^19 Sep 2026 · close, INR: 150\.5\. Open 150 · High 151 · Low 149/),
    );
    const freshness = screen.getByRole("group", { name: "How current this data is" });
    expect(within(freshness).getByText("Latest trading day")).toBeInTheDocument();
    expect(within(freshness).getByText("19 Sep 2026")).toBeInTheDocument();
    expect(within(freshness).getByText("Imported into RUMIN")).toBeInTheDocument();

    expect(await screen.findByText("Weekend date")).toBeInTheDocument();
    expect(screen.getByText("Trading gap")).toBeInTheDocument();
  });

  it("lists every price exactly in the table, newest first", async () => {
    mockInstrument();
    const user = userEvent.setup();
    renderRoute("/data/instruments/demo-synthetic-co");
    await screen.findByRole("slider");
    await user.click(screen.getByRole("button", { name: "Table" }));
    const table = screen.getByRole("table", { name: /Prices exactly as they appear/ });
    const first = within(table).getAllByRole("row")[1] as HTMLElement;
    expect(within(first).getByRole("rowheader")).toHaveTextContent("19 Sep 2026");
    expect(within(first).getByText("150.5")).toBeInTheDocument();
    expect(within(first).getByText("Flagged for review")).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(137);
  });

  it("never blends sources: prices are loaded for the chosen dataset", async () => {
    const instrument = synthetic.instrument();
    const [first] = instrument.price_datasets;
    instrument.price_datasets.push({
      ...(first as NonNullable<typeof first>),
      id: "second-source",
      name: "A second (synthetic) source",
    });
    const api = mockInstrument(instrument);
    const user = userEvent.setup();
    renderRoute("/data/instruments/demo-synthetic-co");

    expect(await screen.findByText(/come from 2 sources/)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox"), "second-source");
    await screen.findByRole("slider");
    const priceRequests = api.requests.filter((request) => request.path.endsWith("/prices"));
    expect(
      priceRequests.map((request) => new URLSearchParams(request.query).get("dataset_id")),
    ).toEqual(["synthetic-prices", "second-source"]);
  });
});

describe("Ingestion run page", () => {
  it("shows what a failed run did, target by target", async () => {
    const job = failed.job();
    mockApi({ [`/api/v1/ingestion-jobs/${job.id}`]: { body: job } });
    renderRoute(`/data/jobs/${job.id}`);

    expect(
      await screen.findByRole("heading", { level: 1, name: /^worldbank-wdi · / }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByText("What went wrong")).toBeInTheDocument();
    expect(
      screen.getByText(/Stopped after 3 consecutive temporary provider failures/),
    ).toBeInTheDocument();

    const targets = screen.getByRole("table", { name: /Received = new \+ revised/ });
    expect(within(targets).getAllByText("The provider could not be reached")).toHaveLength(3);
    expect(
      within(targets).getAllByText("Skipped: the provider appeared to be unavailable"),
    ).toHaveLength(8);
    expect(screen.getByText("Nothing was received, so nothing was stored.")).toBeInTheDocument();
    expect(screen.getByText("No quality issues were recorded by this run.")).toBeInTheDocument();
  });

  it("lists the stored responses with their hashes, and the issues found", async () => {
    const job = synthetic.job();
    mockApi({ [`/api/v1/ingestion-jobs/${job.id}`]: { body: job } });
    renderRoute(`/data/jobs/${job.id}`);

    const captures = await screen.findByRole("table", {
      name: /stored \(compressed\) with their SHA-256/,
    });
    const rows = within(captures).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const firstCapture = job.captures[0];
    expect(
      within(rows[0] as HTMLElement).getByText(`${firstCapture?.sha256.slice(0, 12)}…`),
    ).toHaveAttribute("title", firstCapture?.sha256);
    expect(screen.getByRole("rowheader", { name: "Outside review range" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^demo-a/ })).toHaveAttribute(
      "href",
      "/data/series/demo-a",
    );
  });
});
