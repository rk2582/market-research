"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { sourceMix, timeline } from "../../../lib/reportModel";
import { CitedText, ClaimLine, useVisibleClaims } from "../Citations";
import { EvidenceDonut } from "../charts/EvidenceDonut";
import { KeyFigures } from "../charts/KeyFigures";
import { SourceMix } from "../charts/SourceMix";
import { useReport } from "../ReportContext";
import type { FactGroup, ReportClaim } from "../../../types";
import { Unavailable } from "./Unavailable";

export function OverviewTab() {
  const { report } = useReport();
  const missing = new Set(report.meta.missing_sections);
  const company = report.company_overview;
  const mix = sourceMix(report);
  const snapshot = company.facts.filter((g) => g.label !== "Recent developments");
  const dated = timeline(report);
  const isMarket = report.meta.mode === "market";

  return (
    <div className="space-y-5">
      <Card>
        <CardTitle title={isMarket ? "Bottom line" : "Executive summary"} />
        {missing.has("executive_summary") ? (
          <Unavailable />
        ) : (
          <p className="mt-4 text-[17px] leading-[1.65] sm:text-[19px]">
            <CitedText text={report.executive_summary} />
          </p>
        )}
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Card className="print-avoid-break">
          <CardTitle title="Evidence" note="Every claim checked against the page it came from" />
          <div className="mt-5">
            <EvidenceDonut validation={report.validation} />
          </div>
          <SecondRoundNote />
        </Card>
        <Card className="print-avoid-break">
          <CardTitle
            title="Where the evidence comes from"
            note={`${report.references.length} sources cited in this report`}
          />
          <div className="mt-6">
            <SourceMix company={mix.company} other={mix.other} />
          </div>
        </Card>
      </div>

      <KeyFigures figures={report.key_figures} company={company.name} />

      <div className="flex flex-wrap items-start gap-5">
        <Card className="min-w-0 flex-[999_1_560px]">
          <CardTitle
            title={isMarket ? "Market snapshot" : "Company snapshot"}
            note={
              company.identity
                ? undefined
                : isMarket
                  ? "Facts about the market, each with its sources; missing topics were not found in public sources"
                  : "Facts about the company, each with its sources"
            }
          />
          {company.identity && (
            <p className="mt-3 rounded-2xl bg-surface-2 px-4 py-3 text-[15px]">
              <span className="font-semibold">{isMarket ? "What this covers: " : "Which company: "}</span>
              <ClaimLine claim={company.identity} />
            </p>
          )}
          <FactRows groups={snapshot} />
          {isMarket && (report.market?.not_found?.length ?? 0) > 0 && (
            <dl>
              {report.market!.not_found!.map((label) => (
                <div key={label} className="grid gap-1 border-t border-rule-soft py-3.5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4">
                  <dt className="pt-0.5 text-[13px] text-ink-faint">{label}</dt>
                  <dd className="text-[15px] text-ink-faint">Not found in public sources — check this yourself.</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
        {dated.length > 0 && (
          <Card className="flex-[1_1_300px] print-avoid-break">
            <CardTitle title="Recent developments" />
            <Timeline items={dated} />
          </Card>
        )}
      </div>

      <Card>
        <CardTitle title={isMarket ? "Market trends" : "Industry overview"} />
        {report.industry_overview.text && (
          <p className="mt-4 text-[17px] leading-relaxed">
            <CitedText text={report.industry_overview.text} />
          </p>
        )}
        <ClaimBullets claims={report.industry_overview.claims} />
      </Card>
    </div>
  );
}

/** Label / statements rows (Description, Pricing …). */
export function FactRows({ groups }: { groups: FactGroup[] }) {
  const { verifiedOnly } = useReport();
  const visible = groups
    .map((g) => ({
      ...g,
      claims: verifiedOnly ? g.claims.filter((c) => c.verdict === "supported") : g.claims,
    }))
    .filter((g) => g.claims.length > 0);
  if (visible.length === 0) return <p className="mt-4 text-[15px] text-ink-faint">No verified facts to show.</p>;
  return (
    <dl className="mt-3">
      {visible.map((group) => (
        <div
          key={group.label}
          className="grid gap-1 border-t border-rule-soft py-3.5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4"
        >
          <dt className="pt-0.5 text-[13px] text-ink-faint">{group.label}</dt>
          <dd className="space-y-2 text-[15px]">
            {group.claims.map((claim) => (
              <p key={claim.id}>
                <ClaimLine claim={claim} />
              </p>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ClaimBullets({ claims }: { claims: ReportClaim[] }) {
  const visible = useVisibleClaims(claims);
  if (visible.length === 0) return null;
  return (
    <ul className="mt-4 space-y-2.5 text-[15px]">
      {visible.map((claim) => (
        <li key={claim.id} className="flex gap-3">
          <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-ink-faint" />
          <ClaimLine claim={claim} />
        </li>
      ))}
    </ul>
  );
}

function Timeline({ items }: { items: Array<{ when: string; claim: ReportClaim }> }) {
  const { verifiedOnly } = useReport();
  const visible = verifiedOnly ? items.filter((i) => i.claim.verdict === "supported") : items;
  return (
    <ol className="mt-5">
      {visible.map(({ when, claim }, i) => (
        <li key={claim.id} className="relative pb-5 pl-7">
          <span
            aria-hidden="true"
            className="absolute left-0 top-1 h-3 w-3 rounded-full border-[3px] border-accent bg-surface"
          />
          {i < visible.length - 1 && (
            <span aria-hidden="true" className="absolute bottom-0 left-[5px] top-5 w-0.5 bg-rule" />
          )}
          <p className="text-xs font-semibold text-accent-ink">{when}</p>
          <p className="mt-1 text-[15px]">
            <ClaimLine claim={claim} />
          </p>
        </li>
      ))}
    </ol>
  );
}

/** M14: what the second research round did (or that it failed and round 1's evidence was used). */
function SecondRoundNote() {
  const { report } = useReport();
  const round = report.meta.second_round;
  if (!round) return null;
  const gaps = round.gaps.length;
  return (
    <details className="mt-5 border-t border-rule-soft pt-4 text-[13px] text-ink-faint">
      <summary className="cursor-pointer">
        {round.error
          ? `A second research round for ${gaps} gap${gaps === 1 ? "" : "s"} did not finish; this report uses the first round.`
          : `Second research round: ${round.filled} of ${gaps} gap${gaps === 1 ? "" : "s"} filled, ${round.new_claims} new claim${round.new_claims === 1 ? "" : "s"}.`}
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {round.gaps.map((gap) => (
          <li key={gap}>{gap}</li>
        ))}
      </ul>
    </details>
  );
}
