import { describe, expect, it } from "vitest";
import {
  type ChartPoint,
  dateTime,
  nearestIndex,
  nextPeriodFollows,
  niceTicks,
  segments,
  timeTicks,
  withinDays,
} from "@/features/data/chartMath";

const point = (date: string, value: number | null, flagged = false): ChartPoint => ({
  key: date,
  time: dateTime(date),
  value,
  flagged,
});

describe("chart arithmetic", () => {
  it("chooses round ticks that cover the data", () => {
    expect(niceTicks(0.8, 14.25)).toEqual({ ticks: [0, 5, 10, 15], domain: [0, 15] });
    expect(niceTicks(-1.2, 3.4).ticks).toEqual([-2, -1, 0, 1, 2, 3, 4]);
    expect(niceTicks(5, 5).ticks.length).toBeGreaterThan(1); // a flat series still has a scale
    expect(niceTicks(0.1, 0.3).ticks).toEqual([0.1, 0.15, 0.2, 0.25, 0.3]);
  });

  it("never draws a line across a missing value", () => {
    const points = [
      point("2001-01-01", 1),
      point("2002-01-01", 2),
      point("2003-01-01", null),
      point("2004-01-01", 3),
      point("2005-01-01", 4),
    ];
    const runs = segments(points, nextPeriodFollows("annual"));
    expect(runs.map((run) => run.map((p) => p.key))).toEqual([
      ["2001-01-01", "2002-01-01"],
      ["2004-01-01", "2005-01-01"],
    ]);
  });

  it("never draws a line across a period that is absent from the data", () => {
    const points = [point("2001-01-01", 1), point("2002-01-01", 2), point("2005-01-01", 3)];
    const runs = segments(points, nextPeriodFollows("annual"));
    expect(runs.map((run) => run.length)).toEqual([2, 1]);
    const monthly = [point("2024-01-01", 1), point("2024-02-01", 2), point("2024-04-01", 3)];
    expect(segments(monthly, nextPeriodFollows("monthly")).length).toBe(2);
  });

  it("treats a weekend as contiguous but a long trading gap as a break", () => {
    const days = [point("2026-06-05", 1), point("2026-06-08", 2), point("2026-06-22", 3)];
    expect(segments(days, withinDays(7)).map((run) => run.length)).toEqual([2, 1]);
  });

  it("finds the period nearest the pointer", () => {
    const points = [point("2001-01-01", 1), point("2002-01-01", 2), point("2003-01-01", 3)];
    expect(nearestIndex(points, dateTime("2001-05-01"))).toBe(0);
    expect(nearestIndex(points, dateTime("2001-09-01"))).toBe(1);
    expect(nearestIndex(points, dateTime("2010-01-01"))).toBe(2);
    expect(nearestIndex([], 0)).toBe(-1);
  });

  it("labels time axes with calendar units that fit", () => {
    const years = timeTicks(dateTime("1990-01-01"), dateTime("2025-01-01"), 8);
    expect(years.map((tick) => tick.label)).toEqual([
      "1990",
      "1995",
      "2000",
      "2005",
      "2010",
      "2015",
      "2020",
      "2025",
    ]);
    const months = timeTicks(dateTime("2026-03-02"), dateTime("2026-09-19"), 8);
    expect(months[0]?.label).toBe("Apr 2026");
  });
});
