"use client";

import { type ReactNode, useMemo, useState } from "react";
import { LocalTime } from "@/components/ui/LocalTime";
import { Monogram } from "@/components/ui/Monogram";
import { PrintButton } from "@/components/ui/PrintButton";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { StatTile } from "@/components/ui/StatTile";
import { Switch } from "@/components/ui/Switch";
import { domainOf, formatDuration, formatNumber } from "../../lib/format";
import { sourceMix, verifiedPct } from "../../lib/reportModel";
import type { Report } from "../../types";
import { CompetitorPanel, SourcePanel } from "./Panels";
import { type ReportActions, ReportProvider } from "./ReportContext";
import { AnalysisTab } from "./tabs/AnalysisTab";
import { CompetitorsTab } from "./tabs/CompetitorsTab";
import { OverviewTab } from "./tabs/OverviewTab";
import { RecommendationsTab } from "./tabs/RecommendationsTab";
import { SourcesTab } from "./tabs/SourcesTab";

export type ReportTab = "overview" | "competitors" | "analysis" | "recommendations" | "sources";

type Tab = { id: ReportTab; label: string; render: () => ReactNode };

const TABS: Tab[] = [
  { id: "overview", label: "Overview", render: () => <OverviewTab /> },
  { id: "competitors", label: "Competitors", render: () => <CompetitorsTab /> },
  { id: "analysis", label: "Analysis", render: () => <AnalysisTab /> },
  {
    id: "recommendations",
    label: "Recommendations",
    render: () => <RecommendationsTab />,
  },
  { id: "sources", label: "Sources", render: () => <SourcesTab /> },
];

/** Market-entry reports (M13): same tabs, named for someone deciding whether to enter a market. */
const MARKET_LABELS: Partial<Record<ReportTab, string>> = {
  competitors: "Players",
  recommendations: "Entry options",
};
const MARKET_TABS: Tab[] = TABS.map((t) => ({
  ...t,
  label: MARKET_LABELS[t.id] ?? t.label,
}));

/**
 * The report as a dashboard: headline band, key numbers, tabs, and side panels for sources and
 * competitors. Every tab is in the page so "Save as PDF" prints them all, one after another.
 */
export function ReportDashboard({ report, durationMs }: { report: Report; durationMs?: number | null }) {
  const [tab, setTab] = useState<ReportTab>("overview");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [source, setSource] = useState<number | null>(null);
  const [competitor, setCompetitor] = useState<number | null>(null);

  const actions: ReportActions = useMemo(
    () => ({
      report,
      verifiedOnly,
      openSource: (ref) => {
        setCompetitor(null);
        setSource(ref);
      },
      openCompetitor: (index) => {
        setSource(null);
        setCompetitor(index);
      },
    }),
    [report, verifiedOnly],
  );

  const { meta, validation, company_overview: company } = report;
  const market = meta.mode === "market" ? (report.market ?? null) : null;
  const tabs = market ? MARKET_TABS : TABS;
  const mix = sourceMix(report);
  const competitorNames = report.competitor_landscape.map((c) => c.name);
  const seconds = durationMs ?? meta.usage.reduce((sum, u) => sum + (u.duration_ms ?? 0), 0);

  return (
    <ReportProvider value={actions}>
      <article className="mx-auto max-w-[1180px] px-6 pb-24 pt-10 print:max-w-none print:px-0 print:pt-0">
        <header className="flex flex-wrap items-center justify-between gap-6">
          <div className="flex min-w-0 items-center gap-5">
            <Monogram name={market ? market.scope.product : company.name} size="lg" className="print:hidden" />
            <div className="min-w-0">
              <p className="text-[15px] font-semibold text-accent-ink">
                {market ? "Market-entry report" : "Market intelligence report"}
              </p>
              <h1 className="mt-1 text-[40px] font-bold leading-[1.05] tracking-tight sm:text-[56px]">
                {market ? market.scope.product : company.name}
              </h1>
              <p className="mt-2 flex flex-wrap gap-x-2 text-[15px] text-ink-faint">
                {market && (
                  <>
                    <span>{market.scope.region}</span>
                    {market.scope.customer_type && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>{market.scope.customer_type}</span>
                      </>
                    )}
                    <span aria-hidden="true">·</span>
                  </>
                )}
                {!market && company.website && (
                  <>
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-accent-ink hover:underline"
                    >
                      {domainOf(company.website)}
                    </a>
                    <span aria-hidden="true">·</span>
                  </>
                )}
                <span>Searched for “{meta.query}”</span>
                {meta.competitors_confirmed && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>Competitors confirmed by you</span>
                  </>
                )}
                <span aria-hidden="true">·</span>
                <LocalTime iso={meta.generated_at} />
              </p>
            </div>
          </div>
          <PrintButton />
        </header>

        {market && (
          <p
            role="note"
            className="mt-6 rounded-card bg-info-tint px-6 py-4 text-[15px] text-info-ink print:border print:border-rule"
          >
            <span className="font-semibold">Please note: </span>
            {market.disclaimer}
          </p>
        )}

        {meta.outcome === "partial" && (
          <div role="note" className="mt-6 rounded-card bg-partial-tint px-6 py-4 text-[15px]">
            <p className="font-semibold text-partial-ink">This is a partial report.</p>
            <p className="mt-0.5 text-ink-soft">
              {Object.values(meta.step_errors)[0] ?? "A step did not finish"}. Sections that need it say so; everything
              else was researched and fact-checked as usual.
            </p>
          </div>
        )}

        <section aria-label="Key figures" className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile
            label="Claims verified"
            value={`${verifiedPct(validation)}%`}
            note={`${validation.supported} of ${validation.claims_total} checked against their source`}
          />
          <StatTile
            label={market ? "Players profiled" : "Competitors profiled"}
            value={String(competitorNames.length)}
            note={competitorNames.join(", ") || "None found"}
          />
          <StatTile
            label="Sources cited"
            value={String(report.references.length)}
            note={`${mix.company} from companies’ own websites`}
          />
          <StatTile
            label="Time to report"
            value={seconds ? formatDuration(seconds) : "—"}
            note={`5 agents · ${formatNumber(meta.total_tokens)} tokens`}
          />
        </section>

        <div className="mt-9 flex flex-wrap items-center justify-between gap-4 print:hidden">
          <SegmentedTabs tabs={tabs} value={tab} onChange={setTab} label="Report sections" idPrefix="report" />
          <Switch checked={verifiedOnly} onChange={setVerifiedOnly} label="Show only verified claims" />
        </div>

        {tabs.map((t) => (
          <section
            key={t.id}
            id={`report-panel-${t.id}`}
            role="tabpanel"
            aria-labelledby={`report-tab-${t.id}`}
            className={`mt-5 print:mt-0 print:block ${t.id === "overview" ? "" : "print:break-before-page"} ${t.id === tab ? "animate-rise" : "hidden"}`}
          >
            <h2 className="mb-4 hidden text-2xl font-bold print:block">{t.label}</h2>
            {t.render()}
          </section>
        ))}
      </article>

      {source !== null && <SourcePanel refNumber={source} onClose={() => setSource(null)} />}
      {competitor !== null && <CompetitorPanel index={competitor} onClose={() => setCompetitor(null)} />}
    </ReportProvider>
  );
}
