/**
 * The canvas's accessible twin: the same nodes and relationships as tables, with the same
 * selection. Everything the picture shows can be read and operated here by keyboard or
 * screen reader.
 */
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import { EVIDENCE_ENCODING, NATURE_ENCODING, typeLabel } from "./encoding";
import { EvidenceSwatch, TypeGlyph } from "./GraphGlyph";
import styles from "./GraphTable.module.css";
import type { Selection } from "./useGraphExplorer";
import { compareNodes, type GraphView } from "./view";

export function GraphTable({
  view,
  selection,
  onSelect,
  hopsLabel = "Hops from centre",
}: {
  view: GraphView;
  selection: Selection | null;
  onSelect: (selection: Selection) => void;
  hopsLabel?: string;
}) {
  const nodes = [...view.nodes.values()].sort((a, b) => a.hops - b.hops || compareNodes(a, b));
  const name = (id: string) => view.nodes.get(id)?.name ?? id;
  const edges = [...view.edges.values()].sort(
    (a, b) =>
      name(a.source).localeCompare(name(b.source)) ||
      a.label.localeCompare(b.label) ||
      name(a.target).localeCompare(name(b.target)),
  );
  const isSelected = (kind: Selection["kind"], id: string) =>
    selection?.kind === kind && selection.id === id;

  return (
    <div className={styles.tables}>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption>
            Nodes shown <span className={styles.count}>{formatCount(nodes.length)}</span>
          </caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Type</th>
              <th scope="col">Nature</th>
              <th scope="col" className={styles.number}>
                {hopsLabel}
              </th>
              <th scope="col" className={styles.number}>
                Edges shown / total
              </th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => (
              <tr key={node.id} data-selected={isSelected("node", node.id) || undefined}>
                <th scope="row">
                  <button
                    type="button"
                    className={styles.rowButton}
                    aria-pressed={isSelected("node", node.id)}
                    onClick={() => onSelect({ kind: "node", id: node.id })}
                  >
                    {node.name}
                  </button>
                </th>
                <td>
                  <span className={styles.type}>
                    <TypeGlyph
                      type={node.type}
                      size={11}
                      hollow={node.data_status === "definition_only" ? true : undefined}
                    />
                    {typeLabel(node.type)}
                  </span>
                </td>
                <td className={cx(node.nature !== "real" && styles.flag)}>
                  {NATURE_ENCODING[node.nature].short}
                </td>
                <td className={styles.number}>{node.hops}</td>
                <td className={styles.number}>
                  {node.shownDegree} / {node.degree}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption>
            Relationships shown <span className={styles.count}>{formatCount(edges.length)}</span>
          </caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Relationship</th>
              <th scope="col">Target</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((edge) => (
              <tr key={edge.id} data-selected={isSelected("edge", edge.id) || undefined}>
                <td>{name(edge.source)}</td>
                <th scope="row">
                  <button
                    type="button"
                    className={styles.rowButton}
                    aria-pressed={isSelected("edge", edge.id)}
                    onClick={() => onSelect({ kind: "edge", id: edge.id })}
                  >
                    {edge.label} {edge.directed ? "→" : "↔"}
                  </button>
                </th>
                <td>{name(edge.target)}</td>
                <td>
                  <span className={styles.type}>
                    <EvidenceSwatch status={edge.evidence_status} width={18} />
                    {EVIDENCE_ENCODING[edge.evidence_status].label}
                    {edge.is_illustrative ? " · illustrative" : ""}
                    {edge.historical ? " · historical" : ""}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
