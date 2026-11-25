#!/usr/bin/env python3
"""Decide which observation source a video analysis uses next, from references/observation-order.json.

The order is data, not code: `default` lists the sources a run starts with, `fallback` what to try after a
source fails, `add_when_cards` what a selected method card adds to the chosen source (the `sound` card adds the
whole-video viewing, which hears the audio: server frames plus a viewing is `combined`) or beside it (the
`audience-response` card adds the comment summary), `add_when_asks` what a kind of request adds beside it (a
find-the-song request adds the song identification), `add_when_modes` what an analysis mode adds beside it (a
diagnosis of a link adds the song identification, so the report can name the track in one closing line), and
`whole_video_max_ms` caps the length a viewing takes.

A side call (`SIDE_CALLS`) is not an observation source: it is one bounded call made in the observation's first
hand-over, read once, never polled and never repeated. A file attached in Kabo has no public link for it, so it
gets none; for any public link the tool's own answer says whether it can read it. The viewing is offered for any link and any `kabo-file:<id>`: whether it can
read that source is the tool's own answer, and an unsupported answer ends that source like any other failure. This module reads the table plus the facts of this run
(platform, duration when known, what already failed, the analysis mode, the method cards selected before the
fetch) and nothing else. It never looks at which host runs it.

Two modes and one kind of question bend the table, the same way on every host:
- `transcript_export` never uses the paid whole-video viewing, not even as a fallback: its answer is the media
  call's transcript, and a finished transcript with no words (music only) is that answer, not a failure.
- A find-the-song request (`--ask identify_track`, recorded by select_method.py) never starts a viewing either:
  a track is named only from metadata, on-screen text and speech, never by ear.
- `craft_teardown` reads frames (its base method card needs them), so a viewing never stands alone there:
  `whole_video` becomes `combined` (or `server_frames` where the viewing is unavailable).

    python3 observation_order.py --platform tiktok [--duration-s 42] [--failed server_frames] [--mode MODE]
        [--cards sound,opening] [--ask identify_track] [--observe-source ID]

prints {"source": "<id>" | null, "reason": "...", "side_calls": [<name>, ...]}.
"""
from __future__ import annotations

import argparse
import json
import math
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
# When the server could not fetch the video itself (deleted, private, region-limited), another, paid path cannot
# fetch it either: no fallback after that.
SOURCE_UNAVAILABLE = "source_unavailable"
NO_FALLBACK_AFTER = {SOURCE_UNAVAILABLE}
# The one evidence marker for that case (a limitation line, whichever script records it) and the one statement the
# creator gets, the same on every path: the observation, the evidence builder and the brief all use these two.
SOURCE_UNAVAILABLE_MARK = ("source_unavailable: the video itself could not be fetched (it may be deleted, private "
                           "or limited to some regions), so nothing in it was seen or heard.")
SOURCE_UNAVAILABLE_REPLY = ("This video can't be opened: it may have been deleted, made private or limited to some "
                            "regions. Send another public link or the video file and I'll analyse that instead.")
# The one total observation deadline, counted from the first fetch and the same on every host. Kabo Web ends a turn
# at 500 seconds: a throttled download once held the fetch step for 477 seconds and the turn died with no reply.
# 330 seconds is a safety net, not the expected wait: it stops only a fetch that is stuck (a throttled platform), and
# leaves about two and a half minutes of the turn for the evidence, the analysis and the reply.
# The deadline bounds when the last hand-over ends, not only when it starts: every hand-over waits inside its tool,
# so one started just before the deadline runs past it (on pre, a 45-second media poll started just before 330
# seconds held a 1 h 50 min video's fetch step for 385 seconds, and the turn died at 500 with no reply). A new
# hand-over therefore starts only while the deadline still covers its own longest wait (`round_waits`).
OBSERVE_DEADLINE_S = 330
# A video known to run past ten minutes stops waiting earlier. Its analysis reads more (the overview sheets, a long
# transcript) and its frames take minutes to decode: on pre an 18-minute video's frames arrived just before 330
# seconds, the analysis that followed needed about two and a half minutes more, and the turn died at 500 with no
# reply. 270 seconds leaves it about three and a half; frames that miss it are named as not arrived in time.
LONG_VIDEO_S = 600
LONG_VIDEO_DEADLINE_S = 270


def deadline_s(duration_s: float | None) -> int:
    """The observation deadline for a video of this duration (unknown: the general one)."""
    if isinstance(duration_s, (int, float)) and not isinstance(duration_s, bool) and duration_s > LONG_VIDEO_S:
        return LONG_VIDEO_DEADLINE_S
    return OBSERVE_DEADLINE_S


