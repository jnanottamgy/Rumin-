/**
 * Search the graph on the server: by name, identifier (ISO, ISIC, ISIN, MIC, provider
 * series key) or details such as an industry or country in a node's subtitle. Partial and
 * case-insensitive. Results show the node's type (glyph and word) and a subtitle that
 * tells similar names apart; names shared by several nodes are flagged.
 */
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/format";
import { graphApi } from "@/services/api";
import type { GraphNodeSearchResult, GraphNodeType } from "@/types/api";
import { typeLabel } from "./encoding";
import { TypeGlyph } from "./GraphGlyph";
import styles from "./GraphSearch.module.css";

const DEBOUNCE_MS = 200;
const RESULT_LIMIT = 12;

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; items: GraphNodeSearchResult[]; total: number }
  | { status: "error"; error: unknown };

/** Debounced, cancellable server search. */
export function useNodeSearch(query: string, types: readonly GraphNodeType[] = []) {
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const typeKey = types.join(",");
  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setState({ status: "idle" });
      return;
    }
    setState({ status: "loading" });
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      graphApi
        .search(
          {
            q: text,
            types: typeKey ? (typeKey.split(",") as GraphNodeType[]) : [],
            limit: RESULT_LIMIT,
          },
          { signal: controller.signal },
        )
        .then(
          (page) => setState({ status: "done", items: page.items, total: page.total }),
          (error: unknown) => {
            if (!controller.signal.aborted) setState({ status: "error", error });
          },
        );
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, typeKey]);
  return state;
}

function ResultRow({ item }: { item: GraphNodeSearchResult }) {
  return (
    <>
      <span className={styles.glyph}>
        <TypeGlyph
          type={item.type}
          size={13}
          hollow={item.data_status === "definition_only" ? true : undefined}
        />
      </span>
      <span className={styles.text}>
        <span className={styles.name}>{item.name}</span>
        <span className={styles.subtitle}>{item.subtitle}</span>
        {(item.match === "identifier" || item.ambiguous) && (
          <span className={styles.flags}>
            {item.match === "identifier" && item.primary_identifier && (
              <span className={styles.flag}>
                {item.primary_identifier.label}{" "}
                <span className="mono">{item.primary_identifier.value}</span>
              </span>
            )}
            {item.ambiguous && (
              <span className={styles.flag} data-tone="warning">
                Same name as another node — check the details
              </span>
            )}
          </span>
        )}
      </span>
      <span className={styles.type}>{typeLabel(item.type)}</span>
    </>
  );
}

export function GraphSearch({
  onPick,
  label = "Search the graph",
  placeholder = "Search by name, code or identifier…",
  types,
  className,
}: {
  onPick: (item: GraphNodeSearchResult) => void;
  label?: string;
  placeholder?: string;
  types?: readonly GraphNodeType[];
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const state = useNodeSearch(query, types);
  const items = state.status === "done" ? state.items : [];
  const showPanel = open && query.trim().length > 0;

  const pick = (item: GraphNodeSearchResult) => {
    onPick(item);
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      setActive((index) => (index - 1 + items.length) % items.length);
    } else if (event.key === "Enter" && showPanel && items.length) {
      event.preventDefault();
      const item = items[active];
      if (item) pick(item);
    } else if (event.key === "Escape") {
      if (showPanel) event.stopPropagation();
      setOpen(false);
    }
  };

  return (
    <div className={cx(styles.search, className)}>
      <Icon name="search" className={styles.icon} />
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-label={label}
        aria-expanded={showPanel && items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showPanel && items.length ? `${listId}-${active}` : undefined}
        placeholder={placeholder}
        value={query}
        maxLength={100}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showPanel && (
        <div className={styles.panel}>
          {state.status === "loading" && (
            <p className={styles.status} role="status">
              Searching…
            </p>
          )}
          {state.status === "error" && (
            <p className={styles.status} role="alert">
              Search failed: {describeError(state.error)}
            </p>
          )}
          {state.status === "done" && items.length === 0 && (
            <p className={styles.status} role="status">
              No node matches “{query.trim()}”. Try part of a name, an ISO or ISIC code, or a
              provider series key.
            </p>
          )}
          <div
            id={listId}
            role="listbox"
            aria-label="Matching nodes"
            className={styles.results}
            hidden={items.length === 0}
          >
            {items.map((item, index) => (
              // biome-ignore lint/a11y/useFocusableInteractive: combobox pattern — focus stays on the input; aria-activedescendant points here.
              <div
                key={item.id}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === active}
                className={cx(styles.result, index === active && styles.active)}
                // mousedown (not click) so the input keeps focus until the pick happens
                onMouseDown={(event) => {
                  event.preventDefault();
                  pick(item);
                }}
                onMouseEnter={() => setActive(index)}
              >
                <ResultRow item={item} />
              </div>
            ))}
          </div>
          {state.status === "done" && state.total > items.length && (
            <p className={styles.more}>
              Showing {items.length} of {formatCount(state.total)} matches — type more to narrow
              them down.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
