/**
 * Shortest paths between two nodes, found on the server by bidirectional breadth-first
 * search (bounded by hops, number of paths and a node budget). A path shows how records
 * are connected; the finder says so every time, because a chain of relationships is
 * easily misread as a chain of cause and effect.
 */
import { type FormEvent, useState } from "react";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatCount } from "@/lib/format";
import type { GraphEdgeSummary, GraphNodeSummary, GraphPath, GraphPaths } from "@/types/api";
import { EVIDENCE_ENCODING, typeFromKey } from "./encoding";
import { EvidenceSwatch, TypeGlyph } from "./GraphGlyph";
import { GraphSearch } from "./GraphSearch";
import styles from "./PathFinder.module.css";
import { DEFAULT_PATH_QUERY, type PathQuery, type Selection } from "./useGraphExplorer";

export type PickedNode = Pick<GraphNodeSummary, "id" | "name" | "type">;

function Picked({
  label,
  node,
  onClear,
  onPick,
}: {
  label: string;
  node: PickedNode | null;
  onClear: () => void;
  onPick: (node: PickedNode) => void;
}) {
  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      {node ? (
        <span className={styles.picked}>
          <TypeGlyph type={node.type} size={12} />
          <span className={styles.pickedName}>{node.name}</span>
          <button
            type="button"
            className={styles.clear}
            onClick={onClear}
            aria-label={`Clear ${label.toLowerCase()}`}
          >
            <Icon name="close" size={12} />
          </button>
        </span>
      ) : (
        <GraphSearch
          label={`${label} node`}
          placeholder={`${label}: search the graph…`}
          onPick={(item) => onPick(item)}
          className={styles.search}
        />
      )}
    </div>
  );
}

function PathSteps({
  path,
  answer,
  onSelect,
}: {
  path: GraphPath;
  answer: GraphPaths;
  onSelect: (selection: Selection) => void;
}) {
  const nodes = new Map(answer.nodes.map((node) => [node.id, node]));
  const edges = new Map(answer.edges.map((edge) => [edge.id, edge]));
  return (
    <ol className={styles.steps}>
      {path.nodes.map((id, index) => {
        const node = nodes.get(id);
        const edgeId = path.edges[index];
        const edge: GraphEdgeSummary | undefined = edgeId ? edges.get(edgeId) : undefined;
        const forward = edge ? edge.source === id : true;
        return (
          <li key={id} className={styles.step}>
            <button
              type="button"
              className={styles.stepNode}
              onClick={() => onSelect({ kind: "node", id })}
            >
              {node && <TypeGlyph type={node.type} size={11} />}
              {node?.name ?? id}
            </button>
            {edge && (
              <button
                type="button"
                className={styles.stepEdge}
                onClick={() => onSelect({ kind: "edge", id: edge.id })}
                title={`${EVIDENCE_ENCODING[edge.evidence_status].label}. Show the evidence.`}
              >
                <EvidenceSwatch status={edge.evidence_status} width={16} />
                {edge.directed
                  ? forward
                    ? `${edge.label} →`
                    : `← ${edge.label}`
                  : `${edge.label} ↔`}
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function PathFinder({
  query,
  answer,
  pending,
  error,
  onSubmit,
  onRetry,
  onSelect,
  initialFrom,
}: {
  query: PathQuery | null;
  answer: GraphPaths | null;
  pending: boolean;
  error: unknown;
  onSubmit: (query: PathQuery) => void;
  onRetry: () => void;
  onSelect: (selection: Selection) => void;
  initialFrom?: PickedNode | null;
}) {
  const known = (id: string | undefined): PickedNode | null => {
    if (!id) return null;
    if (answer?.source.id === id) return answer.source;
    if (answer?.target.id === id) return answer.target;
    const type = typeFromKey(id);
    return type ? { id, name: id, type } : null;
  };
  const [from, setFrom] = useState<PickedNode | null>(() => initialFrom ?? known(query?.from));
  const [to, setTo] = useState<PickedNode | null>(() => known(query?.to));
  const [maxDepth, setMaxDepth] = useState(query?.maxDepth ?? DEFAULT_PATH_QUERY.maxDepth);
  const [limit, setLimit] = useState(query?.limit ?? DEFAULT_PATH_QUERY.limit);

  // A node known only by its key (opened from a link) takes its name from the answer.
  const named = (node: PickedNode | null): PickedNode | null => {
    if (!node || node.name !== node.id) return node;
    if (answer?.source.id === node.id) return answer.source;
    if (answer?.target.id === node.id) return answer.target;
    return node;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (from && to) onSubmit({ from: from.id, to: to.id, maxDepth, limit });
  };

  return (
    <div className={styles.finder}>
      <form className={styles.form} onSubmit={submit} aria-label="Find paths between two nodes">
        <Picked label="From" node={named(from)} onPick={setFrom} onClear={() => setFrom(null)} />
        <Picked label="To" node={named(to)} onPick={setTo} onClear={() => setTo(null)} />
        <div className={styles.row}>
          <label className={styles.small}>
            Up to
            <select value={maxDepth} onChange={(event) => setMaxDepth(Number(event.target.value))}>
              {[1, 2, 3, 4, 5, 6].map((value) => (
                <option key={value} value={value}>
                  {value} {value === 1 ? "hop" : "hops"}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.small}>
            Show
            <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
              {[1, 3, 5, 10].map((value) => (
                <option key={value} value={value}>
                  {value} {value === 1 ? "path" : "paths"}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" size="sm" variant="primary" disabled={!from || !to}>
            Find paths
          </Button>
        </div>
      </form>

      {pending && <LoadingState label="Searching for paths…" lines={3} />}
      {Boolean(error) && (
        <ErrorState error={error} title="The path search failed" onRetry={onRetry} />
      )}
      {answer && !pending && (
        <section className={styles.results} aria-label="Paths found" aria-live="polite">
          {answer.found ? (
            <p className={styles.summary}>
              {formatCount(answer.paths.length)} shortest{" "}
              {answer.paths.length === 1 ? "path" : "paths"} of {answer.length}{" "}
              {answer.length === 1 ? "hop" : "hops"} between <strong>{answer.source.name}</strong>{" "}
              and <strong>{answer.target.name}</strong>
              {answer.paths.length >= (query?.limit ?? 0) ? " (more may exist)" : ""}.
            </p>
          ) : (
            <EmptyState title="No path found">
              No chain of at most {answer.max_depth} {answer.max_depth === 1 ? "hop" : "hops"} links{" "}
              {answer.source.name} and {answer.target.name} with the current filters. That means
              RUMIN holds no such chain of records — not that the two are unrelated in the world.
            </EmptyState>
          )}
          {answer.budget_exhausted && (
            <p className={styles.warning}>
              <Icon name="alert" size={14} /> The search stopped at its limit of explored nodes (
              {formatCount(answer.nodes_explored)}); shorter filters or fewer hops may help.
            </p>
          )}
          {answer.paths.map((path, index) => (
            <div key={path.edges.join("|") || index} className={styles.path}>
              <p className={styles.pathLabel}>Path {index + 1}</p>
              <PathSteps path={path} answer={answer} onSelect={onSelect} />
            </div>
          ))}
          <p className={styles.note}>{answer.note}</p>
        </section>
      )}
      {!answer && !pending && !error && (
        <p className={styles.note}>
          Choose two nodes to see how RUMIN's records connect them. Paths are counted in hops
          (edges), direction ignored unless you filter it; a shorter path is not a stronger
          relationship.
        </p>
      )}
    </div>
  );
}
