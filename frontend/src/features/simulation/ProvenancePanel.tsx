/**
 * Where a run came from, and a check that it can be reproduced: the model version and its
 * definition hash, the engine, the hashes of the inputs and the result, the knowledge-graph
 * build and the relationships it confirmed, any stored observation used (with its licence),
 * and every transmission path. "Check reproducibility" re-executes the run from its stored
 * snapshot on the server and compares the hashes.
 */
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { StatusIndicator } from "@/components/StatusIndicator";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { describeError } from "@/lib/apiClient";
import { formatExact } from "@/lib/decimal";
import { formatDateTime } from "@/lib/format";
import { simulationApi } from "@/services/api";
import type {
  EvidenceStatus,
  SimulationGraphEdge,
  SimulationProvenance,
  SimulationVerification,
} from "@/types/api";
import { shortHash } from "./format";
import styles from "./Simulation.module.css";

function Hash({ value }: { value: string }) {
  return (
    <span className={styles.hash} title={value}>
      <span className="mono">{shortHash(value)}</span>
      <span className="visually-hidden">{value.slice(12)}</span>…
    </span>
  );
}

function evidenceLabel(edge: SimulationGraphEdge): string {
  const status = edge.evidence_status as EvidenceStatus;
  return EVIDENCE_ENCODING[status]?.label ?? edge.evidence_status;
}

function EdgeRow({
  rule,
  edge,
  names,
}: {
  rule: string;
  edge: SimulationGraphEdge | null;
  names: Record<string, string>;
}) {
  if (!edge) {
    return (
      <tr>
        <th scope="row" className="mono">
          {rule}
        </th>
        <td colSpan={3} className={styles.muted}>
          Not needed or not confirmed for this run
        </td>
      </tr>
    );
  }
  const query = new URLSearchParams({ from: edge.source, to: edge.target });
  return (
    <tr>
      <th scope="row" className="mono">
        {rule}
      </th>
      <td>
        {names[edge.source] ?? edge.source} → {names[edge.target] ?? edge.target}
        <span className={styles.barSub}>{edge.edge_type.replace(/_/g, " ")}</span>
      </td>
      <td>
        {evidenceLabel(edge)}
        {edge.is_illustrative && <span className={styles.barSub}>Illustrative</span>}
      </td>
      <td>
        <Link to={`/graph?${query.toString()}`} className="mono">
          {edge.edge_key}
        </Link>
      </td>
    </tr>
  );
}

