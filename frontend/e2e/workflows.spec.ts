/**
 * The core workflows in a real browser: building and executing a scenario from a template,
 * the Analyst answering with sources, and what a viewer may and may not do. The scenario's
 * figures are HYPOTHETICAL round numbers for the fictional Aerisca Airways.
 */
import { expect, test } from "@playwright/test";
import { expectAccessible, watchConsole } from "./checks";
import { ADMIN_STATE, prepared, VIEWER_STATE } from "./state";

test.describe("as an administrator", () => {
  test.use({ storageState: ADMIN_STATE });

  test("a scenario from a template: figures, live preview, save and execute", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Stores a scenario: once is enough.");
    test.setTimeout(120_000);
    const problems = watchConsole(page);
    await page.goto("/scenarios/new?template=crude_oil_airline", { waitUntil: "networkidle" });
    await expect(
      page.getByRole("heading", { level: 1, name: "Crude oil shock on an airline" }),
    ).toBeVisible();
    const execute = page.getByRole("button", { name: "Save and execute" });
    await expect(execute).toBeDisabled();

    // The scenario's own name; each stress case's is "Name of stress case N".
    await page.getByLabel("Name", { exact: true }).fill("E2E: crude on Aerisca (HYPOTHETICAL)");
    await page
      .getByLabel("Company in the knowledge graph")
      .selectOption({ label: "Aerisca Airways" });
    await page.getByLabel("Reporting currency").fill("INR");
    await page.getByLabel("Annual revenue").fill("300000000");
    await page.getByLabel("Annual operating costs").fill("250000000");
    await page.getByLabel("Exchange rate").fill("80");
    await page.getByLabel("Baseline jet fuel price", { exact: true }).fill("750");
    await page.getByLabel("Baseline jet fuel price unit").selectOption("usd_per_kilolitre");
    await page.getByLabel("Annual fuel consumption", { exact: true }).fill("1000");
    await page.getByLabel("Annual fuel consumption unit").selectOption("kilolitre");

    // The backend computes a live preview as the figures arrive; nothing is stored yet.
    await expect(execute).toBeEnabled({ timeout: 20_000 });
    await expect(page.getByText(/Live preview/).first()).toBeVisible();
    await execute.click();

    await expect(page.getByText(/^Completed in .* stored and reproducible$/)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page).toHaveURL(/\/scenarios\/[0-9a-f-]{36}\?execution=/);
    await expect(page.getByText(/^Showing stored execution · v1/)).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Results" })).toContainText(
      /profit before tax/i,
    );
    await expectAccessible(page);
    expect(problems, "console errors").toEqual([]);
  });

  test("the Analyst answers a suggested question and cites its sources", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto("/analyst", { waitUntil: "networkidle" });
    const suggestion = page.getByRole("button", { name: /exposed to|Which companies/i }).first();
    await suggestion.click();
    const conversation = page.getByRole("region", { name: "Conversation" });
    await expect(conversation.getByRole("article").last()).toContainText(/Sources|source/i, {
      timeout: 30_000,
    });
    await expectAccessible(page);
    expect(problems, "console errors").toEqual([]);
  });

  test("people and the audit trail list the run's accounts", async ({ page }) => {
    await page.goto("/people", { waitUntil: "networkidle" });
    const accounts = page.getByRole("list", { name: "Accounts" });
    await expect(accounts.getByRole("listitem", { name: "E2E Viewer" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Security audit trail" })).toContainText(
      "Account created",
    );
  });
});

test.describe("as a viewer", () => {
  test.use({ storageState: VIEWER_STATE });

  test("reads everything, previews, and is told why nothing can be stored", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto(`/scenarios/${prepared().scenario}`, { waitUntil: "networkidle" });
    await expect(
      page.getByText(/Your role \(viewer\) can read the workspace/).first(),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Save new version" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Execute" })).toBeDisabled();

    await page.goto("/simulation", { waitUntil: "networkidle" });
    await expect(page.getByRole("button", { name: "Run simulation" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Check inputs" })).toBeEnabled();

    await page.goto("/people", { waitUntil: "networkidle" });
    await expect(page.getByText("Only administrators manage people")).toBeVisible();
    expect(problems, "console errors").toEqual([]);
  });
});
