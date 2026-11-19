#!/usr/bin/env python3
"""Pick the method cards for one analysis from the method library.

    python3 select_method.py --mode <diagnosis|content_read|craft_teardown|transcript_export> [--focus id1,id2]
        [--evidence analysis/content_evidence.json] --out analysis/method.json [--library <dir>]

It runs twice in one analysis. First from the creator's request alone, before anything is fetched (no
`--evidence`): that selection decides what the observation needs (observe_video.py reads `analysis/method.json`;
the `sound` card adds the whole-video viewing). Then prepare_analysis.py runs the same selection again against the
evidence that arrived.

The mode's base card is always included (transcript_export has none). `--focus` adds zero to two topic cards
the model chose after reading the library's index.md; with none the analysis is the default one
(`default_only`, which follows the request, not the cards that survived). With `--evidence`, a card whose
`needs_evidence` kinds are not all present in that evidence is skipped and recorded; without it no card is
skipped. A card may carry a frame hint (`frames`: `include_shot_starts`, `dense_windows`); the selection merges
the hints of the cards it keeps into `frames` in method.json, which the keyframes request takes as it is (shot
starts on unless a card turns them off; at most three dense windows, in card order). Unknown or non-topic focus ids, more than two, or a base card the evidence cannot support, exit 2 with a
message.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

LIBRARY = Path(__file__).resolve().parents[1] / "references" / "video-method"
INDEX_SCHEMA = "video-method-index/v1"
SCHEMA_VERSION = "method-selection/v1"
MODES = ("diagnosis", "content_read", "craft_teardown", "transcript_export")
EVIDENCE_KINDS = ("frames", "transcript", "measure", "viewer_observations", "metadata")
MAX_TOPICS = 2
# The keyframes request's limits on dense windows (collect_media.py sends them as they are).
MAX_DENSE_WINDOWS = 3
MIN_DENSE_INTERVAL_S = 0.2


def valid_window(window: Any) -> bool:
    if not isinstance(window, dict) or set(window) != {"start_s", "end_s", "interval_s"}:
        return False
    values = [window[key] for key in ("start_s", "end_s", "interval_s")]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return False
    start, end, interval = values
    return start >= 0 and end > start and interval >= MIN_DENSE_INTERVAL_S


class SelectionError(ValueError):
    """A request the library cannot satisfy: exit 2."""


def load_index(library: Path) -> dict[str, Any]:
    index = json.loads((library / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA:
        raise ValueError(f"{library / 'index.json'} is not a {INDEX_SCHEMA} index")
    cards = index.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("the method index lists no cards")
    seen = set()
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("id"), str) or card["id"] in seen:
            raise ValueError("the method index has a card with a missing or repeated id")
        seen.add(card["id"])
        if not (library / str(card.get("file") or "")).is_file():
            raise ValueError(f"method card {card['id']} names a file that is not in the library")
        unknown = [kind for kind in card.get("needs_evidence") or [] if kind not in EVIDENCE_KINDS]
        if unknown:
            raise ValueError(f"method card {card['id']} needs unknown evidence kinds: {', '.join(unknown)}")
        hint = card.get("frames")
        if hint is not None and not (
                isinstance(hint, dict) and set(hint) <= {"include_shot_starts", "dense_windows"}
                and isinstance(hint.get("include_shot_starts", True), bool)
                and isinstance(hint.get("dense_windows", []), list)
                and len(hint.get("dense_windows", [])) <= MAX_DENSE_WINDOWS
                and all(valid_window(window) for window in hint.get("dense_windows", []))):
            raise ValueError(f"method card {card['id']} has a frame hint that is not include_shot_starts (true or "
                             f"false) and up to {MAX_DENSE_WINDOWS} dense_windows of start_s, end_s and interval_s "
                             f"(at least {MIN_DENSE_INTERVAL_S}s)")
    return index


def present_kinds(evidence: dict[str, Any]) -> set[str]:
    """Which evidence kinds this ContentEvidence actually carries."""
    kinds = set()
    frames = evidence.get("frames") or {}
    if frames.get("status") == "available" and frames.get("items"):
        kinds.add("frames")
    images = evidence.get("images") or {}
    if any(item.get("status") == "available" for item in images.get("items") or [] if isinstance(item, dict)):
        kinds.add("frames")
    transcript = evidence.get("transcript") or {}
    if transcript.get("status") == "available" and (transcript.get("cues") or transcript.get("plain_text")):
        kinds.add("transcript")
    if (evidence.get("media") or {}).get("probed"):
        kinds.add("measure")
    if (evidence.get("viewer_observations") or {}).get("items"):
        kinds.add("viewer_observations")
    if (evidence.get("content_metadata") or {}).get("status") == "available":
        kinds.add("metadata")
    return kinds


def parse_focus(text: str | None) -> list[str]:
    ids: list[str] = []
    for item in (text or "").split(","):
        item = item.strip()
        if item and item not in ids:
            ids.append(item)
    return ids


def requested_focus(method: dict[str, Any]) -> list[str]:
    """The topic cards an earlier selection was asked for: those it kept and those it skipped."""
    kept = [card["id"] for card in method.get("cards") or [] if isinstance(card, dict) and card.get("role") == "topic"]
    return kept + [item["id"] for item in method.get("skipped") or []
                   if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"] not in kept]


def frame_plan(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """The kept cards' frame hints, merged: shot starts on unless a card turns them off, dense windows in card order."""
    windows: list[dict[str, Any]] = []
    shots = True
    for card in cards:
        hint = card.get("frames") or {}
        if hint.get("include_shot_starts") is False:
            shots = False
        for window in hint.get("dense_windows") or []:
            if window not in windows:
                windows.append(window)
    return {"include_shot_starts": shots, "dense_windows": windows[:MAX_DENSE_WINDOWS]}


