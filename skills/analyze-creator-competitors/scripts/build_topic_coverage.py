#!/usr/bin/env python3
"""Project retrieved titles/captions so 'they have not done X' can be checked."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def normalize_title(value: str) -> str:
    return " ".join((value or "").split()).strip()


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
    """Tokens from the selected-account roster. None means no roster was supplied."""
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


def build(snapshot: dict[str, Any], selection: dict[str, Any] | None = None) -> dict[str, Any]:
    allow = included_tokens(selection)
    creators = {
        str(creator.get("creator_id") or ""): creator
        for creator in snapshot.get("creators") or []
        if isinstance(creator, dict) and creator.get("creator_id")
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        creator_id = str(item.get("creator_id") or "")
        content_id = str(item.get("content_id") or "")
        url = str(item.get("url") or "")
        if not creator_id or not content_id or not url:
            continue
        creator = creators.get(creator_id) or {}
        if allow is not None and allow.isdisjoint(creator_tokens(creator_id, creator)):
            continue
        grouped.setdefault(creator_id, []).append({
            "content_id": content_id,
            "url": url,
            "title": normalize_title(str(item.get("title") or "")),
            "published_at": item.get("published_at"),
        })
    accounts = []
    for creator_id, posts in grouped.items():
        creator = creators.get(creator_id) or {}
        accounts.append({
            "creator_id": creator_id,
            "handle": creator.get("handle"),
            "post_count": len(posts),
            "titles": [post["title"] for post in posts],
            "posts": posts,
        })
    accounts.sort(key=lambda row: str(row.get("handle") or row["creator_id"]))
    scope = snapshot.get("scope") if isinstance(snapshot.get("scope"), dict) else {}
    return {
        "schema_version": "topic-coverage.v1",
        "window": scope.get("window"),
        "post_count": sum(int(row["post_count"]) for row in accounts),
        "accounts": accounts,
    }


def coverage_table(coverage: dict[str, Any]) -> str:
    """One line per account: what each of them has actually published in the window.

    Synthesis needs this to say "they have not done X", and reading the JSON file back
    costs a whole round trip (measured 12s of model time on an Instagram run) for data
    the command that writes it already holds. Titles are the only field a gap claim is
    checked against, so `posts` and `content_id` stay in the file and out of this view.
    """
    window = coverage.get("window")
    header = f"topic-coverage: {coverage.get('post_count', 0)} posts"
    if isinstance(window, dict) and window.get("since") and window.get("until"):
        header += f" in {window['since']}/{window['until']}"
    lines = [header]
    for index, row in enumerate(coverage.get("accounts") or [], start=1):
        label = row.get("handle") or row.get("creator_id")
        titles = " | ".join(title for title in row.get("titles") or [] if title)
        lines.append(f"{index}. [{label}] ({row.get('post_count', 0)}) {titles}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--print", dest="print_table", action="store_true", help="also print one title line per account")
    args = parser.parse_args()
    try:
        selection = load(args.selection) if args.selection else None
        coverage = build(load(args.snapshot), selection)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.print_table:
            print(coverage_table(coverage))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
