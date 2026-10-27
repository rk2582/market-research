"use client";

import { type FormEvent, useState } from "react";
import { Spinner } from "@/components/ui/Spinner";
import { checkQuery } from "../lib/validateQuery";

/**
 * The big search box. Checks the input with the same rules as the backend, then calls `onSubmit`.
 * `onSubmit` may throw an Error whose message is shown under the box (e.g. the backend's 422 text).
 * The value is controlled by the parent so example chips can fill it in.
 */
export function NewResearchForm({
  value,
  onChange,
  onSubmit,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const check = checkQuery(value);
    if (!check.ok) {
      setError(check.message);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await onSubmit(check.query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the research. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mx-auto max-w-[680px]">
      <label htmlFor="research-query" className="sr-only">
        Company name or website
      </label>
      <div
        className={`flex items-center gap-3 rounded-full border bg-surface py-2 pl-6 pr-2 shadow-float transition ${
          error ? "border-removed" : "border-black/5 focus-within:border-accent dark:border-white/10"
        }`}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" className="flex-none text-ink-faint">
          <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          id="research-query"
          name="query"
          type="text"
          autoComplete="off"
          placeholder="Company name or website"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            if (error) setError(null);
          }}
          maxLength={400}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "research-query-error" : "research-query-help"}
          className="min-w-0 flex-1 bg-transparent py-3 text-[19px] text-ink placeholder:text-ink-faint focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="inline-flex min-h-12 items-center gap-2 whitespace-nowrap rounded-full bg-accent px-6 text-[17px] font-medium text-on-accent hover:brightness-110 disabled:opacity-60 sm:px-7"
        >
          {busy && <Spinner label="Starting research" />}
          {busy ? "Starting…" : "Research"}
        </button>
      </div>
      {error ? (
        <p id="research-query-error" role="alert" className="mt-3 text-[15px] text-removed-ink">
          {error}
        </p>
      ) : (
        <p id="research-query-help" className="mt-3 text-[13px] text-ink-faint">
          Takes about a minute. Every fact in the report links to the page it came from.
        </p>
      )}
    </form>
  );
}
