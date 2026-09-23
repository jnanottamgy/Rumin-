/** Small inline marks for legends, lists and panels — the same shapes the canvas draws. */
import type { EvidenceStatus, GraphNodeType, NodeNature } from "@/types/api";
import {
  EVIDENCE_ENCODING,
  type GlyphShape,
  glyphPath,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
} from "./encoding";

/** A glyph centred on the origin, for use inside an <svg> (canvas and legends). */
export function GlyphMark({
  shape,
  r,
  hollow,
  className,
}: {
  shape: GlyphShape;
  r: number;
  hollow: boolean;
  className?: string;
}) {
  if (shape === "dot" || shape === "ring") {
    return <circle className={className} r={r} data-hollow={hollow} />;
  }
  if (shape === "target") {
    return (
      <>
        <circle className={className} r={r} data-hollow="true" />
        <circle className={className} r={Math.max(1.4, r * 0.32)} data-hollow="false" />
      </>
    );
  }
  return <path className={className} d={glyphPath(shape, r) ?? ""} data-hollow={hollow} />;
}

/** The shape that stands for a node type. `hollow` overrides the type's default fill. */
export function TypeGlyph({
  type,
  size = 12,
  hollow,
}: {
  type: GraphNodeType;
  size?: number;
  hollow?: boolean;
}) {
  const encoding = NODE_TYPE_ENCODING[type];
  const isHollow = hollow ?? encoding.hollow;
  return (
    <svg
      width={size}
      height={size}
      viewBox="-7.5 -7.5 15 15"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none", overflow: "visible" }}
    >
      <g
        fill={isHollow ? "none" : "currentColor"}
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinejoin="round"
      >
        {encoding.shape === "target" ? (
          <>
            <circle r={4.6} fill="none" />
            <circle r={1.5} fill="currentColor" stroke="none" />
          </>
        ) : encoding.shape === "dot" || encoding.shape === "ring" ? (
          <circle r={encoding.shape === "dot" ? 4 : 4.6} />
        ) : (
          <path d={glyphPath(encoding.shape, 4.6) ?? ""} />
        )}
      </g>
    </svg>
  );
}

/** A short line drawn in an evidence status's pattern. */
export function EvidenceSwatch({
  status,
  width = 26,
  arrow = false,
}: {
  status: EvidenceStatus;
  width?: number;
  arrow?: boolean;
}) {
  const { dash, linecap } = EVIDENCE_ENCODING[status];
  return (
    <svg
      width={width}
      height="10"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none", overflow: "visible" }}
    >
      <line
        x1="1"
        y1="5"
        x2={arrow ? width - 6 : width - 1}
        y2="5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeDasharray={dash ?? undefined}
        strokeLinecap={linecap}
      />
      {arrow && (
        <path d={`M${width - 7} 1.6 ${width - 0.5} 5 ${width - 7} 8.4Z`} fill="currentColor" />
      )}
    </svg>
  );
}

/** The outer ring that marks fictional and sample records. */
export function NatureSwatch({ nature, size = 14 }: { nature: NodeNature; size?: number }) {
  const { ringDash } = NATURE_ENCODING[nature];
  return (
    <svg
      width={size}
      height={size}
      viewBox="-7.5 -7.5 15 15"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none", overflow: "visible" }}
    >
      <circle r={2.6} fill="currentColor" />
      {ringDash && (
        <circle
          r={6}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.1"
          strokeDasharray={ringDash}
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
