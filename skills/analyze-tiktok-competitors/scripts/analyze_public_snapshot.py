#!/usr/bin/env python3
"""Build deterministic public facts for Account, Trend, and Competitor tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from evidence_contract import RELIABLE_OUTLIER_MIN_SAMPLE

RULE_VERSION = "public-content-facts.v1.4"
AVAILABLE = {"available", "zero"}
NON_COMPARABLE_FORMATS = {"unknown", "unknown_video", "format_unknown", "unclassified"}


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def metric(item: dict[str, Any], name: str) -> float | None:
    entry = item.get("metrics", {}).get(name)
    if not isinstance(entry, dict) or entry.get("status") not in AVAILABLE:
        return None
    value = entry.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{item.get('content_id')}.metrics.{name}.value must be a non-negative finite number")
    return float(value)


def sample_confidence(size: int) -> str:
    if size < 3:
        return "insufficient"
    if size < 5:
        return "low"
    if size < 10:
        return "medium"
    return "high"


def comparable_format(value: Any) -> bool:
    return str(value or "").strip().casefold() not in NON_COMPARABLE_FORMATS


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def format_evidence(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in ("format_confidence", "format_source")
        if isinstance(source.get(key), str) and source[key].strip()
    }


def outlier_evidence_strength(comparable_n: int) -> str:
    """Keep sample sufficiency separate from denominator magnitude."""
    if comparable_n < RELIABLE_OUTLIER_MIN_SAMPLE:
        return "directional_sample"
    return "reliable"


def outlier_evidence_score(views: float, multiple: float, comparable_n: int) -> float:
    """Continuously rank absolute heat, relative lift and sample support.

    The formula has no baseline-size cliff. Because ``views = baseline * multiple``,
    ``log1p(views)`` carries denominator scale without letting a large account
    swamp relative breakout, while the second term rewards lift in proportion
    to the amount of same-account evidence behind it.
    """
    sample_support = math.sqrt(comparable_n / (comparable_n + RELIABLE_OUTLIER_MIN_SAMPLE))
    relative_lift = math.log(multiple) * sample_support if multiple > 0 else 0.0
    return round(math.log1p(views) + relative_lift, 6)


def validate_snapshot(snapshot: dict[str, Any]) -> tuple[datetime, datetime, datetime, set[str]]:
    required = {"schema_version", "snapshot_id", "observed_at", "platform", "scope", "source", "creators", "items"}
    missing = sorted(required - snapshot.keys())
    if missing:
        raise ValueError(f"snapshot missing fields: {missing}")
    if snapshot["schema_version"] != "public-content-snapshot.v1":
        raise ValueError("schema_version must be public-content-snapshot.v1")
    observed = parse_time(snapshot["observed_at"])
    window = snapshot.get("scope", {}).get("window", {})
    start, end = parse_time(window["start"]), parse_time(window["end"])
    if start > end or end > observed:
        raise ValueError("scope window must be ordered and must not end after observed_at")
    creator_ids = [row.get("creator_id") for row in snapshot["creators"]]
    if None in creator_ids or len(creator_ids) != len(set(creator_ids)):
        raise ValueError("creators must have unique non-empty creator_id values")
    return observed, start, end, set(creator_ids)


def normalized_items(snapshot: dict[str, Any], start: datetime, end: datetime, creator_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    unique: dict[str, dict[str, Any]] = {}
    dropped = Counter()
    for source in snapshot["items"]:
        if not isinstance(source, dict):
            raise ValueError("every item must be an object")
        required = ("content_id", "creator_id", "url", "title", "published_at", "format", "metrics")
        missing = [key for key in required if source.get(key) in (None, "")]
        if missing:
            raise ValueError(f"item missing required fields {missing}: {source!r}")
        if source["creator_id"] not in creator_ids:
            raise ValueError(f"item references unknown creator_id: {source['creator_id']}")
        published = parse_time(source["published_at"])
        if not start <= published <= end:
            dropped["outside_window"] += 1
            continue
        row = dict(source)
        row["query_refs"] = sorted(set(source.get("query_refs") or []))
        key = str(row["content_id"])
        if key in unique:
            old = dict(unique[key])
            old_refs = old.pop("query_refs", [])
            new = dict(row)
            new_refs = new.pop("query_refs", [])
            if canonical_bytes(old) != canonical_bytes(new):
                raise ValueError(f"conflicting duplicate content_id: {key}")
            unique[key]["query_refs"] = sorted(set(old_refs + new_refs))
            dropped["duplicate_rows_merged"] += 1
        else:
            unique[key] = row
    return sorted(unique.values(), key=lambda row: (row["published_at"], row["content_id"])), dict(sorted(dropped.items()))


def analyze(snapshot: dict[str, Any], mode: str, focus_creator_id: str | None) -> dict[str, Any]:
    observed, start, end, creator_ids = validate_snapshot(snapshot)
    if focus_creator_id and focus_creator_id not in creator_ids:
        raise ValueError(f"unknown focus creator: {focus_creator_id}")
    if mode == "account" and not focus_creator_id:
        raise ValueError("account mode requires --focus-creator-id")
    items, dropped = normalized_items(snapshot, start, end, creator_ids)
    creator_meta = {row["creator_id"]: row for row in snapshot["creators"]}

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        if comparable_format(row["format"]):
            groups[(row["creator_id"], row["format"])].append(row)

    cohorts, baseline_by_group = [], {}
    for (creator_id, content_format), rows in sorted(groups.items()):
        values = {name: [value for row in rows if (value := metric(row, name)) is not None] for name in ("views", "likes", "comments")}
        medians = {name: median(data) for name, data in values.items()}
        baseline_by_group[(creator_id, content_format)] = medians
        cohort = {
            "creator_id": creator_id,
            "handle": creator_meta[creator_id]["handle"],
            "format": content_format,
            "sample_size": len(rows),
            "sample_confidence": sample_confidence(len(rows)),
            "median_metrics": medians,
        }
        if any(format_evidence(row) for row in rows):
            cohort["format_classification"] = {
                "confidence_counts": dict(sorted(Counter(
                    str(row.get("format_confidence") or "unspecified") for row in rows
                ).items())),
                "source_counts": dict(sorted(Counter(
                    str(row.get("format_source") or "unspecified") for row in rows
                ).items())),
            }
        cohorts.append(cohort)

    evidence, ranked, outliers = [], [], []
    for row in items:
        evidence_id = "ev-content-" + hashlib.sha256(str(row["url"]).encode()).hexdigest()[:16]
        values = {name: metric(row, name) for name in ("views", "likes", "comments")}
        evidence.append({
            "evidence_id": evidence_id,
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
            "source_url": row["url"],
            "published_at": row["published_at"],
            "format": row["format"],
            **format_evidence(row),
            "metrics": values,
            "query_refs": row.get("query_refs", []),
        })
        if values["views"] is not None:
            ranked.append({
                "evidence_id": evidence_id,
                "content_id": row["content_id"],
                "creator_id": row["creator_id"],
                "handle": creator_meta[row["creator_id"]]["handle"],
                "title": row["title"],
                "url": row["url"],
                "published_at": row["published_at"],
                "format": row["format"],
                **format_evidence(row),
                "views": values["views"],
                "likes": values["likes"],
                "comments": values["comments"],
            })
        group_rows = groups.get((row["creator_id"], row["format"]), [])
        if not comparable_format(row["format"]):
            continue
        if snapshot.get("platform") == "youtube":
            comparable_rows = [
                candidate for candidate in group_rows
                if candidate["content_id"] != row["content_id"]
                and (observed - parse_time(candidate["published_at"])).total_seconds() >= 14 * 86400
            ]
            comparable_views = [
                value for candidate in comparable_rows
                if (value := metric(candidate, "views")) is not None
            ]
            baseline = median(comparable_views)
            comparable_n = len(comparable_views)
        else:
            baseline = baseline_by_group[(row["creator_id"], row["format"])]["views"]
            comparable_n = sum(
                metric(candidate, "views") is not None for candidate in group_rows
            )
        multiple = round(values["views"] / baseline, 6) if values["views"] is not None and baseline not in (None, 0) and comparable_n >= 3 else None
        if multiple is not None:
            outliers.append({
                "evidence_id": evidence_id,
                "content_id": row["content_id"],
                "creator_id": row["creator_id"],
                "handle": creator_meta[row["creator_id"]]["handle"],
                "format": row["format"],
                "views": values["views"],
                "baseline_median_views": baseline,
                "account_median_multiple": multiple,
                "comparable_n": comparable_n,
                "sample_confidence": sample_confidence(comparable_n),
                "evidence_strength": outlier_evidence_strength(comparable_n),
                "evidence_score": outlier_evidence_score(float(values["views"]), multiple, comparable_n),
                **format_evidence(row),
                "formula_version": "account-format-median-loo.v1" if snapshot.get("platform") == "youtube" else "account-format-median.v1",
            })

    ranked.sort(key=lambda row: (-row["views"], row["published_at"], row["content_id"]))
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    outliers.sort(key=lambda row: (-float(row["evidence_score"]), row["content_id"]))

    focus_summary = None
    if focus_creator_id:
        focus_items = [row for row in items if row["creator_id"] == focus_creator_id]
        timestamps = [parse_time(row["published_at"]) for row in focus_items]
        span_days = max((max(timestamps) - min(timestamps)).total_seconds() / 86400, 1) if len(timestamps) >= 2 else None
        focus_summary = {
            "creator_id": focus_creator_id,
            "handle": creator_meta[focus_creator_id]["handle"],
            "content_count": len(focus_items),
            "format_mix": dict(sorted(Counter(row["format"] for row in focus_items).items())),
            "observed_span_days": round(span_days, 3) if span_days is not None else None,
            "posts_per_week": round(len(focus_items) / span_days * 7, 6) if span_days else None,
            "top_content_ids": [row["content_id"] for row in ranked if row["creator_id"] == focus_creator_id][:10],
        }

    input_sha = digest(snapshot)
    analysis_id = "public-analysis-" + hashlib.sha256(f"{mode}:{focus_creator_id}:{input_sha}".encode()).hexdigest()[:16]
    return {
        "schema_version": "public-content-analysis.v1",
        "analysis_id": analysis_id,
        "mode": mode,
        "snapshot_ref": snapshot["snapshot_id"],
        "rule_version": RULE_VERSION,
        "data_quality": {
            "input_item_count": len(snapshot["items"]),
            "analyzed_item_count": len(items),
            "creator_count": len(creator_ids),
            "items_with_views": sum(metric(row, "views") is not None for row in items),
            "dropped": dropped,
            "coverage_complete": bool(snapshot["source"].get("coverage_complete")),
            "source_mode": snapshot["source"].get("source_mode"),
            "source_row_coverage": snapshot["source"].get("pagination", {}),
        },
        "cohorts": cohorts,
        "ranked_content": ranked,
        "account_outliers": outliers,
        "focus_summary": focus_summary,
        "claim_boundary": {
            "snapshot_count": 1,
            "allowed": ["current_public_performance", "raw_popularity", "account_relative_outlier"],
            "not_allowed": ["growth", "acceleration", "breakout_confirmed", "private_ctr", "retention", "audience_demographics", "conversion"],
        },
        "evidence": evidence,
        "reproducibility": {
            "input_sha256": input_sha,
            "formula_set_version": RULE_VERSION,
            "observed_at": observed.isoformat(),
            "window": {"start": start.isoformat(), "end": end.isoformat()},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--mode", choices=["account", "trend", "competitor"], required=True)
    parser.add_argument("--focus-creator-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        result = analyze(snapshot, args.mode, args.focus_creator_id)
        text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
