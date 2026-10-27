"""Every agent's output schema must be accepted by OpenAI's STRICT structured outputs.

These rules were learned the hard way (M5 live run: OpenAI returned 400 "$ref cannot have keywords
{'description'}"). The check uses the exact schema Agno sends, so it catches problems for free,
before any paid call.
"""

from __future__ import annotations

from typing import Any

import pytest
from agno.utils.models.schema_utils import get_response_schema_for_provider

from registry.factory import ALL_SPECS

UNSUPPORTED_KEYWORDS = ("default", "format", "minItems", "maxItems", "minLength", "maxLength", "pattern")


def strict_schema_problems(schema: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        if "$ref" in node and len(node) > 1:
            problems.append(f"{path}: $ref combined with {sorted(k for k in node if k != '$ref')}")
        if "anyOf" in node and any(isinstance(o, dict) and "$ref" in o for o in node["anyOf"]):
            extra = sorted(k for k in node if k not in ("anyOf", "title"))
            if extra:
                problems.append(f"{path}: anyOf with $ref combined with {extra}")
        if "properties" in node:
            props, required = set(node["properties"]), set(node.get("required", []))
            if props != required:
                problems.append(f"{path}: optional fields {sorted(props - required)} (strict needs all required)")
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: additionalProperties must be false")
        for keyword in UNSUPPORTED_KEYWORDS:
            if keyword in node:
                problems.append(f"{path}: unsupported keyword {keyword!r}")
        for key, value in node.items():
            walk(value, f"{path}.{key}")

    walk(schema, "$")
    return problems


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
def test_output_schema_is_openai_strict_compatible(spec):
    schema = get_response_schema_for_provider(spec.output_schema, "openai")
    assert strict_schema_problems(schema) == []


def test_checker_catches_the_m5_live_error():
    bad = {"properties": {"x": {"$ref": "#/$defs/A", "description": "d"}}, "required": ["x"]}
    bad["additionalProperties"] = False
    assert strict_schema_problems(bad) == ["$.properties.x: $ref combined with ['description']"]


def test_checker_catches_other_strict_violations():
    bad = {
        "properties": {
            "a": {"type": "string", "format": "uri", "default": "x"},
            "b": {"anyOf": [{"$ref": "#/$defs/A"}, {"type": "null"}], "description": "d"},
        },
        "required": ["a"],
    }
    problems = strict_schema_problems(bad)
    assert any("optional fields ['b']" in p for p in problems)
    assert any("additionalProperties" in p for p in problems)
    assert any("'format'" in p for p in problems) and any("'default'" in p for p in problems)
    assert any("anyOf with $ref" in p for p in problems)
