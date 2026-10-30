#!/usr/bin/env python3
"""Build a strict, canonical TikTok trend candidate set from Connector Envelopes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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
    if "runs" in value:
        if not isinstance(runs, dict) or not runs or any(not isinstance(row, dict) for row in runs.values()):
            raise ValueError("envelope runs must be a non-empty object of Envelopes")
        return list(runs.items())
    if "status" not in value and "data" not in value:
        direct = [(str(name), row) for name, row in value.items() if isinstance(row, dict)]
        if direct and all("status" in row or "data" in row for _, row in direct):
            return direct
    return [("input", value)]


def source_of(name: str, envelope: dict[str, Any], call: dict[str, Any]) -> tuple[str, str]:
    """Bind each unchanged response to actual request arguments, never its filename."""
    if not isinstance(call, dict) or call.get("connector_id") != "tiktok-discovery":
        raise ValueError(f"{name} requires tiktok-discovery request provenance")
    request_id = call.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or request_id != envelope.get("request_id"):
        raise ValueError(f"{name} missing or mismatched request_id")
    operation = call.get("operation")
    if operation != envelope.get("operation"):
        raise ValueError(f"{name} request/response operation mismatch")
    if envelope.get("connector_id", "tiktok-discovery") != "tiktok-discovery":
        raise ValueError(f"{name} response connector mismatch")
    params = call.get("params")
    if not isinstance(params, dict):
        raise ValueError(f"{name} request params must be an object")
    data = envelope.get("data")
    if data is not None and not isinstance(data, dict):
        raise ValueError(f"{name} response data must be an object or null")
    returned_query = (data or {}).get("query")
    if operation == "list_top_contents":
        if "query" in params or "keyword" in params or "sort_type" in params or returned_query not in (None, ""):
            raise ValueError(f"{name} ranked board cannot carry a search query or sort")
        return "ranked_board", ""
    if operation != "search_videos":
        raise ValueError(f"{name} unsupported discovery operation: {operation}")
    sort_type = params.get("sort_type")
    if type(sort_type) is not int or sort_type not in (0, 1):
        raise ValueError(f"{name} requires explicit sort_type 0 or 1")
    query = params.get("keyword")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"{name} requires the actual non-empty search query")
    if returned_query is not None and returned_query != query:
        raise ValueError(f"{name} request/response query mismatch")
    return ("relevance" if sort_type == 0 else "most_liked"), query


def validate_scope(request: dict[str, Any], runs: list[tuple[str, dict[str, Any]]], calls: dict[str, Any]) -> None:
    """Check declared collection scope and receipt-bound board fallback, without using today's clock."""
    region = request.get("locale", {}).get("region")
    # The Request schema allows an unknown region. Then no call can conflict with the Request, but
    # every search and board must still share one region so the candidate set has a single scope.
    if not isinstance(region, str) or not region.strip():
        region = None
    used: set[Any] = set()
    since, until = (parse_time(request["window"][key]) for key in ("since", "until"))
    boards = []
    for name, envelope in runs:
        call = calls[name]
        params = call["params"]
        observed = None
        if isinstance(envelope.get("retrieved_at"), str):
            observed = parse_time(envelope["retrieved_at"])
        elif envelope.get("status") == "completed":
            raise ValueError(f"{name} requires the actual receipt timestamp")
        # A failed or unsupported route returned no rows, and the connector does not stamp a
        # receipt time on it (observed 2026-09-17: HTTP 400 on one of four searches). There is
        # nothing to date, so skip the receipt checks below and keep the route as failed evidence
        # instead of rejecting the whole collection.
        if call["operation"] == "search_videos":
            # Search uses region; the board uses country_code. They are different API fields.
            if (region is not None and params.get("region") != region) or "country_code" in params:
                raise ValueError(f"{name} search region conflicts with the Request")
            used.add(params.get("region"))
            if type(params.get("count")) is not int or params["count"] != 30:
                raise ValueError(f"{name} search count must be 30")
            days = params.get("publish_time")
            if type(days) is not int or days not in (1, 7, 30, 90, 180) or until - since > timedelta(days=days):
                raise ValueError(f"{name} publish_time does not cover the requested duration")
            # The API exposes whole-day buckets, not the exact provider cutoff.
            # Do not turn transport seconds into a false rejection of a 30-day request.
            if observed is not None and (since.date() < observed.date() - timedelta(days=days) or until > observed):
                raise ValueError(f"{name} requested dates are outside the declared publish_time bucket")
        else:
            if (region is not None and params.get("country_code") != region) or "region" in params:
                raise ValueError(f"{name} board country_code conflicts with the Request")
            used.add(params.get("country_code"))
            stamp = params.get("period_end_timestamp")
            if type(stamp) is not int or not 0 <= stamp <= 253402300799:
                raise ValueError(f"{name} board date must be an integer UTC timestamp")
            if observed is not None:
                boards.append((name, envelope, observed, datetime.fromtimestamp(stamp, timezone.utc).date()))
    if region is None and len(used) > 1:
        raise ValueError("searches and boards used different regions while the Request region is unknown")
    if not boards:
        return
    # Receipt chronology, not object-key/filename order, proves which response came first.
    boards.sort(key=lambda row: row[2])
    first = boards[0]
    day = first[2].date()
    if len(boards) > 2 or first[3] != day - timedelta(days=1):
        raise ValueError("ranked board must start at D-1 and have at most one D-2 fallback")
    if len(boards) == 2:
        second = boards[1]
        if (second[3] != day - timedelta(days=2) or second[2] <= first[2]
                or first[1].get("status") != "completed" or (first[1].get("data") or {}).get("items") != []):
            raise ValueError("D-2 fallback requires a prior completed, empty D-1 board")


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def signal_fields(signals: dict[str, Any]) -> dict[str, Any]:
    """The item fields a search row's `content_signals` carries, for eligibility and the Gate summary.

    The row has them only when the search asked with `include: ["content_signals"]`, which the
    driver does only when the Creator's account profile is attached; a row without them gets none of
    these keys, so the candidate set and its `candidate_set_id` are what they were before. Each field
    the platform did not return is null, never a guess: a missing duration is not a photo post, a
    missing ad flag is not "no ad".
    """
    hashtags = signals.get("hashtags")
    duration_ms = signals.get("duration_ms")
    is_ads = signals.get("is_ads")
    suggest = signals.get("suggest_words")
    return {
        "language": _string_or_none(signals.get("desc_language")),
        "hashtags": ([str(tag["name"]) for tag in hashtags if isinstance(tag, dict) and _string_or_none(tag.get("name"))]
                     if isinstance(hashtags, list) else None),
        # The platform counts milliseconds; the eligibility and format rules count seconds.
        "duration_seconds": (duration_ms / 1000 if isinstance(duration_ms, (int, float)) and not isinstance(duration_ms, bool)
                             and duration_ms >= 0 else None),
        "is_ad": is_ads if isinstance(is_ads, bool) else None,
        "sound_id": _string_or_none(signals.get("music_id")),
        # The platform's own text about the video, kept as written. It is not the author's caption,
        # so it never goes where the caption goes.
        "platform_summary_source": {
            "content_desc": _string_or_none(signals.get("content_desc")),
            "suggest_words": ([word for word in suggest if _string_or_none(word)] if isinstance(suggest, list) else None),
        },
    }


