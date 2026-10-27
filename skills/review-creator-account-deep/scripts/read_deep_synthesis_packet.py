#!/usr/bin/env python3
"""Print every selected cue without raw metadata bulk; optionally create a canonical seed.

No connector calls, media viewing, or conclusions. Existing inputs and seeds are never rewritten.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from media_payload import load_json
from synthesis_contract import synthesis_schema, synthesis_seed


def packet(source: dict[str, Any], content_id: str | None = None) -> dict[str, Any]:
    # Validate the source identity even when this invocation only reads evidence.
    synthesis_seed(source, "en")
    rows = source.get("watched") or []
    ids = [row["content_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate watched content_id")
    if content_id is not None and content_id not in ids:
        raise ValueError(f"unknown watched content_id: {content_id}")
    selected = []
    for row in rows:
        if content_id is not None and row["content_id"] != content_id:
            continue
        metadata = row.get("metadata") or {}
        selected.append({
            **{key: row.get(key) for key in ("content_id", "url", "role", "format", "views", "view_multiple", "title", "duration_s")},
            "metadata": {key: metadata.get(key) for key in ("status", "connector_status", "origin", "limitations")},
            "opening_cues": row.get("opening_cues") or [],
            "later_cues": row.get("later_cues") or [],
            "transcript_origin": row.get("transcript_origin"),
            "frames_origin": row.get("frames_origin"),
            "available_frame_count": len(row.get("frame_seconds") or []),
            "available_opening_frame_seconds": [second for second in row.get("frame_seconds") or [] if 0 <= second <= 3],
            "point_evidence_scope": {"cue_times": "Start is cue onset; null end does not establish completion or word timing.",
                                     "frames": "Available sampled timestamps are not viewed frames or continuous interval coverage."},
        })
    return {
        "schema_version": "deep-synthesis-read-packet.v1",
        **({"observation_contract": source["observation_contract"]} if "observation_contract" in source else {}),
        "analysis_id": source["analysis_id"],
        "platform": source.get("platform"), "user_question": source.get("user_question"),
        "hook_context": source.get("hook_context"),
        "baseline_availability": source.get("baseline_availability"),
        "all_watched_content_ids": ids, "watched_total": len(rows),
        "watched": selected, "unwatched": source.get("unwatched") or [],
        "read_scope": "Selected transcript cues only. Frame availability is not proof of image viewing. Metadata may be partial.",
        "packet_end": {"analysis_id": source["analysis_id"], "included_content_ids": [row["content_id"] for row in selected]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("synthesis_input", type=Path)
    parser.add_argument("--video", default=None, help="Read one original content_id if the host truncates the full packet")
    parser.add_argument("--schema", action="store_true", help="Print the full expanded canonical synthesis contract")
    parser.add_argument("--schema-only", action="store_true", help="Read the canonical contract separately after truncated output")
    seeds = parser.add_mutually_exclusive_group()
    seeds.add_argument("--seed", type=Path, help="Create a legacy canonical seed exclusively")
    seeds.add_argument("--authoring-seed", type=Path, help="Create a source-bound authoring seed exclusively")
    parser.add_argument("--frame-object-ref", action="append", default=[], help="Include an already viewed frame object_ref in this same bound read packet")
    parser.add_argument("--authoring", action="store_true", help="Read bound point refs and the new authoring schema")
    parser.add_argument("--stability", type=Path, help="Matching catalog stability; required for a non-English seed to include unselected formats")
    parser.add_argument("--output-language", choices=("en", "zh-CN"), default="en", help="Report language (default: en)")
    args = parser.parse_args(argv)
    source = load_json(args.synthesis_input)
    output = packet(source, args.video)
    author_mode = args.authoring or args.authoring_seed is not None
    if args.frame_object_ref and not author_mode:
        parser.error("--frame-object-ref requires --authoring or --authoring-seed")
    if author_mode:
        from deep_authoring import load_strict, bound_sources, point_index, authoring_schema, authoring_seed, create_authoring_seed
        source = load_strict(args.synthesis_input)
        original = bound_sources(args.synthesis_input, source, stability_path=args.stability)
        points = point_index(original["evidence"])
        requested_frames = set()
        for object_ref in args.frame_object_ref:
            matches = [ref for ref, point in points.items()
                       if point["kind"] == "frame" and point["object_ref"] == object_ref]
            if len(matches) != 1:
                raise ValueError("viewed frame object_ref must identify exactly one original frame")
            if args.video is not None and points[matches[0]]["content_id"] != args.video:
                raise ValueError("viewed frame object_ref belongs to another selected video")
            if matches[0] in requested_frames:
                raise ValueError("duplicate viewed frame object_ref")
            requested_frames.add(matches[0])
        selected_ids = set(output["packet_end"]["included_content_ids"])
        selected_cues = {(row["content_id"], cue["start_s"], cue["text"])
                         for row in source["watched"] for cue in row["opening_cues"] + row["later_cues"]}
        output["authoring_points"] = [{"point_ref": ref, **point} for ref, point in points.items()
            if point["content_id"] in selected_ids and
            ((point["kind"] == "frame" and (args.video is not None or point["start_s"] <= 3 or ref in requested_frames)) or
             (point["kind"] == "cue" and (point["content_id"], point["start_s"], point["quote"].strip()) in selected_cues))]
        output["point_read_scope"] = "Original point refs only, not proof of image viewing. Include already viewed --frame-object-ref values in this read, or --authoring --video <id> when recovering truncated output."
        if args.authoring_seed is not None:
            create_authoring_seed(args.authoring_seed, authoring_seed(source, args.output_language, original["stability"]))
    if args.seed:
        # Closed runs are immutable. This check is portable and does not require a host directory.
        for directory in args.seed.resolve().parents:
            manifest = directory / "run-manifest.json"
            if manifest.exists():
                if load_json(manifest).get("status") in {"ok", "failed"}:
                    raise ValueError("cannot write a synthesis seed in a closed run")
                break
        if args.seed.exists():
            raise FileExistsError(args.seed)
        seed = synthesis_seed(source, args.output_language, load_json(args.stability) if args.stability else None)
        descriptor = os.open(args.seed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(seed, ensure_ascii=False, indent=2) + "\n")
    if args.schema_only:
        output = {"analysis_id": source["analysis_id"], "synthesis_contract": authoring_schema() if author_mode else synthesis_schema(), "contract_end": True}
    elif args.schema:
        output["synthesis_contract"] = authoring_schema() if author_mode else synthesis_schema()
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
