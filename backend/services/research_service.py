"""Research runs: start them, report their status, and save their results to our tables.

How a run moves through the system:
1. `start()` inserts a `research_runs` row (status running) and starts the Agno workflow in the
   background. It returns at once (the API answers 202).
2. While it runs, each workflow step calls `progress()`, which writes `current_step`.
3. Agno does not tell us when a background run ends, so we check when someone asks: every read
   (`detail`, `list_runs`, `report`) and every `start` first calls `reconcile_running()`. Runs that
   Agno has finished are "finalised": status, totals, report and sources are written to our tables.
4. After a restart, background tasks are gone. `reconcile_after_restart()` (app startup) finalises
   runs that did finish and marks the rest failed.

One asyncio.Lock makes start (count + insert) and finalising safe within this single process.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agno.workflow import Workflow

from core.config import Settings
from core.errors import AppError, CapacityError, ConflictError, NotFoundError
from db.models.research import RunMode, RunStatus
from db.session import Database
from repositories.company_repo import CompanyRepository
from repositories.research_repo import ResearchRunRepository
from repositories.source_repo import SourceRepository
from schemas.api import (
    CompanyIn,
    CompetitorIn,
    MarketIn,
    ResearchRunDetail,
    ResearchRunList,
    ResearchRunSummary,
    StepInfo,
    classify_query,
)
from schemas.report import Report
from schemas.research import ConfirmedCompetitor, ResearchRun, ResearchRunCreate, RunTotals, SourceCreate
from workflow.research_workflow import COMPETITORS_STEP, DEEPEN_STEP, STEP_NAMES, ResearchStepResult, outcome_from_run
from workflow.source_harvest import url_key

logger = logging.getLogger(__name__)

FINISHED_AGNO_STATUSES = frozenset({"COMPLETED", "ERROR", "CANCELLED"})
START_GRACE_S = 60  # a run with no Agno run id after this long never started
RESTART_ERROR = "Interrupted: the server restarted while this run was in progress. Please start it again."
_OUTCOME_STATUS = {"succeeded": RunStatus.SUCCEEDED, "partial": RunStatus.PARTIAL, "failed": RunStatus.FAILED}


def _status(value: Any) -> str:
    """Agno run status as a plain string (an enum in memory, a string after reload)."""
    return str(getattr(value, "value", value) or "")


def _usage(content: Any) -> dict[str, Any]:
    usage = content.get("usage") if isinstance(content, dict) else None
    return usage if isinstance(usage, dict) else {}


def build_steps(current_step: str | None, agno_run: Any | None, *, finished: bool) -> list[StepInfo]:
    """The five steps with their state. While running, Agno has no step results yet, so the state
    comes from `current_step`; once finished, it comes from Agno's stored step results."""
    results = {getattr(s, "step_name", None): s for s in (getattr(agno_run, "step_results", None) or [])}
    second_round = current_step == DEEPEN_STEP and not finished
    if current_step in (DEEPEN_STEP, COMPETITORS_STEP) and not finished:
        # M15 parallel competitors and M14's second round both happen inside Research (shown as running);
        # in the second round, fact-checking has already finished once
        current_step, results = "research", {}
    steps: list[StepInfo] = []
    reached_current = False
    for name in STEP_NAMES:
        result = results.get(name)
        if result is not None:
            usage = _usage(result.content)
            ok = bool(getattr(result, "success", True))
            steps.append(
                StepInfo(
                    name=name,
                    status="completed" if ok else "failed",
                    duration_ms=usage.get("duration_ms"),
                    input_tokens=usage.get("input_tokens") or 0,
                    output_tokens=usage.get("output_tokens") or 0,
                    error=None if ok else (getattr(result, "error", None) or "Step failed"),
                )
            )
        elif finished:
            steps.append(StepInfo(name=name, status="skipped"))
        elif name == current_step:
            reached_current = True
            steps.append(StepInfo(name=name, status="running"))
        else:
            steps.append(
                StepInfo(name=name, status="pending" if reached_current or current_step is None else "completed")
            )
    if second_round:
        steps[1] = StepInfo(name="validate", status="completed")
    return steps


def _flat_steps(results: list[Any]) -> list[Any]:
    """Step results including those nested in a Condition (M14's second round)."""
    flat: list[Any] = []
    for result in results:
        flat.append(result)
        flat.extend(_flat_steps(list(getattr(result, "steps", None) or [])))
    return flat


def _totals(agno_run: Any, created_at: datetime) -> RunTotals:
    results = _flat_steps(list(getattr(agno_run, "step_results", None) or []))
    usages = [_usage(getattr(s, "content", None)) for s in results]
    if created_at.tzinfo is None:  # SQLite returns naive datetimes
        created_at = created_at.replace(tzinfo=UTC)
    return RunTotals(
        input_tokens=sum(u.get("input_tokens") or 0 for u in usages),
        output_tokens=sum(u.get("output_tokens") or 0 for u in usages),
        total_tokens=sum(u.get("total_tokens") or 0 for u in usages),
        duration_ms=max(0, int((datetime.now(UTC) - created_at).total_seconds() * 1000)),
    )


