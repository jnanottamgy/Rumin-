/**
 * Signing in and out, the session guard and choosing a password (Phase 10), through the real
 * route table against a fake API. The people are the made-up test accounts of
 * `fixtures/accounts.ts`; the password strings exist only in these tests.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { safeNext } from "@/app/session";
import { sessionFixture } from "../fixtures/accounts";
import { errorReply, mockApi, type RecordedRequest, signedOut, unreachable } from "../utils/api";
import { renderRoute } from "../utils/render";

const SESSION = "/api/v1/auth/session";
const LOGIN = "POST /api/v1/auth/login";
const LOGOUT = "POST /api/v1/auth/logout";
const PASSWORD = "POST /api/v1/auth/password";
const TEST_PASSPHRASE = "a test-only passphrase";

afterEach(() => {
  vi.restoreAllMocks();
});

/** A server that signs in whoever gives the test passphrase, and remembers it. */
function signInRoutes() {
  let signedIn = false;
  return {
    [SESSION]: () => (signedIn ? { body: sessionFixture("analyst") } : signedOut),
    [LOGIN]: (request: RecordedRequest) => {
      const body = request.body as { email: string; password: string };
      if (body.password !== TEST_PASSPHRASE) {
        return errorReply(401, "unauthorized", "The e-mail address or password is incorrect.");
      }
      signedIn = true;
      return { body: sessionFixture("analyst") };
    },
  };
}

describe("signing in", () => {
  it("sends a visitor to sign in, then back to the page they asked for", async () => {
    const api = mockApi(signInRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/scenarios?template=crude_oil_airline");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Sign in to RUMIN" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe(
      `?next=${encodeURIComponent("/scenarios?template=crude_oil_airline")}`,
    );
    // The title is set by an effect after the page renders.
    await waitFor(() => expect(document.title).toBe("Sign in — RUMIN"));
    // Nothing from the workspace was asked for while signed out.
    expect(api.requests.map((request) => request.path)).toEqual([SESSION]);

    await user.type(screen.getByLabelText("E-mail address"), "analyst@rumin.test");
    await user.type(screen.getByLabelText("Password"), TEST_PASSPHRASE);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/scenarios"));
    expect(router.state.location.search).toBe("?template=crude_oil_airline");
    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: "/api/v1/auth/login",
        query: "",
        body: { email: "analyst@rumin.test", password: TEST_PASSPHRASE },
      },
    ]);
  });

  it("says when the e-mail or password is wrong, and asks for the password again", async () => {
    mockApi(signInRoutes());
    const user = userEvent.setup();
    const { router } = renderRoute("/login");

    await user.type(await screen.findByLabelText("E-mail address"), "analyst@rumin.test");
    await user.type(screen.getByLabelText("Password"), "not the passphrase");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The e-mail address or password is incorrect.",
    );
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Password")).toHaveFocus();
    expect(screen.getByLabelText("E-mail address")).toHaveValue("analyst@rumin.test");
    expect(router.state.location.pathname).toBe("/login");
  });

  it("names each missing field instead of asking the server", async () => {
    const api = mockApi(signInRoutes());
    const user = userEvent.setup();
    renderRoute("/login");

    await user.click(await screen.findByRole("button", { name: "Sign in" }));

    const email = screen.getByLabelText("E-mail address");
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription("Enter your e-mail address.");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Enter your password.");
    expect(email).toHaveFocus();
    expect(api.writes()).toEqual([]);
  });

  it("passes on the server's wait when there have been too many attempts", async () => {
    mockApi({
      ...signInRoutes(),
      [LOGIN]: {
        ...errorReply(429, "rate_limited", "Too many sign-in attempts. Try again in 2 minutes."),
        headers: { "Retry-After": "120" },
      },
    });
    const user = userEvent.setup();
    renderRoute("/login");

    await user.type(await screen.findByLabelText("E-mail address"), "analyst@rumin.test");
    await user.type(screen.getByLabelText("Password"), TEST_PASSPHRASE);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many sign-in attempts. Try again in 2 minutes.",
    );
  });

  it("goes straight on when already signed in, and never to another site", async () => {
    mockApi({ [SESSION]: { body: sessionFixture("analyst") } });
    const { router } = renderRoute(`/login?next=${encodeURIComponent("//evil.example/steal")}`);
    await waitFor(() => expect(router.state.location.pathname).toBe("/dashboard"));
  });

  it("keeps the next page inside RUMIN", () => {
    expect(safeNext("/scenarios?template=x")).toBe("/scenarios?template=x");
    expect(safeNext("//evil.example")).toBe("/dashboard");
    expect(safeNext("/\\evil.example")).toBe("/dashboard");
    expect(safeNext("https://evil.example")).toBe("/dashboard");
    expect(safeNext("javascript:alert(1)")).toBe("/dashboard");
    expect(safeNext("/login?next=/x")).toBe("/dashboard");
    expect(safeNext(null)).toBe("/dashboard");
  });

  it("says when the server cannot be reached, and asks again on request", async () => {
    const api = mockApi({ [SESSION]: unreachable });
    const user = userEvent.setup();
    renderRoute("/dashboard");

    expect(
      await screen.findByText("RUMIN cannot check your session right now"),
    ).toBeInTheDocument();
    api.setRoute(SESSION, { body: sessionFixture("admin") });
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
  });
});

