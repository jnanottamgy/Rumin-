/// <reference types="vite/client" />

/** Frontend version, injected at build time from package.json (see vite.config.ts). */
declare const __RUMIN_VERSION__: string;

interface ImportMetaEnv {
  /** Base URL of the RUMIN API as seen by the browser. Empty = same origin. PUBLIC. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
