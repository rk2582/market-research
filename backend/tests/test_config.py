from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings, get_settings
from tests.conftest import make_settings


def test_defaults(settings: Settings):
    assert settings.default_model == "gpt-4.1-mini"
    assert settings.max_concurrent_runs == 2
    assert settings.cors_origins == ["http://localhost:3001"]
    assert settings.agno_db_schema == "agno"
    assert settings.agno_telemetry is False
    assert settings.tracing_enabled is False


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost:5432/db",  # sync driver
        "postgres://u:p@localhost/db",
        "mysql+aiomysql://u:p@localhost/db",
    ],
)
def test_database_url_must_use_async_driver(tmp_path: Path, url: str):
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        make_settings(tmp_path, database_url=url)


def test_agno_db_url_uses_sync_psycopg_driver_for_postgres(tmp_path: Path):
    s = make_settings(tmp_path, database_url="postgresql+asyncpg://postgres:pw@localhost:5432/market360")
    assert s.agno_db_url == "postgresql+psycopg://postgres:pw@localhost:5432/market360"


def test_agno_db_url_for_sqlite(tmp_path: Path):
    s = make_settings(tmp_path, database_url="sqlite+aiosqlite:////tmp/x.db")
    assert s.agno_db_url == "sqlite:////tmp/x-agno.db"  # own file: no lock clashes with our tables


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3001, http://127.0.0.1:3001")
    assert make_settings(tmp_path).cors_origins == ["http://localhost:3001", "http://127.0.0.1:3001"]


def test_cors_wildcard_rejected(tmp_path: Path):
    with pytest.raises(ValidationError, match="explicit origins"):
        make_settings(tmp_path, cors_origins="*")


def test_empty_env_values_are_treated_as_not_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MODEL_RESEARCHER", "")
    assert make_settings(tmp_path).model_researcher is None


def test_model_for_uses_override_then_default(tmp_path: Path):
    s = make_settings(tmp_path, default_model="gpt-4.1-mini", model_analyst="gpt-4.1")
    assert s.model_for("analyst") == "gpt-4.1"
    assert s.model_for("researcher") == "gpt-4.1-mini"


@pytest.mark.parametrize(("field", "value"), [("max_concurrent_runs", 0), ("log_level", "LOUD")])
def test_invalid_values_rejected(tmp_path: Path, field: str, value: object):
    with pytest.raises(ValidationError):
        make_settings(tmp_path, **{field: value})


def test_secrets_are_hidden_in_repr(tmp_path: Path):
    s = make_settings(tmp_path, openai_api_key="sk-secret-123", tavily_api_key="tvly-secret-456")
    assert "sk-secret-123" not in repr(s)
    assert "tvly-secret-456" not in repr(s)
    assert s.openai_api_key is not None and s.openai_api_key.get_secret_value() == "sk-secret-123"


def test_get_settings_reads_environment_and_is_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'env.db'}")
    get_settings.cache_clear()
    try:
        first = get_settings()
        assert first.database_url.endswith("env.db")
        assert get_settings() is first
    finally:
        get_settings.cache_clear()


def test_agno_schema_cannot_be_public(tmp_path: Path):
    with pytest.raises(ValidationError, match="must not be 'public'"):
        make_settings(tmp_path, agno_db_schema="public")
