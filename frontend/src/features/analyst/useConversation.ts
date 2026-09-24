/**
 * One conversation: its stored turns, and asking a new question.
 *
 * Asking stores the question (creating the conversation first if there is none), then
 * reads the turn again every `poll_after_ms` until it is final — its tool calls appear as
 * the server records them. Nothing is shown that the server has not stored: no typing
 * effect, no invented progress. A conversation opened while one of its questions is still
 * being answered follows that question the same way. Leaving the conversation stops the
 * polling; the answer is still stored when it finishes.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { analystApi } from "@/services/api";
import type { AnalystSession, AnalystTurn } from "@/types/api";

const MIN_POLL_MS = 300;
const MAX_POLL_MS = 3000;
const GIVE_UP_MS = 180_000;

export type ConversationState =
  | { status: "empty" }
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; session: AnalystSession };

export interface Asking {
  question: string;
  turn: AnalystTurn | null; // null until the server has stored it
  error: unknown;
  stalled: boolean; // still not final after GIVE_UP_MS
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

export function isFinal(turn: AnalystTurn): boolean {
  return turn.status === "completed" || turn.status === "failed";
}

export function useConversation(
  sessionId: string | null,
  { onCreated, onSettled }: { onCreated: (id: string) => void; onSettled: () => void },
) {
  const [state, setState] = useState<ConversationState>(
    sessionId ? { status: "loading" } : { status: "empty" },
  );
  const [asking, setAsking] = useState<Asking | null>(null);
  const controller = useRef<AbortController | null>(null);
  const created = useRef<string | null>(null);
  const settled = useRef(onSettled);
  settled.current = onSettled;

  const replaceTurn = useCallback((turn: AnalystTurn) => {
    setState((current) => {
      if (current.status !== "ready" || current.session.id !== turn.session_id) return current;
      const turns = current.session.turns.filter((item) => item.id !== turn.id);
      turns.push(turn);
      turns.sort((a, b) => a.position - b.position);
      return {
        status: "ready",
        session: {
          ...current.session,
          turns,
          turn_count: Math.max(current.session.turn_count, turn.position),
        },
      };
    });
  }, []);

  /** Read a stored turn again until it is final, showing each read. */
  const follow = useCallback(
    async (first: AnalystTurn, signal: AbortSignal) => {
      let turn = first;
      const question = turn.question;
      setAsking({ question, turn, error: null, stalled: false });
      try {
        const began = Date.now();
        while (!isFinal(turn)) {
          if (Date.now() - began > GIVE_UP_MS) {
            setAsking({ question, turn, error: null, stalled: true });
            return;
          }
          const delay = Math.min(MAX_POLL_MS, Math.max(MIN_POLL_MS, turn.poll_after_ms ?? 500));
          await wait(delay, signal);
          turn = await analystApi.turn(turn.session_id, turn.id, { signal });
          setAsking({ question, turn, error: null, stalled: false });
        }
        replaceTurn(turn);
        setAsking(null);
        settled.current();
      } catch (error) {
        if (!signal.aborted) setAsking({ question, turn, error, stalled: false });
      }
    },
    [replaceTurn],
  );

  const start = useCallback(() => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    return next.signal;
  }, []);

  const load = useCallback(
    async (id: string, signal: AbortSignal) => {
      try {
        const session = await analystApi.session(id, { signal });
        setState({ status: "ready", session });
        const pending = session.turns.find((turn) => !isFinal(turn));
        if (pending) void follow(pending, signal);
      } catch (error) {
        if (!signal.aborted) setState({ status: "error", error });
      }
    },
    [follow],
  );

  useEffect(() => {
    // A conversation this hook just created is already on screen: no reload.
    if (sessionId && sessionId === created.current) {
      created.current = null;
      return;
    }
    setAsking(null);
    if (!sessionId) {
      controller.current?.abort();
      setState({ status: "empty" });
      return;
    }
    const signal = start();
    setState({ status: "loading" });
    void load(sessionId, signal);
  }, [sessionId, load, start]);

  useEffect(() => () => controller.current?.abort(), []);

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text) return;
      const signal = start();
      setAsking({ question: text, turn: null, error: null, stalled: false });
      try {
        let session: AnalystSession;
        if (state.status === "ready") {
          session = state.session;
        } else {
          session = await analystApi.create(null, { signal });
          created.current = session.id;
          setState({ status: "ready", session });
          onCreated(session.id);
        }
        const turn = await analystApi.ask(session.id, text, { signal });
        await follow(turn, signal);
      } catch (error) {
        if (!signal.aborted) setAsking({ question: text, turn: null, error, stalled: false });
      }
    },
    [state, onCreated, follow, start],
  );

  /** After an error: read the stored question again, or ask it again if it was not stored. */
  const retry = useCallback(() => {
    if (!asking) return;
    if (asking.turn) void follow(asking.turn, start());
    else void ask(asking.question);
  }, [asking, follow, ask, start]);

  const dismiss = useCallback(() => setAsking(null), []);

  const reload = useCallback(() => {
    if (!sessionId) return;
    const signal = start();
    setState({ status: "loading" });
    void load(sessionId, signal);
  }, [sessionId, load, start]);

  const rename = useCallback((title: string) => {
    setState((current) =>
      current.status === "ready"
        ? { status: "ready", session: { ...current.session, title } }
        : current,
    );
  }, []);

  return { state, asking, ask, retry, dismiss, reload, rename };
}
