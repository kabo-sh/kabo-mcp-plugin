#!/usr/bin/env python3
"""Build the server-ranked YouTube enrichment input from one semantic Gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from trend_gate_contract import (
    YOUTUBE_LOCALE_FIT_FLOOR,
    YOUTUBE_TOPIC_RELEVANCE_FLOOR,
    semantic_scores,
    validate_complete,
)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def write_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def semantic_total(scores: dict[str, float]) -> float:
    """三项加权；缺 creator_transferability 时把它的权重按比例摊给另外两项。

    Gate 只在 Request 带上 anchor 信息时才打 creator_transferability——没有 anchor 就没有
    「这个 Creator 接不接得住」可判。省略它时把那 0.25 按原比例归一化到 topic_relevance 与
    locale_fit（0.5:0.25 → 2/3:1/3），总分仍落在 0–100，同一份 Gate 内的相对次序也只由真正
    打过的维度决定。跨运行的总分不可直接比较：有无 anchor 衡量的维度本就不同。
    """
    topic = scores["topic_relevance"] * 0.5
    locale = scores["locale_fit"] * 0.25
    transferability = scores.get("creator_transferability")
    if transferability is None:
        return (topic + locale) / 0.75
    return topic + transferability * 0.25 + locale


def view_count_rank(item: dict[str, Any]) -> int:
    ranks = [
        source.get("rank")
        for source in item.get("sources") or []
        if isinstance(source, dict)
        and source.get("route") == "view_count"
        and isinstance(source.get("rank"), int)
    ]
    return min(ranks) if ranks else 10**9


def semantic_sort_key(item: dict[str, Any], scores: dict[str, dict[str, float]]) -> tuple:
    key = str(item["content_key"])
    return (
        -semantic_total(scores[key]),
        min(
            [
                source.get("rank")
                for source in item.get("sources") or []
                if isinstance(source, dict) and isinstance(source.get("rank"), int)
            ]
            or [10**9]
        ),
        key,
    )


# 语义 50 会把播放路高位挤掉（006：view_count 第 3、语义 85，截在 86.25）。
# 先留 12 个播放路名额，其余仍按语义填满 50。
VIEW_COUNT_RESERVE = 12


def select_enrichment_pool(
    eligible: list[dict[str, Any]],
    scores: dict[str, dict[str, float]],
    limit: int,
    reserve_view_count: int = VIEW_COUNT_RESERVE,
) -> list[dict[str, Any]]:
    reserve_n = min(reserve_view_count, limit, len(eligible))
    by_view = sorted(
        [item for item in eligible if view_count_rank(item) < 10**9],
        key=lambda item: (
            view_count_rank(item),
            -semantic_total(scores[str(item["content_key"])]),
            str(item["content_key"]),
        ),
    )
    reserved = by_view[:reserve_n]
    reserved_keys = {str(item["content_key"]) for item in reserved}
    rest = [item for item in eligible if str(item["content_key"]) not in reserved_keys]
    rest.sort(key=lambda item: semantic_sort_key(item, scores))
    return reserved + rest[: max(0, limit - len(reserved))]


def build(
    request: dict[str, Any],
    candidates: dict[str, Any],
    gate: dict[str, Any],
    limit: int = 50,
) -> dict[str, Any]:
    if candidates.get("schema_version") != "youtube-trend-candidate-set.v1":
        raise ValueError("candidates must be youtube-trend-candidate-set.v1")
    if request.get("request_id") != gate.get("request_id"):
        raise ValueError("gate request_id does not match request")
    if gate.get("platform") != "youtube":
        raise ValueError("YouTube ranking requires a YouTube semantic gate")
    items = candidates.get("items")
    if not isinstance(items, list):
        raise ValueError("candidate items must be an array")
    by_key = {str(item["content_key"]): item for item in items}
    if len(by_key) != len(items):
        raise ValueError("duplicate candidate content_key")
    validate_complete(gate, set(by_key))
    scores = semantic_scores(gate)
    eligible = [
        item
        for item in items
        if scores[str(item["content_key"])]["topic_relevance"]
        >= YOUTUBE_TOPIC_RELEVANCE_FLOOR
        and scores[str(item["content_key"])]["locale_fit"]
        >= YOUTUBE_LOCALE_FIT_FLOOR
    ]
    selected_items = select_enrichment_pool(eligible, scores, limit)
    window = request.get("window") or {}
    if not isinstance(window.get("since"), str) or not isinstance(window.get("until"), str):
        raise ValueError("request window must contain exact since and until timestamps")
    payload = {
        "platform": "youtube",
        "ranking_mode": "evidence_ranked.v1",
        "window": {"since": window["since"], "until": window["until"]},
    }
    # 句柄形态:候选集留在服务端，入参只带编号与本次选中的 content_key。
    candidate_set_id = candidates.get("candidate_set_id")
    if candidate_set_id is not None:
        if not isinstance(candidate_set_id, str) or not candidate_set_id:
            raise ValueError("candidate_set_id must be a non-empty string")
        payload["candidate_set_id"] = candidate_set_id
        payload["selected"] = [
            {
                "content_key": str(item["content_key"]),
                "semantic_scores": scores[str(item["content_key"])],
            }
            for item in selected_items
        ]
        return payload
    output_items = []
    for item in selected_items:
        copied = json.loads(json.dumps(item))
        copied["semantic_scores"] = scores[str(item["content_key"])]
        copied.pop("relevance", None)
        output_items.append(copied)
    payload["items"] = output_items
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--print", action="store_true", help="also print the ranking input compactly (the enrichment call takes it verbatim)")
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        result = build(load(args.request), load(args.candidates), load(args.gate), args.limit)
        write_once(args.output, result)
        selected = result.get("selected", result.get("items"))
        print(json.dumps({"status": "ok", "eligible": len(selected), "path": str(args.output)}))
        if args.print:
            # enrich 的入参就是这份文件的原文；打印紧凑形式，模型不必再 jq 一次。
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
