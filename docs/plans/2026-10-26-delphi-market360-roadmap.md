# Delphi Market360 — Roadmap after the POC

**Date:** 2026-10-26 · **Status:** Agreed in outline; each milestone planned and approved separately. M11 = UI redesign, M13 = market-entry mode (both added after the POC review) · **Builds on:** `2026-10-20-delphi-market360-poc-plan.md` (§6.3 priorities, §17 roadmap)

> Nothing here is approved yet. As with the POC, each phase gets a detailed plan before work starts, and each
> milestone waits for your confirmation before the next one begins.

## Ground rules (unchanged)

- Local only: no Docker, no cloud. Cloud is Phase 5 and needs your explicit approval.
- OpenAI is the only LLM and Tavily the only data source. Any new data source (Phase 3) needs your approval first.
- One milestone at a time, each with tests, docs and verification steps for you.
- Never commit secrets.

## Where we are

| Phase | Status |
|---|---|
| 1 — Local POC (M1–M10) | Built. Benchmark: 5/5 reports, 70–90 s, 43–88k tokens, 6–16 Tavily credits, 84–95% of claims supported. **Open:** your manual check of 50 sampled claims (criterion 5). |

Lessons from the POC that shape the plan:

0. **The UI must be demo-ready for management** → M11 redesign first (mockup approved).
0b. **Market-entry questions** ("should I start a milk company?") are a strong use case, especially for a consulting firm → M13, proved on 3 ideas before polishing further.
1. **Competitor choice is the weakest part** (Notion → "Craft Agents", Reflect; Canva → Stability AI). Fix first.
2. Evidence quality is now good (84–95% supported) — keep the code checks; don't loosen them.
3. A run takes 70–90 s, mostly the sequential research step — parallel research is the speed lever.
4. Tokens are dominated by the research step; page cleaning already halved them.

---

## Phase 2 — Local MVP (≈ 6–8 weeks)

Goal: a tool a small team could use daily on one machine — accurate company and competitors, market-entry
reports for new ideas, faster runs, live progress, cost visible, login.

| # | Milestone | What you get | Done when | Effort |
|---|---|---|---|---|
| **M11** | **UI redesign and charts** | The approved Apple-inspired design built into the app: new Home, progress pipeline, report dashboard with tabs, clickable citations, side panels, charts, dark mode. Analyst adds sourced `key_figures` for number charts. Plan: `2026-10-26-m11-ui-redesign-plan.md`. | All three screens match the design on real runs; every chart number traces to a verified source. | 1–1.5 weeks |
| **M12** | **Confirm company and competitors** | A quick "identify" step (a few searches, a few seconds) shows the company it matched, its website, and 3–5 suggested competitors; you confirm, pick another match, or edit the list before the full research starts. It also tells a **company** from a **market** ("Milk", "electric scooters in India") so a product name is never researched as some company of that name. New tables `companies` and `run_competitors`. Plan: `2026-10-26-m12-confirm-company-plan.md`. | Ambiguous names (e.g. "Mercury") are matched correctly; the research uses exactly your list; "Milk" is recognised as a market. | 4–5 days |
| **M13** | **Market-entry mode** | For an idea rather than a company ("Should I start a milk company in Kerala?"): confirm product, region and customer type, then a sourced report on market size and growth, main players and prices, demand trends, supply chain, licences and rules, typical costs and margins (where public), market attractiveness, risks, signals for and against, entry options, and what to check in real life before investing. Same agents and evidence rules, new instructions and report sections. Clearly evidence, not a verdict or financial advice. | Tested on 3 ideas (e.g. milk in Kerala, electric scooters in India, specialty coffee in the UK); every claim sourced or flagged; gaps shown, not guessed; you judge the reports useful. | 1–1.5 weeks |
| **M14** | **Research-more loop** | After fact-checking, if a competitor or a key field (pricing, funding) has too few confirmed claims, one targeted extra research round fills the gap (Agno `Condition`/`Loop`), capped at 1 round and a token budget. | On the benchmark, fewer "unconfirmed" claims, with run time and tokens still within the targets. | 3–4 days |
| **M15** | **Parallel research** | The company and each competitor are researched at the same time (Agno `Parallel`), each by a smaller focused Researcher. | Run time drops by about 40% with the same quality on the benchmark. | 3–4 days |
| **M16** | **Live progress** | The progress page updates instantly instead of every 3 s, and shows what is happening ("Reading coda.io…", "Checking 25 claims…"). Uses AgentOS streaming (server-sent events); polling stays as a fallback. | Steps and activity appear within a second; a dropped connection recovers. | 3 days |
| **M17** | **Cost in currency and limits** | Model prices in config; cost per step and per run (in USD) on the run page and in history; a daily spending limit that blocks new runs when reached. | Costs shown match the OpenAI usage page within a few percent; the limit stops new runs. | 2 days |
| **M18** | **Re-run, cancel and history** | Buttons to cancel a running research and re-run a finished one; history with search, filter by status, and delete. | Cancel stops the run within seconds and marks it cancelled; re-run starts with the same company and competitors. | 2–3 days |
| **M19** | **Server-side PDF** | A "Download PDF" button that returns a ready PDF (same look as the page), instead of the browser print dialog. | PDFs of all benchmark reports are readable, with no cut-off tables. | 2 days |
| **M20** | **Login** | User accounts with password login; every API and AgentOS route protected; each user sees only their own research. | Without logging in, nothing is reachable; users can't see each other's runs. | 3–4 days |
| **M21** | **MVP benchmark and sign-off** | The benchmark on 20 companies of mixed types and sizes (plus 5 market-entry ideas), with targets agreed at the end of the POC. | Targets met; you make a go/no-go decision for Phase 3. | 2 days |

