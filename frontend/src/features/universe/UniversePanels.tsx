/**
 * The 3D universe's side panels: the legend, the scenario overlay's picker and its panel.
 *
 * The legend names every channel the picture uses — strata, shapes, outlines, halos, line
 * patterns, arrowheads and the overlay's roles — so nothing is read from position or colour
 * alone. The overlay panel shows what the stored execution recorded, with its identity,
 * and labels every figure as a hypothetical input or a simulated result.
 */
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { ErrorState, LoadingState } from "@/components/States";
import {
  EVIDENCE_ENCODING,
  EVIDENCE_ORDER,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
} from "@/features/graph/encoding";
import { EvidenceSwatch, NatureSwatch, TypeGlyph } from "@/features/graph/GraphGlyph";
import type { Selection } from "@/features/graph/useGraphExplorer";
import { formatMoney, withSign } from "@/features/simulation/format";
import { useApiResource } from "@/hooks/useApiResource";
import { formatRounded } from "@/lib/decimal";
import { formatDateTime, plural } from "@/lib/format";
import { api } from "@/services/api";
import type { GraphNodeType } from "@/types/api";
import {
  EDGE_ROLE_LABEL,
  NODE_ROLE_LABEL,
  type OverlayEdge,
  type OverlayEdgeRole,
  type ScenarioOverlay,
} from "./overlay";
import { STRATA } from "./strata";
import styles from "./UniversePanels.module.css";

/** The 3D forms of the 2D glyphs, in words for the legend. */
const SOLID_FORM: Record<string, string> = {
  dot: "sphere",
  ring: "hollow sphere",
  diamond: "octahedron",
  square: "cube",
  hexagon: "hexagonal prism",
  target: "ring with a core",
  pill: "capsule",
  triangle: "pyramid",
  invertedTriangle: "inverted pyramid",
};

export function UniverseLegend({ types }: { types: readonly GraphNodeType[] }) {
  const present = new Set(types);
  return (
    <details className={styles.legend}>
      <summary>
        <Icon name="layers" size={14} />
        How to read the universe
      </summary>
      <div className={styles.legendBody}>
        <section>
          <h3>Height is kind</h3>
          <ol className={styles.strata}>
            {STRATA.map((stratum) => (
              <li key={stratum.id}>
                <strong>{stratum.label}</strong> <span>{stratum.description}</span>
              </li>
            ))}
          </ol>
          <p className={styles.note}>
            Horizontal position follows connections: linked records sit near each other. Size,
            height and brightness never encode a magnitude.
          </p>
        </section>
        <section>
          <h3>Shape is type</h3>
          <ul className={styles.keys}>
            {(Object.keys(NODE_TYPE_ENCODING) as GraphNodeType[])
              .filter((type) => present.has(type))
              .map((type) => {
                const encoding = NODE_TYPE_ENCODING[type];
                return (
                  <li key={type}>
                    <TypeGlyph type={type} size={14} />
                    {encoding.label}
                    <span className={styles.form}>{SOLID_FORM[encoding.shape]}</span>
                  </li>
                );
              })}
          </ul>
          <p className={styles.note}>
            Outlined shapes are hollow kinds, and series or instruments with no stored values.
          </p>
        </section>
        <section>
          <h3>Rings are nature</h3>
          <ul className={styles.keys}>
            {(["fictional", "sample"] as const).map((nature) => (
              <li key={nature}>
                <NatureSwatch nature={nature} />
                {NATURE_ENCODING[nature].label}
              </li>
            ))}
            <li>
              <span className={styles.none} aria-hidden="true" />
              {NATURE_ENCODING.real.label}: no ring
            </li>
          </ul>
        </section>
        <section>
          <h3>Line pattern is evidence</h3>
          <ul className={styles.keys}>
            {EVIDENCE_ORDER.map((status) => (
              <li key={status}>
                <EvidenceSwatch status={status} />
                {EVIDENCE_ENCODING[status].label}
              </li>
            ))}
          </ul>
          <p className={styles.note}>
            Economic relationships are heavier than structural links; an arrowhead gives a
            direction. A relationship is stated by a source or assumed by a model — it is not
            evidence that one thing causes another.
          </p>
        </section>
        <section>
          <h3>Sky blue is emphasis</h3>
          <p className={styles.note}>
            The selection and what it touches, or a scenario overlay's modelled relationships and
            the variables it changed. Everything else is set back.
          </p>
        </section>
      </div>
    </details>
  );
}

