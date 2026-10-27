"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { CiteChips } from "../Citations";
import { useReport } from "../ReportContext";
import { Unavailable } from "./Unavailable";

const IMPACT = {
  high: { label: "High impact", tone: "accent" },
  medium: { label: "Medium impact", tone: "neutral" },
  low: { label: "Low impact", tone: "neutral" },
} as const;

export function RecommendationsTab() {
  const { report } = useReport();
  const missing = new Set(report.meta.missing_sections);
  const recs = report.recommendations;
  const high = recs.filter((r) => r.impact === "high").length;
  const market = report.meta.mode === "market" ? (report.market ?? null) : null;
  const noun = market ? ["entry option", "entry options"] : ["recommendation", "recommendations"];

  return (
    <div className="space-y-5">
      {missing.has("recommendations") ? (
        <Card>
          <CardTitle title={market ? "Entry options" : "Strategic recommendations"} />
          <Unavailable what={market ? "Entry options" : "Recommendations"} />
        </Card>
      ) : (
        <>
          <p className="print-keep-next text-[15px] text-ink-faint">
            {recs.length} {recs.length === 1 ? noun[0] : noun[1]}, {market ? "most promising" : "most important"} first
            {high > 0 && ` · ${high} high impact`}
          </p>
          {recs.map((rec) => (
            <Card key={rec.priority} as="article" className="print-avoid-break">
              <div className="grid gap-x-5 gap-y-2 sm:grid-cols-[3.5rem_minmax(0,1fr)]">
                <span aria-hidden="true" className="text-[44px] font-bold leading-none text-unconfirmed">
                  {rec.priority}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap gap-2">
                    <Pill tone={IMPACT[rec.impact].tone}>{IMPACT[rec.impact].label}</Pill>
                    {rec.warning && <Pill tone="partial">{rec.warning}</Pill>}
                  </div>
                  <h2 className="mt-2.5 text-[22px] font-bold leading-tight tracking-tight sm:text-2xl">
                    <span className="sr-only">
                      {market ? "Entry option" : "Recommendation"} {rec.priority}:{" "}
                    </span>
                    {rec.title}
                  </h2>
                  <p className="mt-3 text-[17px] leading-relaxed text-ink-soft">
                    {rec.rationale}
                    <CiteChips refs={rec.refs} />
                  </p>
                  <div className="mt-5 grid gap-6 md:grid-cols-2">
                    <div>
                      <h3 className="text-[13px] font-semibold text-ink-faint">What to do</h3>
                      <ul className="mt-2.5 list-disc space-y-2 pl-5 text-[15px] leading-snug marker:text-ink-faint">
                        {rec.next_steps.map((s) => (
                          <li key={s}>{s}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className="text-[13px] font-semibold text-ink-faint">Risks and trade-offs</h3>
                      <ul className="mt-2.5 list-disc space-y-2 pl-5 text-[15px] leading-snug text-ink-soft marker:text-ink-faint">
                        {rec.risks_tradeoffs.map((s) => (
                          <li key={s}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </>
      )}

      {market && (
        <Card className="print-avoid-break">
          <CardTitle
            title="Check before you invest"
            note="Real-world checks for the biggest unknowns — do these before spending money"
          />
          {missing.has("recommendations") ? (
            <Unavailable what="The checklist" />
          ) : market.checks_before_investing.length === 0 ? (
            <p className="mt-4 text-[15px] text-ink-faint">No checks were suggested.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {market.checks_before_investing.map((check) => (
                <li key={check} className="flex gap-3 text-[15px] leading-snug">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 h-[18px] w-[18px] flex-none rounded-[5px] border-2 border-ink-faint print:border-ink"
                  />
                  {check}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Card className="print-avoid-break">
        <CardTitle title="Next steps" note={`A short action list drawn from the ${noun[1]}`} />
        {missing.has("next_steps") ? (
          <Unavailable what="Next steps" />
        ) : (
          <ol className="mt-4 space-y-3">
            {report.next_steps.map((step, i) => (
              <li key={step} className="flex gap-3 text-[15px] leading-snug">
                <span
                  aria-hidden="true"
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent-ink"
                >
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
