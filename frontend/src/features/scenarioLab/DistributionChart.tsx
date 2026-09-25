/**
 * The distribution of a Monte Carlo analysis's accepted draws: a histogram of equal-width
 * bins (one series, sky blue), with hairline rules at P5, P50 and P95, the execution's own
 * value in grey and an optional threshold dashed. Bars sit 2 px apart with rounded data
 * ends. The chart works as a slider from the keyboard; the table lists every bin exactly.
 * Counts describe the draws under the stated distributions — not probabilities of the
 * future.
 */
import { type KeyboardEvent, type PointerEvent, useMemo, useRef, useState } from "react";
import { linearScale, niceTicks } from "@/features/data/chartMath";
import simulation from "@/features/simulation/Simulation.module.css";
import { useElementSize } from "@/hooks/useElementSize";
import { toNumber } from "@/lib/decimal";
import type { HistogramBin } from "@/types/api";
import styles from "./Analyses.module.css";

export interface DistributionMarker {
  id: string;
  label: string;
  value: string;
  tone: "percentile" | "base" | "threshold";
}

const PLOT_HEIGHT = 170;
const TOP = 46;
const AXIS_BAND = 34;
const LEFT = 44;
const RIGHT = 16;

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });

function tick(value: number): string {
  return Math.abs(value) >= 10_000
    ? compact.format(value).replace("-", "−")
    : new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(value).replace("-", "−");
}

/** A bar from the baseline up to `top`, its data end rounded (4 px). */
function barPath(left: number, right: number, base: number, top: number): string {
  const width = right - left;
  const height = base - top;
  if (height < 0.5) return `M${left} ${base}H${right}`;
  const r = Math.min(4, width / 2, height);
  return `M${left} ${base}V${top + r}Q${left} ${top} ${left + r} ${top}H${right - r}Q${right} ${top} ${right} ${top + r}V${base}Z`;
}

