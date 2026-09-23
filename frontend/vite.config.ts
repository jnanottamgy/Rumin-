/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
) as { version: string };

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
      // Same-origin API calls in development: no CORS, no hard-coded backend URL.
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
        "/health": { target: apiTarget, changeOrigin: true },
        "/docs": { target: apiTarget, changeOrigin: true },
        "/openapi.json": { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      target: "es2022",
      sourcemap: true,
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.ts"],
      include: ["tests/**/*.test.{ts,tsx}"],
      exclude: ["tests/integration/**"],
      restoreMocks: true,
      css: false,
    },
  };
});
