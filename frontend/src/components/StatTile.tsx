import type { ReactNode } from "react";
import styles from "./StatTile.module.css";

/**
 * A headline figure. Values are real application state; `source` says where the number
 * comes from, so a reader can always tell data from decoration.
 */
export function StatTile({
  label,
  value,
  detail,
  source,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  source?: ReactNode;
}) {
  return (
    <div className={styles.tile}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.value}>{value}</dd>
      {detail && <dd className={styles.detail}>{detail}</dd>}
      {source && <dd className={styles.source}>{source}</dd>}
    </div>
  );
}

export function StatGrid({ children, label }: { children: ReactNode; label: string }) {
  return (
    <dl className={styles.grid} aria-label={label}>
      {children}
    </dl>
  );
}
