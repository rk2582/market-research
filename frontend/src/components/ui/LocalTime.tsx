"use client";

import { useEffect, useState } from "react";
import { formatDateTime } from "@/modules/research/lib/format";

/**
 * A date in the reader's own time zone, without hydration errors: the server and the first
 * browser render both show UTC (identical text); right after loading, the browser switches to
 * local time.
 */
export function LocalTime({ iso, className }: { iso: string; className?: string }) {
  const [text, setText] = useState(() => `${formatDateTime(iso, "UTC")} UTC`);
  useEffect(() => {
    setText(formatDateTime(iso));
  }, [iso]);
  return (
    <time dateTime={iso} className={className}>
      {text}
    </time>
  );
}
