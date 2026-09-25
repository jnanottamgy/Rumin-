/**
 * A stand-in for the 3D universe's renderer. jsdom has no WebGL, so tests hand the canvas
 * host this instead of Three.js: it records what it was asked to draw (the scene model,
 * the palette, the camera, the frames) and projects points with a plain top-down camera —
 * x and z across the screen, at the scale the real perspective camera has at its target —
 * so a test can say exactly where a node is on screen and click it.
 */
import { FOV, type Orbit } from "@/features/universe/camera";
import type { Vec3 } from "@/features/universe/layout3d";
import type {
  Palette,
  Projected,
  RendererInfo,
  StratumGuide,
  UniverseRenderer,
} from "@/features/universe/rendererTypes";
import type { SceneModel } from "@/features/universe/scene";

export class StandInRenderer implements UniverseRenderer {
  scene: SceneModel | null = null;
  palette: Palette | null = null;
  guides: readonly StratumGuide[] = [];
  orbit: Orbit | null = null;
  orbits: Orbit[] = [];
  size = { width: 0, height: 0, pixelRatio: 1 };
  frames = 0;
  scenes = 0;
  disposed = false;

  constructor(
    readonly canvas: HTMLCanvasElement,
    readonly events: { onContextLost: () => void },
  ) {}

  setScene(scene: SceneModel, palette: Palette, guides: readonly StratumGuide[]): void {
    this.scene = scene;
    this.palette = palette;
    this.guides = guides;
    this.scenes += 1;
  }

  setOrbit(orbit: Orbit): void {
    this.orbit = orbit;
    this.orbits.push(orbit);
  }

  resize(width: number, height: number, pixelRatio: number): void {
    this.size = { width, height, pixelRatio };
  }

  render(): void {
    this.frames += 1;
  }

  project(point: Vec3): Projected {
    const orbit = this.orbit;
    if (!orbit) return { x: 0, y: 0, depth: 0, visible: false, scale: 0 };
    const scale = this.size.height / 2 / (orbit.radius * Math.tan(((FOV / 2) * Math.PI) / 180));
    const x = this.size.width / 2 + (point.x - orbit.target.x) * scale;
    const y = this.size.height / 2 + (point.z - orbit.target.z) * scale;
    return {
      x,
      y,
      depth: orbit.radius - (point.y - orbit.target.y),
      visible: x >= 0 && x <= this.size.width && y >= 0 && y <= this.size.height,
      scale,
    };
  }

  info(): RendererInfo {
    return { calls: 7, triangles: 1234, geometries: 9, programs: 4 };
  }

  dispose(): void {
    this.disposed = true;
  }

  /** The browser reclaims the WebGL context. */
  loseContext(): void {
    this.events.onContextLost();
  }

  /** Where a node is on screen now. */
  at(id: string): Projected {
    const node = this.scene?.nodes.find((item) => item.id === id);
    if (!node) throw new Error(`The scene does not hold ${id}.`);
    return this.project(node.position);
  }

  node(id: string) {
    const node = this.scene?.nodes.find((item) => item.id === id);
    if (!node) throw new Error(`The scene does not hold ${id}.`);
    return node;
  }

  edge(id: string) {
    const edge = this.scene?.edges.find((item) => item.id === id);
    if (!edge) throw new Error(`The scene does not hold ${id}.`);
    return edge;
  }
}
