#!/usr/bin/env python3
"""Compact synthesis input: watched videos only carry cues/frames.

Unwatched rows keep id/role/reason. Catalog multiples come from watch_set.json.
Does not call the connector or a model.
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
from media_payload import load_json, write_json
from prepare_hook_context import build_research_context_ref
from baseline_availability import baseline_availability
from point_observations import CONTRACT

SCHEMA_VERSION = "deep-synthesis-input.v1"
OPENING_CUE_LIMIT = 2
LATER_CUE_LIMIT = 3
OPENING_WINDOW_S = 3.0


def _cues(item: dict[str, Any]) -> list[dict[str, Any]]:
    transcript = item.get("transcript") if isinstance(item.get("transcript"), dict) else {}
    if transcript.get("status") != "available":
        return []
    out: list[dict[str, Any]] = []
    for raw in transcript.get("cues") or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        start = raw.get("start_s")
        if not isinstance(start, (int, float)):
            continue
        out.append({"start_s": float(start), "end_s": raw.get("end_s"), "text": text})
    return out


def _frame_seconds(item: dict[str, Any]) -> list[float]:
    frames = item.get("frames") if isinstance(item.get("frames"), dict) else {}
    if frames.get("status") != "available":
        return []
    seconds: list[float] = []
    for raw in frames.get("items") or []:
        if not isinstance(raw, dict):
            continue
        value = raw.get("t_seconds")
        if isinstance(value, (int, float)):
            seconds.append(float(value))
    return seconds


def _catalog_row(watch_set: dict[str, Any], content_id: str) -> dict[str, Any]:
    for raw in watch_set.get("selected") or []:
        if isinstance(raw, dict) and raw.get("content_id") == content_id:
            return raw
    return {}


def build_deep_synthesis_input(
    evidence: dict[str, Any],
    watch_set: dict[str, Any],
    *,
    user_question: str | None = None,
    account_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis_id = str(evidence.get("analysis_id") or watch_set.get("analysis_id") or "").strip()
    if account_analysis is not None and account_analysis.get("analysis_id") != analysis_id:
        raise ValueError("account analysis_id does not match watched evidence")
    if account_analysis is not None and account_analysis.get("platform") != watch_set.get("platform"):
        raise ValueError("account analysis platform does not match watch set")
    watched: list[dict[str, Any]] = []
    unwatched: list[dict[str, Any]] = []
    for item in evidence.get("items") or []:
        if not isinstance(item, dict):
            continue
        content_id = str(item.get("content_id") or "").strip()
        if not content_id:
            continue
        catalog = _catalog_row(watch_set, content_id)
        if item.get("watched"):
            cues = _cues(item)
            opening = [row for row in cues if row["start_s"] < OPENING_WINDOW_S][:OPENING_CUE_LIMIT]
            if not opening:
                opening = cues[:OPENING_CUE_LIMIT]
            used = {id(row) for row in opening}
            later = [row for row in cues if id(row) not in used][:LATER_CUE_LIMIT]
            transcript = item.get("transcript") if isinstance(item.get("transcript"), dict) else {}
            frames = item.get("frames") if isinstance(item.get("frames"), dict) else {}
            watched.append(
                {
                    "content_id": content_id,
                    "url": str(item.get("url") or catalog.get("url") or ""),
                    "role": item.get("role") or catalog.get("role"),
                    "format": item.get("format") or catalog.get("format"),
                    "views": catalog.get("views"),
                    "view_multiple": catalog.get("view_multiple"),
                    "duration_s": item.get("duration_s"),
                    "title": item.get("title") or catalog.get("title"),
                    "metadata": item.get("metadata") or {},
                    "opening_cues": opening,
                    "later_cues": later,
                    "frame_seconds": _frame_seconds(item),
                    "transcript_origin": transcript.get("origin"),
                    "frames_origin": frames.get("origin"),
                }
            )
        else:
            unwatched.append(
                {
                    "content_id": content_id,
                    "role": item.get("role") or catalog.get("role"),
                    "reason": item.get("unwatched_reason"),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_contract": CONTRACT,
        "analysis_id": analysis_id,
        "baseline_availability": baseline_availability(account_analysis),
        "platform": str(watch_set.get("platform") or "").strip(),
        "user_question": user_question,
        "hook_context": build_research_context_ref(str(watch_set.get("platform") or ""), "deep_review"),
        "watched": watched,
        "unwatched": unwatched,
        "watched_count": len(watched),
        "unwatched_count": len(unwatched),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("watched_evidence", type=Path)
    parser.add_argument("--watch-set", type=Path, required=True)
    parser.add_argument("--user-question", default=None)
    parser.add_argument("--account-analysis", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authoring-basis", action="store_true", help="Bind original files for the source-bound authoring entry")
    parser.add_argument("--stability", type=Path, help="Original catalog stability; required with --authoring-basis")
    args = parser.parse_args(argv)
    if args.authoring_basis and (args.account_analysis is None or args.stability is None):
        parser.error("--authoring-basis requires --account-analysis and --stability")
    if args.stability is not None and not args.authoring_basis:
        parser.error("--stability is only used with --authoring-basis")
    loader = load_json
    if args.authoring_basis:
        from deep_authoring import load_strict
        loader = load_strict
    payload = build_deep_synthesis_input(
        loader(args.watched_evidence),
        loader(args.watch_set),
        user_question=args.user_question,
        account_analysis=loader(args.account_analysis) if args.account_analysis else None,
    )
    if not payload["analysis_id"]:
        raise ValueError("watched_evidence.json is missing analysis_id")
    if args.authoring_basis:
        from deep_authoring import make_basis
        payload["authoring_basis"] = make_basis(payload, args.output, {"evidence": args.watched_evidence,
            "watch_set": args.watch_set, "account_analysis": args.account_analysis, "stability": args.stability})
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
