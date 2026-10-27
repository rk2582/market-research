"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { Pill, type PillTone } from "@/components/ui/Pill";
import type { ClaimKind, ForceName, ForceRating, Insight, MarketSection } from "../../../types";
import { CiteChips } from "../Citations";
import { useReport } from "../ReportContext";
import { Unavailable } from "./Unavailable";

const KIND: Record<ClaimKind, { label: string; tone: PillTone }> = {
  fact: { label: "Fact", tone: "verified" },
  interpretation: { label: "Interpretation", tone: "info" },
  prediction: { label: "Prediction", tone: "predict" },
};

const QUADRANTS = [
  {
    key: "strengths",
    title: "Strengths",
    box: "bg-verified-tint",
    ink: "text-verified-ink",
  },
  {
    key: "weaknesses",
    title: "Weaknesses",
    box: "bg-partial-tint",
    ink: "text-partial-ink",
  },
  {
    key: "opportunities",
    title: "Opportunities",
    box: "bg-info-tint",
    ink: "text-info-ink",
  },
  {
    key: "threats",
    title: "Threats",
    box: "bg-removed-tint",
    ink: "text-removed-ink",
  },
] as const;

export function AnalysisTab() {
  const { report } = useReport();
  const missing = new Set(report.meta.missing_sections);
  const market = report.meta.mode === "market" ? (report.market ?? null) : null;

  return (
    <div className="space-y-5">
      {market ? (
        <MarketAttractiveness market={market} unavailable={missing.has("swot")} />
      ) : (
        <section aria-labelledby="swot-title">
          <h2 id="swot-title" className="sr-only">
            SWOT analysis
          </h2>
          {missing.has("swot") ? (
            <Card>
              <CardTitle title="SWOT analysis" />
              <Unavailable what="The SWOT analysis" />
            </Card>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              {QUADRANTS.map((q) => (
                <div
                  key={q.key}
                  aria-label={q.title}
                  className={`rounded-card p-7 print-avoid-break print:border print:border-rule ${q.box}`}
                >
                  <h3 className={`text-[21px] font-bold ${q.ink}`}>{q.title}</h3>
                  <InsightList items={report.swot[q.key]} plain />
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {(
          [
            ["market_trends", "Market trends", report.market_trends],
            ["opportunities", "Opportunities", report.opportunities],
            ["risks", "Risks", report.risks],
          ] as const
        ).map(([key, title, items]) => (
          <Card key={key} className="print-avoid-break">
            <CardTitle title={title} />
            {missing.has(key) ? <Unavailable /> : <InsightList items={items} />}
          </Card>
        ))}
      </div>
    </div>
  );
}

function InsightList({ items, plain = false }: { items: Insight[]; plain?: boolean }) {
  if (items.length === 0) return <p className="mt-4 text-[15px] text-ink-faint">None with enough evidence.</p>;
  return (
    <ul className="mt-4 space-y-4">
      {items.map((item) => (
        <li key={item.id} className="text-[15px] leading-relaxed">
          {!plain && (
            <Pill tone={KIND[item.kind].tone} className="mb-1.5">
              {KIND[item.kind].label}
            </Pill>
          )}
          <p>
            {item.text}
            <CiteChips refs={item.refs} />
            {plain && <span className="ml-2 text-[11px] font-semibold text-ink-faint">{KIND[item.kind].label}</span>}
          </p>
        </li>
      ))}
    </ul>
  );
}

const FORCES: Array<{ force: ForceName; title: string; question: string }> = [
  {
    force: "rivalry",
    title: "Rivalry",
    question: "How hard do existing players compete?",
  },
  {
    force: "entry_barriers",
    title: "Entry barriers",
    question: "How hard is it for a newcomer to get in?",
  },
  {
    force: "supplier_power",
    title: "Supplier power",
    question: "How much can suppliers set the terms?",
  },
  {
    force: "buyer_power",
    title: "Buyer power",
    question: "How much can customers push prices down?",
  },
  {
    force: "substitutes",
    title: "Substitutes",
    question: "How easily can customers switch to something else?",
  },
];

const RATING: Record<ForceRating["rating"], { label: string; tone: PillTone }> = {
  low: { label: "Low", tone: "verified" },
  medium: { label: "Medium", tone: "partial" },
  high: { label: "High", tone: "removed" },
};

/** Five forces + signals for and against entering (M13). No overall score: each rating stands on its own claims. */
function MarketAttractiveness({ market, unavailable }: { market: MarketSection; unavailable: boolean }) {
  if (unavailable) {
    return (
      <Card>
        <CardTitle title="Market attractiveness" />
        <Unavailable what="The market analysis" />
      </Card>
    );
  }
  const byForce = new Map(market.forces.map((f) => [f.force, f]));
  return (
    <>
      <Card>
        <CardTitle
          title="Market attractiveness"
          note="Five forces from a newcomer’s point of view. High means that force works against you. Each rating cites its evidence."
        />
        <ul className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {FORCES.map(({ force, title, question }) => {
            const rated = byForce.get(force);
            return (
              <li
                key={force}
                aria-label={title}
                className="rounded-2xl bg-surface-2 p-5 print-avoid-break print:border print:border-rule"
              >
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-[15px] font-semibold">{title}</h3>
                  {rated ? (
                    <Pill tone={RATING[rated.rating].tone}>{RATING[rated.rating].label}</Pill>
                  ) : (
                    <Pill tone="unconfirmed">Not rated</Pill>
                  )}
                </div>
                <p className="mt-1 text-[13px] text-ink-faint">{question}</p>
                <p className="mt-3 text-[15px] leading-snug">
                  {rated ? (
                    <>
                      {rated.reason}
                      <CiteChips refs={rated.refs} />
                    </>
                  ) : (
                    <span className="text-ink-faint">Not enough sourced evidence to rate this.</span>
                  )}
                </p>
              </li>
            );
          })}
        </ul>
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <div
          aria-label="Signals for entering"
          className="rounded-card bg-verified-tint p-7 print-avoid-break print:border print:border-rule"
        >
          <h3 className="text-[21px] font-bold text-verified-ink">Signals for entering</h3>
          <InsightList items={market.signals_for} plain />
        </div>
        <div
          aria-label="Signals against entering"
          className="rounded-card bg-removed-tint p-7 print-avoid-break print:border print:border-rule"
        >
          <h3 className="text-[21px] font-bold text-removed-ink">Signals against entering</h3>
          <InsightList items={market.signals_against} plain />
        </div>
      </div>
    </>
  );
}
