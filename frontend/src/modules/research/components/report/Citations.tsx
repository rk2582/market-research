"use client";

import { Pill } from "@/components/ui/Pill";
import { VERDICT_SHORT, VERDICT_TONE } from "../../lib/reportModel";
import type { ReportClaim } from "../../types";
import { useReport } from "./ReportContext";

/** Source numbers after a statement; each opens the source panel. */
export function CiteChips({ refs, small = false }: { refs: number[]; small?: boolean }) {
  const { openSource } = useReport();
  if (refs.length === 0) return null;
  return (
    <span className="whitespace-nowrap">
      {refs.map((ref) => (
        <button
          key={ref}
          type="button"
          onClick={() => openSource(ref)}
          aria-label={`Source ${ref}`}
          className={`ml-1 rounded-md bg-accent-tint align-[2px] font-semibold text-accent-ink hover:brightness-95 print:bg-transparent print:px-0 ${
            small ? "px-1.5 text-[10px]" : "px-1.5 py-px text-[11px]"
          }`}
        >
          {ref}
        </button>
      ))}
    </span>
  );
}

/** Prose with "[3][7]" markers (from the backend) shown as clickable source numbers. */
export function CitedText({ text }: { text: string }) {
  const parts: Array<string | number[]> = [];
  let last = 0;
  for (const match of text.matchAll(/(?:\[\d+\])+/g)) {
    const index = match.index ?? 0;
    parts.push(text.slice(last, index).replace(/\s+$/, ""));
    parts.push([...match[0].matchAll(/\d+/g)].map((m) => Number(m[0])));
    last = index + match[0].length;
  }
  parts.push(text.slice(last));
  return (
    <>
      {parts.map((part, i) => (typeof part === "string" ? <span key={i}>{part}</span> : <CiteChips key={i} refs={part} />))}
    </>
  );
}

/** One researched statement: text, source numbers, and a label when it is not fully verified. */
export function ClaimLine({ claim }: { claim: ReportClaim }) {
  return (
    <span className="leading-relaxed">
      {claim.text}
      <CiteChips refs={claim.refs} />
      {claim.verdict !== "supported" && (
        <Pill tone={VERDICT_TONE[claim.verdict]} className="ml-2 align-[1px]">
          {VERDICT_SHORT[claim.verdict]}
        </Pill>
      )}
      {claim.estimate && <EstimateTag numeric={/\d/.test(claim.text)} />}
      {claim.old_source_year && (
        <span title={`The only dated source is from ${claim.old_source_year} — this may no longer be true.`}>
          <Pill tone="partial" className="ml-2 align-[1px]">
            Old source ({claim.old_source_year})
          </Pill>
        </span>
      )}
    </span>
  );
}

/** Marks something that rests on a market-research firm's summary page: for a number, one firm's estimate. */
export function EstimateTag({ numeric = true }: { numeric?: boolean }) {
  return (
    <span title="From a market-research firm's summary page — one firm's view, not an official figure.">
      <Pill tone="predict" className="ml-2 align-[1px]">
        {numeric ? "Estimate · research firm" : "Source: research firm"}
      </Pill>
    </span>
  );
}

/** Claims filtered by the "show only verified" switch. */
export function useVisibleClaims(claims: ReportClaim[]): ReportClaim[] {
  const { verifiedOnly } = useReport();
  return verifiedOnly ? claims.filter((c) => c.verdict === "supported") : claims;
}
