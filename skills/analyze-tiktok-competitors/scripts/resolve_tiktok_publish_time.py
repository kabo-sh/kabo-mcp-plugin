#!/usr/bin/env python3
"""Map a competitor request window onto the TikTok search_videos publish_time enum.

The catalog accepts only 0|1|7|30|90|180 (days). Agents were sending ISO dates
or the word "window" because SKILL said "narrowest supported publish_time
window". This script prints the integer to copy into every search_videos call.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sampling_policy import policy

PUBLISH_TIME_DAYS = (0, 1, 7, 30, 90, 180)


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


def resolve_publish_time(request: dict[str, Any]) -> int:
    if policy(request):
        return 0
    date_policy = request.get("window_policy") or "recent_30d"
    if date_policy == "recent_30d":
        return 30
    days = window_days(request)
    for value in PUBLISH_TIME_DAYS:
        if value >= days:
            return value
    return 180


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        request = load(args.request)
        publish_time = resolve_publish_time(request)
        print(json.dumps({"publish_time": publish_time}))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
