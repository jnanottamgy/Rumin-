/** Checks every page gets: axe, console errors, horizontal overflow and timings. */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

/** Console errors and uncaught exceptions while a page is open. */
export function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text().slice(0, 300)}`);
  });
  page.on("pageerror", (error) => problems.push(`exception: ${error.message.slice(0, 300)}`));
  return problems;
}

export async function expectAccessible(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const found = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact}): ${violation.nodes
        .slice(0, 3)
        .map((node) => node.target.join(" "))
        .join(" | ")}`,
  );
  expect(found, "axe violations").toEqual([]);
}

export async function expectNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow in pixels").toBeLessThanOrEqual(0);
}

/** First contentful paint, largest contentful paint, load, and what was transferred. */
export async function recordTimings(page: Page, testInfo: TestInfo): Promise<void> {
  const timings = await page.evaluate(async () => {
    const lcp = await new Promise<number | null>((resolve) => {
      let latest: number | null = null;
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) latest = entry.startTime;
      }).observe({ type: "largest-contentful-paint", buffered: true });
      setTimeout(() => resolve(latest), 100);
    });
    const navigation = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    const fcp = performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null;
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const transferred = (kind: RegExp) =>
      resources
        .filter((entry) => kind.test(entry.name))
        .reduce((sum, entry) => sum + entry.transferSize, 0);
    return {
      fcpMs: fcp === null ? null : Math.round(fcp),
      lcpMs: lcp === null ? null : Math.round(lcp),
      domContentLoadedMs: navigation ? Math.round(navigation.domContentLoadedEventEnd) : null,
      loadMs: navigation ? Math.round(navigation.loadEventEnd) : null,
      scriptBytes: transferred(/\.js(\?|$)/),
      styleBytes: transferred(/\.css(\?|$)/),
      apiRequests: resources.filter((entry) => entry.name.includes("/api/")).length,
    };
  });
  await testInfo.attach("timings", {
    body: JSON.stringify(timings),
    contentType: "application/json",
  });
}
