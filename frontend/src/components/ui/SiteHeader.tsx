import Link from "next/link";

/** Frosted header that stays at the top. */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-black/[0.08] bg-paper/80 backdrop-blur-xl backdrop-saturate-150 dark:border-white/10 print:hidden">
      <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between gap-4 px-6">
        <Link href="/" className="flex items-center gap-2.5 text-[17px] font-semibold tracking-tight text-ink">
          <LogoMark />
          Market360
        </Link>
        <nav aria-label="Main" className="flex items-center gap-6 text-sm">
          <Link href="/#recent" className="hidden text-ink-soft hover:text-ink sm:inline">
            History
          </Link>
          <Link href="/#how" className="hidden text-ink-soft hover:text-ink sm:inline">
            How it works
          </Link>
          <Link href="/#start" className="rounded-full bg-accent px-4 py-2 font-medium text-on-accent hover:brightness-110">
            New research
          </Link>
        </nav>
      </div>
    </header>
  );
}

export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true" className="flex-none">
      <rect width="26" height="26" rx="7" className="fill-ink" />
      <path
        d="M7 17.5V8.5l6 5 6-5v9"
        fill="none"
        className="stroke-paper"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
