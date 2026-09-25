/**
 * People (Phase 10, administrators only): the accounts, their roles, temporary passwords,
 * signing someone out everywhere, and the security audit trail. The API refuses all of it
 * to anyone else; this page only says so instead of offering controls that would fail.
 */
import { type FormEvent, useEffect, useId, useState } from "react";
import { ROLE_LABEL, ROLE_SUMMARY, useAccess } from "@/app/session";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import {
  Field,
  type FormProblems,
  noProblems,
  PasswordRules,
  problemsFrom,
} from "@/features/account/fields";
import { invalidateResource, useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { peopleApi } from "@/services/api";
import type { Account, AuditEvent, Role } from "@/types/api";
import authStyles from "./AuthPage.module.css";
import styles from "./PeoplePage.module.css";

const PEOPLE_KEY = "people";
const EVENTS_KEY = "audit-events";
const ROLES: Role[] = ["viewer", "analyst", "admin"];

function refreshPeople() {
  invalidateResource(PEOPLE_KEY);
  invalidateResource(EVENTS_KEY);
}

function RoleSelect({
  id,
  value,
  onChange,
}: {
  id: string;
  value: Role;
  onChange: (role: Role) => void;
}) {
  return (
    <div className={authStyles.field}>
      <label htmlFor={id} className={authStyles.label}>
        Role
      </label>
      <select
        id={id}
        className={authStyles.input}
        value={value}
        aria-describedby={`${id}-summary`}
        onChange={(event) => onChange(event.target.value as Role)}
      >
        {ROLES.map((role) => (
          <option key={role} value={role}>
            {ROLE_LABEL[role]}
          </option>
        ))}
      </select>
      <p id={`${id}-summary`} className={authStyles.hint}>
        {ROLE_SUMMARY[value]}
      </p>
    </div>
  );
}

function Outcome({ ok, error }: { ok: string | null; error: string | null }) {
  if (error) {
    return (
      <p className={authStyles.message} data-tone="error" role="alert">
        <Icon name="alert" size={14} /> {error}
      </p>
    );
  }
  return ok ? (
    <p className={authStyles.message} data-tone="good" role="status">
      <Icon name="check" size={14} /> {ok}
    </p>
  ) : null;
}

function CreateAccount() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<FormProblems>(noProblems);
  const [created, setCreated] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = noProblems();
    if (!name.trim()) found.fields.name = ["Give the person's name."];
    if (!email.trim()) found.fields.email = ["Give their e-mail address."];
    if (!password) found.fields.temporary_password = ["Set a temporary password."];
    setCreated(null);
    if (Object.keys(found.fields).length > 0) {
      setProblems(found);
      return;
    }
    setBusy(true);
    setProblems(noProblems());
    try {
      const account = await peopleApi.create({
        name: name.trim(),
        email: email.trim(),
        role,
        temporary_password: password,
      });
      setCreated(
        `Account created for ${account.name} (${account.email}) as ${ROLE_LABEL[account.role].toLowerCase()}. Give them the temporary password privately; they must replace it when they first sign in.`,
      );
      setName("");
      setEmail("");
      setPassword("");
      refreshPeople();
    } catch (error) {
      setProblems(problemsFrom(error, ["name", "email", "role", "temporary_password"]));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className={authStyles.form} onSubmit={(event) => void submit(event)} noValidate>
      <Field
        id="person-name"
        label="Name"
        autoComplete="off"
        value={name}
        onChange={setName}
        errors={problems.fields.name}
        maxLength={120}
      />
      <Field
        id="person-email"
        label="E-mail address"
        type="email"
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        value={email}
        onChange={setEmail}
        errors={problems.fields.email}
      />
      <RoleSelect id="person-role" value={role} onChange={setRole} />
      <Field
        id="person-password"
        label="Temporary password"
        type={showPassword ? "text" : "password"}
        autoComplete="new-password"
        value={password}
        onChange={setPassword}
        errors={problems.fields.temporary_password}
        hint={<PasswordRules />}
      />
      <label className={authStyles.check}>
        <input
          type="checkbox"
          checked={showPassword}
          onChange={(event) => setShowPassword(event.target.checked)}
        />
        Show password
      </label>
      <Outcome ok={created} error={problems.form} />
      <div className={authStyles.actions}>
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </Button>
      </div>
    </form>
  );
}

