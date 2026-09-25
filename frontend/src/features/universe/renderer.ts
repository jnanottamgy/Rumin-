/**
 * The universe's renderer: Three.js, drawing a `SceneModel` and nothing else.
 *
 * Every mark's meaning was decided in `scene.ts`; this module only turns records into
 * pixels, as cheaply as it can:
 *
 * - **Nodes**: one instanced mesh per shape, plus an outline mesh per shape drawn behind it
 *   (the same geometry, a little larger, back faces only). Solid kinds are ink with a
 *   surface-coloured outline, so they stay legible where lines cross them; hollow kinds are
 *   surface-coloured with an ink outline. The selection, the node under the pointer and an
 *   overlay's changed variables and entity get a sky-blue outline.
 * - **Edges**: one draw call for all of them — instanced screen-space quads with a pattern
 *   shader: solid, dashes, dash-dot and dots, in CSS pixels, as in the 2D explorer.
 *   Directed edges get an arrowhead near their target.
 * - **Nature**: a camera-facing ring around fictional (dashed) and sample (dotted) records.
 * - **Strata**: a faint circle on each layer's height; their names are HTML, drawn by the host.
 *
 * It renders only when asked (the host asks after a change), caps the pixel ratio at 2, and
 * frees every geometry, material and the WebGL context when disposed.
 */
