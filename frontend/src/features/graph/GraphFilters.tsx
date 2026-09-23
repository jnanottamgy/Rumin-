/**
 * Filters for traversal and paths. They are sent to the API — the server decides what is
 * traversed — so a filter changes what is fetched, not just what is painted. An empty
 * selection means "no filter".
 */
import { type ReactNode, useId, useState } from "react";
import { Icon } from "@/components/Icon";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import type {
  EvidenceStatus,
  GraphDirection,
  GraphEdgeType,
  GraphEdgeTypeInfo,
  GraphNodeType,
} from "@/types/api";
import { EVIDENCE_ENCODING, EVIDENCE_ORDER, NODE_TYPE_ENCODING } from "./encoding";
import styles from "./GraphFilters.module.css";
import { EvidenceSwatch, TypeGlyph } from "./GraphGlyph";
import { DEFAULT_FILTERS, type ExplorerFilters, isFiltered } from "./useGraphExplorer";

/**
 * Toggle one value in an "empty means all" selection. The last value left on cannot be
 * turned off (an empty selection would mean "all" again).
 */
export function toggleInSelection<T>(selected: readonly T[], all: readonly T[], value: T): T[] {
  const current = selected.length ? selected : all;
  const next = current.includes(value)
    ? current.filter((item) => item !== value)
    : all.filter((item) => item === value || current.includes(item));
  if (next.length === 0) return [...current];
  return next.length === all.length ? [] : next;
}

const isOn = <T,>(selected: readonly T[], value: T) =>
  selected.length === 0 || selected.includes(value);

const DIRECTION_LABEL: Record<GraphDirection, string> = {
  any: "Both directions",
  out: "Outgoing only",
  in: "Incoming only",
};

interface PickerOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
  count?: number;
  mark?: ReactNode;
  group?: string;
}

/** A labelled drop-down of checkboxes over an "empty means all" selection. */
function Picker<T extends string>({
  label,
  options,
  selected,
  onChange,
  note,
}: {
  label: string;
  options: readonly PickerOption<T>[];
  selected: readonly T[];
  onChange: (next: T[]) => void;
  note?: string;
}) {
  const all = options.map((option) => option.value);
  const onCount = options.filter((option) => isOn(selected, option.value)).length;
  const groups = [...new Set(options.map((option) => option.group ?? ""))];
  return (
    <details className={styles.picker}>
      <summary className={styles.chip} data-active={selected.length > 0 || undefined}>
        {label}
        <span className={styles.count}>
          {onCount}/{options.length}
        </span>
        <Icon name="arrowDown" size={12} />
      </summary>
      <div className={styles.pickerPanel}>
        {groups.map((group) => (
          <fieldset key={group || "all"} className={styles.pickerGroup}>
            <legend className={group ? undefined : "visually-hidden"}>{group || label}</legend>
            {options
              .filter((option) => (option.group ?? "") === group)
              .map((option) => {
                const on = isOn(selected, option.value);
                const last = on && onCount === 1;
                return (
                  <label key={option.value} className={styles.check}>
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={last}
                      title={last ? "At least one must stay on." : undefined}
                      onChange={() => onChange(toggleInSelection(selected, all, option.value))}
                    />
                    <span>
                      <span className={styles.checkLabel}>
                        {option.mark}
                        {option.label}
                        {option.count !== undefined && (
                          <span className={styles.count}>{formatCount(option.count)}</span>
                        )}
                      </span>
                      {option.hint && <span className={styles.checkHint}>{option.hint}</span>}
                    </span>
                  </label>
                );
              })}
          </fieldset>
        ))}
        {note && <p className={styles.pickerNote}>{note}</p>}
        {selected.length > 0 && (
          <button type="button" className={styles.link} onClick={() => onChange([])}>
            Show all
          </button>
        )}
      </div>
    </details>
  );
}

