/**
 * Minimal, typed HTTP client for the RUMIN API.
 *
 * Every failure becomes an `ApiError` with a `kind`, so screens can show an honest,
 * specific message: the backend is unreachable, it timed out, or it answered with the
 * standard error envelope (validation problems, not found, …).
 */
import type { ErrorDetail } from "@/types/api";

export type ApiErrorKind = "http" | "network" | "timeout" | "invalid_response";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;

  constructor(
    kind: ApiErrorKind,
    message: string,
    options: {
      status?: number | null;
      code?: string | null;
      details?: ErrorDetail[];
      requestId?: string | null;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status ?? null;
    this.code = options.code ?? null;
    this.details = options.details ?? [];
    this.requestId = options.requestId ?? null;
  }
}

export const DEFAULT_TIMEOUT_MS = 15_000;

/** Base URL of the API. Empty means same-origin (the Vite dev server proxies /api). */
export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return typeof configured === "string" ? configured.replace(/\/+$/, "") : "";
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Non-2xx statuses whose JSON body should be returned instead of thrown (e.g. 503 readiness). */
  acceptStatuses?: number[];
  baseUrl?: string;
}

function isErrorEnvelope(value: unknown): value is {
  error: { code: string; message: string; details?: ErrorDetail[]; request_id?: string | null };
} {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("invalid_response", "The API returned a response that is not valid JSON.", {
      status: response.status,
      requestId: response.headers.get("X-Request-ID"),
    });
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS, acceptStatuses = [] } = options;
  const url = `${options.baseUrl ?? apiBaseUrl()}${path}`;
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (timeout.aborted) {
      throw new ApiError("timeout", "The RUMIN API did not respond in time.");
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error; // Cancelled by the caller: not an application error.
    }
    throw new ApiError(
      "network",
      "Could not reach the RUMIN API. Check that the backend is running.",
    );
  }

  if (response.status === 204) return undefined as T;

  const payload = await readJson(response);
  if (response.ok || acceptStatuses.includes(response.status)) {
    return payload as T;
  }

  const requestId = response.headers.get("X-Request-ID");
  if (isErrorEnvelope(payload)) {
    throw new ApiError("http", payload.error.message, {
      status: response.status,
      code: payload.error.code,
      details: payload.error.details ?? [],
      requestId: payload.error.request_id ?? requestId,
    });
  }
  throw new ApiError("http", `The API responded with HTTP ${response.status}.`, {
    status: response.status,
    requestId,
  });
}

/** A short, user-facing explanation for any error thrown by the data layer. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
