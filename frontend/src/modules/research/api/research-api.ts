// The research endpoints (backend: /api/v1/research). Only this module talks to the backend.

import { request } from "@/lib/http";
import type {
  IdentifyResult,
  Report,
  ResearchRunDetail,
  ResearchRunList,
  ResearchRunSummary,
  StartOptions,
} from "../types";

const BASE = "api/v1/research";

/** Confirm step: which company (or market) is meant, plus suggested competitors. Takes a few seconds. */
export function identify(query: string): Promise<IdentifyResult> {
  return request<IdentifyResult>(`${BASE}/identify`, { method: "POST", body: { query } });
}

/** Start a run; with `options` (from the confirm step) it researches exactly that company and list. */
export function startResearch(query: string, options: StartOptions = {}): Promise<ResearchRunSummary> {
  return request<ResearchRunSummary>(BASE, { method: "POST", body: { query, ...options } });
}

export function listResearch(limit = 20, offset = 0): Promise<ResearchRunList> {
  return request<ResearchRunList>(`${BASE}?limit=${limit}&offset=${offset}`);
}

export function getRun(id: string): Promise<ResearchRunDetail> {
  return request<ResearchRunDetail>(`${BASE}/${encodeURIComponent(id)}`);
}

export function getReport(id: string): Promise<Report> {
  return request<Report>(`${BASE}/${encodeURIComponent(id)}/report`);
}
