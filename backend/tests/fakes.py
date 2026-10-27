"""Fakes for OpenAI and Tavily, so agent tests run offline, for free, with predictable answers.

FakeOpenAI replaces OpenAI at the HTTP level: Agno's real code runs (tool calls, structured
output parsing, metrics); only the network is fake. It also records every request Agno sends.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from schemas.findings import ResearchFindings


def tool_call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"name": name, "arguments": arguments}


class FakeOpenAI:
    """Answers chat-completion requests from a script.

    `script` is either a list (answers in order) or a dict keyed by the output schema name the agent
    asks for (e.g. "ResearchFindings", "ValidationResult"), each a list of answers in order. The dict
    form works when agents run in parallel (fact-check batches).

    Each answer is either:
    - a list of tool calls (from `tool_call(...)`) → the model asks for those tools, or
    - a dict / BaseModel / str → the model's final answer (JSON-encoded if not a str), or
    - an int → that HTTP error status (e.g. 500), or
    - a function(request_body) returning one of the above.
    """

    def __init__(
        self, script: list[Any] | dict[str, list[Any]], *, prompt_tokens: int = 100, completion_tokens: int = 50
    ) -> None:
        self.script = {k: list(v) for k, v in script.items()} if isinstance(script, dict) else list(script)
        self.requests: list[dict[str, Any]] = []
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    @staticmethod
    def schema_name(body: dict[str, Any]) -> str:
        return ((body.get("response_format") or {}).get("json_schema") or {}).get("name", "")

    def requests_for(self, schema: str) -> list[dict[str, Any]]:
        return [r for r in self.requests if self.schema_name(r) == schema]

    def _next(self, body: dict[str, Any]) -> Any:
        queue = self.script.get(self.schema_name(body), []) if isinstance(self.script, dict) else self.script
        return queue.pop(0) if queue else None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        step = self._next(body)
        if step is None:
            return httpx.Response(500, json={"error": {"message": "FakeOpenAI script exhausted"}})
        if callable(step):
            step = step(body)
        if isinstance(step, int):
            return httpx.Response(step, json={"error": {"message": f"fake HTTP {step}"}})
        usage = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
        }
        if isinstance(step, list):
            message: dict[str, Any] = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{len(self.requests)}_{i}",
                        "type": "function",
                        "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                    }
                    for i, call in enumerate(step)
                ],
            }
            finish_reason = "tool_calls"
        else:
            if hasattr(step, "model_dump_json"):
                content = step.model_dump_json()
            elif isinstance(step, str):
                content = step
            else:
                content = json.dumps(step)
            message = {"role": "assistant", "content": content}
            finish_reason = "stop"
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model", "fake"),
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                "usage": usage,
            },
        )


class FakeTavily:
    """Async stand-in for tavily.AsyncTavilyClient. Records calls; returns canned results."""

    def __init__(
        self,
        search_results: dict[str, list[dict[str, Any]]] | None = None,
        pages: dict[str, str] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.search_results = search_results or {}
        self.pages = pages or {}
        self.fail = fail
        self.calls: list[tuple[str, Any]] = []

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search", query))
        if self.fail:
            raise RuntimeError("Tavily is down")
        return {"query": query, "results": self.search_results.get(query, [])}

    async def extract(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("extract", urls))
        if self.fail:
            raise RuntimeError("Tavily is down")
        results = [{"url": u, "raw_content": self.pages[u]} for u in urls if u in self.pages]
        return {"results": results, "failed_results": [u for u in urls if u not in self.pages]}


def sample_findings(source_url: str = "https://www.notion.com") -> ResearchFindings:
    """A small but complete, valid Researcher answer."""

    def s(text: str, kind: str = "fact") -> dict[str, Any]:
        return {"text": text, "source_urls": [source_url], "kind": kind}

    competitor = {
        "name": "Coda",
        "website": "https://coda.io",
        "relation": "direct",
        "description": s("Coda is an all-in-one doc for teams."),
        "offerings": [s("Docs with tables and automations.")],
        "pricing": None,
        "target_segments": [s("Teams and startups.")],
        "positioning": None,
    }
    return ResearchFindings.model_validate(
        {
            "company": {
                "name": "Notion",
                "website": "https://www.notion.com",
                "identity_note": s("Notion Labs Inc., maker of the Notion workspace app."),
                "description": s("Notion is a connected workspace for docs, wikis and projects."),
                "industry": s("Productivity software (SaaS)."),
                "products_services": [s("Notion workspace"), s("Notion AI")],
                "customer_segments": [s("Teams and enterprises.")],
                "geographic_presence": [s("Global.")],
                "business_model": s("Freemium subscriptions."),
                "pricing": None,
                "funding": None,
                "recent_developments": [],
                "positioning_usp": s("All-in-one flexible workspace.", "interpretation"),
            },
            "competitors": [competitor, {**competitor, "name": "Confluence", "website": "https://confluence.com"}],
            "competitor_shortfall_reason": "Only two clear direct competitors found in sources.",
            "industry_context": [s("Collaboration software is a crowded market.", "interpretation")],
        }
    )


# ---------------------------------------------------------------------------
# Answers for the later agents, built from the claim ids the code will assign
# ---------------------------------------------------------------------------


def validation_for(claim_ids: list[str], verdicts: dict[str, str] | None = None) -> dict[str, Any]:
    """Fact-Checker answer: 'supported' for every id unless overridden."""
    verdicts = verdicts or {}
    return {
        "verdicts": [
            {
                "claim_id": cid,
                "verdict": verdicts.get(cid, "supported"),
                "confidence": "high",
                "reason": f"Excerpt states it ({cid}).",
                "supporting_urls": [],
                "source_year": None,
            }
            for cid in claim_ids
        ]
    }


def analysis_for(company: str, competitor: str, claim_ids: list[str]) -> dict[str, Any]:
    """Analyst answer citing the given claim ids (one bad id included on purpose)."""
    first, second = claim_ids[0], claim_ids[-1]

    def insight(text: str, ids: list[str], kind: str = "fact") -> dict[str, Any]:
        return {"text": text, "kind": kind, "evidence_claim_ids": ids}

    return {
        "comparison": [
            {
                "dimension": "Core offering",
                "cells": [
                    {"company": company, "value": "Connected workspace", "claim_ids": [first]},
                    {"company": competitor, "value": "Docs for teams", "claim_ids": [second]},
                ],
            }
        ],
        "swot": {
            "strengths": [insight("Broad product.", [first])],
            "weaknesses": [insight("Pricing unclear.", [second], "interpretation")],
            "opportunities": [insight("AI features.", [first], "prediction")],
            "threats": [insight("Crowded market.", [second]), insight("Invented threat.", ["C999"])],
        },
        "trends": [insight("Collaboration market grows.", [second], "interpretation")],
        "opportunities": [insight("Enterprise upsell.", [first], "interpretation")],
        "risks": [insight("Strong rivals.", [first, second])],
        "data_gaps": ["Market share", " "],
        "key_figures": [],
    }


def strategy_for(insight_ids: list[str]) -> dict[str, Any]:
    def rec(priority: int, title: str, ids: list[str]) -> dict[str, Any]:
        return {
            "priority": priority,
            "title": title,
            "rationale": "Because the evidence says so.",
            "evidence_ids": ids,
            "impact": "high",
            "next_steps": ["Do the first thing", "Do the second thing"],
            "risks_tradeoffs": ["It costs money"],
        }

    return {
        "recommendations": [
            rec(3, "Third", [insight_ids[-1]]),
            rec(1, "First", [insight_ids[0], "C1"]),
            rec(2, "Second", [insight_ids[1]]),
            rec(4, "No evidence", ["F999"]),
        ]
    }


def narrative_for(claim_id: str) -> dict[str, Any]:
    return {
        "executive_summary": f"Notion is a connected workspace [{claim_id}]. Unknown ref [C999].",
        "industry_overview": f"The market is crowded [{claim_id}].",
        "actionable_next_steps": ["Ship AI features", "  ", "Target enterprises"],
    }


def prompt_payload(body: dict[str, Any]) -> dict[str, Any]:
    """The JSON our prompt builders put after the first blank line of the user message."""
    user = [m for m in body["messages"] if m.get("role") == "user"][-1]["content"]
    text = user if isinstance(user, str) else " ".join(part.get("text", "") for part in user)
    return json.loads(text.split("\n\n", 1)[1])


def fact_checker_echo(verdicts: dict[str, str] | None = None) -> Any:
    """A Fact-Checker answer that verdicts exactly the claim ids in the request (works for parallel batches)."""

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        ids = [c["id"] for c in prompt_payload(body)["claims"]]
        return validation_for(ids, verdicts)

    return answer
