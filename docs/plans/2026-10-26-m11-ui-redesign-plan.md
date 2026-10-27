# M11 — UI redesign and charts (first MVP milestone)

**Date:** 2026-10-26 · **Status:** Draft for approval · **Design:** the approved Apple-inspired mockup
("Delphi Market360 — UI redesign": Home, Research in progress, Report dashboard)

## Goal

Build the approved design into the real app, on real data, so the app is ready for a management demo.
No change to how research works.

## What you get

| Screen | Built in M11 |
|---|---|
| **Everywhere** | Apple-style look: off-white page, white rounded cards, one blue accent, the device's own font (San Francisco / Segoe UI), frosted sticky header, gentle animations (off when the user prefers reduced motion), **dark mode** (follows the computer's setting). |
| **Home** | Big headline, one large search box, example chips, headline numbers, recent research as cards with trust score, "Five agents" section. |
| **Research in progress** | The 5 agents as a pipeline (done / running / waiting), elapsed timer, progress bar, and a step-by-step activity list built from what the API already returns (step started, step finished with its time and tokens). |
| **Report** | Headline band, 4 headline-number tiles, tabs (Overview, Competitors, Analysis, Recommendations, Sources), clickable citations that open a source panel, competitor cards with a profile panel, "show only verified claims" switch, comparison table, colour-coded SWOT, recommendation cards, sources list. PDF export keeps working (all tabs printed in order). |
| **Charts** | Evidence donut, where the evidence comes from (company sites vs others), claims verified per competitor, seconds and tokens per agent, and **key figures** (below). |

## Key figures (the one backend change)

The mockup's market-size and pricing charts need real numbers, but today numbers only exist inside sentences.
So the Analyst gets one new output field, `key_figures`: up to 8 numbers like
`{label: "Entry paid plan", company: "Craft", value: 6, unit: "USD per user/month", year: null, claim_ids: ["C31"]}`.

Code keeps a figure only if **the number appears in the text of a claim it cites** and that claim is not contradicted.
Anything else is dropped with a warning. The report then shows a bar chart per group of figures
(e.g. entry prices, market size). No sourced numbers → no chart; the section simply doesn't appear.

This keeps the rule: **no chart without a sourced number behind it.**

## What stays the same

- The research workflow, prompts (except the Analyst's new field), database and API shape. One new optional field
  in the report JSON (`key_figures`); old reports without it still open.
- Polling every 3 s. The live "Reading coda.io…" feed from the mockup needs streaming and comes in **M15 (Live progress)**.
- Letter tiles instead of company logos (real logos need an outside service — a later decision).

## Decisions (my choices; tell me if you disagree)

| # | Decision | Choice and why |
|---|---|---|
| D13 | Chart library | **None for now**: the charts are simple (bars, donut), drawn with SVG/CSS like the mockup. Lighter, matches the design exactly, prints well, no new dependency. ECharts later only if we need complex charts. |
| D15 | Dark mode | Follows the computer's setting; no toggle yet. |
| D16 | Fonts | System fonts only (no download): San Francisco on Mac/iPhone, Segoe UI on Windows. |

## Steps

1. Design tokens (colours light/dark, radius, shadows, type scale) in `globals.css`; shared header; base components (Card, Pill, Tabs, Switch, Drawer, Stat tile).
2. Home screen.
3. Progress screen (pipeline, timer, activity list from step data).
4. Report: header, stat tiles, tabs, Overview (summary with clickable citations, donut, source mix, company snapshot, recent developments).
5. Report: Competitors (cards, profile panel, table), Analysis (SWOT, trends, opportunities, risks), Recommendations, Sources (list + agent chart), source panel, verified-only switch.
6. Backend: `key_figures` in the Analyst schema and prompt (analyst@4), code check in `report_assembler`, tests; frontend key-figure charts.
7. Print/PDF stylesheet for the new layout; dark mode check; keyboard and screen-reader check (tabs, panels, citations).
8. Tests (frontend and backend), README screenshots section, CLAUDE.md, commit, zip.

## Done when

- All three screens match the approved design on real runs (Notion, Monzo, a failed run, a partial report).
- Every chart number traces to a verified source; a test proves a figure without a matching claim is dropped.
- Works by keyboard; panels close with the close button and clicking outside; reduced-motion respected.
- PDF export still readable; all tests, type check and build pass.

**Effort:** about 1 to 1.5 weeks. You verify by running the app and clicking through the three screens.
