#!/usr/bin/env python3
"""Project provider-neutral Trend workflow outputs into PublicContentSnapshot V1."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from trend_gate_contract import classifications, validate_complete


YOUTUBE_SHORT_FORMATS = frozenset(("youtube_short", "short", "shorts", "short_form", "shortform"))
YOUTUBE_LONG_FORMATS = frozenset(("youtube_long", "long", "long_form", "longform"))


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def metric(value: Any, native_name: str) -> dict[str, Any]:
    if value is None:
        return {"status": "unavailable", "value": None, "native_name": native_name}
    number = float(value)
    return {
        "status": "zero" if number == 0 else "available",
        "value": number,
        "native_name": native_name,
    }


def nested(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def visible_text(*values: Any) -> str:
    """Return the first non-empty title/caption without rewriting provider text."""
    for value in values:
        if not isinstance(value, str):
            continue
        if value.strip():
            return value
    return ""


def youtube_format_of(source: dict[str, Any], url: str) -> tuple[str, bool]:
    """Return an explicit YouTube format and whether it remains unknown.

    Explicit provider declarations and canonical Shorts URLs take priority. The current backend's
    exact `youtube_long`/`moderate` pair is also safe to accept: that candidate is emitted only for
    videos over 180 seconds, which excludes Shorts under this contract. A provisional Short
    candidate remains unknown because duration alone does not prove use of the Shorts surface.
    """
    for path in (
        ("is_short",), ("isShort",), ("short",),
        ("snippet", "is_short"), ("snippet", "isShort"),
        ("contentDetails", "isShort"), ("content_details", "is_short"),
    ):
        declared = nested(source, path)
        if isinstance(declared, bool):
            return ("youtube_short" if declared else "youtube_long"), False
    for path in (
        ("format",), ("content_format",), ("video_format",), ("video_type",),
        ("snippet", "format"), ("snippet", "content_format"),
    ):
        declared = nested(source, path)
        if not isinstance(declared, str) or not declared.strip():
            continue
        normalized = re.sub(r"[\s-]+", "_", declared.strip().lower())
        if normalized in YOUTUBE_SHORT_FORMATS:
            return "youtube_short", False
        if normalized in YOUTUBE_LONG_FORMATS:
            return "youtube_long", False
    if re.search(r"/shorts(?:/|$)", url, flags=re.IGNORECASE):
        return "youtube_short", False
    candidate = re.sub(r"[\s-]+", "_", str(source.get("format_candidate") or "").strip().lower())
    confidence = str(source.get("format_confidence") or "").strip().lower()
    if candidate == "youtube_long" and confidence == "moderate":
        return "youtube_long", False
    return "unknown", True


def empty_enrichment(candidate_version: str) -> dict[str, Any]:
    if candidate_version == "youtube-trend-candidate-set.v1":
        return {
            "schema_version": "youtube-trend-enrichment.v1",
            "status": "completed",
            "items": [],
            "coverage": {
                "requested_items": 0,
                "enriched_items": 0,
                "unique_channels": 0,
                "channel_cache_hits": 0,
                "channel_cache_misses": 0,
            },
            "limitations": [
                "No direct or adjacent candidate passed the relevance gate; enrichment was skipped."
            ],
        }
    if candidate_version == "trend-candidate-set.v1":
        return {
            "schema_version": "trend-enrichment.v1",
            "status": "completed",
            "items": [],
            "coverage": {
                "requested_items": 0,
                "enriched_items": 0,
                "unique_authors": 0,
                "author_cache_hits": 0,
                "author_cache_misses": 0,
            },
            "limitations": [
                "No direct or adjacent candidate passed the relevance gate; enrichment was skipped."
            ],
        }
    raise ValueError("candidates must be an Instagram or YouTube trend candidate set")


def combine_enrichments(enrichments: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge bounded enrichment responses without trusting their batch-local ranks."""
    if not enrichments:
        raise ValueError("at least one enrichment artifact is required")
    versions = {str(value.get("schema_version") or "") for value in enrichments}
    if len(versions) != 1 or next(iter(versions)) not in {
        "trend-enrichment.v1", "youtube-trend-enrichment.v1",
    }:
        raise ValueError("all enrichment batches must use one supported schema_version")
    version = next(iter(versions))
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    limitations: list[str] = []
    for batch_index, batch in enumerate(enrichments, start=1):
        if not isinstance(batch.get("items"), list):
            raise ValueError(f"enrichment batch {batch_index} must contain an explicit items array")
        if batch.get("status") not in {"completed", "partial", "failed"}:
            raise ValueError(f"enrichment batch {batch_index} has an invalid status")
        for item in batch["items"]:
            key = str(item.get("content_key") or "")
            if not key:
                raise ValueError(f"enrichment batch {batch_index} contains an item without content_key")
            if key in seen:
                raise ValueError(f"duplicate content_key across enrichment batches: {key}")
            seen.add(key)
            # `absolute_view_rank` is scoped to one server response. The Analyzer recomputes its
            # own deterministic order after the merged Snapshot, so carrying duplicate batch ranks
            # would make an audit field look globally comparable when it is not.
            normalized = dict(item)
            normalized.pop("absolute_view_rank", None)
            items.append(normalized)
        for limitation in batch.get("limitations") or []:
            if limitation not in limitations:
                limitations.append(limitation)
    statuses = {str(batch.get("status") or "failed") for batch in enrichments}
    # An empty array is a valid result and must not turn partial into failed; real failures stay failed.
    status = "completed" if statuses == {"completed"} else (
        "failed" if not items and "failed" in statuses else "partial"
    )
    coverage: dict[str, Any] = {
        "requested_items": sum(int((batch.get("coverage") or {}).get("requested_items") or 0) for batch in enrichments),
        "enriched_items": len(items),
        "batch_count": len(enrichments),
    }
    if version == "youtube-trend-enrichment.v1":
        coverage.update({
            "unique_channels": len({str((item.get("channel") or {}).get("id")) for item in items if (item.get("channel") or {}).get("id")}),
            "channel_cache_hits": sum(int((batch.get("coverage") or {}).get("channel_cache_hits") or 0) for batch in enrichments),
            "channel_cache_misses": sum(int((batch.get("coverage") or {}).get("channel_cache_misses") or 0) for batch in enrichments),
        })
    else:
        coverage.update({
            "unique_authors": len({str((item.get("author") or {}).get("id")) for item in items if (item.get("author") or {}).get("id")}),
            "author_cache_hits": sum(int((batch.get("coverage") or {}).get("author_cache_hits") or 0) for batch in enrichments),
            "author_cache_misses": sum(int((batch.get("coverage") or {}).get("author_cache_misses") or 0) for batch in enrichments),
        })
    if len(enrichments) > 1:
        limitations.append(
            f"Merged {len(enrichments)} bounded enrichment batches; batch-local ranks were discarded and downstream ranking is recomputed from the merged Snapshot."
        )
    merged: dict[str, Any] = {
        "schema_version": version,
        "status": status,
        "items": items,
        "coverage": coverage,
        "limitations": limitations,
    }
    # The thresholds the platform applied travel with the result (absent from older platforms).
    policies = [batch["applied_policy"] for batch in enrichments if isinstance(batch.get("applied_policy"), dict)]
    if policies:
        merged["applied_policy"] = policies[0]
        if any(policy != policies[0] for policy in policies[1:]):
            limitations.append("Enrichment batches reported different applied policies; the first batch's is used.")
    return merged


