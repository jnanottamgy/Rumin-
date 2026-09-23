import { type KeyboardEvent, useId, useMemo, useState } from "react";
import { Icon } from "@/components/Icon";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cx } from "@/lib/cx";
import type { EdgeType } from "@/types/api";
import { KIND_ENCODING } from "./encoding";
import { KindGlyph } from "./KindGlyph";
import { type GraphModel, type GraphNode, KIND_ORDER, searchNodes } from "./model";
import styles from "./NetworkFilters.module.css";
import type { NetworkExplorer } from "./useNetworkExplorer";

export type NetworkView = "graph" | "table";

function EntitySearch({ model, onPick }: { model: GraphModel; onPick: (node: GraphNode) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const results = useMemo(() => searchNodes(model, query), [model, query]);
  const expanded = open && results.length > 0;

  const pick = (node: GraphNode) => {
    onPick(node);
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && results.length) {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault();
      setActive((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === "Enter" && expanded) {
      event.preventDefault();
      const node = results[active];
      if (node) pick(node);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className={styles.search}>
      <Icon name="search" className={styles.searchIcon} />
      <input
        type="search"
        role="combobox"
        aria-label="Find an entity"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded ? `${listId}-${active}` : undefined}
        placeholder="Find an entity…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {expanded && (
        <div id={listId} role="listbox" className={styles.results} aria-label="Matching entities">
          {results.map((node, index) => (
            // biome-ignore lint/a11y/useFocusableInteractive: combobox pattern — focus stays on the input; aria-activedescendant points here.
            <div
              key={node.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className={cx(styles.result, index === active && styles.resultActive)}
              // mousedown (not click) so the input keeps focus until the pick happens
              onMouseDown={(event) => {
                event.preventDefault();
                pick(node);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <KindGlyph kind={node.kind} />
              <span className={styles.resultLabel}>{node.label}</span>
              <span className={styles.resultKind}>{KIND_ENCODING[node.kind].label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ToggleChip({
  pressed,
  onClick,
  children,
  label,
}: {
  pressed: boolean | "mixed";
  onClick: () => void;
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={pressed}
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function RelationshipTypePicker({
  model,
  explorer,
}: {
  model: GraphModel;
  explorer: NetworkExplorer;
}) {
  const types = [...model.types.values()];
  const visibleCount = types.filter((type) => explorer.filters.edgeTypes.has(type.type)).length;
  return (
    <details className={styles.picker}>
      <summary className={styles.chip}>
        Relationship types
        <span className={styles.count}>
          {visibleCount}/{types.length}
        </span>
      </summary>
      <div className={styles.pickerPanel}>
        {(["economic", "structural"] as const).map((category) => (
          <fieldset key={category} className={styles.pickerGroup}>
            <legend>
              {category === "economic" ? "Economic (curated)" : "Structural (derived)"}
            </legend>
            {types
              .filter((type) => type.category === category)
              .map((type) => (
                <label key={type.type} className={styles.check}>
                  <input
                    type="checkbox"
                    checked={explorer.filters.edgeTypes.has(type.type as EdgeType)}
                    onChange={() => explorer.toggleEdgeType(type.type as EdgeType)}
                  />
                  <span>
                    <span className={styles.checkLabel}>{type.label}</span>
                    <span className={styles.checkHint}>{type.description}</span>
                  </span>
                </label>
              ))}
          </fieldset>
        ))}
      </div>
    </details>
  );
}

export function NetworkFilters({
  model,
  explorer,
  onPick,
}: {
  model: GraphModel;
  explorer: NetworkExplorer;
  onPick: (node: GraphNode) => void;
}) {
  const counts = useMemo(() => {
    const byKind = new Map(KIND_ORDER.map((kind) => [kind, 0]));
    for (const node of model.nodes) byKind.set(node.kind, (byKind.get(node.kind) ?? 0) + 1);
    return byKind;
  }, [model]);

  const narrow = useMediaQuery("(max-width: 40rem)");
  const [expanded, setExpanded] = useState(false);
  const groupsId = useId();
  const showGroups = !narrow || expanded;

  const categoryState = (category: "economic" | "structural"): boolean | "mixed" => {
    const types = [...model.types.values()].filter((type) => type.category === category);
    const on = types.filter((type) => explorer.filters.edgeTypes.has(type.type)).length;
    return on === 0 ? false : on === types.length ? true : "mixed";
  };

  return (
    <div className={styles.filters}>
      <EntitySearch model={model} onPick={onPick} />
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
          {explorer.isFiltered && <span className={styles.count}>on</span>}
        </button>
      )}
      <div id={groupsId} className={styles.groups} hidden={!showGroups}>
        <fieldset className={styles.group}>
          <legend className={styles.groupLabel}>Entities</legend>
          {KIND_ORDER.map((kind) => (
            <ToggleChip
              key={kind}
              pressed={explorer.filters.kinds.has(kind)}
              onClick={() => explorer.toggleKind(kind)}
            >
              <KindGlyph kind={kind} />
              {KIND_ENCODING[kind].plural}
              <span className={styles.count}>{counts.get(kind) ?? 0}</span>
            </ToggleChip>
          ))}
        </fieldset>

        <fieldset className={styles.group}>
          <legend className={styles.groupLabel}>Links</legend>
          {(["economic", "structural"] as const).map((category) => {
            const state = categoryState(category);
            return (
              <ToggleChip
                key={category}
                pressed={state}
                onClick={() => explorer.setCategoryVisible(category, state !== true)}
              >
                <span className={styles.lineKey} data-category={category} aria-hidden="true" />
                {category === "economic" ? "Economic" : "Structural"}
              </ToggleChip>
            );
          })}
          <RelationshipTypePicker model={model} explorer={explorer} />
        </fieldset>
      </div>
    </div>
  );
}

/** Graph ↔ table switch. The table is the accessible twin of the canvas. */
export function ViewSwitch({
  view,
  onChange,
}: {
  view: NetworkView;
  onChange: (view: NetworkView) => void;
}) {
  return (
    <fieldset className={styles.segmented}>
      <legend className="visually-hidden">View</legend>
      {(["graph", "table"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={view === option}
          onClick={() => onChange(option)}
        >
          <Icon name={option === "graph" ? "graph" : "table"} size={14} />
          {option === "graph" ? "Graph" : "Table"}
        </button>
      ))}
    </fieldset>
  );
}
