/** Shown where a section could not be produced (a step did not finish): it says so instead of vanishing. */
export function Unavailable({ what = "This section" }: { what?: string }) {
  return (
    <p className="mt-4 rounded-2xl bg-surface-2 px-4 py-3 text-[15px] text-ink-faint">
      {what} is not available in this report: the step that writes it did not finish.
    </p>
  );
}
