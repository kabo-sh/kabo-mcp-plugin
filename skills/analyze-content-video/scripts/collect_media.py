#!/usr/bin/env python3
"""Get this video's media (transcript, frames, measurements) with one backend call and persist it.

Run it from the run directory.

- First run: prints one `collect_video_media` call for the media operations this mode needs, the
  file to save its result in when it has no download url, and the resume command. The backend
  queues every job itself and waits for them; nothing is polled job by job.
- `--placed --id=<id>`: fetches that result. While the backend still reports running jobs
  (`coverage.pending` above 0) it prints the same call again: nothing is queued or charged twice.
  Once every job is terminal (or after `MAX_ROUNDS` results) it persists each terminal envelope as
  `snapshot/envelope-NN.json`, prints the `--envelope` / `--pending` arguments for
  `build_content_evidence.py`, and the one `read_research_data_artifacts` call that brings the
  frames into the run.

Prints `status: failed` with the reason when a result cannot be used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import static_host  # noqa: E402

TOOL = "collect_video_media"
CONNECTOR = "public-video-media"
STATE = Path("collect-media.json")
# One call waits on the backend for at most 45 seconds (within the Codex tool timeout of 60 seconds); a media
# round often takes two to three minutes, so 6 results are enough to wait it out.
MAX_ROUNDS = 6
# Option name -> operation of collect_video_media. Metadata goes through the media tool only for Instagram /
# TikTok (YouTube uses youtube_get_video).
OPERATIONS = {
    "metadata": "collect_public_metadata",
    "transcript": "fetch_transcript",
    "keyframes": "extract_keyframes",
    "measure": "measure_media_signals",
}
# The same value as the frame-count cap in static_host.job-call.
MAX_FRAMES = static_host.FRAME_CAPS["public_video_extract_keyframes"]
# Same approach as the connector_driver.py handoff (kabo ADR-0084 "2026-11-04"): the model hands over only the
# result id, and the resume fetches by id itself; saving to a file is only the fallback when there is no
# download link.
SAVE_RULE = ("Do not save the result. Its download url holds its result id: the 22 characters between "
             "`research-export/v1/` and `.json`. Put the id of your last call's result into the resume command "
             "below as `--id=<id>`. Only if that result has no download url, save it whole, as returned, to the "
             "fallback file named under the call (with the host's file-write tool, never as a command-line "
             "argument) and leave `--id` out. Never download anything yourself; call get_research_data_download "
             "only when the resume says the id expired.")


def say(text: str) -> None:
    print(text, flush=True)


def state() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def save_state(value: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def quote(text: str) -> str:
    return "'" + str(text).replace("'", "'\\''") + "'"


def run_key() -> str:
    # The same run always gets the same key: a repeated call just continues the wait; another run's key differs, so
    # it never replays someone else's job.
    return "acv:" + hashlib.sha256(str(static_host.run_dir().resolve()).encode()).hexdigest()[:32]


def call_arguments(args: argparse.Namespace) -> dict[str, Any]:
    requests = []
    for name in args.operations:
        parameters: dict[str, Any] = {"url": args.url}
        if name == "keyframes":
            parameters.update({"sampling": "duration_scaled", "max_frames": args.max_frames})
        requests.append({"content_id": "video", "operation": OPERATIONS[name], "parameters": parameters})
    return {"requests": requests, "run_key": run_key(), "delivery": "download"}


def resume_command(args: argparse.Namespace) -> str:
    run_directory = quote(str(static_host.run_dir()))
    argv = [str(SCRIPTS / "collect_media.py"), "--url", args.url, "--operations", ",".join(args.operations),
            "--max-frames", str(args.max_frames), "--placed"]
    # No KABO_STATIC_RUN_DIR=... prefix: the run is found from the current directory (static_host.run_dir). This
    # line and the slot lines below use the same format as the connector_driver.py handoff, which is the only way the
    # Web host (kabo-agent-service plugin-handover.ts) can recognize it, make the call itself, and resume; if it
    # cannot recognize it, the whole handoff falls to the model, which often fumbles the staging step (pre M3b/M4c/M5a).
    return (f"cd {run_directory} && python3 "
            # `--id=<id>` rather than `--id <id>`: a result id may start with "-" (observed `-lNCEjm2WwISAEzMxbDqAA`), and
            # written as two words argparse takes it for another option and the resume errors out directly. The Web host
            # skips the `--id=` word all the same.
            + " ".join(quote(part) for part in argv) + " --id=<id>")


def bind_run_to_cwd() -> None:
    """The resume command is only `cd '<run>' && python3 ...` with no environment variable, yet static_host.run_dir reads the environment variable first. When
    the shell still holds another run's KABO_STATIC_RUN_DIR, the media evidence gets written into that run. If the current directory is inside a run, it takes precedence."""
    here = Path.cwd().resolve()
    run = next((path for path in (here, *here.parents) if (path / ".static-run.json").is_file()), None)
    if run is not None:
        os.environ["KABO_STATIC_RUN_DIR"] = str(run)


