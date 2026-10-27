# M13 — Market-entry mode

**Date:** 2026-10-27 · **Status:** Done (27 Oct) — remaining depth issues (thin research, vague players, old sources) moved to M14 · **Roadmap:** Phase 2, milestone 3 · **Builds on:** M12 (the
confirm sheet already recognises a market such as "Milk" and collects product, region and customers)

## Goal

Answer "should I enter this market?" with the same evidence standard as company reports: every claim sourced and
fact-checked, gaps shown instead of guessed, and a clear statement that this is evidence to inform a decision — not
a verdict or financial advice.

## What you get

1. On the confirm sheet's market view, **Start market research** (product and region required; "Global" allowed;
   customers optional), e.g. *Fresh packaged milk · Kerala · households*.
2. The same progress screen (five agents), then a **market-entry report** with the M11 dashboard look:

| Tab | Contents |
|---|---|
| **Overview** | Bottom line (2–3 sentences, balanced), key numbers (claims verified, players profiled, sources, time), evidence donut, sourced key-figure charts (market size, growth, prices), market snapshot: size and growth, customers and demand, typical prices, supply chain and distribution, licences and rules, start-up costs and margins (where public), entry barriers. |
| **Players** | 3–6 main players in that market and region, as cards with profile panels, plus a comparison table (offer, price, customers, positioning). Same rules as competitors. |
| **Analysis** | **Market attractiveness**: five forces — rivalry, entry barriers, supplier power, buyer power, substitutes — each rated low / medium / high *with the claims behind it*; **signals for** and **signals against** entering, side by side; trends; risks. No single overall score — a number would suggest more precision than the evidence has. |
| **Entry options** | 3–5 ways in (e.g. a niche product, a local brand, a B2B channel), each with what to do, risks and trade-offs; and **"Check before you invest"**: concrete real-world checks (talk to 3 distributors, test prices at 5 shops, confirm the licence cost …). |
| **Sources** | As today. |

3. A banner on every market report: *"Evidence to help you decide — not a recommendation to invest and not financial
   advice. Check the 'before you invest' list."* Also printed in the PDF.
4. History and home cards show market reports with a "Market" label.

## How it works

| Part | Change |
|---|---|
| **Run** | `POST /api/v1/research` accepts `mode: "market"` with `market: {product, region, customer_type}`; stored in `research_runs.mode` / `scope` (columns added in M12). No migration needed. |
| **Agents** | Three new specs with their own versions — **market_researcher**, **market_analyst**, **market_strategist** — using the same models as their company versions. Fact-Checker and Report Writer are shared (the writer gets a market brief). Same workflow, same five steps; each step picks the spec by mode. |
| **Researcher (market)** | New output schema: scope note, market size, growth, customers and demand, prices, supply chain, regulation, costs and margins, barriers, trends, and main players (same shape as competitors). Searches region-specific sources first (government statistics, industry bodies, regulators, trade press), then national, then global — and says which level a figure is. All the existing evidence rules apply: retrieved pages only, dates only when stated, page cleaning, cited-page fetching, fact-checking, year check. |
| **Analyst (market)** | Five-forces ratings (each must cite claims; code drops a rating with no valid evidence), signals for/against, trends, risks, comparison table of players, key figures. Opportunities/risks never "fact" (M10 rule). |
| **Strategist (market)** | Entry options plus the "check before you invest" list. Code keeps the existing rules (evidence ids required, no recommendations built on missing data). |
| **Report** | Same `Report` shape plus `meta.mode` and a `market` section (scope, forces, signals, checks), so PDF, sources, panels and the "verified only" switch all keep working. Older reports are unchanged. |
| **Frontend** | Market view gets the start button and validation; dashboard shows the market tabs and banner when `meta.mode == "market"`; cards and history label market runs. |
| **Measure** | `tests/live/market_check.py` runs 3 ideas end to end (milk in Kerala, electric scooters in India, specialty coffee in the UK) and writes a scorecard: claims verified, players found, sections filled vs. marked missing, figures charted, time, tokens, Tavily credits. |

## Decisions (my choices; tell me if you disagree)

| # | Decision | Choice and why |
|---|---|---|
| D22 | Region required? | **Yes** ("Global" allowed). Market size, prices, players and rules all depend on place; without it the report is generic. |
| D23 | Separate market agents or one agent with a switch? | **Separate specs** (own instructions, schema and version), sharing models and tools. Prompts stay readable, and every report records exactly which prompts produced it. |
| D24 | Overall "attractiveness score"? | **No.** Five sourced ratings plus signals for/against. A single number would look more certain than the evidence is. |
| D25 | Disclaimer | Always shown on market reports and in the PDF. |

## Steps

1. Market schemas (findings, analysis, strategy, report section) + claim extraction for market sections; tests.
2. Market agent specs (researcher, analyst, strategist) + writer brief; workflow picks specs by mode; fake-OpenAI tests
   for the whole market run (happy path, missing data, partial report).
3. API: start a market run (validation, stored mode/scope); history shows mode; tests incl. PostgreSQL.
4. Frontend: market start on the confirm sheet; market dashboard (Overview, Players, Analysis with forces and signals,
   Entry options with checks, Sources); banner; print; tests.
5. `tests/live/market_check.py` + scoring tests; docs; commit; zip.

## Done when

- A market run completes end to end with fake APIs in tests, and the dashboard shows all market tabs.
- Every claim, rating, signal and chart number traces to a verified source or is visibly flagged; gaps say "not found
  in public sources" instead of guessing.
- Your live check on the 3 ideas produces reports you judge useful (that's the real test — local data may be thin).
- Company reports are unchanged; all tests, type check and build pass.

**Effort:** about 1–1.5 weeks.

**Open from M12:** the competitor quality check (`uv run python -m tests.live.competitor_eval`) hasn't been run yet;
it can run any time and doesn't block M13.

## Fix round after the first live run (Milk · Kerala, 27 Oct)

| Problem in the report | Fix |
|---|---|
| Headline "INR 706.1 Billion" was one research firm's (IMARC) estimate of the whole **dairy** market, presented as the **milk** market | Research-firm pages (IMARC, Mordor, Grand View …) are marked **"Estimate · research firm"** on claims and charts; the writer never opens with an estimate and keeps each figure's exact scope; the Researcher looks for official figures first |
| Thin research (16 claims, 7 sources, researcher stopped early); no real prices | Researcher asks for 10–15 searches, actual per-unit prices for ≥3 players, and reads each player's own site |
| Players with one vague fact ("X is a known player") | A player needs ≥2 sourced statements, otherwise it's left out with a note |
| Missing topics (costs and margins) silently absent | Shown as "Not found in public sources — check this yourself" |
| Title "milk"; label "(by 2030) (2030)" | First letter capitalised; year not repeated |