def _research_result(agno_run: Any) -> ResearchStepResult | None:
    """The research behind the report, with every source page: after the second round when it ran (M14)."""
    steps = _flat_steps(list(getattr(agno_run, "step_results", None) or []))
    by_name = {getattr(s, "step_name", None): s for s in steps}
    deepened = by_name.get(DEEPEN_STEP)
    candidates = []
    if (
        deepened is not None
        and isinstance(deepened.content, dict)
        and isinstance(deepened.content.get("research"), dict)
    ):
        candidates.append(deepened.content["research"])
    research = by_name.get("research")
    if research is not None and isinstance(research.content, dict):
        candidates.append(research.content)
    for content in candidates:
        try:
            return ResearchStepResult.model_validate(content)
        except ValueError:
            continue
    return None


def report_sources(report: Report, research: ResearchStepResult | None) -> list[SourceCreate]:
    """The report's references in order [1], [2] …, with the excerpt we fact-checked against."""
    by_key = {url_key(s.url): s for s in (research.sources if research else [])}
    sources: list[SourceCreate] = []
    for ref in report.references:
        found = by_key.get(url_key(ref.url))
        sources.append(
            SourceCreate(
                url=ref.url,
                title=ref.title or (found.title if found else None),
                excerpt=found.excerpt if found else None,
                retrieved_by=found.retrieved_by if found else ref.retrieved_by,
            )
        )
    return sources