def hand_over_media(args: argparse.Namespace, note: str = "") -> None:
    current = state()
    results = Path.cwd() / "host-results"
    first = len(list(results.glob("*.json"))) + 1 if results.is_dir() else 1
    file = results / f"{first:02d}-{TOOL}.json"
    current.setdefault("awaiting", []).append(str(file))
    current["handed_at"] = datetime.now(timezone.utc).isoformat()
    save_state(current)
    wanted = ", ".join(args.operations)
    if note:
        # The instruction goes on its own line: the Web host (plugin-handover.ts) recognizes only lines starting with
        # "Hand-over: ", and if anything else precedes it, the host cannot recognize a re-sent round while jobs are still
        # running, and the whole handoff falls back to the model.
        say(note)
    say(f"Hand-over: make this one call now with the arguments verbatim; the backend queues this video's {wanted} "
        f"jobs and waits for them. If its result still reports running jobs (coverage.pending above 0), make the "
        f"same call again right away with the same arguments (nothing is queued or charged twice) until pending is "
        f"0 or you have made it {MAX_ROUNDS} times; only the last result counts. The media is not ready until this "
        f"script says so: the run is not over while jobs are running. " + SAVE_RULE)
    say("call: " + json.dumps({"tool": TOOL, "arguments": call_arguments(args)}, ensure_ascii=False))
    say(f"  result {file.name.split('-', 1)[0]}  (fallback file, only if the result has no download url: {file})")
    say("Then run this one command right away, <id> replaced by the last result's id (ids expire in 10 "
        "minutes): " + resume_command(args))


def staged_since(moment: str | None) -> bool:
    if not moment:
        return False
    return any(str(record.get("staged_at") or "") >= moment for record in static_host.composite_records(TOOL))


def take_saved(result_id: str | None) -> None:
    current = state()
    taken = current.setdefault("taken", {})
    awaiting = current.get("awaiting") or []
    if result_id:
        name = awaiting[-1] if awaiting else ""
        key = "id:" + static_host.result_id_of(result_id)
        if name and taken.get(name) != key:
            try:
                static_host.fetch_id(TOOL, result_id)
            except (ValueError, OSError, KeyError, TypeError) as error:
                raise ValueError(f"--id {result_id} gave no usable {TOOL} result ({error}). Run the same resume "
                                 "command again with the id from the last call's download url") from None
            taken[name] = key
            save_state(current)
        awaiting = awaiting[:-1]
    for name in awaiting:
        path = Path(name)
        if str(taken.get(name) or "").startswith("id:"):
            continue
        if not path.is_file():
            if staged_since(current.get("handed_at")):
                # The host has already put the result into this run in its own way (e.g. staged directly) without saving a
                # separate file: use the one already in place.
                continue
            raise ValueError(f"no result for this hand-over: run the same resume command again with --id=<id>, the "
                             f"id from the last {TOOL} call's download url (only for a result with no download url, "
                             f"save it whole at {path} and leave --id out). On a host that passes results as "
                             f"evidence references, first run static_host.py stage --tool {TOOL} on the last "
                             f"{TOOL} result, then this same resume command")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if taken.get(name) == digest:
            continue
        try:
            result = static_host.fetch(TOOL, raw)
            if result.get("fetched") == 0:
                result = static_host.stage(TOOL, raw)
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise ValueError(f"{path} does not hold a usable {TOOL} result ({error}). Save the complete result there "
                             "as returned, download link included, then run the same resume command again") from None
        taken[name] = digest
        save_state(current)


def next_slot() -> int:
    used = [int(path.stem.split("-")[-1]) for path in Path("snapshot").glob("envelope-*.json")
            if path.stem.split("-")[-1].isdigit()]
    return max(used, default=0) + 1


