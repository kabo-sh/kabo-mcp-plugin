#!/usr/bin/env python3
"""Read a video that is on this machine, and sample frames out of it the way the connector does.

A creator's unpublished cut has no URL, so the media capability cannot reach it: that capability
runs server-side and nothing about it runs here. The file still exists and can still be read -- by
this script, on the machine the run is executing on, over the one file the creator named.

**The output has to be the same shape as the connector's, or nothing downstream can stay simple.**
Everything after acquisition -- the sampling plan, the frame list, how a frame is cited, what the
report may say about what was seen -- was written once, for frames. Emitting a second shape here
would mean every consumer learns to branch on where a frame came from, and the first consumer that
forgets is one that treats a real frame as if nobody had looked at it. So this writes
`duration_scaled_v1` frames with the same fields, and the ledger -- not the frame -- records that
the step ran locally.

**The plan is the connector's plan.** The opening three seconds and the closing two every 0.5s, the
body every second between them and spread out evenly over the frame cap (120, the server's), a frame
0.05s after each cut the connector's detector finds, and any dense windows asked for -- in the
connector's budget order (opening, closing, shot starts, dense windows, body) with its 0.25s dedupe.
Each frame records which of those it is (`source`). Timestamps match to the millisecond where the
cuts match; the cuts themselves come from this machine's ffmpeg, so a borderline cut can differ.

**Reading the file is not the same as trusting it.** A creator's filename can contain a space, a
quote or a leading dash; a container can lie about its duration or carry no audio at all. Every
invocation passes an argument list, never a shell string, and every one has a timeout. A file whose
duration cannot be established is refused rather than sampled against a guess -- a plan needs a
length, and inventing one produces a frame list that looks authoritative and points nowhere.

**What it writes has to survive being carried back by a host.** A host that runs this in a sandbox
copies the run directory back afterwards, and it refuses a whole step over one file name it cannot
replay or over a directory that grew past its size limit -- after the script already succeeded.
So frame files are named by a hash of their id, never by the id itself (the id carries `#` and the
creator's own file name), each frame is scaled down to a long edge that still reads on-screen text,
and the frame count and total bytes are capped. The id in the artifact is unchanged.

    python3 extract_local_frames.py --media FILE --out-dir DIR --artifact FILE
                                    [--hook-window-s 3.0] [--base-interval-s 1.0]
                                    [--hook-multiplier 2] [--budget 600] [--max-frames 120]
                                    [--no-shot-starts] [--dense-window START:END:INTERVAL ...]
                                    [--no-contact-sheets] [--max-total-bytes 12582912] [--jpeg-quality 3]
                                    [--measure-loudness] [--measure-signals] [--dry-run]
                                    [--deadline-s 40]

The frames are also laid out as contact sheets (`sheet-NN.jpg` beside them, nine frames to a sheet in
time order, each tile captioned with its second where ffmpeg can draw text; `frames.contact_sheets`
lists every tile's frame and second either way), so many frames are scanned in a few image reads.
    python3 extract_local_frames.py --media FILE --artifact FILE --signals-only [--deadline-s 40]

`--measure-signals` measures where the file cuts, where its audio drops below the speech floor and
where its picture holds still, with the thresholds the connector uses on a published video, and
writes them in that operation's shape under `media.signals`. Frames alone cannot answer pacing: a
cut shorter than the sampling interval falls between two frames, and silence has no pixels.

**A command that is stopped from outside delivers nothing, so this one stops itself first.** Some
hosts end a command after a fixed time and keep nothing it wrote -- not the frames already on disk,
not the artifact. Every step therefore runs against `--deadline-s`, counted from the moment the
command started: frames are written opening first and the body thinned when time runs out, the
artifact is written before any measurement starts, and a measurement still running at the deadline
is stopped and kept as far as it got, with the stretch it never reached named as unread.

**Measurement is its own command.** `--signals-only` measures the file and adds `media.signals` to
the artifact an earlier frame command wrote for that same file, leaving its frames as they were.
Run on its own it gets the whole deadline instead of whatever the frames left over, and a
measurement that fails or runs out costs the frames nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# Every executable this package is allowed to start. Kept identical to the survey script's set and
# enforced the same way: these two read and decode media, and nothing else here needs a subprocess.
ALLOWED_TOOLS = frozenset({"ffmpeg", "ffprobe"})

PROBE_TIMEOUT_S = 60
FRAME_TIMEOUT_S = 60
LOUDNESS_TIMEOUT_S = 900

# A frame near the end that a seek cannot decode (an input seek close to the final timestamp lands
# past the last decodable frame on several containers) is tried once more this much earlier.
CLOSING_RETRY_OFFSET_S = 0.25

# Loudness integrated over less than roughly this much audio is not a measurement of anything.
MIN_LOUDNESS_AUDIO_S = 3.0

# A frame is scaled so its longer edge is at most this. 720 still reads a caption on a phone-sized
# frame; a full-resolution 4K master is ten times the bytes and reads the same words.
FRAME_LONG_EDGE_PX = 720
FRAME_SCALE_FILTER = (f"scale='if(gte(iw,ih),min({FRAME_LONG_EDGE_PX},iw),-2)'"
                      f":'if(gte(iw,ih),-2,min({FRAME_LONG_EDGE_PX},ih))'")

# The frame cap is the server's (120), so a local file is sampled like a link. A sandboxed host that
# collects every file the step wrote refuses the whole step past a file count or a total size (one host
# allowed 128 files and 16 MiB for the run directory, the run's other files counted too): there, pass a
# smaller --max-frames (90 leaves room for the contact sheets). The byte cap stops writing before 16 MiB
# either way; the plan thins the body the same honest way it does for --budget.
DEFAULT_MAX_FRAMES = 120
DEFAULT_MAX_TOTAL_BYTES = 12 * 1024 * 1024

# Measurement thresholds, the connector's defaults verbatim so one video measured on either path gives
# the same numbers. Scene-change sensitivity 0.15: at 0.30 a six-cut talking-head clip shot in one
# room measured zero cuts, which reads as "one take" rather than as a gap.
SHOT_THRESHOLD = 0.15
SILENCE_FLOOR_DB = -40
SILENCE_MIN_S = 0.5
FREEZE_MIN_S = 1.0
SIGNAL_TIMEOUT_S = 900
# The measurement reads a reduced copy of the picture: ten frames a second, long edge 640. Decoding
# the file is unavoidable, but running both detectors on every full-resolution frame was most of the
# cost -- three separate full decodes of a 4K file did not fit in a minute. Both detectors compare
# whole frames, so a cut or a held picture survives the reduction, and the thresholds above stay the
# connector's: on a generated 4K test reel the reduced pass found the same held spans as full
# resolution and every real cut (full resolution missed one and added one). Cut times are then on a
# 0.1s grid, finer than any pacing call made from them.
SIGNAL_FPS = 10
SIGNAL_LONG_EDGE_PX = 640
SIGNAL_SCALE_FILTER = (f"scale='if(gte(iw,ih),min({SIGNAL_LONG_EDGE_PX},iw),-2)'"
                       f":'if(gte(iw,ih),-2,min({SIGNAL_LONG_EDGE_PX},ih))'")
# Every step stops itself this many seconds after the command started unless told otherwise. A
# host that ends a command after about a minute keeps nothing from one it had to kill, and fetching
# the input can already have spent part of that minute.
DEFAULT_DEADLINE_S = 40.0
# A pass started with less time than this left reads too little to be worth a ledger entry.
MIN_SIGNAL_PASS_S = 2.0
SIGNAL_OPERATIONS = frozenset({"measure_shots", "measure_silence", "measure_freeze",
                               "measure_shots_and_freeze"})
BYTE_BUDGET_REASON = "the frame byte budget for this step was used up"
TIME_BUDGET_REASON = "this command's time budget was used up"
# Below this a single shot is an ordinary one-take clip; above it, "no cuts" is worth a second look.
ONE_SHOT_SUSPECT_S = 15.0

# More than this share of the plan missing means the frame track is not a reading of the video any
# more, and the status says so rather than presenting a quarter-sampled video as sampled.
MAX_SKIPPED_SHARE = 0.25


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def readability(path: Path) -> tuple[str, str]:
    """Whether this file can actually be opened here, and why not when it cannot.

    Opening it rather than asking `exists()` or `os.access`, because on a sandboxed host those two
    answer a different question than the one that matters. A host may deny a whole directory tree,
    and a denied path then reports as absent: `is_file()` swallows the permission error and returns
    False. A creator whose video is right where they left it would be told there is no file there,
    which sends them looking for a missing file instead of at the one thing they can act on.

    The three answers are different situations with different advice, so they stay distinct all the
    way out to the message.
    """
    try:
        with path.open("rb") as handle:
            handle.read(1)
    except FileNotFoundError:
        return "not_found", "no file exists at this path"
    except IsADirectoryError:
        return "not_a_file", "this path is a directory, not a video file"
    except PermissionError:
        return "denied", (
            "the file is there, but this host does not allow reading that location. Hosts that "
            "sandbox the agent commonly deny the personal folders whole -- Documents, Desktop, "
            "Downloads, Pictures, Movies, Music -- and external volumes with them. Ask the creator "
            "to put a copy somewhere outside those (a folder they make in their home directory "
            "works) and name that path instead"
        )
    except OSError as error:
        return "unreadable", f"this file could not be opened here: {error}"
    return "ok", ""


def invocation_digest(args: list[str], media: Path) -> str:
    """Hash the argument list with the media path standing in as a placeholder.

    Two machines that ran the same step should produce the same hash, and they will not if the hash
    covers macOS home directories. Substituting the path also keeps a home directory out of an
    artifact that travels downstream -- the same rule the evidence builder already applies to frame
    paths.
    """
    generic = ["<media>" if part == str(media) else part for part in args]
    return hashlib.sha256(json.dumps(generic, ensure_ascii=False).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    """sha256 of a file, read in chunks: a master export can be several gigabytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_tool(name: str, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    if name not in ALLOWED_TOOLS:
        raise ValueError(f"{name!r} is not an allowed tool; this package starts only {sorted(ALLOWED_TOOLS)}")
    return subprocess.run(  # noqa: S603 - argv is a list, shell is never used, timeout is always set
        [name, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def tool_version(name: str) -> str | None:
    try:
        result = run_tool(name, ["-version"], 10)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (result.stdout or result.stderr or "").strip().splitlines()
    return lines[0] if lines else None


def as_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def as_int(value) -> int | None:
    number = as_float(value)
    return int(number) if number is not None else None


def probe(media: Path) -> tuple[dict, dict]:
    """One ffprobe call, read as JSON.

    JSON rather than parsing the human-readable output: that output is written for a person, changes
    between releases, and a regex over it fails silently by matching the wrong line rather than
    loudly by not matching.
    """
    args = ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", "--", str(media)]
    started = now()
    result = run_tool("ffprobe", args, PROBE_TIMEOUT_S)
    step = {
        "step": "local_extraction",
        "operation": "probe_media",
        "tool": "ffprobe",
        "tool_version": tool_version("ffprobe"),
        "invocation_sha256": invocation_digest(args, media),
        "started_at": started,
        "status": "completed" if result.returncode == 0 else "failed",
    }
    if result.returncode != 0:
        step["note"] = (result.stderr or "").strip()[:500]
        return step, {}
    try:
        return step, json.loads(result.stdout)
    except json.JSONDecodeError as error:
        step["status"] = "failed"
        step["note"] = f"ffprobe returned output that is not JSON: {error}"
        return step, {}


def read_media_facts(payload: dict) -> dict:
    """Turn one ffprobe response into the media block's fields.

    Duration is taken from the container first and from the video stream second, because a stream
    duration can be absent on a remuxed file while the container's is right there. If neither is
    present the caller refuses the file: every part of the plan below is a fraction of the length,
    and a plan built on a guessed length is a frame list that cites seconds nothing was read at.
    """
    streams = payload.get("streams") or []
    container = payload.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = as_float(container.get("duration"))
    if duration is None and video is not None:
        duration = as_float(video.get("duration"))

    facts = {
        "duration_s": round(duration, 3) if duration is not None else None,
        "width": as_int(video.get("width")) if video else None,
        "height": as_int(video.get("height")) if video else None,
        "has_audio": audio is not None,
        "encoding": {
            "video_codec": (video or {}).get("codec_name"),
            "video_bitrate_bps": as_int((video or {}).get("bit_rate")) if video else None,
            # Kept as the string ffprobe reports ("30000/1001"): the evidence schema types this as a
            # string, and evaluating the fraction would turn an exact rate into 29.97.
            "frame_rate": (video or {}).get("avg_frame_rate") if video else None,
            "audio_codec": (audio or {}).get("codec_name"),
            "audio_bitrate_bps": as_int((audio or {}).get("bit_rate")) if audio else None,
            "audio_sample_rate": as_int((audio or {}).get("sample_rate")) if audio else None,
            "audio_channels": as_int((audio or {}).get("channels")) if audio else None,
        },
    }
    facts["_exact_duration_s"] = duration
    return facts


# Body spacing above which a thinned body counts as degraded coverage.
DEGRADED_ABOVE_S = 1.0
# The connector's duration_scaled_v1 plan (public-video-media), mirrored: a fixed opening window and a closing
# window sampled at the hook interval, the body at the base interval between them, and, when asked, a frame just
# after each cut and denser windows, all inside one frame budget.
HOOK_DENSE_S = 3.0
CLOSING_WINDOW_S = 2.0
SHOT_START_OFFSET_S = 0.05
DEDUPE_S = 0.25
MIN_DENSE_INTERVAL_S = 0.2
MAX_DENSE_WINDOWS = 3
# Which frames survive when the budget runs short, and the order they are written in when time or bytes do.
BUDGET_PRIORITY = ("hook", "closing", "shot_start", "dense_window", "body")
# Shot starts read cuts off a cheap decode: every frame, picture only, 240 lines high, at the measurement's
# sensitivity. This pass gets at most this share of the time left, so the frames still have most of it.
SHOT_SCALE_FILTER = "scale=-2:240:flags=fast_bilinear"
SHOT_TIME_SHARE = 0.35


def _ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def _near(seconds: float, others: list[float], within_s: float) -> bool:
    # Integer milliseconds and a strict "<", as the connector compares them.
    limit = _ms(within_s)
    return any(abs(_ms(seconds) - _ms(other)) < limit for other in others)


def _even_pick(items: list, keep: int) -> list:
    """`keep` items spread evenly by index: item floor(i*n/keep)."""
    if keep <= 0:
        return []
    if len(items) <= keep:
        return list(items)
    return [items[(index * len(items)) // keep] for index in range(keep)]


def parse_dense_window(text: str) -> dict:
    """`start:end:interval` in seconds, as --dense-window takes it."""
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"--dense-window takes start:end:interval in seconds; got {text!r}")
    start, end, interval = (float(part) for part in parts)
    if start < 0 or end <= start or interval < MIN_DENSE_INTERVAL_S:
        raise ValueError(f"--dense-window {text!r}: start must be at least 0, end after start, and the interval "
                         f"at least {MIN_DENSE_INTERVAL_S}s")
    return {"start_s": start, "end_s": end, "interval_s": interval}


def method_frames(artifact: Path) -> dict:
    """The frame plan select_method.py wrote beside the artifact (analysis/method.json), when there is one."""
    plan = {"include_shot_starts": True, "dense_windows": []}
    try:
        method = json.loads((artifact.expanduser().parent / "method.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return plan
    frames = method.get("frames") if isinstance(method, dict) else None
    if not isinstance(frames, dict):
        return plan
    plan["include_shot_starts"] = frames.get("include_shot_starts") is not False
    for window in frames.get("dense_windows") or []:
        try:
            plan["dense_windows"].append(parse_dense_window(
                f"{window['start_s']}:{window['end_s']}:{window['interval_s']}"))
        except (KeyError, TypeError, ValueError):
            continue
    plan["dense_windows"] = plan["dense_windows"][:MAX_DENSE_WINDOWS]
    return plan


def plan_frames(duration_s: float, hook_window_s: float, base_interval_s: float,
                hook_multiplier: int, budget: int, *, cuts: list[float] | None = None,
                dense_windows: list[dict] | tuple = (), shot_detection: dict | None = None) -> dict:
    """Where to sample, and what to record about the choice: the connector's duration_scaled_v1 plan.

    The opening three seconds every `base_interval_s / hook_multiplier` (0.5s), a closing window over the last two
    seconds at the same spacing, and the body between them every `base_interval_s` (1s), spread out evenly when
    that would pass the budget. `cuts` (None when shot starts were not asked for) add a frame 0.05s after each
    cut and `dense_windows` add denser stretches; both come out of the body's share. When the budget runs short
    the order is opening, closing, shot starts, dense windows, body: the opening is never thinned. A frame closer
    than 0.25s to one of a higher-priority kind is dropped (a dense window closer than half its interval), and
    a body point that close to a shot start or dense frame is skipped without giving its slot back.

    `hook_window_s` is how far in the hook is judged (3s for a Short, 15-30 for long-form); it is recorded and
    does not change what is sampled. Timestamps are computed from the unrounded interval and only the reported
    interval is rounded.
    """
    hook_interval_s = base_interval_s / hook_multiplier
    shots_requested = cuts is not None
    dropped_budget = {"shot_start": 0, "dense_window": 0}
    dropped_duplicate = {"shot_start": 0, "dense_window": 0, "body": 0}
    window_records: list[dict] = []
    if duration_s <= HOOK_DENSE_S:
        count = max(1, min(budget, math.ceil(duration_s / hook_interval_s - 1e-9)))
        hook = [round(index * hook_interval_s, 3) for index in range(count)]
        closing: list[float] = []
        closing_start = None
        span = 0.0
    else:
        hook = [round(index * hook_interval_s, 3)
                for index in range(min(budget, int(round(HOOK_DENSE_S / hook_interval_s))))]
        closing_start = max(HOOK_DENSE_S, duration_s - CLOSING_WINDOW_S)
        count = max(0, min(budget - len(hook), math.ceil((duration_s - closing_start) / hook_interval_s - 1e-9)))
        closing = [round(closing_start + index * hook_interval_s, 3) for index in range(count)]
        span = closing_start - HOOK_DENSE_S
    fixed = hook + closing
    left = budget - len(fixed)

    shot_frames: list[float] = []
    if shots_requested and duration_s > HOOK_DENSE_S:
        for cut in cuts:
            at = round(cut + SHOT_START_OFFSET_S, 3)
            if not (cut > 0 and at < duration_s):
                continue
            if _near(at, fixed + shot_frames, DEDUPE_S):
                dropped_duplicate["shot_start"] += 1
                continue
            shot_frames.append(at)
        kept = _even_pick(shot_frames, max(0, left))
        dropped_budget["shot_start"] = len(shot_frames) - len(kept)
        shot_frames = kept
    left -= len(shot_frames)

    dense_frames: list[float] = []
    if dense_windows and duration_s > HOOK_DENSE_S:
        clipped = []
        for window in list(dense_windows)[:MAX_DENSE_WINDOWS]:
            start, end = min(window["start_s"], duration_s), min(window["end_s"], duration_s)
            clipped.append((window, start, end, start != window["start_s"] or end != window["end_s"]))

        def lay(windows: list, factor: int) -> tuple[list[list[float]], int]:
            placed: list[list[float]] = []
            taken: list[float] = []
            duplicates = 0
            for window, start, end, _ in windows:
                interval = window["interval_s"] * factor
                grid = [start] if end <= start else [start + step * interval
                                                     for step in range(int(math.ceil((end - start) / interval - 1e-9)))]
                within = min(DEDUPE_S, interval / 2)
                frames = []
                for at in (round(value, 3) for value in grid):
                    if at >= duration_s or _near(at, fixed + shot_frames, within) or _near(at, taken, within):
                        duplicates += 1
                        continue
                    frames.append(at)
                    taken.append(at)
                placed.append(frames)
            return placed, duplicates

        usable = [index for index, entry in enumerate(clipped) if entry[1] < duration_s]
        factor = 1
        while True:
            placed, duplicates = lay([clipped[index] for index in usable], factor)
            if sum(len(frames) for frames in placed) <= max(0, left) or all(len(frames) <= 1 for frames in placed):
                break
            factor += 1
        while usable and sum(len(frames) for frames in placed) > max(0, left):
            # Still too many at one frame a window: the later windows go whole.
            dropped_budget["dense_window"] += len(placed[-1])
            usable = usable[:-1]
            placed, duplicates = lay([clipped[index] for index in usable], factor)
        dropped_duplicate["dense_window"] = duplicates
        for index, (window, start, end, was_clipped) in enumerate(clipped):
            frames = placed[usable.index(index)] if index in usable else []
            record = {"start_s": round(start, 3), "end_s": round(end, 3), "requested_interval_s": window["interval_s"],
                      "interval_s": round(window["interval_s"] * factor, 3), "frames": len(frames),
                      "clipped": was_clipped}
            if index not in usable:
                record["ignored"] = "budget" if start < duration_s else "out_of_range"
            window_records.append(record)
            dense_frames += frames
    left -= len(dense_frames)

    body: list[float] = []
    body_interval_s = 0.0
    if span > 0 and left > 0:
        body_interval_s = max(base_interval_s, span / left)
        count = min(left, int(math.floor(span / body_interval_s + 1e-9)))
        extra = shot_frames + dense_frames
        for index in range(count):
            at = round(HOOK_DENSE_S + index * body_interval_s, 3)
            if extra and _near(at, extra, DEDUPE_S):
                dropped_duplicate["body"] += 1
                continue
            body.append(at)
    body_degraded = duration_s > HOOK_DENSE_S and (body_interval_s > DEGRADED_ABOVE_S or not closing
                                                     or (span > 0 and not body))

    kinds = ([(at, "hook") for at in hook] + [(at, "closing") for at in closing]
             + [(at, "shot_start") for at in shot_frames] + [(at, "dense_window") for at in dense_frames]
             + [(at, "body") for at in body])
    kinds.sort(key=lambda pair: (pair[0], BUDGET_PRIORITY.index(pair[1])))
    timestamps = [at for at, _ in kinds]

    hook_dense_window_s = min(HOOK_DENSE_S, duration_s)
    note = (f"Opening {hook_dense_window_s:g}s sampled every {hook_interval_s:g}s"
            + (f", the body every {round(body_interval_s, 3):g}s" if body else "")
            + (f", and the closing {CLOSING_WINDOW_S:g}s from {closing_start:g}s every {hook_interval_s:g}s"
               if closing else "")
            + (f"; {len(shot_frames)} frame(s) just after a cut" if shots_requested else "")
            + (f"; {len(dense_frames)} frame(s) in dense windows" if dense_windows else "")
            + ". Sampled on this machine.")
    if body_degraded:
        note += (f" The body was thinned to fit a budget of {budget} frames, so a cut shorter than "
                 f"{round(body_interval_s, 3):g}s may fall between frames.")

    plan = {
        "base_interval_s": base_interval_s,
        "hook_window_s": hook_window_s,
        "hook_dense_window_s": hook_dense_window_s,
        "hook_interval_s": hook_interval_s,
        "hook_frames": len(hook),
        "body_interval_s": round(body_interval_s, 3),
        "body_frames": len(body),
        "closing_frame_s": round(closing_start, 3) if closing_start is not None else round(duration_s, 3),
        "budget": budget,
        "frames": len(timestamps),
        "body_degraded": body_degraded,
        "note": note,
        "_timestamps": timestamps,
        "_kinds": [kind for _, kind in kinds],
    }
    if shots_requested or dense_windows:
        plan.update({
            "include_shot_starts": shots_requested,
            "shot_detection": shot_detection or {"status": "detected" if shots_requested else "not_requested",
                                                 "cuts": len(cuts or []), "threshold": SHOT_THRESHOLD},
            "shot_start_frames": len(shot_frames),
            "dense_window_frames": len(dense_frames),
            "dense_windows": window_records,
            "dropped_for_budget": dropped_budget,
            "dropped_as_duplicate": dropped_duplicate,
            "dedupe_s": DEDUPE_S,
            "budget_priority": list(BUDGET_PRIORITY),
        })
    return plan


def frame_identifier(content_id: str, ordinal: int, seconds: float) -> str:
    """The connector's id shape, with the local file's stem where the platform id would be.

    The shape carries the ordinal and the second, which is what makes a citation readable in a
    report without opening anything. Matching it means a consumer that learned to read one kind of
    frame id does not have to learn a second.
    """
    return f"{content_id}#frame-{ordinal:03d}-{seconds:.3f}s.jpg"


def frame_file_name(frame_id: str) -> str:
    """The file a frame is written to: a hash of its id, never the id itself.

    The id carries `#` and the creator's own file name, which can hold Unicode, brackets or quotes.
    A host that copies the run directory back accepts only plain names and rejects the whole step
    over one it cannot replay -- in production that turned 60 successfully written frames into a
    failed step. Hashing the exact id keeps two files extracted into one directory from colliding,
    which an ordinal-and-second name would not. The evidence builder names connector frames the
    same way for the same reason.
    """
    return "frame-" + hashlib.sha256(frame_id.encode("utf-8")).hexdigest() + ".jpg"


def coarse_to_fine(indices: list[int]) -> list[int]:
    """`indices` in an order whose every prefix is spread evenly over them: running out leaves an even thinning."""
    ordered: list[int] = []
    taken: set[int] = set()
    step = 1
    while step < len(indices):
        step *= 2
    while step >= 1:
        for position in range(0, len(indices), step):
            if position not in taken:
                taken.add(position)
                ordered.append(indices[position])
        step //= 2
    return ordered


def extraction_order(kinds: list[str]) -> list[int]:
    """The order frames are written in: the opening, the close, shot starts, dense windows, then the body.

    Written in time order, a step that runs out of room loses the end of the video -- the ending is
    one of the four things a creator asks about before posting. Written in budget priority, running out
    leaves the hook and the close whole, and each later kind is written coarse-to-fine, so what is left
    out is an even thinning, not a missing final third.
    """
    ordered: list[int] = []
    for kind in BUDGET_PRIORITY:
        indices = [index for index, value in enumerate(kinds) if value == kind]
        ordered += indices if kind in ("hook", "closing") else coarse_to_fine(indices)
    return ordered


def extract(media: Path, out_dir: Path, plan: dict, content_id: str, quality: int,
            max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
            deadline: float | None = None) -> tuple[dict, list, list]:
    """Write the planned frames, in `extraction_order`, until the plan, the bytes or the time ends.

    Running out of time is handled exactly like running out of bytes: the frames not yet written
    are skipped with the reason, and because the opening and the close are written first, what is
    left is the hook, the ending and an evenly thinner body rather than a missing final third.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamps = plan["_timestamps"]
    items: list[dict] = []
    skipped: list[dict] = []
    written_bytes = 0
    started = started_at = now()
    sample_args: list[str] = []

    kinds = plan["_kinds"]
    last = len(timestamps) - 1
    for index in extraction_order(kinds):
        ordinal, seconds = index + 1, timestamps[index]
        is_closing = index == last and kinds[index] in ("closing", "body")
        attempts = [seconds]
        if is_closing:
            attempts.append(round(max(0.0, seconds - CLOSING_RETRY_OFFSET_S), 3))

        if written_bytes >= max_total_bytes:
            # Out of room. The rest are skipped rather than written and then refused with the whole
            # step: a thinner frame track is a reading, a refused step is nothing at all.
            skipped.append({"ordinal": ordinal, "t_seconds": seconds, "reason": BYTE_BUDGET_REASON})
            continue
        left = None if deadline is None else deadline - time.monotonic()
        if left is not None and left <= 0:
            # Out of time, for the same reason: a host that has to stop this command keeps none of
            # the frames already written.
            skipped.append({"ordinal": ordinal, "t_seconds": seconds, "reason": TIME_BUDGET_REASON})
            continue

        written = None
        frame_id = frame_identifier(content_id, ordinal, seconds)
        for attempt in attempts:
            target = out_dir / frame_file_name(frame_id)
            args = ["-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{attempt:.3f}", "-i", str(media),
                    "-frames:v", "1", "-update", "1", "-vf", FRAME_SCALE_FILTER,
                    "-q:v", str(quality), str(target)]
            if not sample_args:
                sample_args = args
            try:
                result = run_tool("ffmpeg", args, FRAME_TIMEOUT_S if left is None
                                  else max(0.5, min(FRAME_TIMEOUT_S, left)))
            except subprocess.TimeoutExpired as error:
                reason = TIME_BUDGET_REASON if left is not None and left < FRAME_TIMEOUT_S else str(error)[:300]
                skipped.append({"ordinal": ordinal, "t_seconds": seconds, "reason": reason})
                target.unlink(missing_ok=True)  # a half-written frame is not a frame
                break
            except (OSError, subprocess.SubprocessError) as error:
                skipped.append({"ordinal": ordinal, "t_seconds": seconds, "reason": str(error)[:300]})
                break
            if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
                written = (target, attempt)
                break
            # An empty or absent output is a skip, not a rename of the next frame: because every
            # frame has its own named output rather than a numbered pattern, one failure here cannot
            # slide every later frame onto a second it was not read at.
            if target.exists() and target.stat().st_size == 0:
                target.unlink()
        if written is None:
            if not any(entry["ordinal"] == ordinal for entry in skipped):
                skipped.append({"ordinal": ordinal, "t_seconds": seconds,
                                "reason": "ffmpeg wrote no frame at this timestamp"})
            continue

        target, _ = written
        written_bytes += target.stat().st_size
        items.append({
            "frame_id": frame_id,
            "_file": target.name,
            "t_seconds": seconds,
            "source": kinds[index],
            "sha256": file_digest(target),
            "bytes": target.stat().st_size,
            "retained_outside_git": True,
            "path": None,  # filled by the caller, relative to the artifact
        })

    items.sort(key=lambda item: item["t_seconds"])
    skipped.sort(key=lambda entry: entry["ordinal"])
    total = len(timestamps)
    if not items:
        status = "failed"
    elif len(skipped) > total * MAX_SKIPPED_SHARE:
        status = "completed_partial"
    else:
        status = "completed"

    step = {
        "step": "local_extraction",
        "operation": "extract_keyframes",
        "tool": "ffmpeg",
        "tool_version": tool_version("ffmpeg"),
        "invocation_sha256": invocation_digest(sample_args, media) if sample_args else "",
        "started_at": started_at,
        "status": status,
        "note": f"{len(items)} of {total} planned frames written" + (f"; {len(skipped)} skipped" if skipped else ""),
    }
    return step, items, skipped


def measure_loudness(media: Path, duration_s: float | None) -> tuple[dict | None, dict, list]:
    """Integrated loudness and true peak, when the caller asks for them.

    Off by default because it decodes the whole audio track, which on a long video costs more than
    every frame above put together. The numbers are worth having: a true peak above zero is what a
    platform's own re-encode turns into audible distortion, and it is the one reading in this block
    that means the same thing on the master as on the delivered copy.
    """
    limitations: list[str] = []
    if duration_s is not None and duration_s < MIN_LOUDNESS_AUDIO_S:
        limitations.append("The track is too short for an integrated loudness measurement to mean "
                           "anything, so none was taken.")
        return None, {}, limitations

    args = ["-nostdin", "-hide_banner", "-i", str(media), "-map", "0:a:0",
            "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    started = now()
    try:
        result = run_tool("ffmpeg", args, LOUDNESS_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as error:
        limitations.append("Loudness could not be measured on this machine.")
        return None, {"step": "local_extraction", "operation": "measure_loudness", "tool": "ffmpeg",
                      "tool_version": tool_version("ffmpeg"),
                      "invocation_sha256": invocation_digest(args, media), "started_at": started,
                      "status": "failed", "note": str(error)[:300]}, limitations

    step = {
        "step": "local_extraction",
        "operation": "measure_loudness",
        "tool": "ffmpeg",
        "tool_version": tool_version("ffmpeg"),
        "invocation_sha256": invocation_digest(args, media),
        "started_at": started,
        "status": "completed",
    }
    stderr = result.stderr or ""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        step["status"] = "failed"
        limitations.append("Loudness could not be measured on this machine.")
        return None, step, limitations
    try:
        payload = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        step["status"] = "failed"
        limitations.append("Loudness could not be measured on this machine.")
        return None, step, limitations

    return {
        "integrated_loudness_lufs": as_float(payload.get("input_i")),
        "true_peak_dbfs": as_float(payload.get("input_tp")),
    }, step, limitations


def shots_from_cuts(cuts: list[float], duration_s: float) -> list[dict]:
    """Cut times and the length into a shot list; N cuts give N+1 shots."""
    bounds = [0.0, *[cut for cut in cuts if 0 < cut < duration_s], duration_s]
    shots = []
    for start, end in zip(bounds, bounds[1:]):
        if end <= start:
            continue
        shots.append({"index": len(shots), "start_s": round(start, 3), "end_s": round(end, 3),
                      "duration_s": round(end - start, 3)})
    return shots


def parse_spans(stderr: str, start_key: str, end_pattern: str, duration_s: float) -> list[dict]:
    """Start/end pairs out of a detector's log, the one the file ends inside closed at its end.

    The trailing span is the one a reader most wants -- a video that ends in silence or on a held
    frame -- and the detector prints no end line for it because the file stopped first. Here the
    length is measured, so its end is a fact rather than a guess, and the evidence schema wants a
    number there.
    """
    spans: list[dict] = []
    for line in stderr.splitlines():
        start = re.search(start_key + r":\s*(-?[\d.]+)", line)
        if start:
            spans.append({"start_s": max(0.0, round(float(start.group(1)), 3)), "end_s": None,
                          "duration_s": None})
            continue
        end = re.search(end_pattern, line)
        if end and spans and spans[-1]["end_s"] is None:
            spans[-1]["end_s"] = round(float(end.group(1)), 3)
            spans[-1]["duration_s"] = round(spans[-1]["end_s"] - spans[-1]["start_s"], 3)
    if spans and spans[-1]["end_s"] is None:
        spans[-1]["end_s"] = round(duration_s, 3)
        spans[-1]["duration_s"] = round(max(0.0, duration_s - spans[-1]["start_s"]), 3)
    return spans


def as_text(value) -> str:
    """Output a timed-out child left behind arrives as bytes even when text was asked for."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def progress_seconds(progress: str) -> float:
    """How far into the file a pass got, from ffmpeg's `-progress` lines; 0 when none arrived."""
    reached = 0.0
    for hit in re.findall(r"^out_time_us=(\d+)\s*$", progress, flags=re.MULTILINE):
        reached = max(reached, int(hit) / 1_000_000)
    return reached


def run_pass(args: list[str], deadline: float) -> tuple[str, str, float | None, str]:
    """One measurement pass, stopped at the deadline and kept as far as it got.

    Returns the pass's status, its log, how many seconds of the file it read (None for all of it)
    and a note. Stopped early, the detectors have already printed everything they found up to the
    point the decoder reached, and `-progress` says where that was, so the part that was read is a
    measurement and only the rest is not. A last log line cut off mid-write is dropped rather than
    read as a shorter number.
    """
    left = deadline - time.monotonic()
    if left < MIN_SIGNAL_PASS_S:
        return "failed", "", 0.0, "not started: this command's time budget was already used up"
    try:
        result = run_tool("ffmpeg", args, min(SIGNAL_TIMEOUT_S, left))
    except subprocess.TimeoutExpired as error:
        log = as_text(error.stderr)
        log = log[:log.rfind("\n") + 1]
        reached = progress_seconds(as_text(error.output))
        if reached <= 0:
            return "failed", "", 0.0, "stopped before reading any of the file: this command's time budget was used up"
        return "completed_partial", log, reached, "stopped early: this command's time budget was used up"
    except (OSError, subprocess.SubprocessError) as error:
        return "failed", "", 0.0, str(error)[:300]
    if result.returncode != 0:
        return "failed", "", 0.0, (result.stderr or "").strip()[-300:]
    return "completed", result.stderr or "", None, ""


def measure_signals(media: Path, duration_s: float, has_audio: bool,
                    deadline: float | None = None) -> tuple[dict, list, list]:
    """Cuts, silences and held frames, each group standing or falling on its own.

    One group failing leaves that group in `unavailable` and the others measured: a failed silence
    pass is "the sound was not measured", never "there was no silence". Two passes, not three: the
    sound alone (no picture decoded), then cuts and held frames together over one reduced decode of
    the picture (no sound decoded). The sound goes first because it costs a fraction of a second
    and would otherwise be the part a deadline starves.

    A pass the deadline stopped keeps what it read. Its group is measured up to that second and
    named in `measured_until_s`; a span still open there is closed there, and a limitation says the
    rest of the file was not read -- so a quiet stretch past it reads as unmeasured, not as speech.
    """
    if deadline is None:
        deadline = time.monotonic() + SIGNAL_TIMEOUT_S
    steps: list[dict] = []
    limitations: list[str] = []
    data: dict = {"duration_s": round(duration_s, 3), "measured": [], "unavailable": []}
    until: dict[str, float] = {}
    out_of_time: set[str] = set()
    base = ["-nostdin", "-hide_banner", "-nostats", "-progress", "pipe:1"]

    def detect(operation: str, args: list[str], covers: tuple[str, ...]) -> tuple[str | None, float]:
        started = now()
        status, log, reached, note = run_pass(args, deadline)
        step = {"step": "local_extraction", "operation": operation, "tool": "ffmpeg",
                "tool_version": tool_version("ffmpeg"), "invocation_sha256": invocation_digest(args, media),
                "started_at": started, "status": status}
        if note:
            step["note"] = note
        steps.append(step)
        if status == "failed":
            if "time budget" in note:
                out_of_time.update(covers)
            return None, 0.0
        if reached is None:
            return log, duration_s
        return log, min(duration_s, reached)

    def partial(groups: str, read_s: float) -> None:
        # Named on the pass's own ledger entry as well, at the second the detectors reached --
        # which can be later than the last progress line, never earlier.
        steps[-1]["note"] = (f"stopped after the first {read_s:.1f}s of the file: this command's "
                             "time budget was used up")
        limitations.append(
            f"{groups} were measured over the first {read_s:.1f}s of {duration_s:.1f}s only: the "
            "measurement stopped there to stay inside this command's time. Past that second they "
            "were not read -- treat the rest as unmeasured, not as found to have none.")

    groups: dict[str, dict] = {}
    if has_audio:
        log, read_s = detect("measure_silence", [
            *base, "-vn", "-sn", "-dn", "-i", str(media), "-map", "0:a:0",
            "-af", f"silencedetect=n={SILENCE_FLOOR_DB}dB:d={SILENCE_MIN_S}", "-f", "null", "-"],
            ("silence",))
        if log is not None:
            ends = [float(hit) for hit in re.findall(r"silence_(?:start|end):\s*(-?[\d.]+)", log)]
            read_s = max([read_s, *[min(duration_s, end) for end in ends]])
            groups["silence"] = {"floor_db": SILENCE_FLOOR_DB, "min_s": SILENCE_MIN_S,
                                 "spans": parse_spans(log, "silence_start",
                                                      r"silence_end:\s*([\d.]+)", read_s)}
            if read_s < duration_s:
                until["silence"] = round(read_s, 3)
                partial("Speech pauses", read_s)

    score = max(1, min(99, round(SHOT_THRESHOLD * 100)))
    chain = (f"fps={SIGNAL_FPS},{SIGNAL_SCALE_FILTER},scdet=threshold={score},"
             f"freezedetect=n=-60dB:d={FREEZE_MIN_S:g}")
    log, read_s = detect("measure_shots_and_freeze", [
        *base, "-an", "-sn", "-dn", "-i", str(media), "-map", "0:v:0", "-vf", chain, "-f", "null", "-"],
        ("shots", "freeze"))
    if log is not None:
        cuts = [round(float(hit), 3) for hit in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", log)]
        held = [float(hit) for hit in re.findall(r"freezedetect\.freeze_(?:start|end):\s*([\d.]+)", log)]
        read_s = max([read_s, *[min(duration_s, hit) for hit in cuts + held]])
        shots = shots_from_cuts(cuts, read_s)
        groups["shots"] = {"count": len(shots), "cuts_at_s": cuts, "shots": shots}
        groups["freeze"] = {"min_s": FREEZE_MIN_S,
                            "spans": parse_spans(log, r"freezedetect\.freeze_start",
                                                 r"freezedetect\.freeze_end:\s*([\d.]+)", read_s)}
        if read_s < duration_s:
            until["shots"] = until["freeze"] = round(read_s, 3)
            partial("Cuts and held frames", read_s)
        if len(shots) == 1 and read_s >= ONE_SHOT_SUSPECT_S:
            limitations.append(
                f"No cuts were detected across {read_s:.1f}s at sensitivity {SHOT_THRESHOLD}. "
                "Cutting inside one location -- same room, same subject, same light -- often scores "
                "below this, so a single shot here may mean the detector was too blunt rather than "
                "that the video is one take. Check the frames before describing it as uncut.")

    # The connector's order, whatever order the passes ran in.
    for group in ("shots", "silence", "freeze"):
        if group in groups:
            data[group] = groups[group]
            data["measured"].append(group)
        else:
            data["unavailable"].append(group)
    if until:
        data["measured_until_s"] = until
    if not has_audio:
        limitations.append("The file carries no audio track, so where speech pauses was not measured.")
    late = [group for group in data["unavailable"] if group in out_of_time]
    if late:
        limitations.append("These measurements were not taken because this command's time ran out "
                           f"before they could read any of the file: {', '.join(late)}. Treat each as "
                           "unread rather than as measured-and-found-nothing.")
    missing = [group for group in data["unavailable"]
               if group not in out_of_time and (has_audio or group != "silence")]
    if missing:
        limitations.append("These measurements could not be taken on this machine: "
                           f"{', '.join(missing)}. Treat each as unread rather than as "
                           "measured-and-found-nothing.")
    return data, steps, limitations


def detect_cuts(media: Path, duration_s: float, deadline: float) -> tuple[list[float], dict, dict]:
    """Where the picture cuts, for the shot-start frames: the cuts, the plan's shot_detection record, a ledger step.

    The connector's detector and sensitivity on a cheap decode (picture only, 240 lines high). It gets at most
    SHOT_TIME_SHARE of the time left, so the frames keep most of the command; stopped early, the cuts it found
    up to that second are used and the record says how far it read.
    """
    left = deadline - time.monotonic()
    score = max(1, min(99, round(SHOT_THRESHOLD * 100)))
    args = ["-nostdin", "-hide_banner", "-nostats", "-progress", "pipe:1", "-an", "-sn", "-dn", "-i", str(media),
            "-map", "0:v:0", "-vf", f"{SHOT_SCALE_FILTER},scdet=threshold={score}", "-f", "null", "-"]
    started = now()
    status, log, reached, note = run_pass(args, time.monotonic() + max(0.0, left * SHOT_TIME_SHARE))
    step = {"step": "local_extraction", "operation": "detect_shot_starts", "tool": "ffmpeg",
            "tool_version": tool_version("ffmpeg"), "invocation_sha256": invocation_digest(args, media),
            "started_at": started, "status": status}
    if note:
        step["note"] = note
    cuts = sorted({round(float(hit), 3) for hit in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", log)})
    record = {"status": "failed" if status == "failed" else "detected", "cuts": len(cuts), "threshold": SHOT_THRESHOLD,
              # The cut times themselves, at full frame rate: the audio measurement lines cuts up with onsets
              # (measure_audio_local.py), which the 0.1s grid of `media.signals` is too coarse for.
              "cuts_at_s": cuts}
    if status == "completed_partial" and reached is not None:
        record["status"] = "partial"
        record["read_until_s"] = round(min(duration_s, reached), 3)
    return cuts, record, step


# Contact sheets: frames in time order, nine to a sheet (three by three), each tile captioned with its second
# where this ffmpeg can draw text. One image read then shows nine frames; a single frame is opened only where a
# detail needs it.
SHEET_COLUMNS = 3
SHEET_ROWS = 3
SHEET_TILE_WIDTH_PX = 320
SHEET_TIMEOUT_S = 30


def contact_sheets(items: list[dict], out_dir: Path, width: int | None, height: int | None, quality: int,
                   deadline: float) -> tuple[list[dict], dict | None]:
    """Write the sheets for the written frames; the sheet list (path set by the caller) and a ledger step."""
    if not items:
        return [], None
    tile_w = SHEET_TILE_WIDTH_PX
    tile_h = max(2, int(round(tile_w * (height or 9) / (width or 16) / 2)) * 2)
    per_sheet = SHEET_COLUMNS * SHEET_ROWS
    sheets: list[dict] = []
    captioned = True
    status, note = "completed", ""
    started = now()
    sample_args: list[str] = []
    for number, first in enumerate(range(0, len(items), per_sheet), start=1):
        group = items[first:first + per_sheet]
        left = deadline - time.monotonic()
        if left <= 0.5:
            status, note = "completed_partial" if sheets else "failed", TIME_BUDGET_REASON
            break
        target = out_dir / f"sheet-{number:02d}.jpg"
        tiles = [{"frame_id": item["frame_id"], "t_seconds": item["t_seconds"], "row": position // SHEET_COLUMNS,
                  "col": position % SHEET_COLUMNS} for position, item in enumerate(group)]
        written = False
        for draw in ([True, False] if captioned else [False]):
            inputs: list[str] = []
            chains = []
            for position, item in enumerate(group):
                inputs += ["-i", str(out_dir / item["_file"])]
                chain = f"[{position}:v]scale={tile_w}:{tile_h}"
                if draw:
                    chain += (f",drawtext=text='{item['t_seconds']:.2f}s':x=6:y=6:fontsize=20:fontcolor=white"
                              ":box=1:boxcolor=black@0.6:boxborderw=4")
                chains.append(chain + f"[t{position}]")
            if len(group) == 1:
                graph = chains[0].replace("[t0]", f",pad={tile_w * SHEET_COLUMNS}:{tile_h}:0:0:black[out]")
            else:
                layout = "|".join(f"{(position % SHEET_COLUMNS) * tile_w}_{(position // SHEET_COLUMNS) * tile_h}"
                                  for position in range(len(group)))
                graph = (";".join(chains) + ";" + "".join(f"[t{position}]" for position in range(len(group)))
                         + f"xstack=inputs={len(group)}:layout={layout}:fill=black[out]")
            args = ["-nostdin", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph,
                    "-map", "[out]", "-frames:v", "1", "-update", "1", "-q:v", str(quality), str(target)]
            if not sample_args:
                sample_args = args
            try:
                result = run_tool("ffmpeg", args, max(0.5, min(SHEET_TIMEOUT_S, deadline - time.monotonic())))
            except (OSError, subprocess.SubprocessError) as error:
                note = str(error)[:300]
                break
            if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
                written = True
                break
            target.unlink(missing_ok=True)
            if draw:
                # No text drawing in this ffmpeg (no drawtext filter or no font): plain tiles, and the
                # tile-to-second list in the artifact carries the times.
                captioned = False
        if not written:
            status = "completed_partial" if sheets else "failed"
            note = note or "ffmpeg wrote no contact sheet"
            break
        sheets.append({"_file": target.name, "path": None, "captioned": draw, "columns": SHEET_COLUMNS,
                       "from_s": group[0]["t_seconds"], "to_s": group[-1]["t_seconds"], "tiles": tiles})
    step = {"step": "local_extraction", "operation": "contact_sheets", "tool": "ffmpeg",
            "tool_version": tool_version("ffmpeg"),
            "invocation_sha256": invocation_digest([Path(part).name if "/" in part else part
                                                    for part in sample_args], Path("-")),
            "started_at": started, "status": status,
            "note": note or f"{len(sheets)} sheet(s) of up to {per_sheet} frames"}
    return sheets, step


def earlier_artifact(path: Path, input_sha256: str) -> tuple[dict | None, str]:
    """The artifact a frame command wrote for this same file, for `--signals-only` to add to.

    None with no message when there is none yet: measuring first and sampling later is allowed.
    A file that is there but is not this script's artifact, or was written for a different video,
    is refused rather than overwritten -- its frames belong to something else.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ""
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path.name} exists but could not be read as an artifact ({error}); name a new --artifact path"
    if not isinstance(document, dict) or document.get("schema_version") != "local-media-extraction.v1":
        return None, f"{path.name} is not an artifact this script wrote; name a new --artifact path"
    if document.get("input_sha256") != input_sha256:
        return None, (f"{path.name} was written for a different file than --media; measure into the "
                      "artifact of the same file, or name a new --artifact path")
    return document, ""


def write_artifact(path: Path, artifact: dict) -> None:
    artifact["tools"] = {step["tool"]: step["tool_version"] for step in artifact["steps"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_signals(artifact: dict, signals: dict, steps: list, notes: list) -> None:
    """Put one measurement into the artifact, replacing any earlier one rather than stacking it.

    The notes a measurement adds are kept beside it, so measuring again removes exactly those and
    leaves every limitation the frames wrote.
    """
    media = artifact["media"]
    earlier = media.get("signals") if isinstance(media.get("signals"), dict) else {}
    stale = set(earlier.get("notes") or [])
    artifact["steps"] = [step for step in artifact["steps"]
                         if step.get("operation") not in SIGNAL_OPERATIONS] + steps
    artifact["limitations"] = [text for text in artifact["limitations"] if text not in stale] + notes
    media["signals"] = {**signals, "notes": notes}
    artifact["generated_at"] = now()


def main() -> int:
    started_at = time.monotonic()
    parser = argparse.ArgumentParser(description="Sample frames from a video on this machine.")
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--hook-window-s", type=float, default=3.0,
                        help="How far in the hook is judged: about 3s for a Short, 15-30 for long-form.")
    parser.add_argument("--base-interval-s", type=float, default=1.0)
    parser.add_argument("--hook-multiplier", type=int, default=2)
    parser.add_argument("--budget", type=int, default=600)
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES,
                        help="Cap on frames written; the body is thinned to fit, the hook never is.")
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES,
                        help="Stop writing frames once this many bytes are on disk.")
    parser.add_argument("--jpeg-quality", type=int, default=3)
    parser.add_argument("--measure-loudness", action="store_true")
    parser.add_argument("--measure-signals", action="store_true",
                        help="Measure cuts, speech pauses and held frames after the frames are written.")
    parser.add_argument("--signals-only", action="store_true",
                        help="Write no frames; measure, and add the result to the artifact an earlier "
                             "frame command wrote for this file.")
    parser.add_argument("--deadline-s", type=float, default=DEFAULT_DEADLINE_S,
                        help="Stop every step this many seconds after the command started and write "
                             "what it has.")
    parser.add_argument("--no-shot-starts", action="store_true",
                        help="Do not add a frame just after each detected cut (added by default, as on the server).")
    parser.add_argument("--dense-window", action="append", default=[], metavar="START:END:INTERVAL",
                        help="A denser stretch, in seconds (interval at least 0.2); up to three, repeatable.")
    parser.add_argument("--no-contact-sheets", action="store_true", help="Write the frames only.")
    parser.add_argument("--dry-run", action="store_true", help="Probe and plan, write no frames.")
    args = parser.parse_args()
    try:
        windows = [parse_dense_window(text) for text in args.dense_window]
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if len(windows) > MAX_DENSE_WINDOWS:
        print(f"ERROR: at most {MAX_DENSE_WINDOWS} --dense-window values", file=sys.stderr)
        return 2
    hint = method_frames(args.artifact)
    if not args.dense_window:
        # The method cards' windows (select_method.py), the same ones a link's keyframes request carries.
        windows = hint["dense_windows"]
    if hint["include_shot_starts"] is False:
        args.no_shot_starts = True
    deadline = started_at + args.deadline_s
    if not args.dry_run:
        # Reading the file is this run's observation; the evidence builder ends the stage.
        sys.dont_write_bytecode = True  # sibling imports must not leave __pycache__ in the Skill
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import acv_timing
        acv_timing.open_for_artifact(args.artifact)

    media = args.media.expanduser()
    if not media.is_absolute():
        print(f"ERROR: --media must be an absolute path; got {media}", file=sys.stderr)
        return 2
    state, why = readability(media)
    if state != "ok":
        print(f"ERROR: {why}", file=sys.stderr)
        # A denied path is a host limit, not a mistake the creator made and not a missing file, so
        # it gets its own exit status: the caller reports it as the gap it is and carries on with
        # whatever else the run has.
        return 4 if state == "denied" else 2
    if (args.hook_multiplier < 1 or args.base_interval_s <= 0 or args.budget < 2
            or args.max_frames < 2 or args.max_total_bytes < 1 or not args.deadline_s > 0):
        print("ERROR: --hook-multiplier must be at least 1, --base-interval-s positive, "
              "--budget and --max-frames at least 2, --max-total-bytes and --deadline-s positive",
              file=sys.stderr)
        return 2
    if args.out_dir is None and not args.signals_only:
        print("ERROR: --out-dir is required unless --signals-only is given", file=sys.stderr)
        return 2

    probe_step, payload = probe(media)
    steps = [probe_step]
    limitations: list[str] = []
    if probe_step["status"] != "completed":
        print("ERROR: the file's properties could not be read on this machine", file=sys.stderr)
        return 1

    facts = read_media_facts(payload)
    duration = facts.pop("_exact_duration_s")
    if duration is None or duration <= 0:
        print("ERROR: this file states no duration, so there is no length to sample against",
              file=sys.stderr)
        return 1

    input_sha256 = file_digest(media)
    artifact = None
    if args.signals_only:
        artifact, problem = earlier_artifact(args.artifact, input_sha256)
        if problem:
            print(f"ERROR: {problem}", file=sys.stderr)
            return 2

    if artifact is None:
        content_id = media.stem
        cuts, detection = None, None
        if not args.no_shot_starts and not args.signals_only and duration > HOOK_DENSE_S:
            if args.dry_run:
                cuts, detection = [], {"status": "not_requested", "cuts": 0, "threshold": SHOT_THRESHOLD}
            else:
                cuts, detection, shot_step = detect_cuts(media, duration, deadline)
                steps.append(shot_step)
                if detection["status"] == "failed":
                    limitations.append("Cuts could not be detected on this machine, so no frame was placed just "
                                       "after a cut; the frames follow the standard plan.")
                elif detection["status"] == "partial":
                    limitations.append(f"Cuts were detected over the first {detection['read_until_s']:g}s only, so "
                                       "shot-start frames stop there.")
        plan = plan_frames(duration, args.hook_window_s, args.base_interval_s,
                           args.hook_multiplier, min(args.budget, args.max_frames),
                           cuts=cuts, dense_windows=windows, shot_detection=detection)
        timestamps = plan.pop("_timestamps")
        kinds = plan.pop("_kinds")

        items: list[dict] = []
        skipped: list[dict] = []
        sheets: list[dict] = []
        if args.dry_run or args.signals_only:
            frames_status = "not_attempted"
        else:
            plan["_timestamps"], plan["_kinds"] = timestamps, kinds
            extract_step, items, skipped = extract(media, args.out_dir, plan, content_id, args.jpeg_quality,
                                                   args.max_total_bytes, deadline)
            plan.pop("_timestamps")
            plan.pop("_kinds")
            steps.append(extract_step)
            if not args.no_contact_sheets:
                sheets, sheet_step = contact_sheets(items, args.out_dir, facts.get("width"), facts.get("height"),
                                                    args.jpeg_quality, deadline)
                if sheet_step:
                    steps.append(sheet_step)
            frames_status = "available" if items else "unavailable"
            artifact_parent = args.artifact.expanduser().resolve().parent
            for item in items:
                # Relative to the artifact, never absolute: this file travels into the evidence object
                # and an operator's home directory has no business travelling with it.
                file_name = item.pop("_file")
                try:
                    item["path"] = str((args.out_dir.resolve() / file_name).relative_to(artifact_parent))
                except ValueError:
                    item["path"] = str(Path(args.out_dir.name) / file_name)
            for sheet in sheets:
                file_name = sheet.pop("_file")
                try:
                    sheet["path"] = str((args.out_dir.resolve() / file_name).relative_to(artifact_parent))
                except ValueError:
                    sheet["path"] = str(Path(args.out_dir.name) / file_name)
            out_of_room = [entry for entry in skipped
                           if entry["reason"] in (BYTE_BUDGET_REASON, TIME_BUDGET_REASON)]
            unreadable = len(skipped) - len(out_of_room)
            if unreadable:
                limitations.append(f"{unreadable} of {len(timestamps)} planned frames could not be "
                                   "read from the file, so those seconds were not seen.")
            if out_of_room and items:
                seen = [item["t_seconds"] for item in items]
                widest = max((later - earlier for earlier, later in zip(seen, seen[1:])), default=0.0)
                # Only claim what was actually written: a budget used up inside the opening leaves
                # part of the hook, and the closing frame, unseen.
                missing = {kinds[entry["ordinal"] - 1] for entry in skipped}
                whole = not missing & {"hook", "closing"}
                coverage = ("The opening and the closing frame are whole; the body is thinner"
                            if whole else
                            "Not all of the opening and closing frames were written, so do not describe "
                            "the whole hook or the ending as seen")
                causes = sorted({"this step's frame byte budget was used up"
                                 if entry["reason"] == BYTE_BUDGET_REASON
                                 else "this command's time budget was used up" for entry in out_of_room})
                limitations.append(f"{len(out_of_room)} of {len(timestamps)} planned frames were not "
                                   f"written because {' and '.join(causes)}. {coverage}, "
                                   f"with up to {widest:.3g}s between written frames, so a cut shorter "
                                   "than that may fall between them.")

        if args.measure_loudness and facts["has_audio"] and not args.dry_run and not args.signals_only:
            loudness, step, notes = measure_loudness(media, duration)
            if step:
                steps.append(step)
            limitations.extend(notes)
            if loudness:
                facts["encoding"].update(loudness)
        elif args.measure_loudness and not facts["has_audio"]:
            limitations.append("The file carries no audio track, so nothing about its sound was measured.")

        artifact = {
            "schema_version": "local-media-extraction.v1",
            "generated_at": now(),
            "media_path": media.name,
            "content_id": content_id,
            "input_sha256": input_sha256,
            "tools": {},
            "steps": steps,
            "media": facts,
            "frames": {
                "status": frames_status,
                "selection": "duration_scaled_v1",
                "sampling_plan": plan,
                "requested_timestamps": timestamps,
                "items": items,
                "skipped": skipped,
                "contact_sheets": sheets,
            },
            "limitations": limitations,
        }
        # On disk before any measurement starts: whatever happens to the measurement, the frames
        # are already delivered.
        write_artifact(args.artifact, artifact)

    measured = None
    if (args.measure_signals or args.signals_only) and not args.dry_run:
        signals, signal_steps, notes = measure_signals(media, duration, facts["has_audio"], deadline)
        add_signals(artifact, signals, signal_steps, notes)
        write_artifact(args.artifact, artifact)
        measured = bool(signals["measured"])

    frames = artifact["frames"]
    summary = {
        "artifact": str(args.artifact),
        "duration_s": artifact["media"]["duration_s"],
        "planned": len(frames["requested_timestamps"]),
        "written": len(frames["items"]),
        "skipped": len(frames["skipped"]),
        "frames_status": frames["status"],
        "frame_sources": {kind: sum(1 for item in frames["items"] if item.get("source") == kind)
                          for kind in BUDGET_PRIORITY},
        # Open these first: nine frames a read, in time order; open a single frame only for a detail.
        "contact_sheets": [{"path": sheet["path"], "from_s": sheet["from_s"], "to_s": sheet["to_s"],
                            "captioned": sheet["captioned"]} for sheet in frames.get("contact_sheets") or []],
    }
    if "signals" in artifact["media"]:
        signals = artifact["media"]["signals"]
        summary["signals"] = {
            "measured": signals["measured"],
            "unavailable": signals["unavailable"],
            "shots": signals.get("shots", {}).get("count"),
            "silences": len(signals.get("silence", {}).get("spans", [])) if "silence" in signals else None,
            "held_frames": len(signals.get("freeze", {}).get("spans", [])) if "freeze" in signals else None,
        }
        if signals.get("measured_until_s"):
            summary["signals"]["measured_until_s"] = signals["measured_until_s"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.signals_only:
        return 0 if measured else 1
    return 0 if (args.dry_run or frames["items"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
