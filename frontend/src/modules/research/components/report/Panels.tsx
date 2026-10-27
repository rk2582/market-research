"use client";

import { Drawer } from "@/components/ui/Drawer";
import { Monogram } from "@/components/ui/Monogram";
import { Pill } from "@/components/ui/Pill";
import { domainOf } from "../../lib/format";
import { VERDICT_SHORT, VERDICT_TONE, claimsBySource, competitorScore, sourceKind } from "../../lib/reportModel";
import { useReport } from "./ReportContext";
import { FactRows } from "./tabs/OverviewTab";

/** One source: title, site, link, and every claim in the report that relies on it. */
export function SourcePanel({ refNumber, onClose }: { refNumber: number; onClose: () => void }) {
  const { report, verifiedOnly } = useReport();
  const ref = report.references.find((r) => r.ref === refNumber);
  if (!ref) return null;
  const claims = (claimsBySource(report).get(refNumber) ?? []).filter((c) => !verifiedOnly || c.claim.verdict === "supported");

  return (
    <Drawer title={`Source ${refNumber}`} onClose={onClose}>
      <p className="text-[13px] font-semibold text-accent-ink">Source {refNumber}</p>
      <h2 className="mt-2 text-2xl font-bold leading-tight tracking-tight">{ref.title ?? domainOf(ref.url)}</h2>
      <p className="mt-2 text-[15px] text-ink-faint">
        {domainOf(ref.url)} · {sourceKind(ref.url, report) === "company" ? "Company website" : "News, analyst or database"}
      </p>
      <a
        href={ref.url}
        target="_blank"
        rel="noreferrer noopener"
        className="mt-4 inline-flex min-h-11 items-center rounded-full bg-accent px-5 text-[15px] font-medium text-on-accent hover:brightness-110"
      >
        Open the page ↗
      </a>
      <h3 className="mt-8 text-[13px] font-semibold text-ink-faint">
        {claims.length === 0 ? "No claims shown with the current filter" : `Claims that cite this source (${claims.length})`}
      </h3>
      <ul className="mt-3 space-y-2.5">
        {claims.map(({ about, claim }) => (
          <li key={claim.id} className="rounded-2xl bg-surface-2 px-4 py-3.5 text-[15px] leading-snug">
            <p className="text-xs text-ink-faint">{about}</p>
            <p className="mt-1">{claim.text}</p>
            <Pill tone={VERDICT_TONE[claim.verdict]} className="mt-2">
              {VERDICT_SHORT[claim.verdict]}
            </Pill>
          </li>
        ))}
      </ul>
    </Drawer>
  );
}

/** A competitor's full profile, every fact with its sources. */
export function CompetitorPanel({ index, onClose }: { index: number; onClose: () => void }) {
  const { report } = useReport();
  const competitor = report.competitor_landscape[index];
  if (!competitor) return null;
  const score = competitorScore(competitor);

  return (
    <Drawer title={`${competitor.name} profile`} onClose={onClose}>
      <p className="text-[13px] font-semibold text-accent-ink">
        {report.meta.mode === "market"
          ? "Player in this market"
          : `${competitor.relation === "direct" ? "Direct" : "Indirect"} competitor`}
      </p>
      <div className="mt-3 flex items-center gap-4">
        <Monogram name={competitor.name} size="md" />
        <div className="min-w-0">
          <h2 className="text-[32px] font-bold leading-tight tracking-tight">{competitor.name}</h2>
          <p className="text-[15px] text-ink-faint">
            {competitor.website ? `${domainOf(competitor.website)} · ` : ""}
            {score.verified} of {score.total} facts verified
          </p>
        </div>
      </div>
      <FactRows groups={competitor.facts} />
    </Drawer>
  );
}
