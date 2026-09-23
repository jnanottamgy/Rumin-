/**
 * The table view: the same filtered slice as the graph, as accessible tables.
 * Every value on the canvas is reachable here without pointing at anything.
 */
import { useMemo } from "react";
import { EVIDENCE_LABEL, KIND_ENCODING, POLARITY_LABEL, STRENGTH_LABEL } from "./encoding";
import { KindGlyph } from "./KindGlyph";
import type { GraphModel, Subgraph } from "./model";
import styles from "./NetworkTable.module.css";

export function NetworkTable({
  model,
  visible,
  selectedId,
  onSelect,
}: {
  model: GraphModel;
  visible: Subgraph;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const nodes = model.nodes.filter((node) => visible.nodeIds.has(node.id));
  const edges = useMemo(
    () =>
      model.edges
        .filter((edge) => visible.edgeIds.has(edge.id))
        .filter((edge) => !selectedId || edge.source === selectedId || edge.target === selectedId)
        .sort(
          (a, b) =>
            a.category.localeCompare(b.category) ||
            a.type.localeCompare(b.type) ||
            a.source.localeCompare(b.source),
        ),
    [model, visible, selectedId],
  );
  const name = (id: string) => model.nodeById.get(id)?.label ?? id;

  return (
    <div className={styles.tables}>
      <section className={styles.block}>
        <h3 className={styles.caption}>Entities ({nodes.length})</h3>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Kind</th>
                <th scope="col" className={styles.numeric}>
                  Connections
                </th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((node) => (
                <tr key={node.id} aria-selected={node.id === selectedId}>
                  <th scope="row">
                    <button
                      type="button"
                      className={styles.rowButton}
                      onClick={() => onSelect(node.id)}
                    >
                      {node.label}
                    </button>
                  </th>
                  <td>
                    <span className={styles.kind}>
                      <KindGlyph kind={node.kind} />
                      {KIND_ENCODING[node.kind].label}
                    </span>
                  </td>
                  <td className={styles.numeric}>{node.degree}</td>
                  <td>{node.entity.is_fictional ? "Fictional" : "Real-world concept"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.block}>
        <h3 className={styles.caption}>
          Relationships ({edges.length})
          {selectedId && (
            <>
              {" "}
              <span className={styles.scope}>touching {name(selectedId)}</span>
            </>
          )}
        </h3>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Relationship</th>
                <th scope="col">Target</th>
                <th scope="col">Polarity</th>
                <th scope="col">Strength</th>
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {edges.map((edge) => {
                const data = edge.data;
                const economic = data.category === "economic";
                return (
                  <tr key={edge.id}>
                    <td>{name(edge.source)}</td>
                    <td>{model.types.get(edge.type)?.label ?? edge.type}</td>
                    <td>{name(edge.target)}</td>
                    <td>{economic ? POLARITY_LABEL[data.polarity] : "—"}</td>
                    <td>{economic ? STRENGTH_LABEL[data.strength] : "—"}</td>
                    <td>
                      {economic ? EVIDENCE_LABEL[data.evidence_level] : "Structural (derived)"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
