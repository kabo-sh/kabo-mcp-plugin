#!/usr/bin/env python3
"""Classify each planned video as watched or not from persisted media envelopes.

Watched means frames arrived or a transcript arrived. Metadata alone is not watched.
Does not call the connector.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from media_payload import (
    MEDIA_CONNECTOR,
    OPERATIONS,
    canonical_operation,
    collect_for_job,
    load_envelope_files,
    load_json,
    parse_pending,
    parse_job_bindings,
    payload_available,
    pick,
    usable,
    write_json,
)

DEST_FILENAME_PATTERN = "media-<content_id>-<operation>[.attempt-<positive integer>].json"

SCHEMA_VERSION = "watch-outcomes.v1"


def _operation_status(
    *,
    envelope: dict[str, Any] | None,
    operation: str,
    pending: bool,
) -> str:
    if envelope is not None:
        if payload_available(operation, envelope):
            return "available"
        if usable(envelope) or envelope.get("status") not in {None, "queued", "running"}:
            return "failed"
    if pending:
        return "pending"
    return "not_attempted"


def _unwatched_reason(operations: dict[str, dict[str, Any]]) -> str:
    statuses = {row["status"] for row in operations.values()}
    frames = operations["extract_keyframes"]["status"]
    transcript = operations["fetch_transcript"]["status"]
    metadata = operations["collect_public_metadata"]["status"]
    if frames == "available" or transcript == "available":
        raise AssertionError("watched videos have no unwatched_reason")
    if "pending" in statuses:
        return "jobs_pending"
    if metadata == "available" and frames != "available" and transcript != "available":
        return "metadata_only"
    if statuses <= {"not_attempted"}:
        return "not_attempted"
    if "failed" in statuses:
        return "jobs_failed"
    return "frames_and_transcript_missing"


def record_watch_outcomes(
    plan: dict[str, Any],
    *,
    envelope_paths: list[Path] | None = None,
    envelope_dir: Path | None = None,
    pending: list[str] | None = None,
    deferred_incomplete: list[str] | None = None,
    jobs: list[str] | None = None,
) -> dict[str, Any]:
    loaded = load_envelope_files(envelope_paths or [], envelope_dir)
    pending_ids = parse_pending(pending)
    pending_ids.update(parse_pending(deferred_incomplete))
    # The --job ledger is in issue order; status flags only supply legacy bindings.
    binding_entries = [*(pending or []), *(deferred_incomplete or []), *(jobs or [])]
    bindings = parse_job_bindings(binding_entries)
    issued_ids: dict[tuple[str, str], list[str]] = {}
    for entry in binding_entries:
        for (owner, operation), job_id in parse_pending([entry]).items():
            ids = issued_ids.setdefault((owner, canonical_operation(operation)), [])
            if job_id in ids:
                ids.remove(job_id)
            ids.append(job_id)
    slots = {
        (str(job.get("content_id") or "").strip(), operation)
        for job in plan.get("jobs") or [] if isinstance(job, dict)
        for operation in OPERATIONS
    }
    if any(slot not in slots for slot in bindings):
        raise ValueError("job binding names content/operation outside the media plan")
    bound_ids = {job_id for ids in bindings.values() for job_id in ids}
    unbound = sorted({str(envelope["job_id"]) for _, envelope in loaded
                      if envelope.get("connector_id") == MEDIA_CONNECTOR
                      and canonical_operation(envelope.get("operation")) in OPERATIONS
                      and envelope.get("job_id") and envelope.get("job_id") not in bound_ids})
    if unbound:
        raise ValueError(
            "Media job ids have no content binding: " + ", ".join(unbound) + ". "
            "Pass --job <content_id>:<planned_operation>=<returned_job_id> for each issued job, "
            "using the request and job response together. Never infer ownership from filenames "
            "or completion order."
        )
    videos: list[dict[str, Any]] = []
    for job in plan.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        content_id = str(job.get("content_id") or "").strip()
        url = str(job.get("url") or "").strip()
        if not content_id:
            continue
        operations: dict[str, dict[str, Any]] = {}
        for operation in OPERATIONS:
            matches = collect_for_job(
                loaded, content_id=content_id, operation=operation, url=url,
                job_ids=bindings.get((content_id, operation)),
            )
            chosen_path = None
            chosen = None
            if matches:
                envelopes = [envelope for _, envelope in matches]
                chosen = pick(envelopes)
                if chosen is not None:
                    for path, envelope in reversed(matches):
                        if envelope is chosen:
                            chosen_path = path
                            break
            slot = (content_id, operation)
            pending_job = pending_ids.get(slot)
            if chosen is None or not payload_available(operation, chosen):
                terminal_ids = {
                    envelope.get("job_id") for _, envelope in matches
                    if envelope.get("status") not in {None, "queued", "running"}
                }
                unresolved = [job_id for job_id in issued_ids.get(slot, [])
                              if job_id not in terminal_ids]
                if unresolved:
                    pending_job = unresolved[-1]
                    chosen_path = None
                    chosen = None
            status = _operation_status(
                envelope=chosen,
                operation=operation,
                pending=pending_job is not None,
            )
            row: dict[str, Any] = {
                "status": status,
                "envelope": str(chosen_path) if chosen_path is not None else None,
                "job_id": pending_job,
            }
            if status != "pending":
                row["job_id"] = chosen.get("job_id") if chosen is not None else row["job_id"]
            operations[operation] = row
        watched = (
            operations["extract_keyframes"]["status"] == "available"
            or operations["fetch_transcript"]["status"] == "available"
        )
        videos.append(
            {
                "content_id": content_id,
                "url": url,
                "role": job.get("role"),
                "format": job.get("format"),
                "watched": watched,
                "unwatched_reason": None if watched else _unwatched_reason(operations),
                "operations": operations,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": str(plan.get("analysis_id") or "").strip(),
        "connector_id": MEDIA_CONNECTOR,
        "videos": videos,
        "watched_count": sum(1 for row in videos if row["watched"]),
        "unwatched_count": sum(1 for row in videos if not row["watched"]),
        "empty_reason": plan.get("empty_reason") if not videos else None,
        "dest_filename_pattern": DEST_FILENAME_PATTERN,
    }


def unattempted(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Planned videos whose three calls were never made at all.

    A video the host tried and could not serve leaves a failed envelope, and one still in flight
    leaves a job id; both are answers. All three operations sitting at `not_attempted` means the
    round simply never went out. Letting that through is what makes a deep review quietly shallow:
    2026-09-21 two regression runs planned ten videos each and dispatched four and zero, then wrote
    a report whose shot-level findings covered only what happened to be watched — the numbers were
    honest, the capability was not delivered, and nothing in the run said so until the artefacts
    were read by hand.
    """
    rows = []
    for video in payload.get("videos") or []:
        statuses = {row.get("status") for row in (video.get("operations") or {}).values()}
        if statuses and statuses <= {"not_attempted"}:
            rows.append(video)
    return rows


