import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi } from "../utils/api";
import { renderRoute } from "../utils/render";

describe("application shell and routing", () => {
  it("renders the landing page with an honest description of the build", async () => {
    mockApi();
    renderRoute("/");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /interactive financial intelligence platform/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Deterministic runs of five registered models/)).toBeInTheDocument();
    // The illustrative network drawing appears once the API has answered.
    expect(await screen.findByText(/30 entities and 71 links/)).toBeInTheDocument();
  });

  it("navigates from the landing page into the workspace", async () => {
    mockApi();
    const user = userEvent.setup();
    const { router } = renderRoute("/");

    await user.click(screen.getByRole("link", { name: "Open workspace" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/dashboard");
  });

  it("moves between modules with the primary navigation", async () => {
    mockApi();
    const user = userEvent.setup();
    const { router } = renderRoute("/dashboard");
    await screen.findByRole("heading", { level: 1, name: "Overview" });
    const nav = screen.getByRole("navigation", { name: "Primary" });

    await user.click(within(nav).getByRole("link", { name: /Scenario Lab/ }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "What happens if something changes?" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/scenarios");

    await user.click(within(nav).getByRole("link", { name: /Universe/ }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "How the sample economy connects" }),
    ).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Universe/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows a not-found page for unknown addresses", async () => {
    mockApi();
    renderRoute("/does-not-exist");
    expect(
      await screen.findByRole("heading", { level: 1, name: "This page does not exist" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the overview" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("reports live workspace status from the API", async () => {
    mockApi();
    renderRoute("/analyst");
    expect(await screen.findAllByText("Illustrative sample v1.0.0")).not.toHaveLength(0);
  });

  it("says plainly that the AI analyst is not connected", async () => {
    const api = mockApi();
    renderRoute("/analyst");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Ask questions about the model" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not available in this build")).toBeInTheDocument();
    expect(screen.getByText("No model connected · no requests are made")).toBeInTheDocument();
    // The question box and the button are inert: there is nothing to send a question to.
    expect(screen.getByLabelText(/Question for the AI Analyst/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(api.requests.some((request) => /analyst|chat|completion/.test(request.path))).toBe(
      false,
    );
  });

  it("lists what the build cannot do yet on the system page", async () => {
    mockApi();
    renderRoute("/system");
    expect(await screen.findByText("Simulation engine")).toBeInTheDocument();
    expect(screen.getByText("AI analyst")).toBeInTheDocument();
    expect(screen.getByText("Probabilistic simulation")).toBeInTheDocument();
    expect(
      screen.getByText(/runs are deterministic and no probabilities are estimated/),
    ).toBeInTheDocument();
  });

  it("switches the colour theme and remembers the choice", async () => {
    mockApi();
    const user = userEvent.setup();
    renderRoute("/");
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("rumin.theme")).toBe("dark");
  });
});
