# M14 — Research-more loop

**Date:** 2026-10-27 · **Status:** Done (27 Oct, after one fix round) · **Roadmap:** Phase 2, milestone 4 · **Builds on:** M13 (market
reports) and the two Milk · Kerala live runs

## Why

Both live market reports were thin for the same reason: the Researcher stops after a few searches (about 25 s),
whatever its instructions say. The second run, for example, had:

- no government or co-operative figures, only research-firm pages and copies of them;
- four of five players described only from an IMARC page, with none of their own websites read;
- a 2018 article about blockchain shown as a current trend, with an entry option built on it.

Company reports have the same weakness in a milder form: a competitor with one confirmed fact, or pricing that is
"not publicly available" because nobody looked.

Prompts alone can't fix this. **Code** has to check what's missing after fact-checking and send the Researcher back
for one targeted round.

## What you get

1. After fact-checking, code lists the **gaps** in the evidence (rules below). If there are none, nothing changes and
   the run takes no longer.
2. If there are gaps, **one extra research round** runs. The Researcher gets a short list of exactly what to find
   (for example "Kerala milk production and consumption from a government or co-operative source", "Malanadu: own
   website, products and prices", "a current source for the supply-chain blockchain claim"). The new claims are
   fact-checked like all the others and merged in.
3. **Old sources are flagged.** The Fact-Checker reports the date each source page states. A claim about trends,
   prices or recent events that rests only on a source more than 3 years old gets an **"Old source (2018)"** label,
   and the analysis is told not to present it as current.
4. The report says what the extra round did. A note under Evidence reads, for example, "Second research round: 6
   gaps, 4 filled (14 new claims)". The gaps that stay unfilled keep showing as "Not found in public sources".
5. Progress screen: the Research step shows "Filling gaps…" while the extra round runs. There are still five steps.

## Gap rules (in code, not left to the model)

| Report | A gap is… |
|---|---|
| Both | a competitor/player with fewer than 2 confirmed claims, or with no claim from its own website |
| Both | a claim about trends, prices or recent developments that rests only on a source older than 3 years |
| Company | no confirmed pricing or funding claim for the company |
| Market | a snapshot topic that is missing (size, growth, demand, prices, supply chain, rules, costs, barriers) |
| Market | market size or growth backed only by research-firm estimates (look for an official figure) |
| Market | fewer than 3 players with real prices |

At most **8 gaps** go into one round, most important first (market size/prices before supply chain, the first
players before the rest).

## How it works

| Part | Change |
|---|---|
| **Workflow** | research → validate → **deepen (only when there are gaps)** → analyse → strategise → write. The deepen step runs inside Agno's `Condition` (checked in the installed agno 2.9.0: `agno/workflow/condition.py`, the evaluator can be a Python function). It does a targeted research call, then fact-checks only the new claims, and returns the merged findings. Later steps use the merged result. |
| **Researcher** | The same agent specs, plus a **gap brief** in the prompt for round 2 ("find only these"). Round 2 is capped at 8 tool calls and 120 s. |
| **Fact-Checker** | fact_checker@3 also returns the date stated on each supporting page (`None` when the page shows none). Code compares it with today. |
| **Caps** | 1 extra round only. If the extra round fails or times out, the report continues with round 1's evidence and a note; it never fails the run. |
| **Report** | `meta.research_rounds` (gaps found, filled, new claims, extra tokens and time); `ReportClaim.old_source_year`. Older reports are unchanged. |
| **Frontend** | "Old source" label next to claims; the second-round note under Evidence; "Filling gaps…" on the progress screen. |
| **Measure** | Re-run `tests.live.market_check` (3 ideas) and `tests.live.benchmark` (5 companies) and compare with today's runs. Scorecards gain columns: gaps found/filled, players with own-site facts, estimate share, old-source claims. |

## Decisions (my choices; tell me if you disagree)

| # | Decision | Choice and why |
|---|---|---|
| D26 | How many extra rounds? | **One.** Each round costs about 8 Tavily credits plus 10–20k tokens and 30–60 s. One focused round should fill most gaps; more rounds can be reconsidered after measuring. |
| D27 | Who decides what's missing? | **Code**, with fixed rules (table above). The model only fills the gaps it is given. That way the result is predictable and testable. |
| D28 | Old-source threshold | **3 years**, and only for trends, prices and recent developments. Facts such as when a company was founded don't go stale. |
| D29 | Progress screen | Keep **five steps**; the extra round shows as "Filling gaps…" inside Research. The live, detailed progress view comes in M16. |

## Steps

1. Gap rules and gap brief (pure functions, unit-tested), for company and market reports.
2. Fact-Checker returns the source page date; old-source rule; tests.
3. The deepen step in an Agno `Condition`: targeted research, fact-check of the new claims, merge (new C-ids continue
   the numbering); fake-OpenAI tests: no gaps (step skipped), gaps filled, round fails (report still produced).
4. Report fields, frontend labels and notes, progress text; tests.
5. Scorecard columns; docs; commit; zip. Then **your live runs** (Milk · Kerala again, plus the scripts).

## Done when

- With fake APIs: a run with no gaps behaves exactly like today; a run with gaps fills them; a failed extra round
  still produces the report.
- On your live runs: fewer missing topics and research-firm-only claims, most players with facts from their own
  sites, old sources labelled. The run takes at most about 60 s longer and uses about 8 more Tavily credits.
- Company reports and all existing tests still pass.

**Effort:** about 3–4 days of developer work (the roadmap estimate). Here it's one build session plus your live
check.
