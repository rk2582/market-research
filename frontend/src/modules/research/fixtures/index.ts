// Test data: two real reports from live runs (Notion, Monzo), one illustrative market report, plus runs in every state.

import type {
  IdentifyResult,
  Report,
  ResearchRunDetail,
  ResearchRunList,
  ResearchRunSummary,
  StepInfo,
  StepName,
  StepState,
} from "../types";
import { STEP_NAMES } from "../types";
import market from "./report-market.json";
import monzo from "./report-monzo.json";
import notion from "./report-notion.json";

export const notionReport = notion as Report;
export const monzoReport = monzo as Report;
/** M13 market-entry report. Illustrative test data (fictional players, .example sources), built by the real
 *  backend assembler — not real research. */
export const marketReport = market as Report;

/** The Notion report as if the analysis step had failed: prose and analysis sections missing. */
export const partialReport: Report = {
  ...notionReport,
  meta: {
    ...notionReport.meta,
    outcome: "partial",
    missing_sections: [
      "executive_summary",
      "competitive_comparison",
      "swot",
      "market_trends",
      "opportunities",
      "risks",
      "recommendations",
      "next_steps",
    ],
    step_errors: { analyse: "Analyst timed out after 120 s" },
  },
  executive_summary: "",
  competitive_comparison: [],
  swot: { strengths: [], weaknesses: [], opportunities: [], threats: [] },
  market_trends: [],
  opportunities: [],
  risks: [],
  recommendations: [],
  next_steps: [],
};

function stepsFromReport(report: Report): StepInfo[] {
  return STEP_NAMES.map((name) => {
    const usage = report.meta.usage.find((u) => u.step === name);
    const error = report.meta.step_errors[name] ?? null;
    return {
      name,
      status: error ? "failed" : usage ? "completed" : "skipped",
      duration_ms: usage?.duration_ms ?? null,
      input_tokens: usage?.input_tokens ?? 0,
      output_tokens: usage?.output_tokens ?? 0,
      error,
    };
  });
}

function steps(states: Partial<Record<StepName, StepState>>, error?: string): StepInfo[] {
  return STEP_NAMES.map((name) => ({
    name,
    status: states[name] ?? "pending",
    duration_ms: states[name] === "completed" ? 8000 : null,
    input_tokens: states[name] === "completed" ? 12000 : 0,
    output_tokens: states[name] === "completed" ? 1500 : 0,
    error: states[name] === "failed" ? (error ?? "Step failed") : null,
  }));
}

function detail(summary: ResearchRunSummary, extra: Partial<ResearchRunDetail>): ResearchRunDetail {
  return {
    ...summary,
    website_url: null,
    error: null,
    agno_run_id: `agno-${summary.id}`,
    current_step: null,
    totals: { input_tokens: 0, output_tokens: 0, total_tokens: 0, duration_ms: null },
    steps: steps({}),
    has_report: false,
    ...extra,
  };
}

function totalsOf(report: Report, durationMs: number) {
  return {
    input_tokens: report.meta.total_input_tokens,
    output_tokens: report.meta.total_output_tokens,
    total_tokens: report.meta.total_tokens,
    duration_ms: durationMs,
  };
}

