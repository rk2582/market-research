"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { formatFigure, keyFigureGroups } from "../../../lib/reportModel";
import type { KeyFigure } from "../../../types";
import { CiteChips, EstimateTag } from "../Citations";
import { BarList } from "./BarList";

/**
 * Charts of the report's key figures. Every number was checked by the backend: it appears in a
 * verified claim it cites. Figures sharing a label and unit become one bar chart; single figures
 * are shown as big numbers. No figures → nothing is shown.
 */
export function KeyFigures({ figures, company }: { figures: KeyFigure[] | undefined; company: string }) {
  const groups = keyFigureGroups(figures);
  const charts = groups.filter((g) => g.figures.length > 1);
  const singles = groups.filter((g) => g.figures.length === 1).map((g) => g.figures[0]);
  if (groups.length === 0) return null;

  return (
    <>
      {charts.map((group) => (
        <Card key={`${group.label}|${group.unit}`} className="print-avoid-break">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <CardTitle title={group.label} />
            <span className="text-[13px] text-ink-faint">{group.unit} · every number from a verified source
              {group.figures.some((f) => f.estimate) && " · estimates marked"}
            </span>
          </div>
          <div className="mt-5">
            <BarList
              label={group.label}
              bars={group.figures.map((f) => ({
                label: withYear(f.company, f.year),
                value: f.value,
                display: formatFigure(f.value),
                highlight: f.company === company,
                note: (
                  <>
                    <CiteChips refs={f.refs} small />
                    {f.estimate && <EstimateTag />}
                  </>
                ),
              }))}
            />
          </div>
        </Card>
      ))}
      {singles.length > 0 && (
        <Card className="print-avoid-break">
          <CardTitle title="Key figures" note={`Each number is quoted from a verified source${singles.some((f) => f.estimate) ? "; estimates are marked" : ""}`}
          />
          <ul className="mt-5 grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
            {singles.map((f) => (
              <li key={`${f.company}|${f.label}`} className="rounded-2xl bg-surface-2 p-5">
                <p className="text-[13px] text-ink-faint">{withYear(`${f.company} · ${f.label}`, f.year)}</p>
                <p className="mt-1 text-[28px] font-bold tracking-tight tabular-nums">
                  {formatFigure(f.value)}
                  <CiteChips refs={f.refs} small />
                </p>
                <p className="text-[13px] text-ink-faint">{f.unit}</p>
                {f.estimate && (
                  <p className="-ml-2 mt-1.5">
                    <EstimateTag />
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

/** "Market size" + 2025 → "Market size (2025)"; no second year when the label already names it. */
export function withYear(text: string, year: number | null): string {
  return year && !text.includes(String(year)) ? `${text} (${year})` : text;
}
