/**
 * Integration: the Phase 2 read API against a running backend.
 *
 * `scripts/smoke_test.sh` prepares the database: the series catalogue is loaded (no values
 * — nothing is fetched from a provider) and a three-row SYNTHETIC price file is imported
 * through the ingestion command line.
 */
import { describe, expect, it } from "vitest";
import { api, dataApi } from "@/services/api";
import { contractViolations } from "./contract";
import { baseUrl, options, signedIn } from "./session";

describe("providers and datasets", () => {
  it("lists the providers with their terms", async () => {
    const providers = await dataApi.providers(options);
    expect(providers.map((provider) => provider.id).sort()).toEqual(["price-file", "worldbank"]);
    for (const provider of providers) {
      expect(contractViolations("ProviderRead", provider)).toEqual([]);
    }
  });

  it("labels curated sample data and provider data apart", async () => {
    const page = await dataApi.datasets(options);
    expect(contractViolations("DatasetPage", page)).toEqual([]);
    const byId = new Map(page.items.map((dataset) => [dataset.id, dataset]));
    expect(byId.get("rumin-sample")).toMatchObject({ kind: "curated", is_illustrative: true });
    expect(byId.get("worldbank-wdi")).toMatchObject({
      kind: "provider",
      is_illustrative: false,
      license: "CC BY 4.0",
    });
    expect(byId.get("smoke-synthetic-prices")).toMatchObject({ is_illustrative: true });
  });
});

describe("economic series", () => {
  it("serves the catalogue with no values until a retrieval has run", async () => {
    const page = await dataApi.series(options);
    expect(contractViolations("SeriesPage", page)).toEqual([]);
    expect(page.total).toBe(11);
    for (const series of page.items) {
      expect(series).toMatchObject({
        observation_count: 0,
        latest: null,
        epistemic_category: "observation",
      });
    }

    const detail = await dataApi.seriesDetail("wb-ind-fp-cpi-totl-zg", options);
    expect(contractViolations("SeriesDetail", detail)).toEqual([]);
    expect(detail.dataset.attribution).toMatch(/^The World Bank/);
    const observations = await dataApi.observations(detail.id, false, options);
    expect(contractViolations("ObservationPage", observations)).toEqual([]);
    expect(observations.total).toBe(0);
  });
});

describe("imported prices", () => {
  it("serves the imported file exactly, labelled as sample data", async () => {
    const instruments = await dataApi.instruments(options);
    expect(contractViolations("InstrumentPage", instruments)).toEqual([]);
    expect(instruments.items.map((item) => item.id)).toEqual(["smoke-synthetic"]);

    const prices = await dataApi.prices("smoke-synthetic", "smoke-synthetic-prices", 0, options);
    expect(contractViolations("PriceBarPage", prices)).toEqual([]);
    // Exact decimal strings: "100.40" in the file is the number 100.4, never a float.
    expect(prices.items.map((bar) => [bar.trade_date, bar.close])).toEqual([
      ["2025-03-03", "101"],
      ["2025-03-04", "102"],
      ["2025-03-05", "100.4"],
    ]);
    expect(prices.dataset).toMatchObject({
      is_illustrative: true,
      license: "None (synthetic test data)",
    });
  });

  it("records the import as a job, with the stored file and no secrets", async () => {
    const jobs = await dataApi.jobs({}, options);
    expect(contractViolations("JobPage", jobs)).toEqual([]);
    const [job] = jobs.items;
    expect(job).toMatchObject({ status: "completed", records_new: 3, records_rejected: 0 });

    const detail = await dataApi.job(job?.id ?? "", options);
    expect(contractViolations("JobDetail", detail)).toEqual([]);
    expect(detail.captures.map((capture) => capture.locator)).toEqual(["smoke-prices.csv"]);
    expect(detail.parameters).toEqual({
      file: "smoke-prices.csv",
      instrument: "smoke-synthetic",
      adjustment: "unadjusted",
    });

    expect(contractViolations("IssuePage", await dataApi.issues({}, options))).toEqual([]);
    const rules = await dataApi.rules(options);
    for (const rule of rules) expect(contractViolations("RuleRead", rule)).toEqual([]);
    expect(rules.find((rule) => rule.code === "high_below_low")?.outcome).toBe("rejected");
  });
});

describe("honesty of the system report", () => {
  it("counts what is stored and claims no live data", async () => {
    const system = await api.system(options);
    expect(system.data).toMatchObject({
      series_total: 11,
      series_with_data: 0,
      observations: 0,
      instruments: 1,
      price_bars: 3,
    });
    const capabilities = new Map(system.capabilities.map((c) => [c.id, c.available]));
    expect(capabilities.get("historical_observations")).toBe(true);
    expect(capabilities.get("live_market_data")).toBe(false);
    expect(capabilities.get("ingestion_from_web")).toBe(false);
  });

  it("offers no way to start ingestion over HTTP", async () => {
    const response = await fetch(`${baseUrl}/api/v1/ingestion-jobs`, {
      method: "POST",
      headers: signedIn,
    });
    expect(response.status).toBe(405);
  });
});
