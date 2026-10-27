#!/usr/bin/env python3
"""Fill YouTube Search rows with get_video plays. Search has no statistics."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CHUNK_SIZE = 50
WATCH_ID = re.compile(r"(?:v=|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_views(value: Any) -> int | None:
    if type(value) is bool:
        return None
    if type(value) is int:
        return value if value >= 0 else None
    if type(value) is float and value >= 0 and value == int(value):
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.isdigit():
            return int(text)
    return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def nested_payloads(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return found
    found.append(payload)
    structured = payload.get("structuredContent")
    if isinstance(structured, dict):
        found.append(structured)
    for part in payload.get("content") or []:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        found.extend(nested_payloads(parsed))
    return found


def payload_operation(payload: dict[str, Any]) -> str:
    for obj in nested_payloads(payload):
        operation = obj.get("operation")
        if isinstance(operation, str) and operation.strip():
            return operation.strip()
    return ""


def payload_status(payload: dict[str, Any]) -> str:
    for obj in nested_payloads(payload):
        status = obj.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip()
    return ""


def unwrap_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(items: Any) -> None:
        if not isinstance(items, list):
            return
        for row in items:
            if not isinstance(row, dict):
                continue
            marker = id(row)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(row)

    for obj in nested_payloads(payload) if isinstance(payload, dict) else []:
        data = as_record(obj.get("data"))
        add(data.get("rows"))
        add(data.get("items"))
        add(obj.get("rows"))
        add(obj.get("items"))
    return rows


def video_id(row: dict[str, Any]) -> str:
    raw = row.get("id")
    if isinstance(raw, str) and raw.strip() and "youtube#" not in raw:
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("videoId", "video_id"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("video_id", "content_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    url = str(row.get("source_url") or row.get("url") or "")
    match = WATCH_ID.search(url)
    return match.group(1) if match else ""


def row_views(row: dict[str, Any]) -> int | None:
    metrics = as_record(row.get("metrics"))
    for value in (row.get("views"), metrics.get("views"), row.get("play_count")):
        parsed = parse_views(value)
        if parsed is not None:
            return parsed
    return None


def unique_ids(rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        identifier = video_id(row)
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        ids.append(identifier)
    return ids


def chunks_of(ids: list[str], size: int = CHUNK_SIZE) -> list[list[str]]:
    return [ids[index:index + size] for index in range(0, len(ids), size)]


def overlay(search: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(search)
    for key, value in detail.items():
        if value is not None:
            merged[key] = value
    metrics = {**as_record(search.get("metrics")), **as_record(detail.get("metrics"))}
    views = row_views(detail)
    if views is None:
        views = row_views(search)
    if views is not None:
        metrics["views"] = views
        merged["views"] = views
    merged["metrics"] = metrics
    identifier = video_id(merged) or video_id(search) or video_id(detail)
    if identifier:
        merged["id"] = identifier
        merged["video_id"] = identifier
        merged["content_id"] = identifier
    return merged


def classify_file(path: Path) -> tuple[str, list[dict[str, Any]], str]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    operation = payload_operation(payload)
    status = payload_status(payload)
    rows = unwrap_rows(payload)
    if operation == "get_video":
        return "detail", rows, status
    if operation == "search_videos":
        return "search", rows, status
    if any(row_views(row) is not None for row in rows):
        return "detail", rows, status
    return "search", rows, status


def collect(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    search: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for path in paths:
        kind, rows, status = classify_file(path)
        if kind == "detail" and status and status != "completed":
            raise ValueError(f"{path} get_video status is {status}")
        if kind == "detail":
            details.extend(rows)
        else:
            search.extend(rows)
    return search, details


def build_chunks(paths: list[Path]) -> dict[str, Any]:
    search, _details = collect(paths)
    ids = unique_ids(search)
    if not ids:
        raise ValueError("no YouTube video ids in search envelopes")
    return {
        "schema_version": "youtube-video-id-chunks.v1",
        "chunk_size": CHUNK_SIZE,
        "video_ids": ids,
        "chunks": chunks_of(ids),
    }


def detail_calls(paths: list[Path]) -> list[list[dict[str, Any]]]:
    """The rows of each persisted get_video call, one list per Envelope, empty ones included."""
    calls = []
    for path in paths:
        kind, rows, _status = classify_file(path)
        if kind == "detail":
            calls.append(rows)
    return calls


def missing_chunks(chunks: dict[str, Any], calls: list[list[dict[str, Any]]]) -> list[int]:
    """Chunks no persisted get_video call accounts for: calls that were skipped.

    A chunk some of whose ids came back was called. A chunk none of whose ids came back was either
    skipped or called for videos the API no longer returns (all removed or private) - the second
    leaves a completed Envelope with none of the planned ids, so each such call accounts for one
    silent chunk. More silent chunks than silent calls means a call is missing, and its plays would
    quietly fall back to Search heat.
    """
    planned = {identifier for chunk in chunks.get("chunks") or [] for identifier in chunk}
    answered = {video_id(row) for rows in calls for row in rows if video_id(row)}
    unanswered = [index for index, chunk in enumerate(chunks.get("chunks") or [], start=1)
                  if chunk and not answered.intersection(chunk)]
    silent_calls = sum(1 for rows in calls if not planned.intersection(video_id(row) for row in rows))
    return unanswered if len(unanswered) > silent_calls else []


def merge(paths: list[Path], since: str, until: str, chunks: dict[str, Any] | None = None) -> dict[str, Any]:
    search, details = collect(paths)
    search_ids = unique_ids(search)
    if not search_ids:
        raise ValueError("no YouTube video ids in search envelopes")
    if not details:
        raise ValueError("get_video envelopes are required after search; do not rank Search as plays")
    if chunks is not None:
        planned = set(chunks.get("video_ids") or [])
        if planned != set(search_ids):
            raise ValueError("--chunks was built from other search envelopes; rerun ids on these")
        skipped = missing_chunks(chunks, detail_calls(paths))
        if skipped:
            raise ValueError(f"no get_video Envelope answers chunk(s) {skipped}; call and persist them before merging")
    by_id = {video_id(row): dict(row) for row in search if video_id(row)}
    for row in details:
        identifier = video_id(row)
        if not identifier:
            continue
        by_id[identifier] = overlay(by_id.get(identifier, {}), row)
    items = [row for row in by_id.values() if video_id(row)]
    views_filled = sum(1 for row in items if row_views(row) is not None)
    if views_filled == 0:
        raise ValueError("get_video returned no usable public plays; do not render heat as plays")
    return {
        "platform": "youtube",
        "window": {"since": since, "until": until},
        "items": items,
        "coverage": {
            "search_ids": len(search_ids),
            "detail_rows": len(details),
            "merged": len(items),
            "views_filled": views_filled,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    ids_cmd = sub.add_parser("ids")
    ids_cmd.add_argument("envelopes", nargs="+", type=Path)
    ids_cmd.add_argument("--output", type=Path, required=True)
    merge_cmd = sub.add_parser("merge")
    merge_cmd.add_argument("envelopes", nargs="+", type=Path)
    merge_cmd.add_argument("--since", required=True)
    merge_cmd.add_argument("--until", required=True)
    merge_cmd.add_argument("--output", type=Path, required=True)
    merge_cmd.add_argument("--chunks", type=Path, required=True,
                           help="video-id-chunks.json from ids: every chunk must have its get_video Envelope")
    args = parser.parse_args()
    try:
        if args.command == "ids":
            result = build_chunks(args.envelopes)
            write_json(args.output, result)
            print(json.dumps({
                "status": "ok",
                "video_ids": len(result["video_ids"]),
                "chunks": len(result["chunks"]),
                "chunk_size": CHUNK_SIZE,
            }))
            return 0
        result = merge(args.envelopes, args.since, args.until, chunks=load_json(args.chunks))
        write_json(args.output, result)
        print(json.dumps({"status": "ok", **result["coverage"]}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
