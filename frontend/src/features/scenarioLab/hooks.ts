/**
 * The Lab's live data: the preview of the scenario being edited, and an execution
 * followed until it is final.
 *
 * The preview is computed by the backend (``POST /scenarios/preview``) a short moment
 * after the last edit; an older request is cancelled when a newer one starts, and the
 * previous result stays on screen, marked as updating, until the new one arrives.
 *
 * An execution is polled at the interval the server asks for (``poll_after_ms``) and
 * only while it is not final, so what the page shows is always the server's state.
 */
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/apiClient";
import { labApi } from "@/services/api";
import type {
  LabPathway,
  ScenarioExecution,
  ScenarioInput,
  ScenarioPreview,
  ScenarioResults,
} from "@/types/api";
import { isFinal } from "./format";

export const PREVIEW_DELAY_MS = 450;

export type PreviewState =
  | { status: "idle"; data: null; error: null; updating: false }
  | { status: "ready"; data: ScenarioPreview; error: null; updating: boolean }
  | { status: "invalid"; data: ScenarioPreview | null; error: ApiError; updating: boolean }
  | { status: "error"; data: ScenarioPreview | null; error: unknown; updating: boolean };

const IDLE: PreviewState = { status: "idle", data: null, error: null, updating: false };

export function usePreview(input: ScenarioInput | null, delay = PREVIEW_DELAY_MS): PreviewState {
  const [state, setState] = useState<PreviewState>(IDLE);
  const key = input ? JSON.stringify(input) : null;
  const inputRef = useRef(input);
  inputRef.current = input;

  // `key` stands for the input's content: a new object with the same content does not
  // start another request.
  // biome-ignore lint/correctness/useExhaustiveDependencies: key captures the input
  useEffect(() => {
    const current = inputRef.current;
    if (!current) {
      setState(IDLE);
      return;
    }
    const controller = new AbortController();
    setState((previous) =>
      previous.status === "idle" ? previous : ({ ...previous, updating: true } as PreviewState),
    );
    const timer = window.setTimeout(() => {
      labApi.preview(current, { signal: controller.signal }).then(
        (data) => setState({ status: "ready", data, error: null, updating: false }),
        (error: unknown) => {
          if (controller.signal.aborted) return;
          setState((previous) => ({
            status: error instanceof ApiError && error.status === 422 ? "invalid" : "error",
            data: previous.data,
            error: error as ApiError,
            updating: false,
          }));
        },
      );
    }, delay);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, delay]);

  return state;
}

export interface ExecutionState {
  execution: ScenarioExecution | null;
  results: ScenarioResults | null;
  pathway: LabPathway | null;
  error: unknown;
}

/** Follows an execution until it is final, then loads its results and pathway. */
export function useExecution(
  executionId: string | null,
  initial: ScenarioExecution | null = null,
): ExecutionState {
  const [state, setState] = useState<ExecutionState>({
    execution: initial && initial.id === executionId ? initial : null,
    results: null,
    pathway: null,
    error: null,
  });

  useEffect(() => {
    if (!executionId) {
      setState({ execution: null, results: null, pathway: null, error: null });
      return;
    }
    let active = true;
    let timer: number | undefined;
    const controller = new AbortController();
    const options = { signal: controller.signal };

    async function follow() {
      try {
        const execution = await labApi.execution(executionId as string, options);
        if (!active) return;
        setState((previous) => ({ ...previous, execution, error: null }));
        if (!isFinal(execution.status)) {
          timer = window.setTimeout(follow, execution.poll_after_ms ?? 500);
          return;
        }
        if (execution.status === "completed") {
          const [results, pathway] = await Promise.all([
            labApi.results(execution.id, options),
            labApi.pathways(execution.id, options),
          ]);
          if (active) setState({ execution, results, pathway, error: null });
        }
      } catch (error) {
        if (active && !controller.signal.aborted) {
          setState((previous) => ({ ...previous, error }));
        }
      }
    }

    setState((previous) =>
      previous.execution?.id === executionId
        ? previous
        : { execution: null, results: null, pathway: null, error: null },
    );
    void follow();
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [executionId]);

  return state;
}
