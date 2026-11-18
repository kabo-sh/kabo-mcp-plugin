#!/usr/bin/env python3
"""Decide which observation source a video analysis uses next, from references/observation-order.json.

The order is data, not code: `default` lists the sources a run starts with, `fallback` what to try after a
source fails, `add_when_cards` what a selected method card adds to the chosen source (the `sound` card adds the
whole-video viewing, which hears the audio: server frames plus a viewing is `combined`), and the whole-video
limits say where that source is available at all. This module reads the table plus the facts of this run
(platform, duration when known, what already failed, the analysis mode, the method cards selected before the
fetch) and nothing else. It never looks at which host runs it.

Two modes bend the table, the same way on every host:
- `transcript_export` never uses the paid whole-video viewing, not even as a fallback: its answer is the media
  call's transcript, and a finished transcript with no words (music only) is that answer, not a failure.
- `craft_teardown` reads frames (its base method card needs them), so a viewing never stands alone there:
  `whole_video` becomes `combined` (or `server_frames` where the viewing is unavailable).

    python3 observation_order.py --platform tiktok [--duration-s 42] [--failed server_frames] [--mode MODE]
        [--cards sound,opening] [--observe-source ID]

prints {"source": "<id>" | null, "reason": "..."}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ORDER_FILE = Path(__file__).resolve().parents[1] / "references" / "observation-order.json"
SCHEMA_VERSION = "observation-order/v2"
# The source names are a fixed contract: a table naming anything else is a broken table and is refused.
SOURCES = ("server_frames", "whole_video", "local_frames", "combined")
# Sources a public link can use. local_frames belongs to a file on the creator's machine only: a link is never
# downloaded locally.
PUBLIC_SOURCES = ("server_frames", "whole_video", "combined")
# When the server could not fetch the video itself (deleted, region-limited), another, paid path cannot fetch it
# either: no fallback after that.
NO_FALLBACK_AFTER = {"source_unavailable"}
VIEWER_SOURCES = ("whole_video", "combined")
# What each source is made of; a set of parts maps back to exactly one source name.
PARTS = {"server_frames": ("server_frames",), "whole_video": ("whole_video",),
         "combined": ("server_frames", "whole_video")}
ADDABLE = ("server_frames", "whole_video")
# Modes that never start a whole-video viewing, and modes whose method needs frames beside any viewing.
NO_VIEWER_MODES = {"transcript_export"}
FRAMES_MODES = {"craft_teardown"}


def load_order(path: Path | None = None) -> dict[str, Any]:
    document = json.loads((path or ORDER_FILE).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{(path or ORDER_FILE).name} is not an {SCHEMA_VERSION} table")
    default = document.get("default")
    fallback = document.get("fallback")
    if not isinstance(default, list) or not default or any(item not in PUBLIC_SOURCES for item in default):
        raise ValueError("observation order: default must list known public sources")
    if not isinstance(fallback, dict) or any(key not in SOURCES or not isinstance(value, list)
                                             or any(item not in PUBLIC_SOURCES for item in value)
                                             for key, value in fallback.items()):
        raise ValueError("observation order: fallback maps a known source to a list of known public sources")
    if type(document.get("whole_video_max_ms")) is not int or document["whole_video_max_ms"] <= 0:
        raise ValueError("observation order: whole_video_max_ms must be a positive integer")
    added = document.get("add_when_cards")
    if not isinstance(added, dict) or any(not isinstance(key, str) or not isinstance(value, list)
                                          or any(item not in ADDABLE for item in value)
                                          for key, value in added.items()):
        raise ValueError("observation order: add_when_cards maps a method card id to a list of "
                         + " / ".join(ADDABLE))
    platforms = document.get("whole_video_platforms")
    if not isinstance(platforms, list) or not all(isinstance(item, str) for item in platforms):
        raise ValueError("observation order: whole_video_platforms must list platform ids")
    return document


def whole_video_available(order: dict[str, Any], platform: str | None, duration_s: float | None) -> tuple[bool, str]:
    if platform not in order["whole_video_platforms"]:
        return False, f"whole-video viewing does not cover {platform or 'this platform'}"
    # An unknown duration does not block: the service fails an over-long video, and the fallback takes over then.
    if duration_s is not None and duration_s * 1000 > order["whole_video_max_ms"]:
        return False, f"the video runs {duration_s:g}s, past the whole-video limit of {order['whole_video_max_ms'] // 1000}s"
    return True, "available"


def available(order: dict[str, Any], source: str, platform: str | None, duration_s: float | None) -> tuple[bool, str]:
    if source == "server_frames":
        return True, "available"
    if source in {"whole_video", "combined"}:
        return whole_video_available(order, platform, duration_s)
    return False, f"{source} is not a source for a public link"


def for_mode(source: str, mode: str | None) -> list[str]:
    """What one table entry stands for in this mode: the entry itself, or what replaces it."""
    if mode in NO_VIEWER_MODES and source in VIEWER_SOURCES:
        return []
    if mode in FRAMES_MODES and source == "whole_video":
        return ["combined", "server_frames"]
    return [source]


def with_cards(order: dict[str, Any], source: str, reason: str, *, cards: list[str] | tuple[str, ...],
               platform: str | None, duration_s: float | None, tried: list[str], mode: str | None) -> tuple[str, str]:
    """`source` plus whatever the selected method cards add to it (`add_when_cards`), where that is available."""
    parts = set(PARTS[source])
    notes = []
    for card in cards:
        for extra in order["add_when_cards"].get(card, []):
            if extra in parts or extra in tried:
                continue
            if extra == "whole_video" and mode in NO_VIEWER_MODES:
                notes.append(f"the {card} card would add whole_video, but a {mode} never starts a viewing")
                continue
            ok, why = available(order, extra, platform, duration_s)
            if not ok:
                notes.append(f"the {card} card would add {extra}, but {why}")
                continue
            parts.add(extra)
            notes.append(f"the {card} card adds {extra}")
    chosen = next(name for name, made_of in PARTS.items() if set(made_of) == parts)
    return chosen, "; ".join([reason, *notes])


def choose(order: dict[str, Any], *, platform: str | None, duration_s: float | None = None,
           failed: list[str] | tuple[str, ...] = (), failure_code: str | None = None,
           force: str | None = None, local_file: bool = False, mode: str | None = None,
           cards: list[str] | tuple[str, ...] = ()) -> tuple[str | None, str]:
    """The next source to use, or None when nothing is left, with the reason."""
    if force is not None:
        if force not in SOURCES:
            raise ValueError(f"--observe-source takes one of {', '.join(SOURCES)}; got {force!r}")
        if mode in NO_VIEWER_MODES and force in VIEWER_SOURCES:
            return "server_frames", f"forced {force}, but a {mode} never starts a whole-video viewing"
        if mode in FRAMES_MODES and force == "whole_video":
            return "combined", f"forced whole_video, but a {mode} needs frames beside the viewing"
        return force, "forced by --observe-source"
    if local_file:
        return "local_frames", "the video is a file on this machine"
    tried = list(failed)
    if tried:
        if failure_code in NO_FALLBACK_AFTER:
            return None, f"{tried[-1]} failed with {failure_code}: the video itself cannot be fetched"
        candidates = order["fallback"].get(tried[-1], [])
    else:
        candidates = order["default"]
    reasons = []
    expanded = []
    for entry in candidates:
        replaced = for_mode(entry, mode)
        if not replaced:
            reasons.append(f"a {mode} never starts a whole-video viewing")
        expanded += [source for source in replaced if source not in expanded]
    for source in expanded:
        # combined contains server_frames and whole_video; once either failed it is not chosen again.
        parts = ("server_frames", "whole_video") if source == "combined" else (source,)
        if any(part in tried for part in parts):
            continue
        ok, why = available(order, source, platform, duration_s)
        if ok:
            return with_cards(order, source, "default order" if not tried else f"fallback after {tried[-1]} failed",
                              cards=cards, platform=platform, duration_s=duration_s, tried=tried, mode=mode)
        reasons.append(why)
    return None, "; ".join(reasons) or "no source left in the observation order"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform")
    parser.add_argument("--duration-s", type=float)
    parser.add_argument("--failed", action="append", default=[])
    parser.add_argument("--failure-code")
    parser.add_argument("--mode")
    parser.add_argument("--cards", default="", help="the method card ids select_method.py chose, comma-separated")
    parser.add_argument("--observe-source", help="test only: force one source")
    parser.add_argument("--local-file", action="store_true")
    parser.add_argument("--order", type=Path, help="test only: another observation-order table")
    args = parser.parse_args(argv)
    try:
        source, reason = choose(load_order(args.order), platform=args.platform, duration_s=args.duration_s,
                                failed=args.failed, failure_code=args.failure_code, force=args.observe_source,
                                local_file=args.local_file, mode=args.mode,
                                cards=[item.strip() for item in args.cards.split(",") if item.strip()])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2
    print(json.dumps({"source": source, "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
