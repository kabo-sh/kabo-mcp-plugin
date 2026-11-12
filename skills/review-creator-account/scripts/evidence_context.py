"""Project existing baseline age rules without changing metrics or rankings."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
from account_analyzers import parse_time


def baseline_maturity_context(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Expose the analyzer's existing per-format minimum-age cutoffs."""
    # Same basis as the Analyzer: the publish day counts as day 1, and must not be read as N full 24-hour
    # periods having elapsed.
    if not analysis["baselines"]:
        return None
    scope = analysis["scope"]
    end = scope.get("window", {}).get("end")
    anchor = parse_time(f"{end}T23:59:59+00:00") if end and "T" not in end else parse_time(end or scope["observed_at"])
    by_format = []
    for baseline in analysis["baselines"]:
        days = baseline["maturity_days"]
        if not isinstance(days, int) or isinstance(days, bool) or days < 1:
            raise ValueError("baseline maturity_days must be a positive integer")
        by_format.append({
            "format": baseline["format"], "maturity_days": days,
            "cutoff_at": (anchor - timedelta(days=days - 1)).isoformat(),
            "minimum_elapsed_days_at_anchor": days - 1,
        })
    return {
        "convention": "publication_day_counts_as_day_one",
        "anchor_source": "scope.window.end" if end else "scope.observed_at",
        "anchor_at": anchor.isoformat(), "comparison": "published_at <= cutoff_at",
        "by_format": by_format,
    }


def maturity_by_format(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index existing age policies by format without choosing a new cohort."""
    context = baseline_maturity_context(analysis)
    return {row["format"]: row for row in context["by_format"]} if context else {}


def content_maturity(published_at: str, policy: dict[str, Any] | None) -> str:
    """Classify the minimum-age eligibility of one published timestamp."""
    if policy is None:
        return "unavailable"
    return "mature" if parse_time(published_at) <= parse_time(policy["cutoff_at"]) else "too_recent"


def evidence_age(row: dict[str, Any], policies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attach source publication time and its applicable baseline age limit."""
    policy = policies.get(row["format"])
    return {
        "published_at": row["published_at"],
        "baseline_maturity": content_maturity(row["published_at"], policy),
        **({"baseline_cutoff_at": policy["cutoff_at"]} if policy else {}),
    }


def public_snapshot_comparison(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Distinguish public cumulative snapshots from equal-length observations; do not infer comparability from the maturity threshold."""
    if not analysis["source_mode"].startswith("public"):
        return None
    return {
        "basis": "cumulative_public_snapshot",
        "equal_observation_windows_verified": False,
        "allowed": ["current_counts", "snapshot_ranks", "wording_observations", "testable_hypotheses"],
        "not_supported": ["age_matched_performance", "content_quality_from_counts", "reach_trend", "sales_attribution"],
        "reason": "Publication dates and minimum-age eligibility do not supply counts measured over equal post-publication windows.",
    }
