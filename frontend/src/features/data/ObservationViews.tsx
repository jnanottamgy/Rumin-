/**
 * An economic series' values, as a chart or as the table that is its exact twin.
 */
import { useMemo } from "react";
import { ScrollRegion } from "@/components/ScrollRegion";
import { EmptyState } from "@/components/States";
import { formatExact, formatRounded, isDecimalString, toNumber } from "@/lib/decimal";
import { formatDateTime, formatPeriod } from "@/lib/format";
import type { Observation, SeriesRef } from "@/types/api";
import { type ChartPoint, dateTime, nextPeriodFollows } from "./chartMath";
import styles from "./DataViews.module.css";
import { QUALITY } from "./labels";
import { TimeSeriesChart } from "./TimeSeriesChart";

export function FlagGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      <path d="M6 1.5 10.5 9.5H1.5Z" fill="var(--viz-flag)" />
    </svg>
  );
}

export function MissingGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      <circle
        cx="6"
        cy="6"
        r="3.25"
        fill="none"
        stroke="var(--color-ink-muted)"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function ChartKey({ flagged, missing }: { flagged: boolean; missing: boolean }) {
  if (!flagged && !missing) return null;
  return (
    <ul className={styles.key} aria-label="Chart key">
      {flagged && (
        <li className={styles.keyItem}>
          <FlagGlyph /> Flagged for review (stored as reported)
        </li>
      )}
      {missing && (
        <li className={styles.keyItem}>
          <MissingGlyph /> No value published — shown as a gap, never filled in
        </li>
      )}
    </ul>
  );
}

/** The literal the provider sent (e.g. "14.250000"), when it is a plain decimal. */
export function publishedValue(observation: Observation): string | null {
  if (observation.value === null) return null;
  const raw = observation.raw_value;
  return formatExact(raw && isDecimalString(raw) ? raw : observation.value);
}

function notesFor(observation: Observation): string[] {
  const notes: string[] = [];
  if (observation.quality_status === "warning") notes.push("Flagged for review.");
  if (observation.provider_flags) notes.push(`Provider flag: ${observation.provider_flags}.`);
  if (observation.revision > 1)
    notes.push(`Revised by the provider (revision ${observation.revision}).`);
  return notes;
}

export function ObservationChart({
  series,
  observations,
}: {
  series: SeriesRef;
  observations: readonly Observation[];
}) {
  const current = useMemo(
    () => observations.filter((observation) => observation.is_current),
    [observations],
  );
  const points = useMemo<ChartPoint[]>(
    () =>
      current.map((observation) => ({
        key: observation.period_label,
        time: dateTime(observation.period_start),
        value: observation.value === null ? null : toNumber(observation.value),
        flagged: observation.quality_status === "warning",
      })),
    [current],
  );
  const contiguous = useMemo(() => nextPeriodFollows(series.frequency), [series.frequency]);

  if (points.length === 0) {
    return <EmptyState title="No values stored for this series yet" />;
  }
  if (!points.some((point) => point.value !== null)) {
    return (
      <EmptyState title="No values to chart">
        The provider listed {points.length} period(s) for this series, all without a value. RUMIN
        records them as missing and never fills them in.
      </EmptyState>
    );
  }

  return (
    <>
      <TimeSeriesChart
        points={points}
        label={series.name}
        unit={series.unit}
        contiguous={contiguous}
        describe={(index) => {
          const observation = current[index];
          if (!observation) return { title: "", value: "", notes: [] };
          return {
            title: `${formatPeriod(observation.period_label)} · ${series.unit}`,
            value: publishedValue(observation) ?? "No value published",
            notes: notesFor(observation),
          };
        }}
        endLabel={(index) => {
          const value = current[index]?.value;
          return value ? formatRounded(value, 2) : "";
        }}
      />
      <ChartKey
        flagged={points.some((point) => point.flagged)}
        missing={points.some((point) => point.value === null)}
      />
    </>
  );
}

export function ObservationTable({
  series,
  observations,
  showRevisions,
}: {
  series: SeriesRef;
  observations: readonly Observation[];
  showRevisions: boolean;
}) {
  if (observations.length === 0) {
    return <EmptyState title="No values stored for this series yet" />;
  }
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption>
          Every value exactly as the provider published it, in {series.unit}. “Retrieved” is when
          RUMIN first received the value.
          {showRevisions ? " Superseded revisions are shown in grey." : ""}
        </caption>
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col" className={styles.number}>
              Value
            </th>
            <th scope="col">Quality</th>
            <th scope="col">Provider flag</th>
            <th scope="col">Retrieved</th>
            {showRevisions && <th scope="col">Revision</th>}
          </tr>
        </thead>
        <tbody>
          {observations.map((observation) => (
            <tr key={observation.id} data-current={observation.is_current}>
              <th scope="row" className={styles.nowrap}>
                {formatPeriod(observation.period_label)}
              </th>
              <td className={styles.number}>
                {observation.value === null ? (
                  <span className={styles.missingValue}>No value published</span>
                ) : (
                  publishedValue(observation)
                )}
              </td>
              <td>
                {observation.quality_status === "warning" ? (
                  <span className={styles.flagMark}>
                    <FlagGlyph /> {QUALITY.warning}
                  </span>
                ) : observation.value === null ? (
                  <span className={styles.muted}>—</span>
                ) : (
                  QUALITY.validated
                )}
              </td>
              <td className={styles.mono}>{observation.provider_flags ?? ""}</td>
              <td className={styles.nowrap}>{formatDateTime(observation.retrieved_at)}</td>
              {showRevisions && (
                <td className={styles.nowrap}>
                  {observation.revision}
                  {observation.is_current
                    ? " · current"
                    : observation.superseded_at
                      ? ` · superseded ${formatDateTime(observation.superseded_at)}`
                      : ""}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}
