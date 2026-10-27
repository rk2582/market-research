import type { ReactNode } from "react";

export type PillTone = "neutral" | "accent" | "info" | "verified" | "partial" | "unconfirmed" | "removed" | "predict";

const TONES: Record<PillTone, string> = {
  neutral: "bg-rule-soft text-ink-soft",
  accent: "bg-accent-tint text-accent-ink",
  info: "bg-info-tint text-info-ink",
  verified: "bg-verified-tint text-verified-ink",
  partial: "bg-partial-tint text-partial-ink",
  unconfirmed: "bg-unconfirmed-tint text-unconfirmed-ink",
  removed: "bg-removed-tint text-removed-ink",
  predict: "bg-predict-tint text-predict-ink",
};

/** A small rounded label: status, verdict, insight kind, impact. */
export function Pill({ tone = "neutral", children, className = "" }: { tone?: PillTone; children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
