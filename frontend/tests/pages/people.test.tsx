/**
 * People and the audit trail (Phase 10, administrators), through the real route table
 * against a fake API. The accounts are the made-up test people of `fixtures/accounts.ts`.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { describeDetail } from "@/pages/PeoplePage";
import type { Account } from "@/types/api";
import { accountFixture, auditEventsFixture, PEOPLE, sessionFixture } from "../fixtures/accounts";
import { errorReply, mockApi, type RecordedRequest, type Route } from "../utils/api";
import { renderRoute } from "../utils/render";

const USERS = "/api/v1/users";
const EVENTS = "/api/v1/audit-events";
const analystId = PEOPLE.analyst.id;

afterEach(() => {
  vi.restoreAllMocks();
});

function peopleRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  const accounts: Account[] = [accountFixture("admin"), accountFixture("analyst")];
  return {
    [USERS]: () => ({ body: { items: accounts } }),
    [EVENTS]: { body: auditEventsFixture() },
    [`POST ${USERS}`]: (request: RecordedRequest) => {
      const body = request.body as { name: string; email: string; role: Account["role"] };
      const created = accountFixture("viewer", {
        id: "00000000-0000-4000-8000-00000000a004",
        name: body.name,
        email: body.email,
        role: body.role,
        must_change_password: true,
        last_login_at: null,
      });
      accounts.push(created);
      return { status: 201, body: created };
    },
    [`PUT ${USERS}/${analystId}`]: (request: RecordedRequest) => {
      const index = accounts.findIndex((account) => account.id === analystId);
      const updated = { ...accounts[index], ...(request.body as Partial<Account>) } as Account;
      accounts[index] = updated;
      return { body: updated };
    },
    [`POST ${USERS}/${analystId}/password`]: {
      body: accountFixture("analyst", { must_change_password: true }),
    },
    [`POST ${USERS}/${analystId}/sessions/revoke`]: { status: 204 },
    ...overrides,
  };
}

async function openPeople() {
  const view = renderRoute("/people");
  await screen.findByRole("heading", { level: 1, name: "People" });
  await screen.findByRole("list", { name: "Accounts" });
  return view;
}

const accounts = () => within(screen.getByRole("list", { name: "Accounts" }));

describe("People", () => {
  it("lists the accounts and the audit trail in words", async () => {
    mockApi(peopleRoutes());
    await openPeople();

    expect(document.title).toBe("People — RUMIN");
    const me = accounts().getByRole("listitem", { name: "Test Administrator" });
    expect(within(me).getByText("You")).toBeInTheDocument();
    expect(within(me).queryByRole("button", { name: /Manage/ })).toBeNull();
    const analyst = accounts().getByRole("listitem", { name: "Test Analyst" });
    expect(within(analyst).getByText("analyst@rumin.test")).toBeInTheDocument();
    expect(within(analyst).getByText("Active")).toBeInTheDocument();

    const trail = within(await screen.findByRole("region", { name: "Security audit trail" }));
    expect(trail.getByRole("row", { name: /Account changed/ })).toHaveTextContent(
      "role viewer → analyst",
    );
    expect(trail.getByRole("row", { name: /Sign-in failed/ })).toHaveTextContent("wrong password");
  });

  it("creates an account with a temporary password", async () => {
    const api = mockApi(peopleRoutes());
    const user = userEvent.setup();
    await openPeople();

    await user.type(screen.getByLabelText("Name"), "Test Newcomer");
    await user.type(screen.getByLabelText("E-mail address"), "newcomer@rumin.test");
    await user.selectOptions(screen.getByLabelText("Role"), "viewer");
    expect(screen.getByLabelText("Role")).toHaveAccessibleDescription(
      "Reads everything in the workspace; creates and runs nothing.",
    );
    await user.type(screen.getByLabelText("Temporary password"), "a temporary test phrase");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Account created for Test Newcomer (newcomer@rumin.test) as viewer.",
    );
    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: USERS,
        query: "",
        body: {
          name: "Test Newcomer",
          email: "newcomer@rumin.test",
          role: "viewer",
          temporary_password: "a temporary test phrase",
        },
      },
    ]);
    expect(await accounts().findByRole("listitem", { name: "Test Newcomer" })).toHaveTextContent(
      "Temporary password",
    );
    expect(screen.getByLabelText("Temporary password")).toHaveValue("");
  });

  it("puts the server's objections under the fields they concern", async () => {
    mockApi(
      peopleRoutes({
        [`POST ${USERS}`]: errorReply(422, "validation_error", "The request is invalid.", [
          {
            location: "body",
            field: "email",
            message: "String should match pattern '^[^@]+@'",
            type: "string_pattern_mismatch",
          },
          {
            location: "body",
            field: "temporary_password",
            message: "Use at least 12 characters.",
            type: "password_policy",
          },
        ]),
      }),
    );
    const user = userEvent.setup();
    await openPeople();

    await user.type(screen.getByLabelText("Name"), "Test Newcomer");
    await user.type(screen.getByLabelText("E-mail address"), "newcomer");
    await user.type(screen.getByLabelText("Temporary password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(screen.getByLabelText("E-mail address")).toHaveAccessibleDescription(
        "Enter an e-mail address like name@example.com.",
      ),
    );
    expect(screen.getByLabelText("Temporary password")).toHaveAccessibleDescription(
      expect.stringContaining("Use at least 12 characters."),
    );
  });

  it("changes a role, sets a temporary password, signs out and deactivates", async () => {
    const api = mockApi(peopleRoutes());
    const user = userEvent.setup();
    await openPeople();

    const row = accounts().getByRole("listitem", { name: "Test Analyst" });
    const manage = within(row).getByRole("button", { name: "Manage Test Analyst" });
    await user.click(manage);
    expect(manage).toHaveAttribute("aria-expanded", "true");
    const panel = within(
      document.getElementById(manage.getAttribute("aria-controls") ?? "") as HTMLElement,
    );

    const save = panel.getByRole("button", { name: "Save role" });
    expect(save).toBeDisabled();
    await user.selectOptions(panel.getByLabelText("Role"), "viewer");
    await user.click(save);
    expect(await panel.findByRole("status")).toHaveTextContent(
      "Test Analyst is now viewer. It applies to their next request.",
    );

    await user.type(panel.getByLabelText("New temporary password"), "a temporary test phrase");
    await user.click(panel.getByRole("button", { name: "Set temporary password" }));
    await waitFor(() =>
      expect(panel.getByRole("status")).toHaveTextContent(
        "Test Analyst has a temporary password and must replace it at their next sign-in.",
      ),
    );

    await user.click(panel.getByRole("button", { name: "Sign out everywhere" }));
    await waitFor(() =>
      expect(panel.getByRole("status")).toHaveTextContent(
        "Every session of Test Analyst has ended.",
      ),
    );

    await user.click(panel.getByRole("button", { name: "Deactivate account" }));
    await waitFor(() =>
      expect(panel.getByRole("status")).toHaveTextContent(
        "Test Analyst is deactivated and signed out everywhere.",
      ),
    );

    expect(api.writes().map(({ method, path, body }) => ({ method, path, body }))).toEqual([
      { method: "PUT", path: `${USERS}/${analystId}`, body: { role: "viewer" } },
      {
        method: "POST",
        path: `${USERS}/${analystId}/password`,
        body: { temporary_password: "a temporary test phrase" },
      },
      { method: "POST", path: `${USERS}/${analystId}/sessions/revoke`, body: undefined },
      { method: "PUT", path: `${USERS}/${analystId}`, body: { is_active: false } },
    ]);
  });

  it("says why the last administrator cannot be demoted", async () => {
    mockApi(
      peopleRoutes({
        [`PUT ${USERS}/${analystId}`]: errorReply(
          409,
          "conflict",
          "This is the only active administrator: make someone else an administrator first.",
        ),
      }),
    );
    const user = userEvent.setup();
    await openPeople();

    await user.click(accounts().getByRole("button", { name: "Manage Test Analyst" }));
    await user.click(screen.getByRole("button", { name: "Deactivate account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This is the only active administrator",
    );
  });

  it("is only for administrators", async () => {
    const api = mockApi({ "/api/v1/auth/session": { body: sessionFixture("analyst") } });
    renderRoute("/people");

    expect(await screen.findByText("Only administrators manage people")).toBeInTheDocument();
    expect(api.requests.some((request) => request.path.startsWith(USERS))).toBe(false);
  });

  it("describes event details it does not know without dropping them", () => {
    expect(
      describeDetail({
        ...auditEventsFixture().items[0],
        detail: { is_active: [true, false], via: "command line", colour: "blue" },
      } as ReturnType<typeof auditEventsFixture>["items"][number]),
    ).toBe("deactivated · via the command line · colour: blue");
  });
});
