/**
 * The Analyst's words and figures in the browser: citations split out of the text, the
 * order sources are cited in, figures written as the API writes them (half-even, fixed
 * places), and conversations exported as Markdown with their sources.
 */
import { describe, expect, it } from "vitest";
import { answerMarkdown, sessionMarkdown } from "@/features/analyst/exportMarkdown";
import {
  citedOrder,
  duration,
  fixed,
  moneyText,
  percentText,
  segments,
} from "@/features/analyst/format";
import type { AnalystAnswer } from "@/types/api";
import { analystFixtures, sessionTurn } from "../fixtures/analyst";

describe("citations", () => {
  it("splits a paragraph into text and the evidence it cites", () => {
    expect(segments("Revenue rose [E1]. Costs too [E2, E4].")).toEqual([
      { kind: "text", text: "Revenue rose " },
      { kind: "cite", ids: ["E1"] },
      { kind: "text", text: ". Costs too " },
      { kind: "cite", ids: ["E2", "E4"] },
      { kind: "text", text: "." },
    ]);
    expect(segments("No citation here, only [brackets].")).toEqual([
      { kind: "text", text: "No citation here, only [brackets]." },
    ]);
  });

  it("orders sources by their first citation and drops ids the answer does not hold", () => {
    const answer = sessionTurn(1).answer as AnalystAnswer;
    const order = citedOrder(answer);
    expect(order.slice(0, 3)).toEqual(["E1", "E2", "E11"]);
    expect(new Set(order).size).toBe(order.length);
    const known = new Set(answer.evidence.map((item) => item.id));
    expect(order.every((id) => known.has(id))).toBe(true);

    const withUnknown = structuredClone(answer);
    withUnknown.blocks = [{ type: "text", role: "answer", text: "A claim [E99] and [E1]." }];
    expect(citedOrder(withUnknown)).toEqual(["E1"]);
  });
});

describe("figures", () => {
  it("rounds half to even at a fixed number of places, as the API's sentences do", () => {
    expect(fixed("18.425", 2)).toBe("18.42");
    expect(fixed("18.435", 2)).toBe("18.44");
    expect(fixed("18.4251", 2)).toBe("18.43");
    expect(fixed("3.6", 2)).toBe("3.60");
    expect(fixed("-11", 2)).toBe("−11.00");
    expect(fixed("-0.004", 2)).toBe("0.00");
    expect(fixed("9587500.5", 0)).toBe("9,587,500");
    expect(fixed("9587501.5", 0)).toBe("9,587,502");
    expect(fixed("not a number", 2)).toBeNull();
  });

  it("writes percentages and amounts with their sign and unit", () => {
    expect(percentText("1.1666666667")).toBe("+1.17 %");
    expect(percentText("-11")).toBe("−11.00 %");
    expect(percentText("0")).toBe("0.00 %");
    expect(percentText(null)).toBe("—");
    expect(moneyText("3500000", "INR", true)).toBe("+3,500,000 INR");
    expect(moneyText("-5500000", "INR", true)).toBe("−5,500,000 INR");
    expect(moneyText("250000000", "INR")).toBe("250,000,000 INR");
    expect(moneyText("12.5", "USD")).toBe("12.50 USD");
    expect(moneyText("1234.5", "USD")).toBe("1,234 USD");
    expect(moneyText(undefined, "INR")).toBe("—");
  });

  it("writes durations in milliseconds or seconds", () => {
    expect(duration(17)).toBe("17 ms");
    expect(duration(1234)).toBe("1.2 s");
    expect(duration(null)).toBe("—");
  });
});

describe("Markdown", () => {
  it("writes an answer with its tables, cards and the sources it cites", () => {
    const text = answerMarkdown(sessionTurn(4), "https://rumin.test");
    expect(text).toMatch(/^### What if Brent crude rises 20% for Aerisca Airways\?/);
    expect(text).toContain("**Operating profit −5,500,000 INR under Brent crude oil price +20 %");
    expect(text).toContain(
      "- Revenue: +3,500,000 INR (+1.17 %) against a baseline of 300,000,000 INR",
    );
    expect(text).toContain("Sources:");
    expect(text).toMatch(/- \[E2\] Preview, not stored: Preview for Aerisca Airways/);
  });

  it("escapes table cells and keeps links to the records", () => {
    const turn = sessionTurn(2);
    const text = answerMarkdown(turn, "https://rumin.test");
    expect(text).toContain(
      "| Company | Channel | How | Weakest evidence | Models that can simulate it |",
    );
    expect(text).toMatch(/- \[E\d+\] [^\n]+ \(https:\/\/rumin\.test\/[^)\s]+\)/);
    const piped = structuredClone(turn);
    const table = piped.answer?.blocks.find((block) => block.type === "table");
    if (table?.type !== "table") throw new Error("no table");
    table.rows[0] = { ...table.rows[0], cells: { company: "A | B" } } as (typeof table.rows)[0];
    expect(answerMarkdown(piped)).toContain("| A \\| B |");
  });

  it("says a failed question was not answered, and heads a conversation with its limits", () => {
    const failed = analystFixtures.turnFailed();
    expect(answerMarkdown(failed)).toContain(
      "_The question could not be answered; the error was logged._",
    );
    const text = sessionMarkdown(analystFixtures.session());
    expect(text).toMatch(/^# What does RUMIN know about Aerisca Airways\?/);
    expect(text).toContain("not forecasts");
    expect(text.match(/^### /gm)).toHaveLength(7);
  });
});
