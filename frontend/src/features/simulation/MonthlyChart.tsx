/**
 * Month by month: the scenario against the baseline (two lines on one scale), and the
 * resulting monthly change as columns from zero. One x-axis, two plots — never two
 * y-scales on one plot.
 *
 * Marks follow the chart rules used across RUMIN: 2 px lines, markers with a surface
 * ring, columns ≤ 24 px with a rounded data end, hairline grid, the zero line emphasised.
 * The scenario is the one series in sky blue; the baseline is grey context. A crosshair
 * snaps to the month under the pointer; the chart works as a slider from the keyboard;
 * the table view lists every exact value.
 */
import { type KeyboardEvent, type PointerEvent, useMemo, useRef, useState } from "react";
import { linearScale, niceTicks } from "@/features/data/chartMath";
import { useElementSize } from "@/hooks/useElementSize";
import { toNumber } from "@/lib/decimal";
import { formatUnitValue } from "./format";
import styles from "./Simulation.module.css";

export interface MonthlySeries {
  id: string;
  label: string;
  unit: string;
  values: string[];
}

const LINE_HEIGHT = 190;
const COLUMN_HEIGHT = 120;
const TOP = 16;
const GAP = 44;
const AXIS_BAND = 30;
const RIGHT = 84;
const TICK_CHAR_WIDTH = 6.6;

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });

function tickFormat(ticks: number[]): (value: number) => string {
  const largest = Math.max(...ticks.map(Math.abs));
  if (largest >= 10_000) return (value) => compact.format(value).replace("-", "−");
  const step = ticks.length > 1 ? Math.abs((ticks[1] ?? 0) - (ticks[0] ?? 0)) : 1;
  const decimals = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step)));
  const format = new Intl.NumberFormat("en", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return (value) => format.format(value).replace("-", "−");
}

/** A column from the zero line to `y`, with a 4 px rounded end away from zero. */
function columnPath(x: number, width: number, zero: number, y: number): string {
  const height = Math.abs(zero - y);
  const r = Math.min(4, width / 2, height);
  const left = x - width / 2;
  const right = x + width / 2;
  if (height < 0.5) return `M${left} ${zero}H${right}`;
  if (y < zero) {
    return `M${left} ${zero}V${y + r}Q${left} ${y} ${left + r} ${y}H${right - r}Q${right} ${y} ${right} ${y + r}V${zero}Z`;
  }
  return `M${left} ${zero}V${y - r}Q${left} ${y} ${left + r} ${y}H${right - r}Q${right} ${y} ${right} ${y - r}V${zero}Z`;
}

