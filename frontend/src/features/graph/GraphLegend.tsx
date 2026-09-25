/**
 * Explains every mark on the canvas — only the ones in the current view, so the legend
 * stays short. Shapes carry node type, ring patterns carry nature, line patterns carry
 * evidence status; sky blue only means "in focus".
 */
import type { EvidenceStatus, GraphNodeType, NodeNature } from "@/types/api";
import {
  EVIDENCE_ENCODING,
  EVIDENCE_ORDER,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
  NODE_TYPE_ORDER,
} from "./encoding";
import { EvidenceSwatch, NatureSwatch, TypeGlyph } from "./GraphGlyph";
import styles from "./GraphLegend.module.css";
import type { GraphView } from "./view";

export function GraphLegend({
  view,
  radial,
  compact = false,
}: {
  view: GraphView;
  radial: boolean;
  compact?: boolean;
}) {
  const types = new Set<GraphNodeType>();
  const natures = new Set<NodeNature>();
  const statuses = new Set<EvidenceStatus>();
  let hollowSeries = false;
  let filledSeries = false;
  let directed = false;
  let hidden = false;
  for (const node of view.nodes.values()) {
    types.add(node.type);
    natures.add(node.nature);
    if (node.type === "data_series" || node.type === "instrument") {
      if (node.data_status === "definition_only") hollowSeries = true;
      if (node.data_status === "values_stored") filledSeries = true;
    }
    if (node.degree > node.shownDegree) hidden = true;
  }
  for (const edge of view.edges.values()) {
    statuses.add(edge.evidence_status);
    if (edge.directed) directed = true;
  }

  return (
    <div className={styles.legend} data-compact={compact}>
      <ul className={styles.list} aria-label="Node types">
        {NODE_TYPE_ORDER.filter((type) => types.has(type)).map((type) => (
          <li key={type}>
            <TypeGlyph type={type} size={13} />
            {NODE_TYPE_ENCODING[type].label}
          </li>
        ))}
        {(["fictional", "sample"] as const)
          .filter((nature) => natures.has(nature))
          .map((nature) => (
            <li key={nature}>
              <NatureSwatch nature={nature} />
              {NATURE_ENCODING[nature].label}
            </li>
          ))}
        {hollowSeries && (
          <li>
            <TypeGlyph type="data_series" size={13} hollow />
            Definition only{filledSeries ? "" : " (no values stored)"}
          </li>
        )}
        {filledSeries && (
          <li>
            <TypeGlyph type="data_series" size={13} hollow={false} />
            Values stored
          </li>
        )}
      </ul>
      <ul className={styles.list} aria-label="Lines">
        {EVIDENCE_ORDER.filter((status) => statuses.has(status)).map((status) => (
          <li key={status} title={EVIDENCE_ENCODING[status].summary}>
            <EvidenceSwatch status={status} />
            {EVIDENCE_ENCODING[status].label}
          </li>
        ))}
        {directed && !compact && (
          <li>
            <EvidenceSwatch status="evidence_backed" arrow />
            Direction
          </li>
        )}
        {hidden && !compact && (
          <li>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path
                d="M2 6h8M6 2v8"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
            More connections not shown
          </li>
        )}
        {radial && !compact && (
          <li>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">
              <circle r="2" fill="currentColor" />
              <circle r="6.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.55" />
            </svg>
            Rings: hops from the centre
          </li>
        )}
        <li>
          <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true">
            <circle r="3.5" className={styles.selected} />
            <circle r="6" className={styles.selectedRing} />
          </svg>
          Selected & connected
        </li>
      </ul>
    </div>
  );
}
