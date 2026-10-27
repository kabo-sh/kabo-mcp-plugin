"""Shared reads of public-video-media envelopes.

Copied detection rules from analyze-content-video's build_content_evidence.py so a
frame or cue is available here on the same evidence the video skill would accept.
This module does not call the connector.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

MEDIA_CONNECTOR = "public-video-media"
OPERATIONS = (
    "collect_public_metadata",
    "fetch_transcript",
    "extract_keyframes",
)
KEYFRAME_OPERATIONS = frozenset({
    "extract_keyframes", "extract_keyframes_hosted_media", "extract_keyframes_hosted_stream",
})
OPERATION_ALIASES = {
    "extract_keyframes": KEYFRAME_OPERATIONS,
    "extract_keyframes_hosted_media": KEYFRAME_OPERATIONS,
    "extract_keyframes_hosted_stream": KEYFRAME_OPERATIONS,
}
USABLE = {"completed", "completed_partial"}
TRANSCRIPT_ORIGINS = {"platform_captions", "provider_transcript", "speech_recognition"}
FRAME_SELECTIONS = {
    "duration_scaled_v1",
    "evenly_spaced_bounded_v1",
    "explicit_timestamps_v1",
    "none",
}
NON_ENVELOPE_NAMES = {
    "account_analysis.json",
    "watch_set.json",
    "media_job_plan.json",
    "watch_outcomes.json",
    "watched_evidence.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def envelope_of(document: Any) -> dict[str, Any]:
    """An envelope, or the terminal envelope a deferred job resource carries."""
    record = as_record(document)
    inner = as_record(record.get("envelope"))
    if {"connector_id", "operation", "status"} <= set(inner):
        if record.get("job_id"):
            if inner.get("job_id") not in (None, record["job_id"]):
                raise ValueError("terminal envelope and job resource have different job ids")
            return {**inner, "job_id": record["job_id"]}
        return inner
    if {"connector_id", "operation", "status"} <= set(record):
        return record
    if record.get("job_id") and not inner:
        raise ValueError(
            f"job {record.get('job_id')} carries no terminal envelope yet"
        )
    raise ValueError("not a connector envelope or a job resource carrying one")


def usable(envelope: dict[str, Any] | None) -> bool:
    return envelope is not None and envelope.get("status") in USABLE


def pick(envelopes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last usable response of one operation, else the last one."""
    for envelope in reversed(envelopes):
        if usable(envelope):
            return envelope
    return envelopes[-1] if envelopes else None


