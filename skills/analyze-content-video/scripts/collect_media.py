#!/usr/bin/env python3
"""Get this video's media (transcript, frames, measurements) with one backend call and persist it.

Run it from the run directory.

- First run: prints one `collect_video_media` call for the media operations this mode needs, the
  file to save its result in when it has no download url, and the resume command. The backend
  queues every job itself and waits for them; nothing is polled job by job.
- `--placed --id=<id>`: fetches that result. While the backend still reports running jobs
  (`coverage.pending` above 0) it prints the same call again: nothing is queued or charged twice.
  Once every job is terminal (or at the observation deadline, `WAIT_BUDGET_S` after the first hand-over, or
  `MAX_ROUNDS` results at most) it persists each terminal envelope as `snapshot/envelope-NN.json`, prints the `--envelope` /
  `--deferred-incomplete` arguments for
  `build_content_evidence.py`, and the one `read_research_data_artifacts` call that brings the
  frames into the run. A call waits inside the tool, so a new hand-over starts only while the deadline still covers
  its wait (`media_plan`): fewer repeats, then a shorter `wait_s`, then none, and the jobs still running are
  recorded as not arrived in time, the same as at the deadline itself.

`--url` is the original public link, or `kabo-file:<uuid>` for a video the creator attached in Kabo (the media
tool reads the stored file the same way it reads a link). A file on the creator's own machine never comes here:
it is read locally and never uploaded.

Prints `status: failed` with the reason when a result cannot be used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import observation_order  # noqa: E402
import static_host  # noqa: E402
import public_video_sources  # noqa: E402
import select_method  # noqa: E402
import viewer_response  # noqa: E402

TOOL = "collect_video_media"
# Videos up to this long keep the plan unchanged; the overview applies above it (acv_timing.OVERVIEW_ABOVE_S).
OVERVIEW_ABOVE_S = 50.0
CONNECTOR = "public-video-media"
STATE = Path("collect-media.json")
# Media waits are measured in wall time, not rounds. One call waits on the backend for at most 45 seconds
# (observation_order.CALL_WAIT_S, within the Codex tool timeout of 60 seconds). The wait from the first hand-over is
# the observation deadline (observation_order.OBSERVE_DEADLINE_S, 330 seconds), the same on every host: Kabo Web ends
# a turn at 500 seconds, and a 15-minute wait once held a throttled Bilibili download for 477 seconds until the turn
# died with no reply. The deadline bounds when the last call ends: a hand-over starts only while what is left covers
# its calls' waits plus observation_order.HAND_OVER_MARGIN_S (`media_plan`). A job still running then is recorded as
# unfinished (`--deferred-incomplete`), never as failed, and the analysis goes on with what arrived; the wait ends as
# soon as every job is terminal.
WAIT_BUDGET_S = observation_order.OBSERVE_DEADLINE_S
# A hard cap besides wall time: a normal round takes about 45-60 seconds, so 15 minutes is about 15-20 rounds;
# if the host returns immediately every time, this stops the hand-overs from repeating forever.
MAX_ROUNDS = 40
# Within one hand-over, how many more times the model may call again on the spot while jobs are still running
# (this only saves steps; how long to wait is still decided by the wall time above, and near the deadline the
# hand-over allows only as many calls as it still covers).
CALLS_PER_HAND_OVER = 6
# Option name -> operation of collect_video_media. Metadata goes through the media tool only on platforms whose
# support-list metadata_route is media_call (YouTube uses youtube_get_video).
OPERATIONS = {
    "metadata": "collect_public_metadata",
    "transcript": "fetch_transcript",
    "keyframes": "extract_keyframes",
    "measure": "measure_media_signals",
}
# The same value as the frame-count cap in static_host.job-call.
MAX_FRAMES = static_host.FRAME_CAPS["public_video_extract_keyframes"]
# The keyframes request's two optional additions to the duration_scaled plan, both still inside max_frames: a frame
# just after each detected cut (on by default), and up to three denser windows: the first 50 seconds every 0.5s on
# every video (select_method.DEFAULT_DENSE_WINDOW) after any a method card asks for (analysis/method.json `frames`,
# written by select_method.py). And `overview`: on a video longer than 50 seconds, low-resolution sheets of every
# second and, in place of the body grid, high-resolution frames where the picture or on-screen text changes
# (acv_timing.py's docstring). A server that does not know them yet ignores them
# and takes its standard plan. One that refuses them gets the same call once more without them: inside this call
# that is the keyframes item failing with `validation_error` (the other items still run); a whole-call MCP -32602
# is handled the same way. `overview` is the newest, so a refusal drops it alone first, then the other two.
FRAME_OPTION_KEYS = ("include_shot_starts", "dense_windows", "overview")
MAX_DENSE_WINDOWS = 3
MIN_DENSE_INTERVAL_S = 0.2
# Same approach as the connector_driver.py handoff (kabo ADR-0084 "2026-11-04"): the model hands over only the
# result id, and the resume fetches by id itself; saving to a file is only the fallback when there is no
# download link.
SAVE_RULE = ("Do not save the result. Its download url holds its result id: the 22 characters between "
             "`research-export/v1/` and `.json`. Put the id of your last call's result into the resume command "
             "below as `--id=<id>`. Only if that result has no download url, save it whole, as returned, to the "
             "fallback file named under the call (with the host's file-write tool, never as a command-line "
             "argument) and leave `--id` out. Never download anything yourself; call get_research_data_download "
             "only when the resume says the id expired.")


# A video the creator attached in Kabo: the same reference form as remake-viral-video's static_host.py FILE_REF_RE.
FILE_REF_RE = re.compile(r"^kabo-file:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.IGNORECASE)


def video_source(raw: str) -> str:
    """The video source as the media tool takes it: a link unchanged, a Kabo file reference in lower case."""
    text = str(raw).strip()
    if not text.lower().startswith("kabo-file:"):
        return text
    found = FILE_REF_RE.match(text)
    if not found:
        raise ValueError("a Kabo file reference is kabo-file:<id>, the id of the attached video exactly as given")
    return f"kabo-file:{found.group(1).lower()}"


def is_file_ref(source: str) -> bool:
    return bool(FILE_REF_RE.match(str(source)))


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


def dense_windows(value: Any) -> list[dict[str, float]]:
    """The valid dense windows of a frame plan, at most MAX_DENSE_WINDOWS, in the request's shape."""
    windows = []
    for window in value if isinstance(value, list) else []:
        if not isinstance(window, dict):
            continue
        numbers = [window.get(key) for key in ("start_s", "end_s", "interval_s")]
        if not all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in numbers):
            continue
        start, end, interval = (float(number) for number in numbers)
        if start >= 0 and end > start and interval >= MIN_DENSE_INTERVAL_S:
            entry = {"start_s": start, "end_s": end, "interval_s": interval}
            if entry not in windows:
                windows.append(entry)
    return windows[:MAX_DENSE_WINDOWS]


