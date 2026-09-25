import { describe, expect, it } from "vitest";
import {
  addDecimals,
  compareDecimals,
  decimalPlaces,
  formatExact,
  formatRounded,
  isDecimalString,
  multiplyDecimals,
  roundDecimal,
} from "@/lib/decimal";

describe("exact decimal strings", () => {
  it("groups every digit without floating point", () => {
    expect(formatExact("1234567.891")).toBe("1,234,567.891");
    expect(formatExact("12345678901234567890.123456789012345678")).toBe(
      "12,345,678,901,234,567,890.123456789012345678",
    );
    expect(formatExact("-0.5")).toBe("−0.5");
    expect(formatExact("-0")).toBe("0");
    expect(formatExact("0.000000000000000001")).toBe("0.000000000000000001");
  });

  it("rounds for display half away from zero, on the digits themselves", () => {
    expect(formatRounded("5.13140747776876", 2)).toBe("5.13");
    expect(formatRounded("2.345", 2)).toBe("2.35");
    expect(formatRounded("-2.345", 2)).toBe("−2.35");
    expect(formatRounded("9.995", 2)).toBe("10");
    expect(formatRounded("0.005", 2)).toBe("0.01");
    expect(formatRounded("-0.001", 2)).toBe("0");
    expect(formatRounded("5.1", 2)).toBe("5.1"); // never pads with zeros
    // 0.1 + 0.2 in floating point is 0.30000000000000004; decimal strings are exact.
    expect(formatRounded("0.30000000000000004", 16)).toBe("0.3");
  });

  it("recognises plain decimals only", () => {
    expect(isDecimalString("14.250000")).toBe(true);
    expect(isDecimalString("1.5E+3")).toBe(false);
    expect(isDecimalString("1,000")).toBe(false);
    expect(decimalPlaces("14.250000")).toBe(6);
    expect(formatExact("n/a")).toBe("n/a"); // anything else is shown as it is
  });

  it("adds, multiplies, compares and rounds exactly", () => {
    expect(addDecimals("0.1", "0.2")).toBe("0.3"); // 0.30000000000000004 in floating point
    expect(addDecimals("20", "-10")).toBe("10");
    expect(addDecimals("-0.25", "0.25")).toBe("0");
    expect(multiplyDecimals("80", "0.95")).toBe("76");
    expect(multiplyDecimals("300000000", "1.1")).toBe("330000000");
    expect(multiplyDecimals("-0.5", "0.5")).toBe("-0.25");
    expect(compareDecimals("10", "9.999")).toBe(1);
    expect(compareDecimals("-1", "-1.0")).toBe(0);
    expect(compareDecimals("0.1", "0.25")).toBe(-1);
    expect(roundDecimal("1.005", 2)).toBe("1.01");
    expect(roundDecimal("-2.5", 0)).toBe("-3");
    expect(roundDecimal("76.000000", 6)).toBe("76");
    expect(addDecimals("x", "1")).toBeNull();
  });
});
