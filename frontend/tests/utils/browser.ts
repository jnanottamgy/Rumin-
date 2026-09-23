/**
 * Browser APIs that jsdom does not implement, replaced with controllable stand-ins.
 * `tests/setup.ts` installs them for every test and resets them afterwards.
 */

/** Media queries that match in the current test, e.g. "(max-width: 40rem)" for a phone. */
export const matchingMediaQueries = new Set<string>();

/** The size every observed element reports (the network canvas frames itself to it). */
export const observedSize = { width: 960, height: 640 };

class ResizeObserverStub implements ResizeObserver {
  readonly #callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.#callback = callback;
  }

  observe(target: Element): void {
    const { width, height } = observedSize;
    const contentRect = {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      width,
      height,
      right: width,
      bottom: height,
      toJSON: () => ({}),
    } satisfies DOMRectReadOnly;
    const entry = {
      target,
      contentRect,
      borderBoxSize: [],
      contentBoxSize: [],
      devicePixelContentBoxSize: [],
    } satisfies ResizeObserverEntry;
    this.#callback([entry], this);
  }

  unobserve(): void {}

  disconnect(): void {}
}

function matchMedia(query: string): MediaQueryList {
  return {
    matches: matchingMediaQueries.has(query),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  };
}

export function installBrowserStubs(): void {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: matchMedia });
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true,
    value: ResizeObserverStub,
  });
}

export function resetBrowserStubs(): void {
  matchingMediaQueries.clear();
  observedSize.width = 960;
  observedSize.height = 640;
}
