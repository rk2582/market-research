"""LIVE Researcher check — calls real OpenAI and Tavily (costs a little money and Tavily credits).

Run from backend/ (keys must be in backend/.env):
    uv run pytest -m live -s

Default: one company by name and one by URL. Override with:
    LIVE_COMPANIES="Monzo;https://www.canva.com"   (PowerShell: $env:LIVE_COMPANIES="...")

For each company it prints a summary (tokens, tool calls, time, sources, citation check) and saves the
output to tests/fixtures/live/<name>.json — Milestone 6 uses these as realistic, free test data.
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
from workflow.claims import extract_claims
from workflow.research_workflow import ResearchStepResult, build_research_workflow

pytestmark = pytest.mark.live

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live"
DEFAULT_COMPANIES = "Notion;https://monzo.com"


def _companies() -> list[str]:
    return [c.strip() for c in os.environ.get("LIVE_COMPANIES", DEFAULT_COMPANIES).split(";") if c.strip()]


@pytest.mark.parametrize("company", _companies())
async def test_researcher_live(company: str, tmp_path: Path):
    get_settings.cache_clear()
    try:
        settings = get_settings()
    except ValidationError as exc:
        pytest.skip(f"backend/.env missing or invalid: {exc.errors()[0]['msg']}")
    if not (settings.openai_api_key and settings.tavily_api_key):
        pytest.skip("OPENAI_API_KEY and TAVILY_API_KEY must be set in backend/.env")
    # Keep Agno's run storage in a throwaway SQLite file, not your real database.
    settings = settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'live.db'}"})

    is_url = company.startswith(("http://", "https://"))
    workflow = build_research_workflow(settings, build_agno_db(settings))
    started = time.perf_counter()
    run = await workflow.arun(
        input=company, session_id=f"live-{int(started)}", additional_data={"website_url": company if is_url else None}
    )
    elapsed = time.perf_counter() - started

    [step] = run.step_results
    assert step.success, f"Research step failed: {step.error}"
    result = ResearchStepResult.model_validate(step.content)

    claims = extract_claims(result.findings, result.sources)
    not_retrieved = sorted({u for c in claims for u in c.cited_but_not_retrieved})
    without_source = [c.text for c in claims if not c.source_urls and not c.cited_but_not_retrieved]

    print(f"\n=== {company}")
    print(f"matched:          {result.findings.company.name} ({result.findings.company.website})")
    print(f"identity note:    {result.findings.company.identity_note.text}")
    print(f"competitors:      {[c.name for c in result.findings.competitors]}")
    print(f"claims:           {len(claims)} ({len(without_source)} without a source)")
    print(f"sources:          {len(result.sources)} retrieved; {len(not_retrieved)} cited URLs NOT retrieved")
    print(f"model / version:  {result.usage.model} / {result.usage.agent_version}")
    print(f"tokens:           {result.usage.input_tokens} in + {result.usage.output_tokens} out")
    print(f"tool calls:       {result.usage.tool_calls} (≈ Tavily credits)")
    print(f"time:             {elapsed:.1f} s")
    for url in not_retrieved[:10]:
        print(f"  not retrieved:  {url}")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    (FIXTURES / f"{slug}.json").write_text(
        json.dumps({"query": company, "elapsed_s": round(elapsed, 1), **result.model_dump(mode="json")}, indent=2),
        encoding="utf-8",
    )

    # Hard requirements for the spike; quality (citations) is reported above and enforced in M6 by code.
    assert result.findings.competitors, "no competitors found"
    assert result.sources, "no sources harvested"
    assert result.usage.tool_calls <= 15
