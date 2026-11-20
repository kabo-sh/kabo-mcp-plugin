#!/usr/bin/env python3
"""Timing of one video analysis run: when its frames are sampled (the overview plan), and how long its stages took.

## Frame timing: a low-resolution overview of every second, and a bounded set of high-resolution frames

The same rule runs on the server (public-video-media `extract_keyframes` with `overview: true`, kabo
packages/creator/src/adapters/connectors/public-video-media.ts) and on this machine (extract_local_frames.py);
the shared golden vectors (scripts/fixtures/acv-overview-parity.json, a copy beside the connector's test) prove
that both pick the same seconds for the same inputs.

Videos up to 50 s (`OVERVIEW_ABOVE_S`, where the default dense window ends) keep today's plan unchanged: the first
50 s every 0.5 s already covers them. Longer videos get two things:

1. **Overview**: one frame every second of the whole video (`stride_s` 1), scaled down and tiled into sheets in
   time order, left to right and top to bottom, sheet k covering seconds [k*T, (k+1)*T) with T = columns*rows*stride.
   The layout is the first of these whose sheets fit in `OVERVIEW_MAX_SHEETS` (16):

       layout   tiles (cols x rows)   tile long edge   seconds in 16 sheets   ~tokens per second
       A        30  (6 x 5)           256 px           480 s  (8 min)         49
       B        56  (8 x 7)           192 px           896 s  (~15 min)       26
       C        120 (12 x 10)         128 px           1920 s (32 min)        12

   Past 32 minutes layout C keeps 16 sheets and the stride grows to ceil(seconds / 1920) whole seconds, which the
   plan states. Tiles keep the video's aspect (long edge as above) with 2 px between them, so a sheet of 16:9 or
   9:16 tiles is at most 1558 x 736 px (or 874 x 1288): about 1.1 MP.

2. **High-resolution frames** (720 px long edge, the frames read one at a time or as 2x2 contact sheets), at most
   `max_frames` (120), in this priority: the opening 3 s and the closing 2 s every 0.5 s; one frame 0.05 s after
   each cut (at most half of what those leave); the dense windows (the default first 50 s every 0.5 s and the
   method cards' windows, with the connector's half-budget cap where the "body need" is the change candidates
   outside the windows plus one anchor per whole 10 s outside them); then **change frames**; then **anchors**. The uniform body grid is gone: the
   overview already shows every second.

   Change frames come from a 64 x 64 luma grid of each overview second (one ffmpeg pass writes the grid and the
   sheets). For second s against s-1, in integer units where 100 is the threshold:
   - picture = floor(sum |luma difference| * 100 / (10 * 4096)): a mean change of 10 grey levels is 100;
   - text = floor(max over the top and bottom 21 rows of |edges(s) XOR edges(s-1)| * 100 / 48), where an edge is a
     horizontal step of at least 24 grey levels between neighbours (63 x 21 cells a band): captions and titles
     appearing, changing or leaving while the picture stays. No OCR.
   A second is a candidate when max(picture, text) >= 100; its reason is `picture_change` when picture >= 100,
   otherwise `text_change`. Candidates lie in the body (3 s up to the closing window) outside the laid windows, and
   one within 1 s of a higher-priority frame is a duplicate. They are taken by score (ties: earlier first), first
   kept at least max(1 s, uncovered body / (2 x slots)) apart so a busy minute cannot take every slot, then at
   least 1 s apart, until the slots run out.
   Anchors then fill what is left: while a gap between consecutive high-resolution frames is longer than 10 s
   (`ANCHOR_GAP_S`), the widest (ties: earliest) gets a frame at its middle second. A static video therefore uses
   fewer frames rather than spending them on a grid.

**Budget** (the host model's image cost; assumed about width x height / 750 tokens, an image at most ~1.15 MP; a
2x2 high-resolution sheet about 1.5k tokens, so a high-resolution frame about 375):

    video     overview                 high-resolution (<= 120)    total (upper bound)   today
    30 s      none                     ~70 frames  ~26k            ~26k                  ~26k
    2 min     A, 4 sheets   ~6k        <= 120      <= 45k          <= 51k                ~45k
    10 min    B, 11 sheets  ~16k       <= 120      <= 45k          <= 61k                ~45k (body every 8.7 s)
    30 min    C, 15 sheets  ~22k       <= 120      <= 45k          <= 67k                ~45k (body every 26 s)

The overview pass decodes the whole video once at one frame a second (like the cut detection); high-resolution
frames are single seeks as before.

## Stage timing

Stage timing of one video analysis run, in <run>/analysis/timing.json.

    {"schema_version": "acv-timing/v1", "observation_source": "server_frames|whole_video|local_frames|combined",
     "stages": [{"stage": "observe|prepare|judge|validate", "started_at": ISO, "ended_at": ISO, "duration_ms": 123}],
     "reply": {"file": "analysis/answer.md", "chars": 2599, "ended_at": ISO, "total_ms": 121000}}

`reply` is the delivered answer: the validated report of a diagnosis, recorded by finish_diagnosis.py, or the
answer of a content read or craft teardown, recorded by `acv_timing.py answer` (which also closes the judge stage).
`total_ms` runs from the first recorded stage start to the reply.

Each script that starts or ends a stage appends its own entry; a stage that starts in one script and ends in
another keeps its start in the sidecar `.timing-open.json` until it ends. Timing never decides anything and a
failure to write it never fails the run: it is a measurement of the run, not part of the analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "acv-timing/v1"
STAGES = ("observe", "prepare", "judge", "validate")
SOURCES = ("server_frames", "whole_video", "local_frames", "combined")
FILE = "timing.json"
OPEN = ".timing-open.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False,
                                     encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(stream.name, path)


def load(analysis: Path) -> dict[str, Any]:
    document = _read(Path(analysis) / FILE, None)
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        document = {"schema_version": SCHEMA_VERSION, "observation_source": None, "stages": []}
    return document


def _ms(start: str, end: str) -> int:
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: E731
    return max(0, round((parse(end) - parse(start)).total_seconds() * 1000))


def set_source(analysis: Path, source: str) -> None:
    if source not in SOURCES:
        return
    try:
        document = load(analysis)
        document["observation_source"] = source
        _write(Path(analysis) / FILE, document)
    except OSError:
        pass


def append(analysis: Path, stage: str, started_at: str, ended_at: str | None = None, *,
           replace: bool = False) -> None:
    """Add one stage entry; with `replace`, it takes the place of that stage's earlier entries (a retried step)."""
    if stage not in STAGES:
        raise ValueError(f"unknown timing stage {stage!r}")
    ended_at = ended_at or now()
    try:
        document = load(analysis)
        if replace:
            document["stages"] = [entry for entry in document["stages"] if entry.get("stage") != stage]
        document["stages"].append({"stage": stage, "started_at": started_at, "ended_at": ended_at,
                                   "duration_ms": _ms(started_at, ended_at)})
        _write(Path(analysis) / FILE, document)
    except (OSError, ValueError):
        pass


