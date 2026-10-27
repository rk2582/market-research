"""Builds the LLM for an agent. OpenAI only for now; adding a provider means changing only this file."""

from __future__ import annotations

import httpx
from agno.models.openai import OpenAIChat

from core.config import AgentKey, Settings

# OpenAI SDK retries 429/5xx with backoff. Agno's own agent retries stay off, to avoid double retries.
OPENAI_MAX_RETRIES = 2
OPENAI_TIMEOUT_S = 90.0


def build_model(settings: Settings, agent: AgentKey, *, http_client: httpx.AsyncClient | None = None) -> OpenAIChat:
    """The model for one agent: per-agent override if set, else DEFAULT_MODEL.

    `http_client` lets tests replace OpenAI with a fake HTTP server.
    The API key may be missing here (e.g. in tests); calls then fail with OpenAI's auth error.
    """
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return OpenAIChat(
        id=settings.model_for(agent),
        api_key=api_key,
        max_retries=OPENAI_MAX_RETRIES,
        timeout=OPENAI_TIMEOUT_S,
        http_client=http_client,
    )
