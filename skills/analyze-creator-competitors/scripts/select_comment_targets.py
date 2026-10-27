#!/usr/bin/env python3
"""Pick a small set of retrieved posts so list_comments stays bounded."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "competitor-comment-targets.v1"
DEFAULT_LIMIT = 4
YOUTUBE_ID = re.compile(
    r"(?:(?:v=)|(?:/shorts/)|(?:/embed/)|(?:/live/)|(?:youtu\.be/))([\w-]{6,64})"
)
TIKTOK_ID = re.compile(r"/video/(\d{1,32})")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def canonical_token(value: str) -> str:
    stripped = (value or "").strip().removeprefix("@")
    if not stripped:
        return ""
    if re.fullmatch(r"UC[\w-]{22}", stripped):
        return stripped
    return stripped.casefold()


def token_aliases(value: str) -> set[str]:
    token = canonical_token(value)
    if not token:
        return set()
    aliases = {token}
    if ":" in token:
        tail = canonical_token(token.split(":", 1)[1])
        if tail:
            aliases.add(tail)
    return aliases


def included_tokens(selection: dict[str, Any] | None) -> set[str] | None:
    if selection is None:
        return None
    tokens: set[str] = set()
    for handle in selection.get("included_handles") or []:
        tokens.update(token_aliases(str(handle)))
    for row in selection.get("included") or []:
        if not isinstance(row, dict):
            continue
        for key in ("account_ref", "handle"):
            tokens.update(token_aliases(str(row.get(key) or "")))
    return tokens


def creator_tokens(creator_id: str, creator: dict[str, Any]) -> set[str]:
    tokens = token_aliases(creator_id)
    tokens.update(token_aliases(str(creator.get("handle") or "")))
    return tokens


def metric_value(item: dict[str, Any], name: str) -> float:
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        return 0.0
    row = metrics.get(name)
    if isinstance(row, dict):
        value = row.get("value")
        return float(value) if isinstance(value, (int, float)) else 0.0
    return float(row) if isinstance(row, (int, float)) else 0.0


def platform_of(snapshot: dict[str, Any]) -> str:
    platform = str(snapshot.get("platform") or "").strip().casefold()
    if platform in {"instagram", "ig"}:
        return "instagram"
    if platform in {"youtube", "yt"}:
        return "youtube"
    if platform in {"tiktok", "tt"}:
        return "tiktok"
    raise ValueError(f"unsupported snapshot platform: {snapshot.get('platform')}")


def youtube_video_id(item: dict[str, Any]) -> str | None:
    content_id = str(item.get("content_id") or "").strip()
    if re.fullmatch(r"[\w-]{6,64}", content_id) and not content_id.isdigit():
        return content_id
    url = str(item.get("url") or "")
    match = YOUTUBE_ID.search(url)
    return match.group(1) if match else None


def tiktok_aweme_id(item: dict[str, Any]) -> str | None:
    content_id = str(item.get("content_id") or "").strip()
    if re.fullmatch(r"\d{1,32}", content_id):
        return content_id
    match = TIKTOK_ID.search(str(item.get("url") or ""))
    return match.group(1) if match else None


def analyzed_content_ids(analysis: dict[str, Any] | None) -> set[str] | None:
    """Citeable posts only. None means the caller did not pass analysis."""
    if analysis is None:
        return None
    ids: set[str] = set()
    for row in analysis.get("evidence") or []:
        if not isinstance(row, dict):
            continue
        content_id = str(row.get("content_id") or "").strip()
        if content_id:
            ids.add(content_id)
    return ids


def connector_for(platform: str) -> tuple[str, str, dict[str, Any] | None]:
    if platform == "instagram":
        return "instagram-discovery", "list_comments", None
    if platform == "youtube":
        return "youtube-public", "list_comments", None
    return "tiktok-discovery", "list_comments", None


def params_for(platform: str, item: dict[str, Any]) -> dict[str, Any] | None:
    url = str(item.get("url") or "").strip()
    if platform == "instagram":
        return {"url": url} if url else None
    if platform == "youtube":
        video_id = youtube_video_id(item)
        return {"video_id": video_id, "limit": 20} if video_id else None
    aweme_id = tiktok_aweme_id(item)
    return {"aweme_id": aweme_id, "count": 20} if aweme_id else None


def build(
    snapshot: dict[str, Any],
    selection: dict[str, Any] | None = None,
    *,
    analysis: dict[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    platform = platform_of(snapshot)
    connector_id, operation, _ = connector_for(platform)
    allow = included_tokens(selection)
    citeable = analyzed_content_ids(analysis)
    creators = {
        str(creator.get("creator_id") or ""): creator
        for creator in snapshot.get("creators") or []
        if isinstance(creator, dict)
    }
    ranked: list[dict[str, Any]] = []
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        creator_id = str(item.get("creator_id") or "")
        creator = creators.get(creator_id) or {}
        if allow is not None and not (creator_tokens(creator_id, creator) & allow):
            continue
        content_id = str(item.get("content_id") or "").strip()
        if citeable is not None and content_id not in citeable:
            continue
        params = params_for(platform, item)
        url = str(item.get("url") or "").strip()
        if not params or not url:
            continue
        ranked.append(
            {
                "content_id": content_id,
                "handle": str(creator.get("handle") or ""),
                "url": url,
                "caption": str(item.get("title") or item.get("caption") or ""),
                "comment_count": int(metric_value(item, "comments")),
                "view_count": int(metric_value(item, "views")),
                "params": params,
            }
        )
    ranked.sort(key=lambda row: (row["comment_count"], row["view_count"]), reverse=True)
    targets = []
    seen: set[str] = set()
    for row in ranked:
        key = json.dumps(row["params"], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {key: row[key] for key in ("content_id", "handle", "url", "caption", "comment_count", "params")}
        )
        if len(targets) >= limit:
            break
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform,
        "connector_id": connector_id,
        "operation": operation,
        "limit": limit,
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        selection = load(args.selection) if args.selection else None
        analysis = load(args.analysis) if args.analysis else None
        payload = build(
            load(args.snapshot),
            selection,
            analysis=analysis,
            limit=args.limit,
        )
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "ok", "targets": len(payload["targets"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
