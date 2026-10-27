#!/usr/bin/env python3
"""Project the full Trend candidate union into the minimum semantic-gate input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def visible_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "caption", "description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return "\n".join(parts)


def creator_label(item: dict[str, Any]) -> str | None:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
    for value in (author.get("handle"), author.get("full_name"), channel.get("title"), channel.get("id")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def project(request: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != "trend-research-request.v3":
        raise ValueError("request must be trend-research-request.v3")
    if candidates.get("schema_version") not in {
        "trend-candidate-set.v1",
        "tiktok-trend-candidate-set.v1",
        "youtube-trend-candidate-set.v1",
    }:
        raise ValueError("candidates must be an Instagram, TikTok or YouTube trend candidate set")
    items = candidates.get("items")
    if not isinstance(items, list):
        raise ValueError("candidate items must be an array")
    projected = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("every candidate item must be an object")
        key = str(item.get("content_key") or "")
        if not key or key in seen:
            raise ValueError(f"missing or duplicate candidate content_key: {key}")
        seen.add(key)
        row = {"content_key": key, "visible_text": visible_text(item)}
        label = creator_label(item)
        if label:
            row["creator_label"] = label
        projected.append(row)
    platforms = request.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise ValueError("request platforms must contain at least one platform")
    if any(not isinstance(value, str) for value in platforms):
        raise ValueError("request platforms must contain only strings")
    platform = candidates.get("platform") if candidates.get("platform") is not None else platforms[0]
    if not isinstance(platform, str) or platform not in {"instagram", "tiktok", "youtube"}:
        raise ValueError("platform must be instagram, tiktok or youtube")
    if platform not in platforms:
        raise ValueError("candidate platform must be included in request platforms")
    locale = request.get("locale")
    if locale is None:
        locale = {}
    if not isinstance(locale, dict):
        raise ValueError("request locale must be an object")
    profile = request.get("creator_profile")
    if profile is not None and not isinstance(profile, dict):
        raise ValueError("request creator_profile must be an object")
    profile = profile or {}
    # The anchor's own format signature is the only evidence that separates
    # same-format content from merely same-subject content. Withholding it
    # leaves the Gate scoring captions against a niche noun phrase, which
    # cannot distinguish a style enumeration from a branding service ad.
    mechanisms = [
        value.strip()
        for value in (profile.get("observed_content_mechanisms") or [])
        if isinstance(value, str) and value.strip()
    ]
    handle = profile.get("handle")
    subject: dict[str, Any] = {
        "niche": str(request.get("niche") or ""),
        "region": locale.get("region"),
        "language": locale.get("language"),
    }
    if isinstance(handle, str) and handle.strip():
        subject["anchor_handle"] = handle.strip()
    if mechanisms:
        subject["anchor_mechanisms"] = mechanisms
    return {
        "schema_version": "trend-relevance-gate-input.v1",
        "request_id": str(request["request_id"]),
        "platform": platform,
        "subject": subject,
        "items": projected,
    }


# Leave room under a bounded host output for surrounding stage messages.
TABLE_BUDGET_BYTES = 32_000


def table_parts(output: dict[str, Any]):
    """Yield the original table records without shortening any evidence."""
    yield 0, json.dumps({key: output[key] for key in ("request_id", "platform", "subject")}, ensure_ascii=False)
    for index, row in enumerate(output["items"], start=1):
        text = " / ".join(part.strip() for part in str(row.get("visible_text") or "").splitlines() if part.strip())
        queries = "; ".join(row.get("matched_queries") or [])
        yield index, (f"\n{index}. [{row.get('creator_label') or '?'}]" +
                      (f" {{{queries}}}" if queries else "") + f" {text}")


def table(output: dict[str, Any]) -> str:
    """Keep the established small-table format byte-for-byte."""
    return "".join(text for _, text in table_parts(output))


def json_character_bytes(char: str) -> int:
    if char in ('"', "\\", "\b", "\f", "\n", "\r", "\t"):
        return 2
    if ord(char) < 32:
        return 6
    return len(char.encode("utf-8"))


def table_chunks(output: dict[str, Any], room: int):
    """Bound memory by one page while preserving every UTF-8 character in record order."""
    chars: list[str] = []
    used = 0
    first = last = None
    for index, text in table_parts(output):
        for char in text:
            size = json_character_bytes(char)
            if chars and used + size > room:
                yield "".join(chars), first, last
                chars, used, first, last = [], 0, None, None
            if index:
                first = index if first is None else first
                last = index
            chars.append(char)
            used += size
    if chars:
        yield "".join(chars), first, last


def page_frame(chunk: str, first: int | None, last: int | None, page: int,
               total: int, input_path: str, next_page: int | None) -> dict[str, Any]:
    return {
        "table_page": page,
        "total_pages": total,
        "first_candidate": first,
        "last_candidate": last,
        "table_chunk": chunk,
        "next": None if next_page is None else {
            "script": "scripts/project_relevance_gate_input.py",
            "arguments": ["--input", input_path, "--table", "--page", str(next_page)],
        },
        "instruction": ("Read every page before scoring. Concatenate table_chunk values without separators; "
                        "a numbered candidate may continue across pages. Run next.script from the same skill "
                        "directory with next.arguments until next is null. Do not recollect or score a partial table."),
    }


def render_table_page(output: dict[str, Any], input_path: str, page: int,
                      status: str, budget: int = TABLE_BUDGET_BYTES) -> str:
    if page < 1:
        raise ValueError("page must be a positive integer")
    # Two print() calls each append a newline. Include both and the status line in the budget.
    room = budget - len(status.encode("utf-8")) - 2
    small_parts: list[str] = []
    size = 0
    for _, text in table_parts(output):
        size += len(text.encode("utf-8"))
        if size > room:
            break
        small_parts.append(text)
    else:
        if page != 1:
            raise ValueError("page is outside this table (only page 1 exists)")
        return "".join(small_parts)
    del small_parts
    # Every page holds at least one character, so the total table length bounds all page numbers.
    maximum = sum(len(text) for _, text in table_parts(output)) + len(output["items"]) + 1
    worst = page_frame("", maximum, maximum, maximum, maximum, input_path, maximum)
    payload_room = room - len(json.dumps(worst, ensure_ascii=False).encode("utf-8"))
    if payload_room < 6:
        raise ValueError("table page metadata exceeds the output budget")
    total = sum(1 for _ in table_chunks(output, payload_room))
    if page > total:
        raise ValueError(f"page is outside this table (1..{total})")
    for number, (chunk, first, last) in enumerate(table_chunks(output, payload_room), 1):
        if number == page:
            result = json.dumps(page_frame(chunk, first, last, page, total, input_path,
                                           page + 1 if page < total else None), ensure_ascii=False)
            if len(result.encode("utf-8")) > room:
                raise ValueError("table page exceeds the output budget")
            return result
    raise ValueError("table page was not found")


def validate_projection(value: dict[str, Any]) -> None:
    if value.get("schema_version") != "trend-relevance-gate-input.v1":
        raise ValueError("input must be trend-relevance-gate-input.v1")
    if value.get("platform") not in {"instagram", "youtube", "tiktok"}:
        raise ValueError("input has an unsupported platform")
    if not isinstance(value.get("request_id"), str) or not value["request_id"]:
        raise ValueError("input must contain a request_id")
    if not isinstance(value.get("subject"), dict) or not isinstance(value.get("items"), list):
        raise ValueError("input must contain subject and items")
    seen: set[str] = set()
    for row in value["items"]:
        if not isinstance(row, dict) or not isinstance(row.get("content_key"), str):
            raise ValueError("every projected item must have a content_key")
        if not row["content_key"] or row["content_key"] in seen:
            raise ValueError("projected content_key must be nonempty and unique")
        if not isinstance(row.get("visible_text"), str):
            raise ValueError("every projected item must retain visible_text")
        if "matched_queries" in row and (not isinstance(row["matched_queries"], list) or
                                          any(not isinstance(query, str) for query in row["matched_queries"])):
            raise ValueError("matched_queries must be an array of strings")
        seen.add(row["content_key"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path, help="read an existing run projection without recollection or writes")
    parser.add_argument("--page", type=int, default=1, help="read this complete table page (1-based)")
    parser.add_argument("--print", action="store_true", help="also print the projection to stdout")
    parser.add_argument("--table", action="store_true", help="print the first table page and continuation instructions")
    args = parser.parse_args()
    try:
        if args.page < 1 or (args.page != 1 and not args.table):
            raise ValueError("--page requires --table and a positive integer")
        if args.table and args.print:
            raise ValueError("choose --table or --print, so one output stays within its budget")
        if args.input:
            if not args.table or args.print or any((args.request, args.candidates, args.output)):
                raise ValueError("--input requires only --table and optional --page")
            output = load(args.input)
            validate_projection(output)
            path = args.input
        else:
            if not all((args.request, args.candidates, args.output)) or args.page != 1:
                raise ValueError("provide --request, --candidates and --output; later pages use --input")
            output = project(load(args.request), load(args.candidates))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            path = args.output
        status = json.dumps({"status": "ok", "items": len(output["items"]), "path": str(path)})
        rendered = render_table_page(output, str(path), args.page, status) if args.table else None
        print(status)
        if args.print:
            print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        if rendered is not None:
            print(rendered)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
