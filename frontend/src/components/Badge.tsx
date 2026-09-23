import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import styles from "./Badge.module.css";

export type BadgeTone = "neutral" | "accent" | "outline" | "good" | "warning" | "critical";

export function Badge({
  tone = "neutral",
  icon,
  children,
  title,
  className,
}: {
  tone?: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span className={cx(styles.badge, styles[tone], className)} title={title}>
      {icon}
      {children}
    </span>
  );
}
