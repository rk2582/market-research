"""LIVE full pipeline — all five agents with real OpenAI and Tavily (costs a few cents per company).

Run from backend/ (keys must be in backend/.env):
    uv run pytest -m live -s tests/live/test_workflow_live.py

Choose companies:  LIVE_COMPANIES="Monzo;https://www.canva.com"   (PowerShell: $env:LIVE_COMPANIES="...")

For each company it prints a summary and saves, in tests/fixtures/live/:
    report-<name>.json   the full report
    report-<name>.md     a readable version — open it in VS Code (Ctrl+Shift+V for preview) and judge the quality
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agno_db import build_agno_db
from core.config import get_settings
from tests.live.render import report_to_markdown
from workflow.research_workflow import build_research_workflow, outcome_from_run

pytestmark = pytest.mark.live

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "live"
DEFAULT_COMPANIES = "Notion;https://monzo.com"


def _companies() -> list[str]:
    return [c.strip() for c in os.environ.get("LIVE_COMPANIES", DEFAULT_COMPANIES).split(";") if c.strip()]


@pytest.mark.parametrize("company", _companies())
async def test_full_workflow_live(company: str, tmp_path: Path):
    get_settings.cache_clear()
    try:
        settings = get_settings()
    except ValidationError as exc:
        pytest.skip(f"backend/.env missing or invalid: {exc.errors()[0]['msg']}")
    if not (settings.openai_api_key and settings.tavily_api_key):
        pytest.skip("OPENAI_API_KEY and TAVILY_API_KEY must be set in backend/.env")
    settings = settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'live.db'}"})

    is_url = company.startswith(("http://", "https://"))
    workflow = build_research_workflow(settings, build_agno_db(settings))
    started = time.perf_counter()
    run = await workflow.arun(
        input=company, session_id=f"live-{int(started)}", additional_data={"website_url": company if is_url else None}
    )
    elapsed = time.perf_counter() - started
    result = outcome_from_run(run)

    print(f"\n=== {company}: {result.outcome} in {elapsed:.0f} s")
    assert result.report is not None, f"No report: {result.failed_step}: {result.error}"
    r = result.report
    v = r.validation
    print(f"company:          {r.company_overview.name} ({r.company_overview.website})")
    print(f"competitors:      {[c.name for c in r.competitor_landscape]}")
    print(
        f"fact-check:       {v.claims_total} claims → {v.supported} supported, {v.partially_supported} partial,"
        f" {v.unsupported} unconfirmed, {v.contradicted} contradicted (removed)"
    )
    print(
        f"analysis:         {len(r.competitive_comparison)} comparison rows, "
        f"SWOT {[len(getattr(r.swot, q)) for q in ('strengths', 'weaknesses', 'opportunities', 'threats')]}, "
        f"{len(r.market_trends)} trends, {len(r.opportunities)} opportunities, {len(r.risks)} risks"
    )
    print(f"recommendations:  {[rec.title for rec in r.recommendations]}")
    print(f"warnings:         {len(v.warnings)}")
    print(f"missing sections: {r.meta.missing_sections or 'none'} {r.meta.step_errors or ''}")
    for u in r.meta.usage:
        print(f"  {u.step:<11} {u.input_tokens:>7,} in {u.output_tokens:>6,} out  {u.tool_calls:>2} tools  {u.model}")
    print(f"  {'TOTAL':<11} {r.meta.total_input_tokens:>7,} in {r.meta.total_output_tokens:>6,} out")

    OUT.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    (OUT / f"report-{slug}.json").write_text(json.dumps(r.model_dump(mode="json"), indent=2), encoding="utf-8")
    (OUT / f"report-{slug}.md").write_text(report_to_markdown(r), encoding="utf-8")
    print(f"saved:            tests/fixtures/live/report-{slug}.md")

    assert result.outcome in ("succeeded", "partial")
    assert r.references and r.competitor_landscape
