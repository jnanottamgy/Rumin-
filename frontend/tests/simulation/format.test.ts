/** Display formatting moves the decimal point and rounds; it never calculates. */
import { describe, expect, it } from "vitest";
import {
  formatInputValue,
  formatMoney,
  formatMoneyCompact,
  formatParts,
  formatRatioPercent,
  formatUnitValue,
  shiftDecimal,
  withSign,
} from "@/features/simulation/format";

describe("simulation formatting", () => {
  it("moves the decimal point on the digits, exactly", () => {
    expect(shiftDecimal("0.0417419951", 2)).toBe("4.17419951");
    expect(shiftDecimal("0.2", 2)).toBe("20");
    expect(shiftDecimal("-6000000", -6)).toBe("-6");
    expect(shiftDecimal("-40598.79", -3)).toBe("-40.59879");
    expect(shiftDecimal("5", -3)).toBe("0.005");
    expect(shiftDecimal("not a number", 2)).toBe("not a number");
  });

  it("formats money in its currency, rounded for display", () => {
    expect(formatMoney("-40598.7920476483", "INR")).toBe("−40,598.79 INR");
    expect(formatMoney("5250000", "INR", { signed: true })).toBe("+5,250,000 INR");
    expect(formatMoney("0", "INR", { signed: true })).toBe("0 INR");
    expect(formatMoneyCompact("-3550000", "INR", true)).toBe("−3.55 million INR");
    expect(formatMoneyCompact("1700000", "INR", true)).toBe("+1.7 million INR");
    expect(formatMoneyCompact("640", "INR")).toBe("640 INR");
  });

  it("shows ratios as percentages and margin changes as percentage points", () => {
    expect(formatRatioPercent("0.2", 2, true)).toBe("+20 %");
    expect(formatUnitValue("0.1666666667", "ratio")).toBe("16.67 %");
    expect(formatUnitValue("-0.0127", "ratio_points", { signed: true })).toBe(
      "−1.27 percentage points",
    );
    expect(formatUnitValue("1.1", "price_relative")).toBe("1.1 × baseline");
    expect(formatUnitValue("-3600000", "INR per year", { signed: true })).toBe(
      "−3,600,000 INR per year",
    );
    expect(formatUnitValue("1320.8602617907", "US gallon per year", { exact: true })).toBe(
      "1,320.8602617907 US gallon per year",
    );
    expect(formatUnitValue(null, "INR")).toBe("—");
  });

  it("splits a figure from its unit for large display", () => {
    expect(formatParts("-3550000", "INR", { signed: true })).toEqual({
      number: "−3,550,000",
      unit: "INR",
    });
    expect(formatParts("-0.0127", "ratio_points", { signed: true })).toEqual({
      number: "−1.27",
      unit: "percentage points",
    });
    expect(formatParts("0.2", "ratio")).toEqual({ number: "20", unit: "%" });
  });

  it("signs only non-zero values", () => {
    expect(withSign("5", "5")).toBe("+5");
    expect(withSign("−5", "-5")).toBe("−5");
    expect(withSign("0", "-0.000")).toBe("0");
  });

  it("shows inputs exactly as entered, with their unit", () => {
    expect(formatInputValue("10", "% change")).toBe("10 % change");
    expect(formatInputValue("300000000", "INR per year")).toBe("300,000,000 INR per year");
    expect(formatInputValue("INR", "ISO 4217 code")).toBe("INR");
    expect(formatInputValue(null, "months")).toBe("Not set");
  });
});
