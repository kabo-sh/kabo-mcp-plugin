#!/usr/bin/env python3
"""Compact per-video watch evidence from persisted public-video-media envelopes.

Reuses the video skill's frame/cue contract (seconds, origin, cue text). This is
not a ContentEvidence rewrite and not a 17-dimension teardown.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from media_payload import (
    OPERATIONS,
    collect_for_job,
    envelope_of,
    envelope_matches,
    frames_from_envelope,
    load_envelope_files,
    load_json,
    metadata_from_envelope,
    pick,
    transcript_from_envelope,
    write_json,
)
from record_watch_outcomes import DEST_FILENAME_PATTERN
from point_observations import CONTRACT

SCHEMA_VERSION = "watch-evidence.v1"


def _envelope_for(
    operation_row: dict[str, Any],
    *,
    content_id: str,
    operation: str,
    url: str,
    loaded: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any] | None:
    dest = operation_row.get("envelope")
    job_id = operation_row.get("job_id")
    job_ids = {job_id} if isinstance(job_id, str) and job_id else None
    if isinstance(dest, str) and dest:
        path = Path(dest)
        if path.is_file():
            try:
                envelope = envelope_of(load_json(path))
            except ValueError as error:
                raise ValueError(f"invalid media envelope for {content_id}:{operation}: {error}") from error
            if job_ids is not None and envelope.get("job_id") != job_id:
                raise ValueError(f"media envelope does not match {content_id}:{operation} job binding")
            if not envelope_matches(path, envelope, content_id=content_id,
                                    operation=operation, url=url, job_ids=job_ids):
                raise ValueError(f"media envelope does not match {content_id}:{operation} job binding")
            return envelope

    candidates = [(path, envelope) for path, envelope in loaded
                  if job_ids is None or envelope.get("job_id") == job_id]
    matches = collect_for_job(candidates, content_id=content_id, operation=operation, url=url,
                              job_ids=job_ids)
    if not matches:
        return None
    return pick([envelope for _, envelope in matches])


def build_watch_evidence(
    outcomes: dict[str, Any],
    *,
    envelope_paths: list[Path] | None = None,
    envelope_dir: Path | None = None,
) -> dict[str, Any]:
    loaded = load_envelope_files(envelope_paths or [], envelope_dir)
    items: list[dict[str, Any]] = []
    for video in outcomes.get("videos") or []:
        if not isinstance(video, dict):
            continue
        content_id = str(video.get("content_id") or "").strip()
        url = str(video.get("url") or "").strip()
        ops = video.get("operations") if isinstance(video.get("operations"), dict) else {}
        envelopes = {
            operation: _envelope_for(
                ops.get(operation) or {},
                content_id=content_id,
                operation=operation,
                url=url,
                loaded=loaded,
            )
            for operation in OPERATIONS
        }
        transcript = transcript_from_envelope(envelopes["fetch_transcript"])
        frames = frames_from_envelope(envelopes["extract_keyframes"])
        metadata = metadata_from_envelope(envelopes["collect_public_metadata"])
        metadata_envelope = envelopes["collect_public_metadata"]
        if (ops.get("collect_public_metadata") or {}).get("status") == "pending" and (
            metadata_envelope is None
            or metadata_envelope.get("status") in {None, "queued", "running"}
        ):
            metadata["status"] = "pending"
        duration_s = frames.get("duration_s") or metadata.get("duration_s")
        duration_source = (
            "connector_extract_keyframes"
            if frames.get("duration_s")
            else ("connector_metadata" if metadata.get("duration_s") else "unavailable")
        )
        items.append(
            {
                "content_id": content_id,
                "url": url,
                "role": video.get("role"),
                "format": video.get("format"),
                "watched": bool(video.get("watched")),
                "unwatched_reason": video.get("unwatched_reason"),
                "duration_s": duration_s,
                "duration_source": duration_source,
                "title": metadata.get("title"),
                "metadata": {
                    key: metadata[key]
                    for key in ("status", "connector_status", "origin", "limitations")
                },
                "transcript": transcript,
                "frames": {
                    "status": frames["status"],
                    "origin": frames["origin"],
                    "selection": frames["selection"],
                    "frame_count": frames["frame_count"],
                    "items": frames["items"],
                },
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "observation_contract": CONTRACT,
        "analysis_id": str(outcomes.get("analysis_id") or "").strip(),
        "items": items,
        "watched_count": sum(1 for row in items if row["watched"]),
        "unwatched_count": sum(1 for row in items if not row["watched"]),
        "empty_reason": outcomes.get("empty_reason") if not items else None,
        "dest_filename_pattern": DEST_FILENAME_PATTERN,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("watch_outcomes", type=Path)
    parser.add_argument("--envelope", type=Path, action="append", default=[])
    parser.add_argument("--envelope-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    outcomes = load_json(args.watch_outcomes)
    if not isinstance(outcomes, dict):
        raise ValueError("watch_outcomes.json must be a JSON object")
    payload = build_watch_evidence(
        outcomes,
        envelope_paths=args.envelope,
        envelope_dir=args.envelope_dir,
    )
    if not payload["analysis_id"]:
        raise ValueError("watch_outcomes.json is missing analysis_id")
    write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
