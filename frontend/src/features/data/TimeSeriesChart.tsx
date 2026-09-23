/**
 * A single-series time chart for historical values.
 *
 * Honesty rules, enforced here and tested in `chartMath`:
 * - a missing value, or a period absent from the data, is a gap: the line is never
 *   drawn across it, and missing periods are marked on the axis;
 * - values flagged for review carry their own shape (a triangle), so the flag never
 *   depends on colour alone;
 * - labels are rounded for display; the tooltip and the table give the exact value.
 *
 * Interaction: a crosshair snaps to the nearest period under the pointer; the same
 * readout is available from the keyboard (arrow keys) and announced to screen readers.
 */
import { type KeyboardEvent, type PointerEvent, useMemo, useRef, useState } from "react";
import { useElementSize } from "@/hooks/useElementSize";
import {
  type ChartPoint,
  linearScale,
  nearestIndex,
  niceTicks,
  segments,
  timeTicks,
} from "./chartMath";
import styles from "./TimeSeriesChart.module.css";

export interface PointDescription {
  title: string;
  value: string;
  notes: string[];
}

const PLOT_HEIGHT = 240;
const AXIS_BAND = 28;
const TOP = 28;
const RIGHT = 64;
const MARKER_LIMIT = 60;
const MARKER_SPACING = 12;
const TICK_CHAR_WIDTH = 6.6;

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });

