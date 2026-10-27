"""Public request/response models for /api/v1/research (what the frontend sees)."""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from db.models.research import InputType, RunMode, RunStatus
from schemas.research import ResearchRun, RunTotals

MIN_QUERY, MAX_QUERY = 2, 300

_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
# "notion.so", "www.monzo.com/about" — a bare domain without a scheme (no spaces allowed).
_BARE_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?::\d{1,5})?(?:[/?#]\S*)?$", re.I)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp")


class QueryInfo(BaseModel):
    """A validated query: a company name, or a public http(s) URL (normalised)."""

    query: str
    input_type: InputType
    website_url: str | None = None


def classify_query(raw: str) -> QueryInfo:
    """Decide name vs URL and apply the input rules (plan §13.1). Raises ValueError with a clear message.

    Note: our server never fetches the URL (Tavily does), but we still refuse local and private
    addresses so the tool can't be pointed at internal systems.
    """
    query = " ".join(_CONTROL.sub(" ", raw).split())  # trim, drop control characters, collapse spaces
    if len(query) < MIN_QUERY:
        raise ValueError(f"Enter a company name or website (at least {MIN_QUERY} characters).")
    if len(query) > MAX_QUERY:
        raise ValueError(f"Keep it under {MAX_QUERY} characters.")

    has_scheme = bool(_SCHEME.match(query))
    if not has_scheme and not _BARE_DOMAIN.match(query):
        return QueryInfo(query=query, input_type=InputType.NAME)

    parts = urlsplit(query if has_scheme else f"https://{query}")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("Only http:// and https:// website addresses are allowed.")
    if parts.username or parts.password:
        raise ValueError("Website addresses with a username or password are not allowed.")
    try:
        host = (parts.hostname or "").rstrip(".").lower()
        port = parts.port  # raises ValueError for a bad port
    except ValueError as exc:
        raise ValueError("That website address is not valid.") from exc
    if not host:
        raise ValueError("That website address is not valid.")
    _check_public_host(host)

    netloc = host if port is None else f"{host}:{port}"
    url = urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))
    return QueryInfo(query=query, input_type=InputType.URL, website_url=url)


def _check_public_host(host: str) -> None:
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        raise ValueError("Local addresses are not allowed. Enter a public website.")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        # A host name: it must look like a public domain ("intranet", "0x7f.1" are refused).
        labels = host.split(".")
        if len(labels) < 2 or not labels[-1].isalpha():
            raise ValueError("Enter a public website address, such as https://example.com.") from None
        return
    if not ip.is_global:
        raise ValueError("Private, local or reserved IP addresses are not allowed.")


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


MAX_COMPETITORS = 6


def public_website(value: str | None) -> str | None:
    """An optional website from the user: must be a public http(s) address (same rules as the query)."""
    if value is None or not value.strip():
        return None
    info = classify_query(value)
    if info.input_type != InputType.URL or info.website_url is None:
        raise ValueError("Enter a website address, such as https://example.com.")
    return info.website_url


def _clean_name(value: str) -> str:
    name = " ".join(_CONTROL.sub(" ", value).split())
    if not name:
        raise ValueError("A name is required.")
    return name


class CompanyIn(BaseModel):
    """The company the user confirmed on the confirm screen."""

    name: str = Field(max_length=200, examples=["Notion"])
    website: str | None = Field(default=None, examples=["https://www.notion.so"])

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        return public_website(value)


class CompetitorIn(BaseModel):
    """A competitor to research: suggested by the Identifier or added by the user (website optional)."""

    name: str = Field(max_length=120, examples=["Airtable"])
    website: str | None = None
    added_by_user: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        return public_website(value)


class MarketIn(BaseModel):
    """Market-entry scope (M13): one product in one region."""

    product: str = Field(max_length=200, examples=["Fresh packaged milk"])
    region: str = Field(max_length=100, examples=["Kerala"], description="Required; 'Global' is allowed.")
    customer_type: str | None = Field(default=None, max_length=100, examples=["households"])

    @field_validator("product", "region")
    @classmethod
    def _required(cls, value: str, info: Any) -> str:
        text = " ".join(_CONTROL.sub(" ", value).split())
        if len(text) < 2:
            raise ValueError(f"Enter the {info.field_name} (at least 2 characters).")
        return text[0].upper() + text[1:]  # "milk" → "Milk" (the report title); the rest as typed

    @field_validator("customer_type")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        text = " ".join(_CONTROL.sub(" ", value).split()) if value else ""
        return text or None


