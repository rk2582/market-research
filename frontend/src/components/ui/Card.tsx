import type { HTMLAttributes, ReactNode } from "react";

/** White rounded panel — the basic building block of every screen. */
export function Card({
  as: Tag = "section",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" | "aside" | "li"; children: ReactNode }) {
  return (
    <Tag className={`rounded-card bg-surface p-6 shadow-card sm:p-7 print:border print:border-rule print:shadow-none ${className}`} {...props}>
      {children}
    </Tag>
  );
}

/** Card heading with an optional one-line description under it. */
export function CardTitle({ title, note, id }: { title: string; note?: ReactNode; id?: string }) {
  return (
    <div className="print-keep-next">
      <h2 id={id} className="text-[19px] font-semibold tracking-tight">
        {title}
      </h2>
      {note && <p className="mt-1 text-[13px] text-ink-faint">{note}</p>}
    </div>
  );
}