**Decisions needed before Phase 2 (I'll give options and a recommendation in the Phase 2 plan):**

| # | Decision | My suggestion |
|---|---|---|
| D11 | Login: our own simple accounts, or AgentOS's built-in JWT authorization? | Our own accounts (FastAPI + hashed passwords + secure cookie); AgentOS routes behind the same check. |
| D12 | Server PDF engine: Playwright (headless Chromium) or WeasyPrint? | Playwright — it renders the same page you see, so print and screen match. |
| D13 | Charts library | Decided in M11: no library for now — SVG/CSS charts matching the design. |
| D14 | MVP targets | From POC: < 2 min, < 100k tokens, < 20 Tavily credits, ≥ 85% claims supported per report. |

---

## Phase 3 — Advanced features (≈ 6–10 weeks)

Goal: from one-off reports to ongoing market intelligence.

| # | Milestone | What you get | Done when | Effort |
|---|---|---|---|---|
| **M22** | **Ask questions about a report** | A chat box on each report: "How does Monzo's pricing compare with Starling's?" Answers use only the stored sources and cite them (RAG with pgvector in PostgreSQL). | Answers cite sources; questions the sources can't answer get "not in the sources". | 1–1.5 weeks |
| **M23** | **History and change tracking** | Re-run a company later and see what changed: new competitors, new products, changed pricing, new risks. | A side-by-side "what changed" view between two runs of the same company. | 1 week |
| **M24** | **Compare several companies** | Pick 2–5 companies and get one comparison report. | Comparison table and SWOT side by side, every cell sourced. | 1 week |
| **M25** | **Monitoring and schedules** | Schedule a company to be re-researched weekly or monthly; a notice in the app when something important changed. | Scheduled runs happen on time while the backend runs; changes are flagged. | 1 week |
| **M26** | **Editable agent settings** | An admin page to change each agent's model and instructions, with versions and a way to roll back. | A changed prompt is used by the next run; every report records the versions used. | 1 week |
| **M27** | **More data sources** *(needs your approval per source)* | Free official sources, for example Companies House (UK filings), SEC EDGAR (US filings) and a news API, alongside Tavily. | Each source passes a licence and terms check; reports cite it like any other source. | 1–2 weeks |

**Decisions needed before Phase 3:** scheduler (APScheduler inside the backend vs a separate local process);
which new data sources, if any; whether notifications stay in-app or also go by email.

---

## Phase 4 — Production readiness, still local (≈ 3–5 weeks)

Goal: safe and reliable enough for real users on a company machine or server.

| # | Milestone | What you get | Done when |
|---|---|---|---|
| **M28** | **Security review** | OWASP checklist, prompt-injection tests with hostile web pages, dependency and secret scanning, rate limits per user, per-user cost limits. | No high findings open; rate and cost limits enforced. |
| **M29** | **Reliability and data** | PostgreSQL backups with a tested restore, a retention policy for stored page excerpts, retries for Tavily/OpenAI outages, and a separate worker process for runs — only if load tests show it's needed. | Restore tested; runs survive an API restart. |
| **M30** | **Automated checks and load test** | Tests, lint and security scans run automatically on every change (CI); a load test with several users at once. | CI green on every change; agreed load handled. |

**Decisions needed before Phase 4:** where CI runs (GitHub Actions only runs checks — it deploys nothing — but
it is a hosted service, so I'll ask first); how the app is installed on a server without Docker.

---

## Phase 5 — Cloud (only with your explicit approval)

Not planned in detail. If and when you approve, I'll first write a separate plan (likely Azure, using the
orchestrator's `infra/` as a reference), covering hosting, secrets vault, separate workers, monitoring and cost.

---

## Summary

| Phase | Milestones | Effort | Ends with |
|---|---|---|---|
| 1 — POC | M1–M10 | done | Your manual check + go/no-go |
| 2 — Local MVP | M11–M21 | 6–8 weeks | 20-company benchmark (+ market-entry ideas) |
| 3 — Advanced | M22–M27 | 6–10 weeks | Per-feature acceptance |
| 4 — Production readiness | M28–M30 | 3–5 weeks | Security and load checks pass |
| 5 — Cloud | — | TBD | Your approval first |

Efforts are rough and assume the same way of working as the POC (one milestone, your check, next milestone).