def frame_options() -> dict[str, Any]:
    """This run's keyframes options, fixed at the first hand-over so a repeated call keeps the same arguments.

    Empty once the server refused them. Shot starts are on unless the method's frame plan turns them off."""
    current = state()
    if current.get("frame_options_refused"):
        return {}
    if isinstance(current.get("frame_options"), dict):
        return current["frame_options"]
    plan: dict[str, Any] = {}
    chosen = static_host.run_dir() / "analysis" / "method.json"
    if chosen.is_file():
        try:
            method = json.loads(chosen.read_text(encoding="utf-8"))
        except ValueError:
            method = {}
        plan = method.get("frames") if isinstance(method, dict) and isinstance(method.get("frames"), dict) else {}
    # The default window (the first 50s every 0.5s) always goes, after the cards' windows; three at most.
    options: dict[str, Any] = {"include_shot_starts": plan.get("include_shot_starts") is not False,
                               "dense_windows": select_method.with_default_window(dense_windows(plan.get("dense_windows"))),
                               "overview": True}
    current["frame_options"] = options
    save_state(current)
    return options


def refuse_frame_options(tool: str) -> str:
    """The server refused the frame options before anything ran: the next call goes without `overview` if it was
    sent, else without any of them. Returns the option names dropped."""
    current = state()
    sent = current.get("frame_options") or {}
    if sent.get("overview") and not current.get("overview_refused"):
        current["overview_refused"] = True
        current["frame_options"] = {key: value for key, value in sent.items() if key != "overview"}
        dropped = "overview"
        current.setdefault("notes", []).append(
            f"{tool} did not accept overview on this server; repeated without it, so the frames follow the "
            "duration-scaled plan with its body grid")
    else:
        current["frame_options_refused"] = True
        dropped = "include_shot_starts / dense_windows"
        current.setdefault("notes", []).append(
            f"{tool} did not accept include_shot_starts / dense_windows on this server; repeated without them, so the "
            "frames follow the standard plan")
    save_state(current)
    return dropped


