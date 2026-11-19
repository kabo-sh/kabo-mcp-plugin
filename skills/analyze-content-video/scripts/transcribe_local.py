#!/usr/bin/env python3
"""Transcribe a video file on this machine with local speech recognition, when the creator has it installed.

The third tier of *Getting the words* in references/local-file.md: a local cut with no subtitle file still has a
spoken track, and this reads it here, on the creator's own machine, with the `faster-whisper` package and its
`small` model (int8 on the CPU, voice-activity filtering on, word timestamps). The audio is decoded by ffmpeg, the
same program the frame extractor runs, and handed over as samples; the package's own decoder is not used.

**It never installs anything and never downloads a model.** The package and its model are optional, and the
creator installs them; the Skill does not (docs/skills-spec.md KS7.2) and its scripts reach no network but Kabo's
(KS7.3), so the model is loaded from this machine's cache only. When either is missing, this exits 3 and prints
the one line that installs both, for the creator to run. probe_media_tools.py reports the same state up front.

**The output is the transcript artifact read_subtitle_file.py writes** (`local-transcript.v1`), with origin
`speech_recognition`: the words are what a machine heard, quotable as heard, never as the creator's exact
wording. Each cue keeps its end and its word timings beside the start the evidence builder reads.

**It stops itself before the host does.** Some hosts end a command after about a minute and keep nothing it
wrote, so recognition stops at `--deadline-s` (40 seconds after the command started, by default) and writes
what it has, naming the second it reached. Running the same command again continues from that second and adds
to the same artifact, until the whole file is read.

    python3 transcribe_local.py --media FILE --artifact analysis/local-transcript.json [--language en]
        [--deadline-s 40]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

MODEL = "small"
COMPUTE_TYPE = "int8"
SAMPLE_RATE = 16000
# One line the creator runs to install the package and fetch its model once; printed, never executed here.
INSTALL_LINE = ("python3 -m pip install faster-whisper && python3 -c \"from faster_whisper import WhisperModel; "
                f"WhisperModel('{MODEL}', device='cpu', compute_type='{COMPUTE_TYPE}')\"")
FFMPEG_HINT = "macOS: brew install ffmpeg  |  Debian/Ubuntu: apt install ffmpeg"
DECODE_TIMEOUT_S = 60
# Recognition runs window by window; stop asking for the next one this long before the deadline, so the artifact
# is written before the host's limit.
STOP_MARGIN_S = 6.0
SCHEMA_VERSION = "local-transcript.v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def missing(what: str, line: str) -> int:
    print(f"MISSING: {what} -- {line}", file=sys.stderr)
    print(json.dumps({"status": "missing", "missing": what, "install": line}, ensure_ascii=False))
    return 3


def readable(path: Path) -> int | None:
    """None when the file opens; otherwise the exit code read_subtitle_file.py uses for the same answer."""
    try:
        with path.open("rb") as handle:
            handle.read(1)
    except FileNotFoundError:
        print("ERROR: no file exists at this path", file=sys.stderr)
        return 2
    except IsADirectoryError:
        print("ERROR: this path is a directory, not a video file", file=sys.stderr)
        return 2
    except PermissionError:
        print("ERROR: the file is there, but this host does not allow reading that location. Ask the creator for "
              "a copy somewhere outside the personal folders (Documents, Desktop, Downloads, Movies).",
              file=sys.stderr)
        return 4
    except OSError as error:
        print(f"ERROR: this file could not be opened here: {error}", file=sys.stderr)
        return 2
    return None


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_audio(media: Path, offset_s: float) -> bytes | None:
    """Mono 16 kHz signed 16-bit samples from `offset_s` on, decoded by ffmpeg; None when the file has no audio."""
    args = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if offset_s > 0:
        args += ["-ss", f"{offset_s:.3f}"]
    # An argument list, never a shell string: a creator's file name is input.
    args += ["-i", str(media), "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    result = subprocess.run(args, capture_output=True, timeout=DECODE_TIMEOUT_S, check=False)  # noqa: S603
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        if any("does not contain any stream" in line or "Output file is empty" in line for line in detail):
            return None
        raise RuntimeError("ffmpeg could not decode the audio: " + (detail[-1][:200] if detail else "no message"))
    return result.stdout or None


def samples(raw: bytes):
    import numpy  # faster-whisper's own dependency: present wherever the package is
    return numpy.frombuffer(raw, dtype=numpy.int16).astype(numpy.float32) / 32768.0


def seconds(value, offset_s: float) -> float:
    return round(float(value) + offset_s, 3)


def cue_from_segment(segment, offset_s: float) -> dict | None:
    """One recognised segment as a cue: seconds from the file's start, text trimmed, word timings kept."""
    text = str(getattr(segment, "text", "") or "").strip()
    if not text:
        return None
    cue = {"start_s": seconds(segment.start, offset_s), "end_s": seconds(segment.end, offset_s), "text": text}
    words = [{"start_s": seconds(word.start, offset_s), "end_s": seconds(word.end, offset_s),
              "text": str(word.word).strip()}
             for word in getattr(segment, "words", None) or [] if str(getattr(word, "word", "")).strip()]
    if words:
        cue["words"] = words
    return cue


def earlier(path: Path, source_sha: str) -> dict | None:
    """The unfinished artifact an earlier run of this command wrote for the same file, to continue."""
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(artifact, dict) and artifact.get("schema_version") == SCHEMA_VERSION
            and artifact.get("origin") == "speech_recognition" and artifact.get("source_file_sha256") == source_sha
            and artifact.get("complete") is False):
        return artifact
    return None


