/**
 * The accounting bridge from the fuel-cost change to the change in operating profit, as
 * a waterfall: each step starts where the previous one ended; the total starts at zero.
 * The engine checks that the steps add up before storing a run; this only draws them.
 *
 * Built as a table (step, amount, bar) so every value is text — the bars are a picture
 * of the amounts beside them, not the only way to read them.
 */
import { toNumber } from "@/lib/decimal";
import type { SimulationBridge } from "@/types/api";
import { formatMoney } from "./format";
import styles from "./Simulation.module.css";

export function spanScale(values: number[]): (value: number) => number {
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const pad = (high - low) * 0.04 || 1;
  const start = low - pad;
  const span = high + pad - start;
  return (value) => ((value - start) / span) * 100;
}

export function BridgeChart({
  bridge,
  currency,
  totalLabel,
}: {
  bridge: SimulationBridge;
  currency: string;
  totalLabel: string;
}) {
  let running = 0;
  const steps = bridge.steps.map((step) => {
    const amount = toNumber(step.value);
    const from = running;
    running += amount;
    return { ...step, from, to: running };
  });
  const total = toNumber(bridge.total.value);
  const scale = spanScale([...steps.flatMap((step) => [step.from, step.to]), total]);
  const zero = scale(0);

  return (
    <table className={styles.barTable}>
      <caption className="visually-hidden">
        Bridge from the fuel-cost change to the change in operating profit
      </caption>
      <thead className="visually-hidden">
        <tr>
          <th scope="col">Step</th>
          <th scope="col">Effect on operating profit ({currency})</th>
          <th scope="col">Bar</th>
        </tr>
      </thead>
      <tbody>
        {steps.map((step) => {
          const left = scale(Math.min(step.from, step.to));
          const right = scale(Math.max(step.from, step.to));
          return (
            <tr key={step.output}>
              <th scope="row" className={styles.barLabel}>
                {step.label}
              </th>
              <td className={styles.barValue}>
                {formatMoney(step.value, currency, { signed: true })}
              </td>
              <td className={styles.barCell} aria-hidden="true">
                <span className={styles.barZero} style={{ left: `${zero}%` }} />
                <span
                  className={styles.bar}
                  data-tone="step"
                  data-direction={step.to < step.from ? "down" : "up"}
                  style={{ left: `${left}%`, width: `${Math.max(0.4, right - left)}%` }}
                />
              </td>
            </tr>
          );
        })}
        <tr className={styles.barTotalRow}>
          <th scope="row" className={styles.barLabel}>
            {totalLabel}
          </th>
          <td className={styles.barValue}>
            <strong>{formatMoney(bridge.total.value, currency, { signed: true })}</strong>
          </td>
          <td className={styles.barCell} aria-hidden="true">
            <span className={styles.barZero} style={{ left: `${zero}%` }} />
            <span
              className={styles.bar}
              data-tone="total"
              data-direction={total < 0 ? "down" : "up"}
              style={{
                left: `${Math.min(zero, scale(total))}%`,
                width: `${Math.max(0.4, Math.abs(scale(total) - zero))}%`,
              }}
            />
          </td>
        </tr>
      </tbody>
    </table>
  );
}