class ResearchService:
    def __init__(self, database: Database, workflow: Workflow, settings: Settings) -> None:
        self.database = database
        self.workflow = workflow
        self.settings = settings
        self._lock = asyncio.Lock()

    # --- progress (called by the workflow steps) -------------------------------

    async def progress(self, research_id: str, step: str) -> None:
        async with self.database.session() as session:
            await ResearchRunRepository(session).set_current_step(uuid.UUID(research_id), step)

    # --- commands ----------------------------------------------------------------

    async def start(
        self,
        raw_query: str,
        *,
        company: CompanyIn | None = None,
        competitors: list[CompetitorIn] | None = None,
        market: MarketIn | None = None,
    ) -> ResearchRunSummary:
        """Start a run. `company` / `competitors` come from the confirm step (M12); without them the
        Researcher identifies the company and picks competitors itself. With `market` (M13) the run is a
        market-entry report for that product and region."""
        info = classify_query(raw_query)
        website_url = (company.website if company else None) or info.website_url
        confirmed = [ConfirmedCompetitor(**c.model_dump()) for c in competitors or []]
        async with self._lock:
            await self._reconcile(after_restart=False)
            async with self.database.session() as session:
                repo = ResearchRunRepository(session)
                running = await repo.count_by_status(RunStatus.RUNNING)
                if running >= self.settings.max_concurrent_runs:
                    raise CapacityError(
                        f"{running} research run(s) already in progress (limit {self.settings.max_concurrent_runs}). "
                        "Try again when one finishes."
                    )
                run = await repo.create(
                    ResearchRunCreate(
                        query=info.query,
                        input_type=info.input_type,
                        website_url=None if market else website_url,
                        company_name=f"{market.product} · {market.region}"[:255]
                        if market
                        else (company.name if company else None),
                        mode=RunMode.MARKET if market else RunMode.COMPANY,
                        scope=market.model_dump() if market else None,
                    )
                )
                companies = CompanyRepository(session)
                if company is not None:
                    await companies.link_run(run.id, await companies.find_or_create(company.name, website_url))
                if confirmed:
                    await companies.add_competitors(run.id, confirmed)
            try:
                started = await self.workflow.arun(
                    input=run.query,
                    session_id=str(run.id),  # one Agno session per research run
                    additional_data={
                        "research_id": str(run.id),
                        "website_url": run.website_url,
                        "company": company.model_dump() if company else None,
                        "competitors": [c.model_dump() for c in confirmed],
                        "mode": "market" if market else "company",
                        "market": market.model_dump() if market else None,
                    },
                    background=True,
                )
            except Exception as exc:
                logger.exception("Could not start workflow for run %s", run.id)
                await self._finish_failed(run.id, f"Could not start the research workflow ({type(exc).__name__}).")
                raise AppError("Could not start the research. Please try again.", code="start_failed") from exc
            async with self.database.session() as session:
                run = await ResearchRunRepository(session).set_agno_run_id(run.id, started.run_id) or run
        logger.info("Started %s research run %s (%s: %s)", run.mode, run.id, run.input_type, run.query)
        return ResearchRunSummary.of(run)

    # --- queries -------------------------------------------------------------------

    async def list_runs(self, limit: int, offset: int) -> ResearchRunList:
        await self.reconcile_running()
        async with self.database.session() as session:
            runs, total = await ResearchRunRepository(session).list_recent(limit=limit, offset=offset)
        return ResearchRunList(items=[ResearchRunSummary.of(r) for r in runs], total=total)

    async def detail(self, run_id: uuid.UUID) -> ResearchRunDetail:
        await self.reconcile_running()
        run = await self._get(run_id)
        agno_run = await self._agno_run(run)
        finished = run.status != RunStatus.RUNNING
        return ResearchRunDetail(
            **ResearchRunSummary.of(run).model_dump(),
            website_url=run.website_url,
            error=run.error,
            agno_run_id=run.agno_run_id,
            current_step=run.current_step,
            totals=RunTotals(
                input_tokens=run.total_input_tokens,
                output_tokens=run.total_output_tokens,
                total_tokens=run.total_tokens,
                duration_ms=run.duration_ms,
            ),
            steps=build_steps(run.current_step, agno_run, finished=finished),
            has_report=run.report is not None,
        )

    async def report(self, run_id: uuid.UUID) -> Report:
        await self.reconcile_running()
        run = await self._get(run_id)
        if run.report is None:
            if run.status == RunStatus.RUNNING:
                raise ConflictError("The report is not ready yet. The research is still running.", "report_not_ready")
            raise ConflictError(f"This run has no report: {run.error or 'it failed'}", "report_not_ready")
        return Report.model_validate(run.report)

    # --- reconciliation ------------------------------------------------------------

    async def reconcile_running(self) -> None:
        async with self._lock:
            await self._reconcile(after_restart=False)

    async def reconcile_after_restart(self) -> None:
        """App startup: background tasks from before the restart are gone."""
        async with self._lock:
            await self._reconcile(after_restart=True)

    async def _reconcile(self, *, after_restart: bool) -> None:
        async with self.database.session() as session:
            running = await ResearchRunRepository(session).list_by_status(RunStatus.RUNNING)
        for run in running:
            try:
                await self._reconcile_one(run, after_restart=after_restart)
            except Exception:  # one bad run must not block the others (or the request)
                logger.exception("Could not reconcile research run %s", run.id)

    async def _reconcile_one(self, run: ResearchRun, *, after_restart: bool) -> None:
        agno_run = await self._agno_run(run)
        status = _status(getattr(agno_run, "status", None)) if agno_run is not None else ""
        if status in FINISHED_AGNO_STATUSES:
            await self._finalise(run, agno_run)
        elif after_restart:
            await self._finish_failed(run.id, RESTART_ERROR)
        elif run.agno_run_id is None and self._age_s(run) > START_GRACE_S:
            await self._finish_failed(run.id, "The research workflow never started.")

    async def _finalise(self, run: ResearchRun, agno_run: Any) -> None:
        outcome = outcome_from_run(agno_run)
        if _status(agno_run.status) == "CANCELLED" and outcome.report is None:
            outcome = outcome.model_copy(update={"error": "The run was cancelled."})
        research = _research_result(agno_run)
        report = outcome.report
        error = outcome.error
        if outcome.failed_step and error:
            error = f"{outcome.failed_step} step failed: {error}"
        company_name = report.meta.company_name if report else (research.name if research else None)
        async with self.database.session() as session:
            repo = ResearchRunRepository(session)
            current = await repo.get(run.id)
            if current is None or current.status != RunStatus.RUNNING:
                return  # already finalised
            await repo.finish(
                run.id,
                status=_OUTCOME_STATUS[outcome.outcome],
                totals=_totals(agno_run, run.created_at),
                report=report.model_dump(mode="json") if report else None,
                error=error,
                company_name=company_name,
            )
            if report is not None:
                await SourceRepository(session).add_many(run.id, report_sources(report, research))
            if report is not None and report.meta.mode == "company":  # a market is not a company
                companies = CompanyRepository(session)
                company_id = current.company_id or await companies.find_or_create(
                    report.company_overview.name, report.company_overview.website
                )
                await companies.link_run(run.id, company_id, researched=True)
        logger.info("Research run %s finished: %s", run.id, outcome.outcome)

    async def _finish_failed(self, run_id: uuid.UUID, error: str) -> None:
        async with self.database.session() as session:
            await ResearchRunRepository(session).finish(run_id, status=RunStatus.FAILED, error=error)
        logger.warning("Research run %s marked failed: %s", run_id, error)

    # --- helpers ---------------------------------------------------------------

    async def _get(self, run_id: uuid.UUID) -> ResearchRun:
        async with self.database.session() as session:
            run = await ResearchRunRepository(session).get(run_id)
        if run is None:
            raise NotFoundError(f"Research run {run_id} not found.", "run_not_found")
        return run

    async def _agno_run(self, run: ResearchRun) -> Any | None:
        if not run.agno_run_id:
            return None
        try:
            return await self.workflow.aget_run(run.agno_run_id, session_id=str(run.id))
        except Exception:
            logger.exception("Could not read Agno run %s", run.agno_run_id)
            return None

    @staticmethod
    def _age_s(run: ResearchRun) -> float:
        created = run.created_at if run.created_at.tzinfo else run.created_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created).total_seconds()
