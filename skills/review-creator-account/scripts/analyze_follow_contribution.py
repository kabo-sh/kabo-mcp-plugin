#!/usr/bin/env python3
"""Rank owner-supplied content by follower contribution without filling missing metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "owner-follow-contribution.v1"
AVAILABLE = {"available", "zero"}
METRICS = ("follows", "views", "reach")


def parse_time(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_number(value: Any, label: str) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative number or blank")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a non-negative number or blank") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a non-negative number or blank")
    return int(number) if number.is_integer() else number


def metric_value(value: Any, label: str) -> float | int | None:
    if isinstance(value, dict):
        if value.get("status") not in AVAILABLE:
            return None
        return parse_number(value.get("value"), label)
    return parse_number(value, label)


def canonical_row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"rows[{index}] must be an object")
    content_id = str(raw.get("content_id") or raw.get("post_id") or "").strip()
    if not content_id:
        raise ValueError(f"rows[{index}].content_id is required")
    published_at = str(raw.get("published_at") or raw.get("timestamp") or "").strip()
    if not published_at:
        raise ValueError(f"rows[{index}].published_at is required")
    parse_time(published_at)
    metrics = raw.get("metrics") or raw.get("owner_metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError(f"rows[{index}].metrics must be an object")
    result = {
        "content_id": content_id,
        "title": str(raw.get("title") or raw.get("caption") or content_id).strip() or content_id,
        "url": str(raw.get("url") or raw.get("permalink") or "").strip() or None,
        "published_at": parse_time(published_at).isoformat().replace("+00:00", "Z"),
        "format": str(raw.get("format") or raw.get("media_product_type") or raw.get("media_type") or "unknown").strip() or "unknown",
        "group": str(raw.get("group") or raw.get("pillar") or "").strip() or None,
        "metrics": {},
    }
    for metric in METRICS:
        source = metrics.get(metric, raw.get(metric))
        value = metric_value(source, f"rows[{index}].{metric}")
        # Normalized owner exports can store observed views in public_metrics.
        # Keep owner zero authoritative, and never infer private Follows/reach
        # from public fields or fetch another source to fill a supplied export.
        if value is None and metric == "views":
            public_metrics = raw.get("public_metrics") or {}
            if not isinstance(public_metrics, dict):
                raise ValueError(f"rows[{index}].public_metrics must be an object")
            value = metric_value(public_metrics.get("views"), f"rows[{index}].public_metrics.views")
        if value is not None:
            result["metrics"][metric] = value
    return result


def load_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("CSV requires a header row")
            rows = []
            for index, source in enumerate(reader, 1):
                raw = {
                    str(name).strip().casefold().replace(" ", "_"): value
                    for name, value in source.items()
                }
                rows.append(canonical_row(raw, index))
        return rows, None

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    if value.get("schema_version") == "owner-follow-input.v1":
        raw_rows = value.get("rows")
        scope = value.get("scope") if isinstance(value.get("scope"), dict) else None
    elif value.get("schema_version") == "normalized-social-snapshot.v1":
        raw_rows = value.get("posts")
        scope = value.get("scope") if isinstance(value.get("scope"), dict) else None
    else:
        raise ValueError("input must be owner-follow-input.v1, normalized-social-snapshot.v1, or CSV")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("input requires at least one row")
    return [canonical_row(row, index) for index, row in enumerate(raw_rows, 1)], scope


def metric_state(metrics: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in metrics:
        return {"status": "missing", "value": None}
    value = metrics[name]
    return {"status": "zero" if value == 0 else "available", "value": value}


def efficiency(follows: dict[str, Any], denominator: dict[str, Any]) -> dict[str, Any]:
    if follows["status"] == "missing":
        return {"status": "missing_follows", "value": None}
    if denominator["status"] == "missing":
        return {"status": "missing_denominator", "value": None}
    if denominator["value"] == 0:
        return {"status": "zero_denominator", "value": None}
    return {
        "status": "available",
        "value": round(follows["value"] / denominator["value"] * 1000, 6),
    }


def ranked(rows: list[dict[str, Any]], value_of) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        value = value_of(row)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            scored.append((value, row["content_id"], row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"rank": index, "content_id": row["content_id"], "value": value}
        for index, (value, _content_id, row) in enumerate(scored, 1)
    ]


def aggregate_efficiency(rows: list[dict[str, Any]], denominator: str) -> dict[str, Any]:
    paired = [
        row for row in rows
        if row["follows"]["status"] != "missing" and row[denominator]["status"] != "missing"
    ]
    if not paired:
        return {"status": "missing_paired_rows", "value": None, "paired_n": 0}
    denominator_total = sum(row[denominator]["value"] for row in paired)
    if denominator_total == 0:
        return {"status": "zero_denominator", "value": None, "paired_n": len(paired)}
    follows_total = sum(row["follows"]["value"] for row in paired)
    return {
        "status": "available",
        "value": round(follows_total / denominator_total * 1000, 6),
        "paired_n": len(paired),
    }


def build(
    rows: list[dict[str, Any]],
    *,
    window_start: str | None = None,
    window_end: str | None = None,
) -> dict[str, Any]:
    start = parse_time(window_start) if window_start else None
    end = parse_time(window_end) if window_end else None
    if window_end and len(window_end.strip()) == 10:
        # A calendar date is inclusive of that whole day; an explicit timestamp
        # is an exact boundary and must not be expanded.
        end += timedelta(days=1) - timedelta(microseconds=1)
    if start and end and start > end:
        raise ValueError("window start must not be after window end")
    filtered = []
    seen: set[str] = set()
    for row in rows:
        if row["content_id"] in seen:
            raise ValueError(f"duplicate content_id: {row['content_id']}")
        seen.add(row["content_id"])
        published = parse_time(row["published_at"])
        if start and published < start:
            continue
        if end and published > end:
            continue
        follows = metric_state(row["metrics"], "follows")
        views = metric_state(row["metrics"], "views")
        reach = metric_state(row["metrics"], "reach")
        filtered.append({
            **{key: row[key] for key in ("content_id", "title", "url", "published_at", "format", "group")},
            "follows": follows,
            "views": views,
            "reach": reach,
            "follows_per_1000_views": efficiency(follows, views),
            "follows_per_1000_reach": efficiency(follows, reach),
        })
    if not filtered:
        raise ValueError("no rows fall inside the requested window")

    groups = []
    group_names = sorted({row["group"] for row in filtered if row["group"]})
    for name in group_names:
        members = [row for row in filtered if row["group"] == name]
        follow_values = [row["follows"]["value"] for row in members if row["follows"]["status"] != "missing"]
        groups.append({
            "group": name,
            "sample_size": len(members),
            "follows_available_n": len(follow_values),
            "follows_total": sum(follow_values) if follow_values else None,
            "follows_median": round(statistics.median(follow_values), 6) if follow_values else None,
            "follows_per_1000_views": aggregate_efficiency(members, "views"),
            "follows_per_1000_reach": aggregate_efficiency(members, "reach"),
        })

    follows_available_n = sum(row["follows"]["status"] != "missing" for row in filtered)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if follows_available_n else "insufficient",
        "window": {
            "start": start.isoformat().replace("+00:00", "Z") if start else None,
            "end": end.isoformat().replace("+00:00", "Z") if end else None,
        },
        "coverage": {
            "input_rows": len(rows),
            "in_window_rows": len(filtered),
            "follows_available_n": follows_available_n,
            "views_available_n": sum(row["views"]["status"] != "missing" for row in filtered),
            "reach_available_n": sum(row["reach"]["status"] != "missing" for row in filtered),
        },
        "rows": filtered,
        "rankings": {
            "absolute_follows": ranked(filtered, lambda row: row["follows"]["value"] if row["follows"]["status"] != "missing" else None),
            "follows_per_1000_views": ranked(filtered, lambda row: row["follows_per_1000_views"]["value"]),
            "follows_per_1000_reach": ranked(filtered, lambda row: row["follows_per_1000_reach"]["value"]),
        },
        "groups": groups,
        "claim_boundary": {
            "owner_supplied_rows_only": True,
            "missing_values_are_zero": False,
            "causal_attribution": False,
        },
    }
    return result


def same_result_value(actual: Any, expected: Any) -> bool:
    """Compare JSON values without treating True as the number 1."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isfinite(actual) and math.isfinite(expected) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            same_result_value(actual[key], item) for key, item in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            same_result_value(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def validate_result(value: dict[str, Any]) -> list[str]:
    """Check result coherence against its rows, not external export authenticity."""
    if not isinstance(value, dict):
        return ["result must be an object"]
    errors: list[str] = []
    expected = {
        "schema_version", "status", "window", "coverage", "rows", "rankings",
        "groups", "claim_boundary",
    }
    if set(value) != expected:
        errors.append("top-level fields are invalid")
    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("rows must be a non-empty array")
    window = value.get("window")
    if not isinstance(window, dict) or set(window) != {"start", "end"} or any(
        boundary is not None and not isinstance(boundary, str)
        for boundary in (window or {}).values()
    ):
        errors.append("window requires start and end as strings or null")
    coverage = value.get("coverage")
    coverage_fields = {
        "input_rows", "in_window_rows", "follows_available_n",
        "views_available_n", "reach_available_n",
    }
    if not isinstance(coverage, dict) or set(coverage) != coverage_fields or any(
        isinstance(count, bool) or not isinstance(count, int) or count < 0
        for count in (coverage or {}).values()
    ):
        errors.append("coverage requires non-negative integer counts")
    elif isinstance(rows, list) and coverage["input_rows"] < len(rows):
        errors.append("coverage.input_rows must be at least the number of retained rows")
    if errors:
        return errors

    try:
        canonical = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"rows[{index}] must be an object")
            canonical.append(canonical_row({
                **row,
                "metrics": {name: row.get(name) for name in METRICS},
            }, index))
        rebuilt = build(canonical, window_start=window["start"], window_end=window["end"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return [f"rows or window cannot reconstruct a valid result: {error}"]

    # Filtered-out source rows are unavailable here: validate this reported count
    # structurally, but do not pretend to prove export completeness from it.
    rebuilt["coverage"]["input_rows"] = coverage["input_rows"]
    for field, expected_value in rebuilt.items():
        if not same_result_value(value.get(field), expected_value):
            errors.append(f"{field} does not match the result reconstructed from rows")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows, scope = load_rows(args.input)
        start = args.window_start or (scope or {}).get("since") or (scope or {}).get("window", {}).get("start")
        end = args.window_end or (scope or {}).get("until") or (scope or {}).get("window", {}).get("end")
        result = build(rows, window_start=start, window_end=end)
        errors = validate_result(result)
        if errors:
            raise ValueError("; ".join(errors))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": "ok", "path": str(args.output), "rows": len(result["rows"])}, ensure_ascii=False))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
