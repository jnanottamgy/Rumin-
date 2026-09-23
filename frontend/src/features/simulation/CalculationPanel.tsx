/**
 * The calculation, step by step, as the engine recorded it: every equation evaluated,
 * with the values that went in and the value that came out (exact, as stored). Monthly
 * steps are shown one month at a time; the equations follow, with their terms, the
 * assumptions they rest on and their limitations.
 */
import { useId, useState } from "react";
import { Badge } from "@/components/Badge";
import { formatExact, isDecimalString } from "@/lib/decimal";
import type { SimulationEquationUse, SimulationStep } from "@/types/api";
import styles from "./Simulation.module.css";

function exact(value: string): string {
  return isDecimalString(value) ? formatExact(value) : value;
}

function StepValue({ symbol, value, unit }: { symbol: string; value: string; unit: string }) {
  return (
    <span className={styles.stepValue}>
      <span className={styles.symbol}>{symbol}</span> ={" "}
      <span className="tabular">{exact(value)}</span>
      {unit && <span className={styles.stepUnit}> {unit}</span>}
    </span>
  );
}

export function StepsTable({ steps, months }: { steps: SimulationStep[]; months: number }) {
  const [month, setMonth] = useState<number | null>(null);
  const selectId = useId();
  const shown = steps.filter((step) => step.month === month);
  return (
    <div className={styles.steps}>
      <div className={styles.inlineField}>
        <label htmlFor={selectId}>Steps for</label>
        <select
          id={selectId}
          value={month ?? ""}
          onChange={(event) => setMonth(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">The whole run (annual and horizon totals)</option>
          {Array.from({ length: months }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
            <option key={index} value={index + 1}>
              Month {index + 1}
            </option>
          ))}
        </select>
        <span className={styles.inlineNote}>
          {steps.length} steps in all, in the order they were calculated
        </span>
      </div>
      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <caption className="visually-hidden">
            Calculation steps{month ? ` for month ${month}` : " for the whole run"}
          </caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Equation</th>
              <th scope="col">Result</th>
              <th scope="col">From</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((step) => (
              <tr key={step.sequence}>
                <td className="tabular">{step.sequence}</td>
                <th scope="row" className={styles.stepName}>
                  <span className="mono">{step.equation}</span> {step.label}
                </th>
                <td>
                  <StepValue {...step.output} />
                </td>
                <td>
                  <ul className={styles.stepInputs}>
                    {step.inputs.map((item) => (
                      <li key={item.symbol}>
                        <StepValue {...item} />
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function EquationList({ equations }: { equations: SimulationEquationUse[] }) {
  return (
    <ol className={styles.equations}>
      {equations.map((equation) => (
        <li key={equation.id} className={styles.equation} id={`equation-${equation.id}`}>
          <div className={styles.equationHead}>
            <span className="mono">{equation.id}</span>
            <h4>{equation.name}</h4>
            {!equation.used && <Badge tone="outline">Not used in this run</Badge>}
          </div>
          <p className={styles.formula}>{equation.formula}</p>
          <p className={styles.equationText}>{equation.explanation}</p>
          <dl className={styles.terms}>
            {[equation.output, ...equation.terms].map((term) => (
              <div key={term.symbol}>
                <dt className={styles.symbol}>{term.symbol}</dt>
                <dd>
                  {term.meaning} <span className={styles.stepUnit}>({term.unit})</span>
                </dd>
              </div>
            ))}
          </dl>
          {(equation.assumptions.length > 0 || equation.limitations.length > 0) && (
            <details className={styles.equationNotes}>
              <summary>
                Rests on {equation.assumptions.length} assumption
                {equation.assumptions.length === 1 ? "" : "s"}; {equation.limitations.length}{" "}
                limitation{equation.limitations.length === 1 ? "" : "s"}
              </summary>
              <ul>
                {equation.assumptions.map((item) => (
                  <li key={item.id}>
                    <span className="mono">{item.id}</span> {item.text}
                  </li>
                ))}
                {equation.limitations.map((item) => (
                  <li key={item.id}>
                    <span className="mono">{item.id}</span> {item.text}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}