def dest_stem(content_id: str, operation: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", content_id.strip()) or "content"
    return f"media-{safe}-{operation}"


def dest_filename(content_id: str, operation: str) -> str:
    return f"{dest_stem(content_id, operation)}.json"


def canonical_operation(operation: str | None) -> str:
    if operation in KEYFRAME_OPERATIONS:
        return "extract_keyframes"
    return operation or ""


def operations_equivalent(left: str | None, right: str | None) -> bool:
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    if left == right:
        return True
    return right in OPERATION_ALIASES.get(left, {left})


def dest_stems(content_id: str, operation: str) -> set[str]:
    names = OPERATION_ALIASES.get(operation, {operation})
    return {dest_stem(content_id, name) for name in names}


# Words a model reaches for when it wants to declare a job pending without having issued it.
# `pending` is the one status that lets an unwatched video pass without an envelope, so a
# placeholder here buys a finished report that never watched anything. Observed 2026-09-21:
# a run closed six of ten planned videos with `=not-started` and reported shot-level findings
# for the other four as if the watch set had been honoured.
NOT_A_JOB_ID = {
    "not-started", "not_started", "notstarted", "none", "null", "nil", "n/a", "na",
    "pending", "unknown", "tbd", "todo", "-", "?",
}


def parse_pending(entries: list[str] | None) -> dict[tuple[str, str], str]:
    """Parse ``<content_id>:<operation>=<job_id>`` flags.

    The job id must be one the host actually returned: `pending` means "this call went out and
    has not come back", never "this call was never made".
    """
    parsed: dict[tuple[str, str], str] = {}
    for entry in entries or []:
        owner, _, rest = entry.partition(":")
        operation, _, job_id = rest.partition("=")
        if not owner or not operation or not job_id:
            raise ValueError(
                f"pending flag takes <content_id>:<operation>=<job id>, got {entry!r}"
            )
        if job_id.strip().lower() in NOT_A_JOB_ID:
            raise ValueError(
                f"{entry!r}: {job_id!r} is not a job id the host returned. A job is pending only "
                "once its call has gone out and come back with an id. If the call was never made, "
                "make it now; if it failed twice, leave it out and let the video be recorded as "
                "unwatched."
            )
        parsed[(owner, operation)] = job_id
    return parsed


def parse_job_bindings(entries: list[str] | None) -> dict[tuple[str, str], set[str]]:
    """Bind returned job ids to planned content, independently of completion order."""
    bindings: dict[tuple[str, str], set[str]] = {}
    owners: dict[str, tuple[str, str]] = {}
    for entry in entries or []:
        for (content_id, operation), job_id in parse_pending([entry]).items():
            operation = canonical_operation(operation)
            if operation not in OPERATIONS:
                raise ValueError(f"unknown media operation in job binding: {operation!r}")
            slot = (content_id, operation)
            if job_id in owners and owners[job_id] != slot:
                raise ValueError(f"job {job_id!r} is bound to more than one content/operation")
            owners[job_id] = slot
            bindings.setdefault(slot, set()).add(job_id)
    return bindings


def _url_matches(envelope: dict[str, Any], url: str) -> bool:
    if not url:
        return False
    data = as_record(envelope.get("data"))
    video = as_record(data.get("video"))
    params = as_record(envelope.get("params"))
    request = as_record(envelope.get("request"))
    candidates = (
        data.get("url"),
        video.get("webpage_url"),
        video.get("url"),
        params.get("url"),
        request.get("url"),
        as_record(request.get("params")).get("url"),
    )
    return any(candidate == url for candidate in candidates if isinstance(candidate, str))


def envelope_matches(
    path: Path,
    envelope: dict[str, Any],
    *,
    content_id: str,
    operation: str,
    url: str,
    job_ids: set[str] | None = None,
) -> bool:
    if not operations_equivalent(envelope.get("operation"), operation):
        return False
    if envelope.get("connector_id") not in (None, MEDIA_CONNECTOR):
        return False
    data = as_record(envelope.get("data"))
    video = as_record(data.get("video"))
    declared_id = str(video.get("id") or "").strip()
    if declared_id and declared_id != content_id:
        return False
    if job_ids is not None and envelope.get("job_id"):
        return envelope.get("job_id") in job_ids
    if envelope.get("job_id"):
        # An asynchronous frame/transcript body need not carry the video URL. A filename
        # cannot prove its owner when several jobs of the same operation finish out of order.
        return False
    stems = dest_stems(content_id, operation)
    if path.stem in stems or any(
        re.fullmatch(re.escape(stem) + r"\.attempt-[1-9][0-9]*", path.stem)
        for stem in stems
    ):
        return True
    if str(video.get("id") or "").strip() == content_id:
        return True
    if _url_matches(envelope, url):
        return True
    return False


def load_envelope_files(
    paths: list[Path],
    envelope_dir: Path | None,
) -> list[tuple[Path, dict[str, Any]]]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved not in seen:
            files.append(resolved)
            seen.add(resolved)
    if envelope_dir is not None:
        for path in sorted(envelope_dir.glob("*.json")):
            if path.name in NON_ENVELOPE_NAMES:
                continue
            resolved = path.expanduser()
            if resolved not in seen:
                files.append(resolved)
                seen.add(resolved)
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in files:
        try:
            loaded.append((path, envelope_of(load_json(path))))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return loaded


def collect_for_job(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    content_id: str,
    operation: str,
    url: str,
    job_ids: set[str] | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, envelope)
        for path, envelope in loaded
        if envelope_matches(
            path, envelope, content_id=content_id, operation=operation, url=url,
            job_ids=job_ids,
        )
    ]


