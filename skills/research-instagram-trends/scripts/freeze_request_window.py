#!/usr/bin/env python3
"""Freeze the Request window from the ask's time wording, the same way on every trend channel.

The model only classifies the ask; this script owns the dates. Three policies:

  user_named_span  the user named a span or dates in any language ("the past 7 days", "this month", "2026-03 to 2026-05"):
                   pass it as --since/--until and it is kept exactly.
  recent_90d       the user said now / recently / lately, in any language, without a number:
                   the last 90 days.
  default_1y       the ask names no time at all (a niche scan, "find hot videos like this one"):
                   the last year, so the scan reaches as many strong posts as the channel can.
                   TikTok search reaches back at most 180 days with a date filter, so TikTok
                   freezes 180 days here instead of 365.

TikTok's date filter is a bucket of days counted back from the moment of the search, so on TikTok a
derived window starts at a UTC midnight two days inside its bucket (178 or 88 days before today):
even a search that runs after the next midnight still reaches its start with the 180- or 90-day
bucket, and the candidate builder's whole-day check still passes. A named span that ends in
the future is cut at now; one that starts before a channel can reach back is kept, and the script
says so with `reaches_since: false` so the report states the coverage as incomplete.

A past-24-hour ask never reaches this script: it has its own two-layer shortcut on every channel.

  python3 scripts/freeze_request_window.py --request trend-research-request.json --policy default_1y
  python3 scripts/freeze_request_window.py --request trend-research-request.json \
      --policy user_named_span --since 2026-09-01T00:00:00Z --until 2026-09-08T00:00:00Z

Writes `window` into the Request in place (and `window_policy` on the channels whose Request schema
carries it; the Instagram Request is shared with other packages and has no such field) and prints
the frozen window. For Instagram it also prints the discovery lanes the window calls for and the
collector bucket for each: one lane over the narrowest bucket that reaches back to the window's
start, or, for a window of a year or more, the relevance lane over `last-month` plus the reach lane
over `last-year` when the window also ends within the last month. Instagram discovery reaches back
one year at most, so a named span that ended longer ago than that fails here, before any
collection is spent on it. Standard library only; the same bytes ship in every trend channel.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

POLICIES = ("user_named_span", "recent_90d", "default_1y")
DEFAULT_DAYS = {"tiktok": 180, "instagram": 365, "youtube": 365}
RECENT_DAYS = 90
RECORDS_POLICY = {"tiktok", "youtube"}
INSTAGRAM_BUCKETS = (("last-day", 1), ("last-week", 7), ("last-month", 30), ("last-year", 365))
INSTAGRAM_REACH_DAYS = 365
TWO_LANE_RECENT_END_DAYS = 30


def instant(value: str, field: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must carry its UTC offset")
    return parsed.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def platform_of(request: dict[str, Any]) -> str:
    platforms = request.get("platforms")
    if not isinstance(platforms, list) or len(platforms) != 1 or platforms[0] not in DEFAULT_DAYS:
        raise ValueError("the Request must name exactly one of instagram, youtube or tiktok in platforms")
    return platforms[0]


def freeze(request: dict[str, Any], policy: str, now: datetime,
           since: str | None = None, until: str | None = None) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {', '.join(POLICIES)}")
    platform = platform_of(request)
    clamped = False
    if policy == "user_named_span":
        if not since or not until:
            raise ValueError("user_named_span needs the span the user named as --since and --until")
        start, end = instant(since, "--since"), instant(until, "--until")
        if start >= end:
            raise ValueError("the window must start before it ends")
        if start > now:
            raise ValueError("the window starts in the future")
        if end > now:
            end, clamped = now, True
    else:
        if since or until:
            raise ValueError(f"{policy} derives its own dates; pass --since/--until only for user_named_span")
        span = DEFAULT_DAYS[platform] if policy == "default_1y" else RECENT_DAYS
        end = now
        if platform == "tiktok":
            start = datetime.combine(now.date() - timedelta(days=span - 2), time.min, tzinfo=timezone.utc)
        else:
            start = end - timedelta(days=span)
    request["window"] = {"since": stamp(start), "until": stamp(end)}
    if platform in RECORDS_POLICY:
        request["window_policy"] = policy
    days = (end - start).total_seconds() / 86400
    result: dict[str, Any] = {
        "platform": platform,
        "window_policy": policy,
        "window": request["window"],
        "window_days": round(days, 4),
    }
    if clamped:
        result["until_clamped_to_now"] = True
    if platform == "instagram":
        reach_back = (now - start).total_seconds() / 86400
        ended_ago = (now - end).total_seconds() / 86400
        if ended_ago > INSTAGRAM_REACH_DAYS:
            raise ValueError("Instagram discovery reaches back one year at most; this span ended before that")
        if days >= INSTAGRAM_REACH_DAYS and ended_ago <= TWO_LANE_RECENT_END_DAYS:
            result["instagram_lanes"] = [
                {"lane": "relevance", "discovery_window": "last-month"},
                {"lane": "reach", "discovery_window": "last-year"},
            ]
        else:
            bucket = next((name for name, size in INSTAGRAM_BUCKETS if size >= reach_back), "last-year")
            result["instagram_lanes"] = [{"lane": "relevance", "discovery_window": bucket}]
        result["reaches_since"] = reach_back <= INSTAGRAM_REACH_DAYS
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--policy", required=True, choices=POLICIES)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--now", help="ISO-8601 with offset (default: now, UTC)")
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError(f"{args.request} must hold the Request object")
        now = instant(args.now, "--now") if args.now else datetime.now(timezone.utc)
        result = freeze(request, args.policy, now, args.since, args.until)
        args.request.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
