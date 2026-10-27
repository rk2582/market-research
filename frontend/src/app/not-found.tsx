import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[680px] px-6 py-28 text-center">
      <h1 className="text-[40px] font-bold tracking-tight">Page not found</h1>
      <p className="mt-3 text-[19px] text-ink-faint">
        This page or research does not exist, or it was deleted. Check the link, or start a new research.
      </p>
      <Link
        href="/"
        className="mt-8 inline-flex min-h-11 items-center rounded-full bg-accent px-6 text-[17px] font-medium text-on-accent hover:brightness-110"
      >
        Start a new research
      </Link>
    </div>
  );
}
