#!/usr/bin/env python3
"""Plan complementary Instagram profile search from the frozen discovery intents.

Search/Popular keep the validated four-intent strings, including any market
token. Profile search is a different index that matches names and bios, not
captions. It uses the two category lanes with the plan's declared
`market_tokens` stripped, plus one compact local variant when that variant can
be derived from the frozen local lanes.

Measured 2026-09-09 on one local-market product: the variant built from the
workflow lane's function noun plus the category surface returned about seven
comparable local products in ten rows and barely overlapped the raw category
query. Raw workflow strings and verb-head composes failed or returned
unrelated greeting accounts. Workflow lanes stay off this route unless folded
into that two-token variant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CATEGORY_LANES = ("local_category", "english_category")
STOPWORDS = {
    "a",
    "as",
    "às",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "no",
    "o",
    "of",
    "para",
    "the",
}
VERB_SUFFIXES = ("ndo", "ing")
VARIANT_ID = "local_category_variant"
SCHEMA_VERSION = "competitor-profile-discovery-plan.v1"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


# The market words the frozen plan declared; set once per plan by build_plan.
MARKET_TOKENS: set[str] = set()


CJK_CHAR = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def strip_market_tokens(query: str) -> str:
    """Drop declared market words: whole words, or the declared part of an unspaced CJK term."""
    kept = []
    for token in query.split():
        if token.casefold() in MARKET_TOKENS:
            continue
        if CJK_CHAR.search(token):
            for market in MARKET_TOKENS:
                if CJK_CHAR.search(market):
                    token = token.replace(market, "")
            if not token:
                continue
        kept.append(token)
    return " ".join(kept)


def first_content_token(query: str) -> str:
    for token in query.split():
        folded = token.casefold()
        if folded in STOPWORDS or folded in MARKET_TOKENS:
            continue
        return token
    return ""


def looks_like_verb(token: str) -> bool:
    return token.casefold().endswith(VERB_SUFFIXES)


def append_call(
    calls: list[dict[str, str]],
    seen: set[str],
    intent_id: str,
    query: str,
) -> None:
    stripped = strip_market_tokens(query.strip())
    if len(stripped.split()) < 2:
        return
    key = stripped.casefold()
    if key in seen:
        return
    seen.add(key)
    calls.append({
        "intent_id": intent_id,
        "query": stripped,
        "envelope": f"profile-discovery-{intent_id}.json",
    })


def local_variant_query(intents: list[dict[str, Any]]) -> str | None:
    by_id: dict[str, dict[str, Any]] = {}
    for intent in intents:
        if isinstance(intent, dict) and isinstance(intent.get("intent_id"), str):
            by_id[intent["intent_id"]] = intent
    category = by_id.get("local_category") or {}
    workflow = by_id.get("local_workflow") or {}
    category_query = category.get("search_query")
    workflow_query = workflow.get("search_query")
    if not isinstance(category_query, str) or not isinstance(workflow_query, str):
        return None
    category_tokens = strip_market_tokens(category_query.strip()).split()
    if len(category_tokens) < 2:
        return None
    # A three-plus-term series tail (remix / part) is not a category; querying it retrieves remix pages.
    if len(category_tokens) >= 3:
        return None
    head = first_content_token(strip_market_tokens(workflow_query.strip()))
    if not head or looks_like_verb(head):
        return None
    return f"{head} {category_tokens[-1]}"


def nested_form_query(query: str) -> str | None:
    tokens = strip_market_tokens(query.strip()).split()
    if len(tokens) < 3:
        return None
    return " ".join(tokens[:2])


def plan_calls(intents: list[dict[str, Any]]) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    seen: set[str] = set()
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        intent_id = intent.get("intent_id")
        query = intent.get("search_query")
        if intent_id not in CATEGORY_LANES:
            continue
        if not isinstance(query, str) or not query.strip():
            continue
        append_call(calls, seen, str(intent_id), query)
        if intent_id == "local_category":
            nested = nested_form_query(query)
            if nested:
                append_call(calls, seen, f"{intent_id}_nested", nested)
    variant = local_variant_query(intents)
    if variant:
        append_call(calls, seen, VARIANT_ID, variant)
    return calls


def build_plan(intents_doc: dict[str, Any]) -> dict[str, Any]:
    intents = intents_doc.get("intents")
    if not isinstance(intents, list):
        raise ValueError("discovery intents must include an intents array")
    MARKET_TOKENS.clear()
    MARKET_TOKENS.update(str(token).strip().casefold() for token in intents_doc.get("market_tokens") or []
                         if isinstance(token, str) and token.strip())
    return {
        "schema_version": SCHEMA_VERSION,
        "calls": plan_calls(intents),
    }


def plan_table(plan: dict) -> str:
    """The planned queries as numbered lines: what the caller sends, in plan order.

    The index is load-bearing — each Envelope is placed at `--at [i]` of that same 0-based
    plan order — so it is printed rather than counted off a re-read of the file. Without
    this the only way to learn the queries is to `cat` the plan back, which is a whole
    round trip for something the command that wrote it already had.
    """
    lines = []
    for index, call in enumerate(plan.get("calls") or []):
        intent = call.get("intent_id") or "?"
        lines.append(f"{index}. {call.get('query')}  [{intent} -> {call.get('envelope')}]")
    return "\n".join(lines) if lines else "(no profile-search lanes planned)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intents", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--print", dest="print_table", action="store_true",
                        help="also print the planned queries with their 0-based --at index")
    args = parser.parse_args(argv)
    plan = build_plan(load(args.intents))
    args.output.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.print_table:
        print(plan_table(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
