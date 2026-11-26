#!/usr/bin/env python3
"""Build the ContentEvidence object from the connector envelopes this run persisted.

Every field written here is a copy, or a unit conversion, of something a connector returned, so it
is this script's to write and never the model's. A model transcribing a fenced, possibly truncated
tool result into JSON is how a cue start in milliseconds reached the evidence as seconds (off by a
factor of a thousand) and how a whole cue set was dropped over a field name that did not match.
What the envelopes cannot carry (a limitation the run observed elsewhere, owner metrics read from a
creator's export) comes in through --limitation and --owner-metrics.

Inputs are the persisted public-video-media envelopes -- collect_public_metadata, fetch_transcript
and extract_keyframes / extract_keyframes_hosted_media -- one --envelope each, in any order. A job
resource that carries its terminal envelope is accepted as is. Any other envelope is recorded in
``acquisition`` only. When one operation was retried, the last usable response is the evidence and
every attempt stays in ``acquisition``. Web kabo-video/get_video_transcript envelopes also supply
captions, preserving their actual connector, operation and source metadata.

A local run has no envelopes for the media at all. Its file was read here, by this package's own
scripts, and their artifacts come in through --local-media and --local-transcript. They are not
envelopes and are never recorded as though they were: each becomes an ``acquisition`` entry marked
``local_extraction``, carrying the tool, its version and a hash of the invocation instead of a
connector and a request id. Everything downstream of that -- the media block, the frame list, the
cues -- is written in exactly the shape the connector path writes, because a frame read here and a
frame read there are the same evidence and nothing reading them should have to ask which.

The two paths never serve one request. A local file and a connector response are readings of two
different copies of the video -- the creator's master and whatever the platform re-encoded and
delivered -- and merging them would produce one object claiming both sets of numbers describe the
same thing. Mixing them is refused, loudly, rather than resolved.

Standard library only: this runs on a user's machine through the host's python3.
"""

from __future__ import annotations

import argparse
import importlib.util
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

_linked_spec = importlib.util.spec_from_file_location("kabo_linked_media", Path(__file__).with_name("linked_media.py"))
linked_media = importlib.util.module_from_spec(_linked_spec)
_linked_spec.loader.exec_module(linked_media)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import observation_order  # noqa: E402
import public_video_sources  # noqa: E402
import viewer_response  # noqa: E402
import acv_timing  # noqa: E402
import transcript_checks  # noqa: E402

SCHEMA_VERSION = "content-evidence.v1"
MEDIA_CONNECTOR = "public-video-media"
# YouTube metadata comes from the platform's own data API, not from the media connector's
# downloader. The downloader reads a video page from a datacentre address and YouTube refuses
# those: in production collect_public_metadata on a YouTube URL is a service_unavailable every
# time, which cost every YouTube run its title, tags, cover and publish date. The data API has
# no such problem -- it is the platform answering about its own video -- so that is where the
# metadata role comes from on YouTube, and the downloader keeps it on the other platforms.
YOUTUBE_METADATA_CONNECTOR = "youtube-public"
YOUTUBE_METADATA_OPERATION = "get_video"
# tiktok_search_get_video: TikTok's own answer about the video (counts, caption, sound), read as metadata.
TIKTOK_METADATA_CONNECTOR = "tiktok-search"
TIKTOK_METADATA_OPERATION = "get_video"
KEYFRAME_OPERATIONS = {
    "extract_keyframes",
    "extract_keyframes_hosted_media",
    "extract_keyframes_hosted_stream",
}
ROLE_OF_OPERATION = {"collect_public_metadata": "metadata", "fetch_transcript": "captions",
                     "measure_media_signals": "measurements"}
ROLE_OF_OPERATION.update({operation: "frames" for operation in KEYFRAME_OPERATIONS})
# The published post row is a platform fact about the post, not a measurement of the file, so it
# comes from a discovery connector rather than from the downloader. Two of them serve the same
# operation; the role follows the operation, not which one answered.
POST_CONNECTORS = {"instagram-discovery", "instagram-detail-proxy"}
POST_OPERATION = "get_post"
# However lookup_instagram_post answers, data is this one fixed projection; judge the shape by it, not by
# connector_id. Envelopes without this marker are the old single-operation tool envelope (GraphQL as-is or a
# detail allowlist) and are read as before.
POST_PROJECTION = "kabo.instagram_post.v1"
PLAYS_NOTE = "A play count, which is neither reach nor an owner view figure."
# A digitally silent sample reads as an extreme negative rather than as an absent one. The floor is
# what separates "the track has not started" from "the track is quiet here".
SILENT_LUFS = -100.0
# A hashtag runs to the next space or hash. Kept in the order the creator wrote them.
HASHTAG = re.compile(r"#([^\s#]+)")
# Copied verbatim from the measurement response, less any key it may grow later: the evidence
# declares these and nothing else, and a block that quietly gained a field would be carrying
# something no reader has a definition for.
PROBED_KEYS = {
    "shots": {"count", "cuts_at_s", "shots"},
    "silence": {"min_s", "floor_db", "spans"},
    "freeze": {"min_s", "spans"},
    "framing": {"fps", "width", "height", "aspect_ratio", "vertical_screen_fill", "bars", "content_rect"},
    "brightness": {"samples", "whole_video", "per_shot"},
}
USABLE = {"completed", "completed_partial"}
ACQUISITION_STATUSES = {
    "completed", "completed_partial", "pending", "deferred_incomplete",
    "blocked_setup", "feature_gated", "unsupported", "failed",
}
FRAME_SELECTIONS = {"duration_scaled_v1", "evenly_spaced_bounded_v1", "explicit_timestamps_v1", "quick_sample_v1",
                    "none"}
TRANSCRIPT_ORIGINS = {"platform_captions", "provider_transcript", "speech_recognition"}
# When only the transcript is exported, metadata is not fetched and the model's request often has no content_id
# either: take it from the original link the creator gave. The platform, the evidence-id prefix and the id
# pattern in the link are read from the support list public-video-sources.v1, not written again here.
content_id_from_url = public_video_sources.content_id_from_url
# Support-list public_metrics keys <- the count field names in metadata. Share and save counts come back only
# from the platforms resolved through the paid path (Douyin, Xiaohongshu, Kuaishou).
METADATA_COUNTERS = {"view_count": "views", "like_count": "likes", "comment_count": "comments",
                     "share_count": "shares", "save_count": "saves"}
# Counts the evidence states as "unavailable, not zero" when the platform does not publish them: only these
# three, so the older platforms' evidence gains no extra notes about shares or saves.
STATED_GAPS = ("views", "likes", "comments")
# Where a Facebook view count comes from (view_count_basis): the page's rounded display is kept with its
# precision noted; when withheld, view_count is null and nothing is kept.
VIEW_BASIS_NOTES = {
    "page_display_rounded": "the page's own rounded display, not an exact figure",
    "page_display": "the page's own display",
}
# The connector's blanket "nothing came back" sentence. It is true of one call, not of the run, so
# it never travels into the evidence when anything else was retrieved.
BLANKET = "no data was retrieved"
# Statuses that say the path is not available here, rather than that a provider failed.
NOT_A_FAILURE = {"unsupported", "blocked_setup", "feature_gated"}
# YouTube names its cover renditions by file name; the evidence tiers are those names.
YOUTUBE_THUMBNAIL_TIERS = {"maxresdefault": "maxres", "sddefault": "standard", "hqdefault": "high",
                           "mqdefault": "medium", "default": "default"}
ZONED = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")
SAMPLING_PLAN_KEYS = {
    "base_interval_s", "hook_window_s", "hook_dense_window_s", "hook_interval_s", "hook_frames",
    "body_interval_s", "body_frames", "budget", "frames", "body_degraded", "note", "closing_frame_s",
    # Present only when shot starts or dense windows were asked for (and the server applied them).
    "include_shot_starts", "shot_detection", "shot_start_frames", "dense_window_frames", "dense_windows",
    "dropped_for_budget", "dropped_as_duplicate", "dedupe_s", "budget_priority",
    # Present only on the overview plan (acv_timing.py's docstring) of a video longer than 50s.
    "overview", "overview_stride_s", "change_candidates", "change_frames", "anchor_frames",
    "change_threshold_units", "anchor_gap_s",
}
# Why a frame is in the plan: the same names on the server and on this machine.
FRAME_SOURCES = {"hook", "body", "closing", "shot_start", "dense_window", "change", "anchor"}
CHANGE_REASONS = {"picture_change", "text_change"}


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def partial_coverage(value: Any) -> dict[str, Any] | None:
    """What a quick first read of a long video covered (`quick_above_s` on the request): the transcript's or the
    measurement's `coverage` when it is partial, as {mode, covered_s: [from, to], duration_s}. No coverage, or a
    malformed one, is a full pass: None."""
    if not isinstance(value, dict) or value.get("mode") != "partial":
        return None
    span = value.get("covered_s")
    if (not isinstance(span, list) or len(span) != 2
            or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in span)
            or not 0 <= span[0] < span[1]):
        return None
    duration = value.get("duration_s")
    return {"mode": "partial", "covered_s": [span[0], span[1]],
            "duration_s": duration if positive_number(duration) else None}


def quick_sampling(value: Any) -> dict[str, Any] | None:
    """The keyframes' `sampling` when the server took a quick sample of a long video: how many frames, at which
    moments, of how long a video. Anything else (the full pass carries no such block) is None."""
    if not isinstance(value, dict) or value.get("mode") != "quick":
        return None
    times = [item for item in value.get("times_s") or []
             if isinstance(item, (int, float)) and not isinstance(item, bool) and item >= 0]
    above, frames, duration = value.get("above_s"), value.get("frames"), value.get("duration_s")
    return {"mode": "quick",
            "above_s": above if isinstance(above, int) and not isinstance(above, bool) else None,
            "frames": frames if isinstance(frames, int) and not isinstance(frames, bool) else len(times),
            "duration_s": duration if positive_number(duration) else None,
            "times_s": times}


def frame_why(frame: dict[str, Any]) -> dict[str, Any]:
    """A frame's `source`, and on a change frame its reason and score, where the plan said them."""
    why: dict[str, Any] = {}
    if frame.get("source") in FRAME_SOURCES:
        why["source"] = frame["source"]
    if frame.get("reason") in CHANGE_REASONS:
        why["reason"] = frame["reason"]
        if isinstance(frame.get("change_units"), int) and not isinstance(frame.get("change_units"), bool):
            why["change_units"] = frame["change_units"]
    return why


def overview_block(overview: Any, ref_key: str) -> dict[str, Any] | None:
    """The overview sheets as the evidence keeps them: where each sheet is and which seconds it covers."""
    if not isinstance(overview, dict) or overview.get("status") != "available":
        return None
    numbers = {key: overview.get(key) for key in ("stride_s", "columns", "rows", "tile_long_edge_px", "seconds")}
    if not all(isinstance(numbers[key], int) and numbers[key] > 0 for key in ("stride_s", "columns", "rows")):
        return None
    sheets = []
    for number, sheet in enumerate(overview.get("sheets") or [], start=1):
        sheet = sheet if isinstance(sheet, dict) else {}
        if not isinstance(sheet.get("from_s"), (int, float)) or not isinstance(sheet.get("to_s"), (int, float)):
            continue
        sheets.append({"sheet_id": str(sheet.get("sheet_id") or f"overview-{number:02d}"),
                       "from_s": sheet["from_s"], "to_s": sheet["to_s"],
                       **({"tiles": sheet["tiles"]} if isinstance(sheet.get("tiles"), int) else {}),
                       "sha256": sheet.get("sha256"), "path": sheet.get(ref_key)})
    if not sheets:
        return None
    block = {key: value for key, value in numbers.items() if isinstance(value, int)}
    if isinstance(overview.get("read_until_s"), (int, float)):
        block["read_until_s"] = overview["read_until_s"]
    return {**block, "sheets": sheets}
