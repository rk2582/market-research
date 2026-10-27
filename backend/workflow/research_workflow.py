"""The market research workflow (Agno Workflow, five fixed steps plus one optional round).

    research → validate → [research_more: deepen] → analyse → strategise → write

M14: `research_more` is an Agno Condition. When code finds gaps in the checked evidence (workflow/gaps.py),
the `deepen` step runs ONE targeted research round, fact-checks only the new claims and hands the merged
evidence to the later steps. If that round fails, the report simply uses the first round's evidence.

Market-entry mode (M13): when the run's `additional_data` has mode "market", the research, analyse and
strategise steps use the market agents (agents/market.py); fact-checking, writing and every code check
are shared.

Failure policy:
- research or validate fails → the run stops (nothing trustworthy to report): outcome "failed".
- analyse, strategise or write fails → later steps continue with what exists and the write step
  always assembles a report: outcome "partial", with the missing sections listed.

Rules learned in the M5 spike (Agno 2.9.0):
- Agno retries a failing step 3 more times by default and still marks the run COMPLETED.
  Every step sets max_retries=0 and catches its own errors; `outcome_from_run()` decides the result.
- Agno's Step has no timeout option → each agent call is wrapped in asyncio.wait_for.
- Agno shows no per-step progress while running → steps call `progress(research_id, step)`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from agno.db.base import BaseDb
from agno.run.agent import RunOutput
from agno.workflow import Condition, Step, Workflow
from agno.workflow.types import StepInput, StepOutput
from pydantic import BaseModel, Field

from agents.analyst import ANALYST, build_analysis_prompt
from agents.competitor_researcher import COMPETITOR_RESEARCHER, build_competitor_prompt
from agents.fact_checker import FACT_CHECKER, build_fact_check_prompt
from agents.gap_researcher import GAP_RESEARCHER
from agents.market import (
    MARKET_ANALYST,
    MARKET_LEAD,
    MARKET_RESEARCHER,
    MARKET_STRATEGIST,
    build_market_analysis_prompt,
    build_market_research_prompt,
    build_market_strategy_prompt,
)
from agents.report_writer import REPORT_WRITER, build_writer_prompt
from agents.researcher import LEAD_RESEARCHER, RESEARCHER, build_research_prompt
from agents.spec import AgentSpec
from agents.strategist import STRATEGIST, build_strategy_prompt
from core.config import Settings
from registry.factory import MARKET_SPECS, WORKFLOW_SPECS, build_agent
from registry.tools_catalog import tavily_client_for
from schemas.findings import (
    Competitor,
    MarketFindings,
    ReportNarrative,
    ResearchFindings,
    SourcedText,
    ValidationResult,
)
from schemas.report import (
    AnalysisOut,
    CheckedClaim,
    ForceOut,
    MarketScopeReport,
    Outcome,
    RecommendationOut,
    Report,
    SecondRoundOut,
    StepUsageOut,
    ValidationSummary,
)
from schemas.research import SourceCreate
from tools.web_research import TavilyClientLike
from workflow.claims import (
    MARKET_FIELDS,
    Findings,
    add_competitor_homepages,
    apply_confirmed_competitors,
    batches,
    competitor_homepages_to_fetch,
    competitors_of,
    current_year,
    dedupe_findings,
    drop_own_brands,
    drop_thin_players,
    extract_claims,
    gate,
    is_estimate,
    merge_competitor,
    merge_verdicts,
    needs_fact_check,
    primary_hosts,
    site_root,
    unread_cited_urls,
    with_competitors,
)
from workflow.gaps import find_gaps, gap_brief, merge_gap_findings
from workflow.report_assembler import (
    Evidence,
    ReportInputs,
    assemble_report,
    process_analysis,
    process_market_analysis,
    process_recommendations,
)
from workflow.source_harvest import fetch_cited_pages, harvest_sources, url_key

logger = logging.getLogger(__name__)

WORKFLOW_ID = "market-research"
STEP_NAMES = ("research", "validate", "analyse", "strategise", "write")
MORE_CONDITION, DEEPEN_STEP = "research_more", "deepen"
COMPETITORS_STEP = "competitors"  # M15: progress while competitors are profiled in parallel (inside research)
MAX_PARALLEL = 6
CONFIRMED_AND_NOT = ("supported", "partially_supported", "unsupported")  # verdicts of kept claims
FACT_CHECK_BATCH = 25

ProgressCallback = Callable[[str, str], Awaitable[None]]  # (research_id, step_name)


# ---------------------------------------------------------------------------
# Step results (stored by Agno as each step's content)
# ---------------------------------------------------------------------------


class StepUsage(BaseModel):
    agent_version: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    duration_ms: int | None = None

    def plus(self, other: StepUsage) -> StepUsage:
        return self.model_copy(
            update={
                "input_tokens": self.input_tokens + other.input_tokens,
                "output_tokens": self.output_tokens + other.output_tokens,
                "total_tokens": self.total_tokens + other.total_tokens,
                "tool_calls": self.tool_calls + other.tool_calls,
                "duration_ms": max(self.duration_ms or 0, other.duration_ms or 0) or None,
            }
        )


class ResearchStepResult(BaseModel):
    findings: ResearchFindings | None = None  # company mode
    market_findings: MarketFindings | None = None  # market mode (M13)
    market_scope: dict[str, Any] | None = None  # product, region, customer_type
    sources: list[SourceCreate]
    usage: StepUsage
    fetched_by_code: int = 0  # pages code fetched afterwards (cited-but-unread pages, competitor homepages)
    competitors_confirmed: bool = False  # the user confirmed the competitor list (M12)
    missing_competitors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # changes code made to the findings (shown as warnings)
    # M15: the lead researcher's and the parallel competitor researchers' own usage, and agent versions
    lead_usage: StepUsage | None = None
    competitor_usage: StepUsage | None = None
    agents: dict[str, str] = Field(default_factory=dict)
    profiled: list[str] = Field(default_factory=list)  # competitors whose own researcher succeeded (M15)

    @property
    def is_market(self) -> bool:
        return self.market_findings is not None

    @property
    def subject(self) -> Findings:
        found = self.market_findings or self.findings
        if found is None:  # research_step always sets one of the two
            raise ValueError("Research step result has no findings.")
        return found

    @property
    def name(self) -> str:
        if self.market_findings is not None:
            return self.market_findings.market_name
        return self.subject.company.name  # type: ignore[union-attr]


@dataclass
class CompetitorRun:
    """One parallel competitor researcher's result (M15)."""

    pick: Competitor
    found: Competitor | None = None
    usage: StepUsage | None = None
    tools: list[Any] = field(default_factory=list)
    error: str | None = None


