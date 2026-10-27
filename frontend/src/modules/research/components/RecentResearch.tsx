import Link from "next/link";
import { LocalTime } from "@/components/ui/LocalTime";
import { Monogram } from "@/components/ui/Monogram";
import { Pill } from "@/components/ui/Pill";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDuration } from "../lib/format";
import type { ResearchRunSummary } from "../types";

/** Recent research as cards: company or market, trust score, competitors or players, time. */
export function RecentResearch({ runs }: { runs: ResearchRunSummary[] }) {
  if (runs.length === 0) {
    return <p className="text-[17px] text-ink-faint">No research yet. Enter a company above to create your first report.</p>;
  }
  return (
    <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {runs.map((run) => {
        const name = run.company_name ?? run.query;
        const isMarket = run.mode === "market";
        const hasScore = run.verified_pct != null && (run.status === "succeeded" || run.status === "partial");
        return (
          <li key={run.id}>
            <Link
              href={`/research/${run.id}`}
              className="flex h-full flex-col rounded-card bg-surface-2 p-6 text-ink transition hover:-translate-y-0.5 hover:shadow-float"
            >
              <span className="flex items-center gap-3.5">
                <Monogram name={name} onMuted />
                <span className="min-w-0">
                  <span className="block truncate text-[19px] font-semibold tracking-tight">{name}</span>
                  <span className="flex items-center gap-2 text-[13px] text-ink-faint">
                    {isMarket && <Pill tone="info">Market</Pill>}
                    <span className="truncate">{run.query}</span>
                  </span>
                </span>
              </span>
              {hasScore ? (
                <>
                  <span className="mt-6 flex items-baseline justify-between">
                    <span className="text-[32px] font-bold tracking-tight tabular-nums">{run.verified_pct}%</span>
                    <span className="text-[13px] text-ink-faint">claims verified</span>
                  </span>
                  <span aria-hidden="true" className="mt-2 block h-1.5 overflow-hidden rounded-full bg-rule">
                    <span className="block h-full bg-verified" style={{ width: `${run.verified_pct}%` }} />
                  </span>
                </>
              ) : (
                <span className="mt-6">
                  <StatusBadge status={run.status} />
                </span>
              )}
              <span className="mt-auto flex flex-wrap justify-between gap-2 pt-4 text-[13px] text-ink-faint">
                <span>
                  {[
                    run.competitor_count != null ? `${run.competitor_count} ${isMarket ? "players" : "competitors"}` : null,
                    run.duration_ms != null ? formatDuration(run.duration_ms) : null,
                    run.status === "partial" ? "partial" : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                <LocalTime iso={run.created_at} />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
