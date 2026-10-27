"""AgentSpec: everything that defines an agent, kept in code so prompt changes are reviewed in git.

Bump `version` whenever instructions, schema or tools change; the version is stored with every
report, so you can always tell which prompt produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from core.config import AgentKey


@dataclass(frozen=True)
class AgentSpec:
    key: AgentKey  # also the agent id in AgentOS
    version: str  # e.g. "researcher@1"
    name: str
    role: str
    instructions: tuple[str, ...]
    output_schema: type[BaseModel]
    tools: tuple[str, ...] = ()
    tool_call_limit: int | None = None
    timeout_s: float = 120.0
