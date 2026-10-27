import { vi } from "vitest";

export type Route = { status?: number; body?: unknown; throws?: boolean };
type Handler = Route | ((url: string, init?: RequestInit) => Route);

/** Replaces global fetch. Keys are "METHOD path-suffix"; the first matching key wins. */
export function mockFetch(routes: Record<string, Handler | Handler[]>) {
  const calls: Array<{ method: string; url: string; body?: unknown }> = [];
  const queues = new Map(Object.entries(routes).map(([k, v]) => [k, Array.isArray(v) ? [...v] : v]));
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = [...queues.keys()].find((k) => {
      const [m, suffix] = k.split(" ");
      return m === method && url.endsWith(suffix);
    });
    if (!key) throw new Error(`Unexpected fetch: ${method} ${url}`);
    const entry = queues.get(key)!;
    const handler = Array.isArray(entry) ? (entry.length > 1 ? entry.shift()! : entry[0]) : entry;
    const route = typeof handler === "function" ? handler(url, init) : handler;
    if (route.throws) throw new TypeError("Failed to fetch");
    return new Response(route.body === undefined ? "not json" : JSON.stringify(route.body), {
      status: route.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
