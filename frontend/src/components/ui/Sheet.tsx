"use client";

import { type ReactNode, useEffect, useRef } from "react";

/**
 * A modal sheet: centred card on larger screens, slides up from the bottom on a phone.
 * Closes with Escape or a click outside; focus moves into it and back afterwards.
 */
export function Sheet({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previous?.focus?.();
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6 print:hidden">
      <button type="button" aria-label="Close" tabIndex={-1} onClick={onClose} className="absolute inset-0 cursor-default bg-black/35" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
        className="animate-rise relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-[28px] bg-surface shadow-float focus:outline-none sm:max-w-[640px] sm:rounded-[28px]"
      >
        <div className="overflow-y-auto px-6 pb-4 pt-7 sm:px-8">{children}</div>
        {footer && <div className="border-t border-rule px-6 py-4 sm:px-8">{footer}</div>}
      </div>
    </div>
  );
}