// --- The overlay's picker ------------------------------------------------------------------

export function OverlayPicker({
  executionId,
  onChange,
}: {
  executionId: string | null;
  onChange: (executionId: string | null) => void;
}) {
  const scenarios = useApiResource("scenarios", () => api.scenarios.list());
  const executed =
    scenarios.data?.items.filter((item) => item.latest_execution?.status === "completed") ?? [];
  const known = executed.some((item) => item.latest_execution?.id === executionId);
  return (
    <label className={styles.picker}>
      <span>Scenario overlay</span>
      <select
        value={executionId ?? ""}
        disabled={scenarios.status === "loading"}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">None</option>
        {executionId && !known && <option value={executionId}>The linked execution</option>}
        {executed.map((item) => {
          const latest = item.latest_execution;
          if (!latest) return null;
          return (
            <option key={latest.id} value={latest.id}>
              {item.name} · version {latest.version}
            </option>
          );
        })}
      </select>
    </label>
  );
}

// --- The overlay's panel -------------------------------------------------------------------

function changeText(value: string, unit: string, changeType: string): string {
  // `formatRounded` adds no trailing zeros: "20" stays "20", "0.5000" becomes "0.5".
  const shown = withSign(formatRounded(value, 4), value);
  if (changeType === "percent_change") return `${shown} %`;
  return `${shown} ${unit}`;
}

const ROLE_ORDER: readonly OverlayEdgeRole[] = ["propagated", "cited", "unmodelled"];

function EdgeRow({
  edge,
  names,
  onSelect,
}: {
  edge: OverlayEdge;
  names: ReadonlyMap<string, string>;
  onSelect: (selection: Selection) => void;
}) {
  const name = (key: string | null) => (key ? (names.get(key) ?? key) : "a model output");
  return (
    <li>
      <button
        type="button"
        className={styles.linkButton}
        onClick={() => onSelect({ kind: "edge", id: edge.id })}
      >
        {name(edge.source)} — {edge.label} → {name(edge.target)}
      </button>
      {edge.role === "propagated" && (
        <span className={styles.meta}>
          {edge.rule ? `Rule ${edge.rule}` : "A model rule"}
          {edge.coefficient !== null ? ` · coefficient ${edge.coefficient}` : ""}
          {edge.lagMonths !== null ? ` · lag ${plural(edge.lagMonths, "month")}` : ""}
          {edge.model ? ` · ${edge.model.title} ${edge.model.version}` : ""}
        </span>
      )}
      {edge.role === "unmodelled" && edge.reason && (
        <span className={styles.meta}>{edge.reason}</span>
      )}
    </li>
  );
}