export function ProvenancePanel({ provenance }: { provenance: SimulationProvenance }) {
  const [check, setCheck] = useState<
    | { state: "idle" }
    | { state: "running" }
    | { state: "done"; result: SimulationVerification }
    | { state: "failed"; message: string }
  >({ state: "idle" });
  const graph = provenance.graph;
  const names = graph.names;

  async function verify() {
    setCheck({ state: "running" });
    try {
      setCheck({ state: "done", result: await simulationApi.verify(provenance.run_id) });
    } catch (error) {
      setCheck({ state: "failed", message: describeError(error) });
    }
  }

  return (
    <div className={styles.provenance}>
      <section className={styles.verify} aria-live="polite">
        <div>
          <h4>Reproducibility</h4>
          <p>{provenance.reproducibility}</p>
        </div>
        <Button onClick={verify} disabled={check.state === "running"}>
          {check.state === "running" ? "Checking…" : "Check reproducibility"}
        </Button>
        {check.state === "done" && (
          <div className={styles.verifyResult}>
            <StatusIndicator
              tone={check.result.reproduced ? "good" : "critical"}
              label={check.result.reproduced ? "Reproduced exactly" : "Not reproduced"}
            />
            <p>{check.result.message}</p>
            {check.result.graph_edges.some((edge) => edge.still_current === false) && (
              <p className={styles.muted}>
                A relationship this run used is no longer in the latest graph build. The run keeps
                the snapshot it was calculated with.
              </p>
            )}
          </div>
        )}
        {check.state === "failed" && (
          <p className={styles.errorText} role="alert">
            <Icon name="alert" /> {check.message}
          </p>
        )}
      </section>

      <dl className={styles.facts}>
        <div>
          <dt>Model</dt>
          <dd>
            {provenance.model.name} {provenance.model.version}{" "}
            <span className={styles.muted}>({provenance.model.status})</span>
          </dd>
        </div>
        <div>
          <dt>Definition hash</dt>
          <dd>
            <Hash value={provenance.model.definition_hash} />
          </dd>
        </div>
        <div>
          <dt>Engine version</dt>
          <dd>{provenance.engine_version}</dd>
        </div>
        <div>
          <dt>Inputs hash</dt>
          <dd>
            <Hash value={provenance.inputs_hash} />
          </dd>
        </div>
        <div>
          <dt>Result hash</dt>
          <dd>
            <Hash value={provenance.result_hash} />
          </dd>
        </div>
        <div>
          <dt>Random seed</dt>
          <dd>{provenance.random_seed ?? "None: the calculation is deterministic"}</dd>
        </div>
        <div>
          <dt>Calculated</dt>
          <dd>{formatDateTime(provenance.finished_at)}</dd>
        </div>
        <div>
          <dt>Knowledge graph</dt>
          <dd>
            {graph.build_id === null
              ? "Not built when the run was calculated"
              : `Build #${graph.build_id}, ${graph.freshness === "current" ? "current" : "older than its sources"} at the time`}
          </dd>
        </div>
      </dl>

      <h4 className={styles.subheading}>Relationships from the knowledge graph</h4>
      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">Relationship</th>
              <th scope="col">Evidence</th>
              <th scope="col">Edge</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(graph.transmission).map(([rule, edge]) => (
              <EdgeRow key={rule} rule={rule} edge={edge} names={names} />
            ))}
            {Object.entries(graph.supporting).map(([rule, edge]) => (
              <EdgeRow key={rule} rule={rule} edge={edge} names={names} />
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        Transmission rules (T) carry a shock; supporting relationships (S) are cited, not followed.{" "}
        {graph.unused_total} other relationship
        {graph.unused_total === 1 ? "" : "s"} around the model's variables{" "}
        {graph.unused_total === 1 ? "was" : "were"} listed and not used: a graph connection is not a
        simulation rule.
      </p>

      <h4 className={styles.subheading}>Stored observations used</h4>
      {provenance.observations.length === 0 ? (
        <p className={styles.muted}>None: every value was entered for this run.</p>
      ) : (
        <ul className={styles.plainList}>
          {provenance.observations.map((observation) => (
            <li key={observation.series_id}>
              <strong>{observation.series_name}</strong>: {formatExact(observation.value)}{" "}
              {observation.series_unit} for {observation.period_label}. Last confirmed{" "}
              {formatDateTime(observation.last_confirmed_at)}. {observation.license}
              {observation.attribution ? `; ${observation.attribution}` : ""}.{" "}
              <Link to={`/data/series/${encodeURIComponent(observation.series_id)}`}>
                Open the series
              </Link>
            </li>
          ))}
        </ul>
      )}

      <h4 className={styles.subheading}>Transmission paths</h4>
      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Change</th>
              <th scope="col">Path</th>
              <th scope="col">Coefficient</th>
              <th scope="col">Lag</th>
              <th scope="col">From month</th>
              <th scope="col">Log change</th>
            </tr>
          </thead>
          <tbody>
            {provenance.transmission.map((path) => (
              <tr key={`${path.input}-${path.nodes.join(">")}`}>
                <td className="mono">{path.input}</td>
                <td>{path.nodes.map((node) => names[node] ?? node).join(" → ")}</td>
                <td className="tabular">{formatExact(path.coefficient)}</td>
                <td className="tabular">{path.lag}</td>
                <td className="tabular">{path.first_month}</td>
                <td className="tabular">{formatExact(path.log_change)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
