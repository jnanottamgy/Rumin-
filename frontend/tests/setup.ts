import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";
import { clearResourceCache } from "@/hooks/useApiResource";
import { installBrowserStubs, resetBrowserStubs } from "./utils/browser";

installBrowserStubs();

// A full page renders in jsdom in a few hundred milliseconds, and in more than the default
// second on a busy CI runner. A longer wait costs nothing when the page renders and still
// fails when it never does.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  // Every test starts without cached API data, preferences or document state.
  clearResourceCache();
  resetBrowserStubs();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.motion;
});
