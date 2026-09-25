/**
 * Accounts and sessions for page tests (Phase 10). The people are made up for the tests —
 * "Test Administrator" and friends on the reserved `.test` domain — and the shapes follow
 * the API contract (`CurrentSessionRead`, `UserRead`, `AuditEventRead`).
 */
import type { Account, AuditEvent, CurrentSession, Permission, Role } from "@/types/api";

export const PEOPLE: Record<Role, { id: string; name: string; email: string }> = {
  admin: {
    id: "00000000-0000-4000-8000-00000000a001",
    name: "Test Administrator",
    email: "admin@rumin.test",
  },
  analyst: {
    id: "00000000-0000-4000-8000-00000000a002",
    name: "Test Analyst",
    email: "analyst@rumin.test",
  },
  viewer: {
    id: "00000000-0000-4000-8000-00000000a003",
    name: "Test Viewer",
    email: "viewer@rumin.test",
  },
};

const PERMISSIONS: Record<Role, Permission[]> = {
  viewer: ["read"],
  analyst: ["read", "write"],
  admin: ["read", "write", "administer"],
};

export function accountFixture(role: Role = "admin", overrides: Partial<Account> = {}): Account {
  return {
    ...PEOPLE[role],
    role,
    is_active: true,
    must_change_password: false,
    last_login_at: "2026-09-25T08:00:00Z",
    password_changed_at: "2026-09-01T08:00:00Z",
    created_at: "2026-09-01T08:00:00Z",
    ...overrides,
  };
}

export function sessionFixture(role: Role = "admin", user: Partial<Account> = {}): CurrentSession {
  return {
    user: accountFixture(role, user),
    permissions: PERMISSIONS[role],
    expires_at: "2026-09-25T20:00:00Z",
    idle_expires_at: "2026-09-25T10:00:00Z",
  };
}

export function auditEventsFixture(): { items: AuditEvent[] } {
  const admin = { id: PEOPLE.admin.id, name: PEOPLE.admin.name };
  const analyst = { id: PEOPLE.analyst.id, name: PEOPLE.analyst.name };
  return {
    items: [
      {
        id: "00000000-0000-4000-8000-0000000e0003",
        occurred_at: "2026-09-25T09:10:00Z",
        event: "user_updated",
        actor: admin,
        subject: analyst,
        client: "127.0.0.1",
        request_id: "req-test-0003",
        detail: { role: ["viewer", "analyst"] },
      },
      {
        id: "00000000-0000-4000-8000-0000000e0002",
        occurred_at: "2026-09-25T09:05:00Z",
        event: "login_failed",
        actor: null,
        subject: analyst,
        client: "127.0.0.1",
        request_id: "req-test-0002",
        detail: { reason: "wrong_password" },
      },
      {
        id: "00000000-0000-4000-8000-0000000e0001",
        occurred_at: "2026-09-25T08:00:00Z",
        event: "login_succeeded",
        actor: admin,
        subject: admin,
        client: "127.0.0.1",
        request_id: "req-test-0001",
        detail: {},
      },
    ],
  };
}