export function DistributionChart({
  bins,
  accepted,
  markers,
  format,
  axisLabel,
}: {
  bins: HistogramBin[];
  accepted: number;
  markers: DistributionMarker[];
  /** Writes a value of the analysed line or metric. */
  format: (value: string) => string;
  axisLabel: string;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 640, height: 0 });
  const [active, setActive] = useState<number | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  const geometry = useMemo(() => {
    const edges = bins.flatMap((bin) => [toNumber(bin.low), toNumber(bin.high)]);
    const marks = markers.map((marker) => toNumber(marker.value));
    let low = Math.min(...edges, ...marks);
    let high = Math.max(...edges, ...marks);
    if (low === high) {
      const pad = Math.abs(low) * 0.05 || 1;
      low -= pad;
      high += pad;
    }
    const xTicks = niceTicks(low, high, 5);
    const counts = niceTicks(0, Math.max(1, ...bins.map((bin) => bin.count)), 3);
    const plotRight = Math.max(LEFT + 80, width - RIGHT);
    const x = linearScale(xTicks.domain, [LEFT, plotRight]);
    const y = linearScale(counts.domain, [TOP + PLOT_HEIGHT, TOP]);
    return { xTicks, counts, plotRight, x, y };
  }, [bins, markers, width]);

  const { xTicks, counts, plotRight, x, y } = geometry;
  const base = TOP + PLOT_HEIGHT;
  const height = base + AXIS_BAND;
  const current = active ?? bins.length - 1;
  const describe = (index: number) => {
    const bin = bins[index];
    if (!bin) return "";
    return `From ${format(bin.low)} to ${format(bin.high)}: ${bin.count} of ${accepted} draws`;
  };

  function activateAt(clientX: number) {
    const frame = frameRef.current;
    if (!frame) return;
    const position = clientX - frame.getBoundingClientRect().left;
    const index = bins.findIndex(
      (bin) => position >= x(toNumber(bin.low)) && position <= x(toNumber(bin.high)),
    );
    if (index >= 0) setActive(index);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, current - 1),
      ArrowDown: Math.max(0, current - 1),
      ArrowRight: Math.min(bins.length - 1, current + 1),
      ArrowUp: Math.min(bins.length - 1, current + 1),
      Home: 0,
      End: bins.length - 1,
    };
    const next = moves[event.key];
    if (next !== undefined) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  // Rules' labels sit on three rows so that close values do not overlap.
  const row: Record<DistributionMarker["tone"], number> = {
    percentile: TOP - 32,
    base: TOP - 19,
    threshold: TOP - 6,
  };
  const activeBin = active !== null ? bins[active] : undefined;
  const tooltipX = activeBin ? x((toNumber(activeBin.low) + toNumber(activeBin.high)) / 2) : 0;
  const tooltipOnLeft = tooltipX > (LEFT + plotRight) / 2;

  return (
    <figure className={simulation.chartFigure}>
      <div className={simulation.figureHeader}>
        <div className={simulation.chartLegend}>
          <span className={simulation.legendItem}>Draws per interval</span>
          <span className={simulation.legendItem}>
            <span className={simulation.lineKey} data-tone="baseline" aria-hidden="true" />
            As executed
          </span>
        </div>
        <fieldset className={simulation.toggle}>
          <legend className="visually-hidden">Distribution view</legend>
          <button type="button" aria-pressed={view === "chart"} onClick={() => setView("chart")}>
            Chart
          </button>
          <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>
            Table
          </button>
        </fieldset>
      </div>
      {view === "chart" ? (
        <div
          ref={frameRef}
          className={simulation.chartFrame}
          style={{ height }}
          role="slider"
          aria-label="Distribution of the draws"
          aria-valuemin={1}
          aria-valuemax={bins.length}
          aria-valuenow={current + 1}
          aria-valuetext={describe(current)}
          tabIndex={0}
          onPointerMove={(event: PointerEvent<HTMLDivElement>) => activateAt(event.clientX)}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onFocus={() => setActive((previous) => previous ?? current)}
          onKeyDown={onKeyDown}
        >
          <svg width={width} height={height} aria-hidden="true" className={simulation.chartSvg}>
            {counts.ticks.map((value) => (
              <g key={`y-${value}`}>
                <line
                  x1={LEFT}
                  x2={plotRight}
                  y1={y(value)}
                  y2={y(value)}
                  className={value === 0 ? simulation.zero : simulation.grid}
                />
                <text x={LEFT - 8} y={y(value)} className={simulation.yTick}>
                  {value}
                </text>
              </g>
            ))}
            {bins.map((bin, index) => {
              const left = x(toNumber(bin.low)) + 1;
              const right = Math.max(left + 1, x(toNumber(bin.high)) - 1);
              return (
                <path
                  // biome-ignore lint/suspicious/noArrayIndexKey: bins are positional
                  key={`b-${index}`}
                  d={barPath(left, right, base, y(bin.count))}
                  className={styles.bar}
                  data-active={active === index ? "true" : undefined}
                />
              );
            })}
            {markers.map((marker) => {
              const position = x(toNumber(marker.value));
              const className =
                marker.tone === "base"
                  ? styles.ruleBase
                  : marker.tone === "threshold"
                    ? styles.ruleThreshold
                    : styles.rule;
              const anchor = position > plotRight - 60 ? "end" : "middle";
              return (
                <g key={marker.id}>
                  <line
                    x1={position}
                    x2={position}
                    y1={row[marker.tone] + 4}
                    y2={base}
                    className={className}
                  />
                  <text
                    x={position}
                    y={row[marker.tone]}
                    textAnchor={anchor}
                    className={styles.ruleLabel}
                  >
                    {marker.label}
                  </text>
                </g>
              );
            })}
            {xTicks.ticks.map((value) => (
              <text key={`x-${value}`} x={x(value)} y={base + 16} className={simulation.xTick}>
                {tick(value)}
              </text>
            ))}
            <text x={LEFT} y={base + 30} className={simulation.xAxisName}>
              {axisLabel}
            </text>
          </svg>
          {activeBin && (
            <div
              className={simulation.tooltip}
              style={{
                left: tooltipOnLeft ? undefined : tooltipX + 14,
                right: tooltipOnLeft ? width - tooltipX + 14 : undefined,
                top: TOP,
              }}
            >
              <p className={simulation.tooltipTitle}>
                {format(activeBin.low)} to {format(activeBin.high)}
              </p>
              <dl className={simulation.tooltipRows}>
                <div>
                  <dt>Draws</dt>
                  <dd>
                    {activeBin.count} of {accepted}
                  </dd>
                </div>
              </dl>
            </div>
          )}
        </div>
      ) : (
        <div className={simulation.tableScroll}>
          <table className={simulation.table}>
            <caption className="visually-hidden">Draws in each interval</caption>
            <thead>
              <tr>
                <th scope="col">From</th>
                <th scope="col">To</th>
                <th scope="col">Draws</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: bins are positional
                <tr key={index}>
                  <td className="tabular">{format(bin.low)}</td>
                  <td className="tabular">{format(bin.high)}</td>
                  <td className="tabular">{bin.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <figcaption className={simulation.figureCaption}>
        How the {accepted.toLocaleString("en")} accepted draws spread over{" "}
        {bins.length === 1 ? "one interval" : `${bins.length} equal intervals`}. Rules mark the 5th,
        50th and 95th percentiles and the execution's own value
        {markers.some((marker) => marker.tone === "threshold") ? ", dashed the threshold" : ""}. The
        shape follows from the distributions you stated; it is not a forecast.
      </figcaption>
    </figure>
  );
}