def confirmed_pick(confirmed: dict[str, Any]) -> Competitor:
    """A competitor the user confirmed (M12), as a starting point for its researcher. The placeholder
    description has no source: if the researcher fails, the competitor is reported missing, never profiled
    from this."""
    return Competitor(
        name=confirmed["name"],
        website=site_root(confirmed.get("website")),
        relation="direct",
        description=SourcedText(text=confirmed["name"], source_urls=[], kind="fact"),
        offerings=[],
        pricing=None,
        target_segments=[],
        positioning=None,
    )


class ValidateStepResult(BaseModel):
    claims: list[CheckedClaim]  # kept after the gate
    validation: ValidationSummary
    usage: StepUsage | None = None


class AnalyseStepResult(BaseModel):
    analysis: AnalysisOut
    forces: list[ForceOut] = Field(default_factory=list)  # market mode
    warnings: list[str] = Field(default_factory=list)
    usage: StepUsage


class StrategyStepResult(BaseModel):
    recommendations: list[RecommendationOut]
    checks_before_investing: list[str] = Field(default_factory=list)  # market mode
    warnings: list[str] = Field(default_factory=list)
    usage: StepUsage


class DeepenStepResult(BaseModel):
    """M14: merged evidence after the second round (None when the round failed: use round 1's)."""

    research: ResearchStepResult | None = None
    validated: ValidateStepResult | None = None
    second_round: SecondRoundOut
    usage: StepUsage | None = None


class WriteStepResult(BaseModel):
    report: Report
    usage: StepUsage | None = None


class RunOutcome(BaseModel):
    """What a finished workflow run means for the product (used by the API in M7)."""

    outcome: Outcome
    report: Report | None = None
    error: str | None = None
    failed_step: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StepFailure(Exception):
    pass


def usage_from(output: RunOutput, *, agent_version: str, model: str) -> StepUsage:
    metrics = output.metrics
    duration = getattr(metrics, "duration", None) if metrics else None
    return StepUsage(
        agent_version=agent_version,
        model=model,
        input_tokens=getattr(metrics, "input_tokens", 0) or 0,
        output_tokens=getattr(metrics, "output_tokens", 0) or 0,
        total_tokens=getattr(metrics, "total_tokens", 0) or 0,
        tool_calls=len(output.tools or []),
        duration_ms=int(duration * 1000) if duration is not None else None,
    )


def failed(step: str, message: str) -> StepOutput:
    """Stop the workflow (research / validate): no Agno retries, no later steps."""
    logger.warning("Step %s failed, stopping run: %s", step, message)
    return StepOutput(content={"error": message}, success=False, error=message, stop=True)


def skipped(step: str, message: str) -> StepOutput:
    """Record a failure but let the run continue towards a partial report (analyse / strategise / write)."""
    logger.warning("Step %s failed, continuing for a partial report: %s", step, message)
    return StepOutput(content={"error": message}, success=False, error=message)


