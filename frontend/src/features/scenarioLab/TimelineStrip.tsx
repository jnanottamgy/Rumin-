/**
 * The simulated months: one line's monthly change as columns from zero, the months the
 * changes last (a rule under the axis), and the events that follow from the models' runs
 * (a lag elapsing, hedges expiring, loans repricing). The scrubber replays the months: the
 * pathway above then shows each step's value in that month. Hovering a month reads its
 * value out in the header. Every value is simulated; the months count from the start of
 * the simulation and are not calendar dates.
 */
import { useMemo, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { useElementSize } from "@/hooks/useElementSize";
import { toNumber } from "@/lib/decimal";
import type { ResultLine, ScenarioTimeline } from "@/types/api";
import { compactMoney } from "./format";
import styles from "./ScenarioLab.module.css";

const HEIGHT = 116;
const TOP = 18;
/** Month numbers, then the rule marking the months the changes last. */
const BOTTOM = 42;
const LEFT = 8;
const RIGHT = 8;

export function TimelineStrip({
  timeline,
  lines,
  month,
  onMonth,
  playing,
  onTogglePlay,
}: {
  timeline: ScenarioTimeline;
  lines: ResultLine[];
  /** The replayed month, or null for totals. */
  month: number | null;
  onMonth: (month: number | null) => void;
  playing: boolean;
  onTogglePlay: () => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 900, height: 0 });
  const [lineId, setLineId] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const chosen =
    lines.find((line) => line.id === lineId) ??
    lines.find((line) => line.id === "profit_before_tax") ??
    lines.find((line) => line.id === "operating_profit") ??
    lines[0];
  const months = timeline.months;
  const values = chosen ? chosen.monthly.map(toNumber) : [];

  const geometry = useMemo(() => {
    const low = Math.min(0, ...values);
    const high = Math.max(0, ...values);
    const span = high - low || 1;
    const plotWidth = Math.max(100, width - LEFT - RIGHT);
    const band = plotWidth / Math.max(1, months);
    const y = (value: number) => TOP + (1 - (value - low) / span) * (HEIGHT - TOP - BOTTOM);
    return { band, y, zero: y(0), x: (index: number) => LEFT + index * band };
  }, [values, width, months]);
  const { band, y, zero, x } = geometry;
  const columnWidth = Math.max(2, Math.min(24, band * 0.6));
  const events = timeline.events;

  function monthAt(event: { clientX: number }): number | null {
    const frame = frameRef.current;
    if (!frame) return null;
    const position = event.clientX - frame.getBoundingClientRect().left - LEFT;
    const index = Math.floor(position / band);
    return index >= 0 && index < months ? index + 1 : null;
  }

  const shown = hover ?? month;
  const readout =
    shown === null || !chosen
      ? "Totals over the horizon"
      : `Month ${shown} of ${months}: ${compactMoney(chosen.monthly[shown - 1] ?? "0")} ${chosen.label.toLowerCase()} — simulated`;
  const plotBottom = HEIGHT - BOTTOM;
  const windowX = x(timeline.start_month - 1);
  const windowWidth = (timeline.end_month - timeline.start_month + 1) * band;

  return (
    <section className={styles.timeline} aria-label="Simulated months">
      <div className={styles.timelineHeader}>
        <div className={styles.replay}>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onTogglePlay}
            aria-label={playing ? "Pause the replay" : "Replay the simulated months"}
          >
            <Icon name={playing ? "pause" : "play"} size={14} />
          </button>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => onMonth(null)}
            aria-label="Show totals over the horizon"
            disabled={month === null}
          >
            <Icon name="rewind" size={14} />
          </button>
          <label className={styles.scrubber}>
            <span className="visually-hidden">Simulated month</span>
            <input
              type="range"
              min={0}
              max={months}
              value={month ?? 0}
              onChange={(event) => {
                const value = Number(event.target.value);
                onMonth(value === 0 ? null : value);
              }}
              aria-valuetext={
                month === null ? "Totals over the horizon" : `Month ${month} of ${months}`
              }
            />
          </label>
          <span className={styles.replayLabel} aria-live="polite">
            {readout}
          </span>
        </div>
        {chosen && (
          <label className={styles.inlineSelect}>
            <span>Line</span>
            <select value={chosen.id} onChange={(event) => setLineId(event.target.value)}>
              {lines.map((line) => (
                <option key={line.id} value={line.id}>
                  {line.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div
        ref={frameRef}
        className={styles.timelineFrame}
        style={{ height: HEIGHT }}
        onPointerMove={(event) => setHover(monthAt(event))}
        onPointerLeave={() => setHover(null)}
        onClick={(event) => onMonth(monthAt(event))}
        aria-hidden="true"
      >
        <svg width={width} height={HEIGHT} className={styles.timelineSvg} aria-hidden="true">
          <line
            x1={LEFT}
            x2={LEFT + months * band}
            y1={zero}
            y2={zero}
            className={styles.timelineZero}
          />
          {values.map((value, index) => {
            const top = Math.min(y(value), zero);
            const height = Math.max(1, Math.abs(zero - y(value)));
            return (
              <rect
                // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                key={index}
                x={x(index) + (band - columnWidth) / 2}
                y={top}
                width={columnWidth}
                height={height}
                rx={Math.min(3, columnWidth / 2)}
                className={styles.timelineColumn}
                data-current={shown === index + 1 ? "true" : undefined}
                data-future={month !== null && index + 1 > month ? "true" : undefined}
              />
            );
          })}
          {events.map((event) => (
            <line
              key={`${event.month}-${event.label}`}
              x1={x(event.month - 1) + band / 2}
              x2={x(event.month - 1) + band / 2}
              y1={4}
              y2={TOP - 2}
              className={styles.eventTick}
            />
          ))}
          {Array.from({ length: months }, (_, index) =>
            index === 0 || (index + 1) % (band < 24 ? 3 : 1) === 0 ? (
              <text
                // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                key={index}
                x={x(index) + band / 2}
                y={plotBottom + 14}
                className={styles.monthTick}
              >
                {index + 1}
              </text>
            ) : null,
          )}
          <line
            x1={windowX + 2}
            x2={windowX + windowWidth - 2}
            y1={plotBottom + 24}
            y2={plotBottom + 24}
            className={styles.windowRule}
          />
          <text x={windowX + 2} y={plotBottom + 37} className={styles.windowLabel}>
            {timeline.start_month === timeline.end_month
              ? `Changes in effect: month ${timeline.start_month}`
              : `Changes in effect: months ${timeline.start_month}–${timeline.end_month}`}
          </text>
        </svg>
      </div>

      <ol className={styles.events}>
        {events.map((event) => (
          <li key={`${event.month}-${event.label}`}>
            <button
              type="button"
              onClick={() => onMonth(event.month)}
              data-current={month === event.month ? "true" : undefined}
            >
              <span className={styles.eventMonth}>M{event.month}</span>
              {event.label}
            </button>
          </li>
        ))}
      </ol>
      <p className={styles.caption}>{timeline.note}</p>
    </section>
  );
}