def finish(artifact: dict, path: Path) -> None:
    cues = artifact.get("cues") or []
    name = artifact["source_file_name"]
    if cues:
        artifact.update(status="available", granularity="timestamped")
        reached = artifact.get("transcribed_until_s")
        artifact["status_basis"] = (
            f"local speech recognition heard {len(cues)} cues in {name!r}"
            + ("" if artifact["complete"] else f", up to {reached:g}s of the file; the rest was not read"))
    elif artifact.get("audio") is False:
        artifact.update(status="no_audio_track", granularity="none", cues=None,
                        status_basis=f"{name!r} carries no audio track, so there were no words to hear")
    elif artifact["complete"]:
        artifact.update(status="no_speech_detected", granularity="none", cues=None,
                        status_basis=f"local speech recognition heard no speech in {name!r} (music or silence only)")
    else:
        # Not finished and nothing heard yet: the next run of the same command continues.
        artifact.update(status="partial", granularity="none",
                        status_basis=f"local speech recognition stopped at its time limit before hearing any speech "
                                     f"in {name!r}")
    step = artifact["steps"][-1]
    step["status"] = "completed"
    if not artifact["complete"]:
        step["note"] = f"stopped at the time limit after {artifact.get('transcribed_until_s') or 0:g}s of the file"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--language", default=None, help="ISO 639-1 code, when the creator states it")
    parser.add_argument("--deadline-s", type=float, default=40.0)
    args = parser.parse_args(argv)
    deadline = started + max(1.0, args.deadline_s)
    # Listening to the file is part of this run's observation; the evidence builder ends the stage.
    sys.dont_write_bytecode = True  # sibling imports must not leave __pycache__ in the Skill
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import acv_timing
    acv_timing.open_for_artifact(args.artifact)

    media = args.media.expanduser()
    refused = readable(media)
    if refused is not None:
        return refused
    if importlib.util.find_spec("faster_whisper") is None:
        return missing("faster_whisper (local speech recognition)", INSTALL_LINE)
    if shutil.which("ffmpeg") is None:
        return missing("ffmpeg (decodes the file's audio)", FFMPEG_HINT)

    source_sha = file_digest(media)
    artifact = earlier(args.artifact, source_sha)
    offset = float(artifact.get("transcribed_until_s") or 0.0) if artifact else 0.0
    if artifact is None:
        artifact = {"schema_version": SCHEMA_VERSION, "generated_at": now(), "source_file_name": media.name,
                    "source_file_sha256": source_sha, "language": args.language, "origin": "speech_recognition",
                    "cues": [], "plain_text": None, "notes": [], "steps": [], "complete": False,
                    "transcribed_until_s": 0.0}
    invocation = hashlib.sha256(json.dumps(["transcribe_local", "<media>", MODEL, COMPUTE_TYPE, args.language,
                                            offset]).encode("utf-8")).hexdigest()
    artifact["steps"].append({"step": "local_extraction", "operation": "transcribe_local",
                              "tool": "faster_whisper", "tool_version": f"{MODEL}/{COMPUTE_TYPE}",
                              "invocation_sha256": invocation, "input_sha256": source_sha,
                              "started_at": now(), "status": "running"})
    try:
        raw = decode_audio(media, offset)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if raw is None:
        # Nothing to hear: no audio track at all, or none left after the second an earlier run reached.
        if offset == 0:
            artifact["audio"] = False
        artifact["complete"] = True
        finish(artifact, args.artifact)
        return report(artifact, args.artifact)
    total_s = offset + len(raw) / 2 / SAMPLE_RATE

    try:
        from faster_whisper import WhisperModel
        # The cache only: a model this machine does not have is not fetched here.
        model = WhisperModel(MODEL, device="cpu", compute_type=COMPUTE_TYPE, local_files_only=True)
    except ImportError:
        return missing("faster_whisper (local speech recognition)", INSTALL_LINE)
    except Exception as error:  # noqa: BLE001 - any load failure means the model is not usable here
        print(f"ERROR: the {MODEL} speech model could not be loaded ({type(error).__name__})", file=sys.stderr)
        return missing(f"the {MODEL} speech model", INSTALL_LINE)

    segments, info = model.transcribe(samples(raw), language=args.language, vad_filter=True,
                                      word_timestamps=True)
    if artifact.get("language") is None and getattr(info, "language", None):
        artifact["language"] = info.language
    reached, finished = offset, True
    iterator = iter(segments)
    while True:
        if time.monotonic() > deadline - STOP_MARGIN_S:
            finished = False
            break
        try:
            segment = next(iterator)
        except StopIteration:
            break
        cue = cue_from_segment(segment, offset)
        if cue:
            artifact["cues"].append(cue)
        reached = seconds(segment.end, offset)
    artifact["transcribed_until_s"] = round(total_s if finished else reached, 3)
    artifact["complete"] = finished
    finish(artifact, args.artifact)
    return report(artifact, args.artifact)


def report(artifact: dict, path: Path) -> int:
    print(json.dumps({"artifact": str(path), "status": artifact["status"], "complete": artifact["complete"],
                      "transcribed_until_s": artifact.get("transcribed_until_s"),
                      "cues": len(artifact.get("cues") or [])}, ensure_ascii=False, indent=2))
    if not artifact["complete"]:
        print("Stopped at the time limit: run the same command again to continue from "
              f"{artifact.get('transcribed_until_s') or 0:g}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
