"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiError } from "@/lib/http";

export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
}

/** Loads once when `key` changes (and when `enabled` becomes true). `refetch` loads again. */
export function useQuery<T>(fetcher: () => Promise<T>, key: string, enabled = true) {
  const [state, setState] = useState<QueryState<T>>({ data: null, loading: enabled, error: null });
  const [attempt, setAttempt] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetcherRef.current().then(
      (data) => !cancelled && setState({ data, loading: false, error: null }),
      (error: ApiError) => !cancelled && setState((s) => ({ ...s, loading: false, error })),
    );
    return () => {
      cancelled = true;
    };
  }, [key, enabled, attempt]);

  const refetch = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, refetch };
}
