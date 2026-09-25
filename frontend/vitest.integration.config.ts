import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Runs the app's real API service layer against a live backend (see scripts/smoke_test.sh).
// Requires RUMIN_API_URL, e.g. http://127.0.0.1:8765.
export default defineConfig({
  define: { __RUMIN_VERSION__: JSON.stringify("test") },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["tests/integration/**/*.test.ts"],
    // One file at a time: the files share one live database, and one file's writes must not
    // land between another's store and read-back (a stored intelligence analysis is rightly
    // "stale" once another file executes a scenario for the same company).
    fileParallelism: false,
    testTimeout: 15_000,
  },
});
