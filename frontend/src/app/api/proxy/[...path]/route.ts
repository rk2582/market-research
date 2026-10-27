// Forwards /api/proxy/api/v1/... to the backend, so the browser never needs the backend's
// address and no CORS setup is needed. Only our product API is reachable through it: the
// AgentOS routes (/agents, /workflows, …) are deliberately not exposed to the browser.

import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic"; // never cache: run status changes every few seconds

const ALLOWED_PREFIX = "api/v1/";
const TIMEOUT_MS = 60_000; // above the backend's slowest call (the confirm step allows 40 s)

function backendOrigin(): string {
  return (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
}

function isAllowed(path: string): boolean {
  if (path.includes("..") || path.includes("//") || path.includes("\\")) return false;
  return path.startsWith(ALLOWED_PREFIX);
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext, method: "GET" | "POST") {
  const { path: segments } = await context.params;
  const path = segments.join("/");
  if (!isAllowed(path)) {
    return NextResponse.json({ detail: "This path is not available through the proxy.", code: "forbidden_path" }, { status: 403 });
  }
  const query = request.nextUrl.searchParams.toString();
  const url = `${backendOrigin()}/${path}${query ? `?${query}` : ""}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
      body: method === "POST" ? await request.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return NextResponse.json(
      { detail: "The research service is not reachable.", code: "backend_unavailable" },
      { status: 502 },
    );
  }
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
  });
}

export function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context, "GET");
}

export function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context, "POST");
}
