#!/usr/bin/env python3
"""Attach TikTok account-history baselines to a frozen discovery shortlist."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def histories(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runs = source.get("runs")
    if not isinstance(runs, dict) and "status" not in source and "data" not in source:
        direct = {str(handle): value for handle, value in source.items() if isinstance(value, dict)}
        if direct and all("status" in value or "data" in value for value in direct.values()):
            runs = direct
    if not isinstance(runs, dict):
        raise ValueError("histories must contain a runs object or a direct envelope map keyed by handle")
    return {str(handle).lstrip("@"): value for handle, value in runs.items() if isinstance(value, dict)}


def baseline(row: dict[str, Any], envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    if not envelope or envelope.get("status") != "completed":
        return None
    observed = parse_time(str(envelope.get("retrieved_at")))
    target_id = str(row["content_id"])
    values: list[float] = []
    for item in (envelope.get("data") or {}).get("rows") or []:
        if str(item.get("content_id") or "") == target_id:
            continue
        published = item.get("published_at")
        if not isinstance(published, str) or (observed - parse_time(published)).total_seconds() < 86400:
            continue
        views = (item.get("metrics") or {}).get("views")
        if isinstance(views, (int, float)) and not isinstance(views, bool) and views >= 0:
            values.append(float(views))
    target = (row.get("metrics") or {}).get("views")
    if len(values) < 3 or not isinstance(target, (int, float)):
        return None
    median = float(statistics.median(values))
    if median <= 0:
        return None
    multiple = float(target) / median
    return {
        "target_play_count": float(target),
        "cohort_median": median,
        "multiple": round(multiple, 6),
        "cohort_size": len(values),
        "bucket": "strong" if multiple >= 3 else "moderate" if multiple >= 1.5 else "ordinary",
        "evidence_strength": "strong" if len(values) >= 10 else "moderate" if len(values) >= 5 else "directional",
        "formula_version": "tiktok-account-median.v1",
    }


def build(ranking: dict[str, Any], history_source: dict[str, Any]) -> dict[str, Any]:
    if ranking.get("schema_version") != "tiktok-trend-ranking-input.v1":
        raise ValueError("ranking must be tiktok-trend-ranking-input.v1")
    by_handle = histories(history_source)
    items = []
    missing = []
    for selected in ranking.get("selected") or []:
        handle = str((selected.get("author") or {}).get("handle") or "").lstrip("@")
        proof = baseline(selected, by_handle.get(handle))
        if proof is None:
            missing.append(handle)
        items.append({
            "content_key": selected["content_key"],
            "platform": "tiktok",
            "content_id": selected["content_id"],
            "url": selected["url"],
            "caption": selected.get("caption") or "",
            "published_at": selected["published_at"],
            "author": selected["author"],
            "metrics": selected.get("metrics") or {},
            "sources": selected.get("sources") or [],
            "semantic_scores": selected.get("semantic_scores") or {},
            "heat_percentile": selected.get("heat_percentile"),
            "pre_score": selected.get("pre_score"),
            "outlier": proof,
        })
    limitations = [
        "Account-history rows do not expose pinned status, so pinned posts could not be excluded from baselines."
    ]
    if missing:
        limitations.append("No reliable account baseline was available for: " + ", ".join(sorted(set(missing))))
    return {
        "schema_version": "tiktok-trend-enrichment.v1",
        "status": "completed" if not missing else "partial",
        "items": items,
        "coverage": {
            "requested_items": len(ranking.get("selected") or []),
            "enriched_items": len(items),
            "unique_authors": len({str(item["author"].get("id") or item["author"].get("handle")) for item in items}),
            "items_with_baseline": sum(item["outlier"] is not None for item in items),
        },
        "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranking", type=Path, required=True)
    parser.add_argument("--histories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(load(args.ranking), load(args.histories))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "items": len(result["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