def transcript_from_envelope(envelope: dict[str, Any] | None) -> dict[str, Any]:
    block: dict[str, Any] = {
        "status": "not_attempted",
        "origin": None,
        "granularity": "none",
        "cue_count": 0,
        "character_count": 0,
        "text_sha256": None,
        "cues": [],
        "plain_text": None,
    }
    if envelope is None:
        return block
    data = as_record(envelope.get("data"))
    origin = data.get("origin") if data.get("origin") in TRANSCRIPT_ORIGINS else None
    if not usable(envelope):
        block["status"] = "unavailable"
        block["origin"] = origin
        return block
    cues: list[dict[str, Any]] = []
    for cue in data.get("cues") or []:
        cue = as_record(cue)
        text = cue.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if isinstance(cue.get("start_ms"), (int, float)):
            raw_start = float(cue["start_ms"]) / 1000.0
            start = round(raw_start, 3)
        elif isinstance(cue.get("start_s"), (int, float)):
            raw_start = float(cue["start_s"])
            start = round(raw_start, 3)
        else:
            continue
        raw_end = cue.get("end_ms")
        end = raw_end / 1000.0 if isinstance(raw_end, (int, float)) and not isinstance(raw_end, bool) else cue.get("end_s") if raw_end is None else raw_end
        if end is not None and (not isinstance(end, (int, float)) or isinstance(end, bool) or not math.isfinite(end) or end < raw_start):
            raise ValueError("transcript cue has an invalid source end time")
        if end is not None:
            start = raw_start
        cues.append({"start_s": start, "end_s": float(end) if end is not None else None, "text": text.strip()})
    plain = data.get("plain_text") if isinstance(data.get("plain_text"), str) else None
    if cues:
        text = "\n".join(cue["text"] for cue in cues)
        block.update(
            {
                "status": "available",
                "origin": origin,
                "granularity": "timestamped",
                "cue_count": len(cues),
                "character_count": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "cues": cues,
            }
        )
        return block
    if plain and plain.strip():
        text = plain.strip()
        block.update(
            {
                "status": "available",
                "origin": origin,
                "granularity": "plain_text",
                "cue_count": 0,
                "character_count": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "plain_text": text,
            }
        )
        return block
    block["status"] = "unavailable"
    block["origin"] = origin
    return block


def frames_from_envelope(envelope: dict[str, Any] | None) -> dict[str, Any]:
    block: dict[str, Any] = {
        "status": "not_attempted",
        "origin": None,
        "selection": "none",
        "frame_count": 0,
        "items": [],
        "duration_s": None,
    }
    if envelope is None:
        return block
    if not usable(envelope):
        block["status"] = "unavailable"
        return block
    data = as_record(envelope.get("data"))
    items: list[dict[str, Any]] = []
    for frame in data.get("frames") or []:
        frame = as_record(frame)
        if not isinstance(frame.get("t_seconds"), (int, float)) or not frame.get("frame_id"):
            continue
        items.append(
            {
                "frame_id": str(frame["frame_id"]),
                "t_seconds": float(frame["t_seconds"]),
                "path": frame.get("object_ref"),
            }
        )
    duration = data.get("duration_s")
    duration_s = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
    selection = data.get("selection") if data.get("selection") in FRAME_SELECTIONS else "none"
    if items:
        return {
            "status": "available",
            "origin": "extracted_frames",
            "selection": selection,
            "frame_count": len(items),
            "items": items,
            "duration_s": duration_s,
        }
    observations = []
    for entry in data.get("observations") or []:
        entry = as_record(entry)
        if isinstance(entry.get("t_seconds"), (int, float)) and isinstance(
            entry.get("description"), str
        ):
            observations.append(
                {
                    "frame_id": f"observation-{len(observations) + 1:04d}",
                    "t_seconds": float(entry["t_seconds"]),
                    "path": None,
                }
            )
    if observations:
        return {
            "status": "available",
            "origin": "model_observation",
            "selection": "none",
            "frame_count": len(observations),
            "items": observations,
            "duration_s": duration_s,
        }
    block["status"] = "unavailable"
    block["duration_s"] = duration_s
    return block


def metadata_from_envelope(envelope: dict[str, Any] | None) -> dict[str, Any]:
    block: dict[str, Any] = {
        "status": "not_attempted",
        "duration_s": None,
        "title": None,
        "connector_status": None,
        "origin": None,
        "limitations": [],
    }
    if envelope is None:
        return block
    block["connector_status"] = envelope.get("status")
    block["limitations"] = envelope.get("limitations") or []
    data = as_record(envelope.get("data"))
    block["origin"] = data.get("origin")
    if not usable(envelope):
        block["status"] = "unavailable"
        return block
    video = as_record(data.get("video"))
    duration = video.get("duration_seconds")
    title = video.get("title")
    return {
        **block,
        "status": "available",
        "duration_s": float(duration) if isinstance(duration, (int, float)) and duration > 0 else None,
        "title": title if isinstance(title, str) else None,
    }


def payload_available(operation: str, envelope: dict[str, Any] | None) -> bool:
    if operation == "collect_public_metadata":
        return metadata_from_envelope(envelope)["status"] == "available"
    if operation == "fetch_transcript":
        return transcript_from_envelope(envelope)["status"] == "available"
    if canonical_operation(operation) == "extract_keyframes":
        return frames_from_envelope(envelope)["status"] == "available"
    return False