# media.encoding closes to additional properties, so the writer filters to exactly its key set
# rather than passing a probe response through and discovering the mismatch at validation.
ENCODING_KEYS = {
    "video_codec", "video_bitrate_bps", "frame_rate", "audio_codec", "audio_bitrate_bps",
    "audio_sample_rate", "audio_channels", "integrated_loudness_lufs", "true_peak_dbfs",
    "loudness_segments",
}
FRAME_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
FRAME_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def materialise_frame_aliases(block: dict[str, Any], snapshot: Path, analysis: Path) -> None:
    """Bind staged pixels to their connector IDs by bytes, never by staging order.

    Hosts may stage only a subset and rename those images sequentially. The envelope still
    carries the full canonical frame list. Keep unavailable references untouched; copy a
    matching image under a portable name derived from its canonical ID; the evidence ID,
    not the filename, remains the reference. Different IDs can identify identical pixels.
    """
    if snapshot.is_symlink() or analysis.is_symlink():
        raise ValueError("frame roots must not be symlinks")
    snapshot, analysis = snapshot.resolve(), analysis.resolve()
    if (snapshot.name != "snapshot" or analysis.name != "analysis"
            or snapshot.parent != analysis.parent or not snapshot.is_dir()):
        raise ValueError("frame roots must be this run's sibling snapshot and analysis directories")
    items = block.get("items") or []
    wanted = {str(item.get("sha256")).lower() for item in items
              if FRAME_SHA256.fullmatch(str(item.get("sha256") or ""))}
    matches: dict[str, tuple[bytes, str]] = {}
    for folder, dirs, names in os.walk(snapshot, followlinks=False):
        directory = Path(folder)
        if any((directory / name).is_symlink() for name in dirs):
            raise ValueError("snapshot frame directories must not be symlinks")
        for name in sorted(names):
            source = directory / name
            if source.suffix.lower() not in FRAME_EXTENSIONS:
                continue
            if source.is_symlink() or not source.is_file():
                raise ValueError("snapshot frames must be regular files, not symlinks")
            body = source.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            if digest in wanted:
                matches.setdefault(digest, (body, source.suffix.lower()))
    if not matches:
        return
    # Keep aliases one level below the analysis directory: hosts may replay a nested run
    # with a bounded collection depth, so an extra frames/ level would lose these bytes.
    target = analysis
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("canonical frame directory must be a regular directory")
    target.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(target, 0o700)
    for item in items:
        match = matches.get(str(item.get("sha256") or "").lower())
        if match is None:
            continue
        frame_id = str(item.get("frame_id") or "")
        if (frame_id in {"", ".", ".."} or any(char in frame_id for char in ("/", "\\", "\0"))):
            raise ValueError("unsafe canonical frame_id")
        body, extension = match
        # IDs may contain '#' or Unicode, which some hosts cannot replay in filenames.
        # Hash the exact ID, never an ordinal or timestamp; keep the ID itself unchanged.
        name = "frame-" + hashlib.sha256(frame_id.encode("utf-8")).hexdigest() + extension
        destination = target / name
        if destination.is_symlink():
            raise ValueError("canonical frame destination must not be a symlink")
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != body:
                raise ValueError("canonical frame destination already contains different bytes")
        else:
            # Exclusive creation also refuses a destination appearing between the checks.
            with destination.open("xb") as stream:
                os.chmod(destination, 0o600)
                stream.write(body)
        item["path"] = str(destination)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def envelope_of(document: Any) -> dict[str, Any]:
    """An envelope, or the terminal envelope a deferred job resource carries."""
    record = as_record(document)
    if {"connector_id", "operation", "status"} <= set(record):
        return record
    inner = as_record(record.get("envelope"))
    if {"connector_id", "operation", "status"} <= set(inner):
        return inner
    if record.get("job_id") and not inner:
        raise ValueError(f"job {record.get('job_id')} carries no terminal envelope yet: pass it as "
                         "--deferred-incomplete <operation>=<job id> instead of the job resource")
    raise ValueError("not a connector envelope or a job resource carrying one")


def role_of(envelope: dict[str, Any]) -> str | None:
    if (envelope.get("connector_id") == "kabo-video"
            and envelope.get("operation") == "get_video_transcript"):
        return "captions"
    if (envelope.get("connector_id") == YOUTUBE_METADATA_CONNECTOR
            and str(envelope.get("operation")) == YOUTUBE_METADATA_OPERATION):
        return "metadata"
    if (envelope.get("connector_id") == TIKTOK_METADATA_CONNECTOR
            and str(envelope.get("operation")) == TIKTOK_METADATA_OPERATION):
        return "metadata"
    if (envelope.get("connector_id") in POST_CONNECTORS
            and str(envelope.get("operation")) == POST_OPERATION):
        return "public_post"
    if envelope.get("connector_id") != MEDIA_CONNECTOR:
        return None
    # A YouTube measurement now runs through the same hosted fetch as its keyframes and comes back
    # under that execution's name; it is still the measurement that was asked for.
    if envelope.get("operation") == "measure_media_signals_hosted_stream":
        return "measurements"
    return ROLE_OF_OPERATION.get(str(envelope.get("operation")))


def normalise_metadata(envelope: dict[str, Any]) -> dict[str, Any]:
    """Give the data API's row the shape the downloader's projection already has.

    Everything downstream reads ``data.video.<field>``. Normalising here rather than teaching
    each reader a second shape keeps one definition of what a metadata envelope looks like --
    and the fields are the same facts under different names, not different facts.
    """
    if (envelope.get("connector_id") == TIKTOK_METADATA_CONNECTOR
            and str(envelope.get("operation")) == TIKTOK_METADATA_OPERATION):
        return normalise_tiktok_metadata(envelope)
    if (envelope.get("connector_id") != YOUTUBE_METADATA_CONNECTOR
            or str(envelope.get("operation")) != YOUTUBE_METADATA_OPERATION):
        return envelope
    rows = as_record(envelope.get("data")).get("rows")
    row = as_record(rows[0]) if isinstance(rows, list) and rows else {}
    if not row:
        return envelope
    metrics = as_record(row.get("metrics"))
    thumbnails = row.get("thumbnails")
    # The connector orders the tiers highest first; take its first rather than re-ranking.
    cover = as_record(thumbnails[0]).get("url") if isinstance(thumbnails, list) and thumbnails else None

    def count(value: Any) -> Any:
        # The data API returns counts as strings; the downloader returned integers.
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return value if isinstance(value, int) else None

    normalised = dict(envelope)
    normalised["data"] = {
        "video": {
            "id": row.get("id"),
            "title": row.get("title"),
            "description": row.get("description"),
            "webpage_url": row.get("source_url"),
            "channel": row.get("channel_title"),
            "channel_id": row.get("channel_id"),
            "duration_seconds": row.get("duration_seconds"),
            # RFC 3339 here, compact YYYYMMDD from the downloader. content_ref() already parses
            # both, and an ISO instant is the more precise of the two -- do not truncate it.
            "upload_date": row.get("published_at"),
            "view_count": count(metrics.get("views")),
            "like_count": count(metrics.get("likes")),
            "comment_count": count(metrics.get("comments")),
            "thumbnail": cover,
            "tags": row.get("tags") or [],
        }
    }
    return normalised


def unresolved_safe_id(ref: dict[str, Any]) -> str:
    """The content id for an evidence id; an unresolved short link gets a stable token from its URL, never a guess."""
    if ref.get("content_id"):
        return str(ref["content_id"])
    return "unresolved-" + hashlib.sha256(str(ref.get("permalink") or "").encode("utf-8")).hexdigest()[:12]


def normalise_tiktok_metadata(envelope: dict[str, Any]) -> dict[str, Any]:
    """The aweme row of tiktok_search_get_video in the downloader's data.video shape, plus the sound it declares."""
    video = as_record(as_record(envelope.get("data")).get("video"))
    if not video:
        return envelope
    stats = as_record(video.get("statistics"))
    music = as_record(video.get("music"))
    author = as_record(video.get("author"))

    def count(value: Any) -> Any:
        return value if type(value) is int else None

    created = video.get("create_time")
    published = (datetime.fromtimestamp(created, timezone.utc).isoformat().replace("+00:00", "Z")
                 if type(created) is int and created > 0 else None)
    duration_ms = as_record(video.get("video")).get("duration")
    tags = [str(item.get("hashtag_name")) for item in video.get("text_extra") or []
            if isinstance(item, dict) and item.get("type") == 1 and item.get("hashtag_name")]
    desc = video.get("desc")
    normalised = dict(envelope)
    normalised["data"] = {"video": {
        "id": str(video["aweme_id"]) if video.get("aweme_id") else None,
        "title": None,
        "description": desc if isinstance(desc, str) else None,
        "webpage_url": None,
        "channel": author.get("unique_id") or None,
        "channel_id": author.get("uid") or None,
        "duration_seconds": duration_ms / 1000 if type(duration_ms) in (int, float) and duration_ms > 0 else None,
        "upload_date": published,
        "view_count": count(stats.get("play_count")),
        "like_count": count(stats.get("digg_count")),
        "comment_count": count(stats.get("comment_count")),
        # The cover is an expiring signed CDN link, so it is not written into the evidence.
        "thumbnail": None,
        "tags": tags,
    }}
    if music:
        original = music.get("is_original_sound")
        normalised["data"]["audio"] = {
            "uses_original_audio": original if isinstance(original, bool) else None,
            "audio_id": str(music.get("id_str") or music.get("id")) if (music.get("id_str") or music.get("id")) else None,
            "artist_name": music.get("author") if isinstance(music.get("author"), str) else None,
            "song_name": music.get("title") if isinstance(music.get("title"), str) else None,
        }
    return normalised


def usable(envelope: dict[str, Any] | None) -> bool:
    return envelope is not None and envelope.get("status") in USABLE


