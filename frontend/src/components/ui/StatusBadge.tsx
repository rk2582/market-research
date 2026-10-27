import { STATUS_LABEL } from "@/modules/research/lib/format";
import type { RunStatus } from "@/modules/research/types";
import { Pill } from "./Pill";

const TONE = { running: "info", succeeded: "verified", partial: "partial", failed: "removed" } as const;

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <Pill tone={TONE[status]}>
      {status === "running" && <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {STATUS_LABEL[status]}
    </Pill>
  );
}
