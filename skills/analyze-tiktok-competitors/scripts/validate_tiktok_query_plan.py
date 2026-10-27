#!/usr/bin/env python3
"""Validate the bounded, natural TikTok Trend query plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


CJK_CHAR = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def search_query_term_count_ok(query: str) -> bool:
    """English needs 2-5 whitespace terms; CJK may be one 2-20 character phrase."""
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if 2 <= len(terms) <= 5:
        return True
    if len(terms) != 1:
        return False
    cjk = CJK_CHAR.findall(terms[0])
    return 2 <= len(cjk) <= 20


def validate(plan: dict[str, Any]) -> None:
    if set(plan) != {"schema_version", "request_id", "intents"}:
        raise ValueError("plan must contain only schema_version, request_id and intents")
    if plan.get("schema_version") != "tiktok-trend-query-plan.v1":
        raise ValueError("schema_version must be tiktok-trend-query-plan.v1")
    if not isinstance(plan.get("request_id"), str) or not plan["request_id"].strip():
        raise ValueError("request_id must be non-empty")
    intents = plan.get("intents")
    if not isinstance(intents, list) or not 1 <= len(intents) <= 2:
        raise ValueError("intents must contain one or two entries")
    seen: set[str] = set()
    for index, intent in enumerate(intents):
        if not isinstance(intent, dict) or set(intent) != {"intent_id", "search_query"}:
            raise ValueError(f"intents[{index}] must contain only intent_id and search_query")
        intent_id = intent.get("intent_id")
        query = intent.get("search_query")
        if not isinstance(intent_id, str) or not 1 <= len(intent_id.strip()) <= 64:
            raise ValueError(f"intents[{index}].intent_id is invalid")
        if intent_id in seen:
            raise ValueError(f"duplicate intent_id: {intent_id}")
        seen.add(intent_id)
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 80:
            raise ValueError(f"intents[{index}].search_query is invalid")
        if not search_query_term_count_ok(query):
            raise ValueError(
                f"intents[{index}].search_query must contain two to five terms, "
                "or one 2-20 character CJK phrase without spaces"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        value = load(args.plan)
        validate(value)
        print(json.dumps({"valid": True, "intents": len(value["intents"])}))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
