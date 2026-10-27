import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/http";
import { usePolling } from "./usePolling";
import { useQuery } from "./useQuery";

afterEach(() => vi.useRealTimers());

describe("useQuery", () => {
  it("loads, reports errors and refetches", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("down", 502, "backend_unavailable"))
      .mockResolvedValueOnce("ok");
    const { result } = renderHook(() => useQuery(fetcher, "k"));
    await waitFor(() => expect(result.current.error?.code).toBe("backend_unavailable"));
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.data).toBe("ok"));
    expect(result.current.error).toBeNull();
  });

  it("does nothing while disabled", () => {
    const fetcher = vi.fn();
    const { result } = renderHook(() => useQuery(fetcher, "k", false));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});

describe("usePolling", () => {
  it("polls until done, waiting between calls", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetcher = vi.fn().mockResolvedValueOnce({ s: "running" }).mockResolvedValueOnce({ s: "running" }).mockResolvedValue({ s: "done" });
    const { result } = renderHook(() => usePolling(fetcher, "k", 3000, (d: { s: string }) => d.s === "done"));
    await waitFor(() => expect(result.current.data).toEqual({ s: "running" }));
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(3000));
    await act(() => vi.advanceTimersByTimeAsync(3000));
    await waitFor(() => expect(result.current.data).toEqual({ s: "done" }));
    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(fetcher).toHaveBeenCalledTimes(3); // stopped once done
  });

  it("stops on an error, keeps the last data, and retries on request", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ s: "running" })
      .mockRejectedValueOnce(new ApiError("down", 502, "backend_unavailable"))
      .mockResolvedValue({ s: "done" });
    const { result, unmount } = renderHook(() => usePolling(fetcher, "k", 1000, (d: { s: string }) => d.s === "done"));
    await waitFor(() => expect(result.current.data).toEqual({ s: "running" }));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    await waitFor(() => expect(result.current.error?.status).toBe(502));
    expect(result.current.data).toEqual({ s: "running" });
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.data).toEqual({ s: "done" }));
    unmount();
  });
});
