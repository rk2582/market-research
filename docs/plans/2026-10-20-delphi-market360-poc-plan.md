# Delphi Market360 — Codebase Analysis and POC Plan

**Date:** 2026-10-20 · **Version:** 4 · **Status:** Draft for approval · **Reference repo:** `agno-orchestrator.zip` (project name inside: *delphi-factory*, last commit `8e4a293`)

> Nothing has been built yet. This document covers the analysis and the plan only. Implementation starts after you approve it, one milestone at a time.

### Milestone 12 fix — competitor quality (from the user's Nestlé India report)

- Problem: suggested Mother Dairy, Bikaji, AWL Agri Business, Varun Beverages (a Pepsi bottler), Prabhat Dairy; missed
  Hindustan Unilever, ITC, Mondelez, Britannia, Amul. Cause: company-database lists group firms by industry code; a
  multi-category company needs rivals per product line; 3 searches were too few to check.
- Fix: identifier@2 lists product lines (with brands) and picks the leading rival per line (`competes_in`), may
  propose candidates from its knowledge but must confirm each with a retrieved page; database-list sources are flagged
  `weak_evidence` and listed last; 6 tool calls, 40 s. researcher@8 gets the same guidance.
- Measured by a fixed test set (`tests/live/competitor_eval.py`), not by eye.

### Milestone 12 notes (plan: `2026-10-26-m12-confirm-company-plan.md`)

- New Identifier agent (identifier@1) behind `POST /api/v1/research/identify`; the confirm sheet on Home lets the user
  pick the match and edit up to 6 competitors; the run researches exactly that list (researcher@7 + code filter).
- Company vs market detection; the market view collects product/region/customers and says reports arrive in M13.
- Migration `05bb7f0bf796`: `companies`, `run_competitors`, `research_runs.company_id/mode/scope`. Every finished run
  is linked to its company (for history and comparison later).
- Deviation from the plan: the market scope is shown and editable but not stored yet — there is no market run to
  attach it to until M13; the `mode`/`scope` columns are ready for it.

### Milestone 11 notes (Phase 2, plan: `2026-10-26-m11-ui-redesign-plan.md`)

- Apple-inspired redesign of all screens from the approved mockup: Home (hero search, stats from history, recent cards),
  progress pipeline with an activity log built from step data, report dashboard (stat tiles, 5 tabs, clickable source
  numbers → source panel, competitor panel, "show only verified claims", charts), dark mode, phone layout.
- Backend: Analyst returns `key_figures` (analyst@4); code keeps a figure only if its exact number is in a verified or
  partly verified claim it cites. History list adds `duration_ms`, `verified_pct`, `competitor_count` for the home cards.
- Charts are SVG/CSS (no chart library). PDF prints every tab, each starting on a new page.

### Milestone 10 notes

- Quality fixes first, from the user's Facebook (→ Meta) report, so the benchmark measures the current pipeline:
  page-text cleaning; no own brands as competitors; competitor homepages fetched and credited only when the
  Fact-Checker says they support a claim; empty comparison columns dropped; opportunities and risks never 'fact'.
- Agent versions: researcher@6, fact_checker@3 (new `supporting_urls` field), analyst@3.
- Benchmark runner: `tests/live/benchmark.py` (lives under tests/ so it stays out of the product code). Counts Tavily
  requests and credits with a wrapper; scores acceptance criteria 2–6 automatically; criterion 5 needs the manual check.
- Default companies: Notion, https://monzo.com (URL input), Facebook, Canva, Pipedrive (smaller B2B).

### Milestone 9 notes

- Browser → Next.js proxy (`/api/proxy/api/v1/...`) → backend. The proxy allows only `api/v1/`, only GET/POST, 30 s timeout, and returns 502 `backend_unavailable` when the backend is down. `BACKEND_URL` stays server-side.
- Polling: one status call every 3 s, the next only after the previous answers; stops when the run finishes, then loads the report once. A lost connection keeps the progress on screen with a Reconnect button.
- Deviation: no `useCreateResearch` hook — `HomeScreen` calls `startResearch` directly (one call, no state worth a hook).
- PDF: print CSS + the browser's "Save as PDF" (no PDF library). Header, contents and run details are hidden in print; tables and SWOT are not split across pages.
- Backend fix found in end-to-end testing: SQLite returned times without a zone; the API now always sends UTC (`...Z`).
- Fixtures are now used by tests only.

### Milestone 8 notes

- Built against fixtures: two real live reports (Notion, Monzo) plus runs in every state (running, partial, failed). Pages read fixtures directly; Milestone 9 swaps in the proxy, API client and polling (`HomeScreen.startRun` and the run page are the seams).
- No new libraries. System fonts only (serif for report prose) so `next build` needs no network.
- Client-side query check mirrors the backend rules; the same test cases run on both sides.
- Evidence first: an "evidence bar" (verified / partly / unconfirmed) under the title; every claim carries linked source numbers; weaker verdicts are labelled, verified ones get a quiet dot.
- Partial reports keep all 12 headings; missing sections say they are not available instead of disappearing.

### Milestone 7 notes

- Endpoints as in §13.1. Status is kept up to date by **reconcile on read**: Agno has no completion hook, so every read and every start first saves runs that Agno has finished. This also frees capacity for runs nobody polled.
- `current_step` column (migration `3b1c9e2d7a40`) written by the workflow's progress callback; while a run is in progress the five steps' states come from it (Agno stores step results only at the end).
- Startup reconcile: finished runs are saved, runs still marked running are failed ("server restarted").
- Input rules enforced in `schemas/api.classify_query`: http/https only, no credentials in URLs, no localhost/`.local`/private/loopback/link-local/reserved IPs, bare domains like `monzo.com` become `https://monzo.com`.
- `research_sources` = the report's references (same numbers, with the excerpt that was fact-checked).
- Error codes: `run_not_found` (404), `report_not_ready` (409, also for failed runs), `capacity_reached` (429), `start_failed` (500, generic message).
- Deviation: report `meta` has no `run_id` (the client already knows it).

### Milestone 6 notes

- Five-step workflow: research → validate → analyse → strategise → write. Research/validate failure → run failed; later failures → **partial** report (write step always assembles). `outcome_from_run()` maps Agno's always-COMPLETED status to succeeded/partial/failed.
- Fact-check: claims citing never-retrieved pages are judged `unsupported` in code (no LLM cost); the rest go to the Fact-Checker in parallel batches of 25 with only the excerpts they cite. Contradicted claims are removed before analysis.
- Report assembled in code: 12 sections, insights numbered F1…, `[C12]` in prose → source numbers, insights/recommendations without valid evidence dropped, 'fact' insights resting only on unconfirmed claims downgraded to 'interpretation'.
- From the M5 live data: Researcher misdated an older acquisition as "September 2026" → researcher@3 adds a strict date rule; company websites cleaned to the site root; http/https duplicates merged; stored excerpts raised to 6,000 chars so the Fact-Checker sees what the Researcher saw.
- Progress: steps call an optional `progress(research_id, step)` callback; the DB-backed version and `current_step` column come with the API in M7 (keeps the workflow runnable from /docs).

### Milestone 5 findings (spike, Agno 2.9.0)

- **Agno upgraded 2.5.17 → 2.9.0.** pip-audit: 2.5.17 has an open advisory; 2.9.0 has none. All M2–M4 tests passed unchanged. 2.9.0 needs `python-multipart` installed explicitly. Whole backend: 0 known vulnerabilities.
- **Q2 background runs: confirmed.** `arun(background=True)` returns in < 0.1 s; status and step outputs are stored in PostgreSQL and readable later with `aget_run(run_id, session_id)`, even from a new object.
  - Gap: step results appear only at the end → no live step progress from Agno. Each step will write `current_step` on `research_runs` (small migration in M6).
- **Q5 failing steps:** Agno retries a failing step 3 times by default (paid calls) and still marks the run `COMPLETED`. Fix applied: `max_retries=0`, steps catch errors and return `stop=True`; `research_runs.status` is the source of truth. `stop=True` verified to skip later steps.
- **Deviation from plan — own async web toolkit** instead of Agno's `TavilyTools`: Agno calls sync tools on the event loop (would freeze the API during each search), and TavilyTools' page extraction returns whole pages (cost). `tools/web_research.py` uses `AsyncTavilyClient`, caps snippets at 1,200 and pages at 6,000 characters. A test proves the event loop stays free during a slow search.
- **Strict structured outputs:** first live run (user) failed with OpenAI 400 "$ref cannot have keywords {'description'}" — a strict-mode rule my offline check missed. Fixed (descriptions moved into instructions, researcher@2) and `tests/test_output_schemas.py` now checks every agent schema for free. **Q1 confirmed once the user's re-run passes.**
- **Q4 tracing:** stays off for the POC; per-step tokens, tool calls and duration are captured in each step's output instead.
- Sources come from the tool results, never from the model's own list, so an invented URL cannot become a source.

### Milestone 4 notes

