#!/usr/bin/env python3
"""Report which local media tools this machine has, before anything tries to use one.

A local video is read here, on the creator's own machine, by programs this package does not ship
and cannot install. Whether those programs exist is a fact about the machine, and it has to be
established before a run commits to a path that depends on them -- not discovered halfway through
by a subprocess that fails with a message nobody wrote for a creator to read.

Three things this deliberately does not do.

**It never installs anything.** Each requirement carries one line saying what would install it, and
that line is printed, never executed. A Skill that silently changes what is installed on a
creator's machine has done something they did not ask for and cannot easily undo, and this package
declares no permission to do it. Handing over the one command is the whole of the help offered.

**A missing tool is a finding, not a crash.** Without `--require`, this exits 0 whatever it found,
because "ffmpeg is not here" is exactly the kind of thing the caller wants reported into the
evidence rather than raised as a script failure. `--require` is for the one caller that genuinely
cannot continue: it exits 3 so the difference between "a requirement is absent" and "this script
itself broke" survives in the exit status.

**A path no script here walks is never reported as available.** Local speech recognition is
declared, because the transcript tiers name it and a creator asking why their draft has no
transcript deserves to see which rung is missing. It reports `not_implemented_here` even on a
machine where the library imports cleanly, because this version of the Skill has nothing that would
call it. Reporting it as available would be a promise the package cannot keep, and the creator
would go install a dependency that changes nothing.

    python3 probe_media_tools.py [--require ffmpeg,ffprobe] [--out FILE]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# Every executable this package is ever allowed to start, named here so a test can read the set
# rather than trust a promise made in prose. `run_tool` refuses anything outside it. The list is
# short on purpose: these two read and decode media, and nothing else here needs a subprocess.
ALLOWED_TOOLS = frozenset({"ffmpeg", "ffprobe"})

# A version query has to finish quickly or the tool is not usable for a media job anyway.
VERSION_TIMEOUT_S = 10


REQUIREMENTS = (
    {
        "key": "ffprobe",
        "kind": "command",
        "name": "ffprobe",
        "enables": "reading a file's duration, dimensions, frame rate and audio layout",
        "implemented": True,
        "install_hint": "macOS: brew install ffmpeg  |  Debian/Ubuntu: apt install ffmpeg",
    },
    {
        "key": "ffmpeg",
        "kind": "command",
        "name": "ffmpeg",
        "enables": "sampling frames out of the file so the analysis can look at them",
        "implemented": True,
        "install_hint": "macOS: brew install ffmpeg  |  Debian/Ubuntu: apt install ffmpeg",
    },
    {
        "key": "faster_whisper",
        "kind": "python_module",
        "name": "faster_whisper",
        "enables": "transcribing a local file that has neither platform captions nor a subtitle file",
        "implemented": False,
        "install_hint": "pip install faster-whisper",
    },
)

# What each unmet requirement costs, phrased for the creator rather than for an operator. These
# strings are handed to the evidence builder verbatim as limitations, so they say what went
# unmeasured -- never which program was missing from which path.
GAP_TEXT = {
    "ffprobe": "The file's own properties -- how long it runs, its dimensions, whether it carries "
               "audio -- could not be read on this machine, so nothing in the analysis rests on them.",
    "ffmpeg": "No frame could be sampled from the file on this machine, so this reading rests on "
              "speech and stated context alone and every visual judgement is unassessed.",
    "faster_whisper": "Local speech recognition is not part of this version of the Skill. Where the "
                      "platform published no captions and no subtitle file was supplied, the spoken "
                      "track was not read.",
}


def run_tool(name: str, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Start one of the two allowed programs, with the argument list passed as a list.

    A list rather than a string, and no shell anywhere: a creator's filename is an input to this
    package and a filename containing a space, a quote or a leading dash is ordinary. Through a
    shell those become syntax. The allow-list is the second half of the same guard -- it makes
    "which programs can this package start" a question with a written answer.
    """
    if name not in ALLOWED_TOOLS:
        raise ValueError(f"{name!r} is not an allowed tool; this package starts only {sorted(ALLOWED_TOOLS)}")
    return subprocess.run(  # noqa: S603 - argv is a list, shell is never used, timeout is always set
        [name, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_command(requirement: dict) -> dict:
    """Locate an executable and read back the version line it prints for itself."""
    name = requirement["name"]
    found = shutil.which(name)
    if not found:
        return {"state": "absent"}
    try:
        result = run_tool(name, ["-version"], VERSION_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as error:
        # On the PATH but not runnable: a broken install, a wrapper that needs something absent, an
        # architecture mismatch. Reported as its own state rather than as "absent", because the
        # install hint is the wrong advice for it -- the tool is already there.
        return {"state": "unusable", "detail": str(error)}
    if result.returncode != 0:
        return {"state": "unusable", "detail": f"exited {result.returncode} on its own version query"}
    first_line = (result.stdout or result.stderr or "").strip().splitlines()
    return {
        "state": "available",
        "path": found,
        "version_line": first_line[0] if first_line else None,
    }


def probe_python_module(requirement: dict) -> dict:
    """Ask whether a module could be imported, without importing it.

    `find_spec` rather than an import: importing a speech-recognition stack loads its inference
    runtime, costs seconds and writes to stderr, and this runs on every local video whether or not
    anything will transcribe. Asking is cheap; loading is not.
    """
    try:
        spec = importlib.util.find_spec(requirement["name"])
    except (ImportError, ValueError):
        spec = None
    return {"state": "available" if spec is not None else "absent"}


def probe(requirement: dict) -> dict:
    """Resolve one requirement into a reportable row."""
    row = {"key": requirement["key"], "enables": requirement["enables"]}
    if requirement["kind"] == "command":
        row.update(probe_command(requirement))
    else:
        row.update(probe_python_module(requirement))

    if not requirement["implemented"]:
        # The honesty rule. Whatever the machine has, no script in this package walks this path, so
        # the only true answer is that it is not implemented here. Overwriting a found module with
        # this state is the point, not a bug: a creator told "available" would reasonably expect a
        # transcript, and would get none.
        row["state"] = "not_implemented_here"

    if row["state"] != "available":
        row["install_hint"] = requirement["install_hint"]
    return row


def survey() -> dict:
    rows = [probe(requirement) for requirement in REQUIREMENTS]
    by_key = {row["key"]: row for row in rows}
    gaps = [
        {
            "key": row["key"],
            "limitation": GAP_TEXT[row["key"]],
            "install_hint": row.get("install_hint"),
        }
        for row in rows
        if row["state"] != "available"
    ]
    return {
        "schema_version": "media-tool-survey.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tools": rows,
        "gaps": gaps,
        "can_probe_media": by_key["ffprobe"]["state"] == "available",
        "can_extract_frames": (
            by_key["ffprobe"]["state"] == "available" and by_key["ffmpeg"]["state"] == "available"
        ),
        "can_transcribe_locally": by_key["faster_whisper"]["state"] == "available",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report which local media tools are present.")
    parser.add_argument(
        "--require",
        default="",
        help="Comma-separated requirement keys that must be available; exit 3 if any is not.",
    )
    parser.add_argument("--out", type=Path, help="Also write the report to this file.")
    args = parser.parse_args()

    report = survey()
    known = {requirement["key"] for requirement in REQUIREMENTS}
    required = {part.strip() for part in args.require.split(",") if part.strip()}
    unknown = required - known
    if unknown:
        print(f"ERROR: unknown requirement {sorted(unknown)}; known keys are {sorted(known)}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)

    states = {row["key"]: row["state"] for row in report["tools"]}
    missing = sorted(key for key in required if states[key] != "available")
    if missing:
        for key in missing:
            hint = next(row.get("install_hint") for row in report["tools"] if row["key"] == key)
            print(f"MISSING: {key} ({states[key]}) -- {hint}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