function tickFormatter(ticks: number[]): (value: number) => string {
  const largest = Math.max(...ticks.map(Math.abs));
  if (largest >= 1_000_000) return (value) => compact.format(value).replace("-", "−");
  const step = ticks.length > 1 ? Math.abs((ticks[1] ?? 0) - (ticks[0] ?? 0)) : 1;
  const decimals = step >= 1 ? 0 : Math.min(6, Math.ceil(-Math.log10(step)));
  const format = new Intl.NumberFormat("en", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return (value) => format.format(value).replace("-", "−");
}

/** Flagged values are triangles: a shape of their own, not only a colour. */
function triangle(x: number, y: number, size: number): string {
  return `M${x} ${y - size}L${x + size} ${y + size * 0.75}L${x - size} ${y + size * 0.75}Z`;
}

export function TimeSeriesChart({
  points,
  label,
  unit,
  contiguous,
  describe,
  endLabel,
}: {
  points: readonly ChartPoint[];
  label: string;
  unit: string;
  contiguous: (previous: ChartPoint, next: ChartPoint) => boolean;
  describe: (index: number) => PointDescription;
  endLabel?: (index: number) => string;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 640, height: 0 });
  const [active, setActive] = useState<number | null>(null);
  const [focused, setFocused] = useState(false);

  const valued = useMemo(() => points.filter((point) => point.value !== null), [points]);
  const geometry = useMemo(() => {
    const values = valued.map((point) => point.value ?? 0);
    const low = values.length ? Math.min(...values) : 0;
    const high = values.length ? Math.max(...values) : 1;
    const { ticks, domain } = niceTicks(low, high);
    const format = tickFormatter(ticks);
    const labelWidth = Math.max(...ticks.map((tick) => format(tick).length)) * TICK_CHAR_WIDTH;
    const left = Math.ceil(labelWidth + 14);
    const plotRight = Math.max(left + 40, width - RIGHT);
    const first = points[0]?.time ?? 0;
    const last = points[points.length - 1]?.time ?? first;
    const x = linearScale(first === last ? [first - 1, last + 1] : [first, last], [
      left,
      plotRight,
    ]);
    const y = linearScale(domain, [TOP + PLOT_HEIGHT, TOP]);
    const xTicks = timeTicks(first, last, Math.floor((plotRight - left) / 72));
    return { ticks, format, left, plotRight, x, y, xTicks };
  }, [points, valued, width]);

  const runs = useMemo(() => segments(points, contiguous), [points, contiguous]);
  const { ticks, format, left, plotRight, x, y, xTicks } = geometry;
  const bottom = TOP + PLOT_HEIGHT;
  const height = bottom + AXIS_BAND;
  // Markers only where there is room for them: at least MARKER_SPACING px per period.
  const showMarkers =
    valued.length <= MARKER_LIMIT &&
    (plotRight - left) / Math.max(1, points.length) >= MARKER_SPACING;
  const lastValued = [...points.keys()].reverse().find((index) => points[index]?.value !== null);
  const activePoint = active !== null ? points[active] : undefined;
  const description = active !== null ? describe(active) : null;
  // The slider's value: the active period, else the latest one with a value.
  const current = active ?? lastValued ?? Math.max(0, points.length - 1);
  const currentDescription = points.length ? describe(current) : null;
  const readout = currentDescription
    ? `${currentDescription.title}: ${currentDescription.value}. ${currentDescription.notes.join(" ")}`.trim()
    : "No values";
  const zeroInside = (ticks[0] ?? 0) < 0 && (ticks[ticks.length - 1] ?? 0) > 0;

  function activateAt(clientX: number) {
    const frame = frameRef.current;
    if (!frame || points.length === 0) return;
    const bounds = frame.getBoundingClientRect();
    const position = clientX - bounds.left;
    const first = points[0]?.time ?? 0;
    const last = points[points.length - 1]?.time ?? first;
    const ratio = (position - left) / Math.max(1, plotRight - left);
    setActive(nearestIndex(points, first + ratio * (last - first)));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (points.length === 0) return;
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, current - 1),
      ArrowDown: Math.max(0, current - 1),
      ArrowRight: Math.min(points.length - 1, current + 1),
      ArrowUp: Math.min(points.length - 1, current + 1),
      Home: 0,
      End: points.length - 1,
    };
    const next = moves[event.key];
    if (next !== undefined) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const tooltipX = activePoint ? x(activePoint.time) : 0;
  const tooltipOnLeft = tooltipX > (left + plotRight) / 2;
  // Beside the point, on the side with more room, so the reading covers little of the line.
  const pointY = activePoint?.value != null ? y(activePoint.value) : bottom;
  const tooltipBelow = pointY < TOP + PLOT_HEIGHT / 2;

  return (
    <div className={styles.chart}>
      {/* The chart is operated like a slider: arrow keys move through the periods and the
          current reading is the slider's value text, so screen readers announce it. */}
      <div
        ref={frameRef}
        className={styles.frame}
        style={{ height }}
        role="slider"
        aria-label={`${label}: values by period`}
        aria-valuemin={0}
        aria-valuemax={Math.max(0, points.length - 1)}
        aria-valuenow={current}
        aria-valuetext={readout}
        tabIndex={0}
        onPointerMove={(event: PointerEvent<HTMLDivElement>) => activateAt(event.clientX)}
        onPointerLeave={() => {
          if (!focused) setActive(null);
        }}
        onFocus={() => {
          setFocused(true);
          setActive((previous) => previous ?? current);
        }}
        onBlur={() => {
          setFocused(false);
          setActive(null);
        }}
        onKeyDown={onKeyDown}
      >
        <svg width={width} height={height} aria-hidden="true" className={styles.svg}>
          <text x={left} y={12} className={styles.unit}>
            {unit}
          </text>
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={left}
                x2={plotRight}
                y1={y(tick)}
                y2={y(tick)}
                className={tick === 0 && zeroInside ? styles.zero : styles.grid}
              />
              <text x={left - 8} y={y(tick)} className={styles.yTick}>
                {format(tick)}
              </text>
            </g>
          ))}
          {xTicks.map((tick) => (
            <text key={tick.time} x={x(tick.time)} y={bottom + 18} className={styles.xTick}>
              {tick.label}
            </text>
          ))}
          {points.map((point) =>
            point.value === null ? (
              <circle
                key={`missing-${point.key}`}
                cx={x(point.time)}
                cy={bottom - 4}
                r={3}
                className={styles.missing}
              />
            ) : null,
          )}
          {runs.map((run) =>
            run.length > 1 ? (
              <path
                key={`run-${run[0]?.key}`}
                className={styles.line}
                d={run
                  .map(
                    (point, index) => `${index ? "L" : "M"}${x(point.time)} ${y(point.value ?? 0)}`,
                  )
                  .join("")}
              />
            ) : null,
          )}
          {valued.map((point) => {
            const cx = x(point.time);
            const cy = y(point.value ?? 0);
            if (point.flagged) {
              return <path key={point.key} d={triangle(cx, cy, 6)} className={styles.flag} />;
            }
            // A value between two gaps has no line: its marker is always drawn.
            const isolated = runs.some((run) => run.length === 1 && run[0]?.key === point.key);
            return showMarkers || isolated || point.key === points[lastValued ?? -1]?.key ? (
              <circle key={point.key} cx={cx} cy={cy} r={4} className={styles.marker} />
            ) : null;
          })}
          {activePoint && (
            <g>
              <line
                x1={x(activePoint.time)}
                x2={x(activePoint.time)}
                y1={TOP}
                y2={bottom}
                className={styles.crosshair}
              />
              {activePoint.value !== null && (
                <circle
                  cx={x(activePoint.time)}
                  cy={y(activePoint.value)}
                  r={6}
                  className={styles.activeMarker}
                />
              )}
            </g>
          )}
          {endLabel && lastValued !== undefined && points[lastValued] && (
            <text
              x={x(points[lastValued].time) + 10}
              y={y(points[lastValued].value ?? 0)}
              className={styles.endLabel}
            >
              {endLabel(lastValued)}
            </text>
          )}
        </svg>
        {description && activePoint && (
          <div
            className={styles.tooltip}
            data-side={tooltipOnLeft ? "left" : "right"}
            data-vertical={tooltipBelow ? "below" : "above"}
            style={{
              left: tooltipOnLeft ? undefined : tooltipX + 12,
              right: tooltipOnLeft ? width - tooltipX + 12 : undefined,
              top: tooltipBelow ? pointY + 12 : pointY - 12,
            }}
          >
            <p className={styles.tooltipValue}>{description.value}</p>
            <p className={styles.tooltipTitle}>{description.title}</p>
            {description.notes.map((note) => (
              <p key={note} className={styles.tooltipNote}>
                {note}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
