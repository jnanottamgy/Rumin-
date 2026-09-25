/**
 * Every page, signed in as an administrator, on a desktop and on a phone: it renders its
 * heading and names itself in the tab, logs no error, does not scroll sideways, and axe finds
 * no accessibility violation. Timings are recorded (not judged) for the readiness report.
 */
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoOverflow, recordTimings, watchConsole } from "./checks";
import { ADMIN_STATE, type PreparedIds, prepared } from "./state";

test.use({ storageState: ADMIN_STATE });

const PAGES: readonly [string, (ids: PreparedIds) => string | null][] = [
  ["introduction", () => "/"],
  ["overview", () => "/dashboard"],
  ["guide", () => "/guide"],
  ["universe", () => "/universe"],
  ["3D universe", () => "/universe/3d"],
  ["graph", () => "/graph"],
  ["graph around a company", () => "/graph?focus=company%3Aco_aerisca_airways"],
  ["data", () => "/data"],
  ["a series", (ids) => (ids.series ? `/data/series/${ids.series}` : null)],
  ["an instrument", (ids) => (ids.instrument ? `/data/instruments/${ids.instrument}` : null)],
  ["an ingestion job", (ids) => (ids.job ? `/data/jobs/${ids.job}` : null)],
  ["scenario library", () => "/scenarios"],
  ["a new scenario from a template", () => "/scenarios/new?template=crude_oil_airline"],
  ["an executed scenario", (ids) => `/scenarios/${ids.scenario}`],
  ["comparison", (ids) => `/scenarios/compare?execution=${ids.execution}`],
  ["simulation", () => "/simulation"],
  ["a simulation run", (ids) => `/simulation/runs/${ids.run}`],
  ["intelligence", () => "/intelligence"],
  ["an entity dossier", () => "/intelligence/company%3Aco_aerisca_airways"],
  ["a stored analysis", (ids) => `/intelligence/analyses/${ids.analysis}`],
  ["analyst", () => "/analyst"],
  ["a conversation", (ids) => `/analyst?session=${ids.session}`],
  ["system", () => "/system"],
  ["people", () => "/people"],
  ["change password", () => "/account/password?next=%2Fdashboard"],
  ["a page that does not exist", () => "/no-such-page"],
];

for (const [name, pathOf] of PAGES) {
  test(`${name}`, async ({ page }, testInfo) => {
    const path = pathOf(prepared());
    test.skip(path === null, "No such record in this database.");
    const problems = watchConsole(page);

    await page.goto(path ?? "/", { waitUntil: "networkidle" });
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page).toHaveTitle(/RUMIN/);
    await page.waitForTimeout(250); // let late layout (charts, the 3D scene) settle

    await recordTimings(page, testInfo);
    await expectNoOverflow(page);
    await expectAccessible(page);
    expect(problems, "console errors").toEqual([]);
  });
}