def replace(analysis: Path, stage: str, started_at: str, ended_at: str | None = None) -> None:
    """Record a stage that may run again (a retried finish): one entry per stage, the latest run's."""
    append(analysis, stage, started_at, ended_at, replace=True)


def open_stage(analysis: Path, stage: str) -> None:
    """Record a stage's start once; a later start of the same open stage keeps the first."""
    marker = Path(analysis) / OPEN
    opened = _read(marker, {})
    opened = opened if isinstance(opened, dict) else {}
    if stage in opened:
        return
    opened[stage] = now()
    try:
        _write(marker, opened)
    except OSError:
        pass


def open_for_artifact(artifact: Path, stage: str = "observe") -> None:
    """Open `stage` for a local step whose artifact goes to <run>/analysis/ (frame extraction, measurement, local
    speech recognition): the evidence builder closes it, so reading a file on this machine is timed as the
    observation it is. Anywhere else (no reserved run around it) nothing is recorded."""
    try:
        analysis = Path(artifact).resolve().parent
        if analysis.name == "analysis" and (analysis.parent / ".static-run.json").is_file():
            open_stage(analysis, stage)
    except OSError:
        pass


def close_stage(analysis: Path, stage: str) -> None:
    marker = Path(analysis) / OPEN
    opened = _read(marker, {})
    if not isinstance(opened, dict) or stage not in opened:
        return
    started = opened.pop(stage)
    append(analysis, stage, started)
    try:
        _write(marker, opened)
    except OSError:
        pass


def last_end(analysis: Path, stage: str) -> str | None:
    entries = [entry for entry in load(analysis)["stages"] if entry.get("stage") == stage]
    return entries[-1]["ended_at"] if entries else None


