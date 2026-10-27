"""M13 market check — runs 3 market-entry ideas end to end with REAL OpenAI and Tavily (costs money: roughly
15-20 Tavily credits plus a few US cents of OpenAI per idea) and writes a scorecard.

Run from backend/ (keys must be in backend/.env):
    uv run python -m tests.live.market_check
    uv run python -m tests.live.market_check "Specialty coffee|UK|cafes"     # your own: product|region|customers

Writes docs/plans/market-check.md (scorecard) and docs/plans/market-check/report-<idea>.md / .json (each report).
The scorecard is rewritten after every idea, so a crash never loses finished runs. The real test is reading the
reports: are they useful for deciding whether to enter that market?
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from schemas.report import Report
from tests.live.benchmark import research_numbers
from workflow.claims import MARKET_FIELDS

DOCS = Path(__file__).resolve().parents[3] / "docs" / "plans"
FORCES = ("rivalry", "entry_barriers", "supplier_power", "buyer_power", "substitutes")


@dataclass(frozen=True)
class Idea:
    product: str
    region: str
    customer_type: str | None = None

    @property
    def label(self) -> str:
        return " · ".join(x for x in (self.product, self.region, self.customer_type) if x)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", f"{self.product} {self.region}".lower()).strip("-")


IDEAS: tuple[Idea, ...] = (
    Idea("Fresh packaged milk", "Kerala", "households"),
    Idea("Electric scooters", "India", "commuters"),
    Idea("Specialty coffee", "United Kingdom", "cafes"),
)


def parse_idea(text: str) -> Idea:
    """'Product|Region|Customers' (customers optional)."""
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Use 'product|region' or 'product|region|customers', got: {text!r}")
    return Idea(parts[0], parts[1], parts[2] if len(parts) > 2 and parts[2] else None)


# ---------------------------------------------------------------------------
# Scoring (pure, unit-tested in tests/test_market_check.py)
# ---------------------------------------------------------------------------


@dataclass
class MarketResult:
    idea: Idea
    outcome: str
    seconds: float
    report: Report | None = None
    error: str | None = None
    tavily_credits: int | None = None


def snapshot_filled(report: Report) -> tuple[int, list[str]]:
    """How many market-snapshot topics have at least one claim, and which are missing."""
    present = {g.label for g in report.company_overview.facts}
    labels = [label for name, label in MARKET_FIELDS if name != "scope_note"]
    missing = [label for label in labels if label not in present]
    return len(labels) - len(missing), missing


def estimate_claims(report: Report) -> int:
    """Claims whose only sources are market-research firms' pages (one firm's estimate)."""
    groups = [*report.company_overview.facts, *(g for c in report.competitor_landscape for g in c.facts)]
    claims = [c for g in groups for c in g.claims] + report.industry_overview.claims
    if report.company_overview.identity:
        claims.append(report.company_overview.identity)
    return sum(c.estimate for c in claims)


def old_source_claims(report: Report) -> int:
    groups = [*report.company_overview.facts, *(g for c in report.competitor_landscape for g in c.facts)]
    claims = [c for g in groups for c in g.claims] + report.industry_overview.claims
    return sum(1 for c in claims if c.old_source_year)


def players_with_own_site_facts(report: Report) -> int:
    """Players with at least one claim sourced from their own website (M14 goal)."""
    url_by_ref = {s.ref: s.url for s in report.references}
    count = 0
    for player in report.competitor_landscape:
        host = (urlsplit(player.website).hostname or "").removeprefix("www.") if player.website else None
        refs = {r for g in player.facts for c in g.claims for r in c.refs}
        if host and any((urlsplit(url_by_ref.get(r, "")).hostname or "").removeprefix("www.") == host for r in refs):
            count += 1
    return count


def score(result: MarketResult) -> dict[str, Any]:
    row: dict[str, Any] = {"idea": result.idea.label, "outcome": result.outcome, "seconds": round(result.seconds)}
    r = result.report
    if r is None or r.market is None:
        return row
    v = r.validation
    total = v.claims_total or 1
    filled, missing = snapshot_filled(r)
    row.update(
        claims=v.claims_total,
        supported_pct=round(100 * v.supported / total),
        players=[c.name for c in r.competitor_landscape],
        snapshot_filled=filled,
        snapshot_total=filled + len(missing),
        snapshot_missing=missing,
        forces_rated=len(r.market.forces),
        signals_for=len(r.market.signals_for),
        signals_against=len(r.market.signals_against),
        entry_options=len(r.recommendations),
        checks=len(r.market.checks_before_investing),
        figures=len(r.key_figures),
        estimates=estimate_claims(r),
        sources=len(r.references),
        old_sources=old_source_claims(r),
        own_site_players=players_with_own_site_facts(r),
        second_round=(
            f"{r.meta.second_round.filled}/{len(r.meta.second_round.gaps)}"
            + (" (failed)" if r.meta.second_round.error else "")
            if r.meta.second_round
            else "—"
        ),
        tokens=r.meta.total_tokens,
        research=research_numbers(r),
        credits=result.tavily_credits,
    )
    return row


def looks_useful(row: dict[str, Any]) -> bool:
    """A rough automatic bar; the real judgement is yours after reading the report."""
    return (
        row.get("outcome") == "succeeded"
        and row.get("supported_pct", 0) >= 80
        and len(row.get("players", [])) >= 3
        and row.get("snapshot_filled", 0) >= 5
        and row.get("forces_rated", 0) >= 3
        and row.get("signals_for", 0) >= 1
        and row.get("signals_against", 0) >= 1
        and row.get("checks", 0) >= 4
    )


def results_markdown(results: list[MarketResult], when: datetime) -> str:
    rows = [score(r) for r in results]
    lines = [
        "# Market-entry check (M13)",
        "",
        f"Run on {when:%d %b %Y %H:%M} UTC with `uv run python -m tests.live.market_check`."
        f" **{sum(looks_useful(r) for r in rows)} of {len(rows)} pass the automatic bar** (≥80% claims supported,"
        " ≥3 players, ≥5 of 8 snapshot topics, ≥3 forces rated, signals on both sides, ≥4 checks).",
        "The real test is reading each report in `docs/plans/market-check/`: would it help you decide?",
        "",
        "| Idea | Outcome | Supported | Sources | Estimates | Old sources | Players (own site) | Snapshot | Forces"
        " | Signals +/− | Options | Checks | Figures | 2nd round filled | Research | Time | Tokens | Tavily |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for res, row in zip(results, rows, strict=True):
        if "claims" not in row:
            lines.append(f"| {row['idea']} | {row['outcome']}: {res.error or 'no report'} |" + " — |" * 16)
            continue
        credits = "—" if row["credits"] is None else str(row["credits"])
        lines.append(
            f"| {row['idea']} | {row['outcome']} | {row['supported_pct']}% of {row['claims']} | {row['sources']}"
            f" | {row['estimates']} | {row['old_sources']} | {len(row['players'])} ({row['own_site_players']})"
            f" | {row['snapshot_filled']}/{row['snapshot_total']} | {row['forces_rated']}/5"
            f" | {row['signals_for']}/{row['signals_against']} | {row['entry_options']} | {row['checks']}"
            f" | {row['figures']} | {row['second_round']} | {row['research'][0]} s, {row['research'][1]:,} tok"
            f" | {row['seconds']} s | {row['tokens']:,} | {credits} |"
        )
    lines += ["", "## Details", ""]
    for row in rows:
        if "claims" in row:
            missing = ", ".join(row["snapshot_missing"]) or "none"
            lines.append(f"- **{row['idea']}:** players {', '.join(row['players']) or 'none'}; not found: {missing}.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Running (live)
# ---------------------------------------------------------------------------


async def run_idea(idea: Idea, settings: Any) -> MarketResult:  # pragma: no cover — live only
    from core.agno_db import build_agno_db
    from registry.tools_catalog import tavily_client_for
    from tests.live.benchmark import CountingTavily
    from workflow.research_workflow import build_research_workflow, outcome_from_run

    tavily = CountingTavily(tavily_client_for(settings))
    workflow = build_research_workflow(settings, build_agno_db(settings), tavily_client=tavily)
    started = time.perf_counter()
    try:
        run = await workflow.arun(
            input=idea.product,
            session_id=f"market-{idea.slug}-{int(time.time())}",
            additional_data={
                "website_url": None,
                "mode": "market",
                "market": {"product": idea.product, "region": idea.region, "customer_type": idea.customer_type},
            },
        )
        outcome = outcome_from_run(run)
        result = MarketResult(idea, outcome.outcome, 0, outcome.report, outcome.error)
    except Exception as exc:  # one idea failing must not stop the check
        result = MarketResult(idea, "failed", 0, None, f"{type(exc).__name__}: {exc}")
    result.seconds = time.perf_counter() - started
    result.tavily_credits = tavily.credits
    return result


async def main(ideas: list[Idea]) -> None:  # pragma: no cover — live only
    from pydantic import ValidationError

    from core.config import get_settings
    from tests.live.render import report_to_markdown

    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.exit(f"backend/.env missing or invalid: {exc.errors()[0]['msg']}")
    if not (settings.openai_api_key and settings.tavily_api_key):
        sys.exit("OPENAI_API_KEY and TAVILY_API_KEY must be set in backend/.env")

    out = DOCS / "market-check"
    out.mkdir(parents=True, exist_ok=True)
    scorecard = DOCS / "market-check.md"
    results: list[MarketResult] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{Path(tmp) / 'market.db'}"})
        for n, idea in enumerate(ideas, start=1):
            print(f"[{n}/{len(ideas)}] {idea.label} …", flush=True)
            result = await run_idea(idea, settings)
            results.append(result)
            row = score(result)
            print(
                f"    {result.outcome} in {row['seconds']} s"
                + (
                    f" — {len(row['players'])} players, {row['supported_pct']}% supported,"
                    f" snapshot {row['snapshot_filled']}/{row['snapshot_total']}, {row['forces_rated']}/5 forces,"
                    f" {row['tokens']:,} tokens, {row['credits']} Tavily credits"
                    if "claims" in row
                    else f" — {result.error}"
                ),
                flush=True,
            )
            if result.report:
                data = json.dumps(result.report.model_dump(mode="json"), indent=2, ensure_ascii=False)
                (out / f"report-{idea.slug}.json").write_text(data, encoding="utf-8")
                (out / f"report-{idea.slug}.md").write_text(report_to_markdown(result.report), encoding="utf-8")
            scorecard.write_text(results_markdown(results, datetime.now(UTC)), encoding="utf-8")
    print(f"\nScorecard: {scorecard}\nReports:   {out}")


if __name__ == "__main__":  # pragma: no cover
    try:
        chosen = [parse_idea(a) for a in sys.argv[1:]] or list(IDEAS)
    except ValueError as exc:
        sys.exit(str(exc))
    asyncio.run(main(chosen))