def pick(envelopes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last usable response of one operation (a retry after a failure), else the last one."""
    for envelope in reversed(envelopes):
        if usable(envelope):
            return envelope
    return envelopes[-1] if envelopes else None


def limitation_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    record = as_record(value)
    message = record.get("message")
    return message.strip() if isinstance(message, str) and message.strip() else None


def carried_metadata(frames: dict[str, Any] | None) -> dict[str, Any] | None:
    """The public metadata a keyframe response carries as ``data.video``, as a metadata envelope.

    On the platforms the backend resolves through a paid vendor (Douyin, Xiaohongshu, Kuaishou) the
    keyframe job is the one billed resolution: it brings the metadata back with the frames, and a
    standalone metadata request answers ``unsupported`` without fetching anything. The projection is
    the same ``video`` shape the metadata operation returns, so it is read as that, named after the
    response it actually came in.
    """
    video = as_record(frames.get("data")).get("video") if usable(frames) else None
    if not isinstance(video, dict) or not video:
        return None
    carried = {key: frames.get(key) for key in ("schema_version", "connector_id", "operation", "provider",
                                                "request_id", "job_id", "evidence_ref", "raw_sha256", "retrieved_at")}
    # The keyframes round's completed_partial is about frames (the budget went to the opening), not metadata:
    # the attached video is a complete projection.
    carried.update(status="completed", limitations=[], data={"video": video})
    return carried


def video_identity(envelopes: list[dict[str, Any]], platform: Any, file_id: str | None = None) -> dict[str, Any] | None:
    """The video the backend says these responses are about (``data.video_identity``), or None.

    Short links only name a video after the server resolved them, and a transcript-only export has no
    metadata round, so this is where their id comes from. Every response that carries one must name
    the same video, on the platform the request names.
    """
    found: dict[str, Any] | None = None
    for envelope in envelopes:
        identity = as_record(as_record(envelope.get("data")).get("video_identity")) if usable(envelope) else {}
        if not identity.get("platform_video_id"):
            continue
        key = (identity.get("platform"), str(identity.get("platform_video_id")))
        if found is not None and key != (found.get("platform"), str(found.get("platform_video_id"))):
            raise ValueError("the media responses name two different videos; build the evidence from one video's "
                             "responses only")
        found = identity
    if found is not None and file_id and str(found.get("platform_video_id")).lower() == file_id:
        # A video attached in Kabo (kabo-file:<id>) is named by its file id and is on no platform yet: the request's
        # platform is the one the creator named for it.
        return found
    if found is not None and found.get("platform") != platform:
        raise ValueError(f"the media responses identify a {found.get('platform')} video, but the request names "
                         f"{platform!r}: set the platform of the link the creator gave")
    return found


def content_ref(request: dict[str, Any], metadata: dict[str, Any] | None, published_at: str | None,
                post_published_at: str | None = None, identity: dict[str, Any] | None = None,
                metadata_ids: list[str] | None = None) -> dict[str, Any]:
    source = as_record(request.get("source"))
    video = as_record(as_record(metadata.get("data")).get("video")) if usable(metadata) else {}
    platform = source.get("platform")
    if platform not in public_video_sources.platform_ids():
        raise ValueError(f"request source.platform is {platform!r}, but the evidence is for one platform "
                         f"({', '.join(sorted(public_video_sources.platform_ids()))}): set the platform the "
                         "creator named in the request")
    file_ref = source.get("file_ref")
    permalink = source.get("url") or video.get("webpage_url")
    # A short link (v.douyin.com, b23.tv, ...) has no readable id: the backend resolves it and writes it into every
    # result's video_identity, including transcript-only exports.
    # With no id in the request (an unresolved short link), take the id a metadata result of this run gives; with none it stays null, never guessed.
    content_id = (source.get("content_id") or video.get("id") or content_id_from_url(platform, permalink)
                  or as_record(identity).get("platform_video_id")
                  or next((str(item) for item in metadata_ids or [] if item), None)
                  or (Path(str(file_ref)).stem if file_ref else None))
    if not permalink and file_ref:
        # An unpublished draft has no platform address; its locator is the file itself.
        permalink = Path(str(file_ref)).expanduser().resolve().as_uri()
    if not permalink:
        raise ValueError("content_ref needs the video's URL or file_ref: put the original post or video link in "
                         "the request's source.url")
    # The post projection's publish time only fills in what metadata did not give: metadata is the platform's own
    # answer about its video, and takes priority when both exist.
    published = published_at or video.get("upload_date") or post_published_at
    if not published and source.get("subject_state") == "own_unpublished":
        published = "unpublished"
    precise = False
    if published and published != "unpublished":
        text = str(published).strip()
        try:
            if re.fullmatch(r"\d{8}", text):  # the metadata's compact YYYYMMDD upload date
                # Written as an ISO date: the brief and the report quote it, and 20260919 reads as a number.
                published = datetime.strptime(text, "%Y%m%d").date().isoformat()
            elif "T" in text:
                datetime.fromisoformat(text.replace("Z", "+00:00"))
                precise = True
            else:
                datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"published_at {text!r} is neither a date nor an ISO date-time") from None
    return {
        "platform": platform,
        "content_id": str(content_id) if content_id else None,
        "permalink": str(permalink),
        "published_at": str(published) if published else "unknown",
        "published_at_precision": "second" if precise else "day",
        # Only a time the creator stated with its offset says which clock it was read on.
        "published_at_timezone_source": "creator_confirmed" if published_at and precise and ZONED.search(str(published_at)) else "unknown",
        "format": source.get("declared_format") or "unknown",
        "owner_ref": video.get("channel") or None,
    }


def acquisition_entry(envelope: dict[str, Any]) -> dict[str, Any]:
    status = envelope.get("status")
    return {
        "step": "connector_call",
        "connector_id": str(envelope.get("connector_id")),
        "operation": str(envelope.get("operation")),
        "connector_request_id": str(envelope.get("request_id") or envelope.get("job_id") or "unknown"),
        "status": status if status in ACQUISITION_STATUSES else "failed",
        "retrieved_at": envelope.get("retrieved_at"),
        "raw_hash": envelope.get("raw_sha256"),
        "raw_retained_outside_git": True,
        "credits_charged": None,
        "note": None,
    }


def viewer_acquisition_entry(viewer: dict[str, Any]) -> dict[str, Any]:
    """One ledger entry for the whole-video viewing: the start call and every poll of the same analysis."""
    run = viewer.get("run") or {}
    polls = int(viewer.get("polls") or 0)
    return {
        "step": "connector_call",
        "connector_id": viewer_response.CONNECTOR,
        "operation": viewer_response.START_TOOL,
        "connector_request_id": str(run.get("id") or viewer.get("idempotency_key") or "unknown"),
        "status": viewer_response.acquisition_status(viewer),
        "retrieved_at": run.get("updatedAt"),
        "raw_hash": viewer.get("raw_sha256"),
        "raw_retained_outside_git": True,
        "credits_charged": None,
        "note": (f"whole-video viewing; final state read after {polls} {viewer_response.POLL_TOOL} poll(s); "
                 "only timestamped notes and the transcript were kept, every score, verdict and piece of advice "
                 "was discarded"),
    }


def local_acquisition_entry(step: dict[str, Any], input_sha256: str | None) -> dict[str, Any]:
    """One step this run ran here, recorded as what it was.

    The connector keys are omitted rather than set to null or to a placeholder. Nothing was asked of
    a connector, so an entry saying `connector_id: "local"` or `connector_request_id: "unknown"`
    would be describing a call that never happened -- and the schema refuses those keys on this
    branch for that reason, including when they are present and null.
    """
    status = step.get("status")
    return {
        "step": "local_extraction",
        "operation": str(step.get("operation")),
        "status": status if status in ACQUISITION_STATUSES else "failed",
        "tool": str(step.get("tool")),
        "tool_version": str(step.get("tool_version") or "unreported"),
        "invocation_sha256": str(step.get("invocation_sha256") or ""),
        "input_sha256": input_sha256,
        "retrieved_at": step.get("started_at"),
        "raw_hash": None,
        "raw_retained_outside_git": True,
        "credits_charged": None,
        "note": step.get("note"),
    }


# The two single-call tools observe_video.py makes beside the observation, as persisted there (acv-side-call/v1).
SIDE_SCHEMA = "acv-side-call/v1"
SIDE_CONNECTOR = "kabo-video-insights"
SONG_STATUSES = {"matched", "platform_metadata", "no_match", "unavailable", "in_progress", "quota_exceeded",
                 "unsupported_platform"}
COMMENT_STATUSES = {"ok": "available", "too_few_comments": "too_few_comments",
                    "unsupported_platform": "unsupported_platform"}
SIDE_WORDS = {"song": "The song recognition", "comment_summary": "The comment summary"}


def side_record(value: Any, name: str) -> dict[str, Any]:
    """A persisted side-call record, checked; ValueError when it is not one observe_video.py wrote for `name`."""
    if not isinstance(value, dict) or value.get("schema_version") != SIDE_SCHEMA or value.get("name") != name:
        raise ValueError(f"the {name} file is not a side-call record observe_video.py persisted")
    return value


def link(value: Any) -> str | None:
    return value if isinstance(value, str) and re.match(r"^https?://\S+$", value) else None


def text_or_none(value: Any, limit: int = 600) -> str | None:
    return " ".join(value.split())[:limit] if isinstance(value, str) and value.strip() else None


def side_failure(record: dict[str, Any]) -> dict[str, Any] | None:
    error = record.get("error")
    if not isinstance(error, dict):
        return None
    return {"code": str(error.get("code") or "tool_error"), "retryable": error.get("retryable") is True}


def song_block(record: dict[str, Any]) -> dict[str, Any]:
    """`song_identification`: what identify_video_song answered, or why there is no answer."""
    block: dict[str, Any] = {"status": "not_attempted", "source": None, "reason": record.get("skipped"),
                             "sample_start_s": None, "song": None, "platform_audio": None, "failure": None}
    answer = record.get("answer")
    if not record.get("attempted"):
        return block
    if not isinstance(answer, dict) or answer.get("status") not in SONG_STATUSES:
        failure = side_failure(record) or {"code": "unreadable_result", "retryable": False}
        return {**block, "status": "failed", "reason": failure["code"], "failure": failure}
    song = answer.get("song") if isinstance(answer.get("song"), dict) else None
    named = song if song and text_or_none(song.get("title")) and text_or_none(song.get("artist")) else None
    tag = answer.get("platform_audio") if isinstance(answer.get("platform_audio"), dict) else None
    status = answer["status"]
    if status == "matched" and named is None:
        return {**block, "status": "failed", "reason": "unreadable_result",
                "failure": {"code": "unreadable_result", "retryable": False}}
    start = answer.get("sample_start_s")
    return {**block, "status": status,
            "source": answer.get("source") if answer.get("source") in {"recognition", "platform_tag"} else None,
            "reason": text_or_none(answer.get("reason"), 80),
            "sample_start_s": start if type(start) is int and start >= 0 else None,
            "song": ({"title": text_or_none(named["title"], 200), "artist": text_or_none(named["artist"], 200),
                      "album": text_or_none(named.get("album"), 200), "url": link(named.get("url"))}
                     if named else None),
            "platform_audio": ({"title": text_or_none(tag.get("title"), 200), "credit": text_or_none(tag.get("credit"), 200),
                                "original": tag.get("original") if isinstance(tag.get("original"), bool) else None,
                                "url": link(tag.get("url"))}
                               if tag and text_or_none(tag.get("title")) else None)}


def audience_block(record: dict[str, Any]) -> dict[str, Any]:
    """`audience_response`: the comment summary summarize_video_comments returned (paraphrased, from a sample of the
    top comments, with no comment text), or why there is none. Only the contract's fields are kept."""
    block: dict[str, Any] = {"status": "not_attempted", "reason": record.get("skipped"), "platform": None,
                             "total_comments": None, "sample_size": None, "language": None, "sentiment": None,
                             "summary": None, "themes": [], "questions": [], "requests": [], "controversy": None,
                             "retrieved_at": None, "failure": None}
    answer = record.get("answer")
    if not record.get("attempted"):
        return block
    if not isinstance(answer, dict) or answer.get("status") not in COMMENT_STATUSES:
        failure = side_failure(record) or {"code": "unreadable_result", "retryable": False}
        return {**block, "status": "failed", "reason": failure["code"], "failure": failure}

    def count(value: Any) -> int | None:
        return value if type(value) is int and value >= 0 else None

    sentiment = answer.get("sentiment") if isinstance(answer.get("sentiment"), dict) else None
    if sentiment is not None and not all(count(sentiment.get(key)) is not None and sentiment[key] <= 100
                                         for key in ("positive", "neutral", "negative")):
        sentiment = None
    themes = []
    for item in answer.get("themes") or []:
        if isinstance(item, dict) and text_or_none(item.get("label")):
            share = item.get("share")
            themes.append({"label": text_or_none(item["label"], 120),
                           "description": text_or_none(item.get("description"), 400),
                           "share": share if isinstance(share, (int, float)) and not isinstance(share, bool)
                           and 0 <= share <= 100 else None})
    controversy = answer.get("controversy") if isinstance(answer.get("controversy"), dict) else None
    status = COMMENT_STATUSES[answer["status"]]
    return {**block, "status": status, "reason": None if status == "available" else answer["status"],
            "platform": answer.get("platform") if isinstance(answer.get("platform"), str) else None,
            "total_comments": count(answer.get("total_comments")), "sample_size": count(answer.get("sample_size")),
            "language": text_or_none(answer.get("language"), 35),
            "sentiment": ({key: sentiment[key] for key in ("positive", "neutral", "negative")} if sentiment else None),
            "summary": text_or_none(answer.get("summary"), 1200), "themes": themes,
            "questions": [text for text in (text_or_none(item, 300) for item in answer.get("questions") or []) if text],
            "requests": [text for text in (text_or_none(item, 300) for item in answer.get("requests") or []) if text],
            "controversy": ({"flagged": controversy.get("flagged") is True,
                             "note": text_or_none(controversy.get("note"), 300)} if controversy else None),
            "retrieved_at": text_or_none(answer.get("retrieved_at"), 40)}


def side_acquisition_entry(record: dict[str, Any], status: str) -> dict[str, Any]:
    """One ledger entry for an attempted side call."""
    digest = record.get("raw_sha256")
    return {
        "step": "connector_call",
        "connector_id": SIDE_CONNECTOR,
        "operation": str(record.get("tool")),
        "connector_request_id": f"{record.get('tool')}:{str(digest)[:16]}" if digest else str(record.get("tool")),
        "status": ("failed" if status == "failed" else "unsupported" if status == "unsupported_platform"
                   else "completed"),
        "retrieved_at": record.get("saved_at"),
        "raw_hash": digest,
        "raw_retained_outside_git": True,
        "credits_charged": None,
        "note": "one bounded call beside the observation, read once",
    }


def side_limitation(name: str, status: str) -> str | None:
    """The plain line for a side call that brought nothing usable; None when it did."""
    what = SIDE_WORDS[name]
    if name == "comment_summary":
        if status == "available":
            return None
        return {
            "not_attempted": "The comments were not read: an uploaded file has no public comments to summarise.",
            "unsupported_platform": "The comments were not read: comment summaries cover YouTube, Instagram and "
                                    "TikTok links only.",
            "too_few_comments": "The comments were not read: the post has too few comments to summarise.",
        }.get(status, "The comments were not read: the comment summary is not available here.")
    if status in {"matched", "platform_metadata"}:
        return None
    return {
        "not_attempted": f"{what} was not run: an uploaded file is named from its own data only.",
        "unsupported_platform": f"{what} covers Instagram, YouTube and TikTok links only.",
        "no_match": f"{what} found no match in the video's audio.",
    }.get(status, f"{what} brought no answer here.")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 2)


