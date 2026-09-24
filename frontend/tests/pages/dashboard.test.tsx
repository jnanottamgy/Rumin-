import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { networkFixture, scenarioFixture, scenarioPageFixture, systemFixture } from "../fixtures";
import { type MockReply, mockApi, unreachable } from "../utils/api";
import { renderRoute } from "../utils/render";

/** The figure shown in a stat tile, read through its label. */
const statValue = (label: string) =>
  screen.getByText(label, { selector: "dt" }).nextElementSibling?.textContent;

function deferred() {
  let release: (reply: MockReply) => void = () => {};
  const promise = new Promise<MockReply>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

describe("Overview dashboard", () => {
  it("shows a loading state until the network arrives", async () => {
    const pending = deferred();
    mockApi({ "/api/v1/network": () => pending.promise });
    renderRoute("/dashboard");

    const loading = await screen.findByText("Loading the network…");
    expect(loading.closest('[role="status"]')).toHaveAttribute("aria-live", "polite");
    expect(statValue("Entities")).toBe("—");

    pending.release({ body: networkFixture() });
    expect(
      await screen.findByRole("group", { name: /^Preview of the financial network: 30 entities/ }),
    ).toBeInTheDocument();
  });

  it("reports the workspace from live API data", async () => {
    mockApi({ "/api/v1/scenarios": { body: scenarioPageFixture() } });
    renderRoute("/dashboard");
    await screen.findByRole("group", { name: /^Preview of the financial network/ });

    expect(statValue("Entities")).toBe("30");
    expect(statValue("Relationships")).toBe("41");
    expect(screen.getByText("+ 30 structural links derived from records")).toBeInTheDocument();
    expect(screen.getByText("All illustrative assumptions")).toBeInTheDocument();
    expect(statValue("Scenarios")).toBe("2");
    expect(
      screen.getByText("Versioned; executed through the model registry in the Scenario Lab"),
    ).toBeInTheDocument();
    expect(statValue("Dataset")).toBe("v1.0.0");

    const recent = screen.getByRole("link", { name: /Oil, rupee and rates on Aerisca/ });
    expect(recent).toHaveAttribute("href", `/scenarios/${scenarioFixture().id}`);
    expect(within(recent).getByText(/3 changes · v1 · executed/)).toBeInTheDocument();
    // The badge follows the latest execution; it never calls an executed scenario "not simulated".
    expect(within(recent).getByText("Executed")).toBeInTheDocument();
    expect(screen.queryByText("Not simulated")).not.toBeInTheDocument();

    // Capabilities that do not exist yet are listed as such; the simulation engine exists.
    expect(screen.queryByText("Simulation engine")).not.toBeInTheDocument();
    expect(screen.getByText("Probabilistic simulation")).toBeInTheDocument();
    expect(screen.getByText("Not available · Phase 9")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument(); // live market data
  });

  it("links a previewed entity to the Universe", async () => {
    mockApi();
    const user = userEvent.setup();
    renderRoute("/dashboard");
    await screen.findByRole("group", { name: /^Preview of the financial network/ });

    await user.click(screen.getByRole("button", { name: /^Anvaya Bank, company/ }));
    expect(screen.getByRole("link", { name: "Open in the Universe" })).toHaveAttribute(
      "href",
      "/universe?focus=co_anvaya_bank",
    );
  });

  it("says when the API is unreachable and recovers on retry", async () => {
    const api = mockApi({
      "/api/v1/network": unreachable,
      "/api/v1/system": unreachable,
      "/api/v1/scenarios": unreachable,
    });
    const user = userEvent.setup();
    renderRoute("/dashboard");

    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
    expect(screen.getAllByText("API unreachable").length).toBeGreaterThan(0);
    expect(statValue("Entities")).toBe("—");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("Could not reach the RUMIN API");

    api.setRoute("/api/v1/network", { body: networkFixture() });
    api.setRoute("/api/v1/system", { body: systemFixture() });
    const networkAlert = alerts.find((alert) => within(alert).queryByText(/Try again/));
    if (!networkAlert) throw new Error("no retry button");
    await user.click(within(networkAlert).getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("group", { name: /^Preview of the financial network/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "try again" }));
    expect(await screen.findByText("Responding · development")).toBeInTheDocument();
  });
});
