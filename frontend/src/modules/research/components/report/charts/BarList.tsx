import type { ReactNode } from "react";

export interface Bar {
  label: string;
  value: number;
  display: string; // text next to the bar, e.g. "$10" or "23.5 s"
  highlight?: boolean; // the target company: accent colour, bold
  note?: ReactNode; // after the value: source numbers, a verdict …
}

/** Horizontal bar chart drawn with plain HTML (prints well, follows the theme). */
export function BarList({ bars, label }: { bars: Bar[]; label: string }) {
  const max = Math.max(...bars.map((b) => b.value), 0);
  return (
    <ul aria-label={label} className="space-y-3.5">
      {bars.map((bar) => (
        <li key={bar.label} className="grid grid-cols-[minmax(5rem,9rem)_minmax(0,1fr)] items-center gap-4 text-[15px]">
          <span className={`truncate ${bar.highlight ? "font-bold" : ""}`}>{bar.label}</span>
          <span className="flex min-w-0 items-center gap-3">
            <span
              aria-hidden="true"
              className={`h-6 min-w-1 rounded-lg ${bar.highlight ? "bg-accent" : "bg-bar"}`}
              style={{ width: `${max ? Math.max((bar.value / max) * 75, 2) : 0}%` }}
            />
            <b className="whitespace-nowrap tabular-nums">{bar.display}</b>
            {bar.note}
          </span>
        </li>
      ))}
    </ul>
  );
}
