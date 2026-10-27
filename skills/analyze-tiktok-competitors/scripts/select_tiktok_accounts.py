#!/usr/bin/env python3
"""Validate a complete semantic gate and deterministically choose TikTok accounts."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def select(candidates: dict[str, Any], gate_input: dict[str, Any], gate: dict[str, Any], limit: int) -> dict[str, Any]:
    if not 2 <= limit <= 5:
        raise ValueError("limit must be between 2 and 5")
    expected = {str(row["account_ref"]): row for row in gate_input.get("items") or []}
    rows = gate.get("items") or []
    if gate.get("schema_version") != "tiktok-competitor-discovery-gate.v1":
        raise ValueError("gate must be tiktok-competitor-discovery-gate.v1")
    if gate.get("request_id") != gate_input.get("request_id"):
        raise ValueError("gate request_id mismatch")
    actual = [str(row.get("account_ref") or "") for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError("gate must classify every projected account exactly once")
    support: dict[str, dict[str, Any]] = defaultdict(lambda: {"content_count": 0, "routes": set(), "max_views": 0})
    for item in candidates.get("items") or []:
        author = item.get("author") or {}
        handle = str(author.get("handle") or "").lower().lstrip("@")
        ref = str(author.get("id") or (f"tiktok:{handle}" if handle else ""))
        if ref not in expected:
            continue
        support[ref]["content_count"] += 1
        support[ref]["routes"].update(str(row.get("route") or "") for row in item.get("sources") or [])
        views = (item.get("metrics") or {}).get("views")
        if isinstance(views, (int, float)) and not isinstance(views, bool):
            support[ref]["max_views"] = max(support[ref]["max_views"], views)
    eligible = []
    floor_rejections = []
    reasons: dict[str, str] = {}
    for row in rows:
        relationship = row["relationship"]
        if relationship == "excluded":
            reasons[str(row["account_ref"])] = "gate_excluded"
            continue
        ref = str(row["account_ref"])
        semantic = (
            0.4 * row["category_fit"]
            + 0.3 * row["audience_job_fit"]
            + 0.2 * row["sustained_focus"]
            + 0.1 * row["locale_fit"]
        )
        if relationship == "direct" and row["category_fit"] < 60:
            floor_rejections.append({
                "account_ref": ref,
                "relationship": relationship,
                "reason": "category_fit_below_60",
            })
            continue
        if relationship == "adjacent" and max(row["category_fit"], row["audience_job_fit"]) < 55:
            floor_rejections.append({
                "account_ref": ref,
                "relationship": relationship,
                "reason": "category_and_audience_job_fit_below_55",
            })
            continue
        evidence = support[ref]
        retrieval = min(100.0, 20 * len(evidence["routes"]) + 10 * min(evidence["content_count"], 4) + 5 * math.log10(evidence["max_views"] + 1))
        eligible.append({
            **expected[ref],
            "relationship": relationship,
            "semantic_score": round(semantic, 3),
            "retrieval_support": round(retrieval, 3),
            "selection_score": round(0.8 * semantic + 0.2 * retrieval, 3),
            "discovery_content_count": evidence["content_count"],
        })
    priority = {"direct": 0, "adjacent": 1, "media": 2}
    eligible.sort(key=lambda row: (priority[row["relationship"]], -row["selection_score"], row["account_ref"]))
    included = []
    media_count = 0
    for row in eligible:
        if row["relationship"] == "media":
            if media_count >= 1:
                continue
            media_count += 1
        included.append(row)
        if len(included) >= limit:
            break
    reasons.update({row["account_ref"]: row["reason"] for row in floor_rejections})
    chosen = {row["account_ref"] for row in included}
    unresolved = [
        {"account_ref": ref, "handle": row["handle"], "reason": reasons.get(ref, "not_selected")}
        for ref, row in sorted(expected.items())
        if row.get("provided") and ref not in chosen
    ]
    return {
        "schema_version": "tiktok-competitor-account-selection.v1",
        "request_id": gate_input["request_id"],
        "included": included,
        "excluded_count": len(expected) - len(included),
        "floor_rejections": sorted(floor_rejections, key=lambda row: row["account_ref"]),
        "unresolved_accounts": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gate-input", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = select(load(args.candidates), load(args.gate_input), load(args.gate), args.limit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": "ok",
            "included": len(result["included"]),
            "handles": [
                {"handle": row.get("handle"), "relationship": row.get("relationship")}
                for row in result["included"]
            ],
            "unresolved": [
                {"handle": row["handle"], "reason": row["reason"]}
                for row in result["unresolved_accounts"]
            ],
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
