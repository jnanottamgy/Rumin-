/**
 * Signing in and out, and choosing a password, through the pages themselves. The
 * administrator's credentials come from the environment; the newcomer and their temporary
 * password from the global setup.
 */
import { expect, test } from "@playwright/test";
import { expectAccessible, watchConsole } from "./checks";
import { credential, prepared } from "./state";

test("a visitor is sent to sign in, then back to the page asked for", async ({ page }) => {
  await page.goto("/scenarios", { waitUntil: "networkidle" });
  await expect(page).toHaveURL(/\/login\?next=%2Fscenarios$/);
  await expect(page.getByRole("heading", { level: 1, name: "Sign in to RUMIN" })).toBeVisible();
  await expectAccessible(page);

  await page.getByLabel("E-mail address").fill(credential("RUMIN_TEST_EMAIL"));
  await page.getByLabel("Password", { exact: true }).fill(credential("RUMIN_TEST_PASSWORD"));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/scenarios$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("a wrong password is refused with one message, and the password asked again", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("E-mail address").fill(credential("RUMIN_TEST_EMAIL"));
  await page.getByLabel("Password", { exact: true }).fill("certainly not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText(/The e-mail address or password is incorrect/);
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
});

test("the introduction shares nothing with a visitor", async ({ page }) => {
  const problems = watchConsole(page);
  const api: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) api.push(new URL(request.url()).pathname);
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByText(/The sample network is drawn here once you sign in/)).toBeVisible();
  expect(api).toEqual(["/api/v1/auth/session"]);
  await expectAccessible(page);
  // The one expected error: the session check answers 401 for a visitor.
  expect(problems.filter((problem) => !problem.includes("401"))).toEqual([]);
});

test("a newcomer chooses their own password before anything else", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Once is enough: it changes the password.");
  const { newcomer } = prepared();
  await page.goto("/simulation");
  await page.getByLabel("E-mail address").fill(newcomer.email);
  await page.getByLabel("Password", { exact: true }).fill(newcomer.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/account\/password\?next=%2Fsimulation$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Choose your own password" }),
  ).toBeVisible();
  await expectAccessible(page);
  const chosen = `chosen ${Date.now()} passphrase`;
  await page.getByLabel("Temporary password").fill(newcomer.password);
  await page.getByLabel("New password", { exact: true }).fill(chosen);
  await page.getByLabel("New password, again").fill(chosen);
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("status")).toHaveText(/Your password has been changed/);
  await page.getByRole("link", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/simulation$/);
});

test("signing out ends the session", async ({ page }, testInfo) => {
  await page.goto("/login");
  await page.getByLabel("E-mail address").fill(credential("RUMIN_TEST_EMAIL"));
  await page.getByLabel("Password", { exact: true }).fill(credential("RUMIN_TEST_PASSWORD"));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  if (testInfo.project.name === "phone") {
    await page.getByRole("button", { name: "Open menu" }).click();
  } else {
    await page.getByRole("button", { name: /^Account:/ }).click();
  }
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText("You have signed out.")).toBeVisible();
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
});
