import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { scenarioFixture, scenarioPageFixture } from "../fixtures";
import { errorReply, mockApi, unreachable } from "../utils/api";
import { renderRoute } from "../utils/render";

async function openLab(path = "/scenarios") {
  const view = renderRoute(path);
  await screen.findByLabelText("Scenario name");
  return view;
}

describe("Scenario Lab", () => {
  it("defines inputs only and never presents results", async () => {
    mockApi();
    await openLab();

    expect(screen.getByRole("heading", { level: 2, name: "New scenario" })).toBeInTheDocument();
    expect(screen.getByText("Not simulated yet")).toBeInTheDocument();
    expect(screen.getByText("No simulation engine in this build")).toBeInTheDocument();
    expect(
      screen.getByText("Saving stores the inputs only. It does not run a simulation."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run|simulate/i })).toBeNull();
  });

  it("validates the form before anything is sent", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    await openLab();

    await user.click(screen.getByRole("button", { name: "Save draft" }));

    const summary = screen.getByRole("alert");
    expect(summary).toHaveTextContent("Check these fields");
    expect(summary).toHaveTextContent("Give the scenario a name.");
    expect(summary).toHaveTextContent("Choose a variable.");
    expect(screen.getByLabelText("Scenario name")).toHaveAttribute("aria-invalid", "true");
    expect(api.writes()).toEqual([]);

    // Each message in the summary leads to its field.
    await user.click(within(summary).getByRole("button", { name: "Choose a variable." }));
    expect(screen.getByLabelText("Economic variable")).toHaveFocus();
  });

  it("applies the variable's published limits", async () => {
    const api = mockApi();
    const user = userEvent.setup();
    await openLab();

    await user.type(screen.getByLabelText("Scenario name"), "Rate hike");
    await user.selectOptions(screen.getByLabelText("Economic variable"), "var_rbi_repo_rate");
    // Rates change only in percentage points.
    expect(screen.queryByRole("radio", { name: "Percent change" })).toBeNull();
    expect(screen.getByRole("radio", { name: "Absolute change" })).toBeChecked();
    expect(screen.getByText(/Rates change in percentage points/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Change"), "40");
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    expect(screen.getByLabelText("Change")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("Must be at most +25 percentage points.").length).toBeGreaterThan(0);
    expect(api.writes()).toEqual([]);
  });

  it("saves a valid draft, sends exactly the inputs, and says nothing was simulated", async () => {
    const saved = scenarioFixture({ name: "Oil price shock" });
    const api = mockApi();
    api.setRoute("POST /api/v1/scenarios", () => {
      api.setRoute("/api/v1/scenarios", { body: scenarioPageFixture([saved]) });
      return { status: 201, body: saved };
    });
    const user = userEvent.setup();
    const { router } = await openLab();

    await user.type(screen.getByLabelText("Scenario name"), "  Oil price shock ");
    await user.selectOptions(screen.getByLabelText("Economic variable"), "var_brent_crude");
    expect(screen.getByRole("radio", { name: "Percent change" })).toBeChecked();
    await user.type(screen.getByLabelText("Change"), "30");
    expect(screen.getByText("Brent crude oil price: +30% (relative change)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    expect(api.writes()).toEqual([
      expect.objectContaining({
        method: "POST",
        path: "/api/v1/scenarios",
        body: {
          name: "Oil price shock",
          description: "",
          shocks: [
            { variable_id: "var_brent_crude", change_type: "percent_change", value: 30, note: "" },
          ],
        },
      }),
    ]);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Edit scenario" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/scenarios/${saved.id}`);
    expect(screen.getByText(/^Saved at .*Nothing was simulated\.$/)).toBeInTheDocument();
    // The new draft appears in the list, still marked as not simulated.
    const list = screen.getByRole("navigation", { name: "Saved scenarios" });
    expect(await within(list).findByText("Oil price shock")).toBeInTheDocument();
    expect(within(list).getByText("1 input · Draft · not simulated")).toBeInTheDocument();
  });

  it("shows the server's validation errors on the matching field", async () => {
    const api = mockApi({
      "POST /api/v1/scenarios": errorReply(
        422,
        "validation_error",
        "The scenario inputs are invalid.",
        [
          {
            location: "body",
            field: "shocks[0].value",
            message: "The server rejected this value.",
            type: "invalid_change",
          },
        ],
      ),
    });
    const user = userEvent.setup();
    await openLab();

    await user.click(screen.getByRole("button", { name: "Load the oil-shock example" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The server rejected this value.");
    expect(screen.getByLabelText("Change")).toHaveAttribute("aria-invalid", "true");
    expect(api.writes()).toHaveLength(1);
  });

  it("explains a failed save when the API is unreachable", async () => {
    mockApi({ "POST /api/v1/scenarios": unreachable });
    const user = userEvent.setup();
    await openLab();

    await user.click(screen.getByRole("button", { name: "Load the oil-shock example" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the RUMIN API");
    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
  });

  it("loads the worked example as an editable, clearly labelled draft", async () => {
    mockApi();
    const user = userEvent.setup();
    await openLab();

    await user.click(screen.getByRole("button", { name: "Load the oil-shock example" }));
    expect(screen.getByLabelText("Scenario name")).toHaveValue("Oil price shock (example)");
    expect(screen.getByLabelText("Economic variable")).toHaveValue("var_brent_crude");
    expect(screen.getByLabelText("Change")).toHaveValue("30");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("edits and deletes a saved scenario", async () => {
    const saved = scenarioFixture();
    const api = mockApi({
      [`/api/v1/scenarios/${saved.id}`]: { body: saved },
      "/api/v1/scenarios": { body: scenarioPageFixture([saved]) },
      [`DELETE /api/v1/scenarios/${saved.id}`]: { status: 204 },
    });
    const user = userEvent.setup();
    const { router } = await openLab(`/scenarios/${saved.id}`);

    expect(screen.getByRole("heading", { level: 2, name: "Edit scenario" })).toBeInTheDocument();
    expect(screen.getByLabelText("Scenario name")).toHaveValue(saved.name);
    expect(screen.queryByText("Unsaved changes")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Delete…" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));

    expect(api.writes()).toEqual([
      expect.objectContaining({ method: "DELETE", path: `/api/v1/scenarios/${saved.id}` }),
    ]);
    expect(
      await screen.findByRole("heading", { level: 2, name: "New scenario" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/scenarios");
  });

  it("reports a scenario that does not exist", async () => {
    mockApi({
      "/api/v1/scenarios/missing": errorReply(404, "not_found", "Scenario not found."),
    });
    renderRoute("/scenarios/missing");
    expect(await screen.findByText("This scenario does not exist")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new scenario" })).toHaveAttribute(
      "href",
      "/scenarios",
    );
  });
});
