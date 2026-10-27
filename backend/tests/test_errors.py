import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from core.errors import AppError, CapacityError, ConflictError, NotFoundError, register_exception_handlers


@pytest.fixture
def error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def not_found():
        raise NotFoundError("Research run not found", code="run_not_found")

    @app.get("/conflict")
    async def conflict():
        raise ConflictError("Report is not ready yet", code="report_not_ready")

    @app.get("/capacity")
    async def capacity():
        raise CapacityError("Too many research runs in progress")

    @app.get("/app-error")
    async def app_error():
        raise AppError("Something we anticipated")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    class Body(BaseModel):
        query: str

    @app.post("/validate")
    async def validate(body: Body):
        return body

    return app


@pytest.fixture
async def error_client(error_app: FastAPI):
    transport = httpx.ASGITransport(app=error_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.parametrize(
    ("path", "status", "body"),
    [
        ("/not-found", 404, {"detail": "Research run not found", "code": "run_not_found"}),
        ("/conflict", 409, {"detail": "Report is not ready yet", "code": "report_not_ready"}),
        ("/capacity", 429, {"detail": "Too many research runs in progress", "code": "capacity_reached"}),
        ("/app-error", 500, {"detail": "Something we anticipated", "code": "internal_error"}),
    ],
)
async def test_domain_errors_map_to_status_and_body(error_client: httpx.AsyncClient, path, status, body):
    r = await error_client.get(path)
    assert r.status_code == status
    assert r.json() == body


async def test_unexpected_error_returns_generic_500_without_leaking_details(
    error_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
):
    r = await error_client.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error", "code": "internal_error"}
    assert "secret internal detail" not in r.text
    assert "secret internal detail" in caplog.text  # still logged for debugging


async def test_validation_errors_keep_fastapi_format(error_client: httpx.AsyncClient):
    r = await error_client.post("/validate", json={})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "query"]


async def test_handlers_are_active_inside_the_agentos_app(app: FastAPI, client: httpx.AsyncClient):
    """AgentOS wraps our base app; our handlers must still apply to routes added to it."""

    @app.get("/api/v1/_test-not-found")
    async def _raise():
        raise NotFoundError("nope")

    r = await client.get("/api/v1/_test-not-found")
    assert r.status_code == 404
    assert r.json() == {"detail": "nope", "code": "not_found"}
