#!/usr/bin/env python3
"""Attach TikTok account-history baselines to a frozen discovery shortlist."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shrunk_baseline  # noqa: E402

# 作者收缩倍数的先验来源：本轮各作者对数中位数的中位数。
PRIOR_SOURCE = "round_authors"


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


def history_samples(envelope: dict[str, Any] | None, exclude_id: str | None = None) -> list[dict[str, Any]]:
    """一个作者的历史作品，写成 shrunk_baseline 的样本形状；目标作品自己不进自己的基线。"""
    if not envelope or envelope.get("status") != "completed":
        return []
    observed = envelope.get("retrieved_at")
    samples = []
    for item in (envelope.get("data") or {}).get("rows") or []:
        if not isinstance(item, dict) or (exclude_id is not None and str(item.get("content_id") or "") == exclude_id):
            continue
        samples.append({
            # 历史行没有时长时按 TikTok 缺省判 short_video；时长 0 的图文不进基线。
            "format": shrunk_baseline.classify_format("tiktok", item.get("duration_seconds")),
            "published_at": item.get("published_at"),
            "observed_at": observed,
            "views": (item.get("metrics") or {}).get("views"),
            "views_basis": "platform_count",
        })
    return samples


def round_priors(by_handle: dict[str, dict[str, Any]], handles: list[str]) -> dict[str, float | None]:
    """每种格式的先验 μ0：本轮每个有成熟作品的作者取对数中位数，再取这些中位数的中位数。"""
    priors: dict[str, float | None] = {}
    for content_format in shrunk_baseline.FORMATS:
        priors[content_format] = shrunk_baseline.round_authors_prior(
            shrunk_baseline.mature_logs(history_samples(by_handle.get(handle)), content_format)
            for handle in dict.fromkeys(handles)
        )
    return priors


def shrunk(row: dict[str, Any], envelope: dict[str, Any] | None, priors: dict[str, float | None]) -> dict[str, Any] | None:
    content_format = shrunk_baseline.classify_format("tiktok", row.get("duration_seconds"))
    prior = priors.get(content_format)
    if content_format == "excluded" or prior is None:
        return None
    proof = shrunk_baseline.baseline(history_samples(envelope, str(row["content_id"])), content_format, prior)
    if proof is None:
        return None
    value = shrunk_baseline.multiple((row.get("metrics") or {}).get("views"), proof["shrunkLogMedian"])
    if value is None:
        return None
    return {
        "multiple": round(value["multiple"], 6),
        "log_baseline": round(proof["shrunkLogMedian"], 9),
        "prior_log_median": round(prior, 9),
        "prior_source": PRIOR_SOURCE,
        "n": proof["n"],
        "k": proof["k"],
        "mature_days": proof["maturityDays"],
        "formula_version": shrunk_baseline.FORMULA_VERSION,
    }


def build(ranking: dict[str, Any], history_source: dict[str, Any], shrink: bool = False) -> dict[str, Any]:
    if ranking.get("schema_version") != "tiktok-trend-ranking-input.v1":
        raise ValueError("ranking must be tiktok-trend-ranking-input.v1")
    by_handle = histories(history_source)
    handles = [str((selected.get("author") or {}).get("handle") or "").lstrip("@")
               for selected in ranking.get("selected") or []]
    priors = round_priors(by_handle, handles) if shrink else {}
    items = []
    missing = []
    for selected in ranking.get("selected") or []:
        handle = str((selected.get("author") or {}).get("handle") or "").lstrip("@")
        proof = baseline(selected, by_handle.get(handle))
        if proof is None:
            missing.append(handle)
        elif shrink:
            # 只增补，不改原有的 multiple 与 bucket：报告与校验仍按原始倍数说话，名额分配读收缩倍数。
            proof["shrunk"] = shrunk(selected, by_handle.get(handle), priors)
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
    parser.add_argument("--shrink", action="store_true",
                        help="add each baseline's shrunk multiple (prior: the round's author medians)")
    args = parser.parse_args()
    try:
        result = build(load(args.ranking), load(args.histories), args.shrink)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "items": len(result["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
