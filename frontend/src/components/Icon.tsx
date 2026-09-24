/**
 * A tiny inline icon set (stroke icons on a 16px grid) — no icon library dependency.
 * Icons are decorative by default; pass `label` when the icon alone carries meaning.
 */
import type { SVGProps } from "react";

const PATHS = {
  arrowRight: "M3 8h9.5M8.5 4l4 4-4 4",
  arrowLeft: "M13 8H3.5M7.5 4l-4 4 4 4",
  arrowDown: "M8 3v9.5M4 8.5l4 4 4-4",
  arrowUp: "M8 13V3.5M4 7.5l4-4 4 4",
  chevronRight: "M6 3.5 10.5 8 6 12.5",
  chevronDown: "M3.5 6 8 10.5 12.5 6",
  play: "M5 3.5v9l7.5-4.5z",
  pause: "M5.5 3.5v9M10.5 3.5v9",
  rewind: "M12.5 4 8.5 8l4 4M7.5 4 3.5 8l4 4",
  check: "M3.5 8.5l3 3 6-7",
  close: "M4 4l8 8M12 4l-8 8",
  menu: "M2.5 4.5h11M2.5 8h11M2.5 11.5h11",
  plus: "M8 3v10M3 8h10",
  minus: "M3 8h10",
  alert: "M8 2.5l6 11H2l6-11zM8 6.5v3.2M8 11.6v.1",
  info: "M8 14A6 6 0 1 0 8 2a6 6 0 0 0 0 12zM8 7.3V11M8 5v.1",
  external: "M9.5 2.5h4v4M13.5 2.5 7.5 8.5M12 9.5v4H2.5V4h4",
  trash: "M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 9h5.8l.6-9",
  search: "M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10zM10.6 10.6 14 14",
  sun: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1",
  moon: "M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z",
  monitor: "M2 3h12v8H2zM6 14h4M8 11v3",
  circle: "M8 13.5A5.5 5.5 0 1 0 8 2.5a5.5 5.5 0 0 0 0 11z",
  dot: "M8 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  pending: "M8 13.5A5.5 5.5 0 1 0 8 2.5M8 5v3l2 1.5",
  layers: "M8 2 14 5 8 8 2 5l6-3zM2 8l6 3 6-3M2 11l6 3 6-3",
  grid: "M2.5 2.5h4.5v4.5H2.5zM9 2.5h4.5v4.5H9zM2.5 9h4.5v4.5H2.5zM9 9h4.5v4.5H9z",
  table: "M2.5 3h11v10h-11zM2.5 6.5h11M2.5 10h11M6.5 3v10",
  graph:
    "M4 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM12 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM5.3 9.8l5.4-3.3M5.5 10.8l5 1.6",
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
  label?: string;
}

export function Icon({ name, size = 16, label, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      {...rest}
    >
      {label && <title>{label}</title>}
      <path d={PATHS[name]} />
    </svg>
  );
}
