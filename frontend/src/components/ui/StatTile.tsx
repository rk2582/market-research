/** One headline number: small label, big value, short note. */
export function StatTile({ label, value, note, align = "left" }: { label: string; value: string; note?: string; align?: "left" | "center" }) {
  return (
    <div className={`animate-rise rounded-card bg-surface px-6 py-6 shadow-card print:border print:border-rule ${align === "center" ? "text-center" : ""}`}>
      <p className="text-[13px] text-ink-faint">{label}</p>
      <p className="mt-1.5 text-[40px] font-bold leading-none tracking-tight tabular-nums sm:text-[44px]">{value}</p>
      {note && <p className="mt-2 text-[13px] leading-snug text-ink-faint">{note}</p>}
    </div>
  );
}
