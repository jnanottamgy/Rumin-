import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type AuthProblem,
  apiRequest,
  describeError,
  onAuthProblem,
} from "@/lib/apiClient";
import { errorReply, mockApi, REQUEST_ID, unreachable } from "../utils/api";

describe("apiRequest", () => {
  it("returns the parsed JSON body of a successful response", async () => {
    mockApi({ "/api/v1/things": { body: { items: [1, 2] } } });
    await expect(apiRequest("/api/v1/things")).resolves.toEqual({ items: [1, 2] });
  });

  it("sends JSON bodies with the right headers and method", async () => {
    const api = mockApi({ "POST /api/v1/things": { status: 201, body: { id: "a" } } });
    await apiRequest("/api/v1/things", { method: "POST", body: { name: "A" } });

    expect(api.requests).toEqual([
      expect.objectContaining({ method: "POST", path: "/api/v1/things", body: { name: "A" } }),
    ]);
    const init = api.fetchMock.mock.calls[0]?.[1];
    expect(init?.headers).toMatchObject({
      Accept: "application/json",
      "Content-Type": "application/json",
    });
  });

  it("turns the standard error envelope into a typed ApiError", async () => {
    mockApi({
      "/api/v1/things": errorReply(422, "validation_error", "The scenario inputs are invalid.", [
        {
          location: "body",
          field: "shocks[0].value",
          message: "The change must be greater than -100 %.",
          type: "invalid_change",
        },
      ]),
    });

    const error = await apiRequest("/api/v1/things").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: "http",
      status: 422,
      code: "validation_error",
      message: "The scenario inputs are invalid.",
      requestId: REQUEST_ID,
      details: [expect.objectContaining({ field: "shocks[0].value" })],
    });
  });

  it("reports a non-envelope error by its HTTP status", async () => {
    mockApi({ "/api/v1/things": { status: 502, body: { detail: "Bad gateway" } } });
    await expect(apiRequest("/api/v1/things")).rejects.toMatchObject({
      kind: "http",
      status: 502,
      code: null,
      message: "The API responded with HTTP 502.",
    });
  });

  it("rejects a body that is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>proxy error</html>", { status: 200 }),
    );
    await expect(apiRequest("/api/v1/things")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("explains an unreachable backend", async () => {
    mockApi({ "/api/v1/things": unreachable });
    await expect(apiRequest("/api/v1/things")).rejects.toMatchObject({
      kind: "network",
      message: expect.stringContaining("Could not reach the RUMIN API"),
    });
  });

  it("gives up after the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted.", "AbortError")),
          );
        }),
    );
    await expect(apiRequest("/api/v1/slow", { timeoutMs: 20 })).rejects.toMatchObject({
      kind: "timeout",
    });
  });

  it("passes a caller's cancellation through instead of reporting an error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted.", "AbortError")),
          );
        }),
    );
    const controller = new AbortController();
    const request = apiRequest("/api/v1/slow", { signal: controller.signal });
    controller.abort();

    const error = await request.catch((caught: unknown) => caught);
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("returns the body of an accepted non-2xx status (readiness answers 503)", async () => {
    mockApi({ "/health/ready": { status: 503, body: { status: "not_ready" } } });
    await expect(apiRequest("/health/ready", { acceptStatuses: [503] })).resolves.toEqual({
      status: "not_ready",
    });
  });

  it("returns undefined for 204 No Content", async () => {
    mockApi({ "DELETE /api/v1/things/a": { status: 204 } });
    await expect(apiRequest("/api/v1/things/a", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("prefixes the configured base URL", async () => {
    const api = mockApi();
    await apiRequest("/health", { baseUrl: "http://api.example.test" });
    expect(String(api.fetchMock.mock.calls[0]?.[0])).toBe("http://api.example.test/health");
  });
});

describe("describeError", () => {
  it("prefers the API's own message and never shows a blank", () => {
    expect(describeError(new ApiError("http", "Scenario not found."))).toBe("Scenario not found.");
    expect(describeError(new Error("Boom"))).toBe("Boom");
    expect(describeError("weird")).toBe("Something went wrong.");
  });
});

describe("sessions (Phase 10)", () => {
  it("sends extra headers, such as the integration suite's session cookie", async () => {
    const api = mockApi({ "/api/v1/things": { body: {} } });
    await apiRequest("/api/v1/things", { headers: { Cookie: "rumin_session=test" } });
    expect(api.fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      Accept: "application/json",
      Cookie: "rumin_session=test",
    });
  });

  it("tells the session layer when a request finds the session ended or a password to change", async () => {
    mockApi({
      "/api/v1/ended": errorReply(401, "unauthorized", "Your session has ended. Sign in again."),
      "/api/v1/password-first": errorReply(
        403,
        "password_change_required",
        "Choose a new password before continuing.",
      ),
      "/api/v1/forbidden": errorReply(403, "forbidden", "Your role does not allow this."),
    });
    const heard: AuthProblem[] = [];
    const stop = onAuthProblem((problem) => heard.push(problem));

    await apiRequest("/api/v1/ended").catch(() => undefined);
    await apiRequest("/api/v1/password-first").catch(() => undefined);
    await apiRequest("/api/v1/forbidden").catch(() => undefined);
    await apiRequest("/api/v1/ended", { quietAuth: true }).catch(() => undefined);
    stop();
    await apiRequest("/api/v1/ended").catch(() => undefined);

    expect(heard).toEqual(["session_ended", "password_change_required"]);
  });
});
