"use client";

import { type ReactNode, useEffect, useRef } from "react";

/**
 * A panel that slides in from the right (source details, competitor profile).
 * Closes with the × button, a click outside, or Escape; focus moves into it and back afterwards.
 */
export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => previous?.focus?.();
  }, []);

  return (
    <div className="fixed inset-0 z-40 flex justify-end print:hidden">
      <button type="button" aria-label="Close panel" tabIndex={-1} onClick={onClose} className="absolute inset-0 cursor-default bg-black/30" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
        className="animate-slide-in relative h-full w-full max-w-[480px] overflow-y-auto bg-surface p-7 shadow-float"
      >
        <div className="flex justify-end">
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-rule-soft text-lg text-ink-soft hover:text-ink"
          >
            ×
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}
