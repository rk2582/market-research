// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function call(handler: typeof GET, path: string, init?: { method?: string; body?: string; search?: string }) {
  const url = `http://localhost:3001/api/proxy/${path}${init?.search ?? ""}`;
  const request = new NextRequest(url, { method: init?.method ?? "GET", body: init?.body });
  return handler(request, { params: Promise.resolve({ path: path.split("/") }) });
}

describe("proxy", () => {
  it("forwards GET with the query string and passes status and body through", async () => {
    const fetchMock = vi.fn(async () => new Response('{"total":0}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("BACKEND_URL", "http://backend:9000/");
    const response = await call(GET, "api/v1/research", { search: "?limit=5" });
    expect(fetchMock).toHaveBeenCalledWith("http://backend:9000/api/v1/research?limit=5", expect.objectContaining({ method: "GET" }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ total: 0 });
  });

  it("forwards POST bodies and error statuses", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response('{"code":"capacity_reached"}', { status: 429, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const response = await call(POST, "api/v1/research", { method: "POST", body: '{"query":"Notion"}' });
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe('{"query":"Notion"}');
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("http://localhost:8000/api/v1/research");
    expect(response.status).toBe(429);
    expect(response.headers.get("content-type")).toBe("application/json");
  });

  it.each(["agents/researcher/runs", "workflows/market-research/runs", "api/v1/../config", "health"])(
    "refuses %s",
    async (path) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const response = await call(GET, path);
      expect(response.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("answers 502 when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    const response = await call(GET, "api/v1/research");
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ code: "backend_unavailable" });
  });
});