def still_pending(payload: dict[str, Any]) -> list[tuple[dict[str, Any], list[str]]]:
    """Planned videos whose jobs went out and have not come back.

    The sibling gate above catches a round that was never issued. This one catches the round that
    was issued and then not waited for, which produces the same shallow review and is easier to
    miss because every number in it is true: the report says which videos were watched, and the
    ones that were not simply do not appear in any shot-level finding.

    A media round takes minutes. Measured 2026-09-22 on a ten-video Instagram watch set, the
    thirty envelopes landed across 178 seconds. That same day another run stopped polling early
    and closed with seven of ten videos at `jobs_pending`, delivering craft findings from the
    three that had arrived — a deep review that watched three videos. Waiting is not optional
    here; watching the selected videos is the whole capability.
    """
    rows = []
    for video in payload.get("videos") or []:
        if video.get("watched"):
            continue
        waiting = [
            f"{name}={row.get('job_id') or 'no job id'}"
            for name, row in (video.get("operations") or {}).items()
            if row.get("status") == "pending"
        ]
        if waiting:
            rows.append((video, sorted(waiting)))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_job_plan", type=Path)
    parser.add_argument("--envelope", type=Path, action="append", default=[])
    parser.add_argument("--envelope-dir", type=Path)
    parser.add_argument("--pending", action="append", default=[])
    parser.add_argument("--deferred-incomplete", action="append", default=[])
    parser.add_argument("--job", action="append", default=[],
                        help="bind a returned job id: <content_id>:<planned_operation>=<job_id>; "
                             "required for asynchronous terminal envelopes, repeat in issue order for retries")
    parser.add_argument("--job-ledger", type=Path,
                        help="preserved initial batch receipts bound to this run and exact media plan")
    parser.add_argument(
        "--allow-unattempted",
        action="store_true",
        help="record videos whose calls were never made; only for a run the host cannot serve at all",
    )
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="record jobs that are still pending; only after polling each one across the whole "
             "media window (two to four minutes) without a terminal state",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = load_json(args.media_job_plan)
    if not isinstance(plan, dict):
        raise ValueError("media_job_plan.json must be a JSON object")
    try:
        if args.job_ledger is not None:
            if args.job:
                raise ValueError("use either --job-ledger or legacy --job, not both")
            from media_job_ledger import load_job_ledger
            args.job = load_job_ledger(args.media_job_plan, args.job_ledger)
        payload = record_watch_outcomes(
            plan,
            envelope_paths=args.envelope,
            envelope_dir=args.envelope_dir,
            pending=args.pending,
            deferred_incomplete=args.deferred_incomplete,
            jobs=args.job,
        )
    except ValueError as bad_flag:
        # A traceback here reads as a broken script; the caller needs the sentence, not the frames.
        raise SystemExit(str(bad_flag)) from None
    if not payload["analysis_id"]:
        raise ValueError("media_job_plan.json is missing analysis_id")
    missing = unattempted(payload)
    if missing and not args.allow_unattempted:
        listed = "\n".join(
            f"  {video['content_id']}  {video.get('url') or ''}" for video in missing[:20]
        )
        raise SystemExit(
            f"{len(missing)} of {len(payload['videos'])} planned videos were never called at all:\n"
            f"{listed}\n"
            "Issue collect_public_metadata, fetch_transcript and extract_keyframes for each of them "
            "through the public-video-media connector, poll the job ids the host returns, persist "
            "every terminal envelope with persist_envelope.py, then run this command again. "
            "Watching the selected videos is what this Skill is for, so do not go on to the report "
            "with these outstanding."
        )
    waiting = still_pending(payload)
    if waiting and not args.allow_pending:
        listed = "\n".join(
            f"  {video['content_id']}  {', '.join(jobs)}" for video, jobs in waiting[:20]
        )
        raise SystemExit(
            f"{len(waiting)} of {len(payload['videos'])} planned videos are still waiting on a job:\n"
            f"{listed}\n"
            "Poll each of these job ids through the platform job tool until it reaches a terminal "
            "state, persist the envelope with persist_envelope.py, then run this command again. A "
            "media round normally needs two to four minutes to come back in full, so a pending job "
            "is usually one that has not been waited for rather than one that cannot be served. "
            "Only after polling across that window without a terminal state, re-run with "
            "--allow-pending to record it as genuinely outstanding."
        )
    write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
