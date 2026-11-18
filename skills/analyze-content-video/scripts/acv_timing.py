#!/usr/bin/env python3
"""Stage timing of one video analysis run, in <run>/analysis/timing.json.

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