function ManageAccount({ account }: { account: Account }) {
  const [role, setRole] = useState<Role>(account.role);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [passwordErrors, setPasswordErrors] = useState<string[]>([]);
  const id = useId();

  const act = async (label: string, action: () => Promise<string>) => {
    setBusy(label);
    setOk(null);
    setError(null);
    try {
      setOk(await action());
      refreshPeople();
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setBusy(null);
    }
  };

  const resetPassword = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordErrors([]);
    if (!password) {
      setPasswordErrors(["Set a temporary password."]);
      return;
    }
    setBusy("password");
    setOk(null);
    setError(null);
    try {
      await peopleApi.resetPassword(account.id, password);
      setPassword("");
      setOk(
        `${account.name} has a temporary password and must replace it at their next sign-in. Their sessions have ended.`,
      );
      refreshPeople();
    } catch (caught) {
      const found = problemsFrom(caught, ["temporary_password"]);
      setPasswordErrors(found.fields.temporary_password ?? []);
      setError(found.form);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.manage}>
      <div className={styles.manageGroup}>
        <RoleSelect id={`${id}-role`} value={role} onChange={setRole} />
        <div className={authStyles.actions}>
          <Button
            size="sm"
            disabled={busy !== null || role === account.role}
            onClick={() =>
              void act("role", async () => {
                const updated = await peopleApi.update(account.id, { role });
                return `${updated.name} is now ${ROLE_LABEL[updated.role].toLowerCase()}. It applies to their next request.`;
              })
            }
          >
            Save role
          </Button>
        </div>
      </div>

      <form
        className={styles.manageGroup}
        onSubmit={(event) => void resetPassword(event)}
        noValidate
      >
        <Field
          id={`${id}-password`}
          label="New temporary password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          errors={passwordErrors}
          hint="They must replace it at their next sign-in; their sessions end now."
        />
        <div className={authStyles.actions}>
          <Button size="sm" type="submit" disabled={busy !== null}>
            Set temporary password
          </Button>
        </div>
      </form>

      <div className={styles.manageGroup}>
        <p className={authStyles.hint}>
          Signing out everywhere ends every session of this account at once. Deactivating also stops
          new sign-ins; their scenarios, runs and analyses stay in the workspace.
        </p>
        <div className={authStyles.actions}>
          <Button
            size="sm"
            disabled={busy !== null}
            onClick={() =>
              void act("revoke", async () => {
                await peopleApi.revokeSessions(account.id);
                return `Every session of ${account.name} has ended.`;
              })
            }
          >
            Sign out everywhere
          </Button>
          <Button
            size="sm"
            variant={account.is_active ? "danger" : "secondary"}
            disabled={busy !== null}
            onClick={() =>
              void act("active", async () => {
                const updated = await peopleApi.update(account.id, {
                  is_active: !account.is_active,
                });
                return updated.is_active
                  ? `${updated.name} can sign in again.`
                  : `${updated.name} is deactivated and signed out everywhere.`;
              })
            }
          >
            {account.is_active ? "Deactivate account" : "Reactivate account"}
          </Button>
        </div>
      </div>

      <div className={styles.manageOutcome}>
        <Outcome ok={ok} error={error} />
      </div>
    </div>
  );
}

/** One person: who they are, their role and state, and (for others) what can be done. */
function AccountItem({ account, isMe }: { account: Account; isMe: boolean }) {
  const [open, setOpen] = useState(false);
  const nameId = useId();
  const panelId = useId();
  return (
    <li className={styles.account} aria-labelledby={nameId}>
      <div className={styles.accountRow}>
        <div className={styles.who}>
          <p className={styles.person}>
            <span id={nameId}>{account.name}</span>
            {isMe && <Badge tone="outline">You</Badge>}
          </p>
          <p className={styles.email}>{account.email}</p>
        </div>
        <dl className={styles.facts}>
          <div>
            <dt>Role</dt>
            <dd>{ROLE_LABEL[account.role]}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd className={styles.badges}>
              {account.is_active ? (
                <Badge tone="good">Active</Badge>
              ) : (
                <Badge tone="neutral">Deactivated</Badge>
              )}
              {account.must_change_password && <Badge tone="warning">Temporary password</Badge>}
            </dd>
          </div>
          <div>
            <dt>Last sign-in</dt>
            <dd className="tabular">
              {account.last_login_at ? formatDateTime(account.last_login_at) : "Never"}
            </dd>
          </div>
        </dl>
        <div className={styles.accountActions}>
          {isMe ? (
            <span className={styles.muted}>Change your own password from the account menu.</span>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              aria-expanded={open}
              aria-controls={panelId}
              aria-label={`Manage ${account.name}`}
              onClick={() => setOpen((value) => !value)}
              iconAfter={<Icon name={open ? "chevronDown" : "chevronRight"} size={12} />}
            >
              Manage
            </Button>
          )}
        </div>
      </div>
      {!isMe && (
        <div id={panelId} hidden={!open}>
          {open && <ManageAccount account={account} />}
        </div>
      )}
    </li>
  );
}

