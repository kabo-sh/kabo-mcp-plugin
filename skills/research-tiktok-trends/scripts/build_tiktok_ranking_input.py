#!/usr/bin/env python3
"""Select a bounded TikTok shortlist from semantic fit and absolute public heat."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import sys
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from trend_gate_contract import (
    TIKTOK_LOCALE_FIT_FLOOR,
    TIKTOK_TOPIC_RELEVANCE_FLOOR,
    semantic_scores,
    signature_content_ids,
    validate_complete,
)
import allocate_signature_content as allocation


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def percentiles(rows: list[dict[str, Any]]) -> dict[str, float]:
    values = sorted({float((row.get("metrics") or {}).get("views")) for row in rows if isinstance((row.get("metrics") or {}).get("views"), (int, float))})
    if not values:
        return {str(row["content_key"]): 0.0 for row in rows}
    denominator = max(len(values) - 1, 1)
    by_value = {value: index / denominator * 100 for index, value in enumerate(values)}
    return {
        str(row["content_key"]): by_value.get(float((row.get("metrics") or {}).get("views") or 0), 0.0)
        for row in rows
    }


def signature_shortlist(request: dict[str, Any], gate: dict[str, Any], eligible: list[tuple[float, float, float, dict[str, Any]]],
                        limit: int) -> tuple[list[tuple[float, float, float, dict[str, Any]]], dict[str, str | None], dict[str, Any]]:
    """带画像时按主打内容预分配 shortlist 的名额，与 rank 末尾的最终分配用同一个名额函数。

    这里还没有作者基线，候选按 pre_score（语义分与热度分位的加权）排；同作者只留 1 条，
    比不带画像时的 2 条更严：一个作者占两个名额，另一个主打内容就少一个代表。
    """
    entries = allocation.signature_entries(request)
    if not entries:
        raise ValueError("--signature-content needs creator_profile.signature_content in the Request")
    matched = signature_content_ids(gate)
    # 没有候选的 Gate 没有行可带这一列，照常给空 shortlist；有行却没有这一列才是没按画像打分。
    if not matched and gate.get("items"):
        raise ValueError("--signature-content needs a Gate scored with the signature_content column")
    accepted = allocation.accepted_languages(request)
    rows = [
        {"key": str(row["content_key"]), "class": matched.get(str(row["content_key"])),
         "author": str((row.get("author") or {}).get("handle") or "").strip().lstrip("@").casefold(),
         "sound": allocation.sound_of(row, "tiktok"), "hashtags": allocation.hashtags_of(row),
         "score": total / 100 + allocation.language_bonus(row.get("language"), accepted)}
        for total, _, _, row in eligible
        if str((row.get("author") or {}).get("handle") or "")
    ]
    result = allocation.select(rows, entries, limit)
    picked = {slot["content_key"]: slot["signature_content_id"] for slot in result["slots"]}
    # 保持 pre_score 的先后：history_requests 按这个顺序发，宿主限流时砍掉的是排在最后的账号。
    ordered = [value for value in eligible if str(value[3]["content_key"]) in picked]
    summary = {"rule_version": allocation.RULE_VERSION, "per_content": result["per_content"],
               "shortfall": result["shortfall"]}
    return ordered, picked, summary


def build(request: dict[str, Any], candidates: dict[str, Any], gate: dict[str, Any], limit: int,
          signature_content: bool = False) -> dict[str, Any]:
    if candidates.get("schema_version") != "tiktok-trend-candidate-set.v1":
        raise ValueError("candidates must be tiktok-trend-candidate-set.v1")
    if gate.get("platform") != "tiktok" or gate.get("request_id") != request.get("request_id"):
        raise ValueError("gate must match the TikTok request")
    items = candidates.get("items") or []
    by_key = {str(row["content_key"]): row for row in items}
    if len(by_key) != len(items):
        raise ValueError("duplicate candidate content_key")
    validate_complete(gate, set(by_key))
    scores = semantic_scores(gate)
    heat = percentiles(items)
    eligible = []
    for row in items:
        key = str(row["content_key"])
        row_scores = scores[key]
        transferability = row_scores.get("creator_transferability")
        # 缺 creator_transferability 时把它的 0.25 按原比例摊给另外两项（0.5:0.25 → 2/3:1/3）。
        # Gate 只在 Request 带 anchor 时才打这一项，没有 anchor 就没有可判的依据。
        semantic = (
            (row_scores["topic_relevance"] * 0.5 + row_scores["locale_fit"] * 0.25) / 0.75
            if transferability is None
            else row_scores["topic_relevance"] * 0.5
            + transferability * 0.25
            + row_scores["locale_fit"] * 0.25
        )
        if (
            scores[key]["topic_relevance"] < TIKTOK_TOPIC_RELEVANCE_FLOOR
            or scores[key]["locale_fit"] < TIKTOK_LOCALE_FIT_FLOOR
        ):
            continue
        eligible.append((semantic * 0.55 + heat[key] * 0.45, semantic, heat[key], row))
    eligible.sort(key=lambda value: (-value[0], -value[1], -value[2], str(value[3]["content_key"])))
    selected = []
    if signature_content:
        ordered, picked, summary = signature_shortlist(request, gate, eligible, limit)
        for total, semantic, heat_score, row in ordered:
            copied = json.loads(json.dumps(row))
            copied["semantic_scores"] = scores[str(row["content_key"])]
            copied["semantic_total"] = round(semantic, 6)
            copied["heat_percentile"] = round(heat_score, 6)
            copied["pre_score"] = round(total, 6)
            copied["signature_content_id"] = picked[str(row["content_key"])]
            selected.append(copied)
    else:
        per_author: dict[str, int] = {}
        for total, semantic, heat_score, row in eligible:
            handle = str((row.get("author") or {}).get("handle") or "")
            if not handle or per_author.get(handle, 0) >= 2:
                continue
            copied = json.loads(json.dumps(row))
            copied["semantic_scores"] = scores[str(row["content_key"])]
            copied["semantic_total"] = round(semantic, 6)
            copied["heat_percentile"] = round(heat_score, 6)
            copied["pre_score"] = round(total, 6)
            selected.append(copied)
            per_author[handle] = per_author.get(handle, 0) + 1
            if len(selected) >= limit:
                break
    result = {
        "schema_version": "tiktok-trend-ranking-input.v1",
        "request_id": request["request_id"],
        "candidate_set_id": candidates.get("candidate_set_id"),
        "selected": selected,
        # Shortlist order, not alphabetical: a host that caps retrievals per turn refuses the last
        # requests, and the accounts it leaves without a baseline should be the lowest-ranked ones.
        "history_requests": [
            {"handle": handle, "limit": 30}
            for handle in dict.fromkeys(str(row["author"]["handle"]) for row in selected)
        ],
        "coverage": {"candidate_count": len(items), "eligible_count": len(eligible), "selected_count": len(selected)},
    }
    if signature_content:
        result["signature_allocation"] = summary
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--signature-content", action="store_true",
                        help="share the shortlist across the Request's signature content (one post per author)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        result = build(load(args.request), load(args.candidates), load(args.gate), args.limit,
                       args.signature_content)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "selected": len(result["selected"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
