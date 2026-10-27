#!/usr/bin/env python3
"""Build the server-ranked Instagram enrichment input from one scored semantic Gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from trend_gate_contract import TOPIC_RELEVANCE_FLOOR, semantic_scores, validate_complete


def instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"window bound {value!r} is not an ISO timestamp") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def clamp_to_discovery(window: dict[str, Any], discovery: Any) -> tuple[str, str]:
    """收窄到发现窗口内。

    发现调用常传相对窗口(last-month)，后端解析成滚动区间；请求里的窗口却往往写成自然月。
    后端要求补全窗口被发现窗口包含，两者错开一天就会整批打回，所以这里取交集而不是原样透传。
    """
    since, until = window["since"], window["until"]
    if not isinstance(discovery, dict):
        return since, until
    if not isinstance(discovery.get("since"), str) or not isinstance(discovery.get("until"), str):
        return since, until
    since = max(since, discovery["since"], key=instant)
    until = min(until, discovery["until"], key=instant)
    if instant(since) >= instant(until):
        raise ValueError("request window does not overlap the candidate set discovery window")
    return since, until


def canonical_handle(value: str) -> str:
    return value.strip().removeprefix("@").casefold()


def anchor_handle(request: dict[str, Any]) -> str | None:
    profile = request.get("creator_profile")
    if not isinstance(profile, dict):
        return None
    handle = profile.get("handle")
    if isinstance(handle, str) and handle.strip():
        return canonical_handle(handle)
    url = profile.get("public_profile_url")
    if isinstance(url, str):
        match = re.search(r"instagram\.com/([^/?#]+)", url)
        if match:
            return canonical_handle(match.group(1))
    return None


def by_anchor(item: dict[str, Any], anchor: str | None) -> bool:
    """锚定账号自己的帖子不该占交付位——报告是给他看别人的。

    竞品那边 select_accounts.py 早就按 subject handle 剔了(标 excluded_subject)，
    趋势这条链路一直没有,v4.7 终版第 4 位就是创作者本人。这里补齐,与竞品口径一致。

    只在提交富化前摘掉交付位,不动发现层:锚定账号被自己的检索词捞到,
    恰恰是这组词选对了的信号,intent_yield 要用。
    """
    if anchor is None:
        return False
    handle = ((item.get("author") or {}).get("handle") or "")
    return bool(handle) and canonical_handle(str(handle)) == anchor


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


def eligible_of(
    request: dict[str, Any],
    candidates: dict[str, Any],
    gate: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """一条车道内的合格候选与它们的语义分，已按本车道的确定序排好。

    分数是**本车道池内的相对位置**，跨车道不可直接比较——名额分配交给后端按车道做。
    """
    if candidates.get("schema_version") != "trend-candidate-set.v1":
        raise ValueError("candidates must be trend-candidate-set.v1")
    if request.get("request_id") != gate.get("request_id"):
        raise ValueError("gate request_id does not match request")
    if gate.get("platform") != "instagram":
        raise ValueError("Instagram ranking requires an Instagram semantic gate")
    items = candidates.get("items")
    if not isinstance(items, list):
        raise ValueError("candidate items must be an array")
    by_key = {str(item["content_key"]): item for item in items}
    if len(by_key) != len(items):
        raise ValueError("duplicate candidate content_key")
    validate_complete(gate, set(by_key))
    scores = semantic_scores(gate)
    anchor = anchor_handle(request)
    eligible = [
        item
        for item in items
        if scores[str(item["content_key"])]["topic_relevance"] >= TOPIC_RELEVANCE_FLOOR
        and not by_anchor(item, anchor)
    ]
    eligible.sort(
        key=lambda item: (
            -semantic_total(scores[str(item["content_key"])]),
            min(
                [
                    source.get("rank")
                    for source in item.get("sources") or []
                    if isinstance(source, dict) and isinstance(source.get("rank"), int)
                ]
                or [10**9]
            ),
            str(item["content_key"]),
        )
    )
    return eligible, scores


def build(
    request: dict[str, Any],
    candidates: dict[str, Any],
    gate: dict[str, Any],
    limit: int = 60,
    reach_candidates: dict[str, Any] | None = None,
    reach_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eligible, scores = eligible_of(request, candidates, gate)
    lane_of = {str(item["content_key"]): "relevance" for item in eligible}
    two_lane = reach_candidates is not None and reach_gate is not None
    if two_lane:
        reach_eligible, reach_scores = eligible_of(request, reach_candidates, reach_gate)
        # 相关车道优先占位：同一条内容被两条车道都捞到时算相关车道，
        # 因为它已经证明自己在窗口内且强相关，没必要再占到达车道的名额。
        seen = {str(item["content_key"]) for item in eligible}
        reach_eligible = [
            item for item in reach_eligible if str(item["content_key"]) not in seen
        ]
        for key, value in reach_scores.items():
            scores.setdefault(key, value)
        for item in reach_eligible:
            lane_of[str(item["content_key"])] = "reach"
        # 两条车道各自先拿一半名额，谁不够再由另一条补满，避免一条车道把
        # 另一条整个挤出去——名额怎么分是后端的事，这里只保证两条都进得来。
        half = limit // 2
        head = eligible[:half] + reach_eligible[: limit - half]
        tail = eligible[half:] + reach_eligible[limit - half :]
        eligible = head + tail[: max(0, limit - len(head))]

    window = request.get("window") or {}
    if not isinstance(window.get("since"), str) or not isinstance(window.get("until"), str):
        raise ValueError("request window must contain exact since and until timestamps")
    discovery = candidates.get("discovery_window")
    if two_lane:
        # 候选来自两条发现窗口，报告窗口的上界就是两者的并集（再与请求窗口取交）。
        # 只按相关车道那 30 天收窄会把到达车道的内容全部挡在窗口外。
        reach_discovery = reach_candidates.get("discovery_window")
        if isinstance(discovery, dict) and isinstance(reach_discovery, dict):
            discovery = {
                "since": min(discovery["since"], reach_discovery["since"]),
                "until": max(discovery["until"], reach_discovery["until"]),
            }
    since, until = clamp_to_discovery(window, discovery)
    if two_lane:
        # 请求窗口本身太窄时直接报错，不悄悄放宽——放宽等于交付用户没有要的时间段。
        # 而窗口盖不住到达车道时后端会把它整批滤掉，那是一条静默失效的车道：
        # 产出看着正常，只是热度内容一条都进不来。
        reach_since = (reach_candidates.get("discovery_window") or {}).get("since")
        if isinstance(reach_since, str) and instant(since) > instant(reach_since):
            raise ValueError(
                "request window does not cover the reach lane discovery window "
                f"({since} > {reach_since}); widen the request window or drop the reach lane"
            )
    payload = {
        "platform": "instagram",
        "ranking_mode": "relevance_saturated.v1" if two_lane else "evidence_ranked.v1",
        "window": {"since": since, "until": until},
    }
    # 句柄形态:候选集留在服务端，入参只带编号与本次选中的 content_key。
    # 两条车道有两个候选集编号，而句柄形态只能绑一个，所以两车道走内联形态。
    candidate_set_id = None if two_lane else candidates.get("candidate_set_id")
    if candidate_set_id is not None:
        if not isinstance(candidate_set_id, str) or not candidate_set_id:
            raise ValueError("candidate_set_id must be a non-empty string")
        payload["candidate_set_id"] = candidate_set_id
        payload["selected"] = [
            {
                "content_key": str(item["content_key"]),
                "semantic_scores": scores[str(item["content_key"])],
            }
            for item in eligible[:limit]
        ]
        return payload
    output_items = []
    for item in eligible[:limit]:
        key = str(item["content_key"])
        copied = json.loads(json.dumps(item))
        copied["semantic_scores"] = scores[key]
        copied.pop("relevance", None)
        if two_lane:
            copied["lane"] = lane_of[key]
        output_items.append(copied)
    payload["items"] = output_items
    return payload


def multiset_handle(
    lean: dict[str, Any], candidates: dict[str, Any], reach_candidates: dict[str, Any]
) -> dict[str, Any] | None:
    """The two-lane enrichment in the multi-set handle form, or None when it cannot be.

    `lean` is the inline call the two lanes send today (the first six of each lane); this names the
    same items, in the same order, by content_key against the two lanes' candidate sets, so the backend
    enriches exactly that set. Without both lanes' `candidate_set_id` there is no handle to send.
    """
    relevance_id = candidates.get("candidate_set_id")
    reach_id = reach_candidates.get("candidate_set_id")
    if not (isinstance(relevance_id, str) and relevance_id and isinstance(reach_id, str) and reach_id):
        return None
    payload = {key: value for key, value in lean.items() if key != "items"}
    payload["candidate_sets"] = [
        {"lane": "relevance", "candidate_set_id": relevance_id},
        {"lane": "reach", "candidate_set_id": reach_id},
    ]
    payload["selected"] = [
        {"content_key": str(item["content_key"]), "semantic_scores": item["semantic_scores"], "lane": item["lane"]}
        for item in lean.get("items") or []
    ]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    # 到达车道是可选的第二条发现车道：跨更长窗口捞高热度内容。给了就走顶档饱和。
    parser.add_argument("--reach-candidates", type=Path)
    parser.add_argument("--reach-gate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--print", action="store_true", help="also print the ranking input compactly (the enrichment call takes it verbatim)")
    args = parser.parse_args()
    try:
        if not 1 <= args.limit <= 60:
            raise ValueError("limit must be between 1 and 60")
        if bool(args.reach_candidates) != bool(args.reach_gate):
            raise ValueError("--reach-candidates and --reach-gate must be given together")
        # 到达车道被丢掉的时候没有任何症状：产出照样是一份合法的单车道排序输入，
        # 只是窗口塌回一个月、到达车道那几十条独有候选一条都进不来，而它们的
        # provider 预算已经花掉了。2026-09-07 实测撞到一次：两条车道都采集并过了
        # 语义门，构建这一步用的却是单车道那条命令，到达车道 58 条独有候选 0 条入选。
        # 所以这里主动看一眼同目录：文件在、没传进来，就报错，别静默降级。
        sibling = args.candidates.with_name(
            f"{args.candidates.stem}-reach{args.candidates.suffix}"
        )
        if not args.reach_candidates and sibling.exists():
            raise ValueError(
                f"{sibling.name} exists next to {args.candidates.name} but --reach-candidates "
                "was not passed; a two-lane run built as one lane silently drops the reach lane "
                "and narrows the report window back to the relevance lane. Pass both "
                "--reach-candidates and --reach-gate, or delete the reach files if that lane "
                "was abandoned on purpose"
            )
        result = build(
            load(args.request),
            load(args.candidates),
            load(args.gate),
            args.limit,
            load(args.reach_candidates) if args.reach_candidates else None,
            load(args.reach_gate) if args.reach_gate else None,
        )
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
