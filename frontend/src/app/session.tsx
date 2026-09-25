/**
 * Who is signed in, and what they may do (Phase 10).
 *
 * The session lives on the server, behind an `HttpOnly` cookie this code never sees. The app
 * asks `GET /api/v1/auth/session` once, then listens: a 401 from any request means the
 * session ended, and `password_change_required` means the password must change first. Every
 * time the person changes (signing in, out, or the session ending) the shared data cache is
 * emptied, so nothing one person loaded is shown to the next.
 *
 * The backend enforces every rule; what this module decides only shapes the interface —
 * which controls are offered, and the reason given when one is not.
 */
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { ErrorState } from "@/components/States";
import { clearResourceCache } from "@/hooks/useApiResource";
import { ApiError, onAuthProblem } from "@/lib/apiClient";
import { RouteLoading } from "@/pages/RouteLoading";
import { authApi } from "@/services/api";
import type { CurrentSession, PersonRef, Role } from "@/types/api";

/** Why nobody is signed in: never was, chose to sign out, or the session ended. */
export type SignedOutReason = "none" | "signed_out" | "session_ended";

export type SessionState =
  | { status: "checking" }
  | { status: "signed_in"; session: CurrentSession }
  | { status: "signed_out"; reason: SignedOutReason }
  | { status: "unavailable"; error: unknown };

