#!/usr/bin/env python3
"""Render scene soundtrack evidence. Join path 1 (video-attached) and path 2 (catalog) on sound_id."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path


def cell(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def as_record(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def envelope_data(node):
    """Read successful envelope data and exclude failed results from soundtrack evidence."""
    if not isinstance(node, dict):
        return {}
    if node.get("status") not in (None, "completed", "completed_partial", "partial"):
        return {}
    if isinstance(node.get("data"), dict):
        return node["data"]
    return node


def sound_row(raw):
    """Normalize one catalog or attached track without inferring unknown originality or rights."""
    item = as_record(raw)
    nested = as_record(item.get("sound"))
    source = nested if nested.get("sound_id") or nested.get("audio_cluster_id") else item
    sound_id = source.get("sound_id") or source.get("audio_cluster_id")
    title = source.get("title")
    original = source.get("is_original")
    title_text = str(title or "").strip().lower()
    if original is None and (title_text.startswith("original sound") or title_text == "original audio"):
        original = True
    if not sound_id or not title and original is not True:
        return None
    title = title or "Original audio"
    count = source.get("video_count")
    if type(count) is not int or count < 0:
        count = None
    return {
        "sound_id": str(sound_id),
        "title": str(title),
        "author": source.get("author"),
        "video_count": count,
        "is_original": original,
        "source_url": source.get("source_url") or source.get("url"),
        "published_at": item.get("published_at") or source.get("published_at"),
        "observed_at": item.get("observed_at") or source.get("observed_at"),
        "usage_evidence": [{"source_url": source.get("source_url") or source.get("url"),
                            "published_at": item.get("published_at") or source.get("published_at")}]
        if source.get("source_url") or source.get("url") or item.get("published_at") or source.get("published_at") else [],
    }


def unique_sounds(rows, include_originals=False):
    """Merge paired evidence and retain originality vetoes until all pools are available."""
    by_id = {}
    for raw in rows:
        mapped = sound_row(raw)
        if mapped is None:
            continue
        existing = by_id.get(mapped["sound_id"])
        if existing is None:
            by_id[mapped["sound_id"]] = mapped
            continue
        if mapped["is_original"] is True:
            existing["is_original"] = True
        for evidence in mapped["usage_evidence"]:
            if evidence not in existing["usage_evidence"]:
                existing["usage_evidence"].append(evidence)
        # URL and date describe the same post; never combine two different posts.
        current_url, next_url = existing.get("source_url"), mapped.get("source_url")
        if next_url and (not current_url or not existing.get("published_at") and mapped.get("published_at")):
            existing["source_url"], existing["published_at"] = next_url, mapped.get("published_at")
        elif current_url == next_url and not existing.get("published_at"):
            existing["published_at"] = mapped.get("published_at")
        for key, value in mapped.items():
            if key in {"usage_evidence", "source_url", "published_at"}:
                continue
            if value is not None and value != "" and existing.get(key) in (None, ""):
                existing[key] = value
        counts = [n for n in (existing.get("video_count"), mapped.get("video_count")) if n is not None]
        existing["video_count"] = max(counts) if counts else None
    return [row for row in by_id.values() if include_originals or row["is_original"] is not True]


def pages(payload):
    """Treat either a single response or a collected page list as an iterable of pages."""
    return payload if isinstance(payload, list) else [payload]


def sound_evidence(raw):
    """Project an attached sound with the post's date and permalink when present."""
    item = as_record(raw)
    sound = as_record(item.get("sound"))
    if not sound:
        music = as_record(as_record(item.get("clips_metadata")).get("music_info"))
        asset = as_record(music.get("music_asset_info"))
        sound = {"sound_id": asset.get("audio_cluster_id") or asset.get("id"), "title": asset.get("title"),
                 "author": asset.get("display_artist"), "is_original": False} if asset else {}
    if not sound:
        return None
    result = dict(sound)
    result["source_url"] = item.get("url") or ("https://www.instagram.com/reel/" + str(item["code"]) + "/" if item.get("code") else None)
    date = item.get("published_at")
    if date is None and type(item.get("taken_at")) in (int, float):
        try:
            date = datetime.fromtimestamp(item["taken_at"], timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            pass
    result["published_at"] = date
    return result


def sounds_from_video(payload, include_originals=False):
    """Collect attached tracks across pages with available post dates and permalinks."""
    rows = []
    for page in pages(payload):
        data = envelope_data(page)
        # Prefer dated post records to the flattened attached-sound list.
        for raw in as_list(data.get("rows")) + as_list(data.get("items")):
            row = sound_evidence(raw)
            if row:
                rows.append(row)
        rows.extend(as_list(data.get("attached_sounds")))
    return unique_sounds(rows, include_originals=include_originals)


def sounds_from_catalog(payload, include_originals=False):
    """Normalize and deduplicate successful catalog hits across collected responses."""
    return unique_sounds([row for page in pages(payload) for row in as_list(envelope_data(page).get("sounds"))],
                         include_originals=include_originals)


def link_text(value):
    """Return escaped HTTP(S) source text only when it has a valid network location."""
    if not isinstance(value, str) or urlparse(value).scheme not in {"https", "http"} or not urlparse(value).netloc:
        return None
    return cell(value)


def usage_text(count):
    """Label available counts as highest observed lifetime use, never monthly popularity."""
    if count is None:
        return "usage not on this row"
    return f"{count} lifetime videos (highest observed count)"


def scene_label(scene):
    """`label` in the delivery language; older payloads carried `label_en` / `label_zh`."""
    for key in ("label", "label_en", "label_zh"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(scene.get("id") or "scene")


def render_scene(scene, language=None, excluded_ids=None):
    """Render all scene candidates in overlap, video-only, and catalog-only groups."""
    label = scene_label(scene)
    keyword = scene.get("keyword") or ""
    video = sounds_from_video(scene.get("video"), include_originals=True)
    catalog = sounds_from_catalog(scene.get("catalog"), include_originals=True)
    excluded = set(excluded_ids or ()) | {row["sound_id"] for row in video + catalog if row["is_original"] is True}
    video = [row for row in video if row["sound_id"] not in excluded]
    catalog = [row for row in catalog if row["sound_id"] not in excluded]
    video_ids = {row["sound_id"] for row in video}
    catalog_ids = {row["sound_id"] for row in catalog}
    catalog_by_id = {row["sound_id"]: row for row in catalog}
    overlap = []
    for row in video:
        if row["sound_id"] not in catalog_ids:
            continue
        catalog_row = catalog_by_id[row["sound_id"]]
        merged = dict(catalog_row, **{k: v for k, v in row.items() if v not in (None, "")})
        counts = [count for count in (catalog_row.get("video_count"), row.get("video_count")) if count is not None]
        merged["video_count"] = max(counts) if counts else None
        evidence = list(row.get("usage_evidence") or [])
        for pair in catalog_row.get("usage_evidence") or []:
            if pair not in evidence:
                evidence.append(pair)
        merged["usage_evidence"] = evidence
        overlap.append(merged)
    video_only = [row for row in video if row["sound_id"] not in catalog_ids]
    catalog_only = [row for row in catalog if row["sound_id"] not in video_ids]

    def sort_key(row):
        return (row["video_count"] is None, -(row["video_count"] or 0), row["title"])

    overlap.sort(key=sort_key)
    video_only.sort(key=sort_key)
    catalog_only.sort(key=sort_key)

    heading = f"## {cell(label)}"
    lines = [heading, ""]
    if keyword:
        lines.append(("Keyword: ") + cell(keyword))
        lines.append("")
    lines.append(
        "Known original sounds are omitted; unknown types remain candidates. Catalog visibility and non-original status do not establish usage rights."
    )
    lines.append("")

    if scene.get("stop_reason"):
        lines.extend([("Collection stopped: ") + cell(scene["stop_reason"]), ""])

    def block(title, rows, empty):
        """Append every candidate with paired usage evidence and explicit rights/monthly limits."""
        lines.append("### " + title)
        lines.append("")
        if not rows:
            lines.append(empty)
            lines.append("")
            return
        for row in rows:
            author = cell(row["author"]) if row.get("author") else ("unknown")
            lines.append(
                f'- {cell(row["title"])} — {author} · {usage_text(row["video_count"])} · `{cell(row["sound_id"])}`'
            )
            for evidence in row.get("usage_evidence") or [{}]:
                url = link_text(evidence.get("source_url"))
                date = evidence.get("published_at")
                lines.append(("  - Usage evidence: ") +
                             (cell(date) if date else ("date unknown")) +
                             " · " + (url or ("source link missing")))
            if row.get("observed_at"):
                lines.append(("  - Observed: ") + cell(row["observed_at"]))
            lines.append("  - Usage rights unknown; popularity within the requested month is not verified.")
        lines.append("")

    block(
        "In both pools",
        overlap,
        "No overlapping sound_id in this scene.",
    )
    block(
        "On scene videos, not in catalog keyword hits",
        video_only,
        "No recommendable attached tracks.",
    )
    block(
        "Catalog keyword hits, not on sampled videos",
        catalog_only,
        "No recommendable catalog tracks.",
    )
    return "\n".join(lines)


def render(payload, language="en"):
    """Render requested-scene candidates with quantity, collection metadata, and evidence limits."""
    scenes = as_list(payload.get("scenes"))
    if not scenes:
        raise ValueError("scene-sounds payload has no scenes")
    lines = [
        "Scene soundtrack",
        "",
        "Soundtrack candidates for the requested scenes; this is not a global or monthly popularity chart. Scenes: " + " / ".join(cell(scene_label(as_record(scene))) for scene in scenes) + "; mood is a grouping, not a query.",
        "",
        "Counts are lifetime usage. Search rows almost never have daily growth; do not call that acceleration.",
        "",
    ]
    all_rows = [row for scene in scenes for row in
                sounds_from_video(as_record(scene).get("video"), include_originals=True) +
                sounds_from_catalog(as_record(scene).get("catalog"), include_originals=True)]
    excluded_ids = {row["sound_id"] for row in all_rows if row["is_original"] is True}
    requested = payload.get("requested_count")
    if requested is not None:
        if type(requested) is not int or requested < 1:
            raise ValueError("requested_count must be a positive integer")
        found = {row["sound_id"] for row in all_rows if row["sound_id"] not in excluded_ids}
        lines.extend([(f"Requested: {requested}; retrieved: {len(found)} unique candidates, not verified monthly-popular tracks."), ""])
    for key, en in [("requested_month", "Requested month"), ("retrieved_at", "Retrieved"), ("stop_reason", "Collection stopped")]:
        if payload.get(key):
            lines.extend([(en) + ": " + cell(payload[key]), ""])
    for scene in scenes:
        lines.append(render_scene(as_record(scene), excluded_ids=excluded_ids))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", choices=("en", "zh-CN"), default="en")
    args = parser.parse_args()
    text = render(json.loads(args.payload.read_text()), args.language)
    args.output.write_text(text, encoding="utf-8")
