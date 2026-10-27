"""/api/v1/research — start a research run, follow its progress, fetch the report.

Thin layer: validation and HTTP shapes here, all logic in services/research_service.py.
Errors are {"detail", "code"}: 404 run_not_found, 409 report_not_ready, 429 capacity_reached,
502 identify_failed (the confirm step could not run; the client can start without confirming).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from schemas.api import (
    IdentifyRequest,
    IdentifyResponse,
    ResearchRequest,
    ResearchRunDetail,
    ResearchRunList,
    ResearchRunSummary,
)
from schemas.report import Report
from services.identify_service import IdentifyService
from services.research_service import ResearchService

router = APIRouter(prefix="/api/v1/research", tags=["Research"])

_ERRORS = {
    404: {"description": "Run not found (code: run_not_found)"},
}


def get_research_service(request: Request) -> ResearchService:
    return request.app.state.research_service


def get_identify_service(request: Request) -> IdentifyService:
    return request.app.state.identify_service


@router.post(
    "/identify",
    response_model=IdentifyResponse,
    responses={502: {"description": "The quick check failed (code: identify_failed)"}},
    summary="Confirm step: which company (or market) is meant, and suggested competitors",
)
async def identify(body: IdentifyRequest, service: IdentifyService = Depends(get_identify_service)) -> IdentifyResponse:
    """Takes a few seconds (up to 3 web searches). Nothing is stored; pass the confirmed company and
    competitors to `POST /api/v1/research`."""
    return await service.identify(body.query)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ResearchRunSummary,
    responses={429: {"description": "Too many runs in progress (code: capacity_reached)"}},
    summary="Start a research run",
)
async def start_research(
    body: ResearchRequest, service: ResearchService = Depends(get_research_service)
) -> ResearchRunSummary:
    """Starts the five-step workflow in the background and returns at once. Poll the run for progress.
    With `company` and `competitors` (from the confirm step) the research uses exactly those.
    With `mode: "market"` and `market` it writes a market-entry report for that product and region."""
    return await service.start(body.query, company=body.company, competitors=body.competitors, market=body.market)


@router.get("", response_model=ResearchRunList, summary="List research runs (newest first)")
async def list_research(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: ResearchService = Depends(get_research_service),
) -> ResearchRunList:
    return await service.list_runs(limit=limit, offset=offset)


@router.get("/{run_id}", response_model=ResearchRunDetail, responses=_ERRORS, summary="Run status and steps")
async def get_research(
    run_id: uuid.UUID, service: ResearchService = Depends(get_research_service)
) -> ResearchRunDetail:
    """Poll this every few seconds until status is succeeded, partial or failed."""
    return await service.detail(run_id)


@router.get(
    "/{run_id}/report",
    response_model=Report,
    responses={**_ERRORS, 409: {"description": "No report yet, or the run failed (code: report_not_ready)"}},
    summary="The finished report",
)
async def get_report(run_id: uuid.UUID, service: ResearchService = Depends(get_research_service)) -> Report:
    return await service.report(run_id)
