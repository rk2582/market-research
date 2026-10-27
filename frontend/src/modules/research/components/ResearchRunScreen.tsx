import type { Report, ResearchRunDetail } from "../types";
import { ProgressView } from "./ProgressView";
import { ReportDashboard } from "./report/ReportDashboard";

/** One run: the progress pipeline while it works (or the reason it failed), the dashboard when done. */
export function ResearchRunScreen({ run, report }: { run: ResearchRunDetail; report: Report | null }) {
  if (report && (run.status === "succeeded" || run.status === "partial")) {
    return <ReportDashboard report={report} durationMs={run.totals.duration_ms} />;
  }
  return <ProgressView run={run} />;
}
