/**
 * The signed-in person, in the header: who they are, what their role allows, when the
 * session ends, and the ways out (password, people for administrators, signing out).
 *
 * A disclosure — a button that shows and hides a panel of ordinary links and buttons —
 * rather than an ARIA menu: Tab moves through it, Escape closes it and returns focus.
 */
import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { ROLE_LABEL, ROLE_SUMMARY, useAccess, useSession } from "@/app/session";
import { Icon } from "@/components/Icon";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import styles from "./AccountMenu.module.css";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((part) => part?.[0]?.toUpperCase() ?? "").join("") || "?";
}

function AccountDetails({ onDone }: { onDone?: () => void }) {
  const { signOut } = useSession();
  const { session, isAdmin } = useAccess();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!session) return null;
  const { user } = session;
  const here = `${location.pathname}${location.search}`;

  return (
    <div className={styles.details}>
      <div className={styles.identity}>
        <p className={styles.name}>{user.name}</p>
        <p className={styles.email}>{user.email}</p>
        <p className={styles.role}>
          <span className={styles.roleBadge}>{ROLE_LABEL[user.role]}</span>
          <span>{ROLE_SUMMARY[user.role]}</span>
        </p>
        <p className={styles.expiry}>
          Signed in until {formatDateTime(session.expires_at)} at the latest; a stretch without
          activity ends the session sooner.
        </p>
      </div>
      <ul className={styles.links}>
        <li>
          <Link to="/guide" onClick={onDone}>
            <Icon name="info" size={14} /> Getting started
          </Link>
        </li>
        <li>
          <Link to={`/account/password?next=${encodeURIComponent(here)}`} onClick={onDone}>
            <Icon name="lock" size={14} /> Change password
          </Link>
        </li>
        {isAdmin && (
          <li>
            <Link to="/people" onClick={onDone}>
              <Icon name="people" size={14} /> People and audit trail
            </Link>
          </li>
        )}
        <li>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await signOut();
              } catch (caught) {
                setError(describeError(caught));
                setBusy(false);
              }
            }}
          >
            <Icon name="signOut" size={14} /> {busy ? "Signing out…" : "Sign out"}
          </button>
        </li>
      </ul>
      {error && (
        <p className={styles.error} role="alert">
          Could not sign out: {error}
        </p>
      )}
    </div>
  );
}

/** The header's account button and its panel (wide screens). */
export function AccountMenu() {
  const { session } = useAccess();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  // Close after navigating.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs on route change only
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  if (!session) return null;
  const { user } = session;

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={cx(styles.trigger, open && styles.open)}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={styles.avatar} aria-hidden="true">
          {initials(user.name)}
        </span>
        <span className="visually-hidden">
          Account: {user.name}, {ROLE_LABEL[user.role]}
        </span>
        <Icon name="chevronDown" size={12} />
      </button>
      <div id={panelId} className={styles.panel} hidden={!open}>
        <AccountDetails onDone={() => setOpen(false)} />
      </div>
    </div>
  );
}

/** The same details, laid out inside the mobile menu. */
export function AccountSection() {
  return (
    <section className={styles.section} aria-label="Account">
      <AccountDetails />
    </section>
  );
}
