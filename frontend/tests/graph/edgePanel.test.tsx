import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EdgePanel } from "@/features/graph/EdgePanel";
import { graphFixtures, graphPath, SERIES_CPI_INDIA_EDGE, USD_INR_EDGE } from "../fixtures/graph";
import { mockApi } from "../utils/api";

async function evidenceFor(edgeId: string) {
  render(<EdgePanel edgeId={edgeId} onSelect={vi.fn()} onClose={vi.fn()} />);
  return screen.findByRole("region", { name: "Evidence records" });
}

describe("EdgePanel retrieval time", () => {
  it("says a catalogued provider series has no values yet, not that it is not provider data", async () => {
    mockApi({
      [graphPath.edge(SERIES_CPI_INDIA_EDGE)]: { body: graphFixtures.edgeSeriesCpiIndia() },
    });
    const evidence = await evidenceFor(SERIES_CPI_INDIA_EDGE);
    expect(within(evidence).getByText("Series catalogue entry")).toBeVisible();
    expect(within(evidence).getByText("Not yet — no values have been retrieved")).toBeVisible();
    expect(within(evidence).queryByText(/not provider data/)).toBeNull();
  });

  it("marks retrieval as not applicable for a reference-data record", async () => {
    mockApi({ [graphPath.edge(USD_INR_EDGE)]: { body: graphFixtures.edgeUsdInrDeltrin() } });
    const evidence = await evidenceFor(USD_INR_EDGE);
    expect(within(evidence).getByText("Reference dataset record")).toBeVisible();
    expect(within(evidence).getByText("Not applicable (not provider data)")).toBeVisible();
  });
});