class ResearchRequest(BaseModel):
    query: str = Field(
        description="A company name (e.g. 'Notion') or its website (e.g. 'https://monzo.com').",
        examples=["Notion", "https://monzo.com"],
    )
    company: CompanyIn | None = Field(
        default=None, description="Optional: the company confirmed by the user (from /identify)."
    )
    competitors: list[CompetitorIn] = Field(
        default_factory=list,
        max_length=MAX_COMPETITORS,
        description="Optional: research exactly these competitors (1-6). Empty: the Researcher chooses.",
    )
    mode: Literal["company", "market"] = Field(
        default="company", description="'market' for a market-entry report (needs `market`)."
    )
    market: MarketIn | None = None

    @model_validator(mode="after")
    def _market_needs_scope(self) -> ResearchRequest:
        if self.mode == "market" and self.market is None:
            raise ValueError("A market-entry report needs the product and region.")
        if self.mode == "market" and (self.company is not None or self.competitors):
            raise ValueError("A market-entry report takes a product and region, not a company or competitors.")
        return self

    @field_validator("query")
    @classmethod
    def _valid_query(cls, value: str) -> str:
        return classify_query(value).query

    @field_validator("competitors")
    @classmethod
    def _unique_competitors(cls, value: list[CompetitorIn]) -> list[CompetitorIn]:
        seen: set[str] = set()
        for competitor in value:
            key = competitor.name.lower()
            if key in seen:
                raise ValueError(f"{competitor.name} is listed twice.")
            seen.add(key)
        return value


class IdentifyRequest(BaseModel):
    query: str = Field(description="What the user typed: a company, a website, or a market such as 'Milk'.")

    @field_validator("query")
    @classmethod
    def _valid_query(cls, value: str) -> str:
        return classify_query(value).query


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class CompanyChoice(BaseModel):
    name: str
    website: str | None
    description: str
    source_url: str


class CompetitorChoice(BaseModel):
    name: str
    website: str | None
    competes_in: str = ""  # the company's product line it competes in, e.g. "Instant noodles"
    reason: str
    source_url: str
    # Only backed by a company-database list (Tracxn, CB Insights …), which groups by industry code, not real rivalry.
    weak_evidence: bool = False


class ProductLineOut(BaseModel):
    name: str
    brands: list[str] = Field(default_factory=list)


class MarketScopeOut(BaseModel):
    product: str
    region: str | None
    customer_type: str | None


class IdentifyResponse(BaseModel):
    """What the confirm screen shows. Every item has a source the Identifier actually retrieved."""

    query: str
    input_type: InputType
    kind: Literal["company", "market"]
    matches: list[CompanyChoice]
    product_lines: list[ProductLineOut] = Field(default_factory=list)
    competitors: list[CompetitorChoice]
    market: MarketScopeOut | None
    note: str
    total_tokens: int = 0
    duration_ms: int | None = None


StepState = Literal["pending", "running", "completed", "failed", "skipped"]


class ResearchRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query: str
    input_type: InputType
    company_name: str | None
    status: RunStatus
    mode: RunMode = RunMode.COMPANY  # M13: "market" for market-entry reports
    created_at: datetime
    finished_at: datetime | None
    duration_ms: int | None = None
    # From the saved report (None while running or without a report): shown on the home page cards.
    verified_pct: int | None = Field(
        default=None, description="Claims fully supported by their sources, % of all checked."
    )
    competitor_count: int | None = None

    @field_validator("created_at", "finished_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        """Always send times with their zone. PostgreSQL returns UTC-aware values; SQLite returns naive
        ones, which browsers would wrongly read as local time."""
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value

    @classmethod
    def of(cls, run: ResearchRun) -> ResearchRunSummary:
        summary = cls.model_validate(run, from_attributes=True)
        return summary.model_copy(update=report_highlights(run.report))


def verified_pct(supported: int, total: int) -> int | None:
    """Share of checked claims fully supported by their sources (removed claims count as checked)."""
    return round(100 * supported / total) if total > 0 else None


def report_highlights(report: dict | None) -> dict[str, int | None]:
    if not isinstance(report, dict):
        return {}
    validation = report.get("validation") or {}
    competitors = report.get("competitor_landscape")
    try:
        pct = verified_pct(int(validation.get("supported", 0)), int(validation.get("claims_total", 0)))
    except (TypeError, ValueError):
        pct = None
    return {"verified_pct": pct, "competitor_count": len(competitors) if isinstance(competitors, list) else None}


class ResearchRunList(BaseModel):
    items: list[ResearchRunSummary]
    total: int


class StepInfo(BaseModel):
    name: str
    status: StepState
    duration_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class ResearchRunDetail(ResearchRunSummary):
    website_url: str | None
    error: str | None
    agno_run_id: str | None
    current_step: str | None
    totals: RunTotals
    steps: list[StepInfo]
    has_report: bool