# Long videos in two steps. A full pass on a 111-minute YouTube video took the server five and a half minutes
# (pre, 2026-11-25: frames 328 s, transcript 231 s, in parallel), past what one turn can wait. By default every keyframes, measurement and transcript
# request of a diagnosis, content read or craft teardown carries `quick_above_s`: a video longer than this gets a
# quick, explicitly partial sample (a small set of frames across it, the first 60 s measured, the first 180 s of
# speech heard when the platform has no captions) and the answer offers a full ("deep") analysis. A shorter video is
# unaffected: the server ignores the threshold and does the full pass. A deep run (`--depth deep`, only after the
# creator accepted that offer) sends no threshold. A transcript export always wants every word, and an uploaded file
# keeps today's full pass, so neither sends it.
QUICK_ABOVE_S = 180
QUICK_MODES = {"diagnosis", "content_read", "craft_teardown"}
DEPTHS = ("quick", "deep")
# The full pass the server needs for a video of this length, in seconds: a rate per second of video plus a fixed
# start (download, probe). Measured on pre (2026-11-25) for a 111-minute (6660 s) YouTube video in full mode: the
# keyframes job took 328 s (resolve 14 s, ffmpeg 308 s) and the chunked speech-to-text transcript 231 s, both in
# parallel, so about 0.05 s per second of video plus 40 s; 0.06 keeps the estimate slightly conservative. A deep
# observation stops waiting once the frames cannot arrive inside its deadline.
DEEP_RATE = 0.06
DEEP_START_S = 40
# The offer adds what the analysis and the report take after the fetch (on that run, about 90 s when nothing was
# missing).
OFFER_EXTRA_S = 90


def deep_fetch_s(duration_s: float) -> float:
    """Seconds the server's full pass takes for a video this long (estimate)."""
    return DEEP_RATE * float(duration_s) + DEEP_START_S


def offer_minutes(duration_s: float) -> int:
    """Whole minutes the offer names for a full analysis of a video this long: fetch plus analysis, rounded up."""
    return max(1, math.ceil((DEEP_RATE * float(duration_s) + OFFER_EXTRA_S) / 60))
# How long one hand-over may wait inside its tool: collect_video_media's own wait when no `wait_s` is sent, and the
# `wait_s` a get_analysis_run reading sends. 45 seconds keeps a call inside the 60-second tool timeout some hosts
# (Codex) apply.
CALL_WAIT_S = 45
# A wait shorter than this is not worth a model turn: below it the call is not started at all. Both tools accept a
# `wait_s` from 0, so this is the script's floor, inside theirs.
MIN_CALL_WAIT_S = 10
# Kept back from the deadline for each hand-over's own overhead: the model making the call and running the resume.
HAND_OVER_MARGIN_S = 15
# A source started after the first one (a fallback, or a viewing waiting for the duration) starts only while this
# much of the deadline is left: a viewing of a video up to ten minutes normally finishes in one to two minutes, the
# frames and transcript of a media call in about one. Each is at least one full wait plus the margin.
MIN_LEFT_S = {"whole_video": 120, "combined": 120, "server_frames": 60}
# The line recorded when the deadline stops the observation, and the limitation it leaves in the evidence.
DEADLINE_MARK = "Observation deadline reached"
DEADLINE_TEXT = (DEADLINE_MARK + " ({deadline}s): {what} did not arrive in time, so the analysis uses only what had "
                 "arrived.")
# The limitation left when the platform refused the video's picture and sound but the post's metadata arrived: a public
# video Kabo could not download this time is not a deleted or private one, and its title, caption and counts are still
# something to answer from.
MEDIA_BLOCKED_MARK = "media_not_fetched"
MEDIA_BLOCKED_TEXT = (MEDIA_BLOCKED_MARK + ": the platform did not let Kabo download this video's picture and sound "
                      "this time, so no frame was seen and no word was heard; only the post's public metadata (title, "
                      "caption, counts) arrived.")
# Requests that never start a whole-video viewing, whatever the mode and cards.
NO_VIEWER_ASKS = {"identify_track"}
ASKS = ("identify_track",)
ASK_NAMES = {"identify_track": "find-the-song request"}
VIEWER_SOURCES = ("whole_video", "combined")
# What each source is made of; a set of parts maps back to exactly one source name.
PARTS = {"server_frames": ("server_frames",), "whole_video": ("whole_video",),
         "combined": ("server_frames", "whole_video")}
