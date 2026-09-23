import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";

function Reader({ id, load }: { id: string; load: () => Promise<string> }) {
  const resource = useApiResource("shared", load);
  return <p data-testid={id}>{resource.status === "success" ? resource.data : resource.status}</p>;
}

describe("useApiResource", () => {
  it("moves from loading to success", async () => {
    const { result } = renderHook(() => useApiResource("value", async () => 42));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toBe(42);
  });

  it("shares one request between every component that asks for the same data", async () => {
    const load = vi.fn(async () => "loaded");
    render(
      <>
        <Reader id="a" load={load} />
        <Reader id="b" load={load} />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("b")).toHaveTextContent("loaded"));
    expect(screen.getByTestId("a")).toHaveTextContent("loaded");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("reports errors and loads again on reload", async () => {
    const load = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("back");
    const { result } = renderHook(() => useApiResource("flaky", load));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toEqual(new Error("offline"));

    act(() => result.current.reload());
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toBe("back");
  });

  it("keeps showing data while refreshing after an invalidation", async () => {
    let version = 0;
    const { result } = renderHook(() => useApiResource("list", async () => ++version));
    await waitFor(() => expect(result.current.data).toBe(1));

    act(() => invalidateResource("list"));
    expect(result.current.status).toBe("success");
    await waitFor(() => expect(result.current.data).toBe(2));
    expect(result.current.isRefreshing).toBe(false);
  });

  it("never shows one key's data under another key", async () => {
    const { result, rerender } = renderHook(
      ({ id }) => useApiResource(`item:${id}`, () => new Promise<string>(() => {})),
      { initialProps: { id: "a" } },
    );
    act(() => setResourceData("item:a", "A"));
    rerender({ id: "a" });
    rerender({ id: "b" });
    expect(result.current.status).toBe("loading");
    expect(result.current.data).toBeUndefined();
  });

  it("uses data stored by a save without refetching", async () => {
    setResourceData("scenario:1", { id: "1" });
    const load = vi.fn(async () => ({ id: "stale" }));
    const { result } = renderHook(() => useApiResource("scenario:1", load));
    expect(result.current.status).toBe("success");
    expect(result.current.data).toEqual({ id: "1" });
    expect(load).not.toHaveBeenCalled();
  });
});