import {
  AmbientLight,
  BackSide,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  CapsuleGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  DynamicDrawUsage,
  HemisphereLight,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
  OctahedronGeometry,
  PerspectiveCamera,
  PlaneGeometry,
  Quaternion,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  TorusGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import type { GlyphShape } from "@/features/graph/encoding";
import { eye, FOV, type Orbit } from "./camera";
import type { Vec3 } from "./layout3d";
import type {
  Projected,
  RendererFactory,
  RendererInfo,
  StratumGuide,
  UniverseRenderer,
} from "./rendererTypes";
import type { Pattern, SceneEdge, SceneNode } from "./scene";

const PATTERN_CODE: Record<Pattern, number> = { solid: 0, dash: 1, dashdot: 2, dot: 3 };

const EDGE_VERTEX = /* glsl */ `
attribute vec3 instanceStart;
attribute vec3 instanceEnd;
attribute vec3 instanceTint;
attribute float instanceWidth;
attribute float instancePattern;
attribute float instanceAlpha;
uniform vec2 resolution;
uniform float pixelRatio;
uniform float near;
varying vec3 vColor;
varying float vAlpha;
varying float vPattern;
varying float vAlong;
varying float vAcross;
varying float vHalf;

void main() {
  vec4 start = modelViewMatrix * vec4(instanceStart, 1.0);
  vec4 end = modelViewMatrix * vec4(instanceEnd, 1.0);
  if (start.z > -near && end.z > -near) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    return;
  }
  if (start.z > -near) {
    start = mix(start, end, (-near - start.z) / (end.z - start.z));
  } else if (end.z > -near) {
    end = mix(end, start, (-near - end.z) / (start.z - end.z));
  }
  vec4 clipStart = projectionMatrix * start;
  vec4 clipEnd = projectionMatrix * end;
  vec2 screenStart = (clipStart.xy / clipStart.w * 0.5 + 0.5) * resolution;
  vec2 screenEnd = (clipEnd.xy / clipEnd.w * 0.5 + 0.5) * resolution;
  vec2 along = screenEnd - screenStart;
  // (GLSL ES reserves "half", and "length" is a built-in function: neither names a variable.)
  float span = max(length(along), 0.0001);
  vec2 normal = vec2(-along.y, along.x) / span;
  float halfWidth = instanceWidth * pixelRatio * 0.5;
  vec4 clip = mix(clipStart, clipEnd, position.x);
  clip.xy += normal * position.y * (halfWidth + pixelRatio) / resolution * 2.0 * clip.w;
  gl_Position = clip;
  vAlong = position.x * span / pixelRatio;
  vAcross = position.y * (halfWidth + pixelRatio);
  vHalf = halfWidth;
  vColor = instanceTint;
  vAlpha = instanceAlpha;
  vPattern = instancePattern;
}
`;

const EDGE_FRAGMENT = /* glsl */ `
uniform float pixelRatio;
varying vec3 vColor;
varying float vAlpha;
varying float vPattern;
varying float vAlong;
varying float vAcross;
varying float vHalf;

float drawn(float along, float pattern) {
  if (pattern < 0.5) return 1.0;
  if (pattern < 1.5) return step(mod(along, 10.5), 7.0);
  if (pattern < 2.5) {
    float m = mod(along, 12.2);
    return (m < 6.0 || (m >= 8.5 && m < 9.7)) ? 1.0 : 0.0;
  }
  return step(mod(along, 4.6), 1.6);
}

void main() {
  if (drawn(vAlong, vPattern) < 0.5) discard;
  float coverage = clamp(vHalf + 0.5 * pixelRatio - abs(vAcross), 0.0, 1.0);
  if (coverage <= 0.0) discard;
  gl_FragColor = vec4(vColor, vAlpha * coverage);
  #include <colorspace_fragment>
}
`;

const HALO_VERTEX = /* glsl */ `
attribute float instanceDotted;
varying vec2 vPoint;
varying float vDotted;
varying vec3 vColor;

void main() {
  vec4 center = modelViewMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
  float size = length(instanceMatrix[0].xyz);
  center.xy += position.xy * size;
  gl_Position = projectionMatrix * center;
  vPoint = position.xy;
  vDotted = instanceDotted;
  #ifdef USE_INSTANCING_COLOR
    vColor = instanceColor;
  #else
    vColor = vec3(0.0);
  #endif
}
`;

const HALO_FRAGMENT = /* glsl */ `
varying vec2 vPoint;
varying float vDotted;
varying vec3 vColor;

void main() {
  float r = length(vPoint);
  if (r < 0.86 || r > 1.0) discard;
  float turn = fract(atan(vPoint.y, vPoint.x) / 6.28318530718 + 0.5);
  float on = vDotted > 0.5 ? step(fract(turn * 22.0), 0.3) : step(fract(turn * 12.0), 0.62);
  if (on < 0.5) discard;
  gl_FragColor = vec4(vColor, 1.0);
  #include <colorspace_fragment>
}
`;

/**
 * A node's solid. `coarse` is the outline hull's: only its silhouette shows, so it needs
 * fewer faces (the hull is drawn for every node, so it doubles the scene's triangles).
 */
function shapeGeometry(shape: GlyphShape, coarse = false): BufferGeometry {
  switch (shape) {
    case "dot":
    case "ring":
      return coarse ? new SphereGeometry(1, 12, 8) : new SphereGeometry(1, 18, 12);
    case "diamond":
      return new OctahedronGeometry(1.3);
    case "square":
      return new BoxGeometry(1.55, 1.55, 1.55);
    case "hexagon":
      return new CylinderGeometry(1.1, 1.1, 0.95, 6);
    case "target":
      return coarse ? new TorusGeometry(1.0, 0.3, 6, 18) : new TorusGeometry(1.0, 0.3, 8, 24);
    case "pill":
      return new CapsuleGeometry(0.62, 1.15, coarse ? 2 : 4, coarse ? 8 : 12).rotateZ(Math.PI / 2);
    case "triangle":
      return new ConeGeometry(1.15, 1.9, 3).translate(0, 0.2, 0);
    case "invertedTriangle":
      return new ConeGeometry(1.15, 1.9, 3).rotateX(Math.PI).translate(0, -0.2, 0);
    default:
      return coarse ? new SphereGeometry(1, 12, 8) : new SphereGeometry(1, 16, 12);
  }
}

interface ShapeMeshes {
  fill: InstancedMesh;
  hull: InstancedMesh;
  core: InstancedMesh | null;
  capacity: number;
  nodes: SceneNode[];
}

const OUTLINE = 1.16;
const MARKED_OUTLINE = 1.34;

export const createRenderer: RendererFactory = (canvas, events) => {
  const renderer = new WebGLRenderer({
    canvas,
    antialias: true,
    alpha: false,
    powerPreference: "high-performance",
  });
  const onLost = (event: Event) => {
    event.preventDefault();
    events.onContextLost();
  };
  canvas.addEventListener("webglcontextlost", onLost);

  const scene = new Scene();
  const camera = new PerspectiveCamera(FOV, 1, 1, 30000);
  scene.add(new HemisphereLight(0xffffff, 0x8a867c, 1.15));
  scene.add(new AmbientLight(0xffffff, 0.35));
  const sun = new DirectionalLight(0xffffff, 0.9);
  sun.position.set(0.4, 1, 0.6);
  scene.add(sun);

  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(item: T): T => {
    disposables.push(item);
    return item;
  };

  const fillMaterial = keep(new MeshLambertMaterial({ color: 0xffffff }));
  const hullMaterial = keep(new MeshBasicMaterial({ color: 0xffffff, side: BackSide }));
  const basicMaterial = keep(new MeshBasicMaterial({ color: 0xffffff }));

  const shapes = new Map<GlyphShape, ShapeMeshes>();
  const geometries = new Map<GlyphShape, BufferGeometry>();
  const hullGeometries = new Map<GlyphShape, BufferGeometry>();
  const coreGeometry = keep(new SphereGeometry(0.42, 16, 12));

  // Edges: a quad per edge, instanced.
  const edgeGeometry = keep(new InstancedBufferGeometry());
  edgeGeometry.setAttribute(
    "position",
    new BufferAttribute(new Float32Array([0, -1, 0, 1, -1, 0, 0, 1, 0, 1, 1, 0]), 3),
  );
  edgeGeometry.setIndex([0, 1, 2, 2, 1, 3]);
  const resolution = new Vector2(1, 1);
  const pixelRatioUniform = { value: 1 };
  const edgeMaterial = keep(
    new ShaderMaterial({
      vertexShader: EDGE_VERTEX,
      fragmentShader: EDGE_FRAGMENT,
      uniforms: {
        resolution: { value: resolution },
        pixelRatio: pixelRatioUniform,
        near: { value: camera.near },
      },
      transparent: true,
      depthWrite: false,
    }),
  );
  const edgeMesh = new Mesh(edgeGeometry, edgeMaterial);
  edgeMesh.frustumCulled = false;
  scene.add(edgeMesh);
  let edgeCapacity = 0;

  const arrowGeometry = keep(new ConeGeometry(1, 2.4, 10).translate(0, -1.2, 0));
  let arrows: InstancedMesh | null = null;

  const haloGeometry = keep(new PlaneGeometry(2, 2));
  const haloMaterial = keep(
    new ShaderMaterial({
      vertexShader: HALO_VERTEX,
      fragmentShader: HALO_FRAGMENT,
      depthWrite: false,
      transparent: true,
    }),
  );
  let halos: InstancedMesh | null = null;

  const guideMaterial = keep(new LineBasicMaterial({ color: 0xffffff, transparent: true }));
  let guides: LineSegments | null = null;

  let colors = {
    background: new Color(),
    ink: new Color(),
    hollow: new Color(),
    structural: new Color(),
    economic: new Color(),
    dimmed: new Color(),
    accent: new Color(),
    guide: new Color(),
  };
  let width = 1;
  let height = 1;

  const matrix = new Matrix4();
  const quaternion = new Quaternion();
  const scale = new Vector3();
  const position = new Vector3();
  const identity = new Quaternion();
  const helper = new Object3D();

  function meshesFor(shape: GlyphShape, count: number): ShapeMeshes {
    const existing = shapes.get(shape);
    if (existing && existing.capacity >= count) return existing;
    if (existing) {
      scene.remove(existing.fill, existing.hull);
      existing.fill.dispose();
      existing.hull.dispose();
      if (existing.core) {
        scene.remove(existing.core);
        existing.core.dispose();
      }
    }
    let geometry = geometries.get(shape);
    if (!geometry) {
      geometry = shapeGeometry(shape);
      geometries.set(shape, geometry);
    }
    let hullGeometry = hullGeometries.get(shape);
    if (!hullGeometry) {
      hullGeometry = shapeGeometry(shape, true);
      hullGeometries.set(shape, hullGeometry);
    }
    const capacity = Math.max(8, count * 2);
    const fill = new InstancedMesh(geometry, fillMaterial, capacity);
    const hull = new InstancedMesh(hullGeometry, hullMaterial, capacity);
    const core =
      shape === "target" ? new InstancedMesh(coreGeometry, basicMaterial, capacity) : null;
    for (const mesh of [fill, hull, core]) {
      if (!mesh) continue;
      mesh.frustumCulled = false;
      mesh.instanceMatrix.setUsage(DynamicDrawUsage);
      mesh.count = 0;
      scene.add(mesh);
    }
    const made = { fill, hull, core, capacity, nodes: [] };
    shapes.set(shape, made);
    return made;
  }

  function fillColor(node: SceneNode, target: Color): Color {
    if (node.hollow) {
      return target.copy(node.tone === "dimmed" ? colors.background : colors.hollow);
    }
    if (node.tone === "dimmed") return target.copy(colors.ink).lerp(colors.background, 0.72);
    return target.copy(colors.ink);
  }

  function marked(node: SceneNode): boolean {
    return node.selected || node.role === "changed" || node.role === "entity";
  }

  function hullColor(node: SceneNode, target: Color): Color {
    if (marked(node)) return target.copy(colors.accent);
    if (node.hollow) return target.copy(node.tone === "dimmed" ? colors.dimmed : colors.ink);
    return target.copy(colors.background);
  }

  /** Instance matrices for one shape; the currency ring faces the camera. */
  function placeNodes(entry: ShapeMeshes, shape: GlyphShape) {
    const facing = shape === "target";
    entry.nodes.forEach((node, index) => {
      const { x, y, z } = node.position;
      position.set(x, y, z);
      if (facing) {
        helper.position.copy(position);
        helper.lookAt(camera.position);
        quaternion.copy(helper.quaternion);
      } else {
        quaternion.copy(identity);
      }
      const outline = marked(node) ? MARKED_OUTLINE : OUTLINE;
      scale.setScalar(node.size);
      entry.fill.setMatrixAt(index, matrix.compose(position, quaternion, scale));
      scale.setScalar(node.size * outline);
      entry.hull.setMatrixAt(index, matrix.compose(position, quaternion, scale));
      if (entry.core) {
        scale.setScalar(node.size);
        entry.core.setMatrixAt(index, matrix.compose(position, quaternion, scale));
      }
    });
    entry.fill.instanceMatrix.needsUpdate = true;
    entry.hull.instanceMatrix.needsUpdate = true;
    if (entry.core) entry.core.instanceMatrix.needsUpdate = true;
  }

  function setNodes(nodes: readonly SceneNode[]) {
    const byShape = new Map<GlyphShape, SceneNode[]>();
    for (const node of nodes) byShape.set(node.shape, [...(byShape.get(node.shape) ?? []), node]);
    for (const [shape, entry] of shapes) {
      if (!byShape.has(shape)) {
        entry.nodes = [];
        entry.fill.count = 0;
        entry.hull.count = 0;
        if (entry.core) entry.core.count = 0;
      }
    }
    const color = new Color();
    for (const [shape, list] of byShape) {
      const entry = meshesFor(shape, list.length);
      entry.nodes = list;
      list.forEach((node, index) => {
        entry.fill.setColorAt(index, fillColor(node, color));
        entry.hull.setColorAt(index, hullColor(node, color));
        entry.core?.setColorAt(
          index,
          color.copy(node.tone === "dimmed" ? colors.dimmed : colors.ink),
        );
      });
      for (const mesh of [entry.fill, entry.hull, entry.core]) {
        if (!mesh) continue;
        mesh.count = list.length;
        if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      }
      placeNodes(entry, shape);
    }
  }

  function edgeColor(edge: SceneEdge, target: Color): Color {
    if (edge.tone === "emphasis") return target.copy(colors.accent);
    if (edge.tone === "dimmed") return target.copy(colors.dimmed);
    return target.copy(edge.economic ? colors.economic : colors.structural);
  }

  function setEdges(edges: readonly SceneEdge[], nodes: readonly SceneNode[]) {
    const count = edges.length;
    if (count > edgeCapacity) {
      edgeCapacity = Math.max(64, count * 2);
      const attribute = (size: number) =>
        new InstancedBufferAttribute(new Float32Array(edgeCapacity * size), size).setUsage(
          DynamicDrawUsage,
        );
      edgeGeometry.setAttribute("instanceStart", attribute(3));
      edgeGeometry.setAttribute("instanceEnd", attribute(3));
      edgeGeometry.setAttribute("instanceTint", attribute(3));
      edgeGeometry.setAttribute("instanceWidth", attribute(1));
      edgeGeometry.setAttribute("instancePattern", attribute(1));
      edgeGeometry.setAttribute("instanceAlpha", attribute(1));
    }
    const start = edgeGeometry.getAttribute("instanceStart") as InstancedBufferAttribute;
    const end = edgeGeometry.getAttribute("instanceEnd") as InstancedBufferAttribute;
    const tint = edgeGeometry.getAttribute("instanceTint") as InstancedBufferAttribute;
    const widths = edgeGeometry.getAttribute("instanceWidth") as InstancedBufferAttribute;
    const patterns = edgeGeometry.getAttribute("instancePattern") as InstancedBufferAttribute;
    const alphas = edgeGeometry.getAttribute("instanceAlpha") as InstancedBufferAttribute;
    const color = new Color();
    edges.forEach((edge, index) => {
      start.setXYZ(index, edge.from.x, edge.from.y, edge.from.z);
      end.setXYZ(index, edge.to.x, edge.to.y, edge.to.z);
      edgeColor(edge, color);
      tint.setXYZ(index, color.r, color.g, color.b);
      widths.setX(index, edge.width);
      patterns.setX(index, PATTERN_CODE[edge.pattern]);
      alphas.setX(index, edge.tone === "dimmed" ? 0.55 : 1);
    });
    for (const attribute of [start, end, tint, widths, patterns, alphas]) {
      attribute.needsUpdate = true;
    }
    edgeGeometry.instanceCount = count;

    const sizeOf = new Map(nodes.map((node) => [node.id, node.size]));
    const directed = edges.filter((edge) => edge.directed);
    if (!arrows || arrows.instanceMatrix.count < directed.length) {
      if (arrows) {
        scene.remove(arrows);
        arrows.dispose();
      }
      arrows = new InstancedMesh(arrowGeometry, basicMaterial, Math.max(32, directed.length * 2));
      arrows.frustumCulled = false;
      scene.add(arrows);
    }
    const up = new Vector3(0, 1, 0);
    const direction = new Vector3();
    directed.forEach((edge, index) => {
      direction
        .set(edge.to.x - edge.from.x, edge.to.y - edge.from.y, edge.to.z - edge.from.z)
        .normalize();
      const back = (sizeOf.get(edge.target) ?? 6) * 1.35 + 1.5;
      position.set(edge.to.x, edge.to.y, edge.to.z).addScaledVector(direction, -back);
      quaternion.setFromUnitVectors(up, direction);
      scale.setScalar(1.1 + edge.width * 0.35);
      arrows?.setMatrixAt(index, matrix.compose(position, quaternion, scale));
      arrows?.setColorAt(index, edgeColor(edge, color));
    });
    if (arrows) {
      arrows.count = directed.length;
      arrows.instanceMatrix.needsUpdate = true;
      if (arrows.instanceColor) arrows.instanceColor.needsUpdate = true;
    }
  }

  function setHalos(nodes: readonly SceneNode[]) {
    const marked = nodes.filter((node) => node.nature !== "real");
    if (!halos || halos.instanceMatrix.count < marked.length) {
      if (halos) {
        scene.remove(halos);
        halos.dispose();
      }
      const capacity = Math.max(16, marked.length * 2);
      halos = new InstancedMesh(haloGeometry, haloMaterial, capacity);
      haloGeometry.setAttribute(
        "instanceDotted",
        new InstancedBufferAttribute(new Float32Array(capacity), 1),
      );
      halos.frustumCulled = false;
      scene.add(halos);
    }
    const dotted = haloGeometry.getAttribute("instanceDotted") as InstancedBufferAttribute;
    const color = new Color();
    marked.forEach((node, index) => {
      position.set(node.position.x, node.position.y, node.position.z);
      scale.setScalar(node.size * 1.75);
      halos?.setMatrixAt(index, matrix.compose(position, identity, scale));
      halos?.setColorAt(index, color.copy(node.tone === "dimmed" ? colors.dimmed : colors.ink));
      dotted.setX(index, node.nature === "sample" ? 1 : 0);
    });
    if (halos) {
      halos.count = marked.length;
      halos.instanceMatrix.needsUpdate = true;
      if (halos.instanceColor) halos.instanceColor.needsUpdate = true;
      dotted.needsUpdate = true;
    }
  }

  function setGuides(list: readonly StratumGuide[]) {
    if (guides) {
      scene.remove(guides);
      guides.geometry.dispose();
      guides = null;
    }
    if (!list.length) return;
    const segments = 96;
    const points = new Float32Array(list.length * segments * 6);
    let offset = 0;
    for (const guide of list) {
      for (let index = 0; index < segments; index += 1) {
        for (const step of [index, index + 1]) {
          const angle = (step / segments) * Math.PI * 2;
          points[offset] = guide.center.x + Math.cos(angle) * guide.radius;
          points[offset + 1] = guide.height;
          points[offset + 2] = guide.center.z + Math.sin(angle) * guide.radius;
          offset += 3;
        }
      }
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(points, 3));
    guides = new LineSegments(geometry, guideMaterial);
    guides.frustumCulled = false;
    scene.add(guides);
  }

  const api: UniverseRenderer = {
    setScene(model, palette, strata) {
      colors = {
        background: new Color(palette.background),
        ink: new Color(palette.ink),
        hollow: new Color(palette.hollow),
        structural: new Color(palette.structural),
        economic: new Color(palette.economic),
        dimmed: new Color(palette.dimmed),
        accent: new Color(palette.accent),
        guide: new Color(palette.guide),
      };
      renderer.setClearColor(colors.background, 1);
      guideMaterial.color.copy(colors.guide);
      guideMaterial.opacity = 0.9;
      setNodes(model.nodes);
      setEdges(model.edges, model.nodes);
      setHalos(model.nodes);
      setGuides(strata);
    },
    setOrbit(orbit: Orbit) {
      const from = eye(orbit);
      camera.position.set(from.x, from.y, from.z);
      camera.up.set(0, 1, 0);
      camera.lookAt(orbit.target.x, orbit.target.y, orbit.target.z);
      const far = Math.max(2000, orbit.radius * 6);
      if (camera.far !== far) {
        camera.far = far;
        camera.updateProjectionMatrix();
      }
      camera.updateMatrixWorld();
      const facing = shapes.get("target");
      if (facing) placeNodes(facing, "target");
    },
    resize(nextWidth, nextHeight, pixelRatio) {
      width = Math.max(1, nextWidth);
      height = Math.max(1, nextHeight);
      const ratio = Math.min(2, Math.max(1, pixelRatio));
      renderer.setPixelRatio(ratio);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      resolution.set(width * ratio, height * ratio);
      pixelRatioUniform.value = ratio;
    },
    render() {
      renderer.render(scene, camera);
    },
    project(point: Vec3): Projected {
      const vector = new Vector3(point.x, point.y, point.z);
      const depth = vector.distanceTo(camera.position);
      const inView = vector.clone().applyMatrix4(camera.matrixWorldInverse).z < -camera.near;
      vector.project(camera);
      const x = ((vector.x + 1) / 2) * width;
      const y = ((1 - vector.y) / 2) * height;
      const scaleAt = height / (2 * Math.tan(((FOV / 2) * Math.PI) / 180) * Math.max(depth, 1));
      return {
        x,
        y,
        depth,
        visible: inView && x >= 0 && x <= width && y >= 0 && y <= height,
        scale: scaleAt,
      };
    },
    info(): RendererInfo {
      return {
        calls: renderer.info.render.calls,
        triangles: renderer.info.render.triangles,
        geometries: renderer.info.memory.geometries,
        programs: renderer.info.programs?.length ?? 0,
      };
    },
    dispose() {
      canvas.removeEventListener("webglcontextlost", onLost);
      for (const entry of shapes.values()) {
        entry.fill.dispose();
        entry.hull.dispose();
        entry.core?.dispose();
      }
      for (const geometry of geometries.values()) geometry.dispose();
      for (const geometry of hullGeometries.values()) geometry.dispose();
      arrows?.dispose();
      halos?.dispose();
      guides?.geometry.dispose();
      for (const item of disposables) item.dispose();
      scene.clear();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
  return api;
};
