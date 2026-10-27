#!/usr/bin/env python3
"""Merge Instagram profile-search rows into the persisted Candidate Set.

Profile rows have a bio, not a Reel. The discovery Gate reads title / caption /
description, so biography is copied onto description. Failed or empty envelopes
are a no-op. Existing Search/Popular items are kept; a profile hit on the same
handle only adds a `profiles` source.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from select_accounts import canonical_handle


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def envelope_payload(raw: dict[str, Any]) -> dict[str, Any]:
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return raw


def profile_rows(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    payload = envelope_payload(envelope)
    if payload.get("status") not in {"completed", "completed_partial", "partial"}:
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def visible_description(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("full_name", "category_name", "biography"):
        value = row.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return "\n".join(parts)


def author_from_row(row: dict[str, Any], handle: str) -> dict[str, Any]:
    author: dict[str, Any] = {"handle": handle}
    identifier = row.get("id")
    if isinstance(identifier, str) and identifier.strip():
        author["id"] = identifier.strip()
    elif isinstance(identifier, (int, float)) and not isinstance(identifier, bool):
        author["id"] = str(int(identifier))
    full_name = row.get("full_name")
    if isinstance(full_name, str) and full_name.strip():
        author["full_name"] = full_name.strip()
    for key, source in (
        ("is_verified", "is_verified"),
        ("follower_count", "follower_count"),
        ("post_count", "media_count"),
        ("is_private", "is_private"),
    ):
        value = row.get(source)
        if value is not None:
            author[key] = value
    return author


def profile_item(
    row: dict[str, Any],
    *,
    intent_id: str,
    query: str,
    rank: int,
    limitations: list[str] | None = None,
) -> dict[str, Any] | None:
    username = row.get("username")
    if not isinstance(username, str) or not username.strip():
        return None
    handle = username.strip().removeprefix("@")
    description = visible_description(row)
    url = row.get("url")
    if not isinstance(url, str) or not url.strip():
        url = f"https://www.instagram.com/{handle}/"
    return {
        "content_key": f"instagram-profile:{canonical_handle(handle)}",
        "platform": "instagram",
        "content_id": f"profile:{canonical_handle(handle)}",
        "url": url,
        "author": author_from_row(row, handle),
        "description": description,
        "sources": [
            {
                "route": "profiles",
                "intent_id": intent_id,
                "query": query,
                "rank": rank,
                "limitations": list(limitations or []),
            }
        ],
        "availability": {
            "author": True,
            "semantic_text": bool(description),
            "published_at": False,
            "play_count": False,
            "detail_status": "not_attempted_profile_search",
        },
    }


def item_handle(item: dict[str, Any]) -> str | None:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    handle = author.get("handle")
    if not isinstance(handle, str) or not handle.strip():
        return None
    return canonical_handle(handle)


def merge(
    candidates: dict[str, Any],
    plan: dict[str, Any],
    envelopes_by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    items = list(candidates.get("items") or [])
    if not isinstance(items, list):
        raise ValueError("candidate set items must be an array")
    by_handle: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        handle = item_handle(item)
        if handle and handle not in by_handle:
            by_handle[handle] = item

    calls = plan.get("calls")
    if not isinstance(calls, list):
        raise ValueError("profile discovery plan must include a calls array")

    for call in calls:
        if not isinstance(call, dict):
            continue
        envelope_name = call.get("envelope")
        intent_id = call.get("intent_id")
        query = call.get("query")
        if not isinstance(envelope_name, str) or not envelope_name.strip():
            continue
        if not isinstance(intent_id, str) or not intent_id.strip():
            continue
        if not isinstance(query, str) or not query.strip():
            continue
        envelope = envelopes_by_path.get(envelope_name)
        if envelope is None:
            continue
        # 部分成功的真实行仍可送 Gate，覆盖限制随来源保留；失败载荷不参与。
        payload = envelope_payload(envelope)
        limitations = payload.get("limitations")
        limitations = [value for value in limitations if isinstance(value, str)] if isinstance(limitations, list) else []
        for rank, row in enumerate(profile_rows(envelope), start=1):
            built = profile_item(row, intent_id=intent_id, query=query, rank=rank, limitations=limitations)
            if built is None:
                continue
            handle = item_handle(built)
            if handle is None:
                continue
            existing = by_handle.get(handle)
            source = built["sources"][0]
            if existing is not None:
                sources = existing.setdefault("sources", [])
                if isinstance(sources, list):
                    sources.append(source)
                continue
            items.append(built)
            by_handle[handle] = built

    merged = dict(candidates)
    merged["items"] = items
    return merged


def envelope_search_dirs(plan_path: Path, envelope_dir: Path | None) -> list[Path]:
    """Resolve planned envelope names from the plan dir *or* the run dir.

    persist_profile_envelopes.py historically defaulted --output-dir to cwd,
    while merge defaulted to the plan's directory. When the plan landed in
    snapshot/ and the envelopes stayed at the run root, merge was a silent
    no-op: measured 2026-09-14 on three product cases, search_profiles had
    already returned local product accounts that never entered the pool.
    """
    ordered: list[Path] = []
    for raw in (
        envelope_dir,
        plan_path.parent,
        Path.cwd(),
        Path.cwd() / "snapshot",
        plan_path.parent.parent,
    ):
        if raw is None:
            continue
        path = Path(raw)
        if path not in ordered:
            ordered.append(path)
    return ordered


def resolve_envelope(name: str, search_dirs: list[Path]) -> Path | None:
    for directory in search_dirs:
        path = directory / name
        if path.is_file():
            return path
    return None


def planned_envelope_names(plan: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for call in plan.get("calls") or []:
        if not isinstance(call, dict):
            continue
        name = call.get("envelope")
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name.strip())
    return names


def load_planned_envelopes(
    plan: dict[str, Any],
    search_dirs: list[Path],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    envelopes: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name in planned_envelope_names(plan):
        path = resolve_envelope(name, search_dirs)
        if path is None:
            missing.append(name)
            continue
        envelopes[name] = load(path)
    return envelopes, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--envelope-dir",
        type=Path,
        default=None,
        help="Preferred directory for planned envelope files. Also searches the run directory.",
    )
    args = parser.parse_args(argv)
    plan = load(args.plan)
    envelopes, missing = load_planned_envelopes(
        plan, envelope_search_dirs(args.plan, args.envelope_dir)
    )
    if missing:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": (
                        "planned profile-search envelopes were not found next to the "
                        "plan or in the run directory: " + ", ".join(missing)
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 2
    merged = merge(load(args.candidates), plan, envelopes)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
