# M12 — Confirm company and competitors before research

**Date:** 2026-10-26 · **Status:** Draft for approval · **Roadmap:** Phase 2, milestone 2

## Problem

Today the Researcher picks the company and its competitors on its own, inside the full run. When it guesses
wrong you only find out a minute later, in the report. Seen in the POC benchmark: Notion got "Craft Agents" and
Reflect, Canva got Stability AI. An ambiguous name (e.g. "Mercury": a bank, a car brand, a mail app) can match the
wrong company entirely. And a product or market name ("Milk") gets researched as some company that happens to
use the word (Milk Makeup, Milk Bar) — a confident report about the wrong thing.

## What you get

1. You type a company and click **Research**. Within a few seconds a **confirm sheet** appears:
   - **The company we matched**: name, website, one-line description, the page it came from.
     If the name could mean several companies, up to 3 choices to pick from ("Not this one?").
   - **Suggested competitors** (3–5), each with name, website and one short reason ("UK digital bank, same
     customers"). Remove any with ×, add your own by name or website (up to 6 in total).
2. **Start research** runs the full workflow on exactly that company and that list. **Back** returns to the search.
3. The report shows "Competitors confirmed by you" so readers know the list was chosen, not guessed.
4. If the quick check fails (Tavily or OpenAI down), the sheet says so and offers **Start without confirming**
   (today's behaviour).
5. **Company or market?** If what you typed is a product or market rather than a company ("Milk", "electric
   scooters in India"), the sheet says so and asks for the **product, region and customer type** (e.g. "fresh
   packaged milk · Kerala · households"). In M12 this scope is saved and the sheet explains that market-entry
   reports arrive in **M13**; if some companies also match the word, you can still pick one of those instead.

## How it works

| Part | Change |
|---|---|
| **New agent: Identifier** | Small and fast (gpt-4.1-mini, at most 3 web searches, 30 s timeout). Returns `kind` (`company` or `market`), 1–3 company matches and 3–6 suggested competitors — or, for a market, a suggested product, region and customer type. Each item comes with the URL it came from. Same evidence rule as the Researcher: only URLs it actually retrieved count; code drops the rest. |
| **New endpoint** | `POST /api/v1/research/identify` `{query}` → `{kind, candidates, competitors, market_scope}`. Runs directly (no background job): a few seconds. |
| **Start endpoint** | `POST /api/v1/research` accepts optional `company` `{name, website}` and `competitors` `[{name, website?}]`. Without them it works exactly as today (the benchmark script and old clients keep working). |
| **Researcher** (researcher@7) | When a list is given: research exactly this company and these competitors; no swaps, no additions. Code also enforces it: a competitor not on the list is dropped; one the Researcher couldn't profile is shown as "not enough public information" with the reason. |
| **Database** (one Alembic migration) | New table `companies` (name, website domain, first/last researched) — one row per company, reused across runs; `research_runs.company_id`. New table `run_competitors` (run, name, website, position, `suggested` or `added_by_user`). `research_runs.mode` (`company` now, `market` from M13) and `research_runs.scope` (product, region, customer type). These are what M13 and Phase 3 need. |
| **Frontend** | Confirm sheet on Home (Apple-style bottom sheet / side panel), chip list with remove and add, keyboard friendly; report header shows "Competitors confirmed by you". |

## Decisions (my choices; tell me if you disagree)

| # | Decision | Choice and why |
|---|---|---|
| D17 | Show the confirm sheet always, or only when unsure? | **Always.** Reviewing competitors is the point, and with a good match it's one click ("Start research"). |
| D18 | Separate Identifier agent, or a first step inside the workflow? | **Separate agent with its own endpoint.** The workflow then starts with a fixed list; no pausing a background run to wait for the user. |
| D19 | A competitor added by name only | The Researcher finds its website during research; it's not required in the sheet. |
| D21 | Company vs market | The Identifier decides, and you can switch it on the sheet ("This is a company" / "This is a market"). |
| D20 | Limits | 1–6 competitors; the Identifier counts against nothing (it's short), but has a 30 s timeout and 3 tool calls max. |

## Cost and time

About **5–10 s and 2–3 Tavily credits** extra per research (the Identifier's searches), plus a few thousand tokens on
gpt-4.1-mini. The full run can get slightly cheaper, because the Researcher no longer searches for competitors.

## Steps

1. Schemas + Identifier agent (instructions, output schema incl. company/market, evidence check in code) + tests with fakes.
2. `POST /identify` endpoint + service + tests (match, ambiguous name, URL input, failure).
3. Migration: `companies`, `run_competitors`, `research_runs.company_id`; repositories; PostgreSQL integration test.
4. Start endpoint accepts the confirmed list; Researcher prompt (researcher@7) + code filter; tests.
5. Frontend confirm sheet (pick match, remove/add competitors, start, back, failure fallback; market scope fields
   and the "coming in M13" note) + tests.
6. Report header note; README, CLAUDE.md; live check on 3 companies (one ambiguous, e.g. "Mercury") and on "Milk"; commit, zip.

## Done when

- "Mercury" shows several matches and the one you pick is the one researched.
- Notion with your edited list (e.g. Airtable, Coda, ClickUp, Confluence) produces a report with exactly those four.
- "Milk" is recognised as a market (not Milk Makeup) and its product/region/customer scope can be confirmed.
- Without a list, everything works as before (benchmark script unchanged).
- Extra time under 15 s and extra Tavily use at most 3 credits per research.
- All tests, type check and build pass; migration applies cleanly on PostgreSQL.

**Effort:** about 4–5 days. You verify by running four searches in the app (one ambiguous, one with an edited list,
one website, and "Milk").

**Next:** M13 Market-entry mode builds the full report for a confirmed market scope.
