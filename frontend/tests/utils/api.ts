/**
 * A fake RUMIN API behind `fetch`. Routes are keyed "METHOD /path" (or just "/path" for
 * GET); the query string is ignored. Every request is recorded so tests can assert
 * exactly what the app sent. Unknown routes answer 404 with the standard error envelope.
 */
import { vi } from "vitest";
import type { ErrorDetail } from "@/types/api";
import { networkFixture, scenarioPageFixture, systemFixture, variablesFixture } from "../fixtures";
import { labFixtures } from "../fixtures/lab";

export interface MockReply {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export interface RecordedRequest {
  method: string;
  path: string;
  query: string;
  body: unknown;
}

export type Route = MockReply | ((request: RecordedRequest) => MockReply | Promise<MockReply>);

export const REQUEST_ID = "req-test-0001";

export function errorReply(
  status: number,
  code: string,
  message: string,
  details: ErrorDetail[] = [],
): MockReply {
  return { status, body: { error: { code, message, details, request_id: REQUEST_ID } } };
}

/** The happy path: every read endpoint the pages use, answering with the fixtures. */
export function defaultRoutes(): Record<string, Route> {
  return {
    "/health": { body: { status: "ok", service: "rumin-api", version: "0.1.0" } },
    "/health/ready": {
      body: {
        status: "ready",
        checks: { database: "ok", migrations: "up_to_date", dataset: "loaded" },
      },
    },
    "/api/v1/network": { body: networkFixture() },
    "/api/v1/variables": { body: variablesFixture() },
    "/api/v1/system": { body: systemFixture() },
    "/api/v1/scenarios": { body: scenarioPageFixture([]) },
    "/api/v1/scenario-templates": { body: labFixtures.templates() },
  };
}

export function mockApi(overrides: Record<string, Route> = {}) {
  const routes: Record<string, Route> = { ...defaultRoutes(), ...overrides };
  const requests: RecordedRequest[] = [];

  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(
        input instanceof Request ? input.url : String(input),
        "http://rumin.test",
      );
      const method = (init?.method ?? "GET").toUpperCase();
      const request: RecordedRequest = {
        method,
        path: url.pathname,
        query: url.search,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      };
      requests.push(request);

      const route =
        routes[`${method} ${url.pathname}`] ??
        (method === "GET" ? routes[url.pathname] : undefined);
      const reply =
        route === undefined
          ? errorReply(404, "not_found", `No test route for ${method} ${url.pathname}.`)
          : typeof route === "function"
            ? await route(request)
            : route;

      const status = reply.status ?? 200;
      const hasBody = reply.body !== undefined && status !== 204;
      return new Response(hasBody ? JSON.stringify(reply.body) : null, {
        status,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": REQUEST_ID,
          ...reply.headers,
        },
      });
    });

  return {
    fetchMock,
    requests,
    /** Replace or add a route after rendering (e.g. the backend comes back up). */
    setRoute: (key: string, route: Route) => {
      routes[key] = route;
    },
    /** Requests other than GET: what the app tried to change. */
    writes: () => requests.filter((request) => request.method !== "GET"),
  };
}

/** A fetch that fails like an unreachable server does. */
export const unreachable: Route = () => {
  throw new TypeError("Failed to fetch");
};
