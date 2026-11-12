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
    """Narrow to the discovery window.

    Discovery calls often pass a relative window (last-month), which the backend resolves to a rolling interval,
    while the window in the request is often written as a calendar month. The backend requires the completion window
    to be contained in the discovery window, and a one-day offset between the two sends the whole batch back, so we
    take the intersection here rather than passing it through unchanged.
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
    """The anchor account's own posts must not take a delivery slot - the report is for showing them other people's posts.

    On the competitor side select_accounts.py has long excluded by subject handle (marked excluded_subject); the
    trend chain never did, and position 4 of the v4.7 final was the creator themselves. This fills the gap, matching
    the competitor basis.

    Drop them from the delivery slots only before submitting enrichment, and leave the discovery layer alone: the
    anchor account being caught by its own search terms is exactly the signal that this set of terms was well
    chosen, and intent_yield needs it.
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
    """Three-item weighting; when creator_transferability is missing, its weight is spread proportionally over the other two.

    The Gate scores creator_transferability only when the Request carries anchor information - without an anchor
    there is nothing to judge about whether this Creator can carry it. When it is omitted, its 0.25 is renormalized
    in the original proportion onto topic_relevance and locale_fit (0.5:0.25 -> 2/3:1/3), the total still falls in
    0-100, and the relative order within one Gate is decided only by the dimensions actually scored. Totals across
    runs are not directly comparable: with and without an anchor the dimensions measured are different.
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
    """Qualified candidates within one lane and their semantic scores, already sorted in this lane's deterministic order.

    The score is the **relative position within this lane's pool** and is not directly comparable across lanes - slot
    allocation is left to the backend, per lane.
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
        # The relevance lane takes a slot first: when the same content is caught by both lanes it counts as the relevance
        # lane, because it has already proven itself within the window and as strongly relevant, so there is no need for
        # it to also take a slot from the reach lane.
        seen = {str(item["content_key"]) for item in eligible}
        reach_eligible = [
            item for item in reach_eligible if str(item["content_key"]) not in seen
        ]
        for key, value in reach_scores.items():
            scores.setdefault(key, value)
        for item in reach_eligible:
            lane_of[str(item["content_key"])] = "reach"
        # Each of the two lanes first takes half the slots, and whichever falls short is filled up by the other, so one
        # lane cannot crowd the other out entirely - how slots are split is the backend's business, and this only
        # guarantees both lanes get in.
        half = limit // 2
        head = eligible[:half] + reach_eligible[: limit - half]
        tail = eligible[half:] + reach_eligible[limit - half :]
        eligible = head + tail[: max(0, limit - len(head))]

    window = request.get("window") or {}
    if not isinstance(window.get("since"), str) or not isinstance(window.get("until"), str):
        raise ValueError("request window must contain exact since and until timestamps")
    discovery = candidates.get("discovery_window")
    if two_lane:
        # Candidates come from two discovery windows, so the report window's upper bound is the union of the two (then
        # intersected with the request window). Narrowing only to the relevance lane's 30 days would put all of the reach
        # lane's content outside the window.
        reach_discovery = reach_candidates.get("discovery_window")
        if isinstance(discovery, dict) and isinstance(reach_discovery, dict):
            discovery = {
                "since": min(discovery["since"], reach_discovery["since"]),
                "until": max(discovery["until"], reach_discovery["until"]),
            }
    since, until = clamp_to_discovery(window, discovery)
    if two_lane:
        # Raise an error directly when the request window itself is too narrow, and do not widen it quietly - widening
        # amounts to delivering a time period the user did not ask for.
        # When the window does not cover the reach lane, the backend filters out that whole batch, which is a silently
        # failing lane: the output looks normal, but none of the hot content gets in.
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
    # Handle form: the candidate set stays on the server, and the input carries only the id and the content_key
    # selected this time. The two lanes have two candidate-set ids, while the handle form can bind only one, so the
    # two lanes use the inline form.
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
    # The reach lane is an optional second discovery lane: it pulls high-popularity content across a longer window.
    # When given, it goes through top-tier saturation.
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
        # When the reach lane is dropped there is no symptom at all: the output is still a valid single-lane ranking
        # input, only the window collapses back to one month and the several dozen candidates unique to the reach lane
        # do not get in at all, even though their provider budget has already been spent. Hit once in a real run on
        # 2026-09-07: both lanes were collected and passed the semantic gate, but this build step used the single-lane
        # command, and 0 of the 58 candidates unique to the reach lane were selected.
        # So look in the same directory proactively here: if the file exists and was not passed in, raise an error
        # rather than silently degrading.
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
            # The enrich input is the verbatim content of this file; print the compact form so the model does not need to
            # run jq again.
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
