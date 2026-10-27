"""Application settings, read from environment variables and backend/.env.

All configuration lives here so it is validated once, at startup.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]

_ASYNC_POSTGRES = "postgresql+asyncpg://"
_ASYNC_SQLITE = "sqlite+aiosqlite://"  # used by tests only

AgentKey = Literal[
    "identifier",
    "researcher",
    "fact_checker",
    "analyst",
    "strategist",
    "report_writer",
    "market_researcher",
    "market_analyst",
    "market_strategist",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # "MODEL_RESEARCHER=" in .env means "not set"
        extra="ignore",
    )

    app_name: str = "Delphi Market360"
    app_version: str = "0.1.0"

    # --- Database ---
    database_url: str = Field(description="Async SQLAlchemy URL for product tables")
    agno_db_schema: str = Field(default="agno", pattern=r"^[a-z_][a-z0-9_]*$")

    # --- OpenAI (required from Milestone 5, when agents are built) ---
    openai_api_key: SecretStr | None = None
    default_model: str = "gpt-4.1-mini"
    model_identifier: str | None = None
    model_researcher: str | None = None
    model_fact_checker: str | None = None
    model_analyst: str | None = None
    model_strategist: str | None = None
    model_report_writer: str | None = None

    # --- Tavily (required from Milestone 5) ---
    tavily_api_key: SecretStr | None = None

    # --- App behaviour ---
    max_concurrent_runs: int = Field(default=2, ge=1, le=10)
    # M14: one targeted research round after fact-checking when code finds gaps (about +8 Tavily credits).
    research_more_enabled: bool = True
    # M15: profile competitors / market players with separate researchers running at the same time.
    parallel_research_enabled: bool = True
    tracing_enabled: bool = False
    agno_telemetry: bool = False  # Agno sends usage telemetry by default; off for a local-only POC
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3001"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        if not value.startswith((_ASYNC_POSTGRES, _ASYNC_SQLITE)):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql+asyncpg://' "
                "(e.g. postgresql+asyncpg://postgres:password@localhost:5432/market360)"
            )
        return value

    @field_validator("agno_db_schema")
    @classmethod
    def _keep_agno_out_of_public(cls, value: str) -> str:
        if value == "public":
            raise ValueError("AGNO_DB_SCHEMA must not be 'public' — our own tables live there")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string from .env, e.g. 'http://a:3001,http://b:3001'."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins, not '*'")
        return value

    @property
    def agno_db_url(self) -> str:
        """Sync URL for Agno's own storage (Agno's PostgresDb/SqliteDb use sync drivers)."""
        if self.database_url.startswith(_ASYNC_POSTGRES):
            return "postgresql+psycopg://" + self.database_url.removeprefix(_ASYNC_POSTGRES)
        # SQLite (tests): a separate file next to ours, like Agno's separate schema on PostgreSQL.
        # Sharing one SQLite file let Agno's writes and ours lock each other ("database is locked").
        path = self.database_url.removeprefix(_ASYNC_SQLITE)
        stem, dot, ext = path.rpartition(".")
        return "sqlite://" + (f"{stem}-agno.{ext}" if dot and "/" not in ext else f"{path}-agno")

    def model_for(self, agent: AgentKey) -> str:
        """Model id for one agent: its override if set, otherwise DEFAULT_MODEL (market_x uses x's override)."""
        # Market-entry agents (M13) use the same model as their company counterpart.
        override: str | None = getattr(self, f"model_{agent.removeprefix('market_')}")
        return override or self.default_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env / .env
