"""Current account counts and historical inputs are distinct evidence scopes."""

from __future__ import annotations

import math
from typing import Any

METRICS = ("current_followers", "follower_history", "view_history")
METRIC_GAP_LABELS = {
    "current_followers": "This review input does not include the current follower/subscriber count; this does not establish that the platform lacks it.",
    "follower_history": "Historical follower/subscriber observations were not included, so recent subscriber growth cannot be verified.",
    "view_history": "Repeated view observations for the same videos were not included; current cumulative views cannot establish recent view growth.",
}


def baseline_availability(analysis: dict[str, Any] | None) -> dict[str, Any]:
    scope = (analysis or {}).get("scope") or {}
    value = scope.get("followers") if isinstance(scope, dict) else None
    available = (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value)) and value >= 0
    )
    return {
        "current_followers": {
            "status": "available" if available else "not_carried",
            "value": value if available else None,
            "source": "account_analysis.scope.followers" if available else None,
        },
        # A dated upload catalog contains current cumulative views. Its publication
        # dates are not repeated account-count or same-video view observations.
        "follower_history": {"status": "not_carried"},
        "view_history": {"status": "not_carried"},
    }


def validate_baseline_input(synthesis: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any] | None:
    if source is None or "baseline_availability" not in source:
        return None
    if source.get("analysis_id") != synthesis.get("analysis_id"):
        raise ValueError("synthesis input analysis_id does not match synthesis")
    availability = source["baseline_availability"]
    if not isinstance(availability, dict) or set(availability) != set(METRICS):
        raise ValueError("baseline_availability must identify current and historical inputs separately")
    for metric in METRICS:
        row = availability[metric]
        if not isinstance(row, dict) or row.get("status") not in {"available", "not_carried"}:
            raise ValueError(f"invalid baseline availability for {metric}")
        if metric == "current_followers":
            if set(row) != {"status", "value", "source"}:
                raise ValueError("current follower availability must carry its value and source")
            if row["status"] == "available":
                value = row.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                    raise ValueError("available current follower count needs a finite nonnegative value")
                if row["source"] != "account_analysis.scope.followers":
                    raise ValueError("current follower count must come from the bound standard analysis")
            elif row["value"] is not None or row["source"] is not None:
                raise ValueError("not_carried current follower input must not invent a value or source")
        elif set(row) != {"status"} or row["status"] != "not_carried":
            raise ValueError("a catalog does not establish historical account observations")
    return availability


def data_gap_lines(synthesis: dict[str, Any], source: dict[str, Any] | None) -> list[str]:
    availability = validate_baseline_input(synthesis, source)
    lines: list[str] = []
    for row in synthesis.get("data_gaps") or []:
        if isinstance(row, str):
            if availability is not None:
                raise ValueError("with baseline_availability, use a metric/availability gap or a detail object; do not infer platform absence from missing input")
            if row.strip():
                lines.append(row)
            continue
        if not isinstance(row, dict):
            raise ValueError("data gap must be text or a structured gap")
        if set(row) == {"detail"} and isinstance(row["detail"], str) and row["detail"].strip():
            lines.append(row["detail"])
            continue
        metric = row.get("metric")
        if set(row) != {"metric", "availability"} or metric not in METRICS or row.get("availability") != "not_carried":
            raise ValueError("metric data gap must name a supported metric with not_carried availability")
        if availability is None:
            raise ValueError("metric data gaps require the matching synthesis input")
        if availability[metric]["status"] != row["availability"]:
            raise ValueError(f"data gap contradicts available input for {metric}")
        labels = (synthesis.get("presentation") or {}).get("metric_gap_labels", {})
        if metric in labels:
            lines.append(labels[metric])
        elif synthesis.get("output_language", "en") == "en":
            lines.append(METRIC_GAP_LABELS[metric])
        else:
            raise ValueError(f"presentation.metric_gap_labels missing used key {metric!r}")
    return lines
