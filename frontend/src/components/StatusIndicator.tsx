/**
 * A status is always icon + label — colour is never the only signal.
 * Tones follow reserved status meanings and are never reused for categories.
 */
import { cx } from "@/lib/cx";
import { Icon, type IconName } from "./Icon";
import styles from "./StatusIndicator.module.css";

export type StatusTone = "good" | "warning" | "critical" | "planned" | "neutral";

const ICONS: Record<StatusTone, IconName> = {
  good: "check",
  warning: "alert",
  critical: "close",
  planned: "pending",
  neutral: "dot",
};

export function StatusIndicator({
  tone,
  label,
  detail,
  className,
}: {
  tone: StatusTone;
  label: string;
  detail?: string;
  className?: string;
}) {
  return (
    <span className={cx(styles.status, className)} data-tone={tone}>
      <span className={styles.icon}>
        <Icon name={ICONS[tone]} size={12} />
      </span>
      <span className={styles.label}>{label}</span>
      {detail && (
        <span className={styles.detail} data-part="detail">
          {detail}
        </span>
      )}
    </span>
  );
}
