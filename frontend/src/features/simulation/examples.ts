/**
 * Example inputs, per model. They are HYPOTHETICAL round numbers — not market data and
 * not any airline's figures — chosen so every result can be checked by hand: 1,000 kL a
 * year at 750 USD per kL and 80 INR per USD is a fuel bill of exactly 5,000,000 INR a
 * month. The page labels them as an example wherever they appear.
 */
import type { FormState } from "./form";

type ExampleValues = Record<string, { value: string; unit?: string }>;

const EXAMPLES: Record<string, { summary: string; values: ExampleValues }> = {
  airline_fuel_cost: {
    summary:
      "A hypothetical airline with a fuel bill of 5,000,000 INR a month, half hedged for " +
      "three months, passing 40 % of fuel-cost changes on to fares after two months. Crude " +
      "oil rises 10 %.",
    values: {
      crude_oil_change: { value: "10" },
      jet_fuel_price: { value: "750", unit: "usd_per_kilolitre" },
      fx_rate: { value: "80" },
      reporting_currency: { value: "INR" },
      annual_revenue: { value: "300000000" },
      annual_operating_costs: { value: "250000000" },
      annual_fuel_consumption: { value: "1000", unit: "kilolitre" },
      hedge_ratio: { value: "50" },
      hedge_months: { value: "3" },
      fare_pass_through: { value: "40" },
      fare_pass_through_lag: { value: "2" },
    },
  },
};

export function exampleSummary(modelId: string): string | null {
  return EXAMPLES[modelId]?.summary ?? null;
}

/** `form` with the model's example values filled in (other fields cleared to defaults). */
export function withExample(modelId: string, form: FormState): FormState | null {
  const example = EXAMPLES[modelId];
  if (!example) return null;
  const next: FormState = {};
  for (const [id, field] of Object.entries(form)) {
    const value = example.values[id];
    next[id] = value
      ? { value: value.value, unit: value.unit ?? field.unit, stored: false }
      : { ...field, value: "", stored: false };
  }
  return next;
}
