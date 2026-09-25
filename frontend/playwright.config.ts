/**
 * The launch verification suite (Phase 10): the built web app in Chromium against a running
 * API — sign-in, every page on a desktop and a phone (axe, console, overflow, timings), and
 * the core workflows. scripts/e2e.sh prepares a fresh database and servers and runs it;
 * RUMIN_E2E_URL can point it at any running RUMIN, e.g. the production stack.
 */
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.RUMIN_E2E_URL ?? "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e-results/artifacts",
  globalSetup: "./e2e/global-setup.ts",
  // The workflows change shared records; one worker keeps the run deterministic.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: "e2e-results/results.json" }]],
  use: {
    baseURL,
    ignoreHTTPSErrors: process.env.RUMIN_E2E_INSECURE === "1",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      // WebGL for the 3D universe without a GPU.
      args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"],
    },
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "phone",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
