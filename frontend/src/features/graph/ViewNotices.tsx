/**
 * What the explorer's current neighbourhood leaves out or could not load: no relationships
 * (or none matching the filters), a neighbourhood cut short by the node limit, nodes not
 * drawn, expansions hidden by the filters, expansions that failed (with a retry). Shared by
 * the 2D explorer and the 3D universe, so both say the same thing about the same view.
 */
import { Icon } from "@/components/Icon";
import { formatCount, plural } from "@/lib/format";
import { type GraphExplorer, isFiltered } from "./useGraphExplorer";
import styles from "./ViewNotices.module.css";

export function ViewNotices({ explorer }: { explorer: GraphExplorer }) {
  const { view } = explorer;
  if (!view || explorer.snapshot.mode !== "explore") return null;
  const failed = view.expansions.filter((item) => item.status === "failed");
  const skipped = view.expansions.filter((item) => item.status === "skipped");
  const truncatedTypes = Object.entries(view.unexploredByType)
    .map(([type, count]) => `${formatCount(count)} ${type.replace("_", " ")}`)
    .join(", ");
  const centre = view.nodes.get(view.focus)?.name ?? "the focus";
  return (
    <div className={styles.notices}>
      {view.edges.size === 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {isFiltered(explorer.filters)
            ? `No relationships around ${centre} match the current filters.`
            : `${centre} has no recorded relationships in the graph.`}
          {isFiltered(explorer.filters) && (
            <button type="button" className={styles.linkButton} onClick={explorer.resetFilters}>
              Reset filters
            </button>
          )}
        </p>
      )}
      {view.focusTruncated && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          The node limit cut this neighbourhood short
          {truncatedTypes ? ` (left out: ${truncatedTypes})` : ""}. Raise the limit, lower the depth
          or add filters.
        </p>
      )}
      {view.hiddenByLimit > 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {plural(view.hiddenByLimit, "node")} not drawn: the view is capped at {explorer.nodeLimit}{" "}
          nodes.
        </p>
      )}
      {skipped.length > 0 && (
        <p className={styles.notice} role="status">
          <Icon name="info" size={14} />
          {plural(skipped.length, "expanded node")} hidden by the current filters.
        </p>
      )}
      {failed.length > 0 && (
        <p className={styles.notice} data-tone="critical" role="alert">
          <Icon name="alert" size={14} />
          {failed.length === 1 ? "An expansion" : `${failed.length} expansions`} could not be
          loaded.
          <button type="button" className={styles.linkButton} onClick={explorer.retry}>
            Try again
          </button>
        </p>
      )}
    </div>
  );
}