export function OverlayPanel({
  overlay,
  names,
  missing,
  currentBuild,
  onSelect,
  onShowAll,
  onClear,
}: {
  overlay: ScenarioOverlay;
  /** Names of the graph's nodes, to write the overlay's relationships. */
  names: ReadonlyMap<string, string>;
  /** The overlay's nodes that the current view does not show. */
  missing: number;
  currentBuild: number | null;
  onSelect: (selection: Selection) => void;
  onShowAll: (() => void) | null;
  onClear: () => void;
}) {
  const byRole = new Map<OverlayEdgeRole, OverlayEdge[]>();
  for (const edge of overlay.edges.values()) {
    byRole.set(edge.role, [...(byRole.get(edge.role) ?? []), edge]);
  }
  const scenarioLink = `/scenarios/${encodeURIComponent(overlay.scenarioId)}?execution=${encodeURIComponent(overlay.executionId)}`;
  return (
    <section className={styles.overlay} aria-label="Scenario overlay">
      <header className={styles.overlayHeader}>
        <div>
          <p className={styles.eyebrow}>Scenario overlay · stored execution</p>
          <h2>{overlay.scenarioName}</h2>
          <p className={styles.meta}>
            Version {overlay.version}
            {overlay.finishedAt ? ` · executed ${formatDateTime(overlay.finishedAt)}` : ""}
            {overlay.buildId !== null ? ` · planned on graph build #${overlay.buildId}` : ""}
          </p>
        </div>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onClear}
          aria-label="Clear the overlay"
        >
          <Icon name="close" size={14} />
        </button>
      </header>
      <div className={styles.badges}>
        <Badge tone="accent">Simulated</Badge>
        {overlay.entity?.nature === "fictional" && <Badge tone="outline">Fictional company</Badge>}
        <Badge tone="outline">Not a forecast</Badge>
      </div>
      {overlay.buildId !== null && currentBuild !== null && overlay.buildId !== currentBuild && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          This execution was planned on graph build #{overlay.buildId}; the universe shows build #
          {currentBuild}. Relationships may have changed since.
        </p>
      )}
      {missing > 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {plural(missing, "of the overlay's records is", "of the overlay's records are")} not in
          this view.
          {onShowAll && (
            <button type="button" className={styles.linkButton} onClick={onShowAll}>
              Show the whole universe
            </button>
          )}
        </p>
      )}

      <h3>What the scenario changed</h3>
      <p className={styles.note}>Hypothetical inputs, stated in the scenario.</p>
      <ul className={styles.list}>
        {overlay.changes.map((change) => (
          <li key={change.key}>
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => onSelect({ kind: "node", id: change.key })}
            >
              {change.name}
            </button>{" "}
            <strong>{changeText(change.value, change.unit, change.changeType)}</strong>
            {!change.modelled && <span className={styles.meta}> · no included model uses it</span>}
          </li>
        ))}
      </ul>

      {overlay.entity && (
        <p className={styles.entity}>
          {NODE_ROLE_LABEL.entity}:{" "}
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => overlay.entity && onSelect({ kind: "node", id: overlay.entity.key })}
          >
            {overlay.entity.name}
          </button>
        </p>
      )}

      <h3>Relationships</h3>
      {ROLE_ORDER.map((role) => {
        const edges = byRole.get(role) ?? [];
        if (!edges.length) return null;
        const body = (
          <ul key={`${role}-list`} className={styles.list}>
            {edges.map((edge) => (
              <EdgeRow key={edge.id} edge={edge} names={names} onSelect={onSelect} />
            ))}
          </ul>
        );
        return role === "unmodelled" ? (
          <details key={role} className={styles.roleGroup}>
            <summary>
              <span className={styles.roleKey} data-role={role} aria-hidden="true" />
              {EDGE_ROLE_LABEL[role]} ({edges.length})
            </summary>
            {body}
          </details>
        ) : (
          <div key={role} className={styles.roleGroup}>
            <p className={styles.roleTitle}>
              <span className={styles.roleKey} data-role={role} aria-hidden="true" />
              {EDGE_ROLE_LABEL[role]} ({edges.length})
            </p>
            {body}
          </div>
        );
      })}

      {overlay.lines.length > 0 && (
        <>
          <h3>
            Simulated results{overlay.entity ? ` for ${overlay.entity.name}` : ""}
            {overlay.horizonMonths ? `, over ${plural(overlay.horizonMonths, "month")}` : ""}
          </h3>
          <p className={styles.note}>
            Simulated under the scenario's changes, figures entered in it and the models'
            assumptions — not observations and not a forecast.
          </p>
          <section
            className={styles.tableScroll}
            // biome-ignore lint/a11y/noNoninteractiveTabindex: the table scrolls sideways in a narrow panel, and a scrolling region must be reachable from the keyboard.
            tabIndex={0}
            aria-label="Simulated results, by line"
          >
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Baseline</th>
                  <th scope="col">Change</th>
                  <th scope="col">Change %</th>
                </tr>
              </thead>
              <tbody>
                {overlay.lines.map((line) => (
                  <tr key={line.id}>
                    <th scope="row">{line.label}</th>
                    <td>{formatMoney(line.baseline, overlay.currency ?? "", { decimals: 0 })}</td>
                    <td>
                      {formatMoney(line.change, overlay.currency ?? "", {
                        decimals: 0,
                        signed: true,
                      })}
                    </td>
                    <td>
                      {line.percentChange === null
                        ? "—"
                        : `${withSign(formatRounded(line.percentChange, 2), line.percentChange)} %`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
      {overlay.models.length > 0 && (
        <p className={styles.meta}>
          Models: {overlay.models.map((model) => `${model.title} ${model.version}`).join(" · ")}
        </p>
      )}
      <p className={styles.note}>{overlay.note}</p>
      <Link className={styles.linkOut} to={scenarioLink}>
        Open the execution in the Scenario Lab
        <Icon name="arrowRight" size={14} />
      </Link>
    </section>
  );
}

export function OverlayLoading() {
  return <LoadingState label="Loading the scenario overlay…" lines={5} />;
}

export function OverlayError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <ErrorState error={error} title="The scenario overlay could not be loaded" onRetry={onRetry} />
  );
}