export function MonthlyChart({
  scenario,
  baseline,
  change,
  table,
}: {
  scenario: MonthlySeries;
  baseline: MonthlySeries;
  change: MonthlySeries;
  /** Every monthly series, for the tooltip and the table view. */
  table: MonthlySeries[];
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { width } = useElementSize(frameRef, { width: 680, height: 0 });
  const [active, setActive] = useState<number | null>(null);
  const [focused, setFocused] = useState(false);
  const [view, setView] = useState<"chart" | "table">("chart");
  const months = scenario.values.length;

  const geometry = useMemo(() => {
    const lineValues = [...scenario.values, ...baseline.values].map(toNumber);
    const lines = niceTicks(Math.min(...lineValues), Math.max(...lineValues), 4);
    const changes = change.values.map(toNumber);
    const columns = niceTicks(Math.min(0, ...changes), Math.max(0, ...changes), 3);
    const formatLines = tickFormat(lines.ticks);
    const formatColumns = tickFormat(columns.ticks);
    const labelWidth =
      Math.max(
        ...lines.ticks.map((tick) => formatLines(tick).length),
        ...columns.ticks.map((tick) => formatColumns(tick).length),
      ) * TICK_CHAR_WIDTH;
    const left = Math.ceil(labelWidth + 14);
    const plotRight = Math.max(left + 60, width - RIGHT);
    const band = (plotRight - left) / Math.max(1, months);
    const x = (index: number) => left + (index + 0.5) * band;
    const lineTop = TOP;
    const lineBottom = lineTop + LINE_HEIGHT;
    const columnTop = lineBottom + GAP;
    const columnBottom = columnTop + COLUMN_HEIGHT;
    const yLine = linearScale(lines.domain, [lineBottom, lineTop]);
    const yColumn = linearScale(columns.domain, [columnBottom, columnTop]);
    return {
      lines,
      columns,
      formatLines,
      formatColumns,
      left,
      plotRight,
      band,
      x,
      lineTop,
      lineBottom,
      columnTop,
      columnBottom,
      yLine,
      yColumn,
    };
  }, [scenario, baseline, change, months, width]);

  const {
    lines,
    columns,
    formatLines,
    formatColumns,
    left,
    plotRight,
    band,
    x,
    lineTop,
    columnTop,
    columnBottom,
    yLine,
    yColumn,
  } = geometry;
  const height = columnBottom + AXIS_BAND;
  const columnWidth = Math.max(2, Math.min(24, band * 0.62));
  const showMarkers = band >= 12;
  // Label every month when there is room, else every 2nd, 3rd, 6th or 12th.
  const tickEvery = [1, 2, 3, 6, 12].find((step) => step * band >= 26) ?? 12;
  const current = active ?? months - 1;
  const readout = `Month ${current + 1}: ${table
    .map((series) => `${series.label} ${formatUnitValue(series.values[current], series.unit)}`)
    .join("; ")}`;

  const path = (series: MonthlySeries) =>
    series.values
      .map((value, index) => `${index ? "L" : "M"}${x(index)} ${yLine(toNumber(value))}`)
      .join("");

  function activateAt(clientX: number) {
    const frame = frameRef.current;
    if (!frame || months === 0) return;
    const position = clientX - frame.getBoundingClientRect().left;
    const index = Math.floor((position - left) / Math.max(1, band));
    setActive(Math.min(months - 1, Math.max(0, index)));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, current - 1),
      ArrowDown: Math.max(0, current - 1),
      ArrowRight: Math.min(months - 1, current + 1),
      ArrowUp: Math.min(months - 1, current + 1),
      Home: 0,
      End: months - 1,
    };
    const next = moves[event.key];
    if (next !== undefined) {
      event.preventDefault();
      setActive(next);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const lastIndex = months - 1;
  const endScenario = yLine(toNumber(scenario.values[lastIndex] ?? "0"));
  const endBaseline = yLine(toNumber(baseline.values[lastIndex] ?? "0"));
  // End labels sit at their lines' ends; when the lines meet, the legend carries identity.
  const endLabelsApart = Math.abs(endScenario - endBaseline) >= 14;
  const zeroColumn = yColumn(0);
  const tooltipX = active !== null ? x(active) : 0;
  const tooltipOnLeft = tooltipX > (left + plotRight) / 2;

  return (
    <figure className={styles.chartFigure}>
      <div className={styles.figureHeader}>
        <div className={styles.chartLegend}>
          <span className={styles.legendItem}>
            <span className={styles.lineKey} data-tone="scenario" aria-hidden="true" />
            {scenario.label}
          </span>
          <span className={styles.legendItem}>
            <span className={styles.lineKey} data-tone="baseline" aria-hidden="true" />
            {baseline.label}
          </span>
        </div>
        <fieldset className={styles.toggle}>
          <legend className="visually-hidden">Monthly view</legend>
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
          className={styles.chartFrame}
          style={{ height }}
          role="slider"
          aria-label="Monthly results"
          aria-valuemin={1}
          aria-valuemax={months}
          aria-valuenow={current + 1}
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
          <svg width={width} height={height} aria-hidden="true" className={styles.chartSvg}>
            <text x={left} y={lineTop - 4} className={styles.axisUnit}>
              {scenario.unit}
            </text>
            {lines.ticks.map((tick) => (
              <g key={`l-${tick}`}>
                <line
                  x1={left}
                  x2={plotRight}
                  y1={yLine(tick)}
                  y2={yLine(tick)}
                  className={styles.grid}
                />
                <text x={left - 8} y={yLine(tick)} className={styles.yTick}>
                  {formatLines(tick)}
                </text>
              </g>
            ))}
            <path d={path(baseline)} className={styles.lineBaseline} />
            <path d={path(scenario)} className={styles.lineScenario} />
            {showMarkers &&
              scenario.values.map((value, index) => (
                <circle
                  // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                  key={`m-${index}`}
                  cx={x(index)}
                  cy={yLine(toNumber(value))}
                  r={4}
                  className={styles.markerScenario}
                />
              ))}
            {endLabelsApart && (
              <>
                <text x={x(lastIndex) + 10} y={endScenario} className={styles.endLabel}>
                  {scenario.label}
                </text>
                <text x={x(lastIndex) + 10} y={endBaseline} className={styles.endLabelMuted}>
                  {baseline.label}
                </text>
              </>
            )}

            <text x={left} y={columnTop - 8} className={styles.axisUnit}>
              {change.label} ({change.unit})
            </text>
            {columns.ticks.map((tick) => (
              <g key={`c-${tick}`}>
                <line
                  x1={left}
                  x2={plotRight}
                  y1={yColumn(tick)}
                  y2={yColumn(tick)}
                  className={tick === 0 ? styles.zero : styles.grid}
                />
                <text x={left - 8} y={yColumn(tick)} className={styles.yTick}>
                  {formatColumns(tick)}
                </text>
              </g>
            ))}
            {change.values.map((value, index) => (
              <path
                // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                key={`c-${index}`}
                d={columnPath(x(index), columnWidth, zeroColumn, yColumn(toNumber(value)))}
                className={styles.column}
                data-active={active === index ? "true" : undefined}
              />
            ))}
            {Array.from({ length: months }, (_, index) =>
              (index + 1) % tickEvery === 0 || index === 0 ? (
                <text
                  // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                  key={`x-${index}`}
                  x={x(index)}
                  y={columnBottom + 18}
                  className={styles.xTick}
                >
                  {index + 1}
                </text>
              ) : null,
            )}
            <text x={plotRight + 12} y={columnBottom + 18} className={styles.xAxisName}>
              month
            </text>

            {active !== null && (
              <g>
                <line
                  x1={x(active)}
                  x2={x(active)}
                  y1={lineTop}
                  y2={columnBottom}
                  className={styles.crosshair}
                />
                <circle
                  cx={x(active)}
                  cy={yLine(toNumber(scenario.values[active] ?? "0"))}
                  r={6}
                  className={styles.activeMarker}
                />
              </g>
            )}
          </svg>
          {active !== null && (
            <div
              className={styles.tooltip}
              style={{
                left: tooltipOnLeft ? undefined : tooltipX + 14,
                right: tooltipOnLeft ? width - tooltipX + 14 : undefined,
                top: lineTop + 8,
              }}
            >
              <p className={styles.tooltipTitle}>Month {active + 1}</p>
              <dl className={styles.tooltipRows}>
                {table.map((series) => (
                  <div key={series.id}>
                    <dt>{series.label}</dt>
                    <dd>{formatUnitValue(series.values[active], series.unit)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      ) : (
        <div className={styles.tableScroll}>
          <table className={styles.table}>
            <caption className="visually-hidden">Monthly results, exact values</caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                {table.map((series) => (
                  <th key={series.id} scope="col">
                    {series.label}
                    <span className={styles.tableUnit}>{series.unit}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: months }, (_, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
                <tr key={index}>
                  <th scope="row">{index + 1}</th>
                  {table.map((series) => (
                    <td key={series.id} className="tabular">
                      {formatUnitValue(series.values[index], series.unit, { exact: true })}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <figcaption className={styles.figureCaption}>
        Top: {scenario.label.toLowerCase()} against {baseline.label.toLowerCase()}, per month.
        Bottom: {change.label.toLowerCase()} per month. The table lists every exact value.
      </figcaption>
    </figure>
  );
}