def options_refused_in(record: dict[str, Any]) -> bool:
    """Whether this terminal result's keyframes item failed on its arguments while the frame options were sent."""
    current = state()
    if current.get("frame_options_refused") or not any((current.get("frame_options") or {}).get(key)
                                                        for key in FRAME_OPTION_KEYS):
        return False
    for call in record.get("calls") or []:
        if not str(call.get("group", "")).endswith("/extract_keyframes") or not Path(call.get("path", "")).is_file():
            continue
        try:
            body = json.loads(Path(call["path"]).read_text())
        except ValueError:
            return False
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        code = body.get("error_code") or error.get("code") or error.get("error_code")
        return body.get("status") == "failed" and code == "validation_error"
    return False


OVERVIEW_NOT_APPLIED = ("The overview was not applied: there are no low-resolution sheets of every second, the body "
                        "follows the evenly spaced grid, and no frame was chosen where the picture or on-screen text "
                        "changes. Say what the gaps between frames may hide.")


def frame_options_note(envelope: dict[str, Any]) -> str | None:
    """What became of the frame options on a finished keyframes envelope; None when nothing needs saying."""
    current = state()
    if current.get("frame_options_refused"):
        return ("This server refused the shot-start and dense-window frame options; the frames follow the standard "
                "plan." + (" " + OVERVIEW_NOT_APPLIED if current.get("overview_refused") else ""))
    sent = current.get("frame_options") or {}
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    plan = data.get("sampling_plan") if isinstance(data.get("sampling_plan"), dict) else {}
    duration = data.get("duration_s")
    long_video = isinstance(duration, (int, float)) and duration > OVERVIEW_ABOVE_S
    overview = data.get("overview") if isinstance(data.get("overview"), dict) else None
    notes = []
    if current.get("overview_refused") and long_video:
        notes.append("This server refused the overview option. " + OVERVIEW_NOT_APPLIED)
    elif sent.get("overview") and long_video and data.get("frames") and (overview or {}).get("status") != "available":
        reason = (overview or {}).get("reason")
        notes.append(("The overview failed on the server" + (f" ({reason})" if reason else "") + ". "
                      if overview else "This server does not make the overview yet. ") + OVERVIEW_NOT_APPLIED)
    if not any(sent.get(key) for key in ("include_shot_starts", "dense_windows")) or not data.get("frames"):
        return " ".join(notes) or None
    if "include_shot_starts" not in plan and "dense_windows" not in plan:
        notes.insert(0, "This server took its standard frame plan: the shot-start and dense-window options were not "
                        "applied, so no frame was placed at a cut on purpose.")
    return " ".join(notes) or None


