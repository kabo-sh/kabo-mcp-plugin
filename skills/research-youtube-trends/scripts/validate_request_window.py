#!/usr/bin/env python3
"""Fail closed when the YouTube trend window does not match the policy it was frozen under.

`scripts/freeze_request_window.py` writes the window and its policy: default_1y (no time named, up to
366 days), recent_90d (now / recently, up to 92 days) or user_named_span (kept as named). An omitted
policy is the legacy recent_30d, which still caps the window at 32 days so an old or hand-written
Request cannot silently widen.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_POLICIES = {"default_1y", "recent_90d", "user_named_span", "recent_30d"}
MAX_DAYS = {"default_1y": 366, "recent_90d": 92, "recent_30d": 32}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def window_days(request: dict[str, Any]) -> float:
    window = request.get("window")
    if not isinstance(window, dict):
        raise ValueError("request window must be an object")
    start = parse_time(window.get("since"), "window.since")
    end = parse_time(window.get("until"), "window.until")
    if end <= start:
        raise ValueError("window.until must be after window.since")
    return (end - start).total_seconds() / 86400


def validate(request: dict[str, Any]) -> None:
    if request.get("schema_version") != "trend-research-request.v3":
        raise ValueError("schema_version must be trend-research-request.v3")
    policy = request.get("window_policy") or "recent_30d"
    if policy not in ALLOWED_POLICIES:
        raise ValueError(
            "window_policy must be default_1y, recent_90d or user_named_span "
            "(let drive.py discover freeze it); an omitted policy is the legacy recent_30d"
        )
    days = window_days(request)
    limit = MAX_DAYS.get(policy)
    if limit is not None and days > limit:
        raise ValueError(
            f"primary window exceeds {limit} days for window_policy {policy}; freeze it with "
            "drive.py discover --policy, or use user_named_span only for a span the user named"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        request = load(args.request)
        validate(request)
        days = window_days(request)
        policy = request.get("window_policy") or "recent_30d"
        print(json.dumps({"valid": True, "window_policy": policy, "window_days": round(days, 4)}))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"valid": False, "error": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