function Accounts() {
  const { session } = useAccess();
  const people = useApiResource(PEOPLE_KEY, () => peopleApi.list());
  if (people.status === "loading") return <LoadingState label="Loading the accounts…" />;
  if (people.status === "error") return <ErrorState error={people.error} onRetry={people.reload} />;
  return (
    <ul className={styles.accounts} aria-label="Accounts">
      {people.data.items.map((account) => (
        <AccountItem key={account.id} account={account} isMe={account.id === session?.user.id} />
      ))}
    </ul>
  );
}

const EVENT_LABEL: Record<string, string> = {
  login_succeeded: "Signed in",
  login_failed: "Sign-in failed",
  login_throttled: "Sign-in refused: too many attempts",
  logout: "Signed out",
  password_changed: "Password changed",
  password_change_failed: "Password change refused",
  password_reset: "Temporary password set",
  user_created: "Account created",
  user_updated: "Account changed",
  sessions_revoked: "Signed out everywhere",
};

const REASON: Record<string, string> = {
  unknown_account: "no such account",
  wrong_password: "wrong password",
  inactive: "deactivated account",
};

/** Which limit made someone wait (the server's `login_throttled` scopes). */
const SCOPE: Record<string, string> = {
  client: "from this address",
  account_client: "for this account, from this address",
  account: "for this account, from anywhere",
};

function describePair(key: string, value: unknown): string | null {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const [before, after] = value;
  if (key === "is_active") return after ? "reactivated" : "deactivated";
  if (key === "role") return `role ${String(before)} → ${String(after)}`;
  if (key === "name") return `name “${String(before)}” → “${String(after)}”`;
  return null;
}

/** An event's detail in words; unknown keys are shown as they are, never dropped. */
export function describeDetail(event: AuditEvent): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(event.detail)) {
    const pair = describePair(key, value);
    if (pair) parts.push(pair);
    else if (key === "reason") parts.push(REASON[String(value)] ?? String(value));
    else if (key === "scope") parts.push(SCOPE[String(value)] ?? String(value));
    else if (key === "sessions") parts.push(`${String(value)} session(s) ended`);
    else if (key === "other_sessions_ended") parts.push(`${String(value)} other session(s) ended`);
    else if (key === "via") parts.push(`via the ${String(value)}`);
    else parts.push(`${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`);
  }
  return parts.join(" · ");
}

function AuditTrail() {
  const events = useApiResource(EVENTS_KEY, () => peopleApi.events(100));
  if (events.status === "loading") return <LoadingState label="Loading the audit trail…" />;
  if (events.status === "error") return <ErrorState error={events.error} onRetry={events.reload} />;
  if (events.data.items.length === 0) {
    return <EmptyState title="No security events yet" />;
  }
  return (
    <section
      className={styles.tableScroll}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: the table scrolls sideways on narrow screens, and a scrolling region must be reachable from the keyboard.
      tabIndex={0}
      aria-label="Security audit trail"
    >
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Event</th>
            <th scope="col">By</th>
            <th scope="col">About</th>
            <th scope="col">Client</th>
            <th scope="col">Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.data.items.map((event) => (
            <tr key={event.id}>
              <td className={`tabular ${styles.when}`}>{formatDateTime(event.occurred_at)}</td>
              <th scope="row">{EVENT_LABEL[event.event] ?? event.event}</th>
              <td>{event.actor?.name ?? "—"}</td>
              <td>{event.subject?.name ?? "—"}</td>
              <td className="mono">{event.client ?? "—"}</td>
              <td className={styles.muted}>{describeDetail(event) || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function PeoplePage() {
  const { isAdmin } = useAccess();

  useEffect(() => {
    document.title = "People — RUMIN";
  }, []);

  if (!isAdmin) {
    return (
      <div className={styles.page}>
        <PageHeader eyebrow="Administration" title="People" />
        <EmptyState title="Only administrators manage people">
          Ask an administrator to create an account, change a role or reset a password.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Administration"
        title="People"
        description="Who can sign in, and what each role allows. Everyone signed in reads the whole workspace; roles decide who creates and changes. Accounts are made here — there is no public sign-up — and every sign-in, change and refusal is recorded in the audit trail below."
      />
      <div className={styles.grid}>
        <Panel title="Accounts" description="Newest changes apply on the person's next request.">
          <Accounts />
        </Panel>
        <Panel
          title="Add a person"
          description="Set a temporary password and pass it on privately: RUMIN sends no e-mail."
        >
          <CreateAccount />
        </Panel>
      </div>
      <Panel
        title="Security audit trail"
        description="The latest 100 events: sign-ins and failures, password changes, account changes and sessions ended. No password or session token is ever recorded."
        actions={
          <Button size="sm" variant="ghost" onClick={() => invalidateResource(EVENTS_KEY)}>
            Refresh
          </Button>
        }
      >
        <AuditTrail />
      </Panel>
    </div>
  );
}