def _content(step_input: StepInput, step: str, model: type[BaseModel]) -> Any:
    """A previous step's result, or None if that step failed or did not run."""
    raw = step_input.get_step_content(step)
    if not isinstance(raw, dict) or "error" in raw:
        return None
    return model.model_validate(raw)


def _error(step_input: StepInput, step: str) -> str | None:
    raw = step_input.get_step_content(step)
    return raw.get("error") if isinstance(raw, dict) else None


def _usage_out(step: str, usage: StepUsage | None) -> StepUsageOut | None:
    return StepUsageOut(step=step, **usage.model_dump()) if usage else None


def _evidence(step_input: StepInput) -> tuple[Any, Any, DeepenStepResult | None]:
    """Research and checked claims for the later steps: after the second round when it ran and worked."""
    research = _content(step_input, "research", ResearchStepResult)
    validated = _content(step_input, "validate", ValidateStepResult)
    deepened = _content(step_input, DEEPEN_STEP, DeepenStepResult)
    if deepened is not None and deepened.research is not None and deepened.validated is not None:
        research, validated = deepened.research, deepened.validated
    if research is not None and validated is not None and research.market_findings is not None:
        research, validated = _without_thin_players(research, validated)
    return research, validated, deepened


def _without_thin_players(
    research: ResearchStepResult, validated: ValidateStepResult
) -> tuple[ResearchStepResult, ValidateStepResult]:
    """Leave out market players with fewer than 2 confirmed facts, with their claims and counts."""
    findings, kept, notes = drop_thin_players(research.market_findings, validated.claims)  # type: ignore[arg-type]
    if not notes:
        return research, validated
    gone = [c for c in validated.claims if c not in kept]
    v = validated.validation
    count = {verdict: sum(1 for c in gone if c.verdict == verdict) for verdict in CONFIRMED_AND_NOT}
    summary = v.model_copy(
        update={
            "claims_total": v.claims_total - len(gone),
            "supported": v.supported - count["supported"],
            "partially_supported": v.partially_supported - count["partially_supported"],
            "unsupported": v.unsupported - count["unsupported"],
            "warnings": [*v.warnings, *notes],
        }
    )
    return (
        research.model_copy(update={"market_findings": findings}),
        validated.model_copy(update={"claims": kept, "validation": summary}),
    )


