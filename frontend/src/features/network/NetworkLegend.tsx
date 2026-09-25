import { KIND_ENCODING } from "./encoding";
import { KindGlyph } from "./KindGlyph";
import { KIND_ORDER } from "./model";
import styles from "./NetworkLegend.module.css";

/** Explains every mark on the canvas. Shapes carry kind; sky blue only means "in focus". */
export function NetworkLegend({ compact = false }: { compact?: boolean }) {
  return (
    <div className={styles.legend} data-compact={compact}>
      <ul className={styles.list} aria-label="Entity kinds">
        {KIND_ORDER.map((kind) => (
          <li key={kind}>
            <KindGlyph kind={kind} size={13} />
            {KIND_ENCODING[kind].label}
          </li>
        ))}
      </ul>
      <ul className={styles.list} aria-label="Links">
        <li>
          <svg width="28" height="10" aria-hidden="true">
            <line x1="1" y1="5" x2="27" y2="5" className={styles.economic} />
          </svg>
          Economic relationship{compact ? "" : " (thicker = stronger)"}
        </li>
        <li>
          <svg width="28" height="10" aria-hidden="true">
            <line x1="1" y1="5" x2="27" y2="5" className={styles.structural} />
          </svg>
          Structural link{compact ? "" : " (derived)"}
        </li>
        {!compact && (
          <li>
            <svg width="28" height="10" aria-hidden="true">
              <line x1="1" y1="5" x2="21" y2="5" className={styles.economic} />
              <path d="M20 1.5 26.5 5 20 8.5Z" className={styles.arrow} />
            </svg>
            Direction of effect
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
