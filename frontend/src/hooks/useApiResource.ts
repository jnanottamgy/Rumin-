/**
 * Loads server data with a small shared cache.
 *
 * - Components that ask for the same `key` share one request (no duplicate fetches,
 *   including React StrictMode's double effects in development).
 * - Loaded data is kept until `reload()` or `invalidateResource(key)` is called, so
 *   navigating back to a page renders instantly.
 * - During a reload the previous data stays on screen (`isRefreshing`) instead of
 *   flashing a loading state. Data is never shown under a different key.
 *
 * Phase 1 needs nothing more. If caching rules grow (background refresh, pagination,
 * optimistic updates), replace this with a dedicated library behind the same interface.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type ResourceState<T> =
  | { status: "loading"; data: undefined; error: undefined; isRefreshing: false }
  | { status: "success"; data: T; error: undefined; isRefreshing: boolean }
  | { status: "error"; data: undefined; error: unknown; isRefreshing: false };

export type Resource<T> = ResourceState<T> & { reload: () => void };

interface CacheEntry {
  hasData: boolean;
  data?: unknown;
  promise?: Promise<unknown>;
}

const cache = new Map<string, CacheEntry>();
const subscribers = new Map<string, Set<() => void>>();

function fetchShared<T>(key: string, load: () => Promise<T>): Promise<T> {
  const entry = cache.get(key);
  if (entry?.promise) return entry.promise as Promise<T>;
  if (entry?.hasData) return Promise.resolve(entry.data as T);

  const promise = load().then(
    (data) => {
      cache.set(key, { hasData: true, data });
      return data;
    },
    (error: unknown) => {
      cache.delete(key);
      throw error;
    },
  );
  cache.set(key, { hasData: false, promise });
  return promise;
}

function subscribe(key: string, listener: () => void): () => void {
  let listeners = subscribers.get(key);
  if (!listeners) {
    listeners = new Set();
    subscribers.set(key, listeners);
  }
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Drop cached data for `key` and make every mounted consumer refetch it. */
export function invalidateResource(key: string): void {
  cache.delete(key);
  for (const listener of subscribers.get(key) ?? []) listener();
}

/** Store data fetched elsewhere (e.g. the response of a save) so readers skip a refetch. */
export function setResourceData<T>(key: string, data: T): void {
  cache.set(key, { hasData: true, data });
}

/** Test helper: forget everything. */
export function clearResourceCache(): void {
  cache.clear();
  subscribers.clear();
}

const LOADING: ResourceState<never> = {
  status: "loading",
  data: undefined,
  error: undefined,
  isRefreshing: false,
};

function initialState<T>(key: string): ResourceState<T> {
  const entry = cache.get(key);
  return entry?.hasData
    ? { status: "success", data: entry.data as T, error: undefined, isRefreshing: false }
    : LOADING;
}

export function useApiResource<T>(key: string, load: () => Promise<T>): Resource<T> {
  const [tagged, setTagged] = useState(() => ({ key, state: initialState<T>(key) }));
  const [generation, setGeneration] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  // `generation` has no use inside the effect: bumping it is how a refetch is requested.
  // biome-ignore lint/correctness/useExhaustiveDependencies: generation triggers refetch
  useEffect(() => {
    let active = true;
    setTagged((previous) => {
      const cached = initialState<T>(key);
      if (cached.status === "success") return { key, state: cached };
      if (previous.key === key && previous.state.status === "success") {
        return { key, state: { ...previous.state, isRefreshing: true } };
      }
      return { key, state: LOADING };
    });

    fetchShared(key, () => loadRef.current()).then(
      (data) => {
        if (!active) return;
        setTagged({
          key,
          state: { status: "success", data, error: undefined, isRefreshing: false },
        });
      },
      (error: unknown) => {
        if (!active) return;
        setTagged({
          key,
          state: { status: "error", data: undefined, error, isRefreshing: false },
        });
      },
    );
    const unsubscribe = subscribe(key, () => setGeneration((value) => value + 1));
    return () => {
      active = false;
      unsubscribe();
    };
  }, [key, generation]);

  const reload = useCallback(() => {
    cache.delete(key);
    setGeneration((value) => value + 1);
  }, [key]);

  // Never expose state that belongs to a previous key.
  const state = tagged.key === key ? tagged.state : initialState<T>(key);
  return { ...state, reload };
}
