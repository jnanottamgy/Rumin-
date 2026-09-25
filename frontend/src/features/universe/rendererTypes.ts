/**
 * The contract between the universe's React host and its renderer. Types only: the host
 * imports these without pulling in Three.js, which loads with the renderer, lazily.
 */
import type { Orbit } from "./camera";
import type { Vec3 } from "./layout3d";
import type { SceneModel } from "./scene";

/** Colours, read from the design tokens (so the scene follows the light and dark themes). */
export interface Palette {
  background: string;
  ink: string;
  hollow: string;
  structural: string;
  economic: string;
  dimmed: string;
  accent: string;
  guide: string;
}

export interface StratumGuide {
  level: number;
  height: number;
  radius: number;
  center: Vec3;
}

export interface Projected {
  /** CSS pixels from the canvas's top left. */
  x: number;
  y: number;
  /** Distance from the camera. */
  depth: number;
  /** In front of the camera and inside the view. */
  visible: boolean;
  /** Pixels per world unit at this depth (for hit radii). */
  scale: number;
}

export interface RendererInfo {
  calls: number;
  triangles: number;
  geometries: number;
  programs: number;
}

export interface UniverseRenderer {
  setScene(scene: SceneModel, palette: Palette, guides: readonly StratumGuide[]): void;
  setOrbit(orbit: Orbit): void;
  resize(width: number, height: number, pixelRatio: number): void;
  render(): void;
  project(point: Vec3): Projected;
  info(): RendererInfo;
  dispose(): void;
}

export type RendererFactory = (
  canvas: HTMLCanvasElement,
  events: { onContextLost: () => void },
) => UniverseRenderer;
