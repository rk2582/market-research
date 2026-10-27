"""M10 benchmark — runs the full workflow for 5 companies with REAL OpenAI and Tavily (costs money).

Run from backend/ (keys must be in backend/.env):
    uv run python -m tests.live.benchmark
    uv run python -m tests.live.benchmark "Notion" "https://monzo.com"     # your own list
    uv run python -m tests.live.benchmark --from-saved   # rebuild poc-results.md from saved reports (free)

Companies run one after another (kind to Tavily's free-plan rate limit). Writes:
    docs/plans/poc-results.md                 scorecard against the POC acceptance criteria (plan §16.2),
                                              plus 10 sampled claims per company for YOU to check by hand
    docs/plans/benchmark/report-<name>.md     each report, readable (VS Code: Ctrl+Shift+V)
    docs/plans/benchmark/report-<name>.json   each report, full data
    docs/plans/benchmark/run-<name>.json      time and Tavily usage of that run (used by --from-saved)
The scorecard is rewritten after every company, so a crash never loses finished runs.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schemas.report import Report, ReportClaim

DEFAULT_COMPANIES = ["Notion", "https://monzo.com", "Facebook", "Canva", "Pipedrive"]
DOCS = Path(__file__).resolve().parents[3] / "docs" / "plans"
SAMPLE_SIZE = 10
SAMPLE_SEED = 42  # same report → same sample, so a re-check sees the same claims


# ---------------------------------------------------------------------------
# Counting Tavily usage
# ---------------------------------------------------------------------------


class CountingTavily:
    """Wraps the real Tavily client and counts requests and credits (basic search = 1 credit,
    basic extract = 1 credit per 5 URLs)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.searches = 0
        self.extracts = 0
        self.credits = 0

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        self.searches += 1
        self.credits += 1
        return await self._client.search(query, **kwargs)

    async def extract(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
        self.extracts += 1
        self.credits += max(1, math.ceil(len(urls) / 5))
        return await self._client.extract(urls, **kwargs)


# ---------------------------------------------------------------------------
# Scoring (pure functions, unit-tested in tests/test_benchmark.py)
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    query: str
    outcome: str
    seconds: float
    report: Report | None = None
    error: str | None = None
    tavily: dict[str, int] = field(default_factory=dict)


def all_claims(report: Report) -> list[tuple[str, str, ReportClaim]]:
    """(subject, topic, claim) for every research claim shown in the report."""
    out: list[tuple[str, str, ReportClaim]] = []
    overview = report.company_overview
    if overview.identity:
        out.append((overview.name, "Identity", overview.identity))
    out += [(overview.name, g.label, c) for g in overview.facts for c in g.claims]
    out += [(comp.name, g.label, c) for comp in report.competitor_landscape for g in comp.facts for c in g.claims]
    out += [("Industry", "Industry context", c) for c in report.industry_overview.claims]
    return out


def sample_supported(
    report: Report, n: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED
) -> list[tuple[str, str, ReportClaim]]:
    """Up to n 'supported' claims, spread across subjects, for the manual check (criterion 5)."""
    supported = [item for item in all_claims(report) if item[2].verdict == "supported"]
    if len(supported) <= n:
        return supported
    picked = random.Random(seed).sample(range(len(supported)), n)  # noqa: S311 — sampling, not security
    return [supported[i] for i in sorted(picked)]


SECTION_COUNT = 12


def sections_present(report: Report) -> int:
    return SECTION_COUNT - len(report.meta.missing_sections)


def unflagged_unsourced(report: Report) -> int:
    """Criterion 4: claims shown as verified without a retrieved source (must be 0)."""
    return sum(1 for _, _, c in all_claims(report) if c.verdict in ("supported", "partially_supported") and not c.refs)


def incomplete_recommendations(report: Report) -> int:
    """Criterion 6: recommendations missing any of title, rationale, impact, next steps, risks."""
    return sum(
        1
        for r in report.recommendations
        if not (r.title and r.rationale and r.impact and r.next_steps and r.risks_tradeoffs)
    )


def research_numbers(report: Report) -> tuple[int, int]:
    """Research step (lead + parallel competitor researchers, M15) seconds and tokens."""
    usage = [u for u in report.meta.usage if u.step in ("research", "competitors")]
    lead = next((u for u in usage if u.step == "research"), None)
    parallel = next((u for u in usage if u.step == "competitors"), None)
    ms = (lead.duration_ms or 0 if lead else 0) + (parallel.duration_ms or 0 if parallel else 0)
    return round(ms / 1000), sum(u.total_tokens for u in usage)


def score(result: RunResult) -> dict[str, Any]:
    """One scorecard row."""
    row: dict[str, Any] = {"query": result.query, "outcome": result.outcome, "seconds": round(result.seconds)}
    row.update(result.tavily)
    r = result.report
    if r is None:
        return row
    v = r.validation
    total = v.claims_total or 1
    row.update(
        company=r.company_overview.name,
        competitors=[c.name for c in r.competitor_landscape],
        sections=sections_present(r),
        claims=v.claims_total,
        supported_pct=round(100 * v.supported / total),
        verified_pct=round(100 * (v.supported + v.partially_supported) / total),
        unconfirmed=v.unsupported,
        removed=v.contradicted,
        tokens=r.meta.total_tokens,
        research_seconds=research_numbers(r)[0],
        research_tokens=research_numbers(r)[1],
        unflagged_unsourced=unflagged_unsourced(r),
        recommendations=len(r.recommendations),
        incomplete_recommendations=incomplete_recommendations(r),
    )
    if r.meta.second_round is not None:  # M14
        row.update(second_gaps=len(r.meta.second_round.gaps), second_filled=r.meta.second_round.filled)
    return row


def criteria(rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(criterion, result, PASS/FAIL/CHECK) for the criteria the benchmark can measure."""
    with_report = [r for r in rows if r["outcome"] in ("succeeded", "partial")]
    full = [r for r in with_report if r.get("sections") == SECTION_COUNT and len(r.get("competitors", [])) >= 3]
    unsourced = sum(r.get("unflagged_unsourced", 0) for r in with_report)
    incomplete = sum(r.get("incomplete_recommendations", 0) for r in with_report)
    need = max(len(rows) - 1, 1)  # "at least 4 of 5"
    return [
        (
            "2. At least 4 of 5 companies produce a report",
            f"{len(with_report)} of {len(rows)}",
            "PASS" if len(with_report) >= need else "FAIL",
        ),
        (
            "3. All 12 sections and ≥ 3 competitors",
            f"{len(full)} of {len(with_report)} reports",
            "PASS" if with_report and len(full) == len(with_report) else "CHECK",
        ),
        (
            "4. Every verified fact cites a retrieved source",
            f"{unsourced} without a source",
            "PASS" if unsourced == 0 else "FAIL",
        ),
        ("5. ≥ 80% of sampled 'supported' claims are correct", "your manual check below", "CHECK"),
        (
            "6. Every recommendation has all five fields",
            f"{incomplete} incomplete",
            "PASS" if incomplete == 0 else "FAIL",
        ),
    ]


def _tavily(row: dict[str, Any]) -> str:
    if "credits" not in row:
        return "not recorded"
    return f"{row.get('searches', 0) + row.get('extracts', 0)} ({row['credits']})"


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def results_markdown(results: list[RunResult], when: datetime) -> str:
    rows = [score(r) for r in results]
    lines = [
        "# Delphi Market360 — POC benchmark results",
        "",
        f"Run on {when:%d %b %Y %H:%M} UTC with the agent versions in each report. "
        "Generated by `uv run python -m tests.live.benchmark`; the manual-check columns are for you to fill in.",
        "",
        "## Scorecard",
        "",
        "| Input | Outcome | Company found | Competitors | Claims | Supported | Supported + partly | Time | "
        "Tokens | Tavily requests (credits) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if "company" not in row:
            lines.append(
                f"| {_cell(row['query'])} | **{row['outcome']}** | — | — | — | — | — | {row['seconds']} s | — | "
                f"{_tavily(row)} |"
            )
            continue
        lines.append(
            f"| {_cell(row['query'])} | {row['outcome']} | {_cell(row['company'])} | "
            f"{_cell(', '.join(row['competitors']))} | {row['claims']} | {row['supported_pct']}% | "
            f"{row['verified_pct']}% | {row['seconds']} s | {row['tokens']:,} | "
            f"{_tavily(row)} |"
        )
    done = [r for r in rows if "company" in r]
    if done:
        keys = ("seconds", "tokens", "supported_pct", "research_seconds", "research_tokens")
        avg = {k: round(sum(r[k] for r in done) / len(done)) for k in keys}
        with_credits = [r["credits"] for r in done if "credits" in r]
        credits = f", {round(sum(with_credits) / len(with_credits))} Tavily credits" if with_credits else ""
        lines += [
            "",
            f"Average per report: {avg['seconds']} s, {avg['tokens']:,} tokens{credits}, "
            f"{avg['supported_pct']}% of claims fully supported.",
            f"Research step (M15: lead + competitors in parallel): {avg['research_seconds']} s,"
            f" {avg['research_tokens']:,} tokens on average.",
        ]
        second = [r for r in done if "second_gaps" in r]
        if second:
            lines.append(
                f"Second research round (M14) ran in {len(second)} of {len(done)} reports: "
                f"{sum(r['second_filled'] for r in second)} of {sum(r['second_gaps'] for r in second)} gaps filled."
            )
    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "Errors:", *[f"- {_cell(r.query)}: {_cell(r.error or '')}" for r in errors]]

    lines += ["", "## Acceptance criteria (plan §16.2)", "", "| Criterion | Result | Status |", "|---|---|---|"]
    lines += [f"| {c} | {r} | {s} |" for c, r, s in criteria(rows)]
    lines += [
        "",
        "Criteria 1, 7, 8, 9 and 10 were checked during M9 (both servers from the README, live progress, "
        "step times and tokens, the PDF, tests and no secrets).",
        "",
        "## Manual check: 10 'supported' claims per report",
        "",
        "Open each source and mark **Correct?** with ✔ (the source says it) or ✘ (it doesn't). "
        "Criterion 5 passes when at least 80% are ✔.",
    ]
    for result in results:
        if result.report is None:
            continue
        refs = {ref.ref: ref.url for ref in result.report.references}
        lines += [
            "",
            f"### {_cell(result.report.company_overview.name)} (`{_cell(result.query)}`)",
            "",
            "| # | About | Claim | Sources | Correct? |",
            "|---|---|---|---|---|",
        ]
        for i, (subject, topic, claim) in enumerate(sample_supported(result.report), start=1):
            urls = " ".join(f"[{n}]({refs[n]})" for n in claim.refs if n in refs)
            lines.append(f"| {i} | {_cell(subject)} — {_cell(topic)} | {_cell(claim.text)} | {urls} |  |")
        lines.append("")
        lines.append("Correct: __ / 10")
    lines += [
        "",
        "## Decision",
        "",
        "- Go / no-go for the MVP: __",
        "- Run-time and cost targets for the MVP: __",
        "- Notes: __",
        "",
    ]
    return "\n".join(lines)


def slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def save_run(folder: Path, result: RunResult) -> None:
    """Save the run's report and its time/Tavily numbers, so the scorecard can be rebuilt later."""
    name = slug(result.query)
    run = {"query": result.query, "outcome": result.outcome, "seconds": result.seconds, "error": result.error}
    (folder / f"run-{name}.json").write_text(json.dumps({**run, "tavily": result.tavily}, indent=2), encoding="utf-8")
    if result.report:
        data = json.dumps(result.report.model_dump(mode="json"), indent=2)
        (folder / f"report-{name}.json").write_text(data, encoding="utf-8")


def load_saved(folder: Path, order: list[str] = DEFAULT_COMPANIES) -> list[RunResult]:
    """Rebuild results from saved files. Without a run-*.json (older runs), time is the sum of the step
    times and Tavily usage is 'not recorded'."""
    results: list[RunResult] = []
    for path in sorted(folder.glob("report-*.json")):
        report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        run_path = folder / f"run-{path.stem.removeprefix('report-')}.json"
        if run_path.exists():
            run = json.loads(run_path.read_text(encoding="utf-8"))
            results.append(RunResult(run["query"], run["outcome"], run["seconds"], report, run["error"], run["tavily"]))
        else:
            seconds = sum(u.duration_ms or 0 for u in report.meta.usage) / 1000
            results.append(RunResult(report.meta.query, report.meta.outcome, seconds, report))
    rank = {slug(q): i for i, q in enumerate(order)}
    return sorted(results, key=lambda r: (rank.get(slug(r.query), len(rank)), r.query))


# ---------------------------------------------------------------------------
# Running (live)
# ---------------------------------------------------------------------------


async def run_one(query: str, settings: Any) -> RunResult:  # pragma: no cover — live only
    from core.agno_db import build_agno_db
    from registry.tools_catalog import tavily_client_for
    from workflow.research_workflow import build_research_workflow, outcome_from_run

    tavily = CountingTavily(tavily_client_for(settings))
    workflow = build_research_workflow(settings, build_agno_db(settings), tavily_client=tavily)
    is_url = query.startswith(("http://", "https://"))
    started = time.perf_counter()
    try:
        run = await workflow.arun(
            input=query,
            session_id=f"benchmark-{slug(query)}-{int(time.time())}",
            additional_data={"website_url": query if is_url else None},
        )
        outcome = outcome_from_run(run)
        error = outcome.error
        result_outcome, report = outcome.outcome, outcome.report
    except Exception as exc:  # one company failing must not stop the benchmark
        result_outcome, report, error = "failed", None, f"{type(exc).__name__}: {exc}"
    counts = {"searches": tavily.searches, "extracts": tavily.extracts, "credits": tavily.credits}
    return RunResult(query, result_outcome, time.perf_counter() - started, report, error, counts)


async def main(companies: list[str]) -> None:  # pragma: no cover — live only
    from pydantic import ValidationError

    from core.config import get_settings
    from tests.live.render import report_to_markdown

    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.exit(f"backend/.env missing or invalid: {exc.errors()[0]['msg']}")
    if not (settings.openai_api_key and settings.tavily_api_key):
        sys.exit("OPENAI_API_KEY and TAVILY_API_KEY must be set in backend/.env")

    out = DOCS / "benchmark"
    out.mkdir(parents=True, exist_ok=True)
    results: list[RunResult] = []
    scorecard = DOCS / "poc-results.md"
    # ignore_cleanup_errors: on Windows the SQLite file can still be open when the folder is removed.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{Path(tmp) / 'bench.db'}"})
        for n, company in enumerate(companies, start=1):
            print(f"[{n}/{len(companies)}] {company} …", flush=True)
            result = await run_one(company, settings)
            results.append(result)
            row = score(result)
            print(
                f"    {result.outcome} in {row['seconds']} s"
                + (
                    f" — {row['company']}, {len(row['competitors'])} competitors, {row['supported_pct']}% supported,"
                    f" {row['tokens']:,} tokens, {row['credits']} Tavily credits"
                    if result.report
                    else f" — {result.error}"
                ),
                flush=True,
            )
            save_run(out, result)
            if result.report:
                (out / f"report-{slug(company)}.md").write_text(report_to_markdown(result.report), encoding="utf-8")
            scorecard.write_text(results_markdown(results, datetime.now(UTC)), encoding="utf-8")

    print(f"\nScorecard: {scorecard}\nReports:   {out}")


def rebuild_from_saved() -> None:  # pragma: no cover — thin wrapper, logic tested in load_saved
    folder = DOCS / "benchmark"
    results = load_saved(folder)
    if not results:
        sys.exit(f"No saved reports in {folder}")
    (DOCS / "poc-results.md").write_text(results_markdown(results, datetime.now(UTC)), encoding="utf-8")
    print(f"Rebuilt {DOCS / 'poc-results.md'} from {len(results)} saved report(s).")


if __name__ == "__main__":  # pragma: no cover
    if sys.argv[1:] == ["--from-saved"]:
        rebuild_from_saved()
    else:
        asyncio.run(main(sys.argv[1:] or DEFAULT_COMPANIES))
