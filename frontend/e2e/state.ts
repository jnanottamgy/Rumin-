/** What the global setup prepared, shared with the specs. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const STATE_DIR = fileURLToPath(new URL("../e2e-results/state/", import.meta.url));
export const ADMIN_STATE = `${STATE_DIR}admin.json`;
export const VIEWER_STATE = `${STATE_DIR}viewer.json`;
export const IDS_FILE = `${STATE_DIR}ids.json`;

export interface PreparedIds {
  scenario: string;
  execution: string;
  run: string;
  analysis: string;
  session: string;
  series: string | null;
  instrument: string | null;
  job: string | null;
  /** A viewer still holding the temporary password an administrator gave them. */
  newcomer: { email: string; password: string };
  admin: { email: string; name: string };
}

export function prepared(): PreparedIds {
  return JSON.parse(readFileSync(IDS_FILE, "utf8")) as PreparedIds;
}

export function credential(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} (scripts/e2e.sh sets it).`);
  return value;
}
