/** Loading, error and empty states — every data view uses these, so no screen is blank. */
import type { ReactNode } from "react";
import { ApiError, describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { Button } from "./Button";
import { Icon } from "./Icon";
import styles from "./States.module.css";

export function LoadingState({
  label = "Loading…",
  className,
  lines = 3,
}: {
  label?: string;
  className?: string;
  lines?: number;
}) {
  return (
    <div className={cx(styles.loading, className)} role="status" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      <div className={styles.skeleton} aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder lines
          <span key={index} style={{ width: `${88 - index * 17}%` }} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  error,
  title = "This data could not be loaded",
  onRetry,
  className,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
  className?: string;
}) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  const hint =
    error instanceof ApiError && (error.kind === "network" || error.kind === "timeout")
      ? "Start the backend with `uvicorn app.main:app` (see README), then retry."
      : null;
  return (
    <div className={cx(styles.message, styles.error, className)} role="alert">
      <Icon name="alert" size={18} />
      <div className={styles.text}>
        <p className={styles.title}>{title}</p>
        <p>{describeError(error)}</p>
        {hint && <p className={styles.hint}>{hint}</p>}
        {requestId && (
          <p className={styles.hint}>
            Request ID <span className="mono">{requestId}</span>
          </p>
        )}
        {onRetry && (
          <div className={styles.actions}>
            <Button size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx(styles.message, styles.empty, className)}>
      <Icon name="circle" size={18} />
      <div className={styles.text}>
        <p className={styles.title}>{title}</p>
        {children && <div>{children}</div>}
        {action && <div className={styles.actions}>{action}</div>}
      </div>
    </div>
  );
}
