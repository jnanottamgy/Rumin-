/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
) as { version: string };

// The production web server's Content-Security-Policy, read from its nginx snippet so the
// preview server (and the launch suite that runs against it) enforces exactly the same one.
function productionCsp(): string {
  const snippet = readFileSync(
    new URL("./nginx/snippets/security-headers.conf", import.meta.url),
    "utf-8",
  );
  const policy = snippet.match(/add_header Content-Security-Policy "([^"]+)"/)?.[1];
  if (!policy)
    throw new Error("No Content-Security-Policy in nginx/snippets/security-headers.conf");
  return policy;
}

// The API trusts X-Forwarded-For from this machine (uvicorn's default), where this proxy runs:
// a header the browser sent must not reach it, or a client could choose the address its
// sign-in attempts are counted against. (Production: nginx overwrites the header.)
function proxied(target: string): ProxyOptions {
  return {
    target,
    configure: (proxy) => {
      proxy.on("proxyReq", (request) => {
        request.removeHeader("x-forwarded-for");
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  // One .env file at the repository root serves the backend and the frontend.
  // Only VITE_* variables reach browser code; RUMIN_API_PROXY_TARGET stays in Node.
  const env = loadEnv(mode, repoRoot, "");
  const apiTarget = env.RUMIN_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    envDir: repoRoot,
    plugins: [react()],
    define: { __RUMIN_VERSION__: JSON.stringify(version) },
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      // Same-origin API calls in development: no CORS, no hard-coded backend URL. The
      // browser's own Host is passed on (no `changeOrigin`), as a production proxy must:
      // the API refuses a change whose Origin is not its own host (Phase 10, CSRF), and a
      // rewritten Host would make every sign-in from the dev or preview server look foreign.
      proxy: {
        "/api": proxied(apiTarget),
        "/health": proxied(apiTarget),
        "/docs": proxied(apiTarget),
        "/openapi.json": proxied(apiTarget),
      },
    },
    preview: {
      headers: { "Content-Security-Policy": productionCsp() },
    },
    build: {
      target: "es2022",
      // Fonts are always files, never inlined as data: URIs (Vite inlines assets under 4 kB):
      // the production Content-Security-Policy allows fonts from RUMIN's own origin only.
      assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf)$/i.test(file) ? false : undefined),
      // Maps are written for decoding a reported stack trace, but the bundles do not point
      // to them and the production web server refuses to serve them (Phase 10): the
      // readable source is not published.
      sourcemap: "hidden",
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.ts"],
      include: ["tests/**/*.test.{ts,tsx}"],
      exclude: ["tests/integration/**"],
      restoreMocks: true,
      css: false,
      // Page tests walk through several renders of a full page; on a slow runner that can
      // take more than the default 5 s without anything being wrong.
      testTimeout: 15_000,
    },
  };
});
