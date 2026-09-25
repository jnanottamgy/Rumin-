/**
 * Whether the draws are enough: the mean of the first k draws as k grows (one line, sky
 * blue), inside a wash of ±2 standard errors. A mean that has settled within a narrow band
 * is estimated precisely; it says nothing about whether the stated distributions are right.
 * Operable from the keyboard; the table lists every checkpoint.
 */
import { type KeyboardEvent, type PointerEvent, useMemo, useRef, useState } from "react";
import { ScrollRegion } from "@/components/ScrollRegion";
import { linearScale, niceTicks } from "@/features/data/chartMath";
import simulation from "@/features/simulation/Simulation.module.css";
import { useElementSize } from "@/hooks/useElementSize";
import { toNumber } from "@/lib/decimal";
import type { ConvergenceCheckpoint } from "@/types/api";
import styles from "./Analyses.module.css";

const PLOT_HEIGHT = 150;
const TOP = 14;
const AXIS_BAND = 34;
const RIGHT = 16;
const LEFT = 62;

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });

function tick(value: number): string {
  return Math.abs(value) >= 10_000
    ? compact.format(value).replace("-", "−")
    : new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(value).replace("-", "−");
}

export function ConvergenceChart({
  checkpoints,
  format,
}: {
  checkpoints: ConvergenceCheckpoint[];
  format: (value: string) => string;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 560, height: 0 });
  const [active, setActive] = useState<number | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  const geometry = useMemo(() => {
    const bounds = checkpoints.flatMap((point) => {
      const mean = toNumber(point.mean);
      const error = point.standard_error ? 2 * toNumber(point.standard_error) : 0;
      return [mean - error, mean + error];
    });
    const values = niceTicks(Math.min(...bounds), Math.max(...bounds), 4);
    const draws = checkpoints.at(-1)?.draws ?? 1;
    const plotRight = Math.max(LEFT + 80, width - RIGHT);
    const x = linearScale([0, draws], [LEFT, plotRight]);
    const y = linearScale(values.domain, [TOP + PLOT_HEIGHT, TOP]);
    return { values, draws, plotRight, x, y };
  }, [checkpoints, width]);

  const { values, draws, plotRight, x, y } = geometry;
  const base = TOP + PLOT_HEIGHT;
  const height = base + AXIS_BAND;
  const withError = checkpoints.filter((point) => point.standard_error !== null);
  const band =
    withError.length > 1
      ? `${withError
          .map(
            (point, index) =>
              `${index ? "L" : "M"}${x(point.draws)} ${y(toNumber(point.mean) + 2 * toNumber(point.standard_error ?? "0"))}`,
          )
          .join("")}${[...withError]
          .reverse()
          .map(
            (point) =>
              `L${x(point.draws)} ${y(toNumber(point.mean) - 2 * toNumber(point.standard_error ?? "0"))}`,
          )
          .join("")}Z`
      : "";
  const line = checkpoints
    .map((point, index) => `${index ? "L" : "M"}${x(point.draws)} ${y(toNumber(point.mean))}`)
    .join("");
  const current = active ?? checkpoints.length - 1;
  const point = checkpoints[current];
  const describe = point
    ? `After ${point.draws} draws: mean ${format(point.mean)}${point.standard_error ? `, standard error ${format(point.standard_error)}` : ""}`
    : "";

  function activateAt(clientX: number) {
    const frame = frameRef.current;
    if (!frame || checkpoints.length === 0) return;
    const position = clientX - frame.getBoundingClientRect().left;
    let best = 0;
    checkpoints.forEach((candidate, index) => {
      const here = Math.abs(x(candidate.draws) - position);
      const bestDistance = Math.abs(x(checkpoints[best]?.draws ?? 0) - position);
      if (here < bestDistance) best = index;
    });
    setActive(best);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = checkpoints.length - 1;
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, current - 1),
      ArrowDown: Math.max(0, current - 1),
      ArrowRight: Math.min(last, current + 1),
      ArrowUp: Math.min(last, current + 1),
      Home: 0,
      End: last,
    };
    const next = moves[event.key];
    if (next !== undefined) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const activePoint = active !== null ? checkpoints[active] : undefined;
  const tooltipX = activePoint ? x(activePoint.draws) : 0;
  const tooltipOnLeft = tooltipX > (LEFT + plotRight) / 2;

  return (
    <figure className={simulation.chartFigure}>
      <div className={simulation.figureHeader}>
        <div className={simulation.chartLegend}>
          <span className={simulation.legendItem}>
            <span className={simulation.lineKey} aria-hidden="true" />
            Mean of the draws so far
          </span>
          <span className={simulation.legendItem}>Shaded: ±2 standard errors</span>
        </div>
        <fieldset className={simulation.toggle}>
          <legend className="visually-hidden">Convergence view</legend>
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
          aria-label="Mean of the draws as the draws accumulate"
          aria-valuemin={1}
          aria-valuemax={checkpoints.length}
          aria-valuenow={current + 1}
          aria-valuetext={describe}
          tabIndex={0}
          onPointerMove={(event: PointerEvent<HTMLDivElement>) => activateAt(event.clientX)}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onFocus={() => setActive((previous) => previous ?? current)}
          onKeyDown={onKeyDown}
        >
          <svg width={width} height={height} aria-hidden="true" className={simulation.chartSvg}>
            {values.ticks.map((value) => (
              <g key={`y-${value}`}>
                <line
                  x1={LEFT}
                  x2={plotRight}
                  y1={y(value)}
                  y2={y(value)}
                  className={simulation.grid}
                />
                <text x={LEFT - 8} y={y(value)} className={simulation.yTick}>
                  {tick(value)}
                </text>
              </g>
            ))}
            {band && <path d={band} className={styles.band} />}
            <path d={line} className={styles.line} />
            {activePoint && (
              <line
                x1={tooltipX}
                x2={tooltipX}
                y1={TOP}
                y2={base}
                className={simulation.crosshair}
              />
            )}
            {[0, Math.round(draws / 2), draws].map((value) => (
              <text key={`x-${value}`} x={x(value)} y={base + 16} className={simulation.xTick}>
                {value.toLocaleString("en")}
              </text>
            ))}
            <text x={LEFT} y={base + 30} className={simulation.xAxisName}>
              draws
            </text>
          </svg>
          {activePoint && (
            <div
              className={simulation.tooltip}
              style={{
                left: tooltipOnLeft ? undefined : tooltipX + 14,
                right: tooltipOnLeft ? width - tooltipX + 14 : undefined,
                top: TOP,
              }}
            >
              <p className={simulation.tooltipTitle}>After {activePoint.draws} draws</p>
              <dl className={simulation.tooltipRows}>
                <div>
                  <dt>Mean</dt>
                  <dd>{format(activePoint.mean)}</dd>
                </div>
                <div>
                  <dt>Standard error</dt>
                  <dd>{activePoint.standard_error ? format(activePoint.standard_error) : "—"}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>
      ) : (
        <ScrollRegion className={simulation.tableScroll}>
          <table className={simulation.table}>
            <caption className="visually-hidden">Mean of the draws at each checkpoint</caption>
            <thead>
              <tr>
                <th scope="col">Draws</th>
                <th scope="col">Mean</th>
                <th scope="col">Standard error</th>
              </tr>
            </thead>
            <tbody>
              {checkpoints.map((row) => (
                <tr key={row.draws}>
                  <td className="tabular">{row.draws}</td>
                  <td className="tabular">{format(row.mean)}</td>
                  <td className="tabular">
                    {row.standard_error ? format(row.standard_error) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}
      <figcaption className={simulation.figureCaption}>
        The mean settles as draws accumulate; the band narrows with the square root of the number of
        draws. A narrow band means the mean is estimated precisely for the stated distributions —
        not that those distributions are right.
      </figcaption>
    </figure>
  );
}
