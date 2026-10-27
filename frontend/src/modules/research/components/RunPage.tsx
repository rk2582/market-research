"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { getReport, getRun } from "../api/research-api";
import { usePolling } from "../hooks/usePolling";
import { useQuery } from "../hooks/useQuery";
import { TERMINAL_STATUSES } from "../types";
import { ResearchRunScreen } from "./ResearchRunScreen";

export const POLL_INTERVAL_MS = 3000;

function Page({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-[1180px] space-y-6 px-6 pt-10">{children}</div>;
}

/** Follows one run: polls its status every 3 s until it ends, then loads the report. */
export function RunPage({ id }: { id: string }) {
  const run = usePolling(() => getRun(id), id, POLL_INTERVAL_MS, (r) => TERMINAL_STATUSES.includes(r.status));
  const finished = run.data !== null && TERMINAL_STATUSES.includes(run.data.status);
  const report = useQuery(() => getReport(id), `report-${id}`, finished && run.data?.has_report === true);

  if (run.error?.status === 404) return <RunNotFound />;
  if (run.error && !run.data) {
    return (
      <Page>
        <ErrorState title="This research could not be loaded" message={run.error.message} onRetry={run.retry} />
      </Page>
    );
  }
  if (!run.data) {
    return (
      <Page>
        <Skeleton lines={6} />
      </Page>
    );
  }

  return (
    <>
      {run.error && (
        <Page>
          <ErrorState
            title="Lost contact with the research service"
            message={`${run.error.message} The research itself keeps running.`}
            onRetry={run.retry}
            retryLabel="Reconnect"
          />
        </Page>
      )}
      {report.error ? (
        <Page>
          <ErrorState title="The report could not be loaded" message={report.error.message} onRetry={report.refetch} />
        </Page>
      ) : finished && run.data.has_report && !report.data ? (
        <Page>
          <Skeleton lines={10} />
        </Page>
      ) : (
        <ResearchRunScreen run={run.data} report={report.data} />
      )}
    </>
  );
}

function RunNotFound() {
  return (
    <div className="mx-auto max-w-[680px] px-6 py-28 text-center">
      <h1 className="text-[40px] font-bold tracking-tight">Research not found</h1>
      <p className="mt-3 text-[19px] text-ink-faint">This research does not exist. Check the link, or start a new research.</p>
      <Link
        href="/"
        className="mt-8 inline-flex min-h-11 items-center rounded-full bg-accent px-6 text-[17px] font-medium text-on-accent hover:brightness-110"
      >
        Start a new research
      </Link>
    </div>
  );
}
