/** Display formatting only moves the decimal point, rounds for display and adds units. */
import { describe, expect, it } from "vitest";
import {
  changeLabel,
  compactMoney,
  duration,
  elapsed,
  fullMoney,
  isFinal,
  metricChange,
  metricValue,
  nodeValue,
  percentValue,
  unitShort,
} from "@/features/scenarioLab/format";

describe("Scenario Lab formatting", () => {
  it("shortens money without losing the sign", () => {
    expect(compactMoney("-6700000")).toBe("−6.7 M");
    expect(compactMoney("375000")).toBe("+375 K");
    expect(compactMoney("306925000", false)).toBe("306.93 M");
    expect(compactMoney("0")).toBe("0");
    expect(compactMoney(null)).toBe("—");
    expect(compactMoney("not a number")).toBe("—");
  });

  it("writes money in full, to whole units", () => {
    expect(fullMoney("-6325000", "INR", true)).toBe("−6,325,000 INR");
    expect(fullMoney("12450000.4", "INR")).toBe("12,450,000 INR");
  });

  it("labels changes in the units the variable declares", () => {
    expect(changeLabel("20", "%")).toBe("+20 %");
    expect(changeLabel("0.5", "percentage points")).toBe("+0.5 pp");
    expect(changeLabel("-10", "USD per barrel")).toBe("−10 USD per barrel");
    expect(changeLabel("5", "")).toBe("+5");
    expect(percentValue("-17.6315789474")).toBe("−17.63 %");
  });

  it("writes metrics and their changes in their own units", () => {
    expect(metricValue("0.1666666667", "ratio")).toBe("16.67 %");
    expect(metricValue("4.1666666667", "times")).toBe("4.17×");
    expect(metricChange("-0.0243680595", "ratio_points")).toBe("−2.44 pp");
    expect(metricChange("-0.6373737374", "times")).toBe("−0.64×");
  });

  it("shows a pathway step's value by its unit", () => {
    expect(nodeValue("12450000", "currency")).toBe("+12.45 M");
    expect(nodeValue("0.2", "ratio")).toBe("+20%");
    expect(nodeValue("0.5", "percentage_points")).toBe("+0.5 pp");
    expect(nodeValue("20", "%")).toBe("+20%");
    expect(nodeValue(null, "currency")).toBe("");
  });

  it("reads the models' unit identifiers as a reader expects them", () => {
    expect(unitShort("percent_change")).toBe("%");
    expect(unitShort("percentage_points")).toBe("pp");
    expect(unitShort("elasticity")).toBe("");
    expect(unitShort("months")).toBe("months");
    expect(unitShort("USD per barrel")).toBe("USD per barrel");
    expect(unitShort(null)).toBe("");
  });

  it("measures stages from the server's timestamps", () => {
    expect(duration(95)).toBe("95 ms");
    expect(duration(1250)).toBe("1.3 s");
    expect(duration(null)).toBe("—");
    expect(elapsed("2026-09-24T03:27:57.129Z", "2026-09-24T03:27:57.160Z")).toBe(31);
    expect(elapsed("2026-09-24T03:27:57.129Z", null)).toBeNull();
    expect(["completed", "failed", "cancelled"].every(isFinal)).toBe(true);
    expect(isFinal("aggregating")).toBe(false);
  });
});