def loudness_summary(loudness: dict[str, Any]) -> dict[str, Any] | None:
    """What an analysis cites from a several-hundred-sample series: the lead-in, the range, the mean.

    Copying the series itself would move the cost of reading it from the one envelope that holds it
    to every consumer of the evidence, which is the opposite of the point. The envelope keeps the
    samples; a reading that needs one goes there.
    """
    points = []
    for sample in loudness.get("series") or []:
        record = as_record(sample)
        at, value = record.get("t_seconds"), record.get("momentary_lufs")
        if isinstance(at, (int, float)) and isinstance(value, (int, float)):
            points.append((float(at), float(value)))
    if not points:
        return None
    points.sort()
    values = [value for _, value in points]
    audible = [(at, value) for at, value in points if value > SILENT_LUFS]
    first_at, first_value = audible[0] if audible else (None, None)
    working = [value for _, value in audible] or values
    # The mean is of the audible track. A digitally silent sample is a sentinel near -120 LUFS, and
    # averaging it in says a video with a quiet opening is quieter throughout than it is: five
    # silent seconds at the head of a thirty-second clip drag the mean down by about twenty dB.
    interval = loudness.get("interval_s")
    lead_in = None
    if isinstance(first_at, float) and isinstance(interval, (int, float)):
        lead_in = round(max(0.0, first_at - float(interval)), 3)
    return {
        "interval_s": interval if isinstance(interval, (int, float)) else None,
        "samples": len(points),
        "mean_lufs": round(sum(working) / len(working), 2),
        "min_lufs": round(min(values), 2),
        "max_lufs": round(max(values), 2),
        "p10_lufs": percentile(working, 0.1),
        "p90_lufs": percentile(working, 0.9),
        "lead_in_silence_s": lead_in,
        "first_audible_s": first_at,
        "first_audible_lufs": round(first_value, 2) if isinstance(first_value, float) else None,
    }


def probed_block(measurements: dict[str, Any] | None) -> dict[str, Any] | None:
    """The measured file, as numbers. Every reading of them is an observation and lives elsewhere."""
    if not usable(measurements):
        return None
    data = as_record(measurements.get("data"))
    block: dict[str, Any] = {}
    for key, allowed in PROBED_KEYS.items():
        value = as_record(data.get(key))
        kept = {name: item for name, item in value.items() if name in allowed}
        if kept:
            block[key] = kept
    summary = loudness_summary(as_record(data.get("loudness")))
    if summary:
        block["loudness"] = summary
        block["mean_volume_db"] = summary["mean_lufs"]
    for key in ("measured", "unavailable"):
        value = data.get(key)
        if isinstance(value, list):
            block[key] = [item for item in value if isinstance(item, str)]
    coverage = partial_coverage(data.get("coverage"))
    if block and coverage:
        # A quick first read measured only the opening: every number above is about that stretch alone.
        block["coverage"] = coverage
    return block or None


def metadata_public_metrics(metadata: dict[str, Any] | None, platform: str | None = None) -> list[dict[str, Any]]:
    """Public counters from the normalized metadata, without inventing missing values."""
    if not usable(metadata):
        return []
    video = as_record(as_record(metadata.get("data")).get("video"))
    metrics = []
    source = f"{metadata.get('connector_id')}.{metadata.get('operation')}"
    for native_name, metric in METADATA_COUNTERS.items():
        # A count the platform does not publish (Douyin and Xiaohongshu views) is not an observation even when
        # metadata says 0: drop it and record it as unavailable.
        if platform is not None and not public_video_sources.publishes(platform, metric):
            continue
        value = video.get(native_name)
        # Zero is observed; null, booleans and non-finite numbers are not counters.
        if type(value) is int or (type(value) is float and math.isfinite(value)):
            basis = VIEW_BASIS_NOTES.get(video.get("view_count_basis")) if native_name == "view_count" else None
            metrics.append({
                "native_name": native_name, "value": value, "equals_owner_metric": None,
                "note": (f"Public {native_name} from {source}"
                         + (f", {basis}" if basis else "") + "; not reach or an owner metric."),
            })
    return metrics


def graphql_post(row: dict[str, Any]) -> tuple[Any, list[tuple[str, Any, str | None]], dict[str, Any]]:
    """Caption, counters and sound of an old single-operation post row (GraphQL field names)."""
    edges = as_record(row.get("edge_media_to_caption")).get("edges")
    caption = (as_record(as_record(edges[0]).get("node")).get("text")
               if isinstance(edges, list) and edges else None)
    counters = [
        ("video_play_count", row.get("video_play_count"), PLAYS_NOTE),
        ("edge_media_preview_like.count", as_record(row.get("edge_media_preview_like")).get("count"), None),
        ("comment_count", row.get("comment_count"), None),
    ]
    return caption, counters, as_record(row.get("clips_music_attribution_info"))


def projected_post(row: dict[str, Any],
                   facts: dict[str, Any]) -> tuple[Any, list[tuple[str, Any, str | None]], dict[str, Any]]:
    """Caption, counters and sound of a `kabo.instagram_post.v1` post; also its publish time."""
    # native_name writes the field path in the projection, and the report cites exactly this name. IG views and the
    # combined IG+FB value are recorded separately, and the combined value does not pass as IG views; when the
    # author hides likes, likes is null, so record one limitation saying it is not 0.
    # thumbnail_url is a CDN link that expires, so it is not written into the evidence as a cover address.
    metrics = as_record(row.get("metrics"))
    if metrics.get("likes_hidden") is True:
        facts["limitations"] = ["The post hides its like count, so likes are unavailable, not zero."]
    if isinstance(row.get("published_at"), str) and row["published_at"].strip():
        facts["published_at"] = row["published_at"]
    counters = [
        ("metrics.plays_instagram", metrics.get("plays_instagram"),
         "An Instagram-only play count, which is neither reach nor an owner view figure."),
        ("metrics.plays_combined", metrics.get("plays_combined"),
         "Instagram and Facebook plays combined: not an Instagram-only count, and neither reach nor an owner "
         "view figure."),
        ("metrics.likes", None if metrics.get("likes_hidden") is True else metrics.get("likes"), None),
        ("metrics.comments", metrics.get("comments"), None),
    ]
    return row.get("caption"), counters, as_record(row.get("audio"))


def post_facts(post: dict[str, Any] | None) -> dict[str, Any]:
    """Platform facts about the published post: its public counters, its caption, its sound.

    These were retrieved on every Instagram run and then dropped on the floor, so an analysis that
    wanted the play count had to read the raw envelope and retype the number. A figure that only
    ever exists because a model typed it is not evidence, and the shape check downstream - which
    grounds every number in the report against this object and the analysis - was grounding those
    numbers against the analysis alone.
    """
    if not usable(post):
        return {}
    data = as_record(post.get("data"))
    row = as_record(data.get("post"))
    if not row:
        return {}
    facts: dict[str, Any] = {}
    if data.get("projection") == POST_PROJECTION:
        caption, counters, sound = projected_post(row, facts)
    else:
        caption, counters, sound = graphql_post(row)
    if isinstance(caption, str) and caption.strip():
        facts["caption"] = caption
        facts["hashtags"] = HASHTAG.findall(caption)  # the creator's own order
    metrics = []
    for native_name, value, note in counters:
        # null and booleans are not counts: if it cannot be obtained, do not write it, and do not treat it as 0.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics.append({"native_name": native_name, "value": value,
                            "equals_owner_metric": None, "note": note})
    if metrics:
        facts["public_metrics"] = metrics
    if sound:
        facts["audio_attribution"] = {
            "uses_original_audio": sound.get("uses_original_audio"),
            "audio_id": sound.get("audio_id"),
            "artist_name": sound.get("artist_name"),
            "song_name": sound.get("song_name"),
            # No registered connector supplies audio usage velocity or competition.
            "trend_metrics_available": False,
        }
    derived = []
    caption = facts.get("caption")
    if isinstance(caption, str):
        derived.append({
            "name": "caption_length_characters", "formula": "len(caption)",
            "formula_version": "v1", "inputs": ["content_metadata.caption"],
            "value": len(caption), "unit": "characters", "denominator_known": True, "caveat": None,
        })
        derived.append({
            "name": "caption_hashtag_count", "formula": "count of '#' tokens in caption",
            "formula_version": "v1", "inputs": ["content_metadata.caption"],
            "value": len(facts.get("hashtags") or []), "unit": "hashtags",
            "denominator_known": True, "caveat": None,
        })
    if derived:
        facts["derived"] = derived
    return facts


# measure_audio_local.py's block, as the evidence carries it: everything but its notes (already limitations) and
# the per-second loudness series (it stays in the local artifact, as a connector's series stays in its envelope).
LOCAL_AUDIO_KEYS = {
    "schema_version", "status", "measured", "unavailable", "skipped", "duration_s", "measured_until_s",
    "speech_source", "loudness", "segments", "voice", "clarity", "pulse", "onsets", "stereo", "cut_alignment",
    "findings", "listen_check", "thresholds",
}
AUDIO_SEGMENT_KEYS = {"start_s", "end_s", "duration_s", "label", "modulation"}
AUDIO_FINDING_KEYS = {"id", "measure", "claim", "confidence", "value", "threshold", "at_s", "end_s"}


def local_audio_block(audio: Any) -> dict[str, Any] | None:
    if not isinstance(audio, dict) or audio.get("schema_version") != "local-audio.v1":
        return None
    block = {key: value for key, value in audio.items() if key in LOCAL_AUDIO_KEYS}
    if isinstance(block.get("loudness"), dict):
        block["loudness"] = {key: value for key, value in block["loudness"].items() if key != "series_1s"}
    block["segments"] = [{key: value for key, value in as_record(item).items() if key in AUDIO_SEGMENT_KEYS}
                         for item in block.get("segments") or []]
    block["findings"] = [{key: value for key, value in as_record(item).items() if key in AUDIO_FINDING_KEYS}
                         for item in block.get("findings") or []]
    return block


