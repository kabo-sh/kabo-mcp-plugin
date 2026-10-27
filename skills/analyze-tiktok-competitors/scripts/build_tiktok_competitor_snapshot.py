#!/usr/bin/env python3
"""Build one public-content snapshot from selected TikTok account histories."""

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
from analyze_public_snapshot import canonical_bytes, comparable_format
from sampling_policy import actual_window, policy


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


def metric(value: Any, native_name: str) -> dict[str, Any]:
    available = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    return {
        "status": "zero" if available and value == 0 else "available" if available else "unavailable",
        "value": value if available else None,
        "native_name": native_name,
    }


def canonical_item(row: dict[str, Any], creator_id: str) -> dict[str, Any]:
    """The existing snapshot field/metric/format normalization, shared by both paths."""
    values = row.get("metrics") or {}
    return {
        "content_id": str(row["content_id"]), "creator_id": creator_id,
        "url": str(row["url"]), "title": str(row.get("title") or "").strip(),
        "published_at": parse_time(str(row["published_at"])).isoformat().replace("+00:00", "Z"),
        "format": str(row.get("format") or "tiktok_video"),
        "metrics": {name: metric(values.get(name), name) for name in ("views", "likes", "comments")},
    }


def build(request: dict[str, Any], selection: dict[str, Any], histories: dict[str, Any]) -> dict[str, Any]:
    selected_policy = policy(request)
    if selected_policy:
        return build_latest(request, selection, histories, selected_policy)
    return build_date(request, selection, histories)


