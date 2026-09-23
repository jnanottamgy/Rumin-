/**
 * Where a value came from and on what terms: provider, dataset, licence, attribution.
 * Shown wherever provider data is shown, as the licences require.
 */
import type { ReactNode } from "react";
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { formatCalendarDate } from "@/lib/format";
import type { DatasetRef, QualityIssue } from "@/types/api";
import { Fact } from "./DataNature";
import styles from "./DataViews.module.css";
import { OUTCOME, ruleLabel } from "./labels";

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className={styles.externalLink}>
      {children}
      <Icon name="external" size={12} />
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

export function ProvenanceFacts({
  dataset,
  providerName,
  children,
}: {
  dataset: DatasetRef;
  providerName?: string | null;
  children?: ReactNode;
}) {
  return (
    <dl className={styles.facts}>
      {providerName && <Fact label="Provider">{providerName}</Fact>}
      <Fact label="Dataset">
        {dataset.name}
        {dataset.is_illustrative && (
          <span className={styles.secondary}>Sample data — not real</span>
        )}
      </Fact>
      <Fact label="Licence">
        {dataset.license_url ? (
          <ExternalLink href={dataset.license_url}>{dataset.license}</ExternalLink>
        ) : (
          dataset.license
        )}
      </Fact>
      <Fact label="Attribution">
        {dataset.attribution ?? <span className={styles.muted}>None stated</span>}
      </Fact>
      {dataset.provider_last_updated && (
        <Fact label="Provider's last update">
          {formatCalendarDate(dataset.provider_last_updated)}
        </Fact>
      )}
      {children}
    </dl>
  );
}

const OUTCOME_TONE = { rejected: "critical", flagged: "warning", noted: "neutral" } as const;

export function QualityIssueList({
  issues,
  empty,
}: {
  issues: readonly QualityIssue[];
  empty: string;
}) {
  if (issues.length === 0) return <p className={styles.muted}>{empty}</p>;
  return (
    <ul className={styles.issues}>
      {issues.map((issue) => (
        <li key={issue.id} className={styles.issue}>
          <div className={styles.issueHead}>
            <span className={styles.issueRule}>{ruleLabel(issue.rule)}</span>
            <Badge tone={OUTCOME_TONE[issue.outcome]} title={OUTCOME[issue.outcome].description}>
              {OUTCOME[issue.outcome].label}
            </Badge>
            {issue.record_key && <span className={styles.mono}>{issue.record_key}</span>}
          </div>
          <p>{issue.message}</p>
          {issue.outcome === "rejected" && issue.raw_record && (
            <details>
              <summary className={styles.muted}>What the source sent</summary>
              <pre className={styles.raw}>{JSON.stringify(issue.raw_record, null, 2)}</pre>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}
