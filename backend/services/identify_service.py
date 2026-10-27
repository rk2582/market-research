"""The confirm step (M12): a quick look at what the user typed, before the full research.

The Identifier agent works out which company (or market) is meant, its main product lines, and the
leading rivals in each. Code then keeps only what is backed by a page the agent actually retrieved,
cleans websites to their homepage, removes duplicates and the company itself, and flags competitors whose
only evidence is a company-database list (those group companies by industry code, not real rivalry —
the Nestlé India run suggested a Pepsi bottler that way); flagged ones go last. The user confirms or
edits the result; nothing is stored until a research run starts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from agents.identifier import IDENTIFIER, build_identify_prompt
from core.config import Settings
from core.errors import AppError
from db.models.research import InputType
from registry.factory import build_agent
from schemas.api import (
    MAX_COMPETITORS,
    CompanyChoice,
    CompetitorChoice,
    IdentifyResponse,
    MarketScopeOut,
    ProductLineOut,
    classify_query,
)
from schemas.findings import Identification
from tools.web_research import TavilyClientLike
from workflow.claims import host_of, name_key, site_root
from workflow.source_harvest import harvest_sources, url_key

logger = logging.getLogger(__name__)

MAX_MATCHES = 3
# Company databases and SEO "alternatives" pages built from them: listed by industry code, not real competition.
DATABASE_LIST_SITES = (
    "tracxn.com",
    "cbinsights.com",
    "owler.com",
    "crunchbase.com",
    "zoominfo.com",
    "growjo.com",
    "craft.co",
    "comparably.com",
    "rocketreach.co",
    "leadiq.com",
    "pitchbook.com",
    "dnb.com",
    "getlatka.com",
    "similarweb.com",
    "semrush.com",
    "zippia.com",
)


def is_database_list(url: str) -> bool:
    host = host_of(url) or ""
    return any(host == site or host.endswith(f".{site}") for site in DATABASE_LIST_SITES)


class IdentifyError(AppError):
    status_code = 502
    default_code = "identify_failed"


def clean_identification(found: Identification, retrieved_urls: set[str], *, input_type: InputType) -> dict[str, Any]:
    """Apply the evidence rule and tidy the lists. Returns the fields of IdentifyResponse."""

    def sourced(url: str) -> bool:
        return url_key(url) in retrieved_urls

    matches: list[CompanyChoice] = []
    for m in found.matches:
        if sourced(m.source_url) and name_key(m.name) not in {name_key(x.name) for x in matches}:
            matches.append(
                CompanyChoice(
                    name=m.name.strip(),
                    website=site_root(m.website),
                    description=m.description.strip(),
                    source_url=m.source_url,
                )
            )
    matches = matches[:MAX_MATCHES]

    # A website is always a company; otherwise trust the agent's call.
    kind = "company" if input_type == InputType.URL else found.kind

    competitors: list[CompetitorChoice] = []
    if kind == "company":
        own_names = {name_key(m.name) for m in matches[:1]}
        own_hosts = {host_of(m.website) for m in matches[:1]} - {None}
        for c in found.competitors:
            if not sourced(c.source_url) or name_key(c.name) in own_names:
                continue
            if host_of(c.website) in own_hosts or name_key(c.name) in {name_key(x.name) for x in competitors}:
                continue
            competitors.append(
                CompetitorChoice(
                    name=c.name.strip(),
                    website=site_root(c.website),
                    competes_in=c.competes_in.strip(),
                    reason=c.reason.strip(),
                    source_url=c.source_url,
                    weak_evidence=is_database_list(c.source_url),
                )
            )
        competitors.sort(key=lambda c: c.weak_evidence)  # stable: keeps the agent's order within each group
    market = (
        MarketScopeOut(
            product=found.market.product.strip(), region=found.market.region, customer_type=found.market.customer_type
        )
        if kind == "market" and found.market is not None
        else None
    )
    product_lines = (
        [
            ProductLineOut(name=p.name.strip(), brands=[b.strip() for b in p.brands if b.strip()])
            for p in found.product_lines
        ]
        if kind == "company"
        else []
    )
    return {
        "kind": kind,
        "matches": matches,
        "product_lines": [p for p in product_lines if p.name][:4],
        "competitors": competitors[:MAX_COMPETITORS],
        "market": market,
        "note": found.note.strip(),
    }


class IdentifyService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        tavily_client: TavilyClientLike | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client
        self._tavily_client = tavily_client

    async def identify(self, raw_query: str) -> IdentifyResponse:
        info = classify_query(raw_query)
        agent = build_agent(IDENTIFIER, self.settings, http_client=self._http_client, tavily_client=self._tavily_client)
        prompt = build_identify_prompt(info.query, website_url=info.website_url)
        try:
            output = await asyncio.wait_for(agent.arun(prompt), timeout=IDENTIFIER.timeout_s)
        except TimeoutError as exc:
            raise IdentifyError("The quick check took too long. You can start without confirming.") from exc
        except Exception as exc:
            logger.exception("Identifier failed for %r", info.query)
            raise IdentifyError("The quick check failed. You can start without confirming.") from exc
        if not isinstance(output.content, Identification):
            raise IdentifyError("The quick check returned no result. You can start without confirming.")

        retrieved = {url_key(s.url) for s in harvest_sources(list(output.tools or []))}
        fields = clean_identification(output.content, retrieved, input_type=info.input_type)
        metrics = output.metrics
        duration = getattr(metrics, "duration", None) if metrics else None
        logger.info(
            "Identified %r as %s: %d match(es), %d competitor(s)",
            info.query,
            fields["kind"],
            len(fields["matches"]),
            len(fields["competitors"]),
        )
        return IdentifyResponse(
            query=info.query,
            input_type=info.input_type,
            total_tokens=getattr(metrics, "total_tokens", 0) or 0,
            duration_ms=int(duration * 1000) if duration is not None else None,
            **fields,
        )
