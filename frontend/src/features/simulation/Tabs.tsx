/**
 * Tabs following the WAI-ARIA pattern: arrow keys move between tabs, Home and End jump to
 * the ends, and only the active panel is rendered.
 */
import { type KeyboardEvent, type ReactNode, useId, useRef } from "react";
import styles from "./Simulation.module.css";

export interface TabItem {
  id: string;
  label: string;
  content: () => ReactNode;
}

export function Tabs({
  items,
  active,
  onChange,
  label,
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const base = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(
    0,
    items.findIndex((item) => item.id === active),
  );
  const current = items[index];

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = {
      ArrowRight: (index + 1) % items.length,
      ArrowLeft: (index - 1 + items.length) % items.length,
      Home: 0,
      End: items.length - 1,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const item = items[next];
    if (!item) return;
    onChange(item.id);
    refs.current[next]?.focus();
  }

  return (
    <div className={styles.tabs}>
      <div className={styles.tabList} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
        {items.map((item, position) => (
          <button
            key={item.id}
            ref={(element) => {
              refs.current[position] = element;
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${item.id}`}
            aria-selected={item.id === current?.id}
            aria-controls={`${base}-panel-${item.id}`}
            tabIndex={item.id === current?.id ? 0 : -1}
            className={styles.tab}
            onClick={() => onChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {current && (
        <div
          role="tabpanel"
          id={`${base}-panel-${current.id}`}
          aria-labelledby={`${base}-tab-${current.id}`}
          className={styles.tabPanel}
        >
          {current.content()}
        </div>
      )}
    </div>
  );
}
