import { describe, expect, it } from "vitest";
import {
  clampScale,
  fitTransform,
  IDENTITY,
  MAX_SCALE,
  MIN_SCALE,
  toScreen,
  zoomAt,
} from "@/features/network/panZoom";

describe("clampScale", () => {
  it("keeps zoom within the allowed range", () => {
    expect(clampScale(0.01)).toBe(MIN_SCALE);
    expect(clampScale(100)).toBe(MAX_SCALE);
    expect(clampScale(1.5)).toBe(1.5);
  });
});

describe("zoomAt", () => {
  it("keeps the point under the cursor fixed", () => {
    const start = { x: 40, y: -20, k: 1.2 };
    const cursor = { x: 300, y: 180 };
    // The world point under the cursor before zooming…
    const world = { x: (cursor.x - start.x) / start.k, y: (cursor.y - start.y) / start.k };
    const zoomed = zoomAt(start, 1.5, cursor);
    // …is still under the cursor afterwards.
    const after = toScreen(zoomed, world);
    expect(zoomed.k).toBeCloseTo(1.8);
    expect(after.x).toBeCloseTo(cursor.x);
    expect(after.y).toBeCloseTo(cursor.y);
  });

  it("stops at the zoom limits", () => {
    expect(zoomAt(IDENTITY, 100, { x: 0, y: 0 }).k).toBe(MAX_SCALE);
    expect(zoomAt(IDENTITY, 0.001, { x: 0, y: 0 }).k).toBe(MIN_SCALE);
  });
});

describe("fitTransform", () => {
  const bounds = { minX: -400, minY: -150, maxX: 400, maxY: 150 };

  it("centres the content in the viewport", () => {
    const t = fitTransform(bounds, 1000, 600, 50);
    const centre = toScreen(t, { x: 0, y: 0 });
    expect(centre.x).toBeCloseTo(500);
    expect(centre.y).toBeCloseTo(300);
  });

  it("fits the content inside the padding", () => {
    const t = fitTransform(bounds, 1000, 600, 50);
    const topLeft = toScreen(t, { x: bounds.minX, y: bounds.minY });
    const bottomRight = toScreen(t, { x: bounds.maxX, y: bounds.maxY });
    expect(topLeft.x).toBeGreaterThanOrEqual(50 - 1e-9);
    expect(topLeft.y).toBeGreaterThanOrEqual(50 - 1e-9);
    expect(bottomRight.x).toBeLessThanOrEqual(950 + 1e-9);
    expect(bottomRight.y).toBeLessThanOrEqual(550 + 1e-9);
    expect(t.k).toBeCloseTo(900 / 800); // width is the binding constraint
  });

  it("does not blow small content up past the maximum scale", () => {
    const tiny = { minX: -5, minY: -5, maxX: 5, maxY: 5 };
    expect(fitTransform(tiny, 1000, 600, 20, 1.6).k).toBe(1.6);
  });

  it("survives a degenerate (single-point) layout", () => {
    const t = fitTransform({ minX: 0, minY: 0, maxX: 0, maxY: 0 }, 800, 600);
    expect(Number.isFinite(t.k) && Number.isFinite(t.x) && Number.isFinite(t.y)).toBe(true);
  });
});
