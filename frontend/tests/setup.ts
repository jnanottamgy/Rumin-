import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { clearResourceCache } from "@/hooks/useApiResource";
import { installBrowserStubs, resetBrowserStubs } from "./utils/browser";

installBrowserStubs();

afterEach(() => {
  cleanup();
  // Every test starts without cached API data, preferences or document state.
  clearResourceCache();
  resetBrowserStubs();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.motion;
});
