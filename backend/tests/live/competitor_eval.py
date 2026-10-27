"""Competitor quality check — runs only the confirm step (Identifier) with REAL OpenAI and Tavily, for a fixed
set of companies whose real rivals are well known, and scores the suggestions. About 6 Tavily credits and a
few thousand tokens per company (much cheaper than a full research run).

Run from backend/ (keys must be in backend/.env):
    uv run python -m tests.live.competitor_eval

Writes docs/plans/competitor-eval.md. Scores:
- precision: share of suggested competitors that are real rivals (in the accepted list)          target ≥ 80%
- must-have: share of the most obvious rivals that were suggested                                  target ≥ 60%
- weak: suggestions backed only by a company-database list (Tracxn, CB Insights …)                 target ≤ 1
The accepted lists are deliberately generous; a miss means a clearly wrong pick (e.g. a Pepsi bottler for Nestlé).
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from workflow.claims import same_company

DOCS = Path(__file__).resolve().parents[3] / "docs" / "plans"
PRECISION_TARGET, MUST_TARGET, WEAK_LIMIT = 80, 60, 1


@dataclass(frozen=True)
class Case:
    query: str
    accepted: tuple[str, ...]  # "A|B" = aliases of one company
    must: tuple[str, ...]


CASES: tuple[Case, ...] = (
    Case(
        "Nestlé India",
        accepted=(
            "Hindustan Unilever|HUL",
            "ITC",
            "Mondelez India|Mondelez|Cadbury",
            "Britannia Industries|Britannia",
            "Amul|Gujarat Cooperative Milk Marketing Federation|GCMMF",
            "Tata Consumer Products|Tata Consumer",
            "Danone",
            "Abbott",
            "Ferrero",
            "Parle Products|Parle",
            "Dabur",
            "Marico",
            "PepsiCo India|PepsiCo",
            "Kraft Heinz|Heinz",
            "Kellogg|Kellanova",
            "Mother Dairy",
            "Patanjali",
            "Hershey",
            "Capital Foods|Ching's",
        ),
        must=("Hindustan Unilever|HUL", "ITC", "Mondelez India|Mondelez|Cadbury", "Britannia Industries|Britannia"),
    ),
    Case(
        "Notion",
        accepted=(
            "Confluence|Atlassian",
            "Coda",
            "ClickUp",
            "Airtable",
            "Microsoft Loop|Microsoft OneNote|Microsoft",
            "Google Docs|Google Workspace|Google",
            "Evernote",
            "Obsidian",
            "Asana",
            "monday.com|Monday",
            "Slite",
            "Nuclino",
            "Craft",
            "Quip",
            "Anytype",
            "Slab",
            "AppFlowy",
            "Guru",
        ),
        must=("Confluence|Atlassian", "Coda", "ClickUp"),
    ),
    Case(
        "https://monzo.com",
        accepted=(
            "Starling Bank|Starling",
            "Revolut",
            "Chase UK|Chase|JPMorgan Chase",
            "Barclays",
            "HSBC|First Direct",
            "Lloyds Bank|Lloyds|Halifax",
            "NatWest",
            "Santander",
            "Nationwide",
            "Wise",
            "Kroo",
            "Zopa",
            "Metro Bank",
            "Virgin Money",
            "Atom Bank",
        ),
        must=("Starling Bank|Starling", "Revolut"),
    ),
    Case(
        "Hindustan Unilever",
        accepted=(
            "Procter & Gamble|P&G|Procter and Gamble",
            "ITC",
            "Nestlé India|Nestle India|Nestlé|Nestle",
            "Dabur",
            "Marico",
            "Godrej Consumer Products|Godrej",
            "Colgate-Palmolive|Colgate",
            "Reckitt|Reckitt Benckiser",
            "Tata Consumer Products|Tata Consumer",
            "Emami",
            "Patanjali",
            "Britannia Industries|Britannia",
            "Jyothy Labs",
            "Wipro Consumer Care",
            "Johnson & Johnson",
        ),
        must=("Procter & Gamble|P&G|Procter and Gamble", "ITC", "Dabur", "Godrej Consumer Products|Godrej"),
    ),
    Case(
        "Pipedrive",
        accepted=(
            "HubSpot",
            "Salesforce",
            "Zoho CRM|Zoho",
            "Freshsales|Freshworks",
            "monday.com|monday CRM|Monday",
            "Copper",
            "Close",
            "Insightly",
            "Microsoft Dynamics 365|Microsoft Dynamics",
            "Keap",
            "Nutshell",
            "Less Annoying CRM",
            "Zendesk Sell",
            "Agile CRM",
            "Capsule CRM|Capsule",
            "Bitrix24",
            "Attio",
        ),
        must=("HubSpot", "Salesforce", "Zoho CRM|Zoho"),
    ),
)


# ---------------------------------------------------------------------------
# Scoring (pure, unit-tested in tests/test_competitor_eval.py)
# ---------------------------------------------------------------------------


def is_listed(name: str, entries: tuple[str, ...]) -> bool:
    return any(same_company(name, None, alias, None) for entry in entries for alias in entry.split("|"))


@dataclass
class Score:
    query: str
    matched: str | None
    suggested: list[tuple[str, bool, bool]] = field(default_factory=list)  # (name, accepted, weak)
    must_found: list[str] = field(default_factory=list)
    must_total: int = 0
    seconds: float = 0.0
    error: str | None = None

    @property
    def precision(self) -> int:
        return round(100 * sum(ok for _, ok, _ in self.suggested) / len(self.suggested)) if self.suggested else 0

    @property
    def must_pct(self) -> int:
        return round(100 * len(self.must_found) / self.must_total) if self.must_total else 0

    @property
    def weak(self) -> int:
        return sum(w for _, _, w in self.suggested)

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.precision >= PRECISION_TARGET
            and self.must_pct >= MUST_TARGET
            and self.weak <= WEAK_LIMIT
        )


def score(case: Case, matched: str | None, competitors: list[tuple[str, bool]], seconds: float = 0.0) -> Score:
    """competitors: (name, weak_evidence) as suggested."""
    names = [n for n, _ in competitors]
    return Score(
        query=case.query,
        matched=matched,
        suggested=[(n, is_listed(n, case.accepted), weak) for n, weak in competitors],
        must_found=[m.split("|")[0] for m in case.must if any(is_listed(n, (m,)) for n in names)],
        must_total=len(case.must),
        seconds=seconds,
    )


def results_markdown(scores: list[Score], when: datetime) -> str:
    passed = sum(s.passed for s in scores)
    lines = [
        "# Competitor quality check",
        "",
        f"Run on {when:%d %b %Y %H:%M} UTC with `uv run python -m tests.live.competitor_eval` (confirm step only).",
        f"Targets per company: precision ≥ {PRECISION_TARGET}%, must-have rivals ≥ {MUST_TARGET}%,"
        f" at most {WEAK_LIMIT} weak-evidence suggestion. **{passed} of {len(scores)} passed.**",
        "",
        "| Search | Matched | Precision | Must-have found | Weak | Time | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        if s.error:
            lines.append(f"| {s.query} | — | — | — | — | {s.seconds:.0f} s | **error:** {s.error} |")
            continue
        lines.append(
            f"| {s.query} | {s.matched or '—'} | {s.precision}% | {len(s.must_found)} of {s.must_total} |"
            f" {s.weak} | {s.seconds:.0f} s | {'✔ pass' if s.passed else '✘ fail'} |"
        )
    lines += ["", "## Suggestions", ""]
    for s in scores:
        marks = ", ".join(f"{'✔' if ok else '✘'} {name}{' (weak)' if weak else ''}" for name, ok, weak in s.suggested)
        lines.append(f"- **{s.query}:** {marks or 'none'}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Running (live)
# ---------------------------------------------------------------------------


async def run_case(case: Case, service: object) -> Score:  # pragma: no cover — live only
    started = time.perf_counter()
    try:
        result = await service.identify(case.query)  # type: ignore[attr-defined]
    except Exception as exc:
        return Score(query=case.query, matched=None, seconds=time.perf_counter() - started, error=str(exc))
    matched = result.matches[0].name if result.matches else None
    competitors = [(c.name, c.weak_evidence) for c in result.competitors]
    return score(case, matched, competitors, time.perf_counter() - started)


async def main() -> None:  # pragma: no cover — live only
    from pydantic import ValidationError

    from core.config import get_settings
    from services.identify_service import IdentifyService

    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.exit(f"backend/.env missing or invalid: {exc.errors()[0]['msg']}")
    if not (settings.openai_api_key and settings.tavily_api_key):
        sys.exit("OPENAI_API_KEY and TAVILY_API_KEY must be set in backend/.env")
    service = IdentifyService(settings)
    scores = []
    for n, case in enumerate(CASES, start=1):
        print(f"[{n}/{len(CASES)}] {case.query} …", flush=True)
        s = await run_case(case, service)
        scores.append(s)
        verdict = s.error or f"precision {s.precision}%, must-have {len(s.must_found)}/{s.must_total}, weak {s.weak}"
        print(f"    {verdict} — {', '.join(n for n, _, _ in s.suggested)}", flush=True)
    out = DOCS / "competitor-eval.md"
    out.write_text(results_markdown(scores, datetime.now(UTC)), encoding="utf-8")
    print(f"\n{sum(x.passed for x in scores)} of {len(scores)} passed. Results: {out}")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