interface SessionContextValue {
  state: SessionState;
  signIn: (email: string, password: string) => Promise<CurrentSession>;
  signOut: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<CurrentSession>;
  /** Ask the server again (after it was unreachable, or when the account changed). */
  refresh: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export const ROLE_LABEL: Record<Role, string> = {
  viewer: "Viewer",
  analyst: "Analyst",
  admin: "Administrator",
};

export const ROLE_SUMMARY: Record<Role, string> = {
  viewer: "Reads everything in the workspace; creates and runs nothing.",
  analyst: "Reads everything; creates scenarios, runs and analyses, and changes their own.",
  admin: "Everything an analyst does, changes anyone's work, and manages people.",
};

function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "checking" });
  const stateRef = useRef(state);
  stateRef.current = state;
  const [generation, setGeneration] = useState(0);

  // `generation` has no use inside the effect: bumping it asks the server again.
  // biome-ignore lint/correctness/useExhaustiveDependencies: generation triggers a new probe
  useEffect(() => {
    let active = true;
    authApi.session().then(
      (session) => {
        if (active) setState({ status: "signed_in", session });
      },
      (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          setState((previous) =>
            previous.status === "signed_out" ? previous : { status: "signed_out", reason: "none" },
          );
        } else {
          setState({ status: "unavailable", error });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [generation]);

  useEffect(
    () =>
      onAuthProblem((problem) => {
        if (stateRef.current.status !== "signed_in") return;
        if (problem === "session_ended") {
          clearResourceCache();
          setState({ status: "signed_out", reason: "session_ended" });
        } else {
          setGeneration((value) => value + 1);
        }
      }),
    [],
  );

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await authApi.login({ email, password });
    clearResourceCache();
    setState({ status: "signed_in", session });
    return session;
  }, []);

  const signOut = useCallback(async () => {
    await authApi.logout();
    clearResourceCache();
    setState({ status: "signed_out", reason: "signed_out" });
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    const session = await authApi.changePassword({
      current_password: currentPassword,
      new_password: newPassword,
    });
    setState({ status: "signed_in", session });
    return session;
  }, []);

  const refresh = useCallback(() => {
    setState((previous) => (previous.status === "unavailable" ? { status: "checking" } : previous));
    setGeneration((value) => value + 1);
  }, []);

  const value = useMemo(
    () => ({ state, signIn, signOut, changePassword, refresh }),
    [state, signIn, signOut, changePassword, refresh],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** The root of the route table: every page, public or not, knows who is signed in. */
export function SessionRoot() {
  return (
    <SessionProvider>
      <Outlet />
    </SessionProvider>
  );
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession needs the SessionRoot route above it.");
  return value;
}

export interface Access {
  /** The signed-in person's session, or null. */
  session: CurrentSession | null;
  role: Role | null;
  /** May create scenarios, runs and stored analyses. */
  canWrite: boolean;
  /** May manage people and change anyone's work. */
  isAdmin: boolean;
  /** May change a resource with this owner (null: made before accounts, admins only). */
  canChange: (owner: PersonRef | null | undefined) => boolean;
  /**
   * Why a resource with this owner cannot be changed, in words for the interface; null when
   * it can. `what` names the resource ("scenario", "run").
   */
  changeBlocker: (owner: PersonRef | null | undefined, what: string) => string | null;
  /** Why nothing can be created, or null when it can. */
  writeBlocker: string | null;
}

export const VIEWER_REASON =
  "Your role (viewer) can read the workspace but not create or change anything. An administrator can give you the analyst role.";

export function useAccess(): Access {
  const { state } = useSession();
  const session = state.status === "signed_in" ? state.session : null;
  return useMemo(() => {
    const me = session?.user ?? null;
    const canWrite = session?.permissions.includes("write") ?? false;
    const isAdmin = session?.permissions.includes("administer") ?? false;
    const canChange = (owner: PersonRef | null | undefined) =>
      isAdmin || (canWrite && owner != null && me !== null && owner.id === me.id);
    return {
      session,
      role: me?.role ?? null,
      canWrite,
      isAdmin,
      canChange,
      writeBlocker: canWrite ? null : VIEWER_REASON,
      changeBlocker: (owner, what) => {
        if (canChange(owner)) return null;
        if (!canWrite) return VIEWER_REASON;
        return owner
          ? `This ${what} belongs to ${owner.name}; only they or an administrator can change it.`
          : `This ${what} was made before accounts existed; only an administrator can change it.`;
      },
    };
  }, [session]);
}

// Only for resolving `next` the way a browser would; never requested.
const RESOLVE_AGAINST = "https://rumin.invalid";

/**
 * Where to go after signing in: a path inside RUMIN, never another site or the sign-in page
 * itself. The value is resolved as a browser resolves a link — which drops tabs and line
 * breaks and reads `\\` as `/`, so `/<tab>/evil.example` means `//evil.example` — and only a
 * result on RUMIN's own origin is kept, rebuilt from its parts. Anything else falls back to
 * the overview.
 */
export function safeNext(value: string | null | undefined, fallback = "/dashboard"): string {
  if (!value?.startsWith("/")) return fallback;
  let url: URL;
  try {
    url = new URL(value, RESOLVE_AGAINST);
  } catch {
    return fallback;
  }
  if (url.origin !== RESOLVE_AGAINST) return fallback;
  if (url.pathname === "/login" || url.pathname.startsWith("/login/")) return fallback;
  return `${url.pathname}${url.search}${url.hash}`;
}

/** Shown when the server cannot say who is signed in: never a sign-in form that cannot work. */
function SessionUnavailable({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  useEffect(() => {
    document.title = "RUMIN is unavailable";
  }, []);
  return (
    <main style={{ maxWidth: "44rem", margin: "0 auto", padding: "var(--space-16) var(--gutter)" }}>
      <h1 className="visually-hidden">RUMIN is unavailable</h1>
      <ErrorState
        title="RUMIN cannot check your session right now"
        error={error}
        onRetry={onRetry}
      />
    </main>
  );
}

/** The pages behind sign-in: sends a visitor to sign in, and back where they were going. */
export function RequireSession() {
  const { state, refresh } = useSession();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

  if (state.status === "checking") return <RouteLoading />;
  if (state.status === "unavailable") {
    return <SessionUnavailable error={state.error} onRetry={refresh} />;
  }
  if (state.status === "signed_out") {
    const target =
      state.reason === "signed_out" ? "/login" : `/login?next=${encodeURIComponent(here)}`;
    return <Navigate to={target} replace state={{ reason: state.reason }} />;
  }
  if (state.session.user.must_change_password && location.pathname !== "/account/password") {
    return <Navigate to={`/account/password?next=${encodeURIComponent(here)}`} replace />;
  }
  return <Outlet />;
}