ADDABLE = ("server_frames", "whole_video")
# One bounded call beside the observation, by name: the tool it calls. Read once from the first hand-over.
SIDE_CALLS = {"song": "identify_video_song", "comment_summary": "summarize_video_comments"}
# Modes that never start a whole-video viewing, and modes whose method needs frames beside any viewing.
NO_VIEWER_MODES = {"transcript_export"}
FRAMES_MODES = {"craft_teardown"}


def round_waits(left_s: float, count: int) -> list[int]:
    """The wait, in whole seconds, each of `count` waiting calls handed over together may take, so the round still
    ends `HAND_OVER_MARGIN_S` before the deadline (`left_s` is what is left of it).

    The calls of one round are made one after another, so their waits add up: each gets an equal share of what is
    left after the margin, at most `CALL_WAIT_S`. A share under `MIN_CALL_WAIT_S` drops the last call (the list comes
    back shorter); an empty list means no call fits and the observation stops waiting now. A full wait is
    `CALL_WAIT_S`: the latest a full-length call starts is `OBSERVE_DEADLINE_S - HAND_OVER_MARGIN_S - CALL_WAIT_S`
    seconds after the first hand-over, a shortened one up to `MIN_CALL_WAIT_S` before that margin."""
    budget = left_s - HAND_OVER_MARGIN_S
    fits = min(count, max(0, int(budget // MIN_CALL_WAIT_S)))
    if fits <= 0:
        return []
    return [min(CALL_WAIT_S, int(budget // fits))] * fits


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
                                          or any(item not in ADDABLE + tuple(SIDE_CALLS) for item in value)
                                          for key, value in added.items()):
        raise ValueError("observation order: add_when_cards maps a method card id to a list of "
                         + " / ".join(ADDABLE + tuple(SIDE_CALLS)))
    asks = document.get("add_when_asks", {})
    if not isinstance(asks, dict) or any(key not in ASKS or not isinstance(value, list)
                                         or any(item not in SIDE_CALLS for item in value)
                                         for key, value in asks.items()):
        raise ValueError("observation order: add_when_asks maps a kind of request to a list of "
                         + " / ".join(SIDE_CALLS))
    modes = document.get("add_when_modes", {})
    if not isinstance(modes, dict) or any(not isinstance(key, str) or not isinstance(value, list)
                                          or any(item not in SIDE_CALLS for item in value)
                                          for key, value in modes.items()):
        raise ValueError("observation order: add_when_modes maps an analysis mode to a list of "
                         + " / ".join(SIDE_CALLS))
    if "whole_video_platforms" in document:
        # The viewing is not limited by platform here: the tool answers for the sources it cannot read.
        raise ValueError("observation order: whole_video_platforms is no longer part of the table")
    return document


def whole_video_available(order: dict[str, Any], platform: str | None, duration_s: float | None) -> tuple[bool, str]:
    # Any platform, and a file attached in Kabo: the tool's own answer says which sources it cannot read. An
    # unknown duration does not block: the service fails an over-long video, and the fallback takes over then.
    if duration_s is not None and duration_s * 1000 > order["whole_video_max_ms"]:
        return False, f"the video runs {duration_s:g}s, past the whole-video limit of {order['whole_video_max_ms'] // 1000}s"
    return True, "available"


def available(order: dict[str, Any], source: str, platform: str | None, duration_s: float | None) -> tuple[bool, str]:
    if source == "server_frames":
        return True, "available"
    if source in {"whole_video", "combined"}:
        return whole_video_available(order, platform, duration_s)
    return False, f"{source} is not a source for a public link"


def viewer_barred(mode: str | None, ask: str | None) -> bool:
    """Whether this run never starts a whole-video viewing: a transcript export, or a find-the-song request."""
    return mode in NO_VIEWER_MODES or ask in NO_VIEWER_ASKS


def barred_by(mode: str | None, ask: str | None) -> str:
    """What bars the viewing, in words: the request kind when there is one, the mode otherwise."""
    return ASK_NAMES.get(ask or "", mode or "")


def for_mode(source: str, mode: str | None, ask: str | None = None) -> list[str]:
    """What one table entry stands for in this mode: the entry itself, or what replaces it."""
    if viewer_barred(mode, ask) and source in VIEWER_SOURCES:
        return []
    if mode in FRAMES_MODES and source == "whole_video":
        return ["combined", "server_frames"]
    return [source]


def with_cards(order: dict[str, Any], source: str, reason: str, *, cards: list[str] | tuple[str, ...],
               platform: str | None, duration_s: float | None, tried: list[str], mode: str | None,
               ask: str | None = None) -> tuple[str, str]:
    """`source` plus whatever the selected method cards add to it (`add_when_cards`), where that is available."""
    parts = set(PARTS[source])
    notes = []
    for card in cards:
        for extra in order["add_when_cards"].get(card, []):
            if extra in parts or extra in tried or extra in SIDE_CALLS:
                continue
            if extra == "whole_video" and viewer_barred(mode, ask):
                notes.append(f"the {card} card would add whole_video, but a {barred_by(mode, ask)} never starts a viewing")
                continue
            ok, why = available(order, extra, platform, duration_s)
            if not ok:
                notes.append(f"the {card} card would add {extra}, but {why}")
                continue
            parts.add(extra)
            notes.append(f"the {card} card adds {extra}")
    chosen = next(name for name, made_of in PARTS.items() if set(made_of) == parts)
    return chosen, "; ".join([reason, *notes])


def side_calls(order: dict[str, Any], *, cards: list[str] | tuple[str, ...] = (), ask: str | None = None,
               file_ref: bool = False, mode: str | None = None) -> list[dict[str, Any]]:
    """The side calls the selected cards, the kind of request and the analysis mode add, in table order:
    {name, tool, why, make}.

    `make` is False for a file attached in Kabo, which has no public link for these tools: the call is not made
    and the gap is recorded the same way as a tool that answered it cannot read the link."""
    wanted: dict[str, str] = {}
    for card in cards:
        for extra in order["add_when_cards"].get(card, []):
            if extra in SIDE_CALLS:
                wanted.setdefault(extra, f"the {card} card adds {extra}")
    for extra in order.get("add_when_asks", {}).get(ask or "", []):
        wanted.setdefault(extra, f"a {ASK_NAMES.get(ask or '', ask)} adds {extra}")
    for extra in order.get("add_when_modes", {}).get(mode or "", []):
        wanted.setdefault(extra, f"a {mode} adds {extra}")
    return [{"name": name, "tool": SIDE_CALLS[name], "make": not file_ref,
             "why": why + (", but an uploaded file has no public link for it" if file_ref else "")}
            for name, why in wanted.items()]


def choose(order: dict[str, Any], *, platform: str | None, duration_s: float | None = None,
           failed: list[str] | tuple[str, ...] = (), failure_code: str | None = None,
           force: str | None = None, local_file: bool = False, mode: str | None = None,
           cards: list[str] | tuple[str, ...] = (), ask: str | None = None) -> tuple[str | None, str]:
    """The next source to use, or None when nothing is left, with the reason."""
    if ask is not None and ask not in ASKS:
        raise ValueError(f"--ask takes one of {', '.join(ASKS)}; got {ask!r}")
    if force is not None:
        if force not in SOURCES:
            raise ValueError(f"--observe-source takes one of {', '.join(SOURCES)}; got {force!r}")
        if viewer_barred(mode, ask) and force in VIEWER_SOURCES:
            return "server_frames", f"forced {force}, but a {barred_by(mode, ask)} never starts a whole-video viewing"
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
        replaced = for_mode(entry, mode, ask)
        if not replaced:
            reasons.append(f"a {barred_by(mode, ask)} never starts a whole-video viewing")
        expanded += [source for source in replaced if source not in expanded]
    for source in expanded:
        # combined contains server_frames and whole_video; once either failed it is not chosen again.
        parts = ("server_frames", "whole_video") if source == "combined" else (source,)
        if any(part in tried for part in parts):
            continue
        ok, why = available(order, source, platform, duration_s)
        if ok:
            return with_cards(order, source, "default order" if not tried else f"fallback after {tried[-1]} failed",
                              cards=cards, platform=platform, duration_s=duration_s, tried=tried, mode=mode, ask=ask)
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
    parser.add_argument("--ask", choices=ASKS, help="the kind of request select_method.py recorded, if any")
    parser.add_argument("--observe-source", help="test only: force one source")
    parser.add_argument("--local-file", action="store_true")
    parser.add_argument("--order", type=Path, help="test only: another observation-order table")
    args = parser.parse_args(argv)
    cards = [item.strip() for item in args.cards.split(",") if item.strip()]
    try:
        order = load_order(args.order)
        source, reason = choose(order, platform=args.platform, duration_s=args.duration_s,
                                failed=args.failed, failure_code=args.failure_code, force=args.observe_source,
                                local_file=args.local_file, mode=args.mode, ask=args.ask, cards=cards)
        extras = [item["name"] for item in side_calls(order, cards=cards, ask=args.ask, mode=args.mode)
                  if not args.local_file]
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2
    print(json.dumps({"source": source, "reason": reason, "side_calls": extras}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
