export function Spinner({ label = "Loading", className = "" }: { label?: string; className?: string }) {
  return (
    <span role="status" aria-label={label} className={`inline-block ${className}`}>
      <span aria-hidden="true" className="block h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current" />
    </span>
  );
}
