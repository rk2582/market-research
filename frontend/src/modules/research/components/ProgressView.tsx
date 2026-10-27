"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { AGENT_JOB, AGENT_NAME, formatClock, formatNumber, MARKET_AGENT_JOB } from "../lib/format";
import type { ResearchRunDetail, StepInfo, StepName } from "../types";

/** Seconds since `from` (until `to`, or now — ticking every second while the run is live). */
function useElapsed(from: string, to: string | null, live: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [live]);
  const end = to ? new Date(to).getTime() : now;
  return Math.max(0, (end - new Date(from).getTime()) / 1000);
}

interface Activity {
  at: number | null; // seconds from start; null for steps that never ran
  agent: string;
  text: string;
  tone?: "error";
}

/**
 * A step-by-step log built from the step data the API returns (time offsets from step durations).
 * `endAt` (seconds from start to finish) places a failure when the failed step has no duration.
 */
export function activityLog(steps: StepInfo[], endAt?: number, jobs: Record<StepName, string> = AGENT_JOB): Activity[] {
  const log: Activity[] = [];
  let at = 0;
  for (const step of steps) {
    const agent = AGENT_NAME[step.name];
    const tokens = step.input_tokens + step.output_tokens;
    if (step.status === "completed") {
      log.push({ at, agent, text: `Started: ${jobs[step.name].toLowerCase()}` });
      at += (step.duration_ms ?? 0) / 1000;
      log.push({ at, agent, text: `Finished${tokens ? ` · ${formatNumber(tokens)} tokens` : ""}` });
    } else if (step.status === "running") {
      log.push({ at, agent, text: `Working: ${jobs[step.name].toLowerCase()}…` });
    } else if (step.status === "failed") {
      const failedAt = step.duration_ms != null ? at + step.duration_ms / 1000 : (endAt ?? at);
      log.push({ at: failedAt, agent, text: step.error ?? "Failed", tone: "error" });
    } else if (step.status === "skipped") {
      log.push({ at: null, agent, text: "Skipped" });
    }
  }
  return log;
}

