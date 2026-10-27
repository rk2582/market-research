import { Button } from "./Button";

/** Says what went wrong and what to do next. */
export function ErrorState({
  title,
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div role="alert" className="flex gap-4 rounded-card bg-surface p-6 shadow-card">
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-full bg-removed-tint text-sm font-bold text-removed-ink"
      >
        !
      </span>
      <div>
        <p className="text-[17px] font-semibold">{title}</p>
        <p className="mt-1 text-[15px] leading-relaxed text-ink-soft">{message}</p>
        {onRetry && (
          <Button variant="secondary" className="mt-4" onClick={onRetry}>
            {retryLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
