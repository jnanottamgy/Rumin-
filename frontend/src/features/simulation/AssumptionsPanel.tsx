/**
 * What a run rests on: the inputs as used (each labelled by the kind of knowledge it is),
 * the assumption parameters against their defaults, the model's assumptions and
 * limitations, and the warnings the engine raised for this run.
 */
import { Badge } from "@/components/Badge";
import { ScrollRegion } from "@/components/ScrollRegion";
import { formatExact } from "@/lib/decimal";
import type {
  SimulationIssue,
  SimulationParameter,
  SimulationResolvedInput,
  SimulationStatement,
} from "@/types/api";
import { formatInputValue } from "./format";
import { KnowledgeLabel, knowledgeOf } from "./knowledge";
import styles from "./Simulation.module.css";

const SOURCE: Record<SimulationResolvedInput["source"], string> = {
  user: "Entered",
  default: "Model default",
  stored_observation: "Stored observation",
};

export function InputsTable({ inputs }: { inputs: SimulationResolvedInput[] }) {
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption className="visually-hidden">Inputs used by this run</caption>
        <thead>
          <tr>
            <th scope="col">Input</th>
            <th scope="col">Value used</th>
            <th scope="col">Kind</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {inputs.map((input) => (
            <tr key={input.id}>
              <th scope="row">{input.label}</th>
              <td className="tabular">
                {formatInputValue(input.value, input.unit_label)}
                {input.observation && (
                  <span className={styles.barSub}>
                    {input.observation.series_name}, {input.observation.period_label}
                  </span>
                )}
              </td>
              <td>
                <KnowledgeLabel kind={knowledgeOf(input.knowledge)} />
              </td>
              <td>{SOURCE[input.source]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

export function WarningList({ warnings }: { warnings: SimulationIssue[] }) {
  if (warnings.length === 0) return null;
  return (
    <ul className={styles.warnings}>
      {warnings.map((warning) => (
        <li key={`${warning.code}-${warning.field ?? ""}-${warning.message}`}>
          <Badge tone="warning">Note</Badge> {warning.message}
        </li>
      ))}
    </ul>
  );
}

export function AssumptionsPanel({
  parameters,
  assumptions,
  limitations,
  warnings,
}: {
  parameters: SimulationParameter[];
  assumptions: SimulationStatement[];
  limitations: SimulationStatement[];
  warnings: SimulationIssue[];
}) {
  return (
    <div className={styles.assumptions}>
      {warnings.length > 0 && (
        <section>
          <h4 className={styles.subheading}>For this run</h4>
          <WarningList warnings={warnings} />
        </section>
      )}
      <section>
        <h4 className={styles.subheading}>Assumption parameters</h4>
        <ScrollRegion className={styles.tableScroll}>
          <table className={styles.table} aria-label="Assumption parameters">
            <thead>
              <tr>
                <th scope="col">Parameter</th>
                <th scope="col">Used</th>
                <th scope="col">Default</th>
                <th scope="col">Why the default</th>
              </tr>
            </thead>
            <tbody>
              {parameters.map((parameter) => (
                <tr key={parameter.id}>
                  <th scope="row">
                    {parameter.label}
                    {parameter.changed_from_default && (
                      <span className={styles.barSub}>Changed from the default</span>
                    )}
                  </th>
                  <td className="tabular">{formatInputValue(parameter.value, parameter.unit)}</td>
                  <td className="tabular">
                    {parameter.default === null ? "—" : formatExact(parameter.default)}
                  </td>
                  <td className={styles.muted}>{parameter.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      </section>
      <div className={styles.statementColumns}>
        <section>
          <h4 className={styles.subheading}>Assumptions</h4>
          <ol className={styles.statements}>
            {assumptions.map((item) => (
              <li key={item.id}>
                <span className="mono">{item.id}</span>
                <p>{item.text}</p>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h4 className={styles.subheading}>Limitations</h4>
          <ol className={styles.statements}>
            {limitations.map((item) => (
              <li key={item.id}>
                <span className="mono">{item.id}</span>
                <p>{item.text}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
