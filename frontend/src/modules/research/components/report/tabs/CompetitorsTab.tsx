"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { Monogram } from "@/components/ui/Monogram";
import { Pill } from "@/components/ui/Pill";
import { domainOf } from "../../../lib/format";
import { competitorScore } from "../../../lib/reportModel";
import { CiteChips } from "../Citations";
import { useReport } from "../ReportContext";
import { Unavailable } from "./Unavailable";

export function CompetitorsTab() {
  const { report, openCompetitor } = useReport();
  const competitors = report.competitor_landscape;
  const rows = report.competitive_comparison;
  const companies = rows[0]?.cells.map((c) => c.company) ?? [];
  const missing = report.meta.missing_competitors ?? [];

  return (
    <div className="space-y-5">
      {missing.length > 0 && (
        <p role="note" className="rounded-card bg-partial-tint px-6 py-4 text-[15px] text-partial-ink">
          No reliable public information was found for {missing.join(", ")}, so {missing.length === 1 ? "it is" : "they are"} not
          profiled below.
        </p>
      )}
      {competitors.length === 0 ? (
        <Card>
          <p className="text-[15px] text-ink-faint">{report.meta.mode === "market" ? "No main players were found for this market." : "No competitors were found for this company."}</p>
        </Card>
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {competitors.map((c, i) => {
            const score = competitorScore(c);
            const description = c.facts.find((g) => g.label === "Description")?.claims[0]?.text;
            return (
              <li key={c.name} className="print-avoid-break">
                <button
                  type="button"
                  onClick={() => openCompetitor(i)}
                  className="flex h-full w-full flex-col gap-4 rounded-card bg-surface p-6 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-float print:border print:border-rule"
                >
                  <span className="flex w-full items-center gap-3.5">
                    <Monogram name={c.name} />
                    <span className="min-w-0">
                      <span className="block text-[19px] font-semibold">{c.name}</span>
                      {c.website && <span className="block truncate text-[13px] text-ink-faint">{domainOf(c.website)}</span>}
                    </span>
                    <Pill className="ml-auto">{c.relation === "direct" ? "Direct" : "Indirect"}</Pill>
                  </span>
                  {description && <span className="text-[15px] leading-relaxed text-ink-soft">{description}</span>}
                  <span className="mt-auto w-full">
                    <span className="flex justify-between text-[13px] text-ink-faint">
                      <span>
                        {score.verified} of {score.total} facts verified
                      </span>
                      <span className="text-accent-ink print:hidden">View profile ›</span>
                    </span>
                    <span aria-hidden="true" className="mt-2 block h-1.5 overflow-hidden rounded-full bg-rule">
                      <span className="block h-full bg-verified" style={{ width: `${score.total ? (100 * score.verified) / score.total : 0}%` }} />
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Card>
        <CardTitle title="Side-by-side comparison" note="Grey cells: no public information found" />
        {report.meta.missing_sections.includes("competitive_comparison") ? (
          <Unavailable what="The comparison" />
        ) : rows.length === 0 ? (
          <p className="mt-4 text-[15px] text-ink-faint">Not enough sourced information to compare.</p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-[13px] leading-snug">
              <thead>
                <tr className="border-b border-rule">
                  <th scope="col" className="w-36 py-3 pr-3 font-normal text-ink-faint">
                    <span className="sr-only">Dimension</span>
                  </th>
                  {companies.map((name, i) => (
                    <th key={name} scope="col" className={`px-3 py-3 text-[15px] font-semibold ${i === 0 ? "text-accent-ink" : ""}`}>
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.dimension} className="border-b border-rule-soft align-top print-avoid-break">
                    <th scope="row" className="py-3.5 pr-3 font-normal text-ink-faint">
                      {row.dimension}
                    </th>
                    {row.cells.map((cell, i) => (
                      <td
                        key={cell.company}
                        className={`px-3 py-3.5 ${i === 0 ? "bg-accent-tint/50" : ""} ${cell.refs.length ? "" : "text-ink-faint"}`}
                      >
                        {cell.refs.length ? cell.value : cell.value || "Not publicly available"}
                        <CiteChips refs={cell.refs} small />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
