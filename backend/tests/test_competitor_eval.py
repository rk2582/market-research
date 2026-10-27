"""Scoring for the live competitor quality check (tests/live/competitor_eval.py)."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.live.competitor_eval import CASES, Score, is_listed, results_markdown, score

NESTLE = next(c for c in CASES if c.query == "Nestlé India")


def test_aliases_and_name_variants_count_as_the_same_company():
    assert is_listed("Cadbury India", NESTLE.accepted)  # alias of Mondelez
    assert is_listed("Hindustan Unilever Limited", NESTLE.accepted)
    assert is_listed("Britannia", NESTLE.accepted)
    assert not is_listed("Varun Beverages", NESTLE.accepted)
    assert not is_listed("AWL Agri Business", NESTLE.accepted)


def test_the_nestle_run_the_user_reported_fails():
    reported = [("Mother Dairy", False), ("Bikaji Foods International", False), ("AWL Agri Business", True)]
    reported += [("Varun Beverages", True), ("Prabhat Dairy", True)]
    s = score(NESTLE, "Nestlé India Limited", reported)
    assert s.precision == 20 and s.must_pct == 0 and s.weak == 3 and not s.passed


def test_a_good_list_passes():
    good = [("Hindustan Unilever", False), ("ITC Limited", False), ("Mondelez India", False), ("Britannia", False)]
    s = score(NESTLE, "Nestlé India Limited", [*good, ("Amul", True)])
    assert (s.precision, s.must_pct, s.weak) == (100, 100, 1) and s.passed
    assert s.must_found == ["Hindustan Unilever", "ITC", "Mondelez India", "Britannia Industries"]


def test_empty_and_error_results():
    assert score(NESTLE, None, []).precision == 0 and not score(NESTLE, None, []).passed
    assert not Score(query="x", matched=None, error="timeout").passed
    assert Score(query="x", matched=None).must_pct == 0


def test_results_page():
    good = score(NESTLE, "Nestlé India Limited", [("Hindustan Unilever", False), ("ITC", False), ("Mondelez", False)])
    bad = score(NESTLE, "Nestlé India Limited", [("Varun Beverages", True)])
    failed = Score(query="Notion", matched=None, seconds=40, error="The quick check took too long.")
    page = results_markdown([good, bad, failed], datetime(2026, 10, 27, tzinfo=UTC))
    assert "**1 of 3 passed.**" in page
    assert "| Nestlé India | Nestlé India Limited | 100% | 3 of 4 | 0 |" in page and "✔ pass" in page
    assert "✘ Varun Beverages (weak)" in page and "**error:** The quick check took too long." in page
    assert "- **Notion:** none" in page


def test_every_case_has_must_haves_inside_its_accepted_list():
    for case in CASES:
        assert set(case.must) <= set(case.accepted), case.query