- `agno_session_id` column dropped from the ERD: the run's own `id` is used as the Agno session id, so storing it twice was redundant.
- Run status values: `running | succeeded | partial | failed` (no `queued`: a run starts as soon as it is created).
- `research_sources.retrieved_by`: `search | extract` (which Tavily function found it).
- Settings now reject `AGNO_DB_SCHEMA=public` (Agno's tables must stay out of our schema).
- Integration tests migrate a temporary database, never the real one.

### Milestone 3 findings (verified against Agno 2.5.17 + PostgreSQL 16)

- **AgentOS works with no agents**, so no placeholder agent is needed. Agents and the workflow are added in M5.
- **Agno telemetry is ON by default** (`AgentOS(telemetry=True)`, and agents/workflows follow `AGNO_TELEMETRY`). It is off in this project; a test proves no telemetry call is made with default settings.
- **CORS:** passing `cors_allowed_origins` replaces Agno's default origin list (`agno.com` domains). Only `http://localhost:3001` is allowed.
- **Agno tables:** AgentOS creates them at startup in the `agno` schema (public behaviour, `auto_provision_dbs`). If the DB is down it only logs a warning. This answers M5 spike question 3.
- **Our error handlers** keep working inside AgentOS; `on_route_conflict="error"` fails fast if a route ever clashes.
- **Run command** uses uvicorn factory mode (`main:create_app --factory`) so importing the app in tests never reads the real `.env`.
- Health lives in `api/health.py` (`GET /api/v1/health`); AgentOS also has its own `GET /health` (process only, no DB check).

### What changed in version 4

- **No Docker.** Your machine is slow with Docker Desktop, and PostgreSQL is already installed. We use your local PostgreSQL (≥ 14) on port 5432. No compose file.
- **Dependency audit (M2):** pydantic-settings bumped to 2.14.2 (CVE fix); Next 15's bundled PostCSS overridden to a fixed version (0 npm vulnerabilities); Vitest 5 used (Vitest 4.1 conflicts with Vite 8). One Agno advisory remains on 2.5.17 with no fix listed; the known Agno advisories hit components we don't use (ClickHouse backend, PythonTools). Moving to a newer 2.x is reviewed at the start of M5, before any agent code exists.

### What changed in version 3

- **Q1 answered — OpenAI only.** Model factory supports OpenAI only (`OpenAIChat`), still behind one function so another provider can be added later. Anthropic/Azure dependencies and settings removed.
- **Q5 answered — project name Delphi Market360.** Repo folder `delphi-market360/`, Python package `delphi-market360`, database `market360`.

### What changed in version 2

| Change | Effect |
|---|---|
| **AgentOS is now the runtime** (was: plain FastAPI) | Workflow runs, background execution, run status, cancel, sessions, token metrics and traces come from AgentOS instead of hand-built code. |
| **Database slimmed to 2 product tables** (was 3) | Step status, step outputs and tokens are read from Agno's stored workflow run. `research_step_runs` is dropped. |
| **Hand-built background runner removed** | Replaced by `Workflow.arun(background=True)`, with a thin fallback only if the M5 spike shows a gap. |
| **Orchestrator treated as reference only** | Section 4 now lists what we take *and* what we deliberately leave out. |
| **Terminal runner script removed** | AgentOS Swagger (`/docs`) can run the workflow and each agent directly. |
| Milestones, API, tests, risks updated | M5 now includes an AgentOS spike; total effort ≈ 14 days. |

---

## 1. Executive summary and product understanding

**What we are building.** A local web app where a user types a company name or website. A fixed pipeline of five Agno agents does the work:

1. Research the company and find 3–5 competitors.
2. Check the facts.
3. Analyse the market.
4. Write recommendations.
5. Produce a report with sources.

The user watches progress, then reads, prints or saves the report as PDF.

**What the POC must prove.** That an agent pipeline can turn one input into a useful, *source-backed* report, reliably, at a known cost, on a laptop.

**Key decisions:**

| # | Decision | Why |
|---|---|---|
| D1 | **Agno Workflow (fixed steps), not an Agno Team** | Every report follows the same order. A Team's leader LLM would decide routing at run time, which adds cost and can skip or reorder steps (see 9.1). |
| D2 | **Five single-purpose agents, each with a Pydantic `output_schema`** | Matches the spec. Structured output makes every finding storable, testable and traceable to a source. |
| D3 | **Fact-check right after research, before analysis** | The spec's goal is to stop bad facts spreading; checking at step 6 would be too late. *(Deviation — needs your OK.)* |
| D4 | **AgentOS hosts the Workflow and the five agents** | Agno's own runtime. It gives run, status, cancel, sessions, metrics and traces endpoints, so we don't build them. |
| D5 | **Background runs via `Workflow.arun(background=True)`; frontend polls** | Runs take minutes. No Redis, no queue. Polling every 3 s is enough and survives page refresh. |
| D6 | **Agno `PostgresDb` attached to the workflow** | Stores runs, step outputs and token metrics. This becomes our execution log. |
| D7 | **Thin product API on AgentOS's `base_app`** | Generic AgentOS endpoints don't validate company/URL input, and don't know about reports or sources. We add a few `/api/v1/research` routes. |
| D8 | **Tavily for search *and* page extraction** | Agno 2.5.17's `TavilyTools` has `web_search_using_tavily` and `extract_url_content` (verified), so no scraping library. |
| D9 | **PDF via browser print stylesheet** | No extra dependencies. Server-side PDF moves to MVP. |
| D10 | **Pin `agno==2.5.17`** | Same as the orchestrator lock file. PyPI now has 3.1.7 (a major version); upgrading is a separate decision. |

Open questions for you are in [section 19.3](#193-open-questions-for-you).

---

## 2. Existing Agno orchestrator — codebase analysis

Every finding below was checked in the actual files: 835 files excluding build output, and about 10.3k lines of backend Python excluding tests.

### 2.1 Repository layout

| Folder | Contents |
|---|---|
| `backend/` | FastAPI + AgentOS app (port 7777) |
| `frontend/` | Next.js 15 app (port 3000) |
| `packages/storybook/` | Storybook for AG-UI components |
| `infra/` | Terraform for Azure — not relevant to POC |
| `.github/workflows/` | CI (tests, lint, 90% coverage gate, audits) + Azure deploy |
| `docs/` | Specs and plans (`docs/superpowers/plans/`), test reports |
| `scripts/` | CSV-driven agent test runner |
| `CLAUDE.md`, `AGENTS.md` | Coding rules: ruff, bandit, 90% coverage, run tests before commit |

### 2.2 Backend findings

| Area | What exists | Files |
|---|---|---|
| **Entry point** | Builds `base_app` (FastAPI) and wraps it in `AgentOS(agents=[placeholder], db=..., base_app=...)`. The placeholder is needed because real agents load from the DB later and are pushed into AgentOS afterwards. Includes 10+ routers. Replaces the lifespan with a chain: AgentOS lifespan → re-index → OTel → metrics → registry load → seed commit → scheduler. Also holds knowledge endpoints and chat-tracking middleware (671 lines). | `backend/main.py` |
| **Container start** | `alembic upgrade head` → create Agno tables via private `db._create_all_tables()` → seed → uvicorn | `backend/start.sh` |
| **Routing** | One `APIRouter` per domain. Mixed prefixes (`/config/agents`, `/agents`, `/teams`, `/v1/proactive`, `/api/v1/auth`, `/v1/knowledge`). Handlers open `async with get_session()` directly. Registry is reached by a lazy `from main import registry`. | `backend/api/*.py` |
| **Agent creation** | Agent configs are DB rows, seeded from `seeds/default_agents.py`. `registry/factory.py::build_agent_from_config()` builds `agno.agent.Agent` with tools, history, `PostgresDb`, events and memory. Legacy `agents/*.py` factories are mostly unused. | `registry/factory.py`, `seeds/` |
| **Model provider** | Hard-coded Azure OpenAI (`_azure_model()`). | `registry/factory.py` |
| **Tools** | Name → factory map, `resolve_tools(names)`, `UnknownToolError`. Custom tools use `@tool`. | `registry/tools_catalog.py`, `tools/` |
| **Orchestration** | `agno.team.Team` "Super Agent" with an LLM coordinator. `api/agui.py` uses regex shortcuts to bypass the team for chart and place prompts. **No Agno `Workflow` and no `output_schema` anywhere** (checked by grep). | `registry/factory.py`, `api/agui.py` |
| **Background jobs** | In-process `asyncio.create_task`. Scheduler claims due DB rows. Run rows go `queued → running → succeeded / partial_failed / failed`. The proactive executor runs **stub** agents. | `services/proactive/*` |
| **Database** | SQLAlchemy 2 async + asyncpg. `get_session()` context manager commits or rolls back. `JSONType`/`UUIDType` decorators work on both Postgres and SQLite. | `db/session.py`, `db/models/agent.py` |
| **Migrations** | Async Alembic, timestamped filenames, 12 revisions. Agno tables (`ai.agno_sessions`, `ai.knowledge_chunks`, traces, spans) sit outside Alembic. | `migrations/` |
| **Repositories / schemas** | One class per table, returning Pydantic models. Pydantic schemas follow Base / Create / Update / Config. | `repositories/`, `schemas/` |
| **Configuration** | `os.environ` read in many places. Only auth has a typed settings object. | `auth/settings.py` |
| **Auth** | Azure AD JWT middleware. `AUTH_DISABLED=1` falls back to an `X-User-Id` header. | `auth/` |
| **Streaming** | AgentOS SSE run endpoints, AG-UI endpoints, and an in-process SSE notification hub. | `api/agui.py`, `services/proactive/sse.py` |
| **Observability** | Agno OTel tracing, run metrics read from Agno sessions (`api/traces.py`), standard `logging`. | `main.py`, `api/traces.py` |
| **Guardrails** | `evals/rag_groundedness.py` post-hook: keyword check, logs only. | `evals/` |
| **Errors** | `HTTPException` per route. No global handlers. | `api/` |
| **Testing** | pytest-asyncio; SQLite in-memory conftest; `httpx.ASGITransport` against the app; `AUTH_DISABLED`; 90% coverage gate; ruff (`E,F,I,S,B,UP`, line 120), bandit. | `tests/`, `pyproject.toml` |

### 2.3 Frontend findings

| Area | What exists | Files |
|---|---|---|
| Stack | Next 15.3 (Turbopack), React 19, TS 5.7, Tailwind 4 | `package.json`, `next.config.ts` |
| Structure | App Router in `src/app`; feature modules `src/modules/<feature>/{api,components,hooks,lib,types,styles}` | `src/modules/proactive-intel/` |
| Components | Atomic design (atoms, molecules, organisms, templates), each with `index.ts` and a test | `src/modules/agui/components/` |
| Backend calls | Route-handler proxy `/api/proxy/[...path]` with a path allowlist. Two client styles: fetch + `authFetch`, and an axios client. One module bypasses the proxy and calls the backend directly. | `src/app/api/proxy/...`, `src/lib/api.ts` |
| Data / state | Custom `useQuery`/`useMutation` hooks, React context, zustand for auth | `modules/proactive-intel/hooks/` |
| Testing | vitest + jsdom + Testing Library (90% thresholds), Playwright e2e | `vitest.config.ts` |

### 2.4 Pinned versions

| Package | Version | | Package | Version |
|---|---|---|---|---|
| Python | 3.12 | | next | ^15.3.0 |
| agno | **2.5.17** | | react | ^19.0.0 |
| fastapi | 0.135.3 | | typescript | ^5.7.0 |
| pydantic | 2.13.1 | | tailwindcss | ^4.0.0 |
| sqlalchemy | 2.0.49 | | vitest | ^4.1.4 |
| alembic | 1.18.4 | | Postgres image | `pgvector/pgvector:pg16` |
| asyncpg | 0.31.0 | | openai | 2.32.0 |
| anthropic | 0.95.0 | | tavily-python | 0.7.23 |

### 2.5 Agno 2.5.17 APIs verified for this plan

I installed `agno==2.5.17` in a throwaway environment and checked the source and signatures.

**Agents and workflows**

- **`Agent`:** supports `output_schema`, `parser_model`, `tool_call_limit`, `retries`, `exponential_backoff`, `pre_hooks` and `post_hooks`. `response_model` does not exist in 2.x.
- **Workflow building blocks:** `Workflow`, `Step`, `Steps`, `Parallel`, `Loop`, `Condition` and `Router`.
- **`Step`:** has `max_retries` and `skip_on_failure`. It has **no timeout setting**, so timeouts are our own `asyncio.wait_for`.
- **`Workflow.arun`:** supports `background=True`, `session_id`, `user_id`, `additional_data` and `stream`. `Workflow` also has `get_run`, `aget_run`, `get_run_output` and `cancel_run`.

**Metrics and tools**

- **`RunOutput.metrics`:** includes `input_tokens`, `output_tokens`, `total_tokens`, `duration` and `cost`.
- **`RunOutput.tools`:** each entry has `tool_name`, `tool_args` and `result`. This lets us capture the raw Tavily source text.
- **`TavilyTools`:** accepts `enable_search`, `enable_extract`, `search_depth` and `format="json"`.

**AgentOS**

- **`AgentOS(...)` accepts:** `agents`, `teams`, `workflows`, `db`, `base_app`, `interfaces`, `authorization`, `on_route_conflict` and `tracing`.
- **Workflow routes:**
  - `GET /workflows` and `GET /workflows/{id}`
  - `POST /workflows/{id}/runs` (supports background)
  - `GET /workflows/{id}/runs/{run_id}`
  - `POST /workflows/{id}/runs/{run_id}/cancel`
- **Other routes:**
  - `POST /agents/{id}/runs`, `GET /agents/{id}/runs/{run_id}`
  - `/sessions`, `/sessions/{id}/runs/{run_id}`
  - `GET /metrics`
  - `/traces`, `/traces/{trace_id}`
  - `/components/{id}/configs` (versioned component configs — a possible P2 replacement for DB-stored agent configs)

### 2.6 Issues found in the orchestrator (the original stays unchanged)

| # | Issue | Severity | For the new project |
|---|---|---|---|
| 1 | `backend/.env.local` and `frontend/.env.production` are **tracked in git**. The backend file holds values for Tavily, OpenWeather, Azure OpenAI and the DB URL (not printed). | **High** | **Rotate those keys** and untrack the files. New project: all `.env*` ignored except examples. |
| 2 | `agno>=1.0.0` in pyproject; lock pins 2.5.17; PyPI has 3.1.7 | Medium | Pin exactly. |
| 3 | CORS `allow_origins=["*"]` with credentials | Medium | Allow `http://localhost:3001` only. |
| 4 | Model provider hard-coded to Azure | Medium | Provider set by config. |
| 5 | Agno tables created with a private method (`_create_all_tables`) | Low | Use Agno's public behaviour. Exclude Agno's schema from Alembic. |
| 6 | `from main import registry` circular coupling | Low | Dependencies passed explicitly. |
| 7 | 671-line `main.py` | Low | `main.py` only wires the app. |
| 8 | `.coverage` files committed | Low | Ignored. |

---

## 3. Existing architecture and execution flow

### 3.1 Current orchestrator architecture

```mermaid
flowchart LR
  subgraph FE["Next.js 15 frontend :3000"]
    Pages["App Router pages<br/>agui, chats, agents, traces, proactive-intel"]
    Proxy["/api/proxy/[...path]<br/>route handler"]
    Pages --> Proxy
    Pages -. "direct calls (proactive-intel)" .-> API
  end

  subgraph BE["FastAPI + AgentOS :7777"]
    MW["AzureAuthMiddleware<br/>ChatTrackingMiddleware"]
    API["Routers: agents, teams, chats,<br/>config, agui, proactive, auth, mcp"]
    AOS["AgentOS run endpoints<br/>/agents|teams/{id}/runs (SSE)"]
    REG["AgentRegistry<br/>(in-memory)"]
    FAC["factory.build_agent/team_from_config"]
    TOOLS["tools_catalog<br/>Tavily, Weather, Wikipedia, Charts, MCP"]
    SCHED["proactive scheduler loop"]
    MW --> API
    MW --> AOS
    API --> REG
    AOS --> REG
    REG --> FAC --> TOOLS
  end

  subgraph DB["PostgreSQL 16 + pgvector :5433"]
    APPT["public: agents, teams, chats,<br/>users, heartbeats, runs..."]
    AGNO["ai: agno_sessions, knowledge_chunks,<br/>traces, spans"]
  end

  Proxy --> MW
  API --> APPT
  FAC --> AGNO
  SCHED --> APPT
  TOOLS --> EXT["Azure OpenAI, Tavily,<br/>OpenWeather, Google Places"]
```

### 3.2 Current chat execution flow (Super Agent team)

```mermaid
sequenceDiagram
  participant U as Browser
  participant P as Next proxy
  participant A as AgentOS /teams/super-agent/runs
  participant T as Team leader (LLM)
  participant M as Member agent
  participant D as Postgres (ai.agno_sessions)
  U->>P: POST message
  P->>A: forward
  A->>T: team.arun(stream=True)
  T->>T: LLM decides which members to call
  T->>M: delegate_task_to_member
  M-->>T: result
  T-->>A: stream events
  A-->>U: SSE events
  T->>D: store session, events, memories
```

---

## 4. Reusable components inventory

The orchestrator is a **reference**. We take a pattern only when it fits this product, and leave out the rest.

### 4.1 What we take

| Component | Location in orchestrator | What it gives us |
|---|---|---|
| AgentOS with `base_app` | `backend/main.py` | Agno runtime plus our own routes on one app (pattern only — not its custom lifespan chain, placeholder agent or middlewares) |
| `get_session()` + cached engine | `backend/db/session.py` | Async DB access |
| `JSONType`, `UUIDType`, `Base` | `backend/db/models/agent.py`, `db/base.py` | Same models on Postgres and SQLite tests |
| Async Alembic env + timestamped filenames | `backend/migrations/env.py`, `alembic.ini` | Migration setup |
| Repository and schema patterns | `backend/repositories/`, `schemas/` | Clean layering |
| Tool name → factory catalog | `backend/registry/tools_catalog.py` | Tool registration by name |
| Agent factory idea | `backend/registry/factory.py` | One place builds agents |
| Test conftest (SQLite, ASGI client) | `backend/tests/conftest.py` | Fast tests |
| ruff / pytest / coverage config | `backend/pyproject.toml` | Same quality rules |
| API proxy route | `frontend/src/app/api/proxy/[...path]/route.ts` | No CORS, backend URL hidden |
| Feature-module layout + `useQuery` | `frontend/src/modules/proactive-intel/` | Frontend structure |
| Atoms (Button, Spinner, Skeleton, StatusBadge) | `frontend/src/modules/agui/components/atoms/` | Basic UI |
| vitest config | `frontend/vitest.config.ts` | Frontend tests |

### 4.2 What we deliberately leave out

| Orchestrator feature | Why not |
|---|---|
| Team + LLM coordinator, regex routing shortcuts | Fixed pipeline → Workflow |
| DB-stored agent configs, seeds, in-memory registry refresh | Agent specs in code (git gives versioning). Revisit with AgentOS component configs in P2. |
| Placeholder agent, custom lifespan chain, chat-tracking middleware, title generation | Chat-product specifics |
| Agent memory, user memories, chat history | One-shot runs |
| Azure AD auth, MSAL, zustand auth store | No auth in POC |
| Knowledge upload, pgvector, RAG | Not needed (section 9.5) |
| AG-UI, SSE hub, trace-engine reducer, private traces-ui packages | Polling is enough; AgentOS `/traces` covers debugging |
| Proactive scheduler / heartbeats | Monitoring is P2 |
| axios client, ECharts, Storybook, Terraform | Not needed for POC |

---

## 5. Codebase reuse and gap analysis

| Existing component | Current implementation | Source files | Reusable? | Changes | POC? | Classification |
|---|---|---|---|---|---|---|
| AgentOS | Wraps app; placeholder agent; agents pushed in after DB load | `main.py` | Yes | Register workflow + 5 agents at construction (no placeholder); default lifespan; product routes on `base_app` | Yes | **Adapt** |
| Agno `PostgresDb` | Attached to every agent for sessions/memory | `registry/factory.py` | Yes | Attach to the **workflow** for run storage; no memory | Yes | **Adapt** |
| Agno tracing | `setup_tracing` + openinference instrumentation | `main.py` | Yes | Use `AgentOS(tracing=...)` behind a setting; confirm deps in M5 | Yes (optional toggle) | **Adapt** |
| DB session / types / base | As above | `db/` | Yes | None | Yes | **Reuse unchanged** |
| Alembic env | Async, timestamped | `migrations/env.py` | Yes | Our models only; **exclude Agno's schema** from autogenerate | Yes | **Adapt** |
| Repository / schema patterns | Class per table; Base/Create/Config | `repositories/`, `schemas/` | Yes | New tables/schemas | Yes | **Adapt** |
| Tools catalog | Name → factory | `registry/tools_catalog.py` | Yes | Tavily only | Yes | **Adapt** |
| Agent factory | Azure-only, memory, history | `registry/factory.py` | Partly | Provider switch; `output_schema`, `tool_call_limit`, `retries`; no memory/history | Yes | **Adapt** |
| Team orchestration | Super Agent | `registry/factory.py` | No | — | No | **Build new**: Workflow |
| Background run lifecycle | Own status rows + `create_task` | `services/proactive/` | Pattern only | Replaced by AgentOS background runs | Yes | **Not required** (AgentOS covers it) |
| Execution logs / token metrics | Read from Agno sessions in `api/traces.py` | `api/traces.py` | Idea | Read from Agno workflow run via our status endpoint | Yes | **Adapt** |
| Settings | Scattered `os.environ` | many | No | — | Yes | **Build new**: `pydantic-settings` |
| Error handlers | Ad hoc | `api/` | No | — | Yes | **Build new** |
| Test conftest | SQLite, ASGI | `tests/conftest.py` | Yes | Agno `SqliteDb` for tests; fake model | Yes | **Adapt** |
| API proxy | Allowlist route | `frontend/src/app/api/proxy/...` | Yes | Allowlist `api/v1/` only | Yes | **Adapt** |
| Module layout, hooks, atoms | proactive-intel, agui | `frontend/src/modules/` | Yes | Polling hook; copy atoms | Yes | **Adapt** |
| Auth, registry, seeds, knowledge, AG-UI, scheduler, charts | — | various | — | — | No | **Not required for POC** |

**Deviations from the orchestrator, and why:**

1. **Workflow instead of Team.** The step order is fixed, so this guarantees it and gives predictable cost and testability.
2. **Agent specs in code, not DB.** Prompt changes are reviewed in git, which meets the "agent versioning" requirement directly.
3. **Typed settings.** One validated place for environment variables.
4. **No memory or history.** Each run is one-shot.
5. **AgentOS used more fully.** We use its workflow runs, background mode, metrics and traces. The orchestrator built its own versions of some of these.

---

## 6. Product requirements analysis and prioritisation

### 6.1 Analysis

| Item | Summary |
|---|---|
| **Core problem** | Market research is slow, costly and scattered; raw data still needs interpreting. |
| **Target users** | Founders, SMBs, analysts, marketing/strategy teams, investors, consultants. POC user: you, locally. |
| **Primary use cases** | Profile a company; find and compare competitors; spot trends, gaps, risks; get prioritised recommendations; export a sourced report. |
| **Core workflow** | Input → validate → research → fact-check → analyse → recommend → write → review/export. |
| **Functional requirements** | Name or URL input; profile; 3–5 competitors; comparison; SWOT; trends; opportunities; risks; recommendations (rationale, evidence, impact, next steps); fact / interpretation / prediction labels; confidence; sources; status tracking; history; PDF. |
| **Non-functional** | Accuracy and traceability first; bounded cost; API never blocked by a run; partial results on failure; per-step logs and tokens; local infrastructure only; secrets outside git. |
| **External integrations** | OpenAI API and Tavily. Business, news and financial-data APIs come later. |

### 6.2 Missing requirements and assumptions

| Gap | Assumption for POC |
|---|---|
| LLM provider / keys | OpenAI (Q1 answered); models set by config |
| Language and region | English sources, global |
| Run-time and cost targets | Measured in M10, then set |
| Direct vs indirect competitors | Mostly direct; each labelled |
| Freshness of "recent" news | Last 12 months, dated where possible |
| Little public data | Report says "not publicly available" — never guesses |
| Ambiguous company names | Researcher states which entity it matched; URL input avoids this; confirm step is P1 |
| Scraping limits | Tavily search + extraction of public pages only; short excerpts stored |
| Users / ownership | Single local user, no login |

### 6.3 Feature prioritisation matrix

| Feature | Priority | Reason |
|---|---|---|
| Start research by name or URL | **P0** | Entry point |
| Company profile with sources | **P0** | Core output; sources give trust |
| 3–5 competitors + basic comparison | **P0** | Core value |
| Fact-checking with confidence and warnings | **P0** | Spec calls it essential |
| SWOT, trends, opportunities, risks | **P0** | Core analysis |
| Recommendations with rationale, evidence, impact, next steps | **P0** | "Insight to action" |
| Five agents in a fixed Workflow on AgentOS | **P0** | Mandatory; minimal form |
| 12-section report with references | **P0** | The deliverable |
| Background run + status/progress | **P0** | Runs take minutes |
| Step logs, duration, tokens | **P0** | Nearly free from AgentOS |
| PostgreSQL persistence | **P0** | Mandatory |
| Basic Next.js UI | **P0** | Needed to demo |
| PDF (browser print) | **P0** | Server PDF is P1 |
| Fact-checker requests more research (`Loop`/`Condition`) | P1 | First measure how often claims fail |
| Parallel company / competitor research | P1 | Speed; more complexity |
| Live progress via SSE (AgentOS streaming) | P1 | Polling enough now |
| Entity confirmation for ambiguous names | P1 | Accuracy |
| Cost in currency | P1 | Tokens recorded now |
| Server-side PDF | P1 | Polish |
| Authentication (AgentOS `authorization` or own) | P1 | Before multiple users |
| Re-run / cancel button in UI | P1 | Cancel endpoint exists already |
| Charts | P2 | Reuse orchestrator ECharts patterns |
| History comparison, multi-company | P2 | Needs normalised tables |
| Follow-up Q&A on reports (RAG) | P2 | Retrieval over stored sources |
| Monitoring / scheduled reports | P2 | Scheduler |
| Editable agent configs (AgentOS component configs) | P2 | Admin need |
| Redis / separate workers | P2 | Only if measured need |
| Industry agents, workspaces, billing, CRM/BI integrations, paid data | P3 | SaaS / enterprise phases |

---

## 7. Mandatory POC scope

Each feature lists its **purpose, workflow, backend, frontend, agent, DB, reuse, dependencies and acceptance criteria**.

**F1 — Start a research run**
- Workflow: user enters a name or URL → Start → run page.
- Backend: `POST /api/v1/research` validates input (URL vs name, normalised, no localhost/private IPs). It inserts `research_runs`, then calls `workflow.arun(input, session_id=<research id>, background=True)`, stores the returned `agno_run_id`, and returns `202`.
- Frontend: `NewResearchForm` on `/` → redirect to `/research/{id}`.
- Agent: none directly.
- DB: insert `research_runs`.
- Depends on: M3, M4, M7.
- Accept:
  - Valid input → 202 within 500 ms.
  - Empty, too long, bad URL, or private host → 422 with a clear message.

**F2 — Company profile with sources**
- Researcher step (Tavily search + extract, `output_schema=ResearchFindings`). Its executor:
  - copies Tavily results from `RunOutput.tools` into `research_sources`, numbered;
  - flattens the profile into claims C1…Cn.
- Frontend: "Company overview" with source numbers.
- Accept, on 5 benchmark companies:
  - core fields filled, or marked "not publicly available";
  - every fact has ≥1 source.

**F3 — Competitors and comparison**
- Researcher finds 3–5 competitors (direct/indirect). The Analyst builds a comparison table.
- Frontend: `CompetitorTable`.
- Accept: ≥3 competitors for 4 of the 5 benchmark companies, each with a website and a source.

**F4 — Fact-checking and confidence**
- Validate step:
  1. Deterministic check first: a claim with no source, or whose URL was not retrieved, is marked `unsupported` (no LLM cost).
  2. The Fact-Checker agent then judges the remaining claims against the stored excerpts, in batches.
  3. Gate: `contradicted` claims are dropped; `unsupported` claims are kept but flagged.
- Frontend: `ConfidenceBadge`, "Verification warnings" panel.
- Accept:
  - every claim has a verdict and a confidence;
  - a planted claim with a fake URL is flagged in a unit test.

**F5 — Market analysis**
- Analyst gets only validated claims, with their IDs. It returns SWOT, trends, opportunities, risks and data gaps; every item is labelled fact / interpretation / prediction and cites claim IDs.
- Accept: code confirms every cited ID exists; labels are present.

**F6 — Recommendations**
- Strategist returns 3–7 prioritised items, each with rationale, evidence IDs, impact, next steps and risks. Code checks that the cited IDs exist.
- Accept: all fields present; priorities unique.

**F7 — Report**
- The Report Writer writes prose only: executive summary, industry overview, next steps.
- `report_assembler` (deterministic code) builds the 12-section JSON from stored data and saves it to `research_runs.report`.
- Accept:
  - all 12 sections present;
  - every reference number resolves to a stored source.

**F8 — Background execution and status**
- AgentOS background run. `GET /api/v1/research/{id}` merges our row with Agno's stored run: status, steps, metrics.
- On startup, runs left `running` by a previous process are marked failed.
- Frontend: `ResearchProgress` polls every 3 s.
- Accept:
  - API responsive during a run;
  - restart mid-run → run shows failed with a reason;
  - Strategist failure → `partial` report.

**F9 — Logs and token usage**
- Per-step status, duration and tokens come from the Agno run (AgentOS). Totals are copied to `research_runs` when the run finishes, for the history list.
- Optional AgentOS traces are available for debugging.
- Accept: totals match the step sums; failed steps show the error.

**F10 — Minimal UI**
- Pages: `/` (form + history) and `/research/[id]` (progress, then report). Skeletons, error states, empty state.

**F11 — PDF**
- `window.print()` with a print stylesheet.
- Accept: "Save as PDF" in Chrome is readable.

### 7.1 Excluded from POC

Authentication · billing · Redis/queues · SSE/AG-UI streaming UI · RAG · agent memory/history · Teams · DB-stored agent configs · charts · monitoring/schedules · multi-company · history comparison · Q&A · re-run/cancel UI · server PDF · paid data APIs · cloud, app containers, CI/CD · Storybook.

---

## 8. Recommended local system architecture

**Style:** a modular monolith — one AgentOS/FastAPI process, one Next.js process and one Postgres container.

### 8.1 Proposed architecture

```mermaid
flowchart LR
  subgraph FE["Next.js 15 :3001"]
    UI["Pages: / and /research/[id]"]
    MOD["modules/research<br/>api, hooks, components"]
    PX["/api/proxy/[...path]"]
    UI --> MOD --> PX
  end

  subgraph BE["AgentOS app :8000 (single process)"]
    subgraph BASE["base_app (our routes)"]
      R["api/research.py<br/>/api/v1/research"]
      S["services/research_service.py"]
      REPO["repositories/*"]
      R --> S --> REPO
    end
    subgraph AOS["AgentOS built-in routes"]
      WR["/workflows/{id}/runs<br/>background, status, cancel"]
      AR["/agents/{id}/runs<br/>(tune one agent)"]
      OBS["/sessions /metrics /traces"]
    end
    WF["workflow/research_workflow.py<br/>Agno Workflow, 5 steps"]
    AG["registry/factory.py<br/>5 agents from agents/*.py"]
    CHK["claims, citation_check,<br/>report_assembler"]
    S -- "arun(background=True)<br/>aget_run()" --> WF
    WR --> WF
    WF --> AG
    WF --> CHK
    WF --> REPO
  end

  subgraph PG["Local PostgreSQL :5432"]
    PUB["public: research_runs,<br/>research_sources (Alembic)"]
    AI["ai: Agno sessions, runs,<br/>metrics, traces (Agno-managed)"]
  end

  PX --> R
  REPO --> PUB
  WF --> AI
  AG --> LLM["LLM API"]
  AG --> TV["Tavily API"]
```

### 8.2 Frontend ↔ backend flow

```mermaid
sequenceDiagram
  participant B as Browser
  participant N as Next proxy :3001
  participant F as Product API (base_app)
  participant W as Agno Workflow (AgentOS)
  participant D as Postgres
  B->>N: POST /api/proxy/api/v1/research {query}
  N->>F: POST /api/v1/research
  F->>D: insert research_runs (running)
  F->>W: arun(input, session_id=id, background=True)
  W-->>F: run_id (returns immediately)
  F->>D: save agno_run_id
  F-->>B: 202 {id, status}
  Note over W,D: steps execute in background,<br/>Agno stores run + step outputs + metrics
  loop every 3 s until terminal
    B->>N: GET /api/proxy/api/v1/research/{id}
    N->>F: forward
    F->>D: read research_runs
    F->>W: aget_run(run_id, session_id)
    F-->>B: 200 {status, steps[], tokens}
  end
  B->>N: GET /api/proxy/api/v1/research/{id}/report
  F-->>B: 200 report JSON
```

### 8.3 Agent execution flow

```mermaid
flowchart TD
  A["Input: name or URL"] --> R1["Step 1 Researcher<br/>Tavily search + extract<br/>output: ResearchFindings"]
  R1 --> H["Save sources, number them<br/>Flatten findings into claims C1..Cn"]
  H --> V0{"Deterministic check<br/>source retrieved?"}
  V0 -- no --> U["mark unsupported"]
  V0 -- yes --> V["Step 2 Fact-Checker<br/>claims vs source excerpts<br/>output: ValidationResult"]
  U --> G["Gate: drop contradicted,<br/>flag unsupported"]
  V --> G
  G --> AN["Step 3 Analyst<br/>output: AnalysisFindings"]
  AN --> ST["Step 4 Strategist<br/>output: StrategyRecommendations"]
  ST --> X["Code check: cited IDs exist"]
  X --> RW["Step 5 Report Writer<br/>output: ReportNarrative"]
  RW --> AS["report_assembler<br/>12-section report JSON"]
  AS --> DONE["Save report, status succeeded"]
  AN -. failure .-> PART["Assemble partial report<br/>status partial"]
  ST -. failure .-> PART
  RW -. failure .-> PART
  R1 -. failure .-> FAIL["status failed"]
```

If research fails, the run fails, because there is nothing to show. If a later step fails, the run is **partial**: we assemble a report from what exists and mark it clearly.

### 8.4 Database interaction flow

1. The product API inserts a `research_runs` row and commits.
2. Agno writes the workflow run (steps, outputs, metrics) into its own tables as the run progresses.
3. The Researcher executor upserts `research_sources`.
4. The final step, or a failure handler, writes the report, token totals, final status and `finished_at` to `research_runs`.
5. On startup, `research_runs` left in `running` are reconciled with Agno's stored run. If it isn't finished there either, the run is marked `failed` ("interrupted by restart").

### 8.5 Error handling and logging

| Layer | Approach |
|---|---|
| Input | Pydantic → 422 |
| Domain | `NotFoundError` → 404, `ReportNotReadyError` → 409, `CapacityError` → 429; body `{"detail","code"}` |
| Unexpected | Global handler → 500; traceback only in logs |
| Agent calls | Agno `retries=2, exponential_backoff=True`; `asyncio.wait_for` per step; schema failure → one re-ask |
| Workflow | Step errors are recorded in the Agno run. Our failure handler sets `failed` or `partial` and assembles whatever exists. |
| Logging | Standard `logging`; one setup in `core/logging.py`; `run_id` and `step` on every line; no keys or prompts logged. AgentOS traces for deep debugging. |

### 8.6 Configuration and dependencies

- **Settings.** `core/config.py` holds `Settings(BaseSettings)`, covering:
  - DB URL;
  - OpenAI key and default model, plus optional per-agent model overrides;
  - API keys;
  - Tavily key;
  - max concurrent runs;
  - step timeouts;
  - CORS origins;
  - tracing on/off;
  - log level.
- **Dependencies.** Managed with **uv**, with exact pins. Runtime:
  - `agno==2.5.17`, `fastapi`, `uvicorn`
  - `sqlalchemy[asyncio]`, `asyncpg`, `psycopg[binary]` (Agno's `PostgresDb` uses a sync driver), `alembic`
  - `pydantic-settings`
  - `openai`, `tavily-python`, `httpx`
  - OpenTelemetry packages, only if `tracing` needs them (confirmed in M5)
- **Dev dependencies:** `pytest`, `pytest-asyncio`, `pytest-cov`, `aiosqlite`, `ruff`, `bandit`.

### 8.7 Mapping to the orchestrator

| Orchestrator | New product |
|---|---|
| `AgentOS(agents=[placeholder], base_app=...)` + custom lifespan | `AgentOS(agents=[5 agents], workflows=[research], db=..., base_app=...)`, default lifespan + one startup reconcile |
| Team (`build_team_from_config`) | `workflow/research_workflow.py` |
| `seeds/default_agents.py` | `agents/<agent>.py` specs in code |
| `registry/factory.py`, `tools_catalog.py` | Same roles; model set by config (OpenAI) |
| `services/proactive/*` own run lifecycle | AgentOS background workflow runs |
| `api/traces.py` reading Agno sessions | AgentOS `/sessions`, `/metrics`, `/traces` + our status endpoint |
| `db/`, `repositories/`, `schemas/` | Same patterns |
| `evals/rag_groundedness.py` (logs only) | `workflow/citation_check.py` (enforcing) |
| `src/modules/proactive-intel/` | `src/modules/research/` |

---

## 9. Agno agent architecture

### 9.1 Which approach?

| Option | Verdict | Reason |
|---|---|---|
| Single agent | No | One huge prompt; no independent validation; poor traceability |
| Independent agents called by plain Python | Fallback only | Re-invents step sequencing that Agno already has |
| Agno Team | No | Leader LLM decides who works next → extra calls, possible skipped or reordered steps, results passed as text through the leader. The orchestrator needed regex shortcuts to force routing. |
| **Agno Workflow on AgentOS** | **Yes** | Order guaranteed in code; structured outputs passed directly; code checks between steps; `Parallel`/`Loop`/`Condition` ready for MVP; AgentOS gives run management and observability |

The spec supports this choice. It asks for disagreements to be resolved "using evidence-based validation rather than uncontrolled agent conversations", and for "bounded agent interactions".

A Team still makes sense later, for interactive features where the path depends on the question, such as follow-up Q&A (P2). If needed, a Team can also run inside a single workflow step (`Step(team=...)`).

There is also a minimal variant: 3 agents (Researcher, Analyst+Strategist, Fact-Checker). It saves about two LLM calls per run but departs from the spec. **Recommended: five agents, with the Report Writer limited to prose** (Q3).

### 9.2 Agents

| Agent | Responsibility | Tools | Output schema | Limits |
|---|---|---|---|---|
| **Researcher** | Identify company, profile, 3–5 competitors, recent news | `TavilyTools(enable_search, enable_extract, format="json", search_depth="basic")` | `ResearchFindings` | `tool_call_limit=15`, 300 s |
| **Fact-Checker** | Judge claims against stored excerpts only | none | `ValidationResult` | ≤25 claims per batch, 120 s |
| **Analyst** | Comparison, SWOT, trends, opportunities, risks, gaps | none | `AnalysisFindings` | 120 s |
| **Strategist** | 3–7 prioritised recommendations | none | `StrategyRecommendations` | 120 s |
| **Report Writer** | Executive summary, industry overview, next steps (prose only) | none | `ReportNarrative` | 120 s |

All agents use one configurable model by default, with per-agent overrides in settings. For example, a cheaper model for the Fact-Checker and a stronger one for the Analyst and Strategist.

All five agents are also registered with AgentOS. You can then run any single agent from `/docs` (`POST /agents/{id}/runs`) to tune its prompt without running the whole pipeline.

### 9.3 Structured output schemas (sketch, not final code)

```python
class SourcedText(BaseModel):
    text: str
    source_urls: list[HttpUrl] = []
    kind: Literal["fact", "interpretation", "prediction"] = "fact"

class CompanyProfile(BaseModel):
    name: str
    website: HttpUrl | None
    identity_note: SourcedText            # which entity was matched and why
    description: SourcedText
    industry: SourcedText
    products_services: list[SourcedText]
    customer_segments: list[SourcedText]
    geographic_presence: list[SourcedText]
    business_model: SourcedText | None    # None = not publicly available
    pricing: SourcedText | None
    funding: SourcedText | None
    recent_developments: list[SourcedText]
    positioning_usp: SourcedText | None

class Competitor(BaseModel):
    name: str
    website: HttpUrl | None
    relation: Literal["direct", "indirect"]
    description: SourcedText
    offerings: list[SourcedText]
    pricing: SourcedText | None
    target_segments: list[SourcedText]
    positioning: SourcedText | None

class ResearchFindings(BaseModel):
    company: CompanyProfile
    competitors: list[Competitor] = Field(min_length=1, max_length=5)
    competitor_shortfall_reason: str | None   # required if fewer than 3
    industry_context: list[SourcedText]

# Code then flattens every SourcedText into Claim(id="C1", text, source_urls, kind, section)

class ClaimVerdict(BaseModel):
    claim_id: str
    verdict: Literal["supported", "partially_supported", "unsupported", "contradicted"]
    confidence: Literal["high", "medium", "low"]
    reason: str

class ValidationResult(BaseModel):
    verdicts: list[ClaimVerdict]

class Finding(BaseModel):
    id: str                                   # "A1"
    text: str
    kind: Literal["fact", "interpretation", "prediction"]
    evidence_claim_ids: list[str] = Field(min_length=1)

class AnalysisFindings(BaseModel):
    comparison: list[ComparisonRow]
    swot: Swot
    trends: list[Finding]
    opportunities: list[Finding]
    risks: list[Finding]
    data_gaps: list[str]

class Recommendation(BaseModel):
    priority: int
    title: str
    rationale: str
    evidence_ids: list[str]
    impact: Literal["high", "medium", "low"]
    next_steps: list[str]
    risks_tradeoffs: list[str]

class ReportNarrative(BaseModel):
    executive_summary: str
    industry_overview: str
    actionable_next_steps: list[str]
```

### 9.4 Workflow and AgentOS wiring (sketch)

```python
research_workflow = Workflow(
    id="market-research",
    name="Market research",
    db=agno_db,                                   # PostgresDb (sync driver), Agno's own schema
    steps=[
        Step(name="research",   executor=research_step),   # agent run + save sources + flatten claims
        Step(name="validate",   executor=validate_step),   # deterministic check + fact-checker + gate
        Step(name="analyse",    executor=analyse_step),
        Step(name="strategise", executor=strategise_step),
        Step(name="write",      executor=write_step),      # narrative + report_assembler + save report
    ],
)

agent_os = AgentOS(
    agents=build_all_agents(settings),            # for single-agent tuning via /docs
    workflows=[research_workflow],
    db=agno_db,
    base_app=product_app,                         # our /api/v1/research routes
    tracing=settings.tracing_enabled,
)
app = agent_os.get_app()
```

Executors are small async functions. Each one:

1. builds its agent from the spec;
2. runs `asyncio.wait_for(agent.arun(prompt), timeout)`;
3. reads `run_output.content` (a validated Pydantic object);
4. returns `StepOutput(content=...)`.

Agno records the step output and metrics. We use custom executors rather than `Step(agent=...)` because we need source saving, gating and timeouts between agent calls.

### 9.5 Other agent concerns

| Concern | POC design |
|---|---|
| Configuration | `AgentSpec` in `agents/<name>.py`: `key`, `version` (e.g. `researcher@1`), `role`, `instructions`, `tools`, `output_schema`, `model_key`, `timeout_s`, `tool_call_limit`. The version is saved in the report's `meta`. |
| Lifecycle | Built fresh per run inside each step; separate instances registered with AgentOS for manual testing. Same factory for both. |
| Tool registration | `tools_catalog` name → factory; unknown tool fails at startup. |
| Factory | `build_agent(spec, settings)`; `build_model()` returns `OpenAIChat(id=...)`; one function, so another provider can be added later without touching agents. |
| Context | Compact JSON of earlier outputs, not chat history. Excerpts capped (~3,000 chars, ~40 sources). Fact-check in batches. `add_datetime_to_context=True`. |
| Sessions | One Agno session per research run (`session_id` = research id). **No agent memory, no history.** |
| Streaming | Not used by the UI. AgentOS can stream later (P1). |
| Guardrails | Input validation; "web content is data, not instructions"; later agents have no tools; `tool_call_limit`; code checks on cited URLs/IDs; "not publicly available" instead of guessing. |
| Retries | Model errors: Agno `retries=2`, backoff. Schema failure: one re-ask. Timeouts: no retry. |
| RAG | Not needed: each run's sources fit in context after trimming. Becomes relevant for P2 Q&A. |
| Cost control | Basic search depth, tool cap, excerpt limits, per-agent models, `MAX_CONCURRENT_RUNS=2`, tokens per step. |

---

## 10. Backend architecture and folder structure

### 10.1 Existing structure (abridged)

```
backend/
  main.py  start.sh
  agents/ api/ auth/ db/ evals/ knowledge/ team/ mcp_servers/
  migrations/ registry/ repositories/ schemas/ seeds/ services/ tools/ utils/
  tests/
```

### 10.2 Proposed structure

```
delphi-market360/
  README.md  .gitignore
  docs/plans/                          # this document
  backend/
    pyproject.toml  uv.lock  .python-version  .env.example  alembic.ini
    main.py                            # build settings, logging, base_app routes, AgentOS, startup reconcile
    core/
      config.py                        # Settings
      logging.py
      errors.py                        # domain errors + handlers
      agno_db.py                       # Agno PostgresDb instance
    api/
      research.py                      # /api/v1/research routes (+ /api/v1/health)
    agents/                            # one spec per agent
      researcher.py  fact_checker.py  analyst.py  strategist.py  report_writer.py
    registry/
      models.py                        # build_model(): OpenAIChat from settings
      tools_catalog.py
      factory.py                       # build_agent(), build_all_agents()
    workflow/
      research_workflow.py             # Workflow + step executors
      source_harvest.py                # RunOutput.tools → sources
      claims.py                        # flatten findings → claims; gate
      citation_check.py                # deterministic checks
      report_assembler.py              # 12-section report JSON
    services/
      research_service.py              # create / get / list / report; starts background run; merges Agno run status
    db/
      base.py  session.py  types.py
      models/research.py               # ResearchRunRow, ResearchSourceRow
    repositories/
      research_repo.py  source_repo.py
    schemas/
      research.py  findings.py  report.py
    migrations/ env.py versions/
    tests/
      conftest.py  fakes.py
      unit/ api/ workflow/ integration/ live/
  frontend/                            # section 11
```

### 10.3 Why each module exists

| Module | Reason |
|---|---|
| `core/` | Settings, logging, errors and the Agno DB in one place |
| `api/` | HTTP only; product-specific contract |
| `agents/` | Prompts and schemas per agent; git diff = version history |
| `registry/` | Builds models, tools and agents |
| `workflow/` | Agno orchestration plus the code checks that make output trustworthy |
| `services/` | Use cases; joins our tables with the Agno run |
| `db/`, `repositories/`, `schemas/` | Same layering as orchestrator |

### 10.4 Reused, new and changed

- **Reused:** DB session/types, Alembic env, repository and schema patterns, tools catalog, test conftest, lint/test config, AgentOS + `base_app` pattern.
- **New:** settings, error handlers, Workflow, structured outputs, citation checks, report assembler.
- **Changed:**
  - AgentOS gets its agents and workflow at construction, so no placeholder or registry refresh is needed.
  - Agno DB is attached to the workflow, not used for agent memory.
  - Product routes sit under `/api/v1`.

---

## 11. Next.js frontend architecture

### 11.1 Structure

```
frontend/
  package.json  next.config.ts  tsconfig.json  postcss.config.mjs  vitest.config.ts  .env.local.example
  src/
    app/
      layout.tsx                       # server component shell
      globals.css                      # Tailwind 4 + print styles
      page.tsx                         # new research + history
      research/[id]/page.tsx           # progress → report
      api/proxy/[...path]/route.ts     # allowlist: api/v1/
    components/ui/                     # Button, Spinner, Skeleton, StatusBadge, ErrorState
    lib/http.ts                        # fetch wrapper → ApiError
    modules/research/
      api/research-api.ts
      types/index.ts
      hooks/useQuery.ts  usePolling.ts  useCreateResearch.ts
      components/
        NewResearchForm.tsx  ResearchHistory.tsx  ResearchProgress.tsx  RunDetails.tsx
        report/ ReportView.tsx  CompanyOverview.tsx  CompetitorTable.tsx  SwotGrid.tsx
                FindingList.tsx  Recommendations.tsx  References.tsx  ConfidenceBadge.tsx  ValidationPanel.tsx
      lib/format.ts
    test/setup.ts
```

### 11.2 Rules

| Topic | Choice |
|---|---|
| Server vs client | Server layout. Pages render client components for the form, polling and report. One data path: browser → proxy → backend. |
| API layer | Only `modules/research/api` calls the backend. The UI uses our `/api/v1` routes only, not raw AgentOS routes — this keeps the frontend independent of Agno's API shape. |
| State | Local state + `useQuery`/`usePolling`; no zustand, React Query or axios |
| Forms | Controlled input; mirrors backend rules; shows 422 messages |
| Loading / errors | Skeletons, `ErrorState` with retry, 404 page |
| Auth / streaming | None |
| New libraries | None beyond Next, React, Tailwind and vitest |

---

## 12. PostgreSQL database design

Two **schemas** in one database:

- `public` — our product tables, managed by Alembic.
- Agno's schema (default `ai`) — Agno's own run, session and metrics tables, managed by Agno. Alembic's `env.py` skips this schema so autogenerate never touches it.

### 12.1 ERD (product tables)

```mermaid
erDiagram
  research_runs ||--o{ research_sources : has

  research_runs {
    uuid id PK
    text query
    varchar input_type
    varchar company_name
    text website_url
    varchar status
    text error
    varchar agno_session_id
    varchar agno_run_id
    jsonb report
    int total_input_tokens
    int total_output_tokens
    int total_tokens
    int duration_ms
    timestamptz created_at
    timestamptz finished_at
    timestamptz updated_at
  }

  research_sources {
    uuid id PK
    uuid research_run_id FK
    int ref_number
    text url
    varchar title
    text excerpt
    varchar retrieved_by
    timestamptz retrieved_at
  }
```

### 12.2 Tables

| Table | Key columns and constraints |
|---|---|
| `research_runs` | PK UUID (also used as Agno `session_id`). `query` 2–300 chars. `input_type` `name\|url`. `status` `running\|succeeded\|partial\|failed` (CHECK). `agno_run_id` set right after start. `report` JSONB, NULL until done. Token totals copied from the Agno run at the end for fast history listing. |
| `research_sources` | FK → `research_runs` ON DELETE CASCADE. `UNIQUE (research_run_id, url)`, `UNIQUE (research_run_id, ref_number)`. Excerpt capped at 3,000 chars. |

**Indexes:**
- `ix_research_runs_created_at` (DESC, for history)
- `ix_research_runs_status` (startup reconcile)
- `ix_research_runs_agno_run_id`
- the unique constraints double as lookup indexes for sources

**Why no step table:** Agno already stores each step's output, status and metrics for the workflow run. Duplicating that would mean two sources of truth.

**Why the report is JSONB:** the POC only reads the whole report. Normalised company and competitor tables come with history comparison in P2.

### 12.3 Migration strategy

- Async Alembic, timestamped files; first migration creates both tables; every migration has a working `downgrade()`.
- `env.py` uses `include_name` to ignore Agno's schema.
- Agno creates its own tables through its public behaviour. M5 confirms whether that happens on first use or needs an explicit call — the private `_create_all_tables()` used in the orchestrator's `start.sh` won't be used.
- Migrations are run by hand locally (`alembic upgrade head`), not on app start.

### 12.4 Session and agent persistence

- One Agno session per research run; the workflow run inside it holds the step outputs and metrics.
- No agent memory and no chat history.
- Prompts live in git; the agent versions are stored in the report's `meta`.

---

## 13. REST API specification

### 13.1 Our product endpoints (used by the frontend)

**Conventions:** prefix `/api/v1`; JSON; snake_case; ISO-8601 UTC; errors are `{"detail", "code"}`. No auth (local POC).

| # | Method + URL | Purpose | Request | Success | Errors | Uses | DB |
|---|---|---|---|---|---|---|---|
| 1 | `GET /api/v1/health` | Liveness + DB | — | `200 {"status":"ok","db":"ok"}` | `503` | — | `SELECT 1` |
| 2 | `POST /api/v1/research` | Start run | `{"query": "Notion" \| "https://notion.so"}` | `202 ResearchRunSummary` | `422` validation; `429 capacity_reached` (≥ `MAX_CONCURRENT_RUNS` running) | `workflow.arun(background=True)` | insert run, set `agno_run_id` |
| 3 | `GET /api/v1/research?limit=20&offset=0` | History | limit 1–100 | `200 {"items": ResearchRunSummary[], "total": int}` | `422` | — | select runs |
| 4 | `GET /api/v1/research/{id}` | Status + steps (polled) | UUID | `200 ResearchRunDetail` | `404 run_not_found`, `422` | `workflow.aget_run()` | run row + Agno run |
| 5 | `GET /api/v1/research/{id}/report` | Final report | UUID | `200 Report` | `404`, `409 report_not_ready` | — | run.report + sources |

**Input rules for `query`:**
- Trimmed, 2–300 characters.
- If it looks like a URL or domain, it must be http/https, and the host must not be localhost or a private, loopback or link-local IP.
- Otherwise it is treated as a company name.

**Response schemas:**

```text
ResearchRunSummary { id, query, input_type, company_name|null, status, created_at, finished_at|null }

ResearchRunDetail = ResearchRunSummary + {
  error|null, agno_run_id,
  current_step|null,
  totals: { input_tokens, output_tokens, total_tokens, duration_ms|null },
  steps: [ { step_name, status, duration_ms|null, input_tokens, output_tokens, error|null } ],   # from Agno run
  has_report
}

Report {
  meta: { run_id, query, company_name, generated_at, partial, agent_versions{} },
  executive_summary, company_overview, industry_overview,
  competitor_landscape[], competitive_comparison[], swot{}, market_trends[],
  opportunities[], risks[], recommendations[], next_steps[],
  references: [ { ref_number, url, title } ],
  validation: { claims_total, supported, partially_supported, unsupported, contradicted, warnings[] }
}
```

### 13.2 AgentOS endpoints (built in; for development and debugging)

| Endpoint | Use in POC |
|---|---|
| `POST /workflows/market-research/runs` | Run the full pipeline from `/docs` without the UI |
| `GET /workflows/market-research/runs/{run_id}` | Inspect a run's steps and outputs |
| `POST /workflows/market-research/runs/{run_id}/cancel` | Stop a runaway run (UI button is P1) |
| `POST /agents/{agent_id}/runs` | Tune one agent's prompt in isolation |
| `GET /sessions`, `/sessions/{id}/runs/{run_id}` | Browse stored runs |
| `GET /metrics` | Token usage overview |
| `GET /traces`, `/traces/{trace_id}` | Detailed traces (if tracing on) |

**Streaming:** not used by the UI. Next.js polls endpoint 4 every 3 s and stops on `succeeded | partial | failed`. AgentOS streaming can drive live progress in P1.

**Security note:** AgentOS routes are open locally. This is acceptable on localhost only. Before any shared use, protect them with AgentOS `authorization` (P1).

---

## 14. Local development setup

### 14.1 Software

| Tool | Version |
|---|---|
| Python | 3.12 |
| uv | latest |
| Node.js | 22 LTS (Next 15 needs ≥ 18.18) |
| npm | bundled (one lock file) |
| PostgreSQL | 14 or newer, installed locally (already on your machine) |

**Ports** avoid the orchestrator's 7777 and 3000. PostgreSQL uses its normal port; Market360 has its own database inside it:

| Service | Port |
|---|---|
| Backend | **8000** |
| Frontend | **3001** |
| Postgres | **5432** (your existing install) |

### 14.2 Steps (finalised in M2)

```bash
# one-time: create role + database in your local PostgreSQL (see README)

cd backend
uv sync
cp .env.example .env                          # fill keys; never commit .env
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8000  # Swagger: http://localhost:8000/docs

cd ../frontend
npm install
cp .env.local.example .env.local              # BACKEND_URL=http://localhost:8000
npm run dev -- --port 3001                    # http://localhost:3001
```

### 14.3 Environment variables (`backend/.env.example`)

```dotenv
DATABASE_URL=postgresql+asyncpg://market360:market360_dev@localhost:5432/market360
DEFAULT_MODEL=
MODEL_RESEARCHER=                   # optional per-agent overrides
MODEL_FACT_CHECKER=
OPENAI_API_KEY=
TAVILY_API_KEY=
MAX_CONCURRENT_RUNS=2
TRACING_ENABLED=false
CORS_ORIGINS=http://localhost:3001
LOG_LEVEL=INFO
```

The Agno DB URL is derived from `DATABASE_URL` (sync driver) in `core/agno_db.py`. Secrets live only in git-ignored `.env` files. A test checks that no `.env` file is tracked.

### 14.4 Debugging

- `/docs`: run the workflow or a single agent; inspect sessions, metrics and traces.
- `LOG_LEVEL=DEBUG` shows Agno tool calls.
- VS Code launch configs for uvicorn and pytest.
- `psql` into the container to inspect both schemas.

### 14.5 Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused :5432` | PostgreSQL service not running — start it (Windows: Services → postgresql) |
| Alembic tries to drop Agno tables | `include_name` filter missing in `env.py` |
| Agno "table not found" | Agno tables not created yet — see M5 decision |
| LLM 401/404 | Provider, key and model name don't match |
| Tavily 401/429 | Key, credits or rate limit |
| Proxy returns 502 | Backend not on 8000, or wrong `BACKEND_URL` |
| Run stuck in `running` after restart | Startup reconcile should fix it; check logs |
| Schema validation errors | Use a stronger model or set `parser_model` |

---

## 15. Milestone plan

Every milestone ends with green tests, a clean ruff run and your confirmation.

**M1 — Architecture approval** · 0.5 day
- Deliverables: this plan and your answers to 19.3.
- Done when: you approve it in chat.

**M2 — Project scaffold and local environment** · 0.5 day
- Create:
  - repo skeleton and git setup;
  - `pyproject.toml` + lock, `.python-version`, `.env.example`, `.gitignore`;
  - Next.js 15 app (TS, App Router, Tailwind 4, `src/`) on port 3001, with vitest;
  - README.
- Tests: one trivial backend test and one trivial frontend test.
- Done when: a fresh clone starts the DB, and both test runs pass.

**M3 — Backend foundation with AgentOS** · 1 day
- Reuse: DB session, types, base.
- Create:
  - `core/` (config, logging, errors, agno_db);
  - `main.py` with `base_app` + `AgentOS` (one trivial echo agent for now);
  - `api/research.py` with health only;
  - conftest.
- Tests:
  - settings succeed and fail as expected;
  - health returns 200 or 503;
  - error shapes;
  - CORS;
  - our routes and AgentOS routes coexist without conflict.
- Done when: `/docs` shows our health route and the AgentOS routes; coverage ≥ 90%.

**M4 — Product tables and migration** · 0.5 day
- Create: `db/models/research.py`, first migration (Agno schema excluded), two repositories, `schemas/research.py`.
- Tests:
  - repository CRUD;
  - cascade delete and unique constraints;
  - Postgres integration: `upgrade head`, then `downgrade base`.
- Done when: the migration is reviewed and the integration tests pass.

**M5 — Agno foundation and AgentOS spike** · 2 days
- Create:
  - `registry/` (models, tools_catalog, factory);
  - `schemas/findings.py`, `agents/researcher.py`;
  - `workflow/source_harvest.py`, `tests/fakes.py`;
  - a one-step workflow registered in AgentOS.
- **Spike — confirm with real calls:**
  1. Does the model return `output_schema` while also using tools? If not, use `parser_model`.
  2. Does `arun(background=True)` return a run id immediately, and does `aget_run()` show step status, outputs, metrics and errors?
  3. ~~How are Agno tables created?~~ Answered in M3: AgentOS auto-provisioning at startup.
  4. What does `tracing=True` need?
  5. How does a failing step show up?
- If (2) has gaps, the fallback is a 30-line `asyncio.create_task` wrapper around `workflow.arun()`. Runs are still stored by Agno.
- Tests:
  - model factory (default and per-agent model);
  - unknown tool;
  - source harvest from recorded Tavily JSON;
  - fake-model researcher returns a schema object.
- Done when: spike results are written down, and live Researcher outputs for 2 companies are saved as fixtures.

**M6 — All agents and the full workflow** · 3 days
- Create:
  - four agent specs;
  - `claims.py`, `citation_check.py`, `report_assembler.py`, `research_workflow.py`;
  - `schemas/report.py`.
- Tests:
  - claim IDs;
  - a planted fake URL is flagged;
  - the gate drops contradicted claims;
  - the assembler produces all 12 sections;
  - workflow with fake agents: happy path; analyst fails → partial; researcher fails → failed; timeout.
- Manual: full run on 3 companies via `/docs`; review with you; tune prompts and bump versions.
- Done when: 3 full reports have been produced and tokens are visible in AgentOS metrics.

**M7 — Product API** · 1 day
- Create: `services/research_service.py`; routes 2–5; startup reconcile.
- Tests:
  - contract tests for 202 / 200 / 404 / 409 / 422 / 429;
  - URL and private-IP validation;
  - status merged from a fake Agno run;
  - concurrency limit;
  - reconcile after a simulated restart.
- Done when: a run can be started and its report fetched via `/docs`, and the API stays responsive during a run.

**M8 — Next.js core screens** · 2 days
- Reuse: proxy, atoms, `useQuery` pattern, vitest setup.
- Create: section 11.1 files, using fixture data.
- Tests: components; `tsc --noEmit`; `next build`.
- Done when: all screens render from fixtures; ≥ 90% coverage for `modules/research`.

**M9 — Integration and PDF** · 1.5 days
- Work: real API client, polling, print CSS, error/404 states.
- Tests: API client with mocked fetch (404 / 409 / 502); manual end-to-end run and PDF.
- Done when: the full journey works locally.

**M10 — Validation and sign-off** · 2 days
- Benchmark: 5 companies you choose (mixed types, one URL input).
- Measure: outcome, time, tokens, Tavily calls, competitor count, % of claims supported, and a manual check of 10 claims per report.
- Optional: one Playwright smoke test.
- Done when: results are in `docs/plans/poc-results.md` and you make a go/no-go decision for the MVP.

**Total: ≈ 14 working days.**

---

## 16. Testing strategy and acceptance criteria

### 16.1 Strategy

| Type | How |
|---|---|
| Python unit | Claims, citation check, assembler, validators, model factory |
| API integration | `httpx.ASGITransport` against the full AgentOS app; SQLite for our tables, Agno `SqliteDb` for Agno storage |
| Postgres integration | Local DB; migrations; Agno `PostgresDb`; `@pytest.mark.integration` |
| Agent behaviour / mock LLM | Fake Agno model returning recorded JSON; fake agents for workflow tests |
| Tool tests | Recorded Tavily responses; no network |
| Live tests | `@pytest.mark.live`, skipped by default (cost) |
| Next.js | vitest + Testing Library; API client with mocked fetch |
| End-to-end | Manual checklist; optional Playwright smoke |
| Error scenarios | Timeout, schema failure, Tavily error, LLM 401, DB down, restart mid-run |
| Basic performance | Step/total durations from Agno metrics; GET p95 < 200 ms during a run |

Quality gates: ruff, ruff format, bandit, ≥ 90% coverage on new backend code and `modules/research`, `tsc --noEmit`, `next build`.

### 16.2 POC acceptance criteria

1. One command each starts the DB, backend and frontend, following the README.
2. At least 4 of 5 benchmark companies produce a report (`succeeded` or `partial`).
3. Each report has all 12 sections and ≥ 3 competitors, or a stated reason why not.
4. **100%** of facts cite a source actually retrieved in that run, or are visibly flagged.
5. At least 80% of the sampled "supported" claims are correct according to their source.
6. Every recommendation has all five required fields.
7. Live progress works, and a restart never leaves a run stuck.
8. Step durations and tokens are visible; totals match.
9. The browser PDF is readable.
10. All tests pass and there are no secrets in git.

Run-time and cost targets will be set after the M10 measurements.

---

## 17. Product roadmap

| Phase | Features | Technical changes | Effort | Done when |
|---|---|---|---|---|
| **1 — Local POC** | Section 7 | As planned | ~3 weeks | 16.2 met |
| **2 — Local MVP** | Research-more loop; parallel research; entity confirmation; live progress (AgentOS streaming); server PDF; cost in currency; auth; re-run/cancel UI; basic charts | `Loop`/`Condition`/`Parallel`; price config; AgentOS `authorization`; normalised company tables | 4–6 weeks | 20-company benchmark meets agreed targets |
| **3 — Advanced** | Report Q&A (RAG); history comparison; multi-company; monitoring and schedules; editable agent configs (AgentOS component configs); more data APIs | pgvector; scheduler | 6–10 weeks | Per-feature acceptance |
| **4 — Production readiness** | Security review, rate limits, backups, load tests, separate workers if needed, CI | Worker split only if measured | 3–5 weeks | Security + load checks pass |
| **5 — Cloud** | Only with your explicit approval | Plan first | TBD | Your approval |

---

## 18. Future production and cloud considerations (not in scope now)

- **Background runs live inside the API process.** With more than one instance, runs need a separate worker or job system.
- **AgentOS routes must be protected** (`authorization`) before any shared use.
- **Data sources need a review:** licensing, robots and terms of use, and a retention policy for stored excerpts.
- **Secrets** should move to a vault, and each tenant needs cost limits.
- **If Azure is chosen,** the orchestrator's `infra/` is a reference.

---

## 19. Technical risks and recommendations

### 19.1 Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Model doesn't return `output_schema` while also using tools | M5 spike; `parser_model`; one re-ask |
| R2 | Hallucinated facts or wrong attribution | URL check in code, fact-checker on excerpts, gate, UI flags |
| R3 | Wrong company matched | `identity_note` at the top of the report; URL input; P1 confirm step |
| R4 | Thin public data | "Not publicly available"; competitor shortfall reason |
| R5 | Cost per run higher than expected | Caps, basic search depth, excerpt limits, per-agent models; measured in M10 |
| R6 | Long run times | Progress page; parallel research in MVP |
| R7 | Prompt injection via web pages | Content treated as data; later agents have no tools; code checks |
| R8 | Tavily limits or outages | Clear step error; provider swappable via the tools catalog |
| R9 | AgentOS background behaviour differs from what we need (status, errors, restart) | M5 spike; small `create_task` fallback; startup reconcile |
| R10 | Agno 2.5 → 3.x upgrade | Pinned; separate task later |
| R11 | Agno's tables outside Alembic | Separate schema, excluded from Alembic; public creation path verified in M5 |
| R12 | SQLite tests hide Postgres differences | Postgres integration suite |
| R13 | Keys leaked in the orchestrator repo | **Rotate now** |

### 19.2 Recommendations

1. Rotate the orchestrator keys today.
2. Approve D1–D10, or tell me which to change.
3. Keep prompts versioned in git from the first run.
4. Save live outputs from M5 and M6 as test fixtures.
5. Choose the 5 benchmark companies early.

### 19.3 Open questions for you

| # | Question | My suggestion |
|---|---|---|
| Q1 | Which LLM provider? | **Answered: OpenAI.** Exact models confirmed in M5 against your account |
| Q2 | Fact-check right after research (D3)? | Yes |
| Q3 | Five agents or the three-agent variant? | Five; Report Writer prose only |
| Q4 | Tavily as the only data source, with enough credits? | Yes |
| Q5 | Project name? | **Answered: Delphi Market360** → `delphi-market360/`, one repo with `backend/` + `frontend/` |
| Q6 | Browser print-to-PDF acceptable for the POC? | Yes |
| Q7 | Benchmark companies you want included? | 5 of mixed types |

---

## 20. Recommended first implementation task

**Milestone 2 — project scaffold and local environment** (Q1 and Q5 now answered).

It creates:
- the repo skeleton;
- your local PostgreSQL on port 5432 (no Docker);
- a pinned `pyproject.toml` (agno 2.5.17, fastapi 0.135.3, sqlalchemy 2.0.49, alembic 1.18.4, asyncpg, psycopg, pydantic-settings, uvicorn, tavily-python, openai), using the orchestrator's ruff, pytest and coverage settings;
- `.env.example` and a `.gitignore` that excludes all `.env*` files except the examples;
- a Next.js 15 + TypeScript + Tailwind 4 app on port 3001, with vitest;
- a README with exact commands;
- one passing smoke test on each side.

It contains no agent logic, so it's quick to review and gives a clean base for M3, where AgentOS comes in.
