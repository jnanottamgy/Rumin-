/**
 * AI Analyst fixtures, captured from a running backend by
 * `backend/scripts/capture_analyst_fixtures.py` (not hand-written): the sample network built
 * into a knowledge graph; SYNTHETIC exchange-rate and inflation histories stored through the
 * ingestion pipeline from a scripted response (test values, not World Bank data); and the
 * backend tests' REFERENCE scenario on the fictional Aerisca Airways with HYPOTHETICAL
 * figures, executed. Every answer is RUMIN's grounded composer's: no language model.
 *
 * `turn-queued`, `turn-running` and `turn-completed` are one question read three times while
 * it was answered; `session` is that conversation with six more questions; `turn-failed` is
 * a question whose orchestrator was made to crash, recorded by the service as it records any
 * failure.
 */
import type {
  AnalystCapabilities,
  AnalystSession,
  AnalystSessionPage,
  AnalystTurn,
} from "@/types/api";
import capabilities from "./analyst/capabilities.json";
import capabilitiesModelNotReady from "./analyst/capabilities-model-not-ready.json";
import session from "./analyst/session.json";
import sessionFailed from "./analyst/session-failed.json";
import sessionNew from "./analyst/session-new.json";
import sessionRunning from "./analyst/session-running.json";
import sessions from "./analyst/sessions.json";
import sessionsEmpty from "./analyst/sessions-empty.json";
import turnCompleted from "./analyst/turn-completed.json";
import turnFailed from "./analyst/turn-failed.json";
import turnQueued from "./analyst/turn-queued.json";
import turnRunning from "./analyst/turn-running.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const analystFixtures = {
  capabilities: () => copy<AnalystCapabilities>(capabilities),
  capabilitiesModelNotReady: () => copy<AnalystCapabilities>(capabilitiesModelNotReady),
  sessions: () => copy<AnalystSessionPage>(sessions),
  sessionsEmpty: () => copy<AnalystSessionPage>(sessionsEmpty),
  sessionNew: () => copy<AnalystSession>(sessionNew),
  session: () => copy<AnalystSession>(session),
  sessionRunning: () => copy<AnalystSession>(sessionRunning),
  sessionFailed: () => copy<AnalystSession>(sessionFailed),
  turnQueued: () => copy<AnalystTurn>(turnQueued),
  turnRunning: () => copy<AnalystTurn>(turnRunning),
  turnCompleted: () => copy<AnalystTurn>(turnCompleted),
  turnFailed: () => copy<AnalystTurn>(turnFailed),
};

/** The conversation of `session.json`, and the one of `session-failed.json`. */
export const SESSION_ID = session.id;
export const FAILED_SESSION_ID = sessionFailed.id;
/** The first question of `session.json`, the one read queued, running and completed. */
export const FIRST_TURN_ID = turnQueued.id;

/** A turn of `session.json` by its position (1–7). */
export function sessionTurn(position: number): AnalystTurn {
  const turn = analystFixtures.session().turns.find((item) => item.position === position);
  if (!turn) throw new Error(`No turn ${position} in the session fixture.`);
  return turn;
}
