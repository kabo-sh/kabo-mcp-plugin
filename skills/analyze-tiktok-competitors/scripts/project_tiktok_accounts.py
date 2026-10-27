#!/usr/bin/env python3
"""Project the complete TikTok discovery author union without popularity signals."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


PROFILE_URL = re.compile(r"tiktok\.com/@([^/?#\s]+)")


def normalize_ref(value: Any) -> str:
    """A supplied competitor ref as a bare lowercase handle; a profile URL gives its @handle and
    a `tiktok:` account ref gives the part after the prefix."""
    text = str(value or "").strip().lower()
    found = PROFILE_URL.search(text)
    return (found.group(1) if found else text).removeprefix("tiktok:").lstrip("@").rstrip("/")


def project(request: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != "competitor-research-request.v3":
        raise ValueError("request must be competitor-research-request.v3")
    if request.get("platforms") != ["tiktok"]:
        raise ValueError("request platforms must be [tiktok]")
    if candidates.get("schema_version") != "tiktok-trend-candidate-set.v1":
        raise ValueError("candidates must be tiktok-trend-candidate-set.v1")
    grouped: dict[str, dict[str, Any]] = {}
    texts: dict[str, list[str]] = defaultdict(list)
    mode = request.get("discovery_mode")
    if mode not in {"auto", "provided", "hybrid"}:
        raise ValueError("discovery_mode must be auto, provided or hybrid")
    provided = list(dict.fromkeys(
        ref for ref in (normalize_ref(value) for value in request.get("competitor_refs") or []) if ref
    ))
    matched: set[str] = set()
    for row in candidates.get("items") or []:
        author = row.get("author") or {}
        handle = str(author.get("handle") or "").lower().lstrip("@")
        account_ref = str(author.get("id") or (f"tiktok:{handle}" if handle else ""))
        if not handle or not account_ref:
            continue
        refs = {handle, account_ref.lower().removeprefix("tiktok:")} & set(provided)
        if mode == "provided" and not refs:
            continue
        matched |= refs
        account = grouped.setdefault(account_ref, {
            "account_ref": account_ref,
            "handle": handle,
            "display_name": author.get("full_name"),
        })
        if refs:
            account["provided"] = True
        caption = str(row.get("caption") or "").strip()
        if caption and caption not in texts[account_ref]:
            texts[account_ref].append(caption)
    # Every supplied handle is projected, with or without a search row: search rows are visible evidence only.
    if mode in {"provided", "hybrid"}:
        for handle in provided:
            if handle not in matched and f"tiktok:{handle}" not in grouped:
                grouped[f"tiktok:{handle}"] = {
                    "account_ref": f"tiktok:{handle}",
                    "handle": handle,
                    "display_name": None,
                    "provided": True,
                }
    items = []
    for account_ref in sorted(grouped):
        item = dict(grouped[account_ref])
        item["visible_content"] = texts[account_ref][:8]
        items.append(item)
    return {
        "schema_version": "tiktok-competitor-discovery-input.v1",
        "request_id": request["request_id"],
        "subject": request["subject"],
        "locale": request["locale"],
        "items": items,
    }


def table(result: dict[str, Any]) -> str:
    """The projection as numbered account lines: what the Gate classifies, line by line.

    The same subject, locale, handles, names and visible posts as the JSON, without the account_ref
    each Gate row used to retype: `build_tiktok_discovery_gate.py` maps a line number back to it.
    """
    head = {"request_id": result["request_id"], "subject": result["subject"], "locale": result["locale"]}
    lines = [json.dumps(head, ensure_ascii=False)]
    for index, row in enumerate(result["items"], start=1):
        name = row["handle"] + (f" | {row['display_name']}" if row.get("display_name") else "")
        posts = " || ".join(" / ".join(part.strip() for part in str(value).splitlines() if part.strip())
                            for value in row.get("visible_content") or [])
        if row.get("provided") and not posts:
            posts = "(supplied by the user; no post in the search results)"
        lines.append(f"{index}. [{name}] {posts}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--print", action="store_true", help="also print the projection to stdout")
    parser.add_argument("--table", action="store_true", help="also print numbered account lines for the Gate")
    args = parser.parse_args()
    try:
        result = project(load(args.request), load(args.candidates))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "accounts": len(result["items"])}))
        if args.print:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        if args.table:
            print(table(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
