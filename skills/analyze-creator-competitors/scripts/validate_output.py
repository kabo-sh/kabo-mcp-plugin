#!/usr/bin/env python3
"""Dependency-free semantic validator for CompetitorResearchReport V3."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


REQUIRED = {
    "schema_version", "report_id", "request_id", "status", "scope", "coverage",
    "overview", "competitors", "top_content", "outliers", "patterns", "gaps", "data_gaps",
}
SEMANTIC = {"pattern", "mechanism", "differentiation"}
# Idea-handoff fields: optional since 0.5.7 (the Creator reply never shows them), but a
# pattern that still carries one must carry a usable value.
OPTIONAL_SEMANTIC = {"audience_problem", "content_promise", "angle", "why_now", "creator_fit"}
PRIVATE_KEYS = {"ctr", "retention", "rpm", "revenue", "traffic_source", "impressions"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_seed_row(item: dict[str, Any], request: dict[str, Any] | None) -> bool:
    """A seed post may appear in top_content without its author joining the roster."""
    if not request or not isinstance(item, dict):
        return False
    subject = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    seed = subject.get("seed_content_ref")
    return isinstance(seed, str) and bool(seed.strip()) and item.get("content_id") == seed.strip()


def validate(report: dict[str, Any], request: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - report.keys())
    if missing:
        return [f"missing top-level fields: {', '.join(missing)}"]
    if report.get("schema_version") != "competitor-research-report.v3":
        errors.append("schema_version must be competitor-research-report.v3")
    if report.get("status") not in {"complete", "partial", "blocked"}:
        errors.append("status must be complete, partial, or blocked")
    scope, coverage = report.get("scope", {}), report.get("coverage", {})
    if request:
        if request.get("schema_version") != "competitor-research-request.v3":
            errors.append("request schema_version must be competitor-research-request.v3")
        if report.get("request_id") != request.get("request_id"):
            errors.append("report request_id does not match request")
        for source_key, report_key in (("subject", "subject"), ("platforms", "platforms"), ("window", "window"), ("locale", "locale"), ("formats", "formats")):
            if scope.get(report_key) != request.get(source_key):
                errors.append(f"scope.{report_key} does not match request.{source_key}")
    if report.get("status") == "complete" and coverage.get("coverage_complete") is False:
        errors.append("status cannot be complete when coverage_complete is false")

    account_refs = set()
    for index, item in enumerate(report.get("competitors") or []):
        path = f"competitors[{index}]"
        ref = item.get("account_ref") if isinstance(item, dict) else None
        if ref in account_refs:
            errors.append(f"duplicate account_ref: {ref}")
        account_refs.add(ref)
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{path}.url must be an HTTP URL")
    if coverage.get("competitor_count") != len(report.get("competitors") or []):
        errors.append("coverage.competitor_count must equal competitors length")

    content_ids, ranks = set(), set()
    for index, item in enumerate(report.get("top_content") or []):
        path = f"top_content[{index}]"
        content_id, rank = item.get("content_id"), item.get("rank")
        if content_id in content_ids:
            errors.append(f"duplicate content_id: {content_id}")
        if rank in ranks:
            errors.append(f"duplicate rank: {rank}")
        content_ids.add(content_id)
        ranks.add(rank)
        if item.get("account_ref") not in account_refs and not is_seed_row(item, request):
            errors.append(f"{path}.account_ref is unresolved")
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{path}.url must be an HTTP URL")
        metrics = item.get("metrics") or {}
        leaked = PRIVATE_KEYS & {str(key).lower() for key in metrics}
        if scope.get("source_mode") != "fixture" and leaked:
            errors.append(f"{path}.metrics contains unsupported public fields: {sorted(leaked)}")

    for index, item in enumerate(report.get("outliers") or []):
        path = f"outliers[{index}]"
        if item.get("content_id") not in content_ids:
            errors.append(f"{path}.content_id is unresolved")
        baseline = item.get("baseline") or {}
        if baseline.get("sample_size", 0) < 3 or baseline.get("value", 0) <= 0:
            errors.append(f"{path}.baseline requires a positive value and sample_size >= 3")
        elif not math.isclose(item.get("value", 0) / baseline["value"], item.get("ratio", -1), rel_tol=0.005, abs_tol=0.01):
            errors.append(f"{path}.ratio is not value / baseline.value")

    for index, pattern in enumerate(report.get("patterns") or []):
        path = f"patterns[{index}]"
        if not isinstance(pattern, dict):
            errors.append(f"{path} must be an object")
            continue
        for field in SEMANTIC:
            if not nonempty(pattern.get(field)):
                errors.append(f"{path}.{field} must be non-empty")
        for field in OPTIONAL_SEMANTIC:
            if field in pattern and not nonempty(pattern.get(field)):
                errors.append(f"{path}.{field} must be non-empty when present")
        if "recommended_formats" in pattern and not pattern.get("recommended_formats"):
            errors.append(f"{path}.recommended_formats must be non-empty when present")
        if len(set(pattern.get("account_refs") or [])) < 2:
            errors.append(f"{path} requires at least two distinct accounts")
        if set(pattern.get("account_refs") or []) - account_refs:
            errors.append(f"{path}.account_refs are unresolved")
        if len(set(pattern.get("content_refs") or [])) < 2:
            errors.append(f"{path} requires at least two distinct content refs")
        if set(pattern.get("content_refs") or []) - content_ids:
            errors.append(f"{path}.content_refs are unresolved")
        if not pattern.get("proof_points"):
            errors.append(f"{path} requires proof_points")

    for index, gap in enumerate(report.get("gaps") or []):
        refs = set(gap.get("content_refs") or []) if isinstance(gap, dict) else set()
        if refs - content_ids:
            errors.append(f"gaps[{index}].content_refs are unresolved")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(load(args.report), load(args.request) if args.request else None)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [str(error)]
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
