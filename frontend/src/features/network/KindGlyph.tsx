import type { EntityKind } from "@/types/api";
import { KIND_ENCODING, shapePath } from "./encoding";

/** The shape that stands for an entity kind, for legends, filters and lists. */
export function KindGlyph({ kind, size = 12 }: { kind: EntityKind; size?: number }) {
  const { shape } = KIND_ENCODING[kind];
  const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.4 };
  return (
    <svg
      width={size}
      height={size}
      viewBox="-7 -7 14 14"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none", overflow: "visible" }}
    >
      {shape === "dot" && <circle r={4} fill="currentColor" />}
      {shape === "ring" && <circle r={4.6} {...stroke} />}
      {shape === "diamond" && <path d={shapePath("diamond", 4.4)} fill="currentColor" />}
      {shape === "square" && <path d={shapePath("square", 5)} {...stroke} />}
    </svg>
  );
}