def persist(operation: str) -> str:
    dest = f"snapshot/envelope-{next_slot():02d}.json"
    done = subprocess.run([sys.executable, str(SCRIPTS / "persist_envelope.py"), "--dest", dest,
                           "--connector", CONNECTOR, "--operation", operation, "--any-status"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError((done.stdout + done.stderr).strip()[-800:] or f"persist {operation} failed")
    return dest


def finish(record: dict[str, Any]) -> None:
    current = state()
    placed = current.setdefault("placed", {})
    jobs = {job["group"]: job for job in (record.get("summary") or {}).get("jobs") or [] if isinstance(job, dict)}
    envelopes, pending = [], []
    for call in record.get("calls") or []:
        operation = str(call["group"]).rsplit("/", 1)[-1]
        if operation not in placed:
            # Persist by the route the envelope actually answered on (for frame extraction and measurement, the operation
            # carries a _hosted_* suffix when fetched via hosted retrieval).
            answered = json.loads(Path(call["path"]).read_text()).get("operation") or operation
            placed[operation] = persist(answered)
            save_state(current)
        envelopes.append(placed[operation])
    for group, job in jobs.items():
        operation = group.rsplit("/", 1)[-1]
        if operation not in placed and job.get("job_id") and job.get("status") in static_host.PENDING:
            pending.append(f"{operation}={job['job_id']}")
    say(json.dumps({"status": "collected", "envelopes": envelopes, "pending": pending}, ensure_ascii=False))
    flags = " ".join(f"--envelope {path}" for path in envelopes)
    flags += "".join(f" --deferred-incomplete {flag}" for flag in pending)
    say("Pass these to build_content_evidence.py, beside the run's other envelopes: " + flags)
    keyframes = next((call for call in record.get("calls") or [] if str(call["group"]).endswith("/extract_keyframes")),
                     None)
    if keyframes and Path(keyframes["path"]).is_file():
        envelope = json.loads(Path(keyframes["path"]).read_text())
        refs = [item.get("object_ref") for item in ((envelope.get("data") or {}).get("frames") or [])
                if isinstance(item, dict) and item.get("object_ref")]
        job_id = envelope.get("job_id") or (jobs.get(keyframes["group"]) or {}).get("job_id")
        if refs and job_id:
            # When the frame-read call itself hands the images to the model (as the Web host does), the frames have already
            # been viewed and the report does not need the frame bytes: the builder lists the frames from the keyframes
            # envelope. Requiring per-frame staging again would make 59 frames 59 steps, exceeding the host's per-turn step
            # limit, and the model would have to give up (11-07 production).
            say("Frames: make this one read now. If its result shows you the images, they are viewed: do not save "
                "or stage them, and go on to build_content_evidence.py. Only if it returns a download link instead, "
                "save and fetch it the way the Skill says for read_research_data_artifacts, then open each image's "
                "path before any visual claim:")
            say("read: " + json.dumps({"tool": "read_research_data_artifacts",
                                       "arguments": {"job_id": job_id, "object_refs": refs, "delivery": "download"}},
                                      ensure_ascii=False))
            return
    say("No frames arrived: keep the missing-visual-evidence limit and read the transcript and measurements only.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the original public video url")
    parser.add_argument("--operations", required=True,
                        help="comma-separated: " + ", ".join(OPERATIONS) + " (metadata only on Instagram and TikTok)")
    parser.add_argument("--max-frames", type=int, default=MAX_FRAMES)
    parser.add_argument("--placed", action="store_true")
    parser.add_argument("--id", dest="result_id", help="the result id of the last collect_video_media call")
    args = parser.parse_args(argv)
    bind_run_to_cwd()
    args.operations = [name.strip() for name in args.operations.split(",") if name.strip()]
    try:
        unknown = [name for name in args.operations if name not in OPERATIONS]
        if unknown or not args.operations:
            raise ValueError("--operations takes " + ", ".join(OPERATIONS) + "; got " + ",".join(unknown or ["nothing"]))
        if not 1 <= args.max_frames <= MAX_FRAMES:
            raise ValueError(f"--max-frames must be from 1 to {MAX_FRAMES}")
        if not args.placed:
            if state().get("awaiting"):
                say("This media round was already handed over; make the call printed earlier, or run with --placed.")
            hand_over_media(args)
            return 0
        take_saved(args.result_id)
        records = static_host.composite_records(TOOL)
        if not records:
            raise ValueError(f"no {TOOL} result was saved in this run; make the printed call and save it first")
        latest = records[-1]
        pending = int((latest.get("coverage") or {}).get("pending") or 0)
        current = state()
        current["rounds"] = int(current.get("rounds") or 0) + 1
        save_state(current)
        if pending and current["rounds"] < MAX_ROUNDS:
            hand_over_media(args, note=f"{pending} media job(s) are still running.")
            return 0
        finish(latest)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as error:
        say(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
