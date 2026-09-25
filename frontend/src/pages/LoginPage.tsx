/**
 * Signing in (Phase 10). Accounts are created by an administrator; there is no sign-up and
 * no e-mail recovery. After signing in the visitor goes back to where they were heading
 * (`?next=`, only ever a path inside RUMIN).
 */
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { type SignedOutReason, safeNext, useSession } from "@/app/session";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { AuthFrame } from "@/features/account/AuthFrame";
import { Field, type FormProblems, noProblems, problemsFrom } from "@/features/account/fields";
import { ApiError } from "@/lib/apiClient";
import styles from "./AuthPage.module.css";
import { RouteLoading } from "./RouteLoading";

const NOTICE: Partial<Record<SignedOutReason, string>> = {
  signed_out: "You have signed out.",
  session_ended: "Your session ended. Sign in again to continue where you were.",
};

export function LoginPage() {
  const { state, signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const reason = (location.state as { reason?: SignedOutReason } | null)?.reason;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<FormProblems>(noProblems);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const signingIn = useRef(false);

  useEffect(() => {
    document.title = "Sign in — RUMIN";
  }, []);

  if (state.status === "checking") return <RouteLoading />;
  // Already signed in (and not in the middle of signing in here): nothing to do on this page.
  if (state.status === "signed_in" && !signingIn.current) return <Navigate to={next} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = noProblems();
    if (!email.trim()) found.fields.email = ["Enter your e-mail address."];
    if (!password) found.fields.password = ["Enter your password."];
    if (Object.keys(found.fields).length > 0) {
      setProblems(found);
      (found.fields.email ? emailRef : passwordRef).current?.focus();
      return;
    }
    setBusy(true);
    setProblems(noProblems());
    signingIn.current = true;
    try {
      await signIn(email.trim(), password);
      navigate(next, { replace: true });
    } catch (error) {
      signingIn.current = false;
      setProblems(problemsFrom(error, ["email", "password"]));
      if (error instanceof ApiError && error.status === 401) {
        setPassword("");
        passwordRef.current?.focus();
      }
    } finally {
      setBusy(false);
    }
  };

  const notice = reason ? NOTICE[reason] : undefined;

  return (
    <AuthFrame
      aside={
        <Link to="/" className={styles.topLink}>
          About RUMIN
        </Link>
      }
    >
      <section className={styles.card} aria-labelledby="login-title">
        <div className={styles.heading}>
          <p className="eyebrow">Workspace access</p>
          <h1 id="login-title" className={styles.title}>
            Sign in to RUMIN
          </h1>
          <p className={styles.lede}>Use the account an administrator created for you.</p>
        </div>

        {notice && !problems.form && (
          <p className={styles.message} role="status">
            <Icon name="info" size={14} /> {notice}
          </p>
        )}
        {problems.form && (
          <p className={styles.message} data-tone="error" role="alert">
            <Icon name="alert" size={14} /> {problems.form}
          </p>
        )}

        <form className={styles.form} onSubmit={(event) => void submit(event)} noValidate>
          <Field
            id="login-email"
            label="E-mail address"
            type="email"
            name="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            inputMode="email"
            value={email}
            onChange={setEmail}
            errors={problems.fields.email}
            inputRef={emailRef}
            required
          />
          <Field
            id="login-password"
            label="Password"
            type={showPassword ? "text" : "password"}
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
            errors={problems.fields.password}
            inputRef={passwordRef}
            required
          />
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
            />
            Show password
          </label>
          <Button type="submit" variant="primary" className={styles.submit} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className={styles.help}>
          Forgotten your password, or locked out after several attempts? An administrator can set a
          temporary password for you; RUMIN never sends passwords by e-mail.
        </p>
      </section>
    </AuthFrame>
  );
}
