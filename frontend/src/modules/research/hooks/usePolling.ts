"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiError } from "@/lib/http";
import type { QueryState } from "./useQuery";

/**
 * Loads now, then again every `intervalMs` until `isDone(data)` is true.
 * Stops on an error (the screen shows it with a retry button); `retry` starts again.
 * Waits for each answer before scheduling the next call, so slow responses never pile up.
 */
export function usePolling<T>(fetcher: () => Promise<T>, key: string, intervalMs: number, isDone: (data: T) => boolean) {
  const [state, setState] = useState<QueryState<T>>({ data: null, loading: true, error: null });
  const [attempt, setAttempt] = useState(0);
  const fetcherRef = useRef(fetcher);
  const isDoneRef = useRef(isDone);
  fetcherRef.current = fetcher;
  isDoneRef.current = isDone;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const data = await fetcherRef.current();
        if (cancelled) return;
        setState({ data, loading: false, error: null });
        if (!isDoneRef.current(data)) timer = setTimeout(tick, intervalMs);
      } catch (error) {
        if (!cancelled) setState((s) => ({ ...s, loading: false, error: error as ApiError }));
      }
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, intervalMs, attempt]);

  const retry = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    setAttempt((n) => n + 1);
  }, []);
  return { ...state, retry };
}
