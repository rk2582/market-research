"""GET /api/v1/health — is the API up and can it reach the database?

AgentOS also has its own GET /health, which only says the process is running.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.session import Database, get_database

router = APIRouter(prefix="/api/v1", tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
)
async def health(database: Database = Depends(get_database)) -> HealthResponse | JSONResponse:
    if await database.ping():
        return HealthResponse(status="ok", database="ok")
    body = HealthResponse(status="degraded", database="error")
    return JSONResponse(status_code=503, content=body.model_dump())
