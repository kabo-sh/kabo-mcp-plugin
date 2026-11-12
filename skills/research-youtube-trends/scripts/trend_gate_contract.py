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
            # creator_transferability can be scored only when the Request carries anchor information: without an anchor
            # there is nothing to judge about "can this Creator carry it", and forcing a score would be making one up. So absence is a legal
            # state, and once scored it must be a number from 0 to 100. Downstream semantic_total spreads its weight over the other two items.
            if "creator_transferability" in scores:
                value = scores["creator_transferability"]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                    raise ValueError(f"invalid creator_transferability for {key}")
            if key in result:
                raise ValueError(f"duplicate gate content_key: {key}")
            # The main-content column appears only when the Gate input carries a profile; absent and null are different things (null means judged, and none matched),
            # so only the type is validated here and no key is filled in. It does not enter the floor judgment: whether it resembles the main content decides which category it ranks in, not whether it stays.
            if "signature_content_id" in row and row["signature_content_id"] is not None and (
                    not isinstance(row["signature_content_id"], str) or not row["signature_content_id"]):
                raise ValueError(f"invalid signature_content_id for {key}")
            # The legacy downstream Snapshot/Analyzer only needs the binary eligible/reject boundary; direct is an internal
            # compatibility projection, no longer a classification for the model input, and takes no part in quota or ranking.
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
        # When creator_transferability is absent this key is not filled in: downstream normalizes weights as "never scored",
        # whereas filling in a 0 would be read as "judged, and extremely low" - two completely different conclusions.
        output[key] = {
            name: float(row["semantic_scores"][name])
            for name in ("topic_relevance", "creator_transferability", "locale_fit")
            if name in row["semantic_scores"]
        }
    return output


def signature_content_ids(gate: dict[str, Any]) -> dict[str, str | None]:
    """The main-content id judged for each Gate row (the id in the Request; null means judged and none matched).

    When the Gate input carries no main content, rows have no such column and an empty dict is returned: the caller uses this to tell "this round has no profile" from
    "there is a profile but this one matches none", and only the latter enters the unmatched quota.
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
