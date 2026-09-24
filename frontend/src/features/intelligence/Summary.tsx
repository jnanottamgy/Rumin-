/**
 * The latest findings, for the Overview dashboard: the first few rows of the workspace
 * ledger (new observations first, then simulations, relationships and coverage), each with
 * its grade. The full ledger, with every evidence chain, is in Financial Intelligence.
 */
import { Link } from "react-router";
import { ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { plural } from "@/lib/format";
import { intelligenceApi } from "@/services/api";
import { GradeMark } from "./Evidence";
import { KIND } from "./format";
import styles from "./Intelligence.module.css";

const SHOWN = 4;

export function LatestFindings() {
  const overview = useApiResource("intelligence:overview:dashboard", () =>
    intelligenceApi.overview(),
  );
  if (overview.status === "loading") return <LoadingState label="Analysing the workspace…" />;
  if (overview.status === "error") {
    return <ErrorState error={overview.error} onRetry={overview.reload} />;
  }
  const { insights } = overview.data;
  if (insights.length === 0) {
    return <p className={styles.emptyLine}>No finding yet: build the knowledge graph first.</p>;
  }
  return (
    <div className={styles.summary}>
      <ul className={styles.summaryList} aria-label="Latest findings">
        {insights.slice(0, SHOWN).map((insight) => (
          <li key={insight.id}>
            <span className={styles.findingKind}>{KIND[insight.kind] ?? insight.kind}</span>
            <span className={styles.summaryHeadline}>{insight.headline}</span>
            <GradeMark
              grade={insight.evidence.grade}
              statement={insight.evidence.statement}
              compact
            />
          </li>
        ))}
      </ul>
      <p className={styles.muted}>
        <Link to="/intelligence">
          {insights.length > SHOWN
            ? `All ${plural(insights.length, "finding")}, with their evidence`
            : "Open the findings, with their evidence"}
        </Link>
      </p>
    </div>
  );
}