export function GraphFilters({
  filters,
  onChange,
  nodeTypes,
  edgeTypes,
  edgeCounts,
  showNodeTypes = true,
}: {
  filters: ExplorerFilters;
  onChange: (next: ExplorerFilters) => void;
  /** Node types present in the graph, with counts. */
  nodeTypes: readonly { type: GraphNodeType; count: number }[];
  edgeTypes: readonly GraphEdgeTypeInfo[];
  edgeCounts: Record<string, number>;
  /** Paths are not filtered by node type (the API does not support it for paths). */
  showNodeTypes?: boolean;
}) {
  const narrow = useMediaQuery("(max-width: 40rem)");
  const [expanded, setExpanded] = useState(false);
  const groupsId = useId();
  const showGroups = !narrow || expanded;
  const filtered = isFiltered(showNodeTypes ? filters : { ...filters, nodeTypes: [] });
  const presentEdgeTypes = edgeTypes.filter((type) => (edgeCounts[type.type] ?? 0) > 0);

  return (
    <div className={styles.filters}>
      {narrow && (
        <button
          type="button"
          className={styles.chip}
          aria-expanded={expanded}
          aria-controls={groupsId}
          onClick={() => setExpanded((value) => !value)}
        >
          <Icon name="layers" size={14} />
          Filters
          {filtered && <span className={styles.count}>on</span>}
        </button>
      )}
      <div id={groupsId} className={styles.groups} hidden={!showGroups}>
        {showNodeTypes && (
          <Picker<GraphNodeType>
            label="Node types"
            selected={filters.nodeTypes}
            onChange={(next) => onChange({ ...filters, nodeTypes: next })}
            options={nodeTypes.map(({ type, count }) => ({
              value: type,
              label: NODE_TYPE_ENCODING[type].plural,
              count,
              mark: <TypeGlyph type={type} />,
            }))}
            note="Hidden kinds are not traversed either, so nodes reached only through them disappear too. The centre always stays."
          />
        )}
        <Picker<EvidenceStatus>
          label="Evidence"
          selected={filters.evidenceStatuses}
          onChange={(next) => onChange({ ...filters, evidenceStatuses: next })}
          options={EVIDENCE_ORDER.map((status) => ({
            value: status,
            label: EVIDENCE_ENCODING[status].label,
            hint: EVIDENCE_ENCODING[status].summary,
            mark: <EvidenceSwatch status={status} width={20} />,
          }))}
        />
        <Picker<GraphEdgeType>
          label="Relationship types"
          selected={filters.edgeTypes}
          onChange={(next) => onChange({ ...filters, edgeTypes: next })}
          options={presentEdgeTypes.map((type) => ({
            value: type.type,
            label: type.label,
            hint: type.description,
            count: edgeCounts[type.type] ?? 0,
            group:
              type.category === "economic"
                ? "Economic (curated or assumed)"
                : "Structural (classifications and records)",
          }))}
        />
        <label className={styles.select}>
          <span className="visually-hidden">Direction to follow</span>
          <select
            value={filters.direction}
            onChange={(event) =>
              onChange({ ...filters, direction: event.target.value as GraphDirection })
            }
          >
            {(["any", "out", "in"] as const).map((direction) => (
              <option key={direction} value={direction}>
                {DIRECTION_LABEL[direction]}
              </option>
            ))}
          </select>
        </label>
        <label
          className={cx(styles.chip, styles.toggle)}
          title="Edges that touch the fictional sample network or sample data."
        >
          <input
            type="checkbox"
            checked={filters.includeIllustrative}
            onChange={(event) =>
              onChange({ ...filters, includeIllustrative: event.target.checked })
            }
          />
          Include illustrative
        </label>
        {filtered && (
          <button
            type="button"
            className={styles.link}
            onClick={() =>
              onChange(
                showNodeTypes
                  ? DEFAULT_FILTERS
                  : { ...DEFAULT_FILTERS, nodeTypes: filters.nodeTypes },
              )
            }
          >
            Reset filters
          </button>
        )}
      </div>
    </div>
  );
}
