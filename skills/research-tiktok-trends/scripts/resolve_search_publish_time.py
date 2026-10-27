#!/usr/bin/env python3
"""Print the TikTok search_videos publish_time that reaches back to the request window's start.

publish_time is an enum of days counted back from the moment of the search, not a date range. The
model used to pick "the narrowest value that does not exclude the window" by hand, and a window that
ended in the past was measured from since to until - a week-old, three-day window got 7 when the
search needed 7 days back from now to reach its start, or 30 once it was older than that.

  python3 scripts/resolve_search_publish_time.py --request trend-research-request.json

Prints {"publish_time": N, "reaches_since": true|false}. Past 180 days no value reaches the window;
the widest is returned and reaches_since is false, which the report states as incomplete coverage.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PUBLISH_TIME_DAYS = (1, 7, 30, 90, 180)


def instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must carry its offset")
    return parsed.astimezone(timezone.utc)


def resolve(request: dict[str, Any], now: datetime) -> dict[str, Any]:
    window = request.get("window")
    if not isinstance(window, dict):
        raise ValueError("the request has no window object")
    since = instant(window.get("since"), "window.since")
    instant(window.get("until"), "window.until")
    if since > now:
        raise ValueError("window.since is in the future")
    days = math.ceil((now - since).total_seconds() / 86400)
    for value in PUBLISH_TIME_DAYS:
        if value >= days:
            return {"publish_time": value, "reaches_since": True, "days_back": days}
    return {"publish_time": PUBLISH_TIME_DAYS[-1], "reaches_since": False, "days_back": days}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--now", help="the search time, ISO-8601 with offset (default: now, UTC)")
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError(f"{args.request} must hold the request object")
        now = instant(args.now, "--now") if args.now else datetime.now(timezone.utc)
        print(json.dumps(resolve(request, now)))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