def build(request: dict[str, Any], source: dict[str, Any], requests: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != "trend-research-request.v3":
        raise ValueError("request must be trend-research-request.v3")
    if request.get("platforms") != ["tiktok"]:
        raise ValueError("TikTok candidate collection requires platforms=[tiktok]")
    window = request.get("window") or {}
    since, until = parse_time(window["since"]), parse_time(window["until"])
    if since > until:
        raise ValueError("request window is reversed")
    source_runs = envelopes(source)
    calls = requests.get("runs")
    if not isinstance(calls, dict) or set(calls) != {name for name, _ in source_runs}:
        raise ValueError("request provenance must have exactly the same run keys as Envelopes")
    sources = {name: source_of(name, envelope, calls[name]) for name, envelope in source_runs}
    validate_scope(request, source_runs, calls)

    merged: dict[str, dict[str, Any]] = {}
    raw_count = outside_window = failed_routes = 0
    route_status: list[dict[str, Any]] = []
    retrieved: list[str] = []
    provider_calls = 0
    for name, envelope in source_runs:
        route, query = sources[name]
        status = str(envelope.get("status") or "failed")
        items = (envelope.get("data") or {}).get("items", [] if status != "completed" else None)
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
            if not since <= timestamp <= until:
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
            signals = row.get("content_signals")
            if isinstance(signals, dict):
                merged[key].update(signal_fields(signals))
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
        ] if not any(row["route"] == "ranked_board" and row["status"] == "completed" and row["count"] for row in route_status) else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--envelopes", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(load(args.request), load(args.envelopes), load(args.requests))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "items": len(result["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