def build_date(request: dict[str, Any], selection: dict[str, Any], histories: dict[str, Any]) -> dict[str, Any]:
    since = parse_time(request["window"]["since"])
    until = parse_time(request["window"]["until"])
    runs = histories.get("runs")
    if not isinstance(runs, dict):
        raise ValueError("history bundle must contain runs")
    creators, items = [], []
    dropped_empty_title = 0
    complete = True
    retrieved = []
    unresolved = [
        {key: str(row[key]) for key in ("account_ref", "handle", "reason")}
        for row in selection.get("unresolved_accounts") or []
    ]
    for selected in selection.get("included") or []:
        handle = str(selected["handle"]).lower().lstrip("@")
        envelope = runs.get(handle)
        if not isinstance(envelope, dict) or envelope.get("status") != "completed":
            complete = False
            unresolved.append({"account_ref": str(selected["account_ref"]), "handle": handle,
                               "reason": "history_not_retrieved"})
            continue
        kept = len(items)
        data = envelope.get("data") or {}
        if data.get("more_available") is not False:
            complete = False
        if isinstance(envelope.get("retrieved_at"), str):
            retrieved.append(envelope["retrieved_at"])
        rows = data.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError(f"{handle} history rows must be an array")
        creator_id = str(next((row.get("creator_id") for row in rows if row.get("creator_id")), selected["account_ref"]))
        creators.append({
            "creator_id": creator_id,
            "handle": handle,
            "title": selected.get("display_name"),
            "source_url": f"https://www.tiktok.com/@{handle}",
            "relationship": "reference" if selected["relationship"] == "media" else selected["relationship"],
        })
        for row in rows:
            published = parse_time(str(row["published_at"]))
            if not since <= published <= until:
                continue
            title = str(row.get("title") or "").strip()
            if not title:
                dropped_empty_title += 1
                complete = False
                continue
            items.append(canonical_item(row, creator_id))
        if len(items) == kept:
            reason = "no_posts_in_window" if data.get("more_available") is False else "no_posts_in_retrieved_history"
            unresolved.append({"account_ref": creator_id, "handle": handle, "reason": reason})
    creators.sort(key=lambda row: row["creator_id"])
    items.sort(key=lambda row: (row["published_at"], row["content_id"]))
    raw = json.dumps({"creators": creators, "items": items}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return {
        "schema_version": "public-content-snapshot.v1",
        "snapshot_id": f"tiktok-competitor-{digest[:16]}",
        "observed_at": until.isoformat().replace("+00:00", "Z"),
        "platform": "tiktok",
        "scope": {
            "window": {
                "start": since.isoformat().replace("+00:00", "Z"),
                "end": until.isoformat().replace("+00:00", "Z"),
            },
            "queries": [],
            "region": request["locale"].get("region"),
            "language": request["locale"].get("language"),
        },
        "source": {
            "source_mode": "public_connector",
            "connector_id": "tiktok-public",
            "retrieved_at": (
                max(parse_time(value) for value in retrieved).isoformat().replace("+00:00", "Z")
                if retrieved else until.isoformat().replace("+00:00", "Z")
            ),
            "raw_sha256": digest,
            "coverage_complete": complete,
            "pagination": {
                "selected_accounts": len(selection.get("included") or []),
                "successful_accounts": len(creators),
                "dropped_empty_title": dropped_empty_title,
            },
            "unresolved_accounts": sorted(unresolved, key=lambda row: row["account_ref"]),
        },
        "creators": creators,
        "items": items,
    }


def build_latest(request: dict[str, Any], selection: dict[str, Any], histories: dict[str, Any],
                 sampling: dict[str, Any]) -> dict[str, Any]:
    """Select distinct latest IDs before title filtering; never backfill or rank by metrics."""
    until = parse_time(sampling["as_of"])
    count = sampling["count"]
    runs = histories.get("runs")
    if not isinstance(runs, dict):
        raise ValueError("history bundle must contain runs")
    sampled, audits, all_dates = {}, [], []
    for selected in selection.get("included") or []:
        handle = str(selected["handle"]).lower().lstrip("@")
        envelope = runs.get(handle)
        audit = {"handle": handle, "account_ref": str(selected["account_ref"]),
                 "requested_count": count, "raw_count": None, "selected_count": 0,
                 "analyzed_count": 0, "window": None, "reason": None}
        audits.append(audit)
        if not isinstance(envelope, dict) or envelope.get("status") != "completed":
            audit["reason"] = "history_not_retrieved"
            continue
        data = envelope.get("data") or {}
        rows = data.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError(f"{handle} history rows must be an array")
        audit["raw_count"] = len(rows)
        # An undated row could be newer than every dated row. Reject this account,
        # rather than sorting unknown dates last and pretending the latest N are known.
        try:
            dates = [parse_time(str(row["published_at"])) for row in rows]
        except (KeyError, TypeError, ValueError):
            audit["reason"] = "publication_order_unverifiable"
            continue
        creator_id = str(next((row.get("creator_id") for row in rows if row.get("creator_id")), selected["account_ref"]))
        unique = {}
        missing_native_format = False
        for row, published in zip(rows, dates):
            if published > until:
                continue
            # Date mode retains its historical default normalization. Latest-N
            # cannot use that default as proof that an unclassified row is a video.
            native_format = row.get("format")
            if not isinstance(native_format, str) or not native_format.strip():
                missing_native_format = True
                break
            canonical = canonical_item(row, creator_id)
            content_id = canonical["content_id"]
            if content_id in unique:
                # Same canonical ID conflict semantics as the unchanged analyzer.
                if canonical_bytes(unique[content_id][1]) != canonical_bytes(canonical):
                    raise ValueError(f"conflicting duplicate content_id: {content_id}")
            else:
                unique[content_id] = (row, canonical)
        if missing_native_format or any(not comparable_format(pair[1]["format"]) for pair in unique.values()):
            audit["reason"] = "video_classification_unverifiable"
            continue
        video_rows = [pair for pair in unique.values() if pair[1]["format"] in request["formats"]]
        ordered = sorted(video_rows, key=lambda pair: (-parse_time(pair[1]["published_at"]).timestamp(), pair[1]["content_id"]))
        chosen = ordered[:count]
        audit["selected_count"] = len(chosen)
        selected_rows = [pair[0] for pair in chosen]
        eligible = [pair[1] for pair in chosen if pair[1]["title"]]
        audit["analyzed_count"] = len(eligible)
        audit["window"] = actual_window(eligible)
        audit["reason"] = ("selected_posts_missing_title" if len(eligible) != len(chosen)
                           else "fewer_posts_than_requested" if len(chosen) < count else None)
        sampled[handle] = {**envelope, "data": {**data, "rows": selected_rows}}
        all_dates += [parse_time(item["published_at"]) for item in eligible]
    for row in selection.get("unresolved_accounts") or []:
        audits.append({"handle": str(row["handle"]), "account_ref": str(row["account_ref"]),
                       "requested_count": count, "raw_count": None, "selected_count": 0,
                       "analyzed_count": 0, "window": None, "reason": str(row["reason"])})
    # The analyzer needs an ordered collection boundary even for no evidence.
    # Actual publication dates are recorded separately as null for empty samples.
    dates = {"since": min(all_dates).isoformat().replace("+00:00", "Z") if all_dates else sampling["as_of"],
             "until": max(all_dates).isoformat().replace("+00:00", "Z") if all_dates else sampling["as_of"]}
    result = build_date({**request, "window": dates}, selection, {"runs": sampled})
    result["observed_at"] = until.isoformat().replace("+00:00", "Z")
    audit_by_handle = {row["handle"]: row for row in audits}
    result["source"]["unresolved_accounts"] = [
        {"account_ref": row["account_ref"], "handle": row["handle"], "reason": row["reason"]}
        for row in audits if row["analyzed_count"] == 0
    ]
    for creator in result["creators"]:
        audit_by_handle[creator["handle"]]["account_ref"] = creator["creator_id"]
    result["source"]["coverage_complete"] = bool(audits) and all(row["reason"] is None for row in audits)
    result["source"]["sampling"] = {"policy": dict(sampling), "accounts": audits,
                                     "window": actual_window(result["items"])}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--histories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(load(args.request), load(args.selection), load(args.histories))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "creators": len(result["creators"]), "items": len(result["items"])}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
