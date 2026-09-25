/**
 * A stored run: the headline result, baseline against scenario, and every view of how it
 * was reached — the pathway and the months, contributions, sensitivity, the calculation,
 * the inputs and assumptions, and provenance. Everything is read from what the run
 * stored; nothing is recalculated here.
 */
import { type ReactNode, useState } from "react";
import { ScrollRegion } from "@/components/ScrollRegion";
import { ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { formatDateTime } from "@/lib/format";
import { simulationApi } from "@/services/api";
import type { SimulationModelDetail, SimulationOutput, SimulationRun } from "@/types/api";
import { AssumptionsPanel, InputsTable, WarningList } from "./AssumptionsPanel";
import { BridgeChart } from "./BridgeChart";
import { EquationList, StepsTable } from "./CalculationPanel";
import { ContributionChart } from "./ContributionChart";
import { formatParts, formatUnitValue } from "./format";
import { KnowledgeGlyph, KnowledgeLabel, knowledgeOf } from "./knowledge";
import { MonthlyChart } from "./MonthlyChart";
import { PathwayDiagram } from "./PathwayDiagram";
import { ProvenancePanel } from "./ProvenancePanel";
import { comparisons, headline, monthlyPlan } from "./presentation";
import { SensitivityPanel } from "./SensitivityPanel";
import styles from "./Simulation.module.css";
import { Tabs } from "./Tabs";

function currencyOf(output: SimulationOutput | null): string {
  const match = /^([A-Z]{3})/.exec(output?.unit ?? "");
  return match?.[1] ?? "";
}

function Figure({ output, hero = false }: { output: SimulationOutput; hero?: boolean }) {
  const parts = formatParts(output.value, output.unit, { signed: output.kind === "simulated" });
  return (
    <div className={hero ? styles.hero : styles.tile}>
      <dt>
        <KnowledgeGlyph kind={knowledgeOf(output.kind)} />
        {output.label}
      </dt>
      <dd className={hero ? styles.heroValue : styles.tileValue}>
        {parts.number}
        {parts.unit && <span className={styles.valueUnit}> {parts.unit}</span>}
      </dd>
      <dd className={styles.tileSource}>
        {output.description} <span className="mono">{output.equation}</span>
      </dd>
    </div>
  );
}

export function RunResults({
  run,
  model,
  animate,
}: {
  run: SimulationRun;
  model: SimulationModelDetail;
  animate: boolean;
}) {
  const [tab, setTab] = useState("pathway");
  const explanation = useApiResource(`simulation:explanation:${run.id}`, () =>
    simulationApi.explanation(run.id),
  );
  const provenance = useApiResource(`simulation:provenance:${run.id}`, () =>
    simulationApi.provenance(run.id),
  );
  const { hero, tiles } = headline(run, model);
  const rows = comparisons(run);
  const plan = monthlyPlan(run, model);
  const currency = currencyOf(hero);
  const totalLabel =
    run.outputs.find((output) => output.id === run.bridge?.total.output)?.label ?? "Total";

  const needExplanation = (render: (data: NonNullable<typeof explanation.data>) => ReactNode) =>
    explanation.status === "success" ? (
      render(explanation.data)
    ) : explanation.status === "error" ? (
      <ErrorState error={explanation.error} onRetry={explanation.reload} />
    ) : (
      <LoadingState label="Loading the explanation…" />
    );

  return (
    <article className={styles.results} aria-labelledby="run-title">
      <header className={styles.resultsHeader}>
        <div>
          <h2 id="run-title" className={styles.resultsTitle}>
            {run.label ?? "Simulation run"}
          </h2>
          <p className={styles.resultsMeta}>
            {run.model_name} {run.model_version}, {run.horizon_months}-month horizon
            {run.entity ? `, ${run.entity.name}` : ""}. Calculated {formatDateTime(run.finished_at)}
            .
          </p>
        </div>
        <KnowledgeLabel kind="simulated" />
      </header>

      <p className={styles.disclaimer}>{run.note}</p>

      <dl className={styles.figures}>
        {hero && <Figure output={hero} hero />}
        {tiles.map((output) => (
          <Figure key={output.id} output={output} />
        ))}
      </dl>

      {rows.length > 0 && (
        <ScrollRegion className={styles.tableScroll}>
          <table className={styles.table}>
            <caption className={styles.tableCaption}>Baseline and scenario</caption>
            <thead>
              <tr>
                <th scope="col">
                  <span className="visually-hidden">Result</span>
                </th>
                <th scope="col">Baseline</th>
                <th scope="col">Scenario</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  <td className="tabular">
                    {formatUnitValue(row.baseline.value, row.baseline.unit)}
                  </td>
                  <td className="tabular">
                    {formatUnitValue(row.scenario.value, row.scenario.unit)}
                  </td>
                  <td className="tabular">
                    {row.change
                      ? formatUnitValue(row.change.value, row.change.unit, { signed: true })
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}

      <WarningList warnings={run.warnings} />

      <Tabs
        label="Views of this run"
        active={tab}
        onChange={setTab}
        items={[
          {
            id: "pathway",
            label: "Pathway and months",
            content: () => (
              <div className={styles.stack}>
                {needExplanation((data) => (
                  <PathwayDiagram
                    nodes={data.pathway.nodes}
                    links={data.pathway.links}
                    animationKey={animate ? run.id : null}
                  />
                ))}
                {plan && (
                  <section>
                    <h3 className={styles.figureTitle}>Month by month</h3>
                    <MonthlyChart
                      scenario={plan.scenario}
                      baseline={plan.baseline}
                      change={plan.change}
                      table={run.monthly}
                    />
                  </section>
                )}
                {run.bridge && (
                  <section>
                    <h3 className={styles.figureTitle}>How the steps add up</h3>
                    <BridgeChart bridge={run.bridge} currency={currency} totalLabel={totalLabel} />
                    <p className={styles.note}>
                      Each step is an output of the run; the engine checks that they add up to the
                      total before the run is stored.
                    </p>
                  </section>
                )}
              </div>
            ),
          },
          {
            id: "contributions",
            label: "Contributions",
            content: () =>
              run.contributions.some((item) => item.items.length > 0) ? (
                needExplanation((data) => (
                  <ContributionChart
                    contributions={run.contributions}
                    outputs={run.outputs}
                    initial={model.bridge_total ?? undefined}
                    method={data.method.contributions ?? ""}
                  />
                ))
              ) : (
                <p className={styles.muted}>
                  Every scenario change is zero, so there is nothing to attribute.
                </p>
              ),
          },
          {
            id: "sensitivity",
            label: "Sensitivity",
            content: () => <SensitivityPanel run={run} model={model} />,
          },
          {
            id: "calculation",
            label: "Calculation",
            content: () =>
              needExplanation((data) => (
                <div className={styles.stack}>
                  <StepsTable steps={data.steps} months={run.horizon_months} />
                  <section>
                    <h3 className={styles.figureTitle}>Equations</h3>
                    <EquationList equations={data.equations} />
                  </section>
                </div>
              )),
          },
          {
            id: "inputs",
            label: "Inputs and assumptions",
            content: () => (
              <div className={styles.stack}>
                <InputsTable inputs={run.inputs} />
                {needExplanation((data) => (
                  <AssumptionsPanel
                    parameters={data.parameters}
                    assumptions={data.assumptions}
                    limitations={data.limitations}
                    warnings={[]}
                  />
                ))}
              </div>
            ),
          },
          {
            id: "provenance",
            label: "Provenance",
            content: () =>
              provenance.status === "success" ? (
                <ProvenancePanel provenance={provenance.data} />
              ) : provenance.status === "error" ? (
                <ErrorState error={provenance.error} onRetry={provenance.reload} />
              ) : (
                <LoadingState label="Loading provenance…" />
              ),
          },
        ]}
      />
    </article>
  );
}
