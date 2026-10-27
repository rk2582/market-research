"""M12: the confirm step (Identifier + /identify), starting with a confirmed company and competitor list,
and linking every run to a row in `companies`."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from db.models.research import CompanyRow, InputType, ResearchRunRow, RunCompetitorRow
from repositories.company_repo import CompanyRepository, domain_of
from repositories.research_repo import ResearchRunRepository
from schemas.findings import Identification
from schemas.research import ConfirmedCompetitor, ResearchRunCreate
from services.identify_service import clean_identification
from tests.fakes import FakeOpenAI, FakeTavily, sample_findings, tool_call
from tests.test_research_api import API, api, wait_until_finished
from tests.test_research_workflow import happy_script
from workflow.claims import apply_confirmed_competitors, same_company
from workflow.source_harvest import url_key

NOTION = "https://www.notion.so/"
AIRTABLE = "https://airtable.com/"
CODA = "https://coda.io/"
LIST_PAGE = "https://example.com/notion-alternatives"


def identification(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "company",
        "matches": [
            {
                "name": "Notion",
                "website": "https://www.notion.so/product",
                "description": "Notion Labs' connected workspace for docs and wikis.",
                "source_url": NOTION,
            }
        ],
        "product_lines": [{"name": "Docs and wikis", "brands": ["Notion"]}],
        "competitors": [
            {
                "name": "Airtable",
                "website": "https://airtable.com/x",
                "competes_in": "Docs and wikis",
                "reason": "Databases",
                "source_url": AIRTABLE,
            },
            {
                "name": "Coda",
                "website": "https://coda.io",
                "competes_in": "Docs and wikis",
                "reason": "Docs as apps",
                "source_url": LIST_PAGE,
            },
            {
                "name": "Confluence",
                "website": None,
                "competes_in": "Docs and wikis",
                "reason": "Team wiki",
                "source_url": "https://never.read/",
            },
        ],
        "market": None,
        "note": "Matched Notion Labs.",
    }
    data.update(overrides)
    return data


def identify_tavily() -> FakeTavily:
    return FakeTavily(
        search_results={
            "Notion competitors": [
                {"url": NOTION, "title": "Notion", "content": "Your connected workspace"},
                {"url": AIRTABLE, "title": "Airtable", "content": "Build apps"},
                {"url": LIST_PAGE, "title": "Alternatives to Notion", "content": "Coda, Airtable, Confluence"},
            ]
        }
    )


# --- evidence rule and tidying (no LLM) -----------------------------------------------------------


def test_clean_identification_keeps_only_sourced_items_and_tidies_them():
    found = Identification.model_validate(
        identification(
            competitors=[
                *identification()["competitors"],
                {
                    "name": "Notion",
                    "website": None,
                    "competes_in": "Docs and wikis",
                    "reason": "itself",
                    "source_url": NOTION,
                },  # the company itself
                {
                    "name": "Notion AI",
                    "website": "https://notion.so",
                    "competes_in": "Docs and wikis",
                    "reason": "own site",
                    "source_url": NOTION,
                },
                {
                    "name": "airtable",
                    "website": None,
                    "competes_in": "Docs and wikis",
                    "reason": "duplicate",
                    "source_url": AIRTABLE,
                },
            ]
        )
    )
    retrieved = {url_key(u) for u in (NOTION, AIRTABLE, LIST_PAGE)}
    out = clean_identification(found, retrieved, input_type=InputType.NAME)
    assert out["kind"] == "company"
    assert [(m.name, m.website) for m in out["matches"]] == [("Notion", "https://www.notion.so")]
    assert [(c.name, c.website) for c in out["competitors"]] == [
        ("Airtable", "https://airtable.com"),
        ("Coda", "https://coda.io"),
    ]  # Confluence: its source was never retrieved; Notion / Notion AI: the company itself; duplicate dropped


def test_clean_identification_for_a_market_and_for_a_website():
    market = Identification.model_validate(
        identification(
            kind="market",
            matches=[
                {
                    "name": "Milk Makeup",
                    "website": "https://milkmakeup.com",
                    "description": "Cosmetics",
                    "source_url": LIST_PAGE,
                }
            ],
            market={"product": "Fresh packaged milk", "region": "Kerala", "customer_type": None},
            product_lines=[{"name": "Milk", "brands": []}],  # ignored for a market
        )
    )
    retrieved = {url_key(LIST_PAGE), url_key(AIRTABLE)}
    out = clean_identification(market, retrieved, input_type=InputType.NAME)
    assert out["kind"] == "market" and out["competitors"] == [] and out["product_lines"] == []
    assert out["market"].product == "Fresh packaged milk" and out["market"].region == "Kerala"
    assert [m.name for m in out["matches"]] == ["Milk Makeup"]  # the user can still pick the company
    # A website is always a company, whatever the agent said
    assert clean_identification(market, retrieved, input_type=InputType.URL)["kind"] == "company"


def test_competitors_found_only_on_company_databases_are_flagged_and_listed_last():
    tracxn = "https://tracxn.com/d/companies/nestle-india/competitors"
    found = Identification.model_validate(
        identification(
            product_lines=[
                {"name": " Instant noodles ", "brands": ["Maggi", " "]},
                {"name": "Coffee", "brands": ["Nescafé"]},
                {"name": "", "brands": []},
            ],
            competitors=[
                {
                    "name": "Varun Beverages",
                    "website": None,
                    "competes_in": "Beverages",
                    "reason": "Pepsi bottler",
                    "source_url": tracxn,
                },
                {
                    "name": "ITC",
                    "website": "https://www.itcportal.com",
                    "competes_in": "Instant noodles",
                    "reason": "Yippee",
                    "source_url": LIST_PAGE,
                },
                {
                    "name": "Hindustan Unilever",
                    "website": None,
                    "competes_in": "Coffee",
                    "reason": "Bru",
                    "source_url": AIRTABLE,
                },
            ],
        )
    )
    retrieved = {url_key(u) for u in (NOTION, AIRTABLE, LIST_PAGE, tracxn)}
    out = clean_identification(found, retrieved, input_type=InputType.NAME)
    assert [(c.name, c.weak_evidence) for c in out["competitors"]] == [
        ("ITC", False),
        ("Hindustan Unilever", False),
        ("Varun Beverages", True),
    ]
    assert [(p.name, p.brands) for p in out["product_lines"]] == [
        ("Instant noodles", ["Maggi"]),
        ("Coffee", ["Nescafé"]),
    ]
    assert out["competitors"][0].competes_in == "Instant noodles"


def test_database_list_sites():
    from services.identify_service import is_database_list

    assert is_database_list("https://tracxn.com/d/x") and is_database_list("https://www.cbinsights.com/company/x")
    assert not is_database_list("https://economictimes.indiatimes.com/maggi-vs-yippee")
    assert not is_database_list("https://not-tracxn.com/x")


# --- /identify --------------------------------------------------------------------------------------


async def test_identify_endpoint_returns_sourced_matches_and_competitors(tmp_path: Path):
    openai = FakeOpenAI({"Identification": [[tool_call("search_web", query="Notion competitors")], identification()]})
    async with api(tmp_path, openai=openai, tavily=identify_tavily()) as (client, _):
        response = await client.post(f"{API}/identify", json={"query": " Notion "})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Notion" and body["input_type"] == "name" and body["kind"] == "company"
    assert body["matches"][0] == {
        "name": "Notion",
        "website": "https://www.notion.so",
        "description": "Notion Labs' connected workspace for docs and wikis.",
        "source_url": NOTION,
    }
    assert [c["name"] for c in body["competitors"]] == ["Airtable", "Coda"]
    assert body["product_lines"] == [{"name": "Docs and wikis", "brands": ["Notion"]}]
    assert (
        body["competitors"][0]["competes_in"] == "Docs and wikis" and body["competitors"][0]["weak_evidence"] is False
    )
    assert body["total_tokens"] > 0
    request = openai.requests_for("Identification")[0]
    assert "Identify: Notion" in str(request["messages"])


async def test_identify_reads_the_website_first(tmp_path: Path):
    openai = FakeOpenAI({"Identification": [identification(competitors=[])]})
    async with api(tmp_path, openai=openai) as (client, _):
        response = await client.post(f"{API}/identify", json={"query": "notion.so"})
    assert response.status_code == 200
    assert response.json()["input_type"] == "url" and response.json()["matches"] == []  # nothing was retrieved
    assert "website is https://notion.so" in str(openai.requests_for("Identification")[0]["messages"])


async def test_identify_failures_are_502_with_a_way_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async with api(tmp_path, openai=FakeOpenAI({"Identification": [500]})) as (client, _):
        response = await client.post(f"{API}/identify", json={"query": "Notion"})
    assert response.status_code == 502
    assert response.json()["code"] == "identify_failed" and "without confirming" in response.json()["detail"]

    class Slow:
        async def arun(self, prompt: str) -> None:
            raise TimeoutError

    monkeypatch.setattr("services.identify_service.build_agent", lambda *a, **k: Slow())
    async with api(tmp_path) as (client, _):
        response = await client.post(f"{API}/identify", json={"query": "Notion"})
    assert response.status_code == 502 and "took too long" in response.json()["detail"]


async def test_identify_validates_the_query(tmp_path: Path):
    async with api(tmp_path) as (client, _):
        response = await client.post(f"{API}/identify", json={"query": "http://localhost"})
    assert response.status_code == 422


# --- starting with a confirmed list ---------------------------------------------------------------


async def test_research_uses_exactly_the_confirmed_competitors(tmp_path: Path):
    openai = FakeOpenAI(happy_script())
    body = {
        "query": "Notion",
        "company": {"name": "Notion", "website": "notion.so"},
        "competitors": [
            {"name": "Confluence", "website": "https://confluence.com"},
            {"name": "Coda"},
            {"name": "Asana", "added_by_user": True},
        ],
    }
    async with api(tmp_path, openai=openai) as (client, app):
        response = await client.post(API, json=body)
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert response.json()["company_name"] == "Notion"
        detail = await wait_until_finished(client, run_id)
        report = (await client.get(f"{API}/{run_id}/report")).json()
        async with app.state.database.session() as session:
            rows = (await session.scalars(select(RunCompetitorRow).order_by(RunCompetitorRow.position))).all()
            run = await session.get(ResearchRunRow, uuid.UUID(run_id))
            company = await session.get(CompanyRow, run.company_id)

    assert detail["status"] == "succeeded"
    prompt = str(openai.requests_for("ResearchFindings")[0]["messages"])
    assert "Research the company Notion (website: https://notion.so)" in prompt
    assert "1. Confluence (https://confluence.com)" in prompt and "3. Asana" in prompt
    # The Researcher returned Coda and Confluence: shown in the user's order; Asana reported missing
    assert [c["name"] for c in report["competitor_landscape"]] == ["Confluence", "Coda"]
    assert report["meta"]["competitors_confirmed"] is True and report["meta"]["missing_competitors"] == ["Asana"]
    assert any("Asana" in w for w in report["validation"]["warnings"])
    assert [(r.position, r.name, r.origin) for r in rows] == [
        (1, "Confluence", "suggested"),
        (2, "Coda", "suggested"),
        (3, "Asana", "added"),
    ]
    assert company.name == "Notion" and company.domain == "notion.so" and company.last_researched_at is not None


async def test_without_a_list_the_run_is_linked_to_its_company_when_it_finishes(tmp_path: Path):
    async with api(tmp_path, openai=FakeOpenAI({k: v * 2 for k, v in happy_script().items()})) as (client, app):
        first = (await client.post(API, json={"query": "Notion"})).json()["id"]
        await wait_until_finished(client, first)
        second = (await client.post(API, json={"query": "Notion"})).json()["id"]
        await wait_until_finished(client, second)
        async with app.state.database.session() as session:
            ids = set((await session.scalars(select(ResearchRunRow.company_id))).all())
            count = await session.scalar(select(func.count()).select_from(CompanyRow))
    assert len(ids) == 1 and None not in ids and count == 1  # both runs share one company row


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"competitors": [{"name": f"C{i}"} for i in range(7)]}, "at most 6"),
        ({"competitors": [{"name": "Coda"}, {"name": " coda "}]}, "listed twice"),
        ({"competitors": [{"name": "Coda", "website": "http://10.0.0.1"}]}, "IP addresses"),
        ({"competitors": [{"name": "  "}]}, "A name is required"),
        ({"company": {"name": "Notion", "website": "Notion Labs"}}, "Enter a website address"),
    ],
)
async def test_confirmed_list_is_validated(tmp_path: Path, body: dict, message: str):
    async with api(tmp_path) as (client, _):
        response = await client.post(API, json={"query": "Notion", **body})
    assert response.status_code == 422 and message in str(response.json())


# --- matching rules -------------------------------------------------------------------------------


def test_same_company_matches_by_website_or_name():
    assert same_company("Freshsales", None, "Freshsales (Freshworks CRM)", None)
    assert same_company("HubSpot", None, "HubSpot CRM", None)
    assert same_company("Monday", "https://monday.com", "monday CRM", "https://www.monday.com/crm")
    assert not same_company("Coda", None, "Codacy", None)  # short names must match exactly
    assert not same_company("Asana", None, "Airtable", None)
    assert not same_company("", None, "Airtable", None)


def test_apply_confirmed_competitors_fills_in_websites_the_user_gave():
    findings = sample_findings()
    no_site = findings.competitors[0].model_copy(update={"website": None})
    findings = findings.model_copy(update={"competitors": [no_site, findings.competitors[1]]})
    kept, notes, missing = apply_confirmed_competitors(findings, [{"name": "Coda", "website": "https://coda.io/home"}])
    assert [(c.name, c.website) for c in kept.competitors] == [("Coda", "https://coda.io")]
    assert notes == ["Removed competitor Confluence: it was not on the list you confirmed."] and missing == []


async def test_company_rows_are_matched_by_domain_then_name(tmp_path: Path):
    async with api(tmp_path) as (_, app):
        async with app.state.database.session() as session:
            repo = CompanyRepository(session)
            plain = await repo.find_or_create("Notion", None)
            same = await repo.find_or_create("notion ", "https://www.notion.so/pricing")  # learns the domain
            by_domain = await repo.find_or_create("Notion Labs", "https://notion.so")
            other = await repo.find_or_create("Notion", "https://notion-clone.example")
            row = await session.get(CompanyRow, plain)
    assert plain == same == by_domain != other
    assert row.domain == "notion.so"
    assert domain_of("https://WWW.Example.com:8080/x") == "example.com" and domain_of(None) is None


async def test_competitors_for_reads_back_the_confirmed_list(tmp_path: Path):
    async with api(tmp_path) as (_, app):
        async with app.state.database.session() as session:
            run = await ResearchRunRepository(session).create(
                ResearchRunCreate(query="Notion", input_type=InputType.NAME)
            )
            repo = CompanyRepository(session)
            wanted = [
                ConfirmedCompetitor(name="Coda", website="https://coda.io"),
                ConfirmedCompetitor(name="Asana", added_by_user=True),
            ]
            await repo.add_competitors(run.id, wanted)
            assert await repo.competitors_for(run.id) == wanted