def _with_sources(sources: list[SourceCreate], more: list[SourceCreate]) -> list[SourceCreate]:
    """Add pages not seen before; a full page read later replaces a search snippet."""
    by_key = {url_key(s.url): s for s in sources}
    for page in more:
        key = url_key(page.url)
        if key not in by_key or (page.retrieved_by == "extract" and by_key[key].retrieved_by == "search"):
            by_key[key] = page
    return list(by_key.values())


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def build_research_workflow(
    settings: Settings,
    agno_db: BaseDb | None,
    *,
    http_client: httpx.AsyncClient | None = None,
    tavily_client: TavilyClientLike | None = None,
    progress: ProgressCallback | None = None,
) -> Workflow:
    """`http_client` / `tavily_client` replace OpenAI / Tavily in tests; `progress` reports step starts."""

    async def report_progress(step_input: StepInput, step: str) -> None:
        research_id = (step_input.additional_data or {}).get("research_id")
        if progress is None or not research_id:
            return
        try:
            await progress(str(research_id), step)
        except Exception:  # progress must never break a run
            logger.exception("Progress callback failed for %s / %s", research_id, step)

    async def run_agent(spec: AgentSpec, prompt: str) -> tuple[Any, StepUsage]:
        agent = build_agent(spec, settings, http_client=http_client, tavily_client=tavily_client)
        try:
            output = await asyncio.wait_for(agent.arun(prompt), timeout=spec.timeout_s)
        except TimeoutError as exc:
            raise StepFailure(f"{spec.name} timed out after {spec.timeout_s:.0f} s") from exc
        except Exception as exc:
            logger.exception("%s crashed", spec.name)
            raise StepFailure(f"{spec.name} error: {type(exc).__name__}: {exc}") from exc
        if not isinstance(output.content, spec.output_schema):
            status = getattr(output.status, "value", output.status)
            raise StepFailure(f"{spec.name} returned no valid output (run status: {status})")
        usage = usage_from(output, agent_version=spec.version, model=settings.model_for(spec.key))
        return output.content, usage

    # --- 1. research -------------------------------------------------------
    # The Researcher also needs its tool calls (for sources), so it has its own runner.
    async def run_researcher(spec: AgentSpec, prompt: str) -> tuple[Any, StepUsage, list[Any]]:
        agent = build_agent(spec, settings, http_client=http_client, tavily_client=tavily_client)
        try:
            output = await asyncio.wait_for(agent.arun(prompt), timeout=spec.timeout_s)
        except TimeoutError as exc:
            raise StepFailure(f"{spec.name} timed out after {spec.timeout_s:.0f} s") from exc
        except Exception as exc:
            logger.exception("%s crashed", spec.name)
            raise StepFailure(f"{spec.name} error: {type(exc).__name__}: {exc}") from exc
        if not isinstance(output.content, spec.output_schema):
            status = getattr(output.status, "value", output.status)
            raise StepFailure(f"{spec.name} returned no valid findings (run status: {status})")
        usage = usage_from(output, agent_version=spec.version, model=settings.model_for(spec.key))
        return output.content, usage, list(output.tools or [])

    async def research_competitor(pick: Competitor, against: str, market: bool) -> CompetitorRun:
        """One competitor / player, profiled by its own small researcher (M15). Never raises."""
        prompt = build_competitor_prompt(pick.name, pick.website, pick.relation, against=against, market=market)
        try:
            found, usage, tools = await run_researcher(COMPETITOR_RESEARCHER, prompt)
        except StepFailure as exc:
            return CompetitorRun(pick=pick, error=str(exc))
        return CompetitorRun(pick=pick, found=found, usage=usage, tools=tools)

    async def research_step(step_input: StepInput) -> StepOutput:
        await report_progress(step_input, "research")
        started = time.perf_counter()
        data = step_input.additional_data or {}
        query = str(step_input.input or "").strip()
        if not query:
            return failed("research", "No company name or URL was given")
        confirmed = list(data.get("competitors") or [])
        scope = data.get("market") if data.get("mode") == "market" else None
        parallel = settings.parallel_research_enabled
        if scope:
            spec, prompt = (
                MARKET_LEAD if parallel else MARKET_RESEARCHER,
                build_market_research_prompt(scope["product"], scope["region"], scope.get("customer_type")),
            )
        else:
            spec, prompt = (
                LEAD_RESEARCHER if parallel else RESEARCHER,
                build_research_prompt(
                    query,
                    website_url=data.get("website_url"),
                    company=data.get("company"),
                    competitors=confirmed,
                    parallel=parallel,
                ),
            )
        try:
            findings, usage, tools = await run_researcher(spec, prompt)
        except StepFailure as exc:
            return failed("research", str(exc))
        lead_usage = usage
        competitors = [c.model_copy(update={"website": site_root(c.website)}) for c in competitors_of(findings)]
        findings = with_competitors(findings, competitors)
        if isinstance(findings, ResearchFindings):
            company = findings.company.model_copy(update={"website": site_root(findings.company.website)})
            findings = findings.model_copy(update={"company": company})
        findings = dedupe_findings(findings)
        missing: list[str] = []
        notes: list[str] = []
        if isinstance(findings, ResearchFindings) and not confirmed:
            findings, notes = drop_own_brands(findings)  # before profiling: never spend a researcher on them
        agents = {spec.key: spec.version}
        competitor_usage: StepUsage | None = None
        profiled_names: list[str] = []
        if parallel:
            await report_progress(step_input, COMPETITORS_STEP)
            picks = [confirmed_pick(c) for c in confirmed] if confirmed else competitors_of(findings)
            against = findings.market_name if isinstance(findings, MarketFindings) else findings.company.name
            phase = time.perf_counter()
            if len(picks) > MAX_PARALLEL:
                notes.append(f"Only the first {MAX_PARALLEL} competitors were profiled.")
            runs = await asyncio.gather(
                *(research_competitor(p, against, isinstance(findings, MarketFindings)) for p in picks[:MAX_PARALLEL])
            )
            profiled: list[Competitor] = []
            for run in runs:
                tools += run.tools
                if run.usage is not None:
                    competitor_usage = run.usage if competitor_usage is None else competitor_usage.plus(run.usage)
                if run.found is not None:
                    profiled.append(merge_competitor(run.pick, run.found))
                    profiled_names.append(run.pick.name)
                else:
                    notes.append(f"Could not profile {run.pick.name} in detail: {run.error}")
                    if run.pick.description.source_urls:  # keep what the lead found about it
                        profiled.append(run.pick)
            if competitor_usage is not None:
                competitor_usage = competitor_usage.model_copy(
                    update={
                        "agent_version": COMPETITOR_RESEARCHER.version,
                        "duration_ms": int((time.perf_counter() - phase) * 1000),
                    }
                )
                usage = usage.plus(competitor_usage)
            agents["competitor_researcher"] = COMPETITOR_RESEARCHER.version
            findings = dedupe_findings(with_competitors(findings, profiled))
            logger.info("Profiled %d of %d competitors in parallel", sum(r.found is not None for r in runs), len(runs))
        if isinstance(findings, ResearchFindings) and confirmed:  # the user's list wins, even over own brands
            findings, confirmed_notes, missing = apply_confirmed_competitors(findings, confirmed)
            notes += confirmed_notes
        # Market players with too few facts are left out later (_evidence), after the second round tried them.
        sources = harvest_sources(tools)
        # One batched fetch: competitors' own homepages (better evidence than third-party lists) and
        # pages the Researcher cited without opening, so the Fact-Checker judges real text.
        fetched = await fetch_cited_pages(
            tavily_client or tavily_client_for(settings),
            [*competitor_homepages_to_fetch(findings, sources), *unread_cited_urls(findings, sources)],
        )
        result = ResearchStepResult(
            findings=findings if isinstance(findings, ResearchFindings) else None,
            market_findings=findings if isinstance(findings, MarketFindings) else None,
            market_scope=scope,
            sources=[*sources, *fetched],
            usage=usage.model_copy(update={"duration_ms": int((time.perf_counter() - started) * 1000)})
            if parallel
            else usage,
            lead_usage=lead_usage if parallel else None,
            competitor_usage=competitor_usage,
            agents=agents,
            profiled=profiled_names,
            fetched_by_code=len(fetched),
            notes=notes,
            competitors_confirmed=bool(confirmed),
            missing_competitors=missing,
        )
        logger.info(
            "Research done (%s): %d competitors, %d sources, %d tokens, %d tool calls",
            "market" if scope else "company",
            len(competitors_of(findings)),
            len(result.sources),
            usage.total_tokens,
            usage.tool_calls,
        )
        return StepOutput(content=result.model_dump(mode="json"))

    async def fact_check(
        claims: list[Any], sources: list[SourceCreate]
    ) -> tuple[list[Any], StepUsage | None, list[str]]:
        """Fact-check claims in parallel batches. Returns verdicts, combined usage and batch errors."""

        async def check(batch: list[Any]) -> tuple[ValidationResult, StepUsage]:
            return await run_agent(FACT_CHECKER, build_fact_check_prompt(batch, sources))

        results = await asyncio.gather(*(check(b) for b in batches(claims, FACT_CHECK_BATCH)), return_exceptions=True)
        verdicts: list[Any] = []
        usage: StepUsage | None = None
        errors = [str(r) for r in results if isinstance(r, BaseException)]
        for result in results:
            if isinstance(result, BaseException):
                continue
            verdict_set, batch_usage = result
            verdicts.extend(verdict_set.verdicts)
            usage = batch_usage if usage is None else usage.plus(batch_usage)
        return verdicts, usage, errors

    # --- 2. validate --------------------------------------------------------
    async def validate_step(step_input: StepInput) -> StepOutput:
        await report_progress(step_input, "validate")
        research: ResearchStepResult | None = _content(step_input, "research", ResearchStepResult)
        if research is None:
            return failed("validate", "No research results to validate")
        claims = add_competitor_homepages(
            extract_claims(research.subject, research.sources), research.subject, research.sources
        )
        to_check = [c for c in claims if needs_fact_check(c)]
        verdicts, usage, errors = await fact_check(to_check, research.sources)
        if to_check and errors and not verdicts:
            return failed("validate", f"Fact-checking failed: {errors[0]}")

        kept, summary = gate(merge_verdicts(claims, verdicts, research.sources))
        summary.warnings.extend(research.notes)
        if research.fetched_by_code:
            summary.warnings.append(
                f"{research.fetched_by_code} page(s) (competitor homepages, or pages cited without being read)"
                " were fetched by code for fact-checking."
            )
        if errors:
            summary.warnings.append(f"{len(errors)} fact-check batch(es) failed; those claims are marked unassessed.")
        result = ValidateStepResult(claims=kept, validation=summary, usage=usage)
        logger.info(
            "Validation done: %d claims — %d supported, %d partial, %d unsupported, %d contradicted",
            summary.claims_total,
            summary.supported,
            summary.partially_supported,
            summary.unsupported,
            summary.contradicted,
        )
        return StepOutput(content=result.model_dump(mode="json"))

    # --- 2b. research more (M14, only when code finds gaps) -------------------
    def needs_more_research(step_input: StepInput) -> bool:
        if not settings.research_more_enabled:
            return False
        research = _content(step_input, "research", ResearchStepResult)
        validated = _content(step_input, "validate", ValidateStepResult)
        if research is None or validated is None:
            return False
        return bool(find_gaps(research.subject, validated.claims, current_year(), research.profiled))

    async def deepen_step(step_input: StepInput) -> StepOutput:
        """One targeted round for the gaps; never fails the run (round 1's evidence stays usable)."""
        await report_progress(step_input, DEEPEN_STEP)
        research: ResearchStepResult = _content(step_input, "research", ResearchStepResult)
        validated: ValidateStepResult = _content(step_input, "validate", ValidateStepResult)
        gaps = find_gaps(research.subject, validated.claims, current_year(), research.profiled)
        asks = [g.ask for g in gaps]
        started = time.perf_counter()

        def give_up(message: str, usage: StepUsage | None = None) -> StepOutput:
            logger.warning("Second research round failed, using round 1: %s", message)
            second = SecondRoundOut(
                gaps=asks,
                error=message,
                total_tokens=usage.total_tokens if usage else 0,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return StepOutput(content=DeepenStepResult(second_round=second, usage=usage).model_dump(mode="json"))

        try:
            found, usage, tools = await run_researcher(
                GAP_RESEARCHER, gap_brief(gaps, research.subject, research.market_scope)
            )
        except StepFailure as exc:
            return give_up(str(exc))
        sources = _with_sources(research.sources, harvest_sources(tools))
        have = {url_key(s.url) for s in sources}
        # Read the pages it cited without opening, and players' homepages it found, in one batched fetch.
        wanted = [u for st in found.statements for u in st.statement.source_urls if url_key(u) not in have]
        wanted += [
            home
            for st in found.statements
            if st.website and (home := site_root(st.website)) and url_key(home) not in have
        ]
        sources = _with_sources(sources, await fetch_cited_pages(tavily_client or tavily_client_for(settings), wanted))
        merged = merge_gap_findings(
            research.subject,
            found,
            gaps,
            sources,
            first_id=validated.validation.claims_total + 1,
            existing=validated.claims,
        )
        new_claims = add_competitor_homepages(merged.claims, merged.findings, sources)
        to_check = [c for c in new_claims if needs_fact_check(c)]
        verdicts, check_usage, errors = await fact_check(to_check, sources)
        if to_check and errors and not verdicts:
            return give_up(f"Fact-checking the new claims failed: {errors[0]}", usage)
        kept, new_summary = gate(merge_verdicts(new_claims, verdicts, sources))
        old = validated.validation
        combined = old.model_copy(
            update={
                "claims_total": old.claims_total + new_summary.claims_total,
                "supported": old.supported + new_summary.supported,
                "partially_supported": old.partially_supported + new_summary.partially_supported,
                "unsupported": old.unsupported + new_summary.unsupported,
                "contradicted": old.contradicted + new_summary.contradicted,
                "warnings": [*old.warnings, *new_summary.warnings, *merged.notes],
            }
        )
        is_market = isinstance(merged.findings, MarketFindings)
        new_research = research.model_copy(
            update={
                "findings": None if is_market else merged.findings,
                "market_findings": merged.findings if is_market else None,
                "sources": sources,
            }
        )
        new_validated = ValidateStepResult(
            claims=[*validated.claims, *kept], validation=combined, usage=validated.usage
        )
        remaining = {g.key for g in find_gaps(merged.findings, new_validated.claims, current_year(), research.profiled)}
        total = usage.plus(check_usage) if check_usage else usage
        second = SecondRoundOut(
            gaps=asks,
            filled=sum(1 for g in gaps if g.key not in remaining),
            new_claims=len(kept),
            total_tokens=total.total_tokens,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        combined.warnings.append(
            f"Second research round: {len(gaps)} gap(s), {second.filled} filled, {len(kept)} new claim(s)."
        )
        if errors:
            combined.warnings.append(f"{len(errors)} fact-check batch(es) of the second round failed.")
        logger.info("Second round: %d gaps, %d filled, %d new claims", len(gaps), second.filled, len(kept))
        result = DeepenStepResult(
            research=new_research,
            validated=new_validated,
            second_round=second,
            usage=total.model_copy(update={"duration_ms": second.duration_ms}),
        )
        return StepOutput(content=result.model_dump(mode="json"))

    # --- 3. analyse ---------------------------------------------------------
    async def analyse_step(step_input: StepInput) -> StepOutput:
        await report_progress(step_input, "analyse")
        research, validated, _ = _evidence(step_input)
        players = [c.name for c in competitors_of(research.subject)]
        evidence = Evidence(validated.claims, research.sources, primary_hosts(research.subject))
        forces: list[ForceOut] = []
        try:
            if research.is_market:
                raw, usage = await run_agent(
                    MARKET_ANALYST,
                    build_market_analysis_prompt(
                        research.name, players, validated.claims, primary_hosts(research.subject)
                    ),
                )
                analysis, forces, warnings = process_market_analysis(raw, evidence)
            else:
                raw, usage = await run_agent(ANALYST, build_analysis_prompt(research.name, players, validated.claims))
                analysis, warnings = process_analysis(raw, evidence)
        except StepFailure as exc:
            return skipped("analyse", str(exc))
        result = AnalyseStepResult(analysis=analysis, forces=forces, warnings=warnings, usage=usage)
        return StepOutput(content=result.model_dump())

    # --- 4. strategise ------------------------------------------------------
    async def strategise_step(step_input: StepInput) -> StepOutput:
        await report_progress(step_input, "strategise")
        analysed: AnalyseStepResult | None = _content(step_input, "analyse", AnalyseStepResult)
        if analysed is None:
            return skipped("strategise", "Skipped: no analysis available")
        research, validated, _ = _evidence(step_input)
        a = analysed.analysis
        checks: list[str] = []
        try:
            if research.is_market:  # signals for/against travel in the SWOT's strengths/weaknesses slots
                insights = {
                    "signals_for": a.swot.strengths,
                    "signals_against": a.swot.weaknesses,
                    "trends": a.trends,
                    "opportunities": a.opportunities,
                    "risks": a.risks,
                }
                forces = [f.model_dump(include={"force", "rating", "reason"}) for f in analysed.forces]
                raw, usage = await run_agent(
                    MARKET_STRATEGIST, build_market_strategy_prompt(research.name, insights, forces, a.data_gaps)
                )
                checks = [c.strip() for c in raw.checks_before_investing if c.strip()]
            else:
                insights = {
                    "strengths": a.swot.strengths,
                    "weaknesses": a.swot.weaknesses,
                    "swot_opportunities": a.swot.opportunities,
                    "threats": a.swot.threats,
                    "trends": a.trends,
                    "opportunities": a.opportunities,
                    "risks": a.risks,
                }
                raw, usage = await run_agent(STRATEGIST, build_strategy_prompt(research.name, insights, a.data_gaps))
        except StepFailure as exc:
            return skipped("strategise", str(exc))
        recs, warnings = process_recommendations(
            raw, a, Evidence(validated.claims, research.sources, primary_hosts(research.subject))
        )
        result = StrategyStepResult(
            recommendations=recs, checks_before_investing=checks, warnings=warnings, usage=usage
        )
        return StepOutput(content=result.model_dump())

    # --- 5. write (always assembles a report) ---------------------------------
    async def write_step(step_input: StepInput) -> StepOutput:
        await report_progress(step_input, "write")
        research, validated, deepened = _evidence(step_input)
        analysed: AnalyseStepResult | None = _content(step_input, "analyse", AnalyseStepResult)
        strategy: StrategyStepResult | None = _content(step_input, "strategise", StrategyStepResult)

        step_errors = {name: err for name in ("analyse", "strategise") if (err := _error(step_input, name)) is not None}
        narrative: ReportNarrative | None = None
        write_usage: StepUsage | None = None
        if analysed is not None:
            try:
                narrative, write_usage = await run_agent(
                    REPORT_WRITER, build_writer_prompt(_writer_material(research, validated, analysed, strategy))
                )
            except StepFailure as exc:
                step_errors["write"] = str(exc)
                logger.warning("Report writer failed; assembling without prose: %s", exc)
        else:
            step_errors.setdefault("write", "Skipped: no analysis available")

        usage = [
            u
            for u in (
                *(
                    [
                        _usage_out("research", research.lead_usage),
                        _usage_out(COMPETITORS_STEP, research.competitor_usage),
                    ]
                    if research.lead_usage is not None
                    else [_usage_out("research", research.usage)]
                ),
                _usage_out("validate", validated.usage),
                _usage_out(DEEPEN_STEP, deepened.usage if deepened else None),
                _usage_out("analyse", analysed.usage if analysed else None),
                _usage_out("strategise", strategy.usage if strategy else None),
                _usage_out("write", write_usage),
            )
            if u is not None
        ]
        report = assemble_report(
            ReportInputs(
                query=str(step_input.input or ""),
                findings=research.subject,
                sources=research.sources,
                claims=validated.claims,
                validation=validated.validation,
                analysis=analysed.analysis if analysed else None,
                recommendations=strategy.recommendations if strategy else None,
                narrative=narrative,
                usage=usage,
                step_errors=step_errors,
                warnings=[*(analysed.warnings if analysed else []), *(strategy.warnings if strategy else [])],
                agent_versions={
                    **{spec.key: spec.version for spec in (MARKET_SPECS if research.is_market else WORKFLOW_SPECS)},
                    **research.agents,
                    **({"gap_researcher": GAP_RESEARCHER.version} if deepened else {}),
                },
                competitors_confirmed=research.competitors_confirmed,
                missing_competitors=research.missing_competitors,
                market_scope=_scope_report(research.market_scope),
                forces=analysed.forces if analysed else [],
                checks_before_investing=strategy.checks_before_investing if strategy else [],
                second_round=deepened.second_round if deepened else None,
            )
        )
        logger.info("Report assembled: outcome=%s, %d total tokens", report.meta.outcome, report.meta.total_tokens)
        return StepOutput(content=WriteStepResult(report=report, usage=write_usage).model_dump(mode="json"))

    return Workflow(
        id=WORKFLOW_ID,
        name="Market research",
        description="Research → fact-check → analyse → recommend → write a sourced market intelligence report.",
        db=agno_db,
        steps=[
            Step(name="research", executor=research_step, max_retries=0),
            Step(name="validate", executor=validate_step, max_retries=0),
            Condition(
                name=MORE_CONDITION,
                evaluator=needs_more_research,
                steps=[Step(name=DEEPEN_STEP, executor=deepen_step, max_retries=0)],
            ),
            Step(name="analyse", executor=analyse_step, max_retries=0),
            Step(name="strategise", executor=strategise_step, max_retries=0),
            Step(name="write", executor=write_step, max_retries=0),
        ],
    )


def _scope_report(scope: dict[str, Any] | None) -> MarketScopeReport | None:
    if not scope:
        return None
    return MarketScopeReport(product=scope["product"], region=scope["region"], customer_type=scope.get("customer_type"))


def _writer_material(
    research: ResearchStepResult,
    validated: ValidateStepResult,
    analysed: AnalyseStepResult,
    strategy: StrategyStepResult | None,
) -> dict[str, Any]:
    """Compact input for the Report Writer: claims it may cite, plus the analysis and recommendations."""
    findings = research.market_findings or research.findings
    citable = [c for c in validated.claims if c.verdict in ("supported", "partially_supported")]

    def insight_texts(items: list[Any]) -> list[dict[str, Any]]:
        return [{"text": i.text, "claims": i.claim_ids} for i in items]

    a = analysed.analysis
    claims = [{"id": c.id, "about": c.subject, "topic": c.label, "claim": c.text} for c in citable]
    recommendations = [
        {"priority": r.priority, "title": r.title, "rationale": r.rationale, "next_steps": r.next_steps}
        for r in (strategy.recommendations if strategy else [])
    ]
    if isinstance(findings, MarketFindings):
        topics = {c.label for c in citable}
        primary = primary_hosts(findings)
        return {
            "mode": "market",
            "market": findings.market_name,
            "scope": research.market_scope,
            "players": [c.name for c in findings.players],
            "claims_you_may_cite": [
                {**claim, "estimate": True} if is_estimate(c, primary) else claim
                for claim, c in zip(claims, citable, strict=True)
            ],
            "not_found_in_public_sources": [
                label for name, label in MARKET_FIELDS if name != "scope_note" and label not in topics
            ],
            "forces": [f.model_dump(include={"force", "rating", "reason"}) for f in analysed.forces],
            "signals_for": insight_texts(a.swot.strengths),
            "signals_against": insight_texts(a.swot.weaknesses),
            "trends": insight_texts(a.trends),
            "opportunities": insight_texts(a.opportunities),
            "risks": insight_texts(a.risks),
            "entry_options": recommendations,
            "checks_before_investing": strategy.checks_before_investing if strategy else [],
            "fact_check": validated.validation.model_dump(exclude={"warnings"}),
        }
    if findings is None:
        raise ValueError("Research step result has no findings.")
    return {
        "company": {"name": findings.company.name, "website": findings.company.website},
        "competitors": [{"name": c.name, "relation": c.relation} for c in findings.competitors],
        "claims_you_may_cite": [{"id": c.id, "about": c.subject, "topic": c.label, "claim": c.text} for c in citable],
        "swot": {
            "strengths": insight_texts(a.swot.strengths),
            "weaknesses": insight_texts(a.swot.weaknesses),
            "opportunities": insight_texts(a.swot.opportunities),
            "threats": insight_texts(a.swot.threats),
        },
        "trends": insight_texts(a.trends),
        "opportunities": insight_texts(a.opportunities),
        "risks": insight_texts(a.risks),
        "recommendations": [
            {"priority": r.priority, "title": r.title, "rationale": r.rationale, "next_steps": r.next_steps}
            for r in (strategy.recommendations if strategy else [])
        ],
        "fact_check": validated.validation.model_dump(exclude={"warnings"}),
    }


def outcome_from_run(run: Any) -> RunOutcome:
    """Turn an Agno workflow run into succeeded / partial / failed (Agno itself always says COMPLETED)."""
    results = list(getattr(run, "step_results", None) or [])
    by_name = {getattr(s, "step_name", None): s for s in results}
    write = by_name.get("write")
    if write is not None and getattr(write, "success", False) and isinstance(write.content, dict):
        report = WriteStepResult.model_validate(write.content).report
        return RunOutcome(outcome=report.meta.outcome, report=report)
    for name in STEP_NAMES:
        step = by_name.get(name)
        if step is not None and not getattr(step, "success", True) and getattr(step, "stop", False):
            return RunOutcome(outcome="failed", error=step.error or "Step failed", failed_step=name)
    status = getattr(getattr(run, "status", None), "value", getattr(run, "status", None))
    return RunOutcome(outcome="failed", error=f"Workflow ended without a report (status: {status})")
