"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Monogram } from "@/components/ui/Monogram";
import { Sheet } from "@/components/ui/Sheet";
import { Spinner } from "@/components/ui/Spinner";
import { identify, startResearch } from "../api/research-api";
import { domainOf } from "../lib/format";
import { checkQuery } from "../lib/validateQuery";
import {
  type CompanyChoice,
  type ConfirmedCompetitor,
  type IdentifyResult,
  MAX_COMPETITORS,
  type ResearchRunSummary,
} from "../types";

interface Pick extends ConfirmedCompetitor {
  reason?: string;
  competesIn?: string;
  weak?: boolean;
}

interface Scope {
  product: string;
  region: string;
  customers: string;
}

type Phase = { name: "checking" } | { name: "failed"; message: string } | { name: "ready"; result: IdentifyResult };

const message = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

/**
 * The confirm step (M12). Asks the backend which company (or market) the query means, then lets the
 * user pick the right match and edit the competitor list before the full research starts.
 */
export function ConfirmSheet({
  query,
  onClose,
  onStarted,
}: {
  query: string;
  onClose: () => void;
  onStarted: (run: ResearchRunSummary) => void;
}) {
  const [phase, setPhase] = useState<Phase>({ name: "checking" });
  const [view, setView] = useState<"company" | "market">("company");
  const [matchIndex, setMatchIndex] = useState(0);
  const [competitors, setCompetitors] = useState<Pick[]>([]);
  const [scope, setScope] = useState<Scope>({
    product: query,
    region: "",
    customers: "",
  });
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    identify(query)
      .then((result) => {
        if (!active) return;
        setView(result.kind);
        setScope({
          product: result.market?.product ?? result.query,
          region: result.market?.region ?? "",
          customers: result.market?.customer_type ?? "",
        });
        setCompetitors(
          result.competitors.map((c) => ({
            name: c.name,
            website: c.website,
            reason: c.reason,
            competesIn: c.competes_in,
            weak: c.weak_evidence,
            added_by_user: false,
          })),
        );
        setPhase({ name: "ready", result });
      })
      .catch((err: unknown) => {
        if (active)
          setPhase({
            name: "failed",
            message: message(err, "The quick check failed."),
          });
      });
    return () => {
      active = false;
    };
  }, [query]);

  async function start(confirmed: boolean) {
    setStarting(true);
    setStartError(null);
    try {
      const match = phase.name === "ready" ? phase.result.matches[matchIndex] : undefined;
      const run = confirmed
        ? await startResearch(query, {
            company: match ? { name: match.name, website: match.website } : undefined,
            competitors: competitors.map(({ name, website, added_by_user }) => ({
              name,
              website,
              added_by_user,
            })),
          })
        : await startResearch(query);
      onStarted(run);
    } catch (err) {
      setStartError(message(err, "Could not start the research. Please try again."));
      setStarting(false);
    }
  }

  async function startMarket() {
    const product = scope.product.trim();
    const region = scope.region.trim();
    if (product.length < 2 || region.length < 2) {
      setScopeError(
        product.length < 2 ? "Enter the product or idea." : "Enter a region (a country, state or city, or “Global”).",
      );
      return;
    }
    setScopeError(null);
    setStarting(true);
    setStartError(null);
    try {
      const customer = scope.customers.trim();
      onStarted(
        await startResearch(query, {
          mode: "market",
          market: { product, region, customer_type: customer || null },
        }),
      );
    } catch (err) {
      setStartError(message(err, "Could not start the research. Please try again."));
      setStarting(false);
    }
  }

  if (phase.name === "checking") {
    return (
      <Sheet title="Checking your search" onClose={onClose}>
        <div className="flex flex-col items-center py-10 text-center" aria-live="polite">
          <Spinner label="Checking" className="h-8 w-8" />
          <p className="mt-5 text-[21px] font-semibold tracking-tight">Checking “{query}”…</p>
          <p className="mt-2 text-[15px] text-ink-faint">
            Finding the company and its main competitors. A few seconds.
          </p>
          <button
            type="button"
            onClick={onClose}
            className="mt-6 min-h-11 rounded-full px-5 text-[15px] text-accent-ink hover:underline"
          >
            Cancel
          </button>
        </div>
      </Sheet>
    );
  }

  const footer = (primary: ReactNode) => (
    <div>
      {startError && (
        <p role="alert" className="mb-3 text-[15px] text-removed-ink">
          {startError}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <button
          type="button"
          onClick={onClose}
          className="min-h-11 rounded-full bg-rule px-5 text-[15px] text-ink hover:bg-unconfirmed-tint"
        >
          Back
        </button>
        {primary}
      </div>
    </div>
  );

  const primaryClass =
    "inline-flex min-h-11 items-center gap-2 rounded-full bg-accent px-6 text-[15px] font-medium text-on-accent hover:brightness-110 disabled:opacity-60";

  if (phase.name === "failed") {
    return (
      <Sheet
        title="Quick check unavailable"
        onClose={onClose}
        footer={footer(
          <button type="button" disabled={starting} onClick={() => start(false)} className={primaryClass}>
            {starting && <Spinner label="Starting research" />}
            Start without confirming
          </button>,
        )}
      >
        <h2 className="text-[24px] font-bold tracking-tight">We couldn’t check “{query}”</h2>
        <p className="mt-3 text-[17px] text-ink-soft">{phase.message}</p>
        <p className="mt-3 text-[15px] text-ink-faint">
          You can still start: the research will identify the company and choose competitors on its own.
        </p>
      </Sheet>
    );
  }

  const { result } = phase;

  if (view === "market") {
    return (
      <Sheet
        title="Market research"
        onClose={onClose}
        footer={footer(
          <button type="button" disabled={starting} onClick={startMarket} className={primaryClass}>
            {starting && <Spinner label="Starting research" />}
            Start market research
          </button>,
        )}
      >
        <MarketView
          result={result}
          scope={scope}
          error={scopeError}
          onScope={(next) => {
            setScope(next);
            setScopeError(null);
          }}
          onPickCompany={(i) => {
            setMatchIndex(i);
            setCompetitors([]);
            setView("company");
          }}
          onIsCompany={() => setView("company")}
        />
      </Sheet>
    );
  }

  const match = result.matches[matchIndex];
  return (
    <Sheet
      title="Confirm company and competitors"
      onClose={onClose}
      footer={footer(
        <button type="button" disabled={starting} onClick={() => start(true)} className={primaryClass}>
          {starting && <Spinner label="Starting research" />}
          Start research
        </button>,
      )}
    >
      <h2 className="text-[24px] font-bold tracking-tight">
        {match ? "Is this the right company?" : `We couldn’t confirm “${query}”`}
      </h2>
      {result.note && <p className="mt-1.5 text-[15px] text-ink-faint">{result.note}</p>}

      {match ? (
        <fieldset className="mt-5 space-y-2.5">
          <legend className="sr-only">Company</legend>
          {result.matches.map((m, i) => (
            <MatchOption
              key={`${m.name}-${i}`}
              match={m}
              checked={i === matchIndex}
              onSelect={() => setMatchIndex(i)}
            />
          ))}
        </fieldset>
      ) : (
        <p className="mt-4 rounded-2xl bg-surface-2 px-4 py-3 text-[15px] text-ink-soft">
          Nothing on the web clearly matched. Check the spelling or search for the website instead — or start anyway and
          the research will try to identify it.
        </p>
      )}

      {match && (result.product_lines?.length ?? 0) > 0 && <ProductLines lines={result.product_lines ?? []} />}

      <CompetitorEditor competitors={competitors} onChange={setCompetitors} />

      <button
        type="button"
        onClick={() => setView("market")}
        className="mt-6 text-[13px] text-accent-ink hover:underline"
      >
        This is a product or market, not a company
      </button>
    </Sheet>
  );
}

function MatchOption({ match, checked, onSelect }: { match: CompanyChoice; checked: boolean; onSelect: () => void }) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3.5 rounded-2xl border p-4 transition ${
        checked ? "border-accent bg-accent-tint/50" : "border-rule hover:border-ink-faint"
      }`}
    >
      <input
        type="radio"
        name="company"
        checked={checked}
        onChange={onSelect}
        className="mt-1 h-4 w-4 accent-[var(--color-accent)]"
      />
      <Monogram name={match.name} />
      <span className="min-w-0 flex-1">
        <span className="block text-[17px] font-semibold">{match.name}</span>
        {match.website && <span className="block text-[13px] text-ink-faint">{domainOf(match.website)}</span>}
        <span className="mt-1 block text-[15px] leading-snug text-ink-soft">{match.description}</span>
        <a
          href={match.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-1 inline-block text-[13px] text-accent-ink hover:underline"
        >
          Source ↗
        </a>
      </span>
    </label>
  );
}

function ProductLines({ lines }: { lines: { name: string; brands: string[] }[] }) {
  return (
    <section aria-labelledby="lines-title" className="mt-6">
      <h3 id="lines-title" className="text-[13px] font-semibold text-ink-faint">
        Main product lines — competitors are suggested for each
      </h3>
      <ul className="mt-2 flex flex-wrap gap-2">
        {lines.map((line) => (
          <li key={line.name} className="rounded-full bg-surface-2 px-3 py-1.5 text-[13px]">
            <span className="font-medium">{line.name}</span>
            {line.brands.length > 0 && <span className="text-ink-faint"> · {line.brands.join(", ")}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function CompetitorEditor({ competitors, onChange }: { competitors: Pick[]; onChange: (next: Pick[]) => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const full = competitors.length >= MAX_COMPETITORS;

  function add(event: FormEvent) {
    event.preventDefault();
    const check = checkQuery(value);
    if (!check.ok) {
      setError(check.message);
      return;
    }
    const website =
      check.kind === "url" ? (/^https?:\/\//i.test(check.query) ? check.query : `https://${check.query}`) : null;
    const name = website ? domainOf(website) : check.query;
    const key = name.toLowerCase();
    const existing = competitors.find(
      (c) => c.name.toLowerCase() === key || (website && c.website && domainOf(c.website) === domainOf(website)),
    );
    if (existing) {
      setError(`${existing.name} is already on the list.`);
      return;
    }
    onChange([...competitors, { name, website, added_by_user: true }]);
    setValue("");
    setError(null);
  }

  return (
    <section aria-labelledby="competitors-title" className="mt-7">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="competitors-title" className="text-[17px] font-semibold">
          Competitors to research
        </h3>
        <span className="text-[13px] text-ink-faint">
          {competitors.length} of {MAX_COMPETITORS}
        </span>
      </div>
      {competitors.length === 0 ? (
        <p className="mt-2 text-[15px] text-ink-faint">None yet. Add some, or start and the research will choose.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {competitors.map((c) => (
            <li key={c.name} className="flex items-center gap-3 rounded-2xl bg-surface-2 px-4 py-2.5">
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium">
                  {c.name}
                  {c.website && c.website.length > 0 && domainOf(c.website) !== c.name && (
                    <span className="ml-2 text-[13px] font-normal text-ink-faint">{domainOf(c.website)}</span>
                  )}
                </span>
                <span className="block text-[13px] text-ink-faint">
                  {c.added_by_user ? "Added by you" : [c.competesIn, c.reason].filter(Boolean).join(" · ")}
                </span>
                {c.weak && (
                  <span className="mt-1 inline-block rounded-full bg-partial-tint px-2 py-0.5 text-[11px] font-semibold text-partial-ink">
                    Weak evidence: only on a company-database list
                  </span>
                )}
              </span>
              <button
                type="button"
                aria-label={`Remove ${c.name}`}
                onClick={() => onChange(competitors.filter((x) => x !== c))}
                className="flex h-8 w-8 flex-none items-center justify-center rounded-full text-lg text-ink-faint hover:bg-rule hover:text-ink"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} noValidate className="mt-3 flex gap-2">
        <label htmlFor="add-competitor" className="sr-only">
          Add a competitor (name or website)
        </label>
        <input
          id="add-competitor"
          value={value}
          disabled={full}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          placeholder={full ? `Up to ${MAX_COMPETITORS} competitors` : "Add a competitor (name or website)"}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "add-competitor-error" : undefined}
          className="min-h-11 min-w-0 flex-1 rounded-full border border-rule bg-surface px-4 text-[15px] placeholder:text-ink-faint focus:border-accent focus:outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={full}
          className="min-h-11 rounded-full bg-rule px-5 text-[15px] text-ink hover:bg-unconfirmed-tint disabled:opacity-60"
        >
          Add
        </button>
      </form>
      {error && (
        <p id="add-competitor-error" role="alert" className="mt-2 text-[13px] text-removed-ink">
          {error}
        </p>
      )}
    </section>
  );
}

function MarketView({
  result,
  scope,
  error,
  onScope,
  onPickCompany,
  onIsCompany,
}: {
  result: IdentifyResult;
  scope: Scope;
  error: string | null;
  onScope: (next: Scope) => void;
  onPickCompany: (index: number) => void;
  onIsCompany: () => void;
}) {
  const field =
    "mt-1 min-h-11 w-full rounded-xl border border-rule bg-surface px-4 text-[15px] placeholder:text-ink-faint focus:border-accent focus:outline-none aria-[invalid=true]:border-removed";

  return (
    <div>
      <h2 className="text-[24px] font-bold tracking-tight">This looks like a market, not a company</h2>
      <p className="mt-1.5 text-[15px] text-ink-faint">
        {result.note || `“${result.query}” reads as a product or business idea.`}
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <label className="text-[13px] text-ink-faint">
          Product or idea
          <input
            value={scope.product}
            onChange={(e) => onScope({ ...scope, product: e.target.value })}
            aria-invalid={error && scope.product.trim().length < 2 ? true : undefined}
            className={field}
          />
        </label>
        <label className="text-[13px] text-ink-faint">
          Region
          <input
            value={scope.region}
            onChange={(e) => onScope({ ...scope, region: e.target.value })}
            placeholder="e.g. Kerala, or Global"
            aria-invalid={error && scope.region.trim().length < 2 ? true : undefined}
            className={field}
          />
        </label>
        <label className="text-[13px] text-ink-faint">
          Customers (optional)
          <input
            value={scope.customers}
            onChange={(e) => onScope({ ...scope, customers: e.target.value })}
            placeholder="e.g. households"
            className={field}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-[15px] text-removed-ink">
          {error}
        </p>
      )}
      <p role="note" className="mt-5 rounded-2xl bg-info-tint px-4 py-3 text-[15px] text-info-ink">
        You’ll get a market-entry report: market size and growth, the main players, prices, rules, risks, signals for
        and against, entry options and what to check before investing. It is evidence to help you decide — not
        investment advice.
      </p>
      {result.matches.length > 0 && (
        <div className="mt-6">
          <h3 className="text-[17px] font-semibold">Did you mean a company?</h3>
          <ul className="mt-3 space-y-2">
            {result.matches.map((m, i) => (
              <li key={`${m.name}-${i}`}>
                <button
                  type="button"
                  onClick={() => onPickCompany(i)}
                  className="flex w-full items-center gap-3 rounded-2xl bg-surface-2 px-4 py-3 text-left hover:bg-rule"
                >
                  <Monogram name={m.name} onMuted />
                  <span className="min-w-0">
                    <span className="block text-[15px] font-semibold">Research {m.name}</span>
                    <span className="block text-[13px] text-ink-faint">{m.description}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <button type="button" onClick={onIsCompany} className="mt-6 text-[13px] text-accent-ink hover:underline">
        This is a company
      </button>
    </div>
  );
}
