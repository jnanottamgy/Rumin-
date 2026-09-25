/**
 * Whether this browser can draw the 3D universe at all: Three.js needs WebGL 2. Checked
 * without loading Three.js, so a browser without it never downloads the renderer.
 */
export function webglAvailable(): boolean {
  if (typeof window === "undefined" || typeof window.WebGL2RenderingContext === "undefined") {
    return false;
  }
  try {
    const probe = document.createElement("canvas");
    const context = probe.getContext("webgl2");
    context?.getExtension("WEBGL_lose_context")?.loseContext();
    return Boolean(context);
  } catch {
    return false;
  }
}
