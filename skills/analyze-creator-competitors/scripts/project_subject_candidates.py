#!/usr/bin/env python3
"""Print the identity rows of a subject search or profile lookup, for disambiguation.

Choosing the subject is a model judgement: the candidates have to be compared on public
bio, display name and official external URL. But *seeing* them was costing separate round
trips — measured on an Instagram run, two `jq` reads of the search envelope plus one of the
profile envelope spent 14.7s of model time to surface fields the persist command already
had on disk. This prints them in the same command that places the envelope.

Accepts either shape without being told which: `data.rows[]` (search results) and
`data.profile` (a resolved profile). Anything it cannot read is reported as a row with the
fields it did find, never dropped — a candidate missing from the table is a candidate the
model cannot choose.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BIO_CHARS = 200


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return ""


def one_line(value: str, limit: int = BIO_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + "…" if len(text) > limit else text


def rows_of(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Identity rows in retrieval order; a resolved profile counts as one row."""
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    profile = data.get("profile")
    if isinstance(profile, dict):
        return [profile]
    rows = data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return [data] if data else []


def describe(row: dict[str, Any]) -> str:
    handle = first(row, "author", "handle", "username", "id")
    name = first(row, "full_name", "name", "title", "display_name")
    label = f"@{handle}" if handle and not handle.startswith("UC") else handle
    if name:
        label = f"{label} | {name}" if label else name
    parts = []
    followers = first(row, "follower_count", "followers", "subscriber_count")
    if followers:
        parts.append(f"followers={followers}")
    url = first(row, "external_url", "website", "source_url")
    if url:
        parts.append(f"url={url}")
    category = first(row, "category_name", "business_category_name", "category")
    if category:
        parts.append(f"category={category}")
    bio = one_line(first(row, "biography", "bio", "description"))
    tail = " ".join(parts)
    return f"[{label or '?'}] {tail}{' | ' if tail and bio else ''}{bio}".rstrip()


def table(envelopes: list[tuple[Path, dict[str, Any]]], limit: int | None) -> str:
    lines: list[str] = []
    for path, envelope in envelopes:
        rows = rows_of(envelope)
        shown = rows[:limit] if limit else rows
        header = f"{path.name}: {len(rows)} row(s) status={envelope.get('status') or '?'}"
        limitations = envelope.get("limitations")
        if limitations:
            header += f" limitations={one_line(json.dumps(limitations, ensure_ascii=False), 160)}"
        lines.append(header)
        for index, row in enumerate(shown, start=1):
            lines.append(f"{index}. {describe(row)}")
        if limit and len(rows) > limit:
            lines.append(f"… {len(rows) - limit} more row(s) not shown")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("envelopes", nargs="+", type=Path)
    parser.add_argument("--limit", type=int, default=8, help="identity rows printed per envelope (0 = all)")
    args = parser.parse_args()
    try:
        loaded = [(path, load(path)) for path in args.envelopes]
        print(table(loaded, args.limit or None))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
