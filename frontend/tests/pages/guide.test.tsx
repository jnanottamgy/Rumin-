/**
 * Getting started (Phase 10): the guide's starter tasks end in real pages, and the Overview's
 * first-use card can be hidden for good.
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { sessionFixture } from "../fixtures/accounts";
import { mockApi } from "../utils/api";
import { renderRoute } from "../utils/render";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Getting started", () => {
  it("lists starter tasks that each open a working page", async () => {
    mockApi();
    renderRoute("/guide");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Getting started" }),
    ).toBeInTheDocument();
    expect(document.title).toBe("Getting started — RUMIN");
    const tasks = within(screen.getByRole("region", { name: "Starter tasks" }));
    const scenario = tasks.getByRole("listitem", { name: "Run a what-if scenario" });
    expect(within(scenario).getByRole("link", { name: /Start from the template/ })).toHaveAttribute(
      "href",
      "/scenarios/new?template=crude_oil_airline",
    );
    expect(tasks.getByRole("link", { name: /Open Aerisca Airways in the graph/ })).toHaveAttribute(
      "href",
      "/graph?focus=company%3Aco_aerisca_airways",
    );
    expect(tasks.getAllByRole("listitem", { name: /./ })).toHaveLength(6);
    // An administrator can finish every task: no role notes.
    expect(screen.queryByText(/need the analyst role/)).toBeNull();
    expect(screen.getByText(/You are signed in as/)).toHaveTextContent("administrator");
  });

  it("tells a viewer which steps their role cannot take", async () => {
    mockApi({ "/api/v1/auth/session": { body: sessionFixture("viewer") } });
    renderRoute("/guide");

    expect(
      await screen.findByText(
        "Your role can follow every step up to saving; saving and executing need the analyst role.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/You are signed in as/)).toHaveTextContent("viewer");
  });
});

describe("the first-use card", () => {
  it("points to the guide and stays hidden once dismissed", async () => {
    mockApi();
    const user = userEvent.setup();
    const { unmount } = renderRoute("/dashboard");

    const card = await screen.findByRole("region", { name: "Welcome, Test" });
    expect(within(card).getByRole("link", { name: "Getting started" })).toHaveAttribute(
      "href",
      "/guide",
    );
    await user.click(within(card).getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("region", { name: "Welcome, Test" })).toBeNull();
    unmount();

    renderRoute("/dashboard");
    await screen.findByRole("heading", { level: 1, name: "Overview" });
    expect(screen.queryByRole("region", { name: "Welcome, Test" })).toBeNull();
  });
});
