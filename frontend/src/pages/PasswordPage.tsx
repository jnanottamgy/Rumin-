/**
 * Choosing one's own password (Phase 10): required after an administrator sets a temporary
 * one, and open to anyone signed in from the account menu. Changing it ends every other
 * session of the account; this one continues.
 */
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { safeNext, useSession } from "@/app/session";
import { Button, ButtonLink } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { AuthFrame } from "@/features/account/AuthFrame";
import {
  Field,
  type FormProblems,
  noProblems,
  PasswordRules,
  problemsFrom,
} from "@/features/account/fields";
import { describeError } from "@/lib/apiClient";
import styles from "./AuthPage.module.css";

export function PasswordPage() {
  const { state, changePassword, signOut } = useSession();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const user = state.status === "signed_in" ? state.session.user : null;
  const forced = user?.must_change_password ?? false;

  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [problems, setProblems] = useState<FormProblems>(noProblems);
  const currentRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const doneRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    document.title = `${forced ? "Choose your password" : "Change your password"} — RUMIN`;
  }, [forced]);

  useEffect(() => {
    if (done) doneRef.current?.focus();
  }, [done]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = noProblems();
    if (!current) {
      found.fields.current_password = [
        forced ? "Enter the temporary password you were given." : "Enter your current password.",
      ];
    }
    if (!password) found.fields.new_password = ["Choose a new password."];
    else if (confirmation !== password) {
      found.fields.confirmation = ["The two new passwords differ; type the same one twice."];
    }
    if (Object.keys(found.fields).length > 0) {
      setProblems(found);
      const first = found.fields.current_password
        ? currentRef
        : found.fields.new_password
          ? passwordRef
          : confirmationRef;
      first.current?.focus();
      return;
    }
    setBusy(true);
    setProblems(noProblems());
    try {
      await changePassword(current, password);
      setCurrent("");
      setPassword("");
      setConfirmation("");
      setDone(true);
    } catch (error) {
      const found = problemsFrom(error, ["current_password", "new_password"]);
      setProblems(found);
      if (found.fields.current_password) currentRef.current?.focus();
      else if (found.fields.new_password) passwordRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const leave = async () => {
    try {
      await signOut();
    } catch (error) {
      setProblems({ fields: {}, form: describeError(error) });
    }
  };

  return (
    <AuthFrame
      aside={
        forced ? (
          <Button variant="ghost" size="sm" onClick={() => void leave()}>
            Sign out
          </Button>
        ) : (
          <Link to={next} className={styles.topLink}>
            Back to the workspace
          </Link>
        )
      }
    >
      <section className={styles.card} aria-labelledby="password-title">
        <div className={styles.heading}>
          <p className="eyebrow">{user ? `${user.name} · ${user.email}` : "Your account"}</p>
          <h1 id="password-title" className={styles.title}>
            {forced ? "Choose your own password" : "Change your password"}
          </h1>
          <p className={styles.lede}>
            {forced
              ? "An administrator set a temporary password for this account. Replace it with one only you know before you continue."
              : "Every other session of your account ends when the password changes; this one continues."}
          </p>
        </div>

        {problems.form && (
          <p className={styles.message} data-tone="error" role="alert">
            <Icon name="alert" size={14} /> {problems.form}
          </p>
        )}

        {done ? (
          <>
            <p
              ref={doneRef}
              tabIndex={-1}
              className={styles.message}
              data-tone="good"
              role="status"
            >
              <Icon name="check" size={14} /> Your password has been changed. Any other session of
              your account has ended.
            </p>
            <div className={styles.actions}>
              <ButtonLink to={next} variant="primary" iconAfter={<Icon name="arrowRight" />}>
                Continue
              </ButtonLink>
            </div>
          </>
        ) : (
          <form className={styles.form} onSubmit={(event) => void submit(event)} noValidate>
            {/* Lets password managers file the new password under the right account. */}
            <input
              type="email"
              name="username"
              autoComplete="username"
              value={user?.email ?? ""}
              readOnly
              hidden
            />
            <Field
              id="password-current"
              label={forced ? "Temporary password" : "Current password"}
              type={showPasswords ? "text" : "password"}
              autoComplete="current-password"
              value={current}
              onChange={setCurrent}
              errors={problems.fields.current_password}
              inputRef={currentRef}
              required
            />
            <Field
              id="password-new"
              label="New password"
              type={showPasswords ? "text" : "password"}
              autoComplete="new-password"
              value={password}
              onChange={setPassword}
              errors={problems.fields.new_password}
              hint={<PasswordRules />}
              inputRef={passwordRef}
              required
            />
            <Field
              id="password-confirmation"
              label="New password, again"
              type={showPasswords ? "text" : "password"}
              autoComplete="new-password"
              value={confirmation}
              onChange={setConfirmation}
              errors={problems.fields.confirmation}
              inputRef={confirmationRef}
              required
            />
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={showPasswords}
                onChange={(event) => setShowPasswords(event.target.checked)}
              />
              Show passwords
            </label>
            <Button type="submit" variant="primary" className={styles.submit} disabled={busy}>
              {busy ? "Saving…" : forced ? "Save and continue" : "Change password"}
            </Button>
          </form>
        )}
      </section>
    </AuthFrame>
  );
}