/** The research while it runs (and the reason when it fails): pipeline, clock, activity. */
export function ProgressView({ run }: { run: ResearchRunDetail }) {
  const live = run.status === "running";
  const elapsed = useElapsed(run.created_at, run.finished_at, live);
  const done = run.steps.filter((s) => s.status === "completed").length;
  const running = run.steps.some((s) => s.status === "running");
  const percent = Math.round(((done + (running ? 0.5 : 0)) / run.steps.length) * 100);
  const tokens = run.steps.reduce((sum, s) => sum + s.input_tokens + s.output_tokens, 0) || run.totals.total_tokens;
  const name = run.company_name ?? run.query;
  const baseJobs = run.mode === "market" ? MARKET_AGENT_JOB : AGENT_JOB;
  // M14: during the second round the Research step runs again, for the gaps only
  const researchNow: Partial<Record<string, string>> = {
    deepen: "Filling gaps (second round)",
    competitors: run.mode === "market" ? "Researching players in parallel" : "Researching competitors in parallel",
  };
  const now = run.current_step ? researchNow[run.current_step] : undefined;
  const jobs = now ? { ...baseJobs, research: now } : baseJobs;
  const log = activityLog(run.steps, live ? undefined : elapsed, jobs);

  return (
    <div className="mx-auto max-w-[1180px] px-6 pb-20 pt-10">
      <Link href="/" className="text-[15px] text-accent-ink hover:underline">
        ‹ All research
      </Link>
      <div className="mt-5 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <p className="text-[15px] text-ink-faint">Searched for “{run.query}”</p>
          <h1 className="mt-1.5 text-[40px] font-bold leading-[1.05] tracking-tight sm:text-[56px]">
            {live ? `Researching ${run.mode === "market" ? "the market for " : ""}${name}` : `${name} could not be researched`}
          </h1>
        </div>
        <div className="text-right">
          <p className="text-[48px] font-bold tracking-tight tabular-nums" aria-label={`${Math.floor(elapsed)} seconds elapsed`}>
            {formatClock(elapsed)}
          </p>
          <p className="text-[13px] text-ink-faint">{live ? "elapsed · usually about a minute" : "until it stopped"}</p>
        </div>
      </div>

      <div
        role="progressbar"
        aria-label="Research progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-7 h-1 overflow-hidden rounded-full bg-rule"
      >
        <div className={`h-full rounded-full transition-[width] duration-700 ${live ? "bg-accent" : "bg-removed"}`} style={{ width: `${percent}%` }} />
      </div>

      {run.status === "failed" && (
        <div className="mt-8">
          <ErrorState
            title="This research could not be completed"
            message={`${sentence(run.error ?? "A step failed")} No report was created. Start a new research to try again.`}
          />
        </div>
      )}

      <ol aria-label="Steps" className="mt-8 grid grid-cols-2 gap-6 rounded-card bg-surface px-6 py-8 shadow-card sm:grid-cols-5 sm:gap-2">
        {run.steps.map((step) => (
          <li
            key={step.name}
            aria-current={step.status === "running" ? "step" : undefined}
            className="flex flex-col items-center gap-3 px-1 text-center"
          >
            <StepDot step={step} />
            <div>
              <p className={`text-[17px] font-semibold ${step.status === "pending" || step.status === "skipped" ? "text-ink-faint" : ""}`}>
                {AGENT_NAME[step.name]}
              </p>
              <p className="mt-1 text-[13px] leading-snug text-ink-faint">{jobs[step.name]}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-5 flex flex-wrap items-start gap-5">
        <Card className="min-w-0 flex-[999_1_560px]">
          <div className="flex items-center justify-between gap-3">
            <CardTitle title="Activity" />
            <span className="text-[13px] text-ink-faint">{log.length} events</span>
          </div>
          <ul aria-live="polite" className="mt-4">
            {log.map((item, i) => (
              <li
                key={`${item.agent}-${i}`}
                className="animate-rise grid grid-cols-[3rem_6.5rem_minmax(0,1fr)] items-baseline gap-3 border-b border-rule-soft py-2.5 text-[15px] last:border-0"
              >
                <span className="text-[13px] text-ink-faint tabular-nums">{item.at == null ? "–" : formatClock(item.at)}</span>
                <span className="text-xs font-semibold text-accent-ink">{item.agent}</span>
                <span className={item.tone === "error" ? "text-removed-ink" : ""}>{item.text}</span>
              </li>
            ))}
            {log.length === 0 && <li className="py-2.5 text-[15px] text-ink-faint">Starting…</li>}
          </ul>
          {live && (
            <p className="mt-4 text-[13px] text-ink-faint">
              You can leave this page; the research keeps running and appears in Recent research.
            </p>
          )}
        </Card>

        <aside aria-label="So far" className="flex flex-[1_1_260px] flex-col gap-4">
          <Counter label="Steps done" value={`${done} of ${run.steps.length}`} />
          <Counter label="Tokens used" value={formatNumber(tokens)} />
          {!live && (
            <Link
              href="/"
              className="inline-flex min-h-11 items-center justify-center rounded-full bg-accent px-5 text-[15px] font-medium text-on-accent hover:brightness-110"
            >
              Start a new research
            </Link>
          )}
        </aside>
      </div>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card bg-surface p-6 shadow-card">
      <p className="text-[13px] text-ink-faint">{label}</p>
      <p className="mt-1 text-[36px] font-bold tracking-tight tabular-nums">{value}</p>
    </div>
  );
}

const STATE_LABEL = { pending: "waiting", running: "in progress", completed: "done", failed: "failed", skipped: "skipped" } as const;

function StepDot({ step }: { step: StepInfo }) {
  const label = `${AGENT_NAME[step.name]}: ${STATE_LABEL[step.status]}`;
  if (step.status === "completed") {
    return (
      <span role="img" aria-label={label} className="flex h-12 w-12 items-center justify-center rounded-full bg-accent">
        <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (step.status === "running") {
    return (
      <span role="img" aria-label={label} className="animate-pulse-ring flex h-12 w-12 items-center justify-center rounded-full border-2 border-accent bg-surface">
        <span className="h-3 w-3 rounded-full bg-accent" />
      </span>
    );
  }
  if (step.status === "failed") {
    return (
      <span role="img" aria-label={label} className="flex h-12 w-12 items-center justify-center rounded-full bg-removed text-xl font-bold text-white">
        !
      </span>
    );
  }
  return <span role="img" aria-label={label} className="h-12 w-12 rounded-full border-2 border-unconfirmed bg-surface" />;
}

/** "research step failed: timed out" → "Research step failed: timed out." */
function sentence(text: string): string {
  const trimmed = text.trim();
  const capital = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}
