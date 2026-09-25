/**
 * The universe's camera, as an orbit around a target: pure maths, no Three.js.
 *
 * The camera looks at `target` from `radius` away, at an azimuth `theta` around the vertical
 * axis and a polar angle `phi` from the vertical (small `phi`: looking down on the strata;
 * `phi` near π/2: looking at them edge-on). The polar angle is kept away from the poles so
 * "up" on the screen is always up in the universe.
 */
import type { Vec3 } from "./layout3d";

export interface Orbit {
  target: Vec3;
  radius: number;
  theta: number;
  phi: number;
}

/** Vertical field of view, degrees. */
export const FOV = 40;
export const MIN_PHI = 0.2;
export const MAX_PHI = Math.PI - 0.2;
export const DEFAULT_THETA = Math.PI / 5;
/** Slightly above the middle stratum, so the layers read as layers. */
export const DEFAULT_PHI = 1.16;
export const MIN_RADIUS = 30;
export const MAX_RADIUS = 6000;

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

export function eye(orbit: Orbit): Vec3 {
  const { target, radius, theta, phi } = orbit;
  return {
    x: target.x + radius * Math.sin(phi) * Math.sin(theta),
    y: target.y + radius * Math.cos(phi),
    z: target.z + radius * Math.sin(phi) * Math.cos(theta),
  };
}

export function rotate(orbit: Orbit, dTheta: number, dPhi: number): Orbit {
  return {
    ...orbit,
    theta: orbit.theta + dTheta,
    phi: clamp(orbit.phi + dPhi, MIN_PHI, MAX_PHI),
  };
}

export function zoom(orbit: Orbit, factor: number): Orbit {
  return { ...orbit, radius: clamp(orbit.radius * factor, MIN_RADIUS, MAX_RADIUS) };
}

function normalize(vector: Vec3): Vec3 {
  const length = Math.hypot(vector.x, vector.y, vector.z) || 1;
  return { x: vector.x / length, y: vector.y / length, z: vector.z / length };
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
}

/** The camera's right and up directions in the universe. */
export function basis(orbit: Orbit): { right: Vec3; up: Vec3; forward: Vec3 } {
  const from = eye(orbit);
  const forward = normalize({
    x: orbit.target.x - from.x,
    y: orbit.target.y - from.y,
    z: orbit.target.z - from.z,
  });
  const right = normalize(cross(forward, { x: 0, y: 1, z: 0 }));
  const up = cross(right, forward);
  return { right, up, forward };
}

/**
 * Move the target across the screen: `dx` and `dy` are fractions of the view's height (a
 * drag of the full height moves the target by what the view shows at the target's depth).
 */
export function pan(orbit: Orbit, dx: number, dy: number): Orbit {
  const { right, up } = basis(orbit);
  const span = 2 * orbit.radius * Math.tan(((FOV / 2) * Math.PI) / 180);
  return {
    ...orbit,
    target: {
      x: orbit.target.x + (-dx * right.x + dy * up.x) * span,
      y: orbit.target.y + (-dx * right.y + dy * up.y) * span,
      z: orbit.target.z + (-dx * right.z + dy * up.z) * span,
    },
  };
}

/** The distance at which a sphere of `radius` fits the view at this aspect ratio. */
export function fitDistance(radius: number, aspect: number): number {
  const vertical = (FOV * Math.PI) / 180;
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * Math.max(aspect, 0.1));
  const narrowest = Math.min(vertical, horizontal);
  return clamp((radius / Math.sin(narrowest / 2)) * 1.05, MIN_RADIUS, MAX_RADIUS);
}

/**
 * A view that fits every point, from the given angles or the default ones: it looks at the
 * middle of the points' bounding box, from the least distance at which each point is inside
 * the view (with a margin, for the names written beside the nodes).
 */
export function frameAll(
  points: readonly Vec3[],
  aspect: number,
  angles: Pick<Orbit, "theta" | "phi"> = { theta: DEFAULT_THETA, phi: DEFAULT_PHI },
  margin = 1.12,
): Orbit {
  if (!points.length) return { target: { x: 0, y: 0, z: 0 }, radius: MIN_RADIUS * 4, ...angles };
  const low = { x: Infinity, y: Infinity, z: Infinity };
  const high = { x: -Infinity, y: -Infinity, z: -Infinity };
  for (const point of points) {
    low.x = Math.min(low.x, point.x);
    low.y = Math.min(low.y, point.y);
    low.z = Math.min(low.z, point.z);
    high.x = Math.max(high.x, point.x);
    high.y = Math.max(high.y, point.y);
    high.z = Math.max(high.z, point.z);
  }
  const target = { x: (low.x + high.x) / 2, y: (low.y + high.y) / 2, z: (low.z + high.z) / 2 };
  const { right, up, forward } = basis({ target, radius: 1, ...angles });
  const tanV = Math.tan((FOV * Math.PI) / 360) / margin;
  const tanH = tanV * Math.max(aspect, 0.1);
  let distance = 0;
  for (const point of points) {
    const d = { x: point.x - target.x, y: point.y - target.y, z: point.z - target.z };
    const across = d.x * right.x + d.y * right.y + d.z * right.z;
    const upward = d.x * up.x + d.y * up.y + d.z * up.z;
    // Beyond the target (positive) or in front of it (negative), along the line of sight.
    const beyond = d.x * forward.x + d.y * forward.y + d.z * forward.z;
    distance = Math.max(
      distance,
      Math.abs(across) / tanH - beyond,
      Math.abs(upward) / tanV - beyond,
    );
  }
  return { target, radius: clamp(distance, MIN_RADIUS, MAX_RADIUS), ...angles };
}

/** A view of a sphere (centre and radius), from the given angles or the default ones. */
export function framing(
  center: Vec3,
  radius: number,
  aspect: number,
  angles: Pick<Orbit, "theta" | "phi"> = { theta: DEFAULT_THETA, phi: DEFAULT_PHI },
): Orbit {
  return { target: { ...center }, radius: fitDistance(radius, aspect), ...angles };
}

export function easeOut(t: number): number {
  const clamped = clamp(t, 0, 1);
  return 1 - (1 - clamped) ** 3;
}

/** Between two views at `t` (0–1): the target moves straight, the distance geometrically and
 * the azimuth the short way round. */
export function interpolate(from: Orbit, to: Orbit, t: number): Orbit {
  const k = clamp(t, 0, 1);
  const turn = Math.atan2(Math.sin(to.theta - from.theta), Math.cos(to.theta - from.theta));
  return {
    target: {
      x: from.target.x + (to.target.x - from.target.x) * k,
      y: from.target.y + (to.target.y - from.target.y) * k,
      z: from.target.z + (to.target.z - from.target.z) * k,
    },
    radius: from.radius * (to.radius / from.radius) ** k,
    theta: from.theta + turn * k,
    phi: from.phi + (to.phi - from.phi) * k,
  };
}
