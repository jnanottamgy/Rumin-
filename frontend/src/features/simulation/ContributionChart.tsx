/**
 * How much of an output each scenario change accounts for (Shapley values, computed by
 * the engine). Bars grow from zero: right for an increase, left for a decrease. Credits add
 * up to the output; the total row shows it.
 */
import { useId, useState } from "react";
import { toNumber } from "@/lib/decimal";
import type { SimulationContribution, SimulationOutput } from "@/types/api";
import { spanScale } from "./BridgeChart";
import { formatUnitValue } from "./format";
import { KnowledgeGlyph } from "./knowledge";
import styles from "./Simulation.module.css";

export function ContributionChart({
  contributions,
  outputs,
  initial,
  method,
}: {
  contributions: SimulationContribution[];
  outputs: SimulationOutput[];
  initial?: string;
  method: string;
}) {
  const available = contributions.filter((item) => item.items.length > 0);
  const [selected, setSelected] = useState(
    available.find((item) => item.output === initial)?.output ?? available[0]?.output ?? "",
  );
  const selectId = useId();
  const current = available.find((item) => item.output === selected);
  const output = outputs.find((item) => item.id === selected);
  if (!current || !output) return null;

  const values = current.items.map((item) => toNumber(item.value));
  const scale = spanScale([...values, toNumber(output.value)]);
  const zero = scale(0);

  return (
    <div className={styles.contributions}>
      <div className={styles.inlineField}>
        <label htmlFor={selectId}>Result</label>
        <select
          id={selectId}
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {available.map((item) => (
            <option key={item.output} value={item.output}>
              {item.label}
            </option>
          ))}
        </select>
      </div>
      <table className={styles.barTable}>
        <caption className="visually-hidden">Contributions to {current.label}</caption>
        <thead className="visually-hidden">
          <tr>
            <th scope="col">Scenario change</th>
            <th scope="col">Contribution ({output.unit})</th>
            <th scope="col">Bar</th>
          </tr>
        </thead>
        <tbody>
          {current.items.map((item) => {
            const at = scale(toNumber(item.value));
            return (
              <tr key={item.input}>
                <th scope="row" className={styles.barLabel}>
                  <KnowledgeGlyph kind="scenario_input" />
                  {item.label}
                </th>
                <td className={styles.barValue}>
                  {formatUnitValue(item.value, output.unit, { signed: true })}
                </td>
                <td className={styles.barCell} aria-hidden="true">
                  <span className={styles.barZero} style={{ left: `${zero}%` }} />
                  <span
                    className={styles.bar}
                    data-tone="contribution"
                    data-direction={at < zero ? "down" : "up"}
                    style={{
                      left: `${Math.min(zero, at)}%`,
                      width: `${Math.max(0.4, Math.abs(at - zero))}%`,
                    }}
                  />
                </td>
              </tr>
            );
          })}
          <tr className={styles.barTotalRow}>
            <th scope="row" className={styles.barLabel}>
              {output.label}
            </th>
            <td className={styles.barValue}>
              <strong>{formatUnitValue(output.value, output.unit, { signed: true })}</strong>
            </td>
            <td className={styles.barCell} aria-hidden="true" />
          </tr>
        </tbody>
      </table>
      <p className={styles.note}>{method}</p>
    </div>
  );
}
