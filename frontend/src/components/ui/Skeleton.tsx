/** Grey placeholder lines while content loads. */
export function Skeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={`space-y-3 rounded-card bg-surface p-6 shadow-card ${className}`} data-testid="skeleton">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3.5 animate-pulse rounded-full bg-rule" style={{ width: `${100 - i * 12}%` }} />
      ))}
    </div>
  );
}
