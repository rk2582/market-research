"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { listResearch } from "../api/research-api";
import { useQuery } from "../hooks/useQuery";
import { AGENT_JOB, AGENT_NAME, formatDuration } from "../lib/format";
import { STEP_NAMES, type ResearchRunSummary } from "../types";
import { ConfirmSheet } from "./ConfirmSheet";
import { NewResearchForm } from "./NewResearchForm";
import { RecentResearch } from "./RecentResearch";

const EXAMPLES = ["Notion", "monzo.com", "Canva", "Pipedrive"];

const AGENT_TEXT = {
  research: "Reads the company’s site, its news and each competitor’s own pages.",
  validate: "Checks every claim against the exact text of its source.",
  analyse: "Builds the comparison, SWOT, trends and risks from verified claims.",
  strategise: "Turns the evidence into prioritised recommendations.",
  write: "Writes the executive summary with numbered sources.",
} as const;

/** Start page: headline, research box, numbers from past reports, recent research, how it works. */
export function HomeScreen() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const history = useQuery(() => listResearch(20), "history");

  async function handleSubmit(value: string) {
    setConfirming(value); // the confirm sheet checks the company and starts the run
  }

  return (
    <>
      <section id="start" className="mx-auto max-w-[980px] px-6 pb-16 pt-20 text-center sm:pt-28">
        <p className="text-[17px] font-semibold text-accent-ink">Delphi Market360</p>
        <h1 className="mt-4 text-[48px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[80px]">
          Know your market.
          <br />
          <span className="text-ink-faint">Verified.</span>
        </h1>
        <p className="mx-auto mt-7 max-w-[640px] text-[19px] leading-relaxed text-ink-soft sm:text-[21px]">
          AI agents research any company and its competitors, check every claim against its source, and turn the
          evidence into strategy — in about a minute.
        </p>
        <div className="mt-12">
          <NewResearchForm value={query} onChange={setQuery} onSubmit={handleSubmit} />
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5 text-sm">
          <span className="text-ink-faint">Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                document.getElementById("research-query")?.focus();
              }}
              className="min-h-9 rounded-full border border-black/[0.08] bg-surface px-4 text-ink hover:border-accent dark:border-white/10"
            >
              {example}
            </button>
          ))}
        </div>
      </section>

      {confirming && (
        <ConfirmSheet query={confirming} onClose={() => setConfirming(null)} onStarted={(run) => router.push(`/research/${run.id}`)} />
      )}

      {history.data && <HistoryStats runs={history.data.items} />}

      <section id="recent" aria-labelledby="recent-title" className="bg-surface py-20">
        <div className="mx-auto max-w-[1180px] px-6">
          <h2 id="recent-title" className="text-[32px] font-bold tracking-tight sm:text-[40px]">
            Recent research
          </h2>
          <div className="mt-8">
            {history.error ? (
              <ErrorState title="Recent research could not be loaded" message={history.error.message} onRetry={history.refetch} />
            ) : history.loading || !history.data ? (
              <Skeleton lines={4} className="bg-surface-2 shadow-none" />
            ) : (
              <RecentResearch runs={history.data.items} />
            )}
          </div>
        </div>
      </section>

      <section id="how" aria-labelledby="how-title" className="mx-auto max-w-[1180px] px-6 py-24">
        <h2 id="how-title" className="text-center text-[32px] font-bold tracking-tight sm:text-[40px]">
          Five agents. One verified report.
        </h2>
        <p className="mx-auto mt-4 max-w-[620px] text-center text-[19px] leading-relaxed text-ink-faint">
          Every statement links to the page it came from. Claims the sources don’t back are flagged or removed.
        </p>
        <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEP_NAMES.map((step, i) => (
            <li key={step} className="rounded-card bg-surface p-6 shadow-card">
              <p className="text-[13px] font-semibold text-accent-ink">Step {i + 1}</p>
              <p className="mt-2 text-[21px] font-semibold tracking-tight">{AGENT_NAME[step]}</p>
              <p className="mt-1 text-[13px] font-medium text-ink-soft">{AGENT_JOB[step]}</p>
              <p className="mt-3 text-[15px] leading-relaxed text-ink-faint">{AGENT_TEXT[step]}</p>
            </li>
          ))}
        </ol>
      </section>

      <footer className="border-t border-rule px-6 py-6 text-center text-xs text-ink-faint">
        Delphi Market360 · Public web sources via Tavily, analysis by OpenAI
      </footer>
    </>
  );
}

/** Headline numbers from the reports on this page; hidden until at least one report exists. */
export function HistoryStats({ runs }: { runs: ResearchRunSummary[] }) {
  const done = runs.filter((r) => r.status === "succeeded" || r.status === "partial");
  if (done.length === 0) return null;
  const average = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
  const pct = average(done.map((r) => r.verified_pct).filter((v): v is number => v != null));
  const time = average(done.map((r) => r.duration_ms).filter((v): v is number => v != null));
  const competitors = average(done.map((r) => r.competitor_count).filter((v): v is number => v != null));

  return (
    <section aria-label="Your reports so far" className="mx-auto max-w-[1180px] px-6 pb-20">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile align="center" label="Reports" value={String(done.length)} note="completed" />
        {pct != null && <StatTile align="center" label="Claims verified" value={`${Math.round(pct)}%`} note="on average" />}
        {time != null && <StatTile align="center" label="Time per report" value={formatDuration(time)} note="on average" />}
        {competitors != null && (
          <StatTile align="center" label="Competitors" value={String(Math.round(competitors))} note="profiled per company" />
        )}
      </div>
    </section>
  );
}
