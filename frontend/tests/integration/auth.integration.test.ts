/**
 * Integration: accounts, sessions and roles (Phase 10) against a running backend, through
 * the app's own service layer. The suite's administrator (created by the smoke test)
 * creates a viewer with a temporary password; the viewer must choose their own before
 * anything else, then reads but cannot write. The passwords are random, made for this run.
 */
import { randomUUID } from "node:crypto";
import { beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "@/lib/apiClient";
import { api, authApi, peopleApi } from "@/services/api";
import type { Account } from "@/types/api";
import { contractViolations } from "./contract";
import { baseUrl, options, signIn } from "./session";

const as = (cookie: string) => ({ baseUrl, headers: { Cookie: cookie } });

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

const viewerEmail = `viewer-${randomUUID().slice(0, 8)}@rumin.test`;
const temporary = `temporary ${randomUUID()}`;
const chosen = `chosen ${randomUUID()}`;
let viewer: Account;

beforeAll(async () => {
  viewer = await peopleApi.create(
    {
      name: "Integration Viewer",
      email: viewerEmail,
      role: "viewer",
      temporary_password: temporary,
    },
    options,
  );
});

describe("without a session", () => {
  it("answers only health and signing in", async () => {
    const error = await failure(api.network({ baseUrl }));
    expect(error.status).toBe(401);
    expect(error.message).toBe("Sign in to continue.");
    expect((await fetch(`${baseUrl}/health`)).status).toBe(200);
  });

  it("gives one message for a wrong password and an unknown account", async () => {
    const wrong = await failure(
      authApi.login({ email: viewerEmail, password: "not the password at all" }, { baseUrl }),
    );
    const unknown = await failure(
      authApi.login(
        { email: "nobody@rumin.test", password: "not the password at all" },
        { baseUrl },
      ),
    );
    expect([wrong.status, unknown.status]).toEqual([401, 401]);
    expect(wrong.message).toBe(unknown.message);
  });
});

describe("the suite's administrator", () => {
  it("reads its own session, with every permission", async () => {
    const session = await authApi.session(options);
    expect(contractViolations("CurrentSessionRead", session)).toEqual([]);
    expect(session.permissions).toEqual(["read", "write", "administer"]);
    expect(session.user.role).toBe("admin");
  });

  it("lists people and the audit trail, with no secret in either", async () => {
    const people = await peopleApi.list(options);
    expect(contractViolations("UserList", people)).toEqual([]);
    expect(people.items.map((person) => person.email)).toContain(viewerEmail);
    const events = await peopleApi.events(50, options);
    expect(contractViolations("AuditEventList", events)).toEqual([]);
    expect(events.items.map((event) => event.event)).toContain("user_created");
    const text = JSON.stringify([people, events]);
    expect(text).not.toContain(temporary);
    expect(text).not.toMatch(/argon2|password_hash|token/i);
  });
});

describe("a viewer", () => {
  let cookie: string;

  it("must replace the temporary password before anything else", async () => {
    cookie = await signIn(viewerEmail, temporary);
    const session = await authApi.session(as(cookie));
    expect(session.user.must_change_password).toBe(true);

    const blocked = await failure(api.network(as(cookie)));
    expect([blocked.status, blocked.code]).toEqual([403, "password_change_required"]);

    const weak = await failure(
      authApi.changePassword({ current_password: temporary, new_password: "password" }, as(cookie)),
    );
    expect(weak.status).toBe(422);
    expect(weak.details.every((detail) => detail.field === "new_password")).toBe(true);

    const changed = await authApi.changePassword(
      { current_password: temporary, new_password: chosen },
      as(cookie),
    );
    expect(changed.user.must_change_password).toBe(false);
    expect((await api.network(as(cookie))).nodes.length).toBeGreaterThan(0);
  });

  it("reads the workspace but cannot create in it", async () => {
    const scenarios = await api.scenarios.list(as(cookie));
    expect(scenarios.items).toBeDefined();
    const refused = await failure(
      api.scenarios.create(
        {
          name: "Integration: a viewer's scenario",
          description: "",
          note: "",
          shocks: [
            { variable_id: "var_brent_crude", change_type: "percent_change", value: "5", note: "" },
          ],
        },
        as(cookie),
      ),
    );
    expect([refused.status, refused.code]).toEqual([403, "forbidden"]);
    expect(refused.message).toMatch(/can read the workspace but not change it/);
    const people = await failure(peopleApi.list(as(cookie)));
    expect(people.status).toBe(403);
  });

  it("is refused a change sent from another site", async () => {
    const response = await fetch(`${baseUrl}/api/v1/analyst/sessions`, {
      method: "POST",
      headers: {
        Cookie: cookie,
        Origin: "https://evil.example",
        "Content-Type": "application/json",
      },
      body: "{}",
    });
    expect(response.status).toBe(403);
  });

  it("follows a role change on the next request, and is signed out by a deactivation", async () => {
    await peopleApi.update(viewer.id, { role: "analyst" }, options);
    expect((await authApi.session(as(cookie))).permissions).toContain("write");

    await peopleApi.update(viewer.id, { is_active: false }, options);
    const ended = await failure(authApi.session(as(cookie)));
    expect(ended.status).toBe(401);
    const again = await failure(
      authApi.login({ email: viewerEmail, password: chosen }, { baseUrl }),
    );
    expect(again.status).toBe(401);
  });
});

describe("signing out", () => {
  it("ends the session for good", async () => {
    const email = `signout-${randomUUID().slice(0, 8)}@rumin.test`;
    const password = `signout ${randomUUID()}`;
    const person = await peopleApi.create(
      { name: "Integration Sign-out", email, role: "analyst", temporary_password: password },
      options,
    );
    const cookie = await signIn(email, password);
    await authApi.logout(as(cookie));
    const ended = await failure(authApi.session(as(cookie)));
    expect(ended.status).toBe(401);
    // The administrator's own session is untouched.
    expect((await authApi.session(options)).user.role).toBe("admin");
    await peopleApi.update(person.id, { is_active: false }, options);
  });

  it("is not an error without a session", async () => {
    const response = await fetch(`${baseUrl}/api/v1/auth/logout`, { method: "POST" });
    expect(response.status).toBe(204);
  });
});