def record_reply(analysis: Path, file: str, chars: int, ended_at: str | None = None) -> dict[str, Any] | None:
    """Record the delivered answer's length and the run's total time up to it; a later call replaces it."""
    ended_at = ended_at or now()
    try:
        document = load(analysis)
        starts = [entry.get("started_at") for entry in document["stages"] if entry.get("started_at")]
        reply = {"file": file, "chars": chars, "ended_at": ended_at,
                 "total_ms": _ms(min(starts), ended_at) if starts else None}
        document["reply"] = reply
        _write(Path(analysis) / FILE, document)
        return reply
    except (OSError, ValueError):
        return None


# ---- Frame timing: the overview plan (see the module docstring). Mirrors the connector's arithmetic exactly. ----

OVERVIEW_ABOVE_S = 50.0
OVERVIEW_MAX_SHEETS = 16
# (columns, rows, tile long edge in px), the first that fits wins.
OVERVIEW_LAYOUTS = ((6, 5, 256), (8, 7, 192), (12, 10, 128))
OVERVIEW_PADDING_PX = 2
LUMA_GRID_PX = 64
PICTURE_MEAN_LEVELS = 10
EDGE_LEVELS = 24
TEXT_BAND_ROWS = 21
TEXT_CELLS = 48
CHANGE_UNITS = 100
CHANGE_DEDUPE_MS = 1000
ANCHOR_GAP_MS = 10_000
OVERVIEW_PRIORITY = ("hook", "closing", "shot_start", "dense_window", "change", "anchor")