def build(
    request: dict[str, Any],
    candidates: dict[str, Any],
    gate: dict[str, Any],
    enrichment: dict[str, Any],
) -> dict[str, Any]:
    if request.get("schema_version") != "trend-research-request.v3":
        raise ValueError("request must be trend-research-request.v3")
    candidate_version = candidates.get("schema_version")
    if candidate_version not in {"trend-candidate-set.v1", "youtube-trend-candidate-set.v1"}:
        raise ValueError("candidates must be an Instagram or YouTube trend candidate set")
    enrichment_version = enrichment.get("schema_version")
    expected_enrichment = (
        "youtube-trend-enrichment.v1"
        if candidate_version == "youtube-trend-candidate-set.v1"
        else "trend-enrichment.v1"
    )
    if enrichment_version != expected_enrichment:
        raise ValueError(f"enrichment must be {expected_enrichment}")
    if gate.get("request_id") != request.get("request_id"):
        raise ValueError("gate request_id does not match request")

    candidate_by_key: dict[str, dict[str, Any]] = {}
    for item in candidates.get("items") or []:
        key = str(item["content_key"])
        if key in candidate_by_key:
            raise ValueError(f"duplicate candidate content_key: {key}")
        candidate_by_key[key] = item
    candidate_keys = set(candidate_by_key)
    roles = validate_complete(gate, candidate_keys, enrichment.get("applied_policy"))

    creators: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    dropped_missing_time = 0
    dropped_missing_creator = 0
    dropped_missing_url = 0
    dropped_missing_title = 0
    title_candidate_fallbacks = 0
    format_unknown = 0
    for source in enrichment.get("items") or []:
        key = str(source.get("content_key") or "")
        role = roles.get(key)
        if role not in {"direct", "adjacent"}:
            continue
        candidate = candidate_by_key.get(key) or {}
        published = source.get("published_at")
        if not isinstance(published, str) or not published:
            dropped_missing_time += 1
            continue
        platform = str(source.get("platform") or candidates.get("platform") or "")
        author = source.get("author") or {}
        channel = source.get("channel") or {}
        if platform == "youtube":
            creator_id = str(channel.get("id") or "")
            title = str(channel.get("title") or "").strip() or None
            raw_handle = str(channel.get("handle") or "").strip()
            handle = raw_handle.lstrip("@") or None
            creator_url = f"https://www.youtube.com/channel/{creator_id}" if creator_id else ""
        else:
            handle = str(author.get("handle") or "").lstrip("@")
            title = None
            creator_id = str(author.get("id") or (f"instagram:{handle}" if handle else ""))
            creator_url = f"https://www.instagram.com/{handle}/" if handle else ""
        if not creator_id or (platform != "youtube" and not handle):
            dropped_missing_creator += 1
            continue
        url = str(source.get("url") or "")
        if not url:
            dropped_missing_url += 1
            continue
        source_title = visible_text(source.get("title"), source.get("caption"))
        candidate_title = visible_text(candidate.get("title"), candidate.get("caption"))
        item_title = source_title or candidate_title
        if not item_title:
            dropped_missing_title += 1
            continue
        if not source_title:
            title_candidate_fallbacks += 1
        creators[creator_id] = {
            "creator_id": creator_id,
            "handle": handle,
            "handle_verified": bool(handle),
            "title": title,
            "source_url": creator_url,
            "relationship": "reference",
        }
        metrics = source.get("metrics") or {}
        queries = sorted({
            str(item.get("query"))
            for item in source.get("sources") or []
            if item.get("query")
        })
        if platform == "youtube":
            content_id = str(source.get("video_id") or key.removeprefix("youtube:"))
            format_name, unknown = youtube_format_of(source, url)
            if unknown:
                format_unknown += 1
            native_metrics = {
                "views": metrics.get("views"),
                "likes": metrics.get("likes"),
                "comments": metrics.get("comments"),
            }
            native_names = {"views": "viewCount", "likes": "likeCount", "comments": "commentCount"}
        else:
            content_id = str(source.get("content_id") or key)
            format_name = "instagram_reel"
            native_metrics = {
                "views": metrics.get("play_count"),
                "likes": metrics.get("like_count"),
                "comments": metrics.get("comment_count"),
            }
            native_names = {"views": "play_count", "likes": "like_count", "comments": "comment_count"}
        item = {
            "evidence_rank": len(items) + 1,
            "content_id": content_id,
            "creator_id": creator_id,
            "url": url,
            "title": item_title,
            "published_at": iso(published),
            "format": format_name,
            "duration_seconds": source.get("duration_seconds"),
            "query_refs": queries,
            "metrics": {
                "views": metric(native_metrics["views"], native_names["views"]),
                "likes": metric(native_metrics["likes"], native_names["likes"]),
                "comments": metric(native_metrics["comments"], native_names["comments"]),
            },
        }
        if platform == "youtube":
            item["format_confidence"] = (
                source.get("format_confidence", "explicit") if format_name != "unknown" else "unknown"
            )
            item["maturity"] = source.get("maturity", "unknown")
        items.append(item)

    window = request["window"]
    source_material = {"candidates": candidates, "gate": gate, "enrichment": enrichment}
    digest = hashlib.sha256(canonical(source_material)).hexdigest()
    retrieved_at = candidates.get("retrieved_at") or window["until"]
    return {
        "schema_version": "public-content-snapshot.v1",
        "snapshot_id": f"trend-workflow-{digest[:16]}",
        "observed_at": iso(str(retrieved_at)),
        "platform": str(candidates.get("platform") or request["platforms"][0]),
        "scope": {
            "window": {"start": iso(window["since"]), "end": iso(window["until"])},
            "queries": sorted({
                str(source.get("query"))
                for item in candidates.get("items") or []
                for source in item.get("sources") or []
                if source.get("query")
            }),
            "region": request.get("locale", {}).get("region"),
            "language": request.get("locale", {}).get("language"),
        },
        "source": {
            "source_mode": "public_connector",
            "connector_id": "trend-candidate-workflow",
            "retrieved_at": iso(str(retrieved_at)),
            "raw_sha256": digest,
            "coverage_complete": False,
            "pagination": {
                "provider_calls": candidates.get("coverage", {}).get("provider_calls", 0),
                "discovery_provider_calls": candidates.get("coverage", {}).get("discovery_provider_calls", 0),
                "detail_provider_calls": candidates.get("coverage", {}).get("detail_provider_calls", 0),
                "candidate_count": candidates.get("coverage", {}).get("candidate_count", 0),
                "deduplicated_candidate_count": candidates.get("coverage", {}).get("deduplicated_candidate_count", candidates.get("coverage", {}).get("candidate_count", 0)),
                "truncated_candidate_count": candidates.get("coverage", {}).get("truncated_candidate_count", 0),
                "gate_items": len(roles),
                "gate_eligible_items": sum(role in {"direct", "adjacent"} for role in roles.values()),
                "enrichment_returned_items": len(enrichment.get("items") or []),
                "enriched_items": enrichment.get("coverage", {}).get("enriched_items", 0),
                "snapshot_items": len(items),
                "dropped_missing_time": dropped_missing_time,
                "dropped_missing_creator": dropped_missing_creator,
                "dropped_missing_url": dropped_missing_url,
                "dropped_missing_title": dropped_missing_title,
                "title_candidate_fallbacks": title_candidate_fallbacks,
                "format_unknown": format_unknown,
            },
        },
        "creators": sorted(creators.values(), key=lambda item: item["creator_id"]),
        "items": sorted(items, key=lambda item: (item["published_at"], item["content_id"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--enrichment", type=Path, action="append", default=[])
    parser.add_argument("--merged-enrichment-output", type=Path)
    parser.add_argument("--empty-enrichment-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = load(args.request)
        candidates = load(args.candidates)
        gate = load(args.gate)
        empty_enrichment_output: Path | None = None
        merged_enrichment_output: Path | None = None
        if args.enrichment:
            if args.empty_enrichment_output:
                raise ValueError("use either --enrichment or --empty-enrichment-output, not both")
            if not args.merged_enrichment_output:
                raise ValueError("--merged-enrichment-output is required with --enrichment")
            enrichment = combine_enrichments([load(path) for path in args.enrichment])
            merged_enrichment_output = args.merged_enrichment_output
        else:
            if args.merged_enrichment_output:
                raise ValueError("--merged-enrichment-output requires at least one --enrichment")
            if not args.empty_enrichment_output:
                raise ValueError("--enrichment is required unless --empty-enrichment-output is used")
            eligible = [role for role in classifications(gate).values() if role in {"direct", "adjacent"}]
            if eligible:
                raise ValueError("empty enrichment is allowed only when no direct or adjacent item passed the gate")
            enrichment = empty_enrichment(str(candidates.get("schema_version") or ""))
            empty_enrichment_output = args.empty_enrichment_output
        result = build(request, candidates, gate, enrichment)
        if empty_enrichment_output is not None:
            empty_enrichment_output.parent.mkdir(parents=True, exist_ok=True)
            empty_enrichment_output.write_text(
                json.dumps(enrichment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if merged_enrichment_output is not None:
            merged_enrichment_output.parent.mkdir(parents=True, exist_ok=True)
            merged_enrichment_output.write_text(
                json.dumps(enrichment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
