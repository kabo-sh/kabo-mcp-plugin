"""Explicit, run-frozen latest-per-account sampling; absent policy preserves date mode."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREEZE_FILE = ".sampling-request.sha256"


def utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("sampling.as_of/publication time must be an ISO timestamp with timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("sampling.as_of/publication time must include timezone")
    return parsed.astimezone(timezone.utc)


def policy(request: dict[str, Any], *, require_as_of: bool = True) -> dict[str, Any] | None:
    if "sampling" not in request:
        return None
    value = request["sampling"]
    if not isinstance(value, dict) or set(value) - {"mode", "count", "as_of"}:
        raise ValueError("sampling must contain only mode, count and as_of")
    if value.get("mode") != "latest_per_account":
        raise ValueError("sampling.mode must be latest_per_account")
    count = value.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError("sampling.count must be an integer from 1 to 100")
    if request.get("discovery_mode") != "provided":
        raise ValueError("latest_per_account sampling requires provided accounts")
    if "window" in request or "window_policy" in request:
        raise ValueError("sampling and a date window are mutually exclusive")
    if require_as_of or "as_of" in value:
        utc(value.get("as_of"))
    return value


def frozen_request(path: Path, *, initialize: bool = False) -> dict[str, Any]:
    """Freeze only explicit latest requests, and refuse later removal or mutation."""
    marker = path.parent / FREEZE_FILE
    if not path.exists() and not marker.exists():
        return {}
    request = json.loads(path.read_text(encoding="utf-8"))
    if "sampling" not in request and not marker.exists():
        return request
    if initialize and not marker.exists():
        selected = policy(request, require_as_of=False)
        if selected is not None and "as_of" not in selected:
            selected["as_of"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    policy(request)
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if marker.exists():
        if marker.read_text().strip() != digest:
            raise ValueError("the frozen sampling request changed; do not reset or replace this run")
    elif initialize:
        marker.write_text(digest + "\n", encoding="utf-8")
    else:
        raise ValueError("sampling request must be frozen by discover before this stage")
    return request


def actual_window(items: list[dict[str, Any]]) -> dict[str, str] | None:
    dates = [utc(item["published_at"]) for item in items]
    if not dates:
        return None
    return {"since": min(dates).isoformat().replace("+00:00", "Z"),
            "until": max(dates).isoformat().replace("+00:00", "Z")}
