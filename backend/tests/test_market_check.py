"""M13: scoring of the live market check (pure functions, no network) and the Markdown of a market report.

Uses the market report fixture that the frontend tests use (built by the real assembler; illustrative data)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from schemas.report import Report
from tests.live.market_check import IDEAS, Idea, MarketResult, looks_useful, parse_idea, results_markdown, score
from tests.live.render import report_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "frontend/src/modules/research/fixtures/report-market.json"


@pytest.fixture
def market_report() -> Report:
    return Report.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_ideas_and_parsing():
    assert [i.label for i in IDEAS][0] == "Fresh packaged milk · Kerala · households"
    assert IDEAS[2].slug == "specialty-coffee-united-kingdom"
    assert parse_idea(" Biscuits | Tamil Nadu ") == Idea("Biscuits", "Tamil Nadu", None)
    assert parse_idea("Coffee|UK|cafes").customer_type == "cafes"
    with pytest.raises(ValueError, match="product\\|region"):
        parse_idea("Coffee")


def test_score_of_a_market_report(market_report: Report):
    row = score(MarketResult(IDEAS[0], "succeeded", 84.4, market_report, tavily_credits=17))
    assert row["players"] == ["Periyar Dairy Co-op", "Malabar Farms", "GreenCow Organics", "Coastline Milk"]
    assert (row["snapshot_filled"], row["snapshot_total"], row["snapshot_missing"]) == (7, 8, ["Costs and margins"])
    assert (row["forces_rated"], row["signals_for"], row["signals_against"]) == (4, 3, 2)
    assert (row["checks"], row["figures"], row["seconds"], row["credits"]) == (5, 4, 84, 17)
    assert (row["estimates"], row["sources"]) == (1, 10)
    assert looks_useful(row)  # the bar a good report passes
    thin = {**row, "checks": 2}
    assert not looks_useful(thin)


def test_missing_snapshot_topics_are_listed(market_report: Report):
    facts = [g for g in market_report.company_overview.facts if g.label not in {"Costs and margins", "Prices"}]
    report = market_report.model_copy(
        update={"company_overview": market_report.company_overview.model_copy(update={"facts": facts})}
    )
    row = score(MarketResult(IDEAS[0], "succeeded", 1, report))
    assert row["snapshot_filled"] == 6 and row["snapshot_missing"] == ["Prices", "Costs and margins"]


def test_scorecard_markdown_shows_failures_too(market_report: Report):
    results = [
        MarketResult(IDEAS[0], "succeeded", 84, market_report, tavily_credits=17),
        MarketResult(IDEAS[1], "failed", 12, None, "research step failed: timed out"),
    ]
    md = results_markdown(results, datetime(2026, 10, 27, 10, 0, tzinfo=UTC))
    assert "**1 of 2 pass the automatic bar**" in md
    assert (
        "| Fresh packaged milk · Kerala · households | succeeded | 94% of 32 | 10 | 1 | 1 | 4 (4) | 7/8 | 4/5"
        " | 3/2 | 2 | 5 | 4 | 1/3 |" in md
    )
    assert "| Electric scooters · India · commuters | failed: research step failed: timed out |" in md
    assert "not found: Costs and margins" in md
    assert "| 1/3 | 48 s, 34,100 tok |" in md  # research time and tokens (M15)


def test_market_report_markdown(market_report: Report):
    md = report_to_markdown(market_report)
    assert md.startswith("# Market-entry report: Fresh packaged milk in Kerala")
    assert "not a recommendation to invest" in md
    assert "- **Entry barriers:** high —" in md and "- **Substitutes:** not rated" in md
    assert "**Signals against entering**" in md and "## 6. SWOT" not in md
    assert "- [ ] Ask 3 distributors in Kochi what margin they take on packaged milk." in md


def test_second_round_and_old_sources_in_the_score(market_report: Report):
    from schemas.report import SecondRoundOut

    facts = market_report.company_overview.facts
    old = facts[0].model_copy(update={"claims": [facts[0].claims[0].model_copy(update={"old_source_year": 2018})]})
    meta = market_report.meta.model_copy(update={"second_round": SecondRoundOut(gaps=["a", "b", "c"], filled=2)})
    overview = market_report.company_overview.model_copy(update={"facts": [old, *facts[1:]]})
    report = market_report.model_copy(update={"meta": meta, "company_overview": overview})
    row = score(MarketResult(IDEAS[0], "succeeded", 90, report))
    assert (row["old_sources"], row["second_round"], row["own_site_players"]) == (2, "2/3", 4)  # fixture has 1
    failed = meta.second_round.model_copy(update={"error": "timed out"})
    report = report.model_copy(update={"meta": meta.model_copy(update={"second_round": failed})})
    assert score(MarketResult(IDEAS[0], "succeeded", 90, report))["second_round"] == "2/3 (failed)"