describe("while signed in", () => {
  it("returns to sign-in, keeping the place, when the session ends", async () => {
    mockApi({ "/api/v1/system": signedOut });
    const { router } = renderRoute("/system");

    expect(
      await screen.findByText("Your session ended. Sign in again to continue where you were."),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent("/system")}`);
  });

  it("shows who is signed in and what the role allows, and signs out", async () => {
    const api = mockApi({ [LOGOUT]: { status: 204 } });
    const user = userEvent.setup();
    const { router } = renderRoute("/dashboard");
    await screen.findByRole("heading", { level: 1, name: "Overview" });

    const account = screen.getByRole("button", {
      name: "Account: Test Administrator, Administrator",
    });
    expect(account).toHaveAttribute("aria-expanded", "false");
    await user.click(account);
    expect(account).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(account.getAttribute("aria-controls") ?? "");
    expect(panel).not.toBeNull();
    const menu = within(panel as HTMLElement);
    expect(menu.getByText("admin@rumin.test")).toBeInTheDocument();
    expect(menu.getByText(/changes anyone's work, and manages people/)).toBeInTheDocument();
    expect(menu.getByRole("link", { name: "People and audit trail" })).toHaveAttribute(
      "href",
      "/people",
    );
    expect(menu.getByRole("link", { name: "Change password" })).toHaveAttribute(
      "href",
      `/account/password?next=${encodeURIComponent("/dashboard")}`,
    );

    await user.keyboard("{Escape}");
    expect(account).toHaveAttribute("aria-expanded", "false");
    expect(account).toHaveFocus();

    await user.click(account);
    await user.click(menu.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("You have signed out.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
    expect(api.writes().map((request) => request.path)).toEqual(["/api/v1/auth/logout"]);
  });

  it("offers no people page to an analyst", async () => {
    mockApi({ [SESSION]: { body: sessionFixture("analyst") } });
    const user = userEvent.setup();
    renderRoute("/dashboard");
    await screen.findByRole("heading", { level: 1, name: "Overview" });

    await user.click(screen.getByRole("button", { name: "Account: Test Analyst, Analyst" }));
    expect(screen.queryByRole("link", { name: "People and audit trail" })).toBeNull();
    expect(screen.getAllByText(/creates scenarios, runs and analyses/)).not.toHaveLength(0);
  });
});

describe("choosing a password", () => {
  const temporary = () => ({
    [SESSION]: { body: sessionFixture("analyst", { must_change_password: true }) },
  });

  it("requires a new password after a temporary one, then continues", async () => {
    const api = mockApi({
      ...temporary(),
      [PASSWORD]: { body: sessionFixture("analyst") },
    });
    const user = userEvent.setup();
    const { router } = renderRoute("/simulation");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Choose your own password" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account/password");
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent("/simulation")}`);

    await user.type(screen.getByLabelText("Temporary password"), "temporary passphrase");
    await user.type(screen.getByLabelText("New password"), "my own long passphrase");
    await user.type(screen.getByLabelText("New password, again"), "my own long passphrase");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your password has been changed. Any other session of your account has ended.",
    );
    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: "/api/v1/auth/password",
        query: "",
        body: {
          current_password: "temporary passphrase",
          new_password: "my own long passphrase",
        },
      },
    ]);
    await user.click(screen.getByRole("link", { name: "Continue" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/simulation"));
  });

  it("checks that the new password was typed the same twice", async () => {
    const api = mockApi(temporary());
    const user = userEvent.setup();
    renderRoute("/account/password");

    await user.type(await screen.findByLabelText("Temporary password"), "temporary passphrase");
    await user.type(screen.getByLabelText("New password"), "my own long passphrase");
    await user.type(screen.getByLabelText("New password, again"), "my own long passphrasf");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    expect(screen.getByLabelText("New password, again")).toHaveAccessibleDescription(
      "The two new passwords differ; type the same one twice.",
    );
    expect(api.writes()).toEqual([]);
  });

  it("shows every policy problem the server names under the new password", async () => {
    mockApi({
      ...temporary(),
      [PASSWORD]: errorReply(422, "validation_error", "The password does not meet the policy.", [
        {
          location: "body",
          field: "new_password",
          message: "Use at least 12 characters.",
          type: "password_policy",
        },
        {
          location: "body",
          field: "new_password",
          message: "This password is too common; choose another.",
          type: "password_policy",
        },
      ]),
    });
    const user = userEvent.setup();
    renderRoute("/account/password");

    await user.type(await screen.findByLabelText("Temporary password"), "temporary passphrase");
    await user.type(screen.getByLabelText("New password"), "password");
    await user.type(screen.getByLabelText("New password, again"), "password");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    const field = screen.getByLabelText("New password");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription(
      expect.stringContaining("Use at least 12 characters."),
    );
    expect(field).toHaveAccessibleDescription(
      expect.stringContaining("This password is too common; choose another."),
    );
    expect(field).toHaveFocus();
  });

  it("goes back where it came from when changed voluntarily", async () => {
    mockApi();
    renderRoute(`/account/password?next=${encodeURIComponent("/data")}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Change your password" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the workspace" })).toHaveAttribute(
      "href",
      "/data",
    );
  });
});

describe("the introduction", () => {
  it("shares nothing with a visitor and offers to sign in", async () => {
    const api = mockApi({ [SESSION]: signedOut });
    renderRoute("/");

    expect(
      await screen.findByText(/The sample network is drawn here once you sign in/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to RUMIN" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(api.requests.map((request) => request.path)).toEqual([SESSION]);
  });

  it("draws the sample network for someone signed in", async () => {
    const api = mockApi();
    renderRoute("/");

    expect(await screen.findByText(/The illustrative sample network:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enter RUMIN" })).toHaveAttribute("href", "/dashboard");
    expect(api.requests.map((request) => request.path)).toContain("/api/v1/network");
  });
});
