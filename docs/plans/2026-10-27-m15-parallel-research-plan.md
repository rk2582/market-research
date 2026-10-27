# M15 — Parallel research

**Date:** 2026-10-27 · **Status:** Built — awaiting your live check · **Roadmap:** Phase 2, milestone 5 · **Builds on:** M12 (confirmed
competitors), M13 (market players), M14 (second round)

## Why

Today one Researcher does everything in a single long conversation: the company (or market), then each competitor,
one after another. Every tool call re-sends all the pages it has read so far. That makes it:

- **Slow.** The research step takes 25–50 s, plus 12–30 s for the second round.
- **Costly.** The last Milk run used 178k tokens in the research step alone, about 85% of the whole report.
- **Shallow on competitors.** They get whatever budget is left at the end, which is why M14 had to send the
  Researcher back for players.

## What changes

Research splits into a **lead researcher** and **one small researcher per competitor/player, running at the same
time**:

1. **Lead researcher** — the company (or the market: size, growth, demand, prices, rules …) and the list of
   competitors/players. If you confirmed competitors in the confirm sheet (M12), it uses your list and skips
   choosing.
2. **Competitor researchers (in parallel)** — one per competitor or player, 3–6 at once. Each has a small budget (about
   4 tool calls, 60 s) and one job: read the competitor's own website, then fill in its description, offering, pricing,
   target customers and positioning. Each one only re-sends its own few pages, so tokens drop sharply.
3. Everything else stays the same: fact-checking, the second round (M14, now with fewer gaps to fill), analysis,
   strategy, writing, the report and the UI.

You won't see a new screen. Reports should arrive faster and with fuller competitor profiles. The progress page
shows "Researching 4 competitors…" during the parallel part.

## How it works

| Part | Change |
|---|---|
| **Workflow** | The research step runs the lead researcher, then the competitor researchers together with `asyncio.gather`, inside the same step. That's the same pattern the fact-checker already uses for its batches. **Why not Agno's `Parallel`:** checked in the installed agno 2.9.0 (`agno/workflow/parallel.py`), its steps are fixed when the workflow is built, but the number of competitors is only known at run time. |
| **Agents** | lead_researcher@1 / market_lead@1: the current Researcher's prompts minus competitor profiling. competitor_researcher@1: new, small, focused on one company's own site. Same models (they use the Researcher's model setting). |
| **Limits** | At most 6 competitor researchers at once. Each has a 60 s timeout. If one fails or times out, that competitor is simply "not profiled" (a note, as today); the report never fails because of one competitor. The lead researcher failing still fails the run, as now. |
| **Sources / claims** | Each researcher's pages are combined into one source list (no duplicates). Claims, fact-checking and every M10–M14 rule work unchanged on the merged findings. |
| **Tavily** | About the same number of credits (the same pages, read by different agents). Up to 6 researchers search at once, within the free plan's limits. (Built without an automatic retry: a researcher that hits a Tavily error simply gets an error result for that search and carries on with what it has.) |
| **Measure** | Benchmark (5 companies) and market check (3 ideas) before and after: time, research-step tokens, total tokens, competitor facts confirmed, second-round gaps. |

## Decisions (my choices; tell me if you disagree)

| # | Decision | Choice and why |
|---|---|---|
| D30 | Agno `Parallel` or `asyncio.gather` in a step? | **asyncio.gather**: the competitor count is only known at run time; Agno's Parallel needs fixed steps. |
| D31 | How many competitors at once? | **Up to 6** (the most a report has). Tavily's free plan allows it; OpenAI rate limits on your key are far higher. |
| D32 | Keep the M14 second round? | **Yes.** It should now find fewer gaps and often not run at all. |

## Steps

1. Lead + competitor researcher specs, prompts and schemas; strict-schema tests.
2. Research step: lead, then competitors in parallel, merge, failure handling; fake-API tests (all succeed, one
   competitor fails, one times out, confirmed list, market players).
3. Progress text ("Researching N competitors…"); usage per agent in "How this report was made".
4. Scorecards: research time and tokens per step; docs; commit; zip. Then **your live runs**: Milk · Kerala and the
   benchmark, compared with today's.

## Done when

- Fake-API tests: all succeed, partial failures, confirmed lists and market mode behave as described.
- On your runs: research about 40% faster, research tokens clearly lower, competitor profiles at least as full, same
  or better share of verified claims.
- All existing tests pass.

**Effort:** about 3–4 days of developer work (the roadmap estimate). Here it's one build session plus your live check.
