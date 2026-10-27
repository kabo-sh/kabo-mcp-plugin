#!/usr/bin/env python3
"""Validate the bounded, natural TikTok Trend query plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


# Scripts written without spaces between words (Han, Kana, Thai, Lao, Khmer, Myanmar). A natural
# query in them is one unbroken run, so its length is counted in characters instead of words.
UNSPACED_SCRIPT = re.compile(
    "[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u31f0-\u31ff"
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f\U00020000-\U0002fa1f]"
)
UNSPACED_MIN_CHARACTERS = 2
UNSPACED_MAX_CHARACTERS = 20


def unspaced_length(query: str) -> int | None:
    """Non-space character count when the query uses an unspaced script, otherwise None."""
    if not UNSPACED_SCRIPT.search(query):
        return None
    return len(re.sub(r"\s+", "", query))


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


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
        # A query that uses an unspaced script passes on its character count; a query that already
        # passed as spaced words (mixed scripts included) keeps passing.
        characters = unspaced_length(query)
        if characters is not None and UNSPACED_MIN_CHARACTERS <= characters <= UNSPACED_MAX_CHARACTERS:
            continue
        terms = [term for term in re.split(r"\s+", query.strip()) if term]
        if not 2 <= len(terms) <= 5:
            if characters is not None:
                raise ValueError(
                    f"intents[{index}].search_query must contain {UNSPACED_MIN_CHARACTERS} to "
                    f"{UNSPACED_MAX_CHARACTERS} characters in an unspaced script, or two to five terms"
                )
            raise ValueError(f"intents[{index}].search_query must contain two to five terms")


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
