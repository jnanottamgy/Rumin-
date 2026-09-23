import { cx } from "@/lib/cx";
import styles from "./Wordmark.module.css";

/**
 * The RUMIN wordmark: two connected nodes — one solid, one open ring in sky blue —
 * followed by the name in widely tracked serif capitals.
 */
export function Wordmark({ size = "md", className }: { size?: "md" | "lg"; className?: string }) {
  return (
    <span className={cx(styles.wordmark, styles[size], className)}>
      <svg className={styles.mark} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <line x1="6.5" y1="16.5" x2="15" y2="9" className={styles.link} />
        <circle cx="6.5" cy="16.5" r="3" className={styles.solid} />
        <circle cx="16" cy="8" r="4.2" className={styles.ring} />
      </svg>
      <span className={styles.name}>RUMIN</span>
    </span>
  );
}
