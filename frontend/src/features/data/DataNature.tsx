/**
 * What kind of data a view shows, in words. The three freshness facts — the period the
 * data describes, when RUMIN retrieved it, and when the provider last updated it — are
 * kept apart and never merged into an invented "freshness score".
 */
import type { ReactNode } from "react";
import { Badge } from "@/components/Badge";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { StatusIndicator } from "@/components/StatusIndicator";
import { cx } from "@/lib/cx";
import { formatCalendarDate, formatDateTime } from "@/lib/format";
import type { DatasetRef, JobItemStatus, JobStatus } from "@/types/api";
import styles from "./DataViews.module.css";
import { describeErrorCode, ITEM_STATUS, JOB_STATUS } from "./labels";

export function DataNatureBadges({
  dataset,
  hasData,
  flaggedCount = 0,
}: {
  dataset: Pick<DatasetRef, "is_illustrative">;
  hasData: boolean;
  flaggedCount?: number;
}) {
  return (
    <div className={styles.badges}>
      <EpistemicBadge category="observation" />
      <Badge tone="outline" title="Stored copies of published values. Nothing is real-time.">
        Historical · not live
      </Badge>
      {dataset.is_illustrative && (
        <Badge tone="warning" icon={<Icon name="alert" size={11} />}>
          Sample data — not real
        </Badge>
      )}
      {!hasData && <Badge tone="neutral">No values retrieved yet</Badge>}
      {flaggedCount > 0 && (
        <Badge tone="warning" icon={<Icon name="alert" size={11} />}>
          {flaggedCount} flagged for review
        </Badge>
      )}
    </div>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function FreshnessFacts({
  latestPeriod,
  retrievedAt,
  providerLastUpdated,
  latestLabel = "Latest period with a value",
  retrievedLabel = "Retrieved by RUMIN",
}: {
  latestPeriod: ReactNode;
  retrievedAt: string | null | undefined;
  providerLastUpdated: string | null | undefined;
  latestLabel?: string;
  retrievedLabel?: string;
}) {
  return (
    <div role="group" aria-label="How current this data is">
      <dl className={styles.freshness}>
        <Fact label={latestLabel}>{latestPeriod}</Fact>
        <Fact label={retrievedLabel}>
          {retrievedAt ? (
            <>
              {formatDateTime(retrievedAt)}
              <span className={styles.muted}> · stored copy</span>
            </>
          ) : (
            <span className={styles.muted}>Never</span>
          )}
        </Fact>
        <Fact label="Provider's last update">
          {providerLastUpdated ? (
            <>
              {formatCalendarDate(providerLastUpdated)}
              <span className={styles.muted}> · as the provider reports it</span>
            </>
          ) : (
            <span className={styles.muted}>Not reported</span>
          )}
        </Fact>
      </dl>
    </div>
  );
}

export function JobStatusIndicator({ status, detail }: { status: JobStatus; detail?: string }) {
  const { label, tone } = JOB_STATUS[status];
  return <StatusIndicator tone={tone} label={label} detail={detail} />;
}

export function ItemStatusIndicator({
  status,
  errorCode,
}: {
  status: JobItemStatus;
  errorCode?: string | null;
}) {
  const { label, tone } = ITEM_STATUS[status];
  return <StatusIndicator tone={tone} label={label} detail={describeErrorCode(errorCode)} />;
}

/** A callout that cannot be missed: the last retrieval failed, or the data is a sample. */
export function Notice({
  tone,
  title,
  children,
  className,
}: {
  tone: "warning" | "critical" | "neutral";
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx(styles.notice, className)} data-tone={tone} role="note">
      <Icon name={tone === "neutral" ? "info" : "alert"} size={16} />
      <div>
        <p className={styles.noticeTitle}>{title}</p>
        {children && <div className={styles.noticeBody}>{children}</div>}
      </div>
    </div>
  );
}

/** A shell command, shown the way the README shows it. */
export function Command({ children }: { children: string }) {
  return <code className={styles.command}>{children}</code>;
}
