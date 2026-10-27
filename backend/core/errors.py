"""Domain errors and their HTTP mapping.

Services raise these errors; they never import FastAPI. The handlers below turn them into
responses shaped as {"detail": "...", "code": "..."}.
Validation errors (422) keep FastAPI's standard format.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = 500
    default_code: str = "internal_error"

    def __init__(self, detail: str, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code or self.default_code


class NotFoundError(AppError):
    status_code = 404
    default_code = "not_found"


class ConflictError(AppError):
    status_code = 409
    default_code = "conflict"


class CapacityError(AppError):
    status_code = 429
    default_code = "capacity_reached"


def error_body(detail: str, code: str) -> dict[str, str]:
    return {"detail": detail, "code": code}


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.detail, exc.code))


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Full details go to the log only; the client gets a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=error_body("Internal server error", "internal_error"))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