def media_block(frames: dict[str, Any] | None, metadata: dict[str, Any] | None,
                local: dict[str, Any] | None = None,
                measurements: dict[str, Any] | None = None,
                captions: dict[str, Any] | None = None,
                stated_duration_s: float | None = None) -> dict[str, Any]:
    if local is not None:
        facts = as_record(local.get("media"))
        duration = facts.get("duration_s")
        encoding = {key: value for key, value in as_record(facts.get("encoding")).items()
                    if key in ENCODING_KEYS}
        # `declared` and `discrepancies` stay absent on this path, and that is correct rather than
        # missing: nothing declared a duration to disagree with. The platform's own numbers are not
        # here because the platform was never asked -- this is the file the creator exported.
        local_block = {
            "status": "available" if isinstance(duration, (int, float)) and duration > 0 else "unavailable",
            "duration_s": duration,
            "duration_source": "local_probe" if isinstance(duration, (int, float)) and duration > 0 else "unavailable",
            "width": facts.get("width"),
            "height": facts.get("height"),
            "has_audio": facts.get("has_audio"),
            "encoding": encoding or None,
        }
        # Measured here with the connector's thresholds and in its shape, so it reads through the
        # same filter: a reader of `probed` never needs to know which side measured the file.
        signals = facts.get("signals")
        probed = probed_block({"status": "completed", "data": signals}) if isinstance(signals, dict) else None
        if probed:
            local_block["probed"] = probed
        audio = local_audio_block(facts.get("audio"))
        if audio:
            local_block["audio"] = audio
        return local_block
    observed = as_record(frames.get("data")).get("duration_s") if usable(frames) else None
    declared = as_record(as_record(metadata.get("data")).get("video")).get("duration_seconds") if usable(metadata) else None
    observed = observed if isinstance(observed, (int, float)) and observed > 0 else None
    declared = declared if isinstance(declared, (int, float)) and declared > 0 else None
    # Douyin, Xiaohongshu and Kuaishou make no separate metadata call, so a transcript-only run had
    # no duration at all and a one-cue transcript could not be closed as a subtitle file. The
    # transcript response carries the platform-declared duration for them; it ranks last.
    spoken = as_record(captions.get("data")).get("duration_seconds") if usable(captions) else None
    spoken = spoken if isinstance(spoken, (int, float)) and spoken > 0 else None
    # The measurement probes the same downloaded file the keyframes do: on a whole-video run it is the call that
    # learns the duration before the viewing starts, and often the only one that carries it.
    measured = as_record(measurements.get("data")).get("duration_s") if usable(measurements) else None
    measured = measured if isinstance(measured, (int, float)) and not isinstance(measured, bool) and measured > 0 else None
    stated = (stated_duration_s if isinstance(stated_duration_s, (int, float)) and stated_duration_s > 0 else None)
    if observed is not None:
        duration, source = float(observed), "connector_extract_keyframes"
    elif measured is not None:
        duration, source = float(measured), "connector_measure"
    elif declared is not None:
        duration, source = float(declared), "connector_metadata"
    elif spoken is not None:
        duration, source = float(spoken), "connector_transcript"
    elif stated is not None:
        # The duration the observation was given (observe_video.py --duration-s) or learned outside these
        # envelopes; it ranks last, below anything fetched about this copy.
        duration, source = float(stated), "host_supplied"
    else:
        duration, source = None, "unavailable"
    block: dict[str, Any] = {
        "status": "available" if duration is not None else ("not_attempted" if frames is None and metadata is None else "unavailable"),
        "duration_s": duration,
        "duration_source": source,
        "width": None,
        "height": None,
        "has_audio": None,
    }
    # Where the media could only be fetched once, the keyframe job measures the same file it sampled
    # and carries the result in the measurement operation's shape. A separate measurement response,
    # when one arrived, still wins: it is the call that was asked for.
    carried = as_record(as_record(frames.get("data")).get("signals")) if usable(frames) else {}
    if not usable(measurements) and carried:
        measurements = {"status": "completed", "data": carried}
    probed = probed_block(measurements)
    if probed and duration is not None:
        # The connector leaves the span a file ends inside open (no end line was printed); the
        # evidence wants a number there, and with the length known its end is the end of the file.
        for key in ("silence", "freeze"):
            for span in as_record(probed.get(key)).get("spans") or []:
                if isinstance(span, dict) and span.get("end_s") is None and isinstance(span.get("start_s"), (int, float)):
                    span["end_s"] = round(duration, 3)
                    span["duration_s"] = round(max(0.0, duration - span["start_s"]), 3)
    if probed:
        block["probed"] = probed
        framing = as_record(probed.get("framing"))
        # The measured frame is the one viewers received; nothing declared it, so this fills a
        # field that has been null on every connector run rather than contradicting one.
        for field in ("width", "height"):
            value = framing.get(field)
            if isinstance(value, int) and value > 0:
                block[field] = value
    if usable(metadata):
        block["declared"] = {"width": None, "height": None, "duration_s": declared}
        # One second is the precision the platforms declare durations at.
        if observed is not None and declared is not None and abs(float(observed) - float(declared)) > 1:
            block["discrepancies"] = [{"field": "duration_s", "declared": declared, "observed": observed}]
    return block


def past_end_notes(block: dict[str, Any], duration_s: float | None) -> list[dict[str, Any]]:
    """Remove from `block` the whole-video notes that start after the video ends; return them.

    The viewer reports its own times. On a seven-minute video it once placed notes at 637 and 658 seconds of a
    417.5-second video, and another at 209 s where the frames showed the moment at 126.8 s: it read 2:09 as 209
    seconds. A note past the end cannot be placed, so it is dropped and named; it is never silently converted."""
    if not isinstance(duration_s, (int, float)) or not block.get("items"):
        return []
    limit_ms = (duration_s + transcript_checks.END_TOLERANCE_S) * 1000
    dropped = [item for item in block["items"] if item["start_ms"] > limit_ms]
    if dropped:
        block["items"] = [item for item in block["items"] if item["start_ms"] <= limit_ms]
        if not block["items"]:
            block.update(status="unavailable", failure={"code": "no_observations", "retryable": False})
    return dropped


def minutes_read_as_seconds(seconds: float, duration_s: float) -> str | None:
    """`2:09` when `seconds` (129 s) looks like minutes:seconds read as plain seconds (209) and fits the video."""
    whole = int(seconds)
    minutes, rest = divmod(whole, 100)
    if minutes and rest < 60 and minutes * 60 + rest <= duration_s + transcript_checks.END_TOLERANCE_S:
        return f"{minutes}:{rest:02d}"
    return None


def past_end_limitation(dropped: list[dict[str, Any]], duration_s: float) -> str:
    named = ", ".join(f"{item['id']} ({item['start_ms'] / 1000:g}s)" for item in dropped)
    text = (f"Whole-video notes {named} start after the end of this {duration_s:g}s video and were dropped: "
            "the viewer's times for them cannot be placed.")
    readings = [(item, minutes_read_as_seconds(item["start_ms"] / 1000, duration_s)) for item in dropped]
    if readings and all(reading for _, reading in readings):
        shown = ", ".join(f"{item['start_ms'] / 1000:g}s as {reading}" for item, reading in readings)
        text += (f" Their times look like minutes:seconds read as seconds ({shown}), so the other notes' times "
                 "may be misread the same way: check each against the frames or measured cuts before citing it. "
                 "No time was converted.")
    else:
        text += " Check the other notes' times against the frames or measured cuts before citing them."
    return text


def cues_from(records: Any) -> list[dict[str, Any]]:
    """Cue records to evidence cues, in one place.

    Both the connector path and a creator's subtitle file arrive here. The millisecond-to-second
    conversion, the blank-text drop and the rounding are written once on purpose: a second copy of
    this loop is exactly how a start pasted across unchanged came out a thousand times too large,
    and how a cue set was dropped because one field name did not match.
    """
    cues = []
    for cue in records or []:
        cue = as_record(cue)
        text = cue.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        # The connector carries each start in milliseconds; the evidence carries seconds.
        if isinstance(cue.get("start_ms"), (int, float)):
            start = round(float(cue["start_ms"]) / 1000.0, 3)
        elif isinstance(cue.get("start_s"), (int, float)):
            start = round(float(cue["start_s"]), 3)
        else:
            continue
        cues.append({"start_s": start, "text": text.strip()})
    return cues