def select(index: dict[str, Any], mode: str, focus: list[str], evidence: dict[str, Any] | None) -> dict[str, Any]:
    """The selection; `evidence` None is the selection made before the fetch, which skips nothing."""
    if mode not in MODES:
        raise SelectionError(f"--mode takes one of {', '.join(MODES)}")
    cards = {card["id"]: card for card in index["cards"]}
    unknown = [item for item in focus if item not in cards]
    if unknown:
        topics = ", ".join(card["id"] for card in index["cards"] if card.get("topic"))
        raise SelectionError(f"unknown method card id(s): {', '.join(unknown)}. Topic cards are: {topics}")
    not_topic = [item for item in focus if not cards[item].get("topic")]
    if not_topic:
        raise SelectionError(f"{', '.join(not_topic)} is a base card, not a topic: it is included by its mode, "
                             "never passed with --focus")
    if len(focus) > MAX_TOPICS:
        raise SelectionError(f"at most {MAX_TOPICS} topic cards; got {len(focus)}")
    if mode == "transcript_export" and focus:
        raise SelectionError("a transcript export reads no method cards; pass no --focus")
    have = set(EVIDENCE_KINDS) if evidence is None else present_kinds(evidence)
    chosen, skipped, kept = [], [], []
    base = [card for card in index["cards"] if mode in (card.get("base_for") or [])]
    if mode != "transcript_export" and len(base) != 1:
        raise ValueError(f"the method library names {len(base)} base cards for {mode}; it must name exactly one")
    for card, role in [(card, "base") for card in base] + [(cards[item], "topic") for item in focus]:
        missing = [kind for kind in card.get("needs_evidence") or [] if kind not in have]
        if missing:
            if role == "base":
                raise SelectionError(f"the {mode} method ({card['id']}) needs {missing[0]} evidence, which this run "
                                     "does not have: say which evidence is missing instead of analysing without it")
            skipped.append({"id": card["id"], "reason": f"evidence_missing:{missing[0]}"})
            continue
        chosen.append({"id": card["id"], "version": card.get("version"), "role": role})
        kept.append(card)
    return {"schema_version": SCHEMA_VERSION, "library_version": index.get("library_version"), "mode": mode,
            # What was asked for, not what survived: a requested topic card skipped for missing evidence is
            # still a focused request, and the brief says it was skipped.
            "cards": chosen, "default_only": not focus,
            "skipped": skipped,
            # What the keyframes request adds to its plan; a transcript export takes no frames.
            "frames": frame_plan(kept) if mode != "transcript_export" else {"include_shot_starts": False,
                                                                            "dense_windows": []}}


def card_text(library: Path, index: dict[str, Any], card_id: str) -> str:
    card = next(card for card in index["cards"] if card["id"] == card_id)
    return (library / card["file"]).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--focus", help="zero to two topic card ids, comma-separated")
    parser.add_argument("--evidence", type=Path, help="the built evidence; leave out before the fetch")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--library", type=Path, default=LIBRARY)
    args = parser.parse_args(argv)
    try:
        index = load_index(args.library)
        evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else None
        selection = select(index, args.mode, parse_focus(args.focus), evidence)
    except SelectionError as error:
        print(json.dumps({"status": "refused", "error": str(error)}, ensure_ascii=False))
        return 2
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.out), "cards": [card["id"] for card in selection["cards"]],
                      "skipped": selection["skipped"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
