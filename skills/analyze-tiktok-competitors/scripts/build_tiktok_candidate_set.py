#!/usr/bin/env python3
"""Build a strict, canonical TikTok trend candidate set from Connector Envelopes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sampling_policy import policy


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def iso(value: str) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def envelopes(value: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    runs = value.get("runs")
    if isinstance(runs, dict):
        return [(str(name), row) for name, row in runs.items() if isinstance(row, dict)]
    if "status" not in value and "data" not in value:
        direct = [(str(name), row) for name, row in value.items() if isinstance(row, dict)]
        if direct and all("status" in row or "data" in row for _, row in direct):
            return direct
    return [("input", value)]


def route_of(name: str, envelope: dict[str, Any]) -> str:
    operation = str(envelope.get("operation") or "")
    if operation == "list_top_contents" or name.startswith("top"):
        return "ranked_board"
    if "liked" in name:
        return "most_liked"
    return "relevance"


def build(request: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") not in {"trend-research-request.v3", "competitor-research-request.v3"}:
        raise ValueError("request must be a Trend or Competitor research request")
    if request.get("platforms") != ["tiktok"]:
        raise ValueError("TikTok candidate collection requires platforms=[tiktok]")
    sampling = policy(request)
    window = ({"until": sampling["as_of"]}
              if sampling else request.get("window") or {})
    since, until = (None if sampling else parse_time(window["since"])), parse_time(window["until"])
    if since is not None and since > until:
        raise ValueError("request window is reversed")

    merged: dict[str, dict[str, Any]] = {}
    raw_count = outside_window = failed_routes = 0
    route_status: list[dict[str, Any]] = []
    retrieved: list[str] = []
    provider_calls = 0
    for name, envelope in envelopes(source):
        route = route_of(name, envelope)
        status = str(envelope.get("status") or "failed")
        items = (envelope.get("data") or {}).get("items") or []
        if not isinstance(items, list):
            raise ValueError(f"{name} items must be an array")
        provider_calls += 1
        if status != "completed":
            failed_routes += 1
        route_status.append({"route": route, "status": status, "count": len(items)})
        if status != "completed":
            continue
        if isinstance(envelope.get("retrieved_at"), str):
            retrieved.append(envelope["retrieved_at"])
        query = str(
            (envelope.get("data") or {}).get("query")
            or request.get("niche")
            or (request.get("subject") or {}).get("description")
            or ""
        )
        for rank, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue
            raw_count += 1
            content_id = str(row.get("content_id") or "")
            url = str(row.get("url") or "")
            published = row.get("published_at")
            if not content_id or not url or not isinstance(published, str):
                raise ValueError(f"{name} row lacks canonical id, URL or published_at")
            timestamp = parse_time(published)
            if timestamp > until or (since is not None and timestamp < since):
                outside_window += 1
                continue
            key = f"tiktok:{content_id}"
            source_ref = {"query": query, "route": route, "rank": rank}
            existing = merged.get(key)
            if existing is not None:
                if source_ref not in existing["sources"]:
                    existing["sources"].append(source_ref)
                continue
            merged[key] = {
                "content_key": key,
                "content_id": content_id,
                "url": url,
                "author": {
                    "id": str(row.get("creator_id") or ""),
                    "handle": str(row.get("creator_handle") or "").lstrip("@"),
                    "full_name": row.get("creator_name"),
                    "followers": row.get("creator_followers"),
                },
                "caption": str(row.get("title") or ""),
                "published_at": iso(published),
                "metrics": {
                    name: row.get(name)
                    for name in ("views", "likes", "comments", "shares")
                },
                "thumbnail_url": row.get("thumbnail_url"),
                "sources": [source_ref],
            }
    items = sorted(merged.values(), key=lambda row: row["content_key"])
    digest = hashlib.sha256(
        json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": "tiktok-trend-candidate-set.v1",
        "candidate_set_id": f"tiktok-candidates-{digest[:16]}",
        "platform": "tiktok",
        "retrieved_at": iso(max(retrieved, key=parse_time) if retrieved else window["until"]),
        "items": items,
        "coverage": {
            "provider_calls": provider_calls,
            "discovery_provider_calls": provider_calls,
            "detail_provider_calls": 0,
            "raw_candidate_count": raw_count,
            "candidate_count": len(items),
            "deduplicated_candidate_count": len(items),
            "duplicate_count": raw_count - outside_window - len(items),
            "outside_window_count": outside_window,
            "failed_route_count": failed_routes,
            "routes": route_status,
        },
        "limitations": [
            "Regional ranked boards were empty; the candidate union uses keyword routes only."
        ] if not any(row["route"] == "ranked_board" and row["count"] for row in route_status) else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--envelopes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(load(args.request), load(args.envelopes))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "items": len(result["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