def overview_lines(envelope: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The overview sheets' object refs (read before the frames) and one line saying how to read them."""
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    overview = data.get("overview") if isinstance(data.get("overview"), dict) else {}
    sheets = [sheet for sheet in overview.get("sheets") or []
              if isinstance(sheet, dict) and sheet.get("object_ref")] if overview.get("status") == "available" else []
    if not sheets:
        return [], []
    spans = "; ".join(f"{sheet.get('sheet_id')} {sheet.get('from_s')}-{sheet.get('to_s')}s" for sheet in sheets)
    return [sheet["object_ref"] for sheet in sheets], [
        f"Overview: the first {len(sheets)} image(s) read are low-resolution sheets of every "
        f"{overview.get('stride_s')}s of the whole video, {overview.get('columns')} tiles a row and "
        f"{overview.get('rows')} rows a sheet, in time order left to right and top to bottom (tile n of a sheet is "
        f"its first second + n x {overview.get('stride_s')}s): {spans}. Look at them first; they are the only view of "
        "the seconds between the high-resolution frames after them. Quote on-screen text from a frame, not from a "
        "sheet."]


def call_arguments(args: argparse.Namespace) -> dict[str, Any]:
    requests = []
    for name in args.operations:
        parameters: dict[str, Any] = {"url": args.url}
        if name == "keyframes":
            parameters.update({"sampling": "duration_scaled", "max_frames": args.max_frames})
            parameters.update({key: value for key, value in (getattr(args, "frame_options", None) or {}).items()
                               if key in FRAME_OPTION_KEYS and value})
        requests.append({"content_id": "video", "operation": OPERATIONS[name], "parameters": parameters})
    arguments: dict[str, Any] = {"requests": requests, "run_key": run_key(), "delivery": "download"}
    wait = getattr(args, "wait_s", None)
    if wait is not None and wait < observation_order.CALL_WAIT_S:
        # Shortened so the call ends inside the observation deadline; a full wait is the tool's own, sent as nothing.
        arguments["wait_s"] = int(wait)
    return arguments


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


def hand_over_media(args: argparse.Namespace, note: str = "",
                    plan: tuple[int, int | None] = (CALLS_PER_HAND_OVER, None)) -> None:
    """Print the media call. `plan` is (how many calls this hand-over may make, the wait_s each sends or None for the
    tool's own wait), from media_plan."""
    calls, args.wait_s = plan
    current = state()
    results = Path.cwd() / "host-results"
    first = len(list(results.glob("*.json"))) + 1 if results.is_dir() else 1
    file = results / f"{first:02d}-{TOOL}.json"
    current.setdefault("awaiting", []).append(str(file))
    current["handed_at"] = datetime.now(timezone.utc).isoformat()
    current.setdefault("started_at", current["handed_at"])
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
        f"0 or you have made it {calls} times; only the last result counts. The media is not ready until this "
        f"script says so: the run is not over while jobs are running. " + SAVE_RULE)
    say("call: " + json.dumps({"tool": TOOL, "arguments": call_arguments(args)}, ensure_ascii=False))
    say(f"  result {file.name.split('-', 1)[0]}  (fallback file, only if the result has no download url: {file})")
    say("Then run this one command right away, <id> replaced by the last result's id (ids expire in 10 "
        "minutes): " + resume_command(args))


def waited_s(current: dict[str, Any]) -> float:
    """Seconds since this run first handed the media call over."""
    try:
        started = datetime.fromisoformat(str(current.get("started_at") or current.get("handed_at")))
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


