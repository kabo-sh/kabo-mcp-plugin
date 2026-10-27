#!/usr/bin/env python3
"""Dependency-free semantic validator for CompetitorResearchReport V3."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from evidence_contract import (
    CREATOR_FACING_OUTLIER_MIN_MULTIPLE,
    RELIABLE_OUTLIER_MIN_SAMPLE,
)
from sampling_policy import policy, utc
from project_tiktok_accounts import normalize_ref


REQUIRED = {
    "schema_version", "report_id", "request_id", "status", "scope", "coverage",
    "overview", "competitors", "top_content", "outliers", "patterns", "gaps", "data_gaps",
}
SEMANTIC = {
    "pattern", "mechanism", "audience_problem", "content_promise", "angle",
    "why_now", "creator_fit", "differentiation",
}
PRIVATE_KEYS = {"ctr", "retention", "rpm", "revenue", "traffic_source", "impressions"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
        fields = [("subject", "subject"), ("platforms", "platforms"), ("locale", "locale"), ("formats", "formats")]
        if "sampling" not in request:
            fields.append(("window", "window"))
            if "sampling" in scope or "account_samples" in coverage:
                errors.append("date-window reports cannot add latest-sampling fields")
        for source_key, report_key in fields:
            if scope.get(report_key) != request.get(source_key):
                errors.append(f"scope.{report_key} does not match request.{source_key}")
        if "sampling" in request:
            try:
                sampling = policy(request)
                if scope.get("sampling") != sampling:
                    errors.append("scope.sampling does not match request.sampling")
                samples = coverage.get("account_samples")
                if not isinstance(samples, list):
                    raise ValueError("coverage.account_samples is required for latest sampling")
                handles = [row.get("handle") for row in samples]
                expected = {normalize_ref(ref) for ref in request.get("competitor_refs") or []}
                if len(handles) != len(set(handles)) or set(handles) != expected:
                    errors.append("sampling audit must contain every exact provided handle once")
                windows = []
                for row in samples:
                    counts = [row.get(key) for key in ("raw_count", "selected_count", "analyzed_count")]
                    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in counts[1:]) or (counts[0] is not None and (isinstance(counts[0], bool) or not isinstance(counts[0], int) or counts[0] < 0)):
                        raise ValueError("sampling audit counts must be nonnegative integers")
                    raw, selected, analyzed = counts
                    if raw is None and (selected or analyzed or not row.get("reason")):
                        errors.append("an unretrieved sample must retain unknown raw count and its reason")
                    if row.get("requested_count") != sampling["count"] or not analyzed <= selected <= min(raw or 0, sampling["count"]):
                        errors.append("sampling audit counts do not match the frozen policy")
                    if analyzed < sampling["count"] and not row.get("reason"):
                        errors.append("an insufficient latest sample must retain its reason")
                    window = row.get("window")
                    if analyzed == 0 and window is not None:
                        errors.append("an empty latest sample must not invent publication dates")
                    if analyzed:
                        if not isinstance(window, dict) or utc(window["since"]) > utc(window["until"]) or utc(window["until"]) > utc(sampling["as_of"]):
                            raise ValueError("sampling audit publication dates must be ordered within as_of")
                        windows.append(window)
                actual = ({"since": min(windows, key=lambda w: utc(w["since"]))["since"],
                           "until": max(windows, key=lambda w: utc(w["until"]))["until"]} if windows else None)
                if scope.get("window") != actual:
                    errors.append("scope.window must be the actual latest-sample publication envelope")
                by_handle = {row["handle"]: row for row in samples}
                for competitor in report.get("competitors") or []:
                    if competitor.get("sample_size") != by_handle.get(competitor.get("handle"), {}).get("analyzed_count"):
                        errors.append("competitor sample_size does not match its sampling audit")
            except (ValueError, KeyError, TypeError) as error:
                errors.append(str(error))
    if report.get("status") == "complete" and coverage.get("coverage_complete") is False:
        errors.append("status cannot be complete when coverage_complete is false")

    account_refs = set()
    for index, item in enumerate(report.get("competitors") or []):
        path = f"competitors[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        ref = item.get("account_ref")
        if ref in account_refs:
            errors.append(f"duplicate account_ref: {ref}")
        if not nonempty(ref):
            errors.append(f"{path}.account_ref must be present")
        else:
            account_refs.add(ref)
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{path}.url must be an HTTP URL")
    if coverage.get("competitor_count") != len(report.get("competitors") or []):
        errors.append("coverage.competitor_count must equal competitors length")

    content_ids, ranks = set(), set()
    for index, item in enumerate(report.get("top_content") or []):
        path = f"top_content[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        content_id, rank = item.get("content_id"), item.get("rank")
        if content_id in content_ids:
            errors.append(f"duplicate content_id: {content_id}")
        if rank in ranks:
            errors.append(f"duplicate rank: {rank}")
        content_ids.add(content_id)
        ranks.add(rank)
        if item.get("account_ref") not in account_refs:
            errors.append(f"{path}.account_ref is unresolved")
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{path}.url must be an HTTP URL")
        metrics = item.get("metrics") or {}
        leaked = PRIVATE_KEYS & {str(key).lower() for key in metrics}
        if scope.get("source_mode") != "fixture" and leaked:
            errors.append(f"{path}.metrics contains unsupported public fields: {sorted(leaked)}")

    for index, item in enumerate(report.get("outliers") or []):
        path = f"outliers[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        if item.get("content_id") not in content_ids:
            errors.append(f"{path}.content_id is unresolved")
        baseline = item.get("baseline") or {}
        if not isinstance(baseline, dict):
            errors.append(f"{path}.baseline must be an object")
            continue
        if baseline.get("sample_size", 0) < RELIABLE_OUTLIER_MIN_SAMPLE or baseline.get("value", 0) <= 0:
            errors.append(
                f"{path}.baseline requires a positive value and "
                f"sample_size >= {RELIABLE_OUTLIER_MIN_SAMPLE}"
            )
        elif item.get("ratio", -1) < CREATOR_FACING_OUTLIER_MIN_MULTIPLE:
            errors.append(
                f"{path}.ratio must be >= {CREATOR_FACING_OUTLIER_MIN_MULTIPLE}"
            )
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
        if len(set(pattern.get("account_refs") or [])) < 2:
            errors.append(f"{path} requires at least two distinct accounts")
        if set(pattern.get("account_refs") or []) - account_refs:
            errors.append(f"{path}.account_refs are unresolved")
        if len(set(pattern.get("content_refs") or [])) < 2:
            errors.append(f"{path} requires at least two distinct content refs")
        if set(pattern.get("content_refs") or []) - content_ids:
            errors.append(f"{path}.content_refs are unresolved")
        if not pattern.get("recommended_formats") or not pattern.get("proof_points"):
            errors.append(f"{path} requires recommended_formats and proof_points")

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
