/**
 * A quiet, non-interactive rendering of the real sample network for the landing page.
 * It is the actual data (same layout as the Universe), not decoration, and it is
 * described by a caption; the SVG itself is hidden from assistive technology.
 * The entrance animation is CSS-only and disabled under reduced motion.
 */
import type { CSSProperties } from "react";
import { KIND_ENCODING, nodeRadius, shapePath } from "./encoding";
import { geometryFor } from "./geometry";
import type { Layout } from "./layout";
import type { GraphModel } from "./model";
import styles from "./NetworkConstellation.module.css";

export function NetworkConstellation({ model, layout }: { model: GraphModel; layout: Layout }) {
  const { minX, minY, maxX, maxY } = layout.bounds;
  const pad = 24;
  const viewBox = `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;

  return (
    <svg className={styles.constellation} viewBox={viewBox} aria-hidden="true" focusable="false">
      <g className={styles.edges}>
        {model.edges.map((edge, index) => {
          const geometry = geometryFor(edge, model, layout);
          if (!geometry) return null;
          return (
            <path
              key={edge.id}
              d={geometry.d}
              data-category={edge.category}
              style={{ "--delay": `${120 + index * 14}ms` } as CSSProperties}
            />
          );
        })}
      </g>
      <g className={styles.nodes}>
        {model.nodes.map((node, index) => {
          const point = layout.positions.get(node.id);
          if (!point) return null;
          const { shape } = KIND_ENCODING[node.kind];
          const r = nodeRadius(node.kind, node.degree) * 0.85;
          const style = { "--delay": `${index * 22}ms` } as CSSProperties;
          return (
            <g key={node.id} transform={`translate(${point.x} ${point.y})`} style={style}>
              {shape === "dot" || shape === "ring" ? (
                <circle r={r} data-hollow={shape === "ring"} />
              ) : (
                <path d={shapePath(shape, r)} data-hollow={shape === "square"} />
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
