/**
 * Signing the integration suite in (Phase 10). Every API route but signing in needs a
 * session, held in an `HttpOnly` cookie; Node's fetch keeps no cookies, so each test file
 * signs in once and sends the cookie itself. `scripts/smoke_test.sh` creates the account and
 * passes its credentials in RUMIN_TEST_EMAIL and RUMIN_TEST_PASSWORD.
 */
const url = process.env.RUMIN_API_URL?.replace(/\/+$/, "");
if (!url) {
  throw new Error(
    "Set RUMIN_API_URL to a running RUMIN API (see scripts/smoke_test.sh), e.g. http://127.0.0.1:8765",
  );
}
export const baseUrl: string = url;

export const SESSION_COOKIE = "rumin_session";

/** Signs in; returns the `Cookie` header value that carries the new session. */
export async function signIn(email: string, password: string): Promise<string> {
  const response = await fetch(`${baseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(
      `Signing in as ${email} failed: HTTP ${response.status} ${await response.text()}`,
    );
  }
  const cookie = response.headers
    .getSetCookie()
    .map((line) => line.split(";")[0] ?? "")
    .find((pair) => pair.startsWith(`${SESSION_COOKIE}=`));
  if (!cookie) throw new Error("Signing in set no session cookie.");
  return cookie;
}

function credential(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Set ${name}: scripts/smoke_test.sh creates the suite's account and sets it.`);
  }
  return value;
}

/** The suite's administrator, signed in once per test file. */
export const adminCookie = await signIn(
  credential("RUMIN_TEST_EMAIL"),
  credential("RUMIN_TEST_PASSWORD"),
);

/** What the service layer needs to reach the API as the suite's administrator. */
export const options = { baseUrl, headers: { Cookie: adminCookie } };

/** The session header for the suite's own `fetch` calls. */
export const signedIn = { Cookie: adminCookie };