const summaries: Record<string, ResearchRunSummary> = {
  "demo-running": {
    id: "demo-running",
    query: "Canva",
    input_type: "name",
    company_name: null,
    status: "running",
    created_at: "2026-10-22T05:10:00Z",
    finished_at: null,
  },
  "demo-monzo": {
    id: "demo-monzo",
    query: "https://monzo.com",
    input_type: "url",
    company_name: "Monzo",
    status: "succeeded",
    created_at: "2026-10-21T23:13:41Z",
    finished_at: "2026-10-21T23:14:44Z",
    duration_ms: 63000,
    verified_pct: 84,
    competitor_count: 4,
  },
  "demo-notion": {
    id: "demo-notion",
    query: "Notion",
    input_type: "name",
    company_name: "Notion",
    status: "succeeded",
    created_at: "2026-10-21T23:12:42Z",
    finished_at: "2026-10-21T23:13:41Z",
    duration_ms: 59000,
    verified_pct: 82,
    competitor_count: 5,
  },
  "demo-partial": {
    id: "demo-partial",
    query: "Notion Labs",
    input_type: "name",
    company_name: "Notion",
    status: "partial",
    created_at: "2026-10-21T21:02:00Z",
    finished_at: "2026-10-21T21:04:10Z",
    duration_ms: 130000,
    verified_pct: null,
    competitor_count: 5,
  },
  "demo-failed": {
    id: "demo-failed",
    query: "Acme Widgets Ltd",
    input_type: "name",
    company_name: null,
    status: "failed",
    created_at: "2026-10-21T20:40:00Z",
    finished_at: "2026-10-21T20:40:31Z",
  },
};

export const fixtureRuns: Record<string, ResearchRunDetail> = {
  "demo-running": detail(summaries["demo-running"], {
    current_step: "analyse",
    steps: steps({ research: "completed", validate: "completed", analyse: "running" }),
    totals: { input_tokens: 61000, output_tokens: 4100, total_tokens: 65100, duration_ms: null },
  }),
  "demo-monzo": detail(summaries["demo-monzo"], {
    website_url: "https://monzo.com",
    steps: stepsFromReport(monzoReport),
    totals: totalsOf(monzoReport, 63000),
    has_report: true,
  }),
  "demo-notion": detail(summaries["demo-notion"], {
    steps: stepsFromReport(notionReport),
    totals: totalsOf(notionReport, 59000),
    has_report: true,
  }),
  "demo-partial": detail(summaries["demo-partial"], {
    steps: stepsFromReport(partialReport).map((s) =>
      s.name === "strategise" || s.name === "write" ? { ...s, status: "skipped" } : s,
    ),
    totals: totalsOf(partialReport, 130000),
    has_report: true,
  }),
  "demo-failed": detail(summaries["demo-failed"], {
    error: "research step failed: Researcher timed out after 300 s",
    steps: steps(
      { research: "failed", validate: "skipped", analyse: "skipped", strategise: "skipped", write: "skipped" },
      "Researcher timed out after 300 s",
    ),
    totals: { input_tokens: 41000, output_tokens: 0, total_tokens: 41000, duration_ms: 300000 },
  }),
};

export const fixtureReports: Record<string, Report> = {
  "demo-monzo": monzoReport,
  "demo-notion": notionReport,
  "demo-partial": partialReport,
};

export const fixtureRunList: ResearchRunList = {
  items: Object.values(summaries),
  total: Object.keys(summaries).length,
};

/** A confirm-step answer: one clear match and three suggested competitors. */
export const identifyResult: IdentifyResult = {
  query: "Notion",
  input_type: "name",
  kind: "company",
  matches: [
    {
      name: "Notion",
      website: "https://www.notion.so",
      description: "Notion Labs’ connected workspace for docs, wikis and projects.",
      source_url: "https://www.notion.so",
    },
  ],
  product_lines: [{ name: "Docs and wikis", brands: ["Notion"] }, { name: "Project management", brands: ["Notion Projects"] }],
  competitors: [
    { name: "Airtable", website: "https://airtable.com", competes_in: "Project management", reason: "Databases for teams", source_url: "https://airtable.com" },
    { name: "Coda", website: "https://coda.io", competes_in: "Docs and wikis", reason: "Docs that work like apps", source_url: "https://coda.io" },
    { name: "Confluence", website: null, competes_in: "Docs and wikis", reason: "Team wiki", source_url: "https://tracxn.com/x", weak_evidence: true },
  ],
  market: null,
  note: "Matched Notion Labs.",
  total_tokens: 3200,
  duration_ms: 6400,
};