def media_plan(current: dict[str, Any]) -> tuple[int, int | None] | None:
    """(calls, wait_s) for the next media hand-over, so its last call still ends inside the observation deadline:
    as many full-length calls as fit (CALLS_PER_HAND_OVER at most, wait_s None), else one shorter call; None when
    not even that fits and the wait stops now."""
    left = WAIT_BUDGET_S - waited_s(current)
    full = int((left - observation_order.HAND_OVER_MARGIN_S) // observation_order.CALL_WAIT_S)
    if full >= 1:
        return min(CALLS_PER_HAND_OVER, full), None
    waits = observation_order.round_waits(left, 1)
    return (1, waits[0]) if waits else None


def staged_since(moment: str | None) -> bool:
    if not moment:
        return False
    return any(str(record.get("staged_at") or "") >= moment for record in static_host.composite_records(TOOL))


def take_saved(result_id: str | None) -> str:
    """Bring the saved results of the last hand-over into the run. The option names dropped when the server refused
    the frame options (MCP -32602) and the call must be made again without them; empty otherwise."""
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
        if (viewer_response.input_rejected(raw) and not current.get("frame_options_refused")
                and any((current.get("frame_options") or {}).get(key) for key in FRAME_OPTION_KEYS)):
            # Nothing was queued or charged: the server refused the arguments before any job ran.
            taken[name] = digest
            save_state(current)
            return refuse_frame_options(TOOL)
        try:
            result = static_host.fetch(TOOL, raw)
            if result.get("fetched") == 0:
                result = static_host.stage(TOOL, raw)
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise ValueError(f"{path} does not hold a usable {TOOL} result ({error}). Save the complete result there "
                             "as returned, download link included, then run the same resume command again") from None
        taken[name] = digest
        save_state(current)
    return ""


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
    if pending:
        # A job still running at the wait cap is unfinished, not failed: the backend reported no error for it. The
        # model used to call it service_unavailable.
        say(f"{len(pending)} media job(s) were still running when waiting stopped after about "
            f"{round(waited_s(current))} s ({', '.join(item.split('=', 1)[0] for item in pending)}). They did not "
            "arrive in time and are unfinished, not failed: the backend reported no error for them. Pass each as "
            "--deferred-incomplete (below) and say plainly in the report that this step did not arrive in time; "
            "never describe it as a backend failure, service_unavailable or a network problem.")
    flags = " ".join(f"--envelope {path}" for path in envelopes)
    flags += "".join(f" --deferred-incomplete {flag}" for flag in pending)
    say("Pass these to build_content_evidence.py, beside the run's other envelopes: " + flags)
    keyframes = next((call for call in record.get("calls") or [] if str(call["group"]).endswith("/extract_keyframes")),
                     None)
    if keyframes and Path(keyframes["path"]).is_file():
        envelope = json.loads(Path(keyframes["path"]).read_text())
        note = frame_options_note(envelope)
        if note:
            say(note)
        refs = [item.get("object_ref") for item in ((envelope.get("data") or {}).get("frames") or [])
                if isinstance(item, dict) and item.get("object_ref")]
        sheet_refs, legend = overview_lines(envelope)
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
            for line in legend:
                say(line)
            say("read: " + json.dumps({"tool": "read_research_data_artifacts",
                                       "arguments": {"job_id": job_id, "object_refs": sheet_refs + refs}},
                                      ensure_ascii=False))
            return
    say("No frames arrived: keep the missing-visual-evidence limit and read the transcript and measurements only.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the original public video url, or kabo-file:<id>")
    parser.add_argument("--operations", required=True,
                        help="comma-separated: " + ", ".join(OPERATIONS) + " (metadata only on "
                        + ", ".join(public_video_sources.media_call_metadata_labels()) + ")")
    parser.add_argument("--max-frames", type=int, default=MAX_FRAMES)
    parser.add_argument("--placed", action="store_true")
    parser.add_argument("--id", dest="result_id", help="the result id of the last collect_video_media call")
    args = parser.parse_args(argv)
    bind_run_to_cwd()
    args.operations = [name.strip() for name in args.operations.split(",") if name.strip()]
    try:
        args.url = video_source(args.url)
        unknown = [name for name in args.operations if name not in OPERATIONS]
        if unknown or not args.operations:
            raise ValueError("--operations takes " + ", ".join(OPERATIONS) + "; got " + ",".join(unknown or ["nothing"]))
        if not 1 <= args.max_frames <= MAX_FRAMES:
            raise ValueError(f"--max-frames must be from 1 to {MAX_FRAMES}")
        args.frame_options = frame_options() if "keyframes" in args.operations else {}
        if not args.placed:
            if state().get("awaiting"):
                say("This media round was already handed over; make the call printed earlier, or run with --placed.")
            hand_over_media(args)
            return 0
        dropped = take_saved(args.result_id)
        if dropped:
            args.frame_options = frame_options()
            plan = media_plan(state())
            if plan is None:
                raise ValueError(f"the {WAIT_BUDGET_S}-second observation deadline left no time to repeat the media "
                                 f"call without {dropped}")
            hand_over_media(args, note=f"This server did not accept {dropped}: repeating "
                                       "the same call without them (nothing was queued or charged).", plan=plan)
            return 0
        records = static_host.composite_records(TOOL)
        if not records:
            raise ValueError(f"no {TOOL} result was saved in this run; make the printed call and save it first")
        latest = records[-1]
        pending = int((latest.get("coverage") or {}).get("pending") or 0)
        current = state()
        current["rounds"] = int(current.get("rounds") or 0) + 1
        save_state(current)
        waited = waited_s(current)
        # No new call once the deadline cannot cover its wait: the jobs still running did not arrive in time.
        plan = media_plan(current) if current["rounds"] < MAX_ROUNDS else None
        if pending and plan:
            hand_over_media(args, note=f"{pending} media job(s) are still running ({round(waited)} of up to "
                                       f"{WAIT_BUDGET_S} s waited); keep waiting.", plan=plan)
            return 0
        if plan and options_refused_in(latest):
            dropped = refuse_frame_options(TOOL)
            args.frame_options = frame_options()
            hand_over_media(args, note=f"This server refused {dropped} for the frames: "
                                       "repeating the same call without them (the finished jobs are not run again).",
                            plan=plan)
            return 0
        finish(latest)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as error:
        say(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