def overview_seconds(duration_s: float) -> int:
    """How many one-second frames ffmpeg's fps=1 filter gives for this duration: round half up, at least one."""
    return max(1, (int(round(duration_s * 1000)) + 500) // 1000)


def overview_layout(duration_s: float) -> dict[str, int]:
    """The overview's layout and stride for a duration: the first layout whose sheets fit, else the last one with a
    wider stride."""
    seconds = overview_seconds(duration_s)
    for columns, rows, edge in OVERVIEW_LAYOUTS:
        per_sheet = columns * rows
        if -(-seconds // per_sheet) <= OVERVIEW_MAX_SHEETS:
            stride = 1
            break
    else:
        stride = -(-seconds // (per_sheet * OVERVIEW_MAX_SHEETS))
    tiles = -(-seconds // stride)
    return {"columns": columns, "rows": rows, "tile_long_edge_px": edge, "stride_s": stride, "tiles": tiles,
            "sheets": -(-tiles // per_sheet), "padding_px": OVERVIEW_PADDING_PX}


def overview_filter(layout: dict[str, int]) -> str:
    """The one ffmpeg filter graph that writes the luma grid ([g]) and the sheets ([s]) from one decode."""
    edge = layout["tile_long_edge_px"]
    rate = "1" if layout["stride_s"] == 1 else f"1/{layout['stride_s']}"
    return (f"[0:v]fps={rate},split=2[a][b];"
            f"[a]scale={LUMA_GRID_PX}:{LUMA_GRID_PX}:flags=area,format=gray[g];"
            f"[b]scale='if(gte(iw,ih),{edge},-2)':'if(gte(iw,ih),-2,{edge})',"
            f"tile={layout['columns']}x{layout['rows']}:padding={layout['padding_px']}[s]")


def _edges(grid: bytes) -> tuple[int, int]:
    """The top and bottom bands' edge cells as two bit sets: a horizontal step of at least EDGE_LEVELS."""
    size = LUMA_GRID_PX
    bands = []
    for rows in (range(0, TEXT_BAND_ROWS), range(size - TEXT_BAND_ROWS, size)):
        bits = 0
        for y in rows:
            row = grid[y * size:(y + 1) * size]
            for x in range(size - 1):
                bits = (bits << 1) | (abs(row[x + 1] - row[x]) >= EDGE_LEVELS)
        bands.append(bits)
    return bands[0], bands[1]


def change_units(grids: bytes, count: int | None = None) -> list[tuple[int, int]]:
    """(picture, text) change units of each second against the one before, from consecutive 64x64 luma grids;
    second 0 is (0, 0). 100 on either is the threshold."""
    cell = LUMA_GRID_PX * LUMA_GRID_PX
    total = len(grids) // cell if count is None else min(count, len(grids) // cell)
    units: list[tuple[int, int]] = []
    previous = None
    for index in range(total):
        grid = grids[index * cell:(index + 1) * cell]
        edges = _edges(grid)
        if previous is None:
            units.append((0, 0))
        else:
            difference = sum(map(abs, map(int.__sub__, grid, previous[0])))
            picture = difference * CHANGE_UNITS // (PICTURE_MEAN_LEVELS * cell)
            changed = max((edges[0] ^ previous[1][0]).bit_count(), (edges[1] ^ previous[1][1]).bit_count())
            units.append((picture, changed * CHANGE_UNITS // TEXT_CELLS))
        previous = (grid, edges)
    return units


def _inside(at_ms: int, stretches: list[tuple[int, int]]) -> bool:
    return any(since <= at_ms < until for since, until in stretches)


def change_candidates(units: list[tuple[int, int]], stride_s: int,
                      stretches: list[tuple[int, int]]) -> list[tuple[int, int, str, int]]:
    """Seconds at or over the threshold inside `stretches` (whole ms): (t_ms, score, reason, picture units)."""
    found = []
    for index, (picture, text) in enumerate(units):
        at = index * stride_s * 1000
        score = max(picture, text)
        if index == 0 or score < CHANGE_UNITS or not _inside(at, stretches):
            continue
        found.append((at, score, "picture_change" if picture >= CHANGE_UNITS else "text_change", picture))
    return found


def pick_changes(candidates: list[tuple[int, int, str, int]], taken_ms: list[int],
                 stretches: list[tuple[int, int]], slots: int) -> tuple[list[tuple[int, str, int]], int]:
    """The change frames (t_ms, reason, score) and how many candidates were duplicates of a higher-priority frame."""
    fresh = [entry for entry in candidates
             if not any(abs(entry[0] - other) < CHANGE_DEDUPE_MS for other in taken_ms)]
    duplicates = len(candidates) - len(fresh)
    if slots <= 0 or not fresh:
        return [], duplicates
    ranked = sorted(fresh, key=lambda entry: (-entry[1], entry[0]))
    uncovered = sum(until - since for since, until in stretches)
    chosen: list[tuple[int, str, int]] = []
    for radius in (max(CHANGE_DEDUPE_MS, uncovered // (2 * slots)), CHANGE_DEDUPE_MS):
        for at, score, reason, _ in ranked:
            if len(chosen) >= slots:
                break
            if any(abs(at - other[0]) < radius for other in chosen):
                continue
            chosen.append((at, reason, score))
    return sorted(chosen), duplicates


def pick_anchors(times_ms: list[int], from_ms: int, until_ms: int, slots: int) -> list[int]:
    """Whole-second frames in the middle of the widest gaps longer than ANCHOR_GAP_MS, while slots last."""
    points = sorted(set(times_ms))
    anchors: list[int] = []
    while len(anchors) < slots:
        best = None
        for earlier, later in zip(points, points[1:]):
            middle = (earlier + later) // 2 // 1000 * 1000
            if later - earlier > ANCHOR_GAP_MS and from_ms <= middle < until_ms and (
                    best is None or later - earlier > best[0]):
                best = (later - earlier, middle)
        if best is None:
            break
        anchors.append(best[1])
        points = sorted(points + [best[1]])
    return sorted(anchors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the end of a content read or craft teardown answer.")
    sub = parser.add_subparsers(dest="command", required=True)
    answer = sub.add_parser("answer", help="close the judge stage and record the answer's length")
    answer.add_argument("--run", type=Path, required=True)
    answer.add_argument("--answer", required=True, help="the answer file, relative to the run directory")
    args = parser.parse_args(argv)
    run = args.run.resolve()
    path = (run / args.answer).resolve()
    if not path.is_relative_to(run):
        print(json.dumps({"status": "failed", "error": "--answer names a file inside the run directory"}))
        return 1
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"cannot read the answer: {error}"}))
        return 1
    if not text.strip():
        print(json.dumps({"status": "failed", "error": "the answer file is empty; write the answer first"}))
        return 1
    analysis = run / "analysis"
    ended = now()
    # The judge stage runs from the end of prepare to the finished answer; a repeat keeps only the latest.
    prepared = last_end(analysis, "prepare")
    if prepared:
        replace(analysis, "judge", prepared, ended)
    reply = record_reply(analysis, args.answer, len(text.strip()), ended)
    print(json.dumps({"status": "recorded", "chars": len(text.strip()),
                      "total_ms": (reply or {}).get("total_ms")}))
    print("Reply with the answer as written.")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
