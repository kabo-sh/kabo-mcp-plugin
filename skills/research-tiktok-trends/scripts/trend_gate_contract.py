#!/usr/bin/env python3
"""Normalize compact and legacy Trend relevance-gate contracts."""

from __future__ import annotations

from typing import Any


ROLES = ("direct", "adjacent", "reject")
TOPIC_RELEVANCE_FLOOR = 40
YOUTUBE_TOPIC_RELEVANCE_FLOOR = 60
YOUTUBE_LOCALE_FIT_FLOOR = 50
TIKTOK_TOPIC_RELEVANCE_FLOOR = 60
TIKTOK_LOCALE_FIT_FLOOR = 50


def classifications(gate: dict[str, Any], applied_policy: Any = None) -> dict[str, str]:
    # applied_policy: same signature as the Instagram/YouTube contract; TikTok has no platform
    # enrichment policy, so it is accepted and unused.
    version = gate.get("schema_version")
    if version == "trend-relevance-gate.v1":
        rows = gate.get("items")
        if not isinstance(rows, list):
            raise ValueError("legacy gate items must be an array")
        result: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("content_key"), str):
                raise ValueError("every legacy gate row must contain content_key")
            key = row["content_key"]
            role = row.get("relevance")
            if role not in ROLES:
                raise ValueError(f"invalid relevance for {key}")
            if key in result:
                raise ValueError(f"duplicate gate content_key: {key}")
            result[key] = role
        return result
    if version == "trend-relevance-gate.v2":
        result = {}
        for role in ROLES:
            keys = gate.get(f"{role}_refs")
            if not isinstance(keys, list):
                raise ValueError(f"{role}_refs must be an array")
            for key in keys:
                if not isinstance(key, str) or not key:
                    raise ValueError(f"{role}_refs must contain non-empty strings")
                if key in result:
                    raise ValueError(f"gate content_key appears more than once: {key}")
                result[key] = role
        return result
    if version == "trend-relevance-gate.v3":
        platform = gate.get("platform")
        if platform not in {"instagram", "tiktok", "youtube"}:
            raise ValueError("v3 gate platform must be instagram, tiktok or youtube")
        rows = gate.get("items")
        if not isinstance(rows, list):
            raise ValueError("v3 gate items must be an array")
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("content_key"), str):
                raise ValueError("every v3 gate row must contain content_key")
            key = row["content_key"]
            scores = row.get("semantic_scores")
            if not isinstance(scores, dict):
                raise ValueError(f"semantic_scores missing for {key}")
            for name in ("topic_relevance", "locale_fit"):
                value = scores.get(name)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                    raise ValueError(f"invalid {name} for {key}")
            # creator_transferability 只有在 Request 带上 anchor 信息时才有得打：没有 anchor
            # 就没有「这个 Creator 接不接得住」可判，硬要一个分等于凭空造分。所以缺席是合法
            # 状态，打了就必须是 0–100 的数。下游 semantic_total 会把它的权重摊给另外两项。
            if "creator_transferability" in scores:
                value = scores["creator_transferability"]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                    raise ValueError(f"invalid creator_transferability for {key}")
            if key in result:
                raise ValueError(f"duplicate gate content_key: {key}")
            # 下游旧 Snapshot/Analyzer 只需要 eligible/reject 二值边界；direct 是内部
            # 兼容投影，不再是模型输入分类，也不参与配额或排序。
            if platform in {"tiktok", "youtube"}:
                eligible = (
                    scores["topic_relevance"] >= (
                        TIKTOK_TOPIC_RELEVANCE_FLOOR
                        if platform == "tiktok"
                        else YOUTUBE_TOPIC_RELEVANCE_FLOOR
                    )
                    and scores["locale_fit"] >= (
                        TIKTOK_LOCALE_FIT_FLOOR
                        if platform == "tiktok"
                        else YOUTUBE_LOCALE_FIT_FLOOR
                    )
                )
            else:
                eligible = scores["topic_relevance"] >= TOPIC_RELEVANCE_FLOOR
            result[key] = "direct" if eligible else "reject"
        return result
    raise ValueError("expected trend-relevance-gate.v1, v2 or v3")


def semantic_scores(gate: dict[str, Any]) -> dict[str, dict[str, float]]:
    if gate.get("schema_version") != "trend-relevance-gate.v3":
        raise ValueError("semantic scores require trend-relevance-gate.v3")
    output: dict[str, dict[str, float]] = {}
    for row in gate.get("items") or []:
        key = str(row["content_key"])
        # creator_transferability 缺席时不补这个键：下游按「没打过」归一化权重，
        # 而补一个 0 会被读成「判过、且极低」——两者是完全不同的结论。
        output[key] = {
            name: float(row["semantic_scores"][name])
            for name in ("topic_relevance", "creator_transferability", "locale_fit")
            if name in row["semantic_scores"]
        }
    return output


def validate_complete(gate: dict[str, Any], expected_keys: set[str], applied_policy: Any = None) -> dict[str, str]:
    result = classifications(gate, applied_policy)
    missing = sorted(expected_keys - set(result))
    unknown = sorted(set(result) - expected_keys)
    if missing or unknown:
        raise ValueError(
            f"gate must classify the complete candidate union; missing={missing}, unknown={unknown}"
        )
    return result
