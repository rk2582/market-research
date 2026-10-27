"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { domainOf, formatNumber } from "../../../lib/format";
import { claimsBySource, sourceKind } from "../../../lib/reportModel";
import { BarList } from "../charts/BarList";
import { useReport } from "../ReportContext";

const AGENT: Record<string, string> = {
  research: "Researcher",
  competitors: "Competitor researchers",
  validate: "Fact-Checker",
  deepen: "Second round",
  analyse: "Analyst",
  strategise: "Strategist",
  write: "Writer",
};

export function SourcesTab() {
  const { report, openSource } = useReport();
  const cited = claimsBySource(report);
  const usage = report.meta.usage;
  const warnings = report.validation.warnings;

  return (
    <div className="flex flex-wrap items-start gap-5">
      <Card className="min-w-0 flex-[999_1_560px]">
        <CardTitle title={`${report.references.length} sources`} note="Select a source to see the claims that rely on it" />
        <ol className="mt-3">
          {report.references.map((ref) => {
            const count = cited.get(ref.ref)?.length ?? 0;
            return (
              <li key={ref.ref} id={`ref-${ref.ref}`} className="border-t border-rule-soft">
                <button
                  type="button"
                  onClick={() => openSource(ref.ref)}
                  className="grid w-full grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-3 py-3.5 text-left"
                >
                  <span className="text-[15px] font-semibold text-ink-faint">{ref.ref}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-[15px] print:whitespace-normal">{ref.title ?? domainOf(ref.url)}</span>
                    <span className="block truncate text-[13px] text-ink-faint print:whitespace-normal">
                      <span className="hidden print:inline">{ref.url}</span>
                      <span className="print:hidden">{domainOf(ref.url)}</span> ·{" "}
                      {sourceKind(ref.url, report) === "company" ? "Company website" : "News, analyst or database"}
                    </span>
                  </span>
                  <span className="whitespace-nowrap text-[13px] text-ink-faint">
                    {count === 0 ? "" : count === 1 ? "1 claim" : `${count} claims`}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      <div className="flex flex-[1_1_320px] flex-col gap-5">
        {usage.length > 0 && (
          <Card className="print-avoid-break">
            <CardTitle title="How this report was made" note={`Seconds per agent · ${formatNumber(report.meta.total_tokens)} tokens in total`} />
            <div className="mt-5">
              <BarList
                label="Seconds per agent"
                bars={usage.map((u) => ({
                  label: AGENT[u.step] ?? u.step,
                  value: (u.duration_ms ?? 0) / 1000,
                  display: `${((u.duration_ms ?? 0) / 1000).toFixed(1)} s`,
                  note: <span className="text-[12px] text-ink-faint">{formatNumber(u.total_tokens)} tokens</span>,
                }))}
              />
            </div>
          </Card>
        )}
        {warnings.length > 0 && (
          <Card className="print-avoid-break">
            <details>
              <summary className="cursor-pointer text-[15px] font-semibold">
                {warnings.length} fact-check {warnings.length === 1 ? "note" : "notes"}
              </summary>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-[13px] leading-snug text-ink-soft">
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          </Card>
        )}
      </div>
    </div>
  );
}
