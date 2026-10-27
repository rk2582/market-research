import { verifiedPct } from "../../../lib/reportModel";
import type { ValidationSummary } from "../../../types";

const R = 60;
const C = 2 * Math.PI * R;

/** Donut of fact-check verdicts with the verified share in the middle, plus a legend with counts. */
export function EvidenceDonut({ validation }: { validation: ValidationSummary }) {
  const total = validation.claims_total;
  const segments = [
    { label: "Verified", count: validation.supported, color: "var(--color-verified)" },
    { label: "Partly verified", count: validation.partially_supported, color: "var(--color-partial)" },
    { label: "Unconfirmed", count: validation.unsupported, color: "var(--color-unconfirmed)" },
    { label: "Removed", count: validation.contradicted, color: "var(--color-removed)" },
  ];
  let offset = 0;
  const arcs = segments.map((s) => {
    const length = total ? (C * s.count) / total : 0;
    const arc = { ...s, dash: `${length} ${C}`, offset: -offset };
    offset += length;
    return arc;
  });
  const summary = segments.map((s) => `${s.count} ${s.label.toLowerCase()}`).join(", ");

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg width="150" height="150" viewBox="0 0 150 150" role="img" aria-label={`${verifiedPct(validation)}% of ${total} claims verified: ${summary}`}>
        <circle cx="75" cy="75" r={R} fill="none" stroke="var(--color-rule-soft)" strokeWidth="16" />
        {arcs.map(
          (a) =>
            a.count > 0 && (
              <circle
                key={a.label}
                cx="75"
                cy="75"
                r={R}
                fill="none"
                stroke={a.color}
                strokeWidth="16"
                strokeDasharray={a.dash}
                strokeDashoffset={a.offset}
                transform="rotate(-90 75 75)"
              />
            ),
        )}
        <text x="75" y="78" textAnchor="middle" fontSize="30" fontWeight="700" fill="var(--color-ink)">
          {verifiedPct(validation)}%
        </text>
        <text x="75" y="98" textAnchor="middle" fontSize="11" fill="var(--color-ink-faint)">
          verified
        </text>
      </svg>
      <ul className="min-w-[10rem] flex-1 space-y-2.5 text-[15px]">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            {s.label}
            <b className="ml-auto pl-3 tabular-nums">{s.count}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}
