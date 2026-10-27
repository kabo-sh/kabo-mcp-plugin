#!/usr/bin/env python3
"""Fail closed when the primary competitor window silently becomes a quarter."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_POLICIES = {"recent_30d", "user_named_span"}
RECENT_MAX_DAYS = 32


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


def normalize_request_platforms(request: dict[str, Any]) -> bool:
    """Rewrite a singular `platform` into `platforms`.

    The request schema requires `platforms`. Agents still write `"platform":
    "instagram"`. Keep that from fail-closing the rest of the run: accept the
    known singular value, write the array, and drop the illegal key. Mixed or
    unknown values still fail.
    """
    platforms = request.get("platforms")
    singular = request.get("platform")
    if isinstance(platforms, list) and platforms:
        if singular is not None:
            raise ValueError(
                'request must use "platforms": ["instagram"] or ["youtube"]; '
                "do not also send singular platform"
            )
        return False
    if isinstance(singular, str) and singular.strip().casefold() in {"instagram", "youtube"}:
        request["platforms"] = [singular.strip().casefold()]
        del request["platform"]
        return True
    raise ValueError('request must include "platforms": ["instagram"] or ["youtube"]')


def ensure_request_id(request: dict[str, Any], path: Path) -> bool:
    """Fill a missing request_id from the reserved run, then fail closed.

    Agents omit `request_id` on the frozen request. A run manifest beside it may already
    own one; copy that id when present; do not invent a slug.
    """
    current = request.get("request_id")
    if isinstance(current, str) and current.strip():
        return False
    for folder in (path.parent, path.parent.parent):
        manifest_path = folder / "run-manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(manifest, dict):
            continue
        mid = manifest.get("request_id") or manifest.get("run_id")
        if isinstance(mid, str) and mid.strip():
            request["request_id"] = mid.strip()
            return True
    raise ValueError(
        'request must include a non-empty "request_id"; '
        "drive.py discover fills it with the run id; do not invent a slug"
    )


def validate(request: dict[str, Any]) -> None:
    if request.get("schema_version") != "competitor-research-request.v3":
        raise ValueError("schema_version must be competitor-research-request.v3")
    normalize_request_platforms(request)
    policy = request.get("window_policy") or "recent_30d"
    if policy not in ALLOWED_POLICIES:
        raise ValueError(
            "window_policy must be recent_30d or user_named_span; "
            "omit it only when the primary window is the last 30 days"
        )
    days = window_days(request)
    if policy == "recent_30d" and days > RECENT_MAX_DAYS:
        raise ValueError(
            "primary window exceeds 32 days; freeze the last 30 days unless the "
            "user named a longer span and window_policy is user_named_span"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        request = load(args.request)
        rewritten = normalize_request_platforms(request)
        filled_id = ensure_request_id(request, args.request)
        validate(request)
        if rewritten or filled_id:
            args.request.write_text(
                json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
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
