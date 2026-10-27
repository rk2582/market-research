/** An on/off switch (a real button with role="switch"). */
export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex min-h-11 items-center gap-3 rounded-full px-1 text-[15px] text-ink"
    >
      <span
        aria-hidden="true"
        className={`relative h-[26px] w-11 flex-none rounded-full transition-colors ${checked ? "bg-verified" : "bg-unconfirmed"}`}
      >
        <span
          className={`absolute top-[2px] h-[22px] w-[22px] rounded-full bg-white shadow transition-[left] ${checked ? "left-[20px]" : "left-[2px]"}`}
        />
      </span>
      {label}
    </button>
  );
}