def local_transcript_block(local: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """The transcript a creator handed over, as evidence.

    `origin` is `creator_supplied` and that is the load-bearing field. It is not machine-heard, so
    a line may be quoted as the creator's own wording; it is also not what the platform published
    and was never checked against the audio, so a second taken from it is the file's claim about
    the video rather than a measurement of it.
    """
    block: dict[str, Any] = {
        "status": "not_attempted",
        "status_basis": "no subtitle file was supplied for this run",
        "source_connector": None,
        "granularity": "none",
        "timestamps_available": False,
        "language_requested": as_record(request.get("acquire")).get("transcript_language"),
        "language": local.get("language"),
        "segment_count": None,
        "character_count": None,
        "text_sha256": None,
        "origin": None,
    }
    if local.get("status") in {"no_speech_detected", "no_audio_track"}:
        # Local speech recognition read the whole file and heard no words: that is the answer, not a failure.
        block["status"] = local["status"]
        block["status_basis"] = str(local.get("status_basis") or "local speech recognition heard no speech")
        block["origin"] = "speech_recognition"
        return block
    if local.get("status") != "available":
        block["status"] = "provider_error"
        block["status_basis"] = str(local.get("status_basis") or "the supplied subtitle file could not be read")
        return block

    cues = cues_from(local.get("cues"))
    plain = local.get("plain_text") if isinstance(local.get("plain_text"), str) else None
    name = local.get("source_file_name") or "the file the creator supplied"
    # A host's machine transcription of the same upload arrives through the same reader, and keeps
    # its own origin: its words are what the analysis heard, never the creator's exact wording.
    heard = local.get("origin") == "speech_recognition"
    if cues:
        text = "\n".join(cue["text"] for cue in cues)
        block.update({
            "status": "available", "granularity": "timestamped", "timestamps_available": True,
            "segment_count": len(cues), "cues": cues,
            "status_basis": (f"read {len(cues)} cues the host transcribed from this file by machine"
                             if heard else
                             f"read {len(cues)} cues from {name}, the subtitle file the creator "
                             "supplied; its timings were not checked against the media"),
        })
    elif plain and plain.strip():
        text = plain.strip()
        block.update({
            "status": "available", "granularity": "plain_text", "plain_text": text,
            "status_basis": ("read untimed text the host transcribed from this file by machine"
                             if heard else f"read untimed text from {name}, the file the creator supplied"),
        })
    else:
        block["status"] = "provider_error"
        block["status_basis"] = f"{name} carried no readable text"
        return block

    block["origin"] = "speech_recognition" if heard else "creator_supplied"
    block["character_count"] = len(text)
    block["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return block


def transcript_block(captions: dict[str, Any] | None, request: dict[str, Any]) -> dict[str, Any]:
    language_requested = as_record(request.get("acquire")).get("transcript_language")
    block: dict[str, Any] = {
        "status": "not_attempted",
        "status_basis": "no fetch_transcript response was persisted for this run",
        "source_connector": None,
        "granularity": "none",
        "timestamps_available": False,
        "language_requested": language_requested,
        "language": None,
        "segment_count": None,
        "character_count": None,
        "text_sha256": None,
    }
    if captions is None:
        return block
    data = as_record(captions.get("data"))
    block["source_connector"] = captions["connector_id"]
    operation = str(captions["operation"])
    native = captions["connector_id"] == "kabo-video"
    language = data.get("language")
    block["language"] = language if isinstance(language, str) and language else None
    if captions.get("status") not in USABLE:
        status = captions.get("status")
        why = ("the transcript path is not available for this video here" if status in NOT_A_FAILURE
               else "the call failed")
        block["status"] = "provider_error"
        block["status_basis"] = f"{operation} returned status {status!r}: {why}"
        return block
    if native and data.get("status") != "available":
        block.update(status="provider_error", status_basis=f"{operation} did not return an available transcript")
        return block
    if data.get("source_unavailable") is True:
        # The backend could not fetch the video itself (deleted, or limited to regions its servers
        # cannot reach). That is not "the video has no subtitle track", which would be a claim about
        # the video; it is a fact about this run, and every other dimension is missing with it.
        block.update(status="provider_error",
                     status_basis=f"{operation}: the source video itself could not be fetched "
                                  "(deleted or region-restricted), so no transcript exists for this run")
        return block
    cues = cues_from(data.get("cues"))
    plain = data.get("plain_text") if isinstance(data.get("plain_text"), str) else None
    origin = data.get("origin") if data.get("origin") in TRANSCRIPT_ORIGINS else None
    if cues:
        text = "\n".join(cue["text"] for cue in cues)
        block.update({
            "status": "available",
            "status_basis": f"{operation} returned {len(cues)} timed cues",
            "granularity": "timestamped",
            "timestamps_available": True,
            "segment_count": len(cues),
            "cues": cues,
        })
    elif plain and plain.strip():
        text = plain.strip()
        block.update({
            "status": "available",
            "status_basis": f"{operation} returned text without cue timing",
            "granularity": "plain_text",
            "plain_text": text,
        })
    else:
        block.update({
            "status": "provider_error" if native else "no_platform_captions",
            "status_basis": (f"{operation} completed with no readable transcript" if native else
                             "fetch_transcript completed with no cue text: the video exposes no subtitle track"),
        })
        block["origin"] = origin
        return block
    block["character_count"] = len(text)
    block["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    block["origin"] = origin
    coverage = partial_coverage(data.get("coverage"))
    if coverage:
        # A quick first read heard only the opening of a long video with no platform captions.
        block["coverage"] = coverage
    return block


def frames_block(frames: dict[str, Any] | None, local: dict[str, Any] | None = None) -> dict[str, Any]:
    empty = {"status": "not_attempted", "selection": "none", "requested_timestamps": None, "items": [],
             "sampling_plan": None, "origin": None}
    if local is not None:
        block = as_record(local.get("frames"))
        items = []
        for frame in block.get("items") or []:
            frame = as_record(frame)
            if not isinstance(frame.get("t_seconds"), (int, float)) or not frame.get("frame_id"):
                continue
            items.append({
                "frame_id": str(frame["frame_id"]),
                "t_seconds": float(frame["t_seconds"]),
                "sha256": frame.get("sha256"),
                "retained_outside_git": True,
                "path": frame.get("path"),
                **frame_why(frame),
            })
        plan = block.get("sampling_plan")
        plan = {key: value for key, value in plan.items() if key in SAMPLING_PLAN_KEYS} if isinstance(plan, dict) else None
        selection = block.get("selection") if block.get("selection") in FRAME_SELECTIONS else "none"
        if not items:
            return {**empty, "status": "unavailable", "selection": selection, "sampling_plan": plan}
        overview = overview_block(block.get("overview"), "path")
        return {
            "status": "available",
            "selection": selection,
            "requested_timestamps": [item["t_seconds"] for item in items],
            "items": items,
            "sampling_plan": plan,
            # Real pixels, sampled from the file the creator named. The same origin the connector
            # path sets, because it is the same claim: somebody looked at this frame this run.
            "origin": "extracted_frames",
            **({"overview": overview} if overview else {}),
        }
    if frames is None:
        return empty
    if not usable(frames):
        return {**empty, "status": "unavailable"}
    data = as_record(frames.get("data"))
    items = []
    for frame in data.get("frames") or []:
        frame = as_record(frame)
        if not isinstance(frame.get("t_seconds"), (int, float)) or not frame.get("frame_id"):
            continue
        items.append({
            "frame_id": str(frame["frame_id"]),
            "t_seconds": float(frame["t_seconds"]),
            "sha256": frame.get("sha256"),
            "retained_outside_git": True,
            "path": frame.get("object_ref"),
            **frame_why(frame),
        })
    plan = data.get("sampling_plan")
    plan = {key: value for key, value in plan.items() if key in SAMPLING_PLAN_KEYS} if isinstance(plan, dict) else None
    selection = data.get("selection") if data.get("selection") in FRAME_SELECTIONS else "none"
    if items:
        overview = overview_block(data.get("overview"), "object_ref")
        sampling = quick_sampling(data.get("sampling"))
        return {
            "status": "available",
            "selection": selection,
            "requested_timestamps": [item["t_seconds"] for item in items],
            "items": items,
            "sampling_plan": plan,
            "origin": "extracted_frames",
            **({"overview": overview} if overview else {}),
            # A quick first read of a long video: a small set of frames at fixed moments, not the full pass.
            **({"sampling": sampling} if sampling else {}),
        }
    observations = []
    for entry in data.get("observations") or []:
        entry = as_record(entry)
        if isinstance(entry.get("t_seconds"), (int, float)) and isinstance(entry.get("description"), str):
            text = entry.get("on_screen_text")
            observations.append({
                "t_seconds": float(entry["t_seconds"]),
                "description": entry["description"],
                "on_screen_text": text if isinstance(text, str) else None,
            })
    if observations:
        return {**empty, "status": "available", "origin": "model_observation", "observations": observations}
    return {**empty, "status": "unavailable"}


def thumbnail_tier(url: str) -> str:
    """The rendition a cover URL names. YouTube spells it in the file name; another platform's single
    cover is its default one, which is the only one it has."""
    stem = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for name, tier in YOUTUBE_THUMBNAIL_TIERS.items():
        if stem == name or stem.startswith(name + "_"):
            return tier
    return "default"


def metadata_block(metadata: dict[str, Any] | None,
                   post: dict[str, Any] | None = None) -> dict[str, Any]:
    # The post row fills what the metadata operation did not return, never what it did: on Instagram
    # the downloader answers with no title and no tags, and the caption a viewer actually reads is
    # in the post row. Where both speak, the metadata operation is the platform's own answer about
    # its own video and wins.
    facts = post_facts(post)

    def filled(block: dict[str, Any]) -> dict[str, Any]:
        # The post row fills fields; it does not vouch for the metadata operation. Promoting the
        # status here would turn "the platform was not asked, or did not answer" into "the platform
        # published no cover and no tags", and the empty `thumbnails` array would then read as a
        # fact. It would also silence the downstream check that only fires on `unavailable`.
        if not facts:
            return block
        if not block.get("caption") and facts.get("caption"):
            block["caption"] = facts["caption"]
        if not block["tags"] and facts.get("hashtags"):
            block["tags"] = facts["hashtags"]
        return block

    if metadata is None:
        return filled({"status": "not_attempted", "title": None, "caption": None,
                       "tags": [], "thumbnails": []})
    # Only a complete metadata response says what the platform declares; a partial one cannot tell
    # "no tags" from "tags not returned".
    if metadata.get("status") != "completed":
        return filled({"status": "unavailable", "title": None, "caption": None,
                       "tags": [], "thumbnails": []})
    video = as_record(as_record(metadata.get("data")).get("video"))
    tags = [tag for tag in video.get("tags") or [] if isinstance(tag, str)]  # the creator's own order
    thumbnail = video.get("thumbnail")
    thumbnails = ([{"tier": thumbnail_tier(thumbnail), "url": thumbnail}]
                  if isinstance(thumbnail, str) and thumbnail else [])
    title = video.get("title")
    caption = video.get("description")
    caption = caption if isinstance(caption, str) and caption.strip() else None
    return filled({"status": "available", "title": title if isinstance(title, str) else None,
                   "caption": caption, "tags": tags, "thumbnails": thumbnails})


def build(
    request: dict[str, Any],
    envelope_paths: list[Path],
    *,
    run_id: str | None = None,
    owner_metrics: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
    published_at: str | None = None,
    pending: list[str] | None = None,
    deferred_incomplete: list[str] | None = None,
    local_media: dict[str, Any] | None = None,
    local_transcript: dict[str, Any] | None = None,
    snapshot_root: Path | None = None,
    analysis_root: Path | None = None,
    now: datetime | None = None,
    viewer: dict[str, Any] | None = None,
    stated_duration_s: float | None = None,
    song: dict[str, Any] | None = None,
    comment_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from prepare_link_request import public_only_request_errors
    scope_errors = public_only_request_errors(request)
    if scope_errors:
        raise ValueError("; ".join(scope_errors))
    if as_record(request.get("source")).get("subject_state") == "unknown" and owner_metrics is not None:
        raise ValueError("unknown ownership cannot consume an owner export")
    acquisition_mode = as_record(request.get("source")).get("acquisition")
    if local_media is not None and acquisition_mode != "local_file":
        raise ValueError(
            f"a local media artifact was given but the request declares acquisition "
            f"{acquisition_mode!r}: the evidence would claim it measured a file the request never named"
        )
    side = {name: side_record(record, name) for name, record in (("song", song), ("comment_summary", comment_summary))
            if record is not None}
    side_blocks = {name: (song_block if name == "song" else audience_block)(record) for name, record in side.items()}
    if viewer is not None and (acquisition_mode == "local_file" or local_media is not None
                               or local_transcript is not None):
        # The whole-video viewer watched the platform's copy; a local file is the creator's master. One object
        # never claims both readings describe the same thing.
        raise ValueError(
            "a whole-video viewing result was given for a local file: the viewer watched the published copy, "
            "not this file, and is not evidence about it"
        )
    # A deferred job still unfinished has a job id and no envelope yet. It is recorded as pending
    # (polling window over, run still going) or deferred_incomplete (the run is closing), never as
    # failed: nothing came back, and nothing failed either.
    pending_entries = []
    for status, entries, flag in (("pending", pending, "--pending"),
                                  ("deferred_incomplete", deferred_incomplete, "--deferred-incomplete")):
        for entry in entries or []:
            operation, _, job_id = entry.partition("=")
            if not operation or not job_id:
                raise ValueError(f"{flag} takes <operation>=<job id>, got {entry!r}")
            pending_entries.append({
                "step": "connector_call",
                "connector_id": MEDIA_CONNECTOR, "operation": operation, "connector_request_id": job_id,
                "status": status, "retrieved_at": None, "raw_hash": None, "raw_retained_outside_git": True,
                "credits_charged": None, "note": "deferred job still unfinished when the acquisition window closed",
            })
    if (not envelope_paths and not pending_entries and local_media is None and local_transcript is None
            and viewer is None):
        # An evidence object records at least one acquisition; with none there is nothing to derive.
        raise ValueError("no connector envelope was given: persist every fetch this run made, failed ones "
                         "included, and pass each with --envelope")
    loaded = [(path, load_json(path)) for path in envelope_paths]
    linked_bundles = [candidate for _, body in loaded
                      for candidate in (body, body.get("linked_media", {}))
                      if isinstance(candidate, dict) and candidate.get("schema_version") == linked_media.SCHEMA]
    envelopes: list[tuple[Path, dict[str, Any]]] = [
        (path, normalise_metadata(envelope_of(body))) for path, body in loaded
        if body.get("schema_version") != linked_media.SCHEMA
        and not (set(body) == {"schema_version", "generated_at", "max_in_flight", "connectors"}
                 and body.get("schema_version") == "1.0"
                 and isinstance(body.get("generated_at"), str)
                 and type(body.get("max_in_flight")) is int
                 and isinstance(body.get("connectors"), list)
                 and all(isinstance(connector, dict) for connector in body["connectors"]))
    ]
    # Hosts also retain readiness catalogs in the same staging directory. They are acquisition
    # metadata, not connector evidence; unknown documents and malformed envelopes still fail.
    if (not envelopes and not linked_bundles and not pending_entries and local_media is None
            and local_transcript is None and viewer is None):
        raise ValueError("no content acquisition was given: a readiness catalog is not post evidence")
    by_role: dict[str, list[dict[str, Any]]] = {}
    for _, envelope in envelopes:
        role = role_of(envelope)
        if role:
            by_role.setdefault(role, []).append(envelope)
    metadata = pick(by_role.get("metadata", []))
    captions = pick(by_role.get("captions", []))
    frames = pick(by_role.get("frames", []))
    measurements = pick(by_role.get("measurements", []))
    post = pick(by_role.get("public_post", []))
    # On the paid-resolver platforms, metadata and measurements come back with the keyframes round (data.video /
    # data.signals); the two standalone calls answer unsupported and fetch nothing. When the data they point to did
    # arrive, their "nothing retrieved" stays out of limitations: there is no gap.
    served_elsewhere: set[str] = set()
    if not usable(metadata) and carried_metadata(frames) is not None:
        metadata = carried_metadata(frames)
        served_elsewhere.add("metadata")
    if not usable(measurements) and usable(frames) and as_record(as_record(frames.get("data")).get("signals")):
        served_elsewhere.add("measurements")

    if acquisition_mode == "local_file" and (frames is not None or captions is not None
                                             or measurements is not None):
        # The enforcement half of the Skill's gate. A media-connector response to a request naming a
        # local file did not measure this video -- it could not have, the file is unreachable from
        # there -- so it is not evidence about it, and merging the two would put two different
        # copies of one video into a single object.
        raise ValueError(
            "this request names a local file, which no public-video-media operation can reach: the "
            "media envelopes passed here did not measure this video and are not evidence about it. "
            "Run the local scripts instead, and pass their artifacts with --local-media / "
            "--local-transcript"
        )

    # Every step a run took gets a ledger entry, the subtitle read included -- a run whose media
    # tools were absent and whose only evidence is that file would otherwise build an evidence
    # object with an empty acquisition array, which the schema refuses.
    local_steps = [as_record(step) for step in as_record(local_media).get("steps") or []]
    local_steps += [as_record(step) for step in as_record(local_transcript).get("steps") or []]

    source_url = str(as_record(request.get("source")).get("url") or "")
    file_id = source_url.split(":", 1)[1].lower() if source_url.lower().startswith("kabo-file:") else None
    identity = video_identity([envelope for _, envelope in envelopes], as_record(request.get("source")).get("platform"),
                              file_id)
    metadata_ids = [as_record(as_record(item.get("data")).get("video")).get("id")
                    for item in by_role.get("metadata", []) if usable(item)]
    ref = content_ref(request, metadata, published_at, post_facts(post).get("published_at"), identity,
                      metadata_ids)
    # Tier 1 before tier 2, which is the order SKILL.md states. A supplied subtitle file is the
    # fallback for a cut with no published captions, not an override of the ones the platform
    # returned: taking it unconditionally would throw away what a viewer with captions on actually
    # reads, and relabel the creator's own published wording as a file they handed over.
    transcript = transcript_block(captions, request)
    unfinished = {entry["operation"]: entry for entry in pending_entries}
    if captions is None and "fetch_transcript" in unfinished:
        # The transcript job was still running when the wait hit its cap: it is unfinished, not failed; say so,
        # so it is not read as a backend error.
        transcript["status_basis"] = (f"the fetch_transcript job {unfinished['fetch_transcript']['connector_request_id']} "
                                      "was still running when waiting stopped: unfinished, not failed")
    if local_transcript is not None and transcript["status"] != "available":
        transcript = local_transcript_block(local_transcript, request)
        used_local_transcript = True
    else:
        used_local_transcript = False
    media = media_block(frames, metadata, local_media, measurements, captions, stated_duration_s)
    duration_s = media.get("duration_s") if isinstance(media.get("duration_s"), (int, float)) else None
    viewer_block = viewer_response.observations(viewer) if viewer is not None else None
    viewer_notes_dropped = past_end_notes(viewer_block, duration_s) if viewer_block is not None else []
    viewer_cues = cues_from(viewer_response.transcript_cues(viewer))
    fetched_transcript = transcript if transcript.get("source_connector") and not used_local_transcript else None
    fetched_cues = list((fetched_transcript or {}).get("cues") or [])
    # Words the fetched transcript holds that may stand for speech: none when it carries only sound markers or the
    # generic lines speech recognition invents over music.
    fetched_worded = transcript_checks.worded_cues(fetched_cues, duration_s)
    fetched_empty = transcript["status"] != "available" or (
        transcript.get("granularity") == "timestamped" and not fetched_worded)
    used_viewer_transcript = False
    if viewer_cues and fetched_empty and not used_local_transcript:
        # The viewer heard the audio itself: its words fill the transcript when no fetched transcript holds words.
        text = "\n".join(cue["text"] for cue in viewer_cues)
        why = ("no fetched transcript was available" if transcript["status"] != "available" else
               f"the fetched transcript's {len(fetched_cues)} cue(s) held only sound markers or generic lines")
        transcript = {
            "status": "available",
            "status_basis": (f"the whole-video viewer ({viewer_response.START_TOOL}) returned {len(viewer_cues)} "
                             f"timed cues heard from the video's audio; {why}"),
            "source_connector": viewer_response.CONNECTOR,
            "granularity": "timestamped",
            "timestamps_available": True,
            "language_requested": transcript.get("language_requested"),
            "language": None,
            "segment_count": len(viewer_cues),
            "character_count": len(text),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "cues": viewer_cues,
            "origin": "speech_recognition",
        }
        used_viewer_transcript = True
    viewer_run = as_record(as_record(viewer).get("run"))
    viewer_heard = viewer_run.get("status") == "completed"
    sources = []
    if fetched_transcript is not None:
        sources.append(transcript_checks.source_entry(
            "fetched", str(fetched_transcript["status"]), fetched_cues, used=not used_viewer_transcript,
            declared=fetched_transcript.get("language"), origin=fetched_transcript.get("origin")))
    if viewer is not None:
        sources.append(transcript_checks.source_entry(
            "whole_video_viewer", ("available" if viewer_cues else "no_speech_heard") if viewer_heard
            else str((viewer_block or {}).get("status") or "unavailable"), viewer_cues, used=used_viewer_transcript,
            origin="speech_recognition"))
    if local_transcript is not None:
        heard = as_record(local_transcript).get("origin") == "speech_recognition" or as_record(local_transcript).get(
            "status") in {"no_speech_detected", "no_audio_track"}
        sources.append(transcript_checks.source_entry(
            "local_speech_recognition" if heard else "subtitle_file", str(as_record(local_transcript).get("status")),
            cues_from(as_record(local_transcript).get("cues")), used=used_local_transcript,
            declared=as_record(local_transcript).get("language"), origin=transcript.get("origin")))
    video_facts = as_record(as_record(metadata.get("data")).get("video")) if usable(metadata) else {}
    transcript_conflicts = transcript_checks.conflicts(
        fetched_cues if fetched_transcript is not None else None, viewer_cues if viewer is not None else None,
        fetched_language=(fetched_transcript or {}).get("language"), viewer_heard=viewer_heard,
        duration_s=duration_s,
        metadata_text=" ".join(str(video_facts.get(key) or "") for key in ("title", "description")) or None,
        used=transcript.get("cues") or [],
        used_label="the whole-video viewer's transcript" if used_viewer_transcript else "the transcript")
    suspect = transcript_checks.suspect_cues(transcript.get("cues") or [], duration_s)
    if sources:
        transcript["sources"] = sources
    if transcript_conflicts:
        transcript["conflicts"] = transcript_conflicts
    if suspect:
        transcript["suspect_cues"] = suspect
    frame_block = frames_block(frames, local_media)
    # Local extraction already writes its own real files under hashed names and records each
    # path. Only connector pixels are renamed by host envelope staging.
    if snapshot_root is not None and local_media is None:
        if analysis_root is None:
            raise ValueError("snapshot frame binding requires this run's analysis directory")
        materialise_frame_aliases(frame_block, snapshot_root, analysis_root)
    anything = (transcript["status"] == "available" or frame_block["status"] == "available" or usable(metadata)
                or bool(viewer_block and viewer_block["items"]))
    notes: list[str] = []
    for _, envelope in envelopes:
        if envelope.get("status") == "unsupported" and role_of(envelope) in served_elsewhere:
            continue
        if role_of(envelope) == "captions" and used_viewer_transcript:
            # Its "no transcript was retrieved" is true of that call only: the viewer's words fill the transcript.
            replaced = (f"{envelope.get('operation')} returned no words; the transcript here is the one the "
                        "whole-video viewer heard.")
            if replaced not in notes:
                notes.append(replaced)
            continue
        fact = f"{envelope.get('operation')} returned {envelope.get('status')}."
        for value in envelope.get("limitations") or []:
            text = limitation_text(value)
            if not text:
                continue
            # The blanket sentence is true of one call, not of the run: keep the fact, drop the words.
            if anything and BLANKET in text.lower():
                text = fact
            if text not in notes:
                notes.append(text)
        if not usable(envelope) and fact not in notes and not any(fact[:-1] in note for note in notes):
            notes.append(fact)
    for text in as_record(local_media).get("limitations") or []:
        if isinstance(text, str) and text.strip() and text.strip() not in notes:
            notes.append(text.strip())
    if local_transcript is not None and not used_local_transcript:
        notes.append("A subtitle file was supplied, but the platform's own captions were retrieved "
                     "and were used instead: they are what a viewer with captions on reads.")
    if used_local_transcript and transcript["status"] == "available":
        last_cue = max((cue["start_s"] for cue in transcript.get("cues") or []), default=None)
        duration = as_record(as_record(local_media).get("media")).get("duration_s")
        if last_cue is not None and isinstance(duration, (int, float)) and last_cue > duration:
            # Cheap catch for the commonest way this tier goes wrong: a subtitle file belonging to a
            # different, longer cut. Nothing here can check the wording, but a cue that starts after
            # the video ends is a file that is not about this video.
            notes.append(
                f"The supplied subtitle file runs past the end of this cut (a line starts at "
                f"{last_cue:g}s in a {duration:g}s video), so it may belong to a different version."
            )
    if used_local_transcript and as_record(local_transcript).get("complete") is False:
        reached = as_record(local_transcript).get("transcribed_until_s")
        notes.append(f"Local speech recognition stopped at its time limit after {reached}s of the file: past that "
                     "second the words were not read, which is not the same as silence.")
    if viewer_cues and not used_viewer_transcript:
        notes.append("The whole-video viewer also returned a transcript; the fetched transcript was used instead.")
    if viewer_notes_dropped:
        notes.append(past_end_limitation(viewer_notes_dropped, duration_s))
    for text in transcript_conflicts:
        if text not in notes:
            notes.append(text)
    if viewer_block is not None and viewer_block["status"] != "available":
        code = (viewer_block.get("failure") or {}).get("code")
        notes.append("Whole-video viewing " + ("was still running when observation closed" if viewer_block["status"] == "pending"
                                                else f"returned no observations ({code})")
                     + ", so its timestamped notes are unavailable.")
    if ref["published_at"] == "unknown":
        notes.append("No publish date was available from the retrieved metadata.")
    if usable(metadata):
        for metric in STATED_GAPS:
            if not public_video_sources.publishes(ref["platform"], metric):
                notes.append(f"{public_video_sources.label(ref['platform'])} does not publish a public "
                             f"{metric[:-1]} count, so {metric} are unavailable, not zero.")
    for text in post_facts(post).get("limitations") or []:
        if text not in notes:
            notes.append(text)
    for text in limitations or []:
        if text.strip() and text.strip() not in notes:
            notes.append(text.strip())
    for name, block in side_blocks.items():
        text = side_limitation(name, block["status"])
        if text and text not in notes:
            notes.append(text)
    if (any(as_record(envelope.get("data")).get("source_unavailable") is True for _, envelope in envelopes)
            and observation_order.SOURCE_UNAVAILABLE_MARK not in notes):
        # The one marker for a video the backend could not fetch at all, whichever result said so.
        notes.append(observation_order.SOURCE_UNAVAILABLE_MARK)

    hashes: dict[str, str] = {}
    for role, chosen in (("metadata_raw", metadata), ("captions_raw", captions), ("frames_raw", frames)):
        if chosen is not None and isinstance(chosen.get("raw_sha256"), str):
            hashes[role] = chosen["raw_sha256"]
    # Keyed by position and file name: a local absolute path would carry the operator's user name and
    # workspace into an artifact that travels downstream, and would key the same input differently per run.
    for index, (path, _) in enumerate(envelopes, start=1):
        hashes.setdefault(f"file:{index:02d}:{path.name}", hashlib.sha256(path.read_bytes()).hexdigest())
    # The replay anchor for a local run: which bytes were read. The invocation that read them is on
    # each acquisition entry, so between the two the step can be run again and compared.
    if isinstance(as_record(local_media).get("input_sha256"), str):
        hashes["local_media_input"] = local_media["input_sha256"]
    if isinstance(as_record(local_transcript).get("source_file_sha256"), str):
        hashes["local_subtitle_input"] = local_transcript["source_file_sha256"]
    if viewer is not None:
        hashes["whole_video_response"] = viewer["raw_sha256"]
    for name, record in side.items():
        if isinstance(record.get("raw_sha256"), str):
            hashes[f"{name}_response"] = record["raw_sha256"]

    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": f"ev-{public_video_sources.content_id_prefix(ref['platform'])}-{unresolved_safe_id(ref)}",
        "request_ref": request.get("request_id"),
        "content_ref": ref,
        "acquisition": (
            [acquisition_entry(envelope) for _, envelope in envelopes]
            + [local_acquisition_entry(step, step.get("input_sha256")
                                       or as_record(local_media).get("input_sha256"))
               for step in local_steps]
            + pending_entries
            + ([viewer_acquisition_entry(viewer)] if viewer is not None else [])
            + [side_acquisition_entry(record, side_blocks[name]["status"]) for name, record in side.items()
               if record.get("attempted")]
        ),
        "media": media,
        "transcript": transcript,
        "frames": frame_block,
        "owner_metrics": owner_metrics or {"status": "unavailable", "source_mode": "unavailable",
                                           "account_ref": None, "snapshot_sha256": None, "items": []},
        "content_metadata": metadata_block(metadata, post),
        "limitations": notes,
        "reproducibility": {
            "run_id": run_id or str(request.get("request_id") or "unknown"),
            "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
            "input_hashes": hashes,
        },
    }
    # Prefer the post row's existing counter names and semantics. When it has no counters,
    # metadata may still carry public ones; absent values stay absent rather than becoming zero.
    facts = post_facts(post)
    if not facts.get("public_metrics"):
        facts["public_metrics"] = metadata_public_metrics(metadata, ref["platform"])
    if not facts.get("audio_attribution"):
        # With no sound in the post row, use the sound platform metadata declares (TikTok's music.is_original_sound and so on).
        declared = next((as_record(as_record(item.get("data")).get("audio")) for item in by_role.get("metadata", [])
                         if usable(item) and as_record(as_record(item.get("data")).get("audio"))), None)
        if declared:
            facts["audio_attribution"] = {**declared, "trend_metrics_available": False}
    for key in ("public_metrics", "derived", "audio_attribution"):
        if facts.get(key):
            evidence[key] = facts[key]
    if viewer_block is not None:
        evidence["viewer_observations"] = viewer_block
    if "song" in side_blocks:
        evidence["song_identification"] = side_blocks["song"]
    if "comment_summary" in side_blocks:
        evidence["audience_response"] = side_blocks["comment_summary"]
    linked = linked_media.bind(linked_bundles, [e for _, e in envelopes], request, analysis_root)
    if linked is not None:
        evidence["images"] = linked
        for index, (path, body) in enumerate(loaded):
            if body.get("schema_version") == linked_media.SCHEMA:
                evidence["reproducibility"]["input_hashes"][f"linked_media:{index}:{path.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    post_data = (linked_media.public_post_facts([e for _, e in envelopes], as_record(request.get("source")))
                 if linked is not None else None)
    if post_data is not None:
        metadata = evidence["content_metadata"]
        if metadata.get("caption") is None and post_data["caption"] is not None:
            metadata["caption"] = post_data["caption"]
            if not metadata.get("tags"):
                metadata["tags"] = HASHTAG.findall(post_data["caption"])
        elif metadata.get("tags") is None and isinstance(metadata.get("caption"), str):
            metadata["tags"] = HASHTAG.findall(metadata["caption"])
        if "public_metrics" not in evidence and post_data["metrics"]:
            evidence["public_metrics"] = post_data["metrics"]
    caption = evidence["content_metadata"]["caption"]
    if isinstance(caption, str):
        for item in evidence.get("derived", []):
            if item["name"] == "caption_length_characters":
                item["value"] = len(caption)
            elif item["name"] == "caption_hashtag_count":
                item["value"] = len(HASHTAG.findall(caption))
    return evidence


# The media operations that observe the video itself (frame and measurement routes may carry a suffix).
OBSERVING_OPERATIONS = ("fetch_transcript", "extract_keyframes", "measure_media_signals")


def observation_source(evidence: dict[str, Any]) -> str:
    """Which observation source this evidence came from, read off its acquisition ledger."""
    steps = evidence.get("acquisition") or []
    if any(entry.get("step") == "local_extraction" for entry in steps):
        return "local_frames"
    # Only what arrived counts: a failed media call before a fallback, or a failed viewing, observed nothing.
    # Metadata alone is not an observation of the video either: a whole-video run fetches it too.
    viewer = (evidence.get("viewer_observations") or {}).get("status") == "available"
    media = any(entry.get("connector_id") == MEDIA_CONNECTOR and entry.get("status") in {"completed", "completed_partial"}
                and str(entry.get("operation") or "").startswith(OBSERVING_OPERATIONS) for entry in steps)
    if viewer and media:
        return "combined"
    if viewer or media:
        return "whole_video" if viewer else "server_frames"
    # Nothing arrived: name what was tried, a viewing only when no media observation was even asked for.
    asked = any(entry.get("connector_id") == MEDIA_CONNECTOR and str(entry.get("operation") or "").startswith(
        OBSERVING_OPERATIONS) for entry in steps)
    return "whole_video" if "viewer_observations" in evidence and not asked else "server_frames"


def own_earlier_pair(output: Path, reference_path: Path) -> bool:
    """Whether the evidence and reference index already at these paths are a pair this builder wrote: both regular
    files, the index naming the evidence's exact sha256. Only such a pair may be built over (`--replace`)."""
    try:
        if output.is_symlink() or reference_path.is_symlink() or not output.is_file() or not reference_path.is_file():
            return False
        index = json.loads(reference_path.read_text(encoding="utf-8"))
        return (isinstance(index, dict) and index.get("schema_version") == "content-evidence-references.v1"
                and index.get("evidence_sha256") == hashlib.sha256(output.read_bytes()).hexdigest())
    except (OSError, ValueError):
        return False


def write_evidence_with_reference_index(output: Path, evidence_bytes: bytes,
                                        reference_path: Path, reference_bytes: bytes) -> None:
    """Stage both files before committing the index, then atomically replace evidence."""
    staged: list[Path] = []
    created_index = False
    try:
        for target, body in ((output, evidence_bytes), (reference_path, reference_bytes)):
            with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                             prefix=f".{target.name}.", delete=False) as stream:
                staged.append(Path(stream.name))
                stream.write(body)
        # A hard link commits the complete index without replacing a concurrent file.
        os.link(staged[1], reference_path)
        created_index = True
        os.replace(staged[0], output)
    except OSError:
        # Never remove a different index another writer installed after our commit.
        if created_index:
            try:
                current = reference_path.lstat()
                ours = staged[1].stat()
                if (current.st_dev, current.st_ino) == (ours.st_dev, ours.st_ino):
                    reference_path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True, help="the VideoAnalysisRequest of this run")
    parser.add_argument("--envelope", type=Path, action="append", default=[],
                        help="one persisted connector envelope (repeat for each)")
    parser.add_argument("--owner-metrics", type=Path, help="the owner_metrics block, when an owner export was read")
    parser.add_argument("--limitation", action="append", default=[], help="a limitation observed outside the envelopes")
    parser.add_argument("--published-at", help="the publish time when the metadata carried none")
    parser.add_argument("--pending", action="append", default=[],
                        help="<operation>=<job id> for a deferred job whose polling window ended, run still going")
    parser.add_argument("--deferred-incomplete", action="append", default=[],
                        help="<operation>=<job id> for a deferred job still unfinished as this run closes")
    parser.add_argument("--local-media", type=Path,
                        help="the artifact extract_local_frames.py wrote, for a file read on this machine")
    parser.add_argument("--local-transcript", type=Path,
                        help="the artifact read_subtitle_file.py wrote, for a subtitle file the creator supplied")
    parser.add_argument("--viewer", type=Path,
                        help="the saved whole-video viewing result (analyze_content_video / get_analysis_run)")
    parser.add_argument("--song", type=Path, help="the persisted song identification (snapshot/song.json)")
    parser.add_argument("--comment-summary", type=Path,
                        help="the persisted comment summary (snapshot/comment-summary.json)")
    parser.add_argument("--run-id", help="by default the run directory's name, when the output is in <run>/analysis/")
    parser.add_argument("--duration-s", type=float,
                        help="the video's duration as observe_video.py printed it; used only when no envelope "
                             "carries one")
    parser.add_argument("--snapshot-root", type=Path,
                        help="this run's snapshot directory; bind staged frame bytes to canonical IDs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-index", type=Path,
                        help="optional same-source structural reference index for the judgment")
    parser.add_argument("--replace", action="store_true",
                        help="build again over this run's earlier evidence and reference index (a pair this builder "
                             "wrote), after another envelope or a per-run flag came in")
    args = parser.parse_args()
    replacing = False
    try:
        reference_path = args.reference_index
        if reference_path is not None:
            inputs = [args.request, *args.envelope, args.owner_metrics,
                      args.local_media, args.local_transcript, args.viewer, args.song, args.comment_summary]
            inputs = [path for path in inputs if path is not None]
            if reference_path.resolve() == args.output.resolve():
                raise ValueError("the evidence and reference index must use different paths")
            for output in (args.output, reference_path):
                for source in inputs:
                    if (output.resolve() == source.resolve()
                            or (output.exists() and source.exists() and output.samefile(source))):
                        raise ValueError("evidence and reference outputs must not overwrite an input")
            if reference_path.exists() or reference_path.is_symlink():
                if not args.replace:
                    raise ValueError("the reference sidecar already exists; no input or output was overwritten")
                if not own_earlier_pair(args.output, reference_path):
                    raise ValueError("--replace builds again only over this builder's own evidence and reference "
                                     "index; no input or output was overwritten")
                replacing = True
        request = load_json(args.request)
        run_id = args.run_id
        if not run_id and not request.get("request_id"):
            # The run directory names the run: <run>/analysis/content_evidence.json. A request written with a relative
            # path once carried an empty request id, and every id composed from it ended in "-unknown".
            candidate = args.output.resolve().parent.parent
            if args.output.resolve().parent.name == "analysis" and (candidate / ".static-run.json").is_file():
                run_id = candidate.name
        evidence = build(
            request,
            args.envelope,
            run_id=run_id,
            stated_duration_s=args.duration_s,
            owner_metrics=load_json(args.owner_metrics) if args.owner_metrics else None,
            limitations=args.limitation,
            published_at=args.published_at,
            pending=args.pending,
            deferred_incomplete=args.deferred_incomplete,
            local_media=load_json(args.local_media) if args.local_media else None,
            local_transcript=load_json(args.local_transcript) if args.local_transcript else None,
            snapshot_root=args.snapshot_root,
            analysis_root=args.snapshot_root.parent / "analysis" if args.snapshot_root else None,
            viewer=viewer_response.read(args.viewer.read_bytes()) if args.viewer else None,
            song=load_json(args.song) if args.song else None,
            comment_summary=load_json(args.comment_summary) if args.comment_summary else None,
        )
        evidence_bytes = (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if reference_path is not None:
            # The validator owns reference resolution; do not maintain a second spelling table
            # or repair the model's judgment. CLI opt-in leaves historical callers unchanged.
            from validate_video_analysis import evidence_handles
            reference_index = {
                "schema_version": "content-evidence-references.v1",
                "evidence_id": evidence["evidence_id"],
                "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                "reference_semantics": "Legal structural references, not proof a fact was observed. "
                                       "Read the evidence value and availability before making a claim.",
                "evidence_refs": sorted(evidence_handles(evidence)),
            }
            reference_path.parent.mkdir(parents=True, exist_ok=True)
            reference_bytes = (json.dumps(reference_index, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if reference_path is None:
            args.output.write_text(evidence_bytes.decode("utf-8"), encoding="utf-8")
        else:
            if replacing:
                # Checked again right before the write: still the same pair, so nothing else is removed.
                if not own_earlier_pair(args.output, reference_path):
                    raise ValueError("the evidence or reference index changed during the build; nothing was replaced")
                reference_path.unlink()
            write_evidence_with_reference_index(args.output, evidence_bytes, reference_path, reference_bytes)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "ok",
        "output": str(args.output),
        **({"reference_index": str(reference_path)} if reference_path is not None else {}),
        "transcript": evidence["transcript"]["status"],
        "cues": len(evidence["transcript"].get("cues") or []),
        "frames": evidence["frames"]["status"],
        "frame_count": len(evidence["frames"]["items"]),
        "transcript_origin": evidence["transcript"].get("origin"),
        "local_steps": sum(1 for entry in evidence["acquisition"] if entry.get("step") == "local_extraction"),
        "content_metadata": evidence["content_metadata"]["status"],
        **({"song_identification": evidence["song_identification"]["status"]}
           if "song_identification" in evidence else {}),
        **({"audience_response": evidence["audience_response"]["status"]} if "audience_response" in evidence else {}),
        **({"viewer_observations": evidence["viewer_observations"]["status"],
            "viewer_notes": len(evidence["viewer_observations"]["items"])} if "viewer_observations" in evidence else {}),
    }, ensure_ascii=False))
    # Observation ends when its evidence is built; which source it was follows from what arrived.
    analysis_dir = args.output.parent
    acv_timing.set_source(analysis_dir, observation_source(evidence))
    acv_timing.close_stage(analysis_dir, "observe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
