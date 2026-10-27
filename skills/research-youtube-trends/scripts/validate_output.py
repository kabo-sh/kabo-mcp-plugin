#!/usr/bin/env python3
"""Dependency-free semantic validator for TrendResearchReport V3."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


REQUIRED = {
    "schema_version", "report_id", "request_id", "status", "scope", "coverage",
    "overview", "top_content", "patterns", "emerging_creators", "data_gaps",
}
SEMANTIC = {
    "pattern", "mechanism", "audience_problem", "content_promise", "angle",
    "why_now", "creator_fit", "differentiation",
}
PRIVATE_KEYS = {"ctr", "retention", "rpm", "revenue", "traffic_source", "impressions"}
MIN_ABSOLUTE_HEAT_POPULATION = 4


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(
    report: dict[str, Any],
    request: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - report.keys())
    if missing:
        return [f"missing top-level fields: {', '.join(missing)}"]
    if report.get("schema_version") != "trend-research-report.v3":
        errors.append("schema_version must be trend-research-report.v3")
    if report.get("status") not in {"complete", "partial", "blocked"}:
        errors.append("status must be complete, partial, or blocked")
    scope, coverage = report.get("scope", {}), report.get("coverage", {})
    if request:
        if request.get("schema_version") != "trend-research-request.v3":
            errors.append("request schema_version must be trend-research-request.v3")
        if report.get("request_id") != request.get("request_id"):
            errors.append("report request_id does not match request")
        for key in ("niche", "platforms", "window", "locale", "formats"):
            if scope.get(key) != request.get(key):
                errors.append(f"scope.{key} does not match request.{key}")
    if report.get("status") == "complete" and coverage.get("coverage_complete") is False:
        errors.append("status cannot be complete when coverage_complete is false")
    snapshot_count = scope.get("snapshot_count")
    if not isinstance(snapshot_count, int) or snapshot_count < 1:
        errors.append("scope.snapshot_count must be an integer >= 1")

    content_ids, ranks = set(), set()
    content_by_id: dict[str, dict[str, Any]] = {}
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
        if isinstance(content_id, str):
            content_by_id[content_id] = item
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{path}.url must be an HTTP URL")
        metrics = item.get("metrics") or {}
        leaked = PRIVATE_KEYS & {str(key).lower() for key in metrics}
        if scope.get("source_mode") != "fixture" and leaked:
            errors.append(f"{path}.metrics contains unsupported public fields: {sorted(leaked)}")
        baseline, multiple = item.get("baseline"), item.get("outlier_multiple")
        if multiple is not None:
            if not isinstance(baseline, dict) or baseline.get("sample_size", 0) < 5 or baseline.get("value", 0) <= 0:
                errors.append(f"{path}.outlier_multiple requires a positive baseline with sample_size >= 5")
            else:
                metric_value = metrics.get(baseline.get("metric"))
                if not isinstance(metric_value, (int, float)) or not math.isclose(metric_value / baseline["value"], multiple, rel_tol=0.005, abs_tol=0.01):
                    errors.append(f"{path}.outlier_multiple is not metric / baseline.value")
    if ranks and ranks != set(range(1, len(ranks) + 1)):
        errors.append("top_content ranks must be contiguous from 1 in report reading order")

    candidate_ids: set[str] | None = None
    analysis_rank_by_id: dict[str, int] = {}
    ranked_population = 0
    if analysis is not None:
        analysis_ranking = analysis.get("ranked_content") or []
        if isinstance(analysis_ranking, list):
            ranked_population = len(analysis_ranking)
            analysis_rank_by_id = {
                str(item["content_id"]): int(item["rank"])
                for item in analysis_ranking
                if isinstance(item, dict)
                and isinstance(item.get("content_id"), str)
                and isinstance(item.get("rank"), int)
                and item["rank"] > 0
            }
        relevance = analysis.get("relevance")
        if not isinstance(relevance, dict):
            errors.append("analysis.relevance is required for Trend evidence validation")
        else:
            candidate_ids = (
                set(relevance.get("direct_content_ids") or [])
                if relevance.get("method") == "semantic-eligibility.v1"
                else set(relevance.get("candidate_content_ids") or [])
            )
            if not candidate_ids and relevance.get("method") != "semantic-eligibility.v1":
                candidate_ids = set(relevance.get("direct_content_ids") or []) | set(relevance.get("adjacent_content_ids") or [])
            unresolved_top = sorted(content_ids - candidate_ids)
            if unresolved_top:
                errors.append(f"top_content contains non-candidate niche evidence: {unresolved_top}")
            if coverage.get("eligible_count") != len(candidate_ids):
                errors.append("coverage.eligible_count must equal analysis candidate-content count")
            analyzed_count = analysis.get("data_quality", {}).get("analyzed_item_count")
            if coverage.get("raw_count") != analyzed_count:
                errors.append("coverage.raw_count must equal analysis analyzed-item count")
            if report.get("status") == "complete" and not content_ids:
                errors.append("status cannot be complete with no selected niche evidence")

    for index, pattern in enumerate(report.get("patterns") or []):
        path = f"patterns[{index}]"
        if not isinstance(pattern, dict):
            errors.append(f"{path} must be an object")
            continue
        for field in SEMANTIC:
            if not nonempty(pattern.get(field)):
                errors.append(f"{path}.{field} must be non-empty")
        refs = pattern.get("content_refs") or []
        unresolved = sorted(set(refs) - content_ids)
        if unresolved:
            errors.append(f"{path}.content_refs are unresolved: {unresolved}")
        if candidate_ids is not None:
            indirect = sorted(set(refs) - candidate_ids)
            if indirect:
                errors.append(f"{path}.content_refs contain non-candidate niche evidence: {indirect}")
        if pattern.get("stage") in {"recurring_pattern", "rising", "falling"} and len(set(refs)) < 2:
            errors.append(f"{path} requires at least two distinct content refs")
        if pattern.get("stage") in {"rising", "falling"} and (not isinstance(snapshot_count, int) or snapshot_count < 2):
            errors.append(f"{path} claims momentum with fewer than two snapshots")
        has_supported_outlier = any(
            isinstance(content_by_id.get(str(ref), {}).get("outlier_multiple"), (int, float))
            and not isinstance(content_by_id.get(str(ref), {}).get("outlier_multiple"), bool)
            and content_by_id[str(ref)]["outlier_multiple"] >= 1.5
            for ref in refs
        )
        # Performance claims are carried by structure, not by wording in any language:
        # `current_high_performance` needs a reliable account-relative outlier or a top-quartile
        # absolute public metric among the cited refs, and the proof shown to the Creator is the
        # Composer's `proof_points`, written from those same metrics.
        absolute_rank_cutoff = max(1, math.ceil(ranked_population * 0.25))
        has_strong_absolute_heat = ranked_population >= MIN_ABSOLUTE_HEAT_POPULATION and any(
            analysis_rank_by_id.get(str(ref), ranked_population + 1) <= absolute_rank_cutoff
            and any(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > 0
                for value in (content_by_id[str(ref)].get("metrics") or {}).values()
            )
            for ref in refs
        )
        if (
            pattern.get("stage") == "current_high_performance"
            and not has_supported_outlier
            and not has_strong_absolute_heat
        ):
            errors.append(
                f"{path}.stage requires a cited >= 1.5x outlier or top-quartile absolute public metric "
                "for current_high_performance"
            )
        if not pattern.get("recommended_formats") or not pattern.get("proof_points"):
            errors.append(f"{path} requires recommended_formats and proof_points")

    for index, creator in enumerate(report.get("emerging_creators") or []):
        refs = set(creator.get("content_refs") or []) if isinstance(creator, dict) else set()
        if refs - content_ids:
            errors.append(f"emerging_creators[{index}] contains unresolved content refs")
        has_supported_outlier = any(
            isinstance(content_by_id.get(str(ref), {}).get("outlier_multiple"), (int, float))
            and not isinstance(content_by_id.get(str(ref), {}).get("outlier_multiple"), bool)
            and content_by_id[str(ref)]["outlier_multiple"] >= 1.5
            for ref in refs
        )
        if isinstance(creator, dict) and creator.get("status") in {"small_account_outlier", "breakout_confirmed"} and not has_supported_outlier:
            errors.append(f"emerging_creators[{index}].status requires cited >= 1.5x evidence")
        if isinstance(creator, dict) and creator.get("status") == "breakout_confirmed" and (not isinstance(snapshot_count, int) or snapshot_count < 2):
            errors.append(f"emerging_creators[{index}] confirms breakout with fewer than two snapshots")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--analysis", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(
            load(args.report),
            load(args.request) if args.request else None,
            load(args.analysis) if args.analysis else None,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        errors = [str(error)]
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
