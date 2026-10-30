#!/usr/bin/env python3
"""Normalize compact and legacy Trend relevance-gate contracts."""

from __future__ import annotations

from typing import Any


ROLES = ("direct", "adjacent", "reject")
# Instagram floor, matching the platform's enrichment floor: the rubric scores 0-54 as off-topic,
# so anything below 55 is dropped by the backend anyway and would only waste shortlist seats.
TOPIC_RELEVANCE_FLOOR = 55
YOUTUBE_TOPIC_RELEVANCE_FLOOR = 60
YOUTUBE_LOCALE_FIT_FLOOR = 50


def applied_floors(platform: str, applied_policy: Any = None) -> dict[str, float]:
    """The relevance floors the platform's enrichment actually applied, else this package's own.

    The backend runs the enrichment and reports its thresholds as ``applied_policy``
    (``topic_relevance_floor``; YouTube also ``locale_fit_floor``). When present and well formed
    those values win, so the package and the platform cannot disagree about who passed; when
    absent (an older platform) the constants above apply unchanged.
    """
    youtube = platform == "youtube"
    floors = {
        "topic_relevance": float(YOUTUBE_TOPIC_RELEVANCE_FLOOR if youtube else TOPIC_RELEVANCE_FLOOR),
        "locale_fit": float(YOUTUBE_LOCALE_FIT_FLOOR) if youtube else 0.0,
    }
    if not isinstance(applied_policy, dict):
        return floors
    for field, name in (("topic_relevance_floor", "topic_relevance"), ("locale_fit_floor", "locale_fit")):
        value = applied_policy.get(field)
        if name == "locale_fit" and not youtube:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100:
            floors[name] = float(value)
    return floors


def classifications(gate: dict[str, Any], applied_policy: Any = None) -> dict[str, str]:
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
        if platform not in {"instagram", "youtube"}:
            raise ValueError("v3 gate platform must be instagram or youtube")
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
            # 主打内容列只在 Gate 输入带画像时出现；缺席与 null 是两回事（null 是判过、都不像），
            # 所以这里只校验类型，不补键。它不进地板判断：像不像主打内容决定排到哪一类，不决定去留。
            if "signature_content_id" in row and row["signature_content_id"] is not None and (
                    not isinstance(row["signature_content_id"], str) or not row["signature_content_id"]):
                raise ValueError(f"invalid signature_content_id for {key}")
            # 下游旧 Snapshot/Analyzer 只需要 eligible/reject 二值边界；direct 是内部
            # 兼容投影，不再是模型输入分类，也不参与配额或排序。
            floors = applied_floors(platform, applied_policy)
            if platform == "youtube":
                eligible = (
                    scores["topic_relevance"] >= floors["topic_relevance"]
                    and scores["locale_fit"] >= floors["locale_fit"]
                )
            else:
                eligible = scores["topic_relevance"] >= floors["topic_relevance"]
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


def signature_content_ids(gate: dict[str, Any]) -> dict[str, str | None]:
    """每条 Gate 行判到的主打内容 id（Request 里的 id；null 表示判过、都不像）。

    Gate 输入没带主打内容时，行里没有这一列，返回空字典：调用方据此区分「这轮没有画像」与
    「有画像但这条哪个都不像」，后者才进未匹配的名额。
    """
    if gate.get("schema_version") != "trend-relevance-gate.v3":
        raise ValueError("signature content requires trend-relevance-gate.v3")
    output: dict[str, str | None] = {}
    for row in gate.get("items") or []:
        if not isinstance(row, dict) or "signature_content_id" not in row:
            continue
        value = row["signature_content_id"]
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"invalid signature_content_id for {row.get('content_key')}")
        output[str(row["content_key"])] = value
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
