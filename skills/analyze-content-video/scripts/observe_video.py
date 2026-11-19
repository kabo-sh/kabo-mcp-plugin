#!/usr/bin/env python3
"""Observe one public video: pick the observation source, hand over its calls, and persist what comes back.

Run it from the run directory, after select_method.py wrote `analysis/method.json` from the creator's request. The
source comes from references/observation-order.json and this run's facts (platform, duration when known, what
already failed, the method cards selected: the `sound` card adds a whole-video viewing), never from the host:

- `server_frames`: one `collect_video_media` call (transcript, keyframes, measurements, metadata) that the
  backend queues and waits for, as collect_media.py does.
- `whole_video`: one `analyze_content_video` call (a viewer watches the whole video with its audio), read back
  with `get_analysis_run` until it is terminal; plus a media call for the platform's metadata where it comes
  from the media tool and, while the duration is unknown, a measurement that reports it (in the same call). The submission returns at once (KS8: no server-side wait on the initial call);
  each reading waits inside the tool (`wait_s`). Both ask for `delivery: "download"`: a
  completed answer then carries a signed download of the complete result, which this script downloads and checks
  (sha256 and bytes, expiry) with static_host.py's downloader; an inline answer (a host that ignores `delivery`)
  is read as it is.
- `combined`: both. The whole-video call goes first so it runs while the media jobs run.

A fallback that needs media operations no earlier media call asked for (a failed viewing on Instagram or TikTok
had only the metadata-only call) starts one more media call for exactly those operations, under the same run key;
each source is judged on the media results that carry its operations. The mode bends the order the way
observation_order.py says: a transcript export never starts a viewing, a craft teardown never views without frames.
The paid viewing starts only once the video's duration is known to be within the whole-video limit: from
`--duration-s`, the media results (metadata, frames, measurement or transcript, in a call already being made or the
viewing's own media call, which measures the file while the duration is unknown) or the YouTube metadata envelope
the run persisted. A run where every source came back empty prints `nothing_observed` and no build arguments. Until then it waits
in the rounds the media call already takes; when the duration stays unknown or is over the limit, no viewing
starts, a limitation says why, and the other source carries on (or, with nothing left, the run ends with that gap).

`--url` is the public link, or `kabo-file:<uuid>` for a video the creator attached in Kabo (frames, transcript and
measurements from the stored file; no whole-video viewing).

First run prints the calls and one resume command. `--placed [--id=<id>]` reads what was saved: while a job is
still running it prints the remaining calls again (a whole-video poll only after `POLL_INTERVAL_S` since the
last hand-over, waited inside the tool or, where the tool came back early, here); when a source fails it falls back
as the order table says; when everything is terminal it persists the media envelopes, a redacted copy of the
whole-video result (`snapshot/whole-video.json`, observations and transcript only), and prints the arguments
for build_content_evidence.py and the one frame read.

At most one whole-video analysis is started per run: its idempotency key never changes, so re-sending the
call after a lost answer replays the same analysis instead of starting a paid second one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import acv_timing  # noqa: E402
import collect_media  # noqa: E402
import observation_order  # noqa: E402
import public_video_sources  # noqa: E402
import static_host  # noqa: E402
import viewer_response  # noqa: E402

STATE = Path("observe-video.json")
MEDIA_TOOL = collect_media.TOOL
START_TOOL = viewer_response.START_TOOL
POLL_TOOL = viewer_response.POLL_TOOL
PERSISTED_VIEWER = "snapshot/whole-video.json"
# At most this many frames per read: hosts cap the images one tool result may show.
READ_CHUNK = 15
# A reading waits inside the call for a final status (`wait_s`), the way collect_video_media waits for its jobs.
# 45 seconds, the same budget as collect_media.py: it keeps the call inside the 60-second tool timeout some hosts
# (Codex) apply. The submission itself does not wait (docs/skills-spec.md KS8, decision of 2026-10-20). Where a reading still comes back sooner (a host or server that does not
# wait), the script waits out the rest of POLL_INTERVAL_S since the hand-over itself (inside one command, well
# under the hosts' one-minute command limit), so a poll costs one model turn per interval, not one per second.
VIEWER_WAIT_S = 45
POLL_INTERVAL_S = 40
# A completed result whose download expired or could not be read is asked for again with get_analysis_run (it only
# reads; nothing is re-run or charged): with a new link after an expiry, inline otherwise. At most this many times.
MAX_REDELIVERIES = 2
# A video of up to ten minutes is normally analysed in one to two minutes; stop waiting well after that.
VIEWER_BUDGET_S = 8 * 60
MAX_POLLS = 15
MODES = ("diagnosis", "content_read", "craft_teardown", "transcript_export")
MODE_OPERATIONS = {
    "diagnosis": ["transcript", "keyframes", "measure"],
    "content_read": ["transcript", "keyframes"],
    "craft_teardown": ["transcript", "keyframes", "measure"],
    "transcript_export": ["transcript"],
}
# Modes whose answer reads the post's own metadata (title, counts, caption, tags).
METADATA_MODES = {"diagnosis", "content_read"}
SAVE_RULE = (
    f"Save each {START_TOOL} / {POLL_TOOL} result whole, as returned (its download link or an error included), to "
    "the file named under its call with the host's file-write tool, never as a command-line argument; this script "
    f"downloads and checks what the link holds. For {MEDIA_TOOL}, do not save the result: put its result id (the 22 characters between "
    "`research-export/v1/` and `.json` in its download url) into the resume command as `--id=<id>`; only if it has "
    "no download url, save it whole to its file and leave `--id` out. Never download anything yourself.")


def say(text: str) -> None:
    print(text, flush=True)


def now() -> datetime:
    return datetime.now(timezone.utc)


def state() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def save_state(value: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def seconds_since(moment: str | None) -> float:
    if not moment:
        return 0.0
    try:
        return max(0.0, (now() - datetime.fromisoformat(moment)).total_seconds())
    except ValueError:
        return 0.0


class DownloadProblem(ValueError):
    """A whole-video download that could not be used; `mode` says how to ask for the result again."""

    def __init__(self, mode: str, reason: str):
        super().__init__(reason)
        self.mode = mode


def platform_of(url: str) -> str | None:
    if collect_media.is_file_ref(url):
        # A file attached in Kabo is on no platform's address: the media tool reads the stored file.
        return None
    found = public_video_sources.match_url(url)
    return found["platform"] if found else None


def media_operations(source: str, mode: str, platform: str | None, *, need_duration: bool = False) -> list[str]:
    metadata = ((public_video_sources.source(platform) or {}).get("metadata_route") == "media_call"
                and mode in METADATA_MODES)
    if source == "whole_video":
        # The viewer replaces frames and measurements, not the post's metadata. With the duration still unknown, the
        # same call also measures the file: the measurement reports the duration the viewing waits for, where the
        # metadata has none (Instagram) or comes from a tool that may answer unsupported (YouTube's).
        return (["metadata"] if metadata else []) + (["measure"] if need_duration and mode != "transcript_export"
                                                      else [])
    return (["metadata"] if metadata else []) + MODE_OPERATIONS[mode]


def viewer_key() -> str:
    # Fixed per run: a repeated start replays the same analysis instead of starting (and charging) a new one.
    return "acv-wv:" + hashlib.sha256(str(static_host.run_dir().resolve()).encode()).hexdigest()[:32] + ":a1"


def slot(tool: str) -> Path:
    results = Path.cwd() / "host-results"
    results.mkdir(exist_ok=True)
    taken = {path.name.split("-", 1)[0] for path in results.glob("*.json")}
    taken |= {Path(name).name.split("-", 1)[0] for name in state().get("slots", [])}
    number = 1
    while f"{number:02d}" in taken:
        number += 1
    current = state()
    current.setdefault("slots", []).append(str(results / f"{number:02d}-{tool}.json"))
    save_state(current)
    return results / f"{number:02d}-{tool}.json"


def resume_command(current: dict[str, Any]) -> str:
    argv = [str(SCRIPTS / "observe_video.py"), "--url", current["url"], "--mode", current["mode"], "--placed"]
    return f"cd {collect_media.quote(str(static_host.run_dir()))} && python3 " + " ".join(
        collect_media.quote(part) for part in argv)


def selected_cards() -> list[str]:
    """The method cards select_method.py chose from the request before the fetch (none when it did not run)."""
    chosen = static_host.run_dir() / "analysis" / "method.json"
    if not chosen.is_file():
        return []
    method = json.loads(chosen.read_text(encoding="utf-8"))
    return [str(card["id"]) for card in method.get("cards") or [] if isinstance(card, dict) and card.get("id")]


def viewer_arguments(current: dict[str, Any], *, start: bool) -> dict[str, Any]:
    viewer = current["viewer"]
    if current.get("legacy_viewer_args"):
        # A server that does not know wait_s / delivery yet: the original arguments, answered inline, polled at the
        # script's own pace (POLL_INTERVAL_S).
        return ({"source_url": current["url"], "idempotency_key": viewer["key"]} if start
                else {"analysis_id": viewer["analysis_id"]})
    if start:
        return {"source_url": current["url"], "idempotency_key": viewer["key"], "delivery": "download"}
    if viewer.get("redeliver") == "inline":
        # The finished result once more, in the answer itself: its download could not be used here.
        return {"analysis_id": viewer["analysis_id"], "delivery": "inline"}
    return {"analysis_id": viewer["analysis_id"], "wait_s": VIEWER_WAIT_S, "delivery": "download"}


def media_namespace(current: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(url=current["url"], operations=current["media"]["operations"],
                           max_frames=collect_media.MAX_FRAMES)


def hand_over_calls(current: dict[str, Any], *, start_viewer: bool, poll_viewer: bool, media: bool,
                    note: str = "") -> None:
    """Print the calls still needed this round, the file for each, and the one resume command."""
    # KS9: this is a bounded wait on ONE whole-video job (one start, then get_analysis_run readings of the same
    # analysis id until it is terminal or VIEWER_BUDGET_S is spent), the same pattern as collect_media.py's
    # hand_over_media for collect_video_media; it is not a multi-round fetch orchestration, so it is not listed in
    # fetch-orchestration.test.mjs HANDOVER_SITES. Each reading waits inside the tool (wait_s), so a viewing of a
    # few minutes normally takes the start and one or two readings.
    calls = []
    if start_viewer:
        file = slot(START_TOOL)
        calls.append((START_TOOL, viewer_arguments(current, start=True), file))
    elif poll_viewer:
        file = slot(POLL_TOOL)
        calls.append((POLL_TOOL, viewer_arguments(current, start=False), file))
    if media:
        file = slot(MEDIA_TOOL)
        calls.append((MEDIA_TOOL, collect_media.call_arguments(media_namespace(current)), file))
        media_state = collect_media.state()
        media_state.setdefault("awaiting", []).append(str(file))
        media_state["handed_at"] = now().isoformat()
        media_state.setdefault("started_at", media_state["handed_at"])
        collect_media.save_state(media_state)
    current = state() | {key: value for key, value in current.items() if key != "slots"}
    current["awaiting"] = [{"tool": tool, "file": str(file)} for tool, _, file in calls]
    current["handed_at"] = now().isoformat()
    save_state(current)
    if note:
        # On its own line: the Web host recognises a hand-over only by a line starting with "Hand-over: ".
        say(note)
    order = " in this order, in one turn," if len(calls) > 1 else ""
    say(f"Hand-over: make {'these ' + str(len(calls)) + ' calls' if len(calls) > 1 else 'this one call'} now"
        f"{order} with the arguments verbatim. The observation is not over until this script says so. " + SAVE_RULE)
    for tool, arguments, file in calls:
        say("call: " + json.dumps({"tool": tool, "arguments": arguments}, ensure_ascii=False))
        kind = "only if the result has no download url" if tool == MEDIA_TOOL else "always, the whole result as returned"
        say(f"  result {file.name.split('-', 1)[0]}  (fallback file, {kind}: {file})")
    tail = resume_command(current)
    if media:
        say("Then run this one command right away, <id> replaced by the collect_video_media result's id (ids "
            "expire in 10 minutes): " + tail + " --id=<id>")
    else:
        say("Then run this one command right away (ids expire in 10 minutes, download links too): " + tail)


def start(args: argparse.Namespace) -> int:
    url = collect_media.video_source(args.url)
    platform = platform_of(url)
    cards = selected_cards()
    order = observation_order.load_order()
    source, reason = observation_order.choose(order, platform=platform, duration_s=args.duration_s,
                                              force=args.observe_source, mode=args.mode, cards=cards)
    if source is None or source == "local_frames":
        raise ValueError(f"no observation source for this link: {reason}")
    current = {"url": url, "mode": args.mode, "platform": platform, "duration_s": args.duration_s, "cards": cards,
               "source": source, "reason": reason, "tried": [], "started_at": now().isoformat(),
               "viewer": {"active": False}, "media": {"active": False}}
    save_state(current)
    analysis = static_host.run_dir() / "analysis"
    acv_timing.open_stage(analysis, "observe")
    acv_timing.set_source(analysis, source)
    return begin(current, note=f"Observation source: {source} ({reason}).")


def begin(current: dict[str, Any], note: str = "") -> int:
    """Start whatever the current source needs that has not started yet."""
    source = current["source"]
    viewer = current["viewer"]
    media = current["media"]
    requested = list(media.get("requested") or (media.get("operations") or [] if media.get("active") else []))
    # Only what no earlier media call asked for: a request already made is never made again under this run key.
    need_duration = source in {"whole_video", "combined"} and known_duration(current) is None
    missing = [name for name in media_operations(source, current["mode"], current["platform"],
                                                 need_duration=need_duration) if name not in requested]
    start_media = bool(missing)
    if start_media:
        if media.get("active"):
            # A new call gets its own wait budget; the earlier call's results stay where they were placed.
            media_state = collect_media.state()
            media_state.pop("started_at", None)
            media_state["rounds"] = 0
            collect_media.save_state(media_state)
        current["media"] = {"active": True, "operations": missing, "requested": requested + missing, "done": False}
    start_viewer = False
    if source in {"whole_video", "combined"} and not viewer.get("active"):
        in_flight = start_media or bool(media.get("active") and not media.get("done"))
        verdict, code = viewer_gate(current, media_in_flight=in_flight)
        if verdict == "start":
            activate_viewer(current)
            start_viewer = True
        elif verdict == "wait":
            current["viewer_deferred"] = True
            if not start_media and not in_flight:
                return duration_round(current, note)
        else:
            refuse_viewer(current, code)
    save_state(current)
    if not start_viewer and not start_media:
        return settle(current)
    hand_over_calls(current, start_viewer=start_viewer, poll_viewer=False, media=start_media, note=note)
    return 0


def download_viewer(offer: dict[str, Any], tool: str) -> bytes:
    """The complete result a whole-video download holds, checked; DownloadProblem says how to ask again."""
    descriptor = offer["download"]
    if not isinstance(descriptor, dict) or descriptor.get("status") != "ready":
        reason = descriptor.get("reason") if isinstance(descriptor, dict) else None
        raise DownloadProblem("inline", f"the result offered no ready download ({reason or 'absent'})")
    if descriptor.get("content_type") != "application/json":
        raise DownloadProblem("inline", "the result's download is not JSON")
    kind = descriptor.get("kind") if descriptor.get("kind") in {"envelope", "artifact"} else "envelope"
    try:
        # The same verified download collect_video_media results get: exact signed-storage host, no redirects,
        # declared bytes and sha256 checked while streaming, nothing returned unless all of them match.
        body = static_host.download(tool, descriptor, kind, "")
    except ValueError as error:
        text = str(error)
        raise DownloadProblem("download" if "expired" in text else "inline", text.split(". ")[0]) from None
    try:
        run = viewer_response.run_of(body)
    except ValueError:
        raise DownloadProblem("inline", "the downloaded result is not JSON") from None
    # The body is the complete answer of this same call: the same analysis, in the same state.
    if not isinstance(run, dict) or run.get("id") != offer.get("id") or run.get("status") != offer.get("status"):
        raise DownloadProblem("inline", "the downloaded result does not match this tool result")
    return body


def read_viewer(current: dict[str, Any], file: Path, tool: str) -> None:
    if not file.is_file():
        raise ValueError(f"no saved {tool} result at {file}: save the result whole, as returned, to that file, "
                         "then run the same resume command again")
    raw = file.read_bytes()
    viewer = current["viewer"]
    if not current.get("legacy_viewer_args") and viewer_response.input_rejected(raw):
        # The server refused the newer inputs (wait_s / delivery) before anything ran: nothing was started or
        # charged. Send the same call once more with the original arguments, and keep them for the rest of the run.
        current["legacy_viewer_args"] = True
        viewer["legacy_retry"] = tool
        current.setdefault("fallback_notes", []).append(
            f"{tool} did not accept wait_s / delivery on this server; repeated with its original arguments")
        return
    if tool == POLL_TOOL:
        viewer["polls"] = int(viewer.get("polls") or 0) + 1
    viewer["read_at"] = now().isoformat()
    offer = viewer_response.download_offer(raw)
    reading, fetched = None, None
    if offer is not None:
        if isinstance(offer.get("id"), str) and viewer_response.UUID.match(offer["id"]):
            viewer["analysis_id"] = offer["id"]
        try:
            raw = download_viewer(offer, tool)
            fetched = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        except DownloadProblem as problem:
            viewer["redeliveries"] = int(viewer.get("redeliveries") or 0) + 1
            if viewer["redeliveries"] <= MAX_REDELIVERIES and viewer.get("analysis_id"):
                # Ask for the same finished result again; nothing is re-run or charged.
                viewer.update(status="download_pending", redeliver=problem.mode, done=False)
                return
            reading = {"run": None, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                       "error": {"code": "download_failed", "message": str(problem)[:300], "retryable": False}}
    if reading is None:
        reading = viewer_response.read(raw)
    viewer.pop("redeliver", None)
    run = reading["run"]
    if run is None:
        viewer.update(status="error", error=reading["error"], done=True)
    else:
        viewer.update(analysis_id=run["id"], status=run["status"],
                      done=run["status"] in viewer_response.TERMINAL)
    # The persisted copy holds observations and the transcript only; scores, verdicts and advice stay behind in
    # host-results/, the tool's own answer, which nothing downstream reads.
    persisted = {"schema_version": viewer_response.PERSISTED, "tool": tool, "source_url": current["url"],
                 "idempotency_key": viewer["key"], "polls": viewer["polls"], "raw_sha256": reading["raw_sha256"],
                 "saved_at": viewer["read_at"], "delivery": "download" if fetched else "inline", "download": fetched,
                 "response": run, "error": reading["error"],
                 "discarded_fields": viewer_response.DISCARDED_FIELDS}
    Path(PERSISTED_VIEWER).write_text(json.dumps(persisted, ensure_ascii=False, indent=2) + "\n")
    viewer["persisted"] = PERSISTED_VIEWER


def duration_of(body: Any) -> float | None:
    """The duration a terminal media or YouTube metadata envelope reports, in seconds."""
    if not isinstance(body, dict) or body.get("status") not in {"completed", "completed_partial"}:
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    video = data.get("video") if isinstance(data.get("video"), dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    for value in (video.get("duration_seconds"), data.get("duration_s"), data.get("duration_seconds"),
                  row.get("duration_seconds")):
        if isinstance(value, str) and value.replace(".", "", 1).isdigit():
            value = float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    return None


def known_duration(current: dict[str, Any]) -> float | None:
    """This video's duration: given, or reported by a media result or the YouTube metadata envelope of this run.

    Only this video's own envelopes count (the media tool's, and youtube-public get_video); a baseline list also
    carries durations, of other videos."""
    if current.get("duration_s") is not None:
        return float(current["duration_s"])
    snapshot = static_host.run_dir() / "snapshot"
    for path in sorted(snapshot.glob("envelope-*.json")) + sorted((snapshot / ".host-evidence").glob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(body, dict):
            continue
        ours = (body.get("connector_id") == collect_media.CONNECTOR
                or (body.get("connector_id") == "youtube-public" and body.get("operation") == "get_video"))
        found = duration_of(body) if ours else None
        if found is not None:
            current["duration_s"] = found
            return found
    return None


def viewer_gate(current: dict[str, Any], *, media_in_flight: bool) -> tuple[str, str]:
    """("start" | "wait" | "refuse", code): whether the paid viewing may start now."""
    limit_s = observation_order.load_order()["whole_video_max_ms"] / 1000
    duration = known_duration(current)
    if duration is not None:
        return ("start", "") if duration <= limit_s else ("refuse", "too_long")
    if media_in_flight:
        return "wait", ""
    if (public_video_sources.source(current.get("platform")) or {}).get("metadata_route") != "media_call" \
            and not current.get("duration_waited"):
        # The platform's metadata comes from its own tool (YouTube: youtube_get_video), which the model calls
        # beside this script: give it one round to be persisted.
        return "wait", ""
    return "refuse", "duration_unknown"


GATE_TEXT = {
    "too_long": "the video runs {duration}s, past the whole-video limit of {limit}s",
    "duration_unknown": "the video duration could not be read first, and the viewing takes only videos up to {limit}s",
}


def refuse_viewer(current: dict[str, Any], code: str) -> None:
    """Record why no viewing starts; a combined observation carries on as server frames."""
    limit_s = observation_order.load_order()["whole_video_max_ms"] // 1000
    duration = current.get("duration_s")
    text = "Whole-video viewing not started because " + GATE_TEXT[code].format(
        duration=f"{duration:g}" if isinstance(duration, (int, float)) else "?", limit=limit_s) + "."
    current["viewer_deferred"] = False
    current.setdefault("limitations", []).append(text)
    if current["source"] == "combined":
        current["source"] = "server_frames"
        current.setdefault("fallback_notes", []).append(f"combined narrowed to server_frames ({code})")
        acv_timing.set_source(static_host.run_dir() / "analysis", "server_frames")
    else:
        # A whole-video observation that cannot start is a failed whole_video: settle falls back from it.
        current["viewer"] = {"active": False, "status": "error", "done": True,
                             "error": {"code": code, "message": text, "retryable": False}}


def activate_viewer(current: dict[str, Any]) -> None:
    current["viewer_deferred"] = False
    current["viewer"] = {"active": True, "key": viewer_key(), "analysis_id": None, "status": None,
                         "polls": 0, "started_at": now().isoformat(), "read_at": None, "done": False}


def duration_round(current: dict[str, Any], note: str) -> int:
    """A YouTube viewing waits one round for the youtube_get_video envelope; nothing else is handed over."""
    current["duration_waited"] = True
    save_state(current)
    if note:
        say(note)
    say("The whole-video viewing starts only once the video's duration is known. Make the youtube_get_video call "
        "the Skill lists (if not made yet), fetch and persist its result, then run this one command: "
        + resume_command(current))
    return 0


def media_pending(current: dict[str, Any]) -> int:
    records = static_host.composite_records(MEDIA_TOOL)
    if not records:
        raise ValueError(f"no {MEDIA_TOOL} result was saved in this run; make the printed call first")
    return int((records[-1].get("coverage") or {}).get("pending") or 0)


def finish_media(mode: str) -> dict[str, Any]:
    """Persist each terminal media envelope once; the build flags, the frame read, whether anything usable came and
    the duration the results report.

    Every media call of this run counts, not only the last: after a fallback the latest call carries only the
    operations the earlier one did not ask for. For each operation the newest result wins."""
    calls, jobs = {}, {}
    for record in static_host.composite_records(MEDIA_TOOL):
        for job in (record.get("summary") or {}).get("jobs") or []:
            if isinstance(job, dict):
                jobs[job["group"]] = job
        for call in record.get("calls") or []:
            calls[str(call["group"]).rsplit("/", 1)[-1]] = call
    media_state = collect_media.state()
    placed = media_state.setdefault("placed", {})
    envelopes, pending, usable, gone, duration = [], [], False, False, None
    read = None
    for operation, call in calls.items():
        body = json.loads(Path(call["path"]).read_text())
        if operation not in placed:
            placed[operation] = collect_media.persist(body.get("operation") or operation)
            collect_media.save_state(media_state)
        envelopes.append(placed[operation])
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        gone = gone or data.get("source_unavailable") is True
        done = body.get("status") in {"completed", "completed_partial"}
        if done and (
                (operation == "fetch_transcript" and (mode == "transcript_export" or data.get("cues")
                                                      or data.get("plain_text")))
                or (operation == "extract_keyframes" and data.get("frames"))):
            # A transcript export asks for the words only: a finished transcript with none (music only) is its
            # answer, not a failure to fall back from.
            usable = True
        if done and duration is None:
            video = data.get("video") if isinstance(data.get("video"), dict) else {}
            for value in (video.get("duration_seconds"), data.get("duration_s")):
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                    duration = float(value)
                    break
        if operation == "extract_keyframes":
            refs = [item.get("object_ref") for item in data.get("frames") or []
                    if isinstance(item, dict) and item.get("object_ref")]
            job_id = body.get("job_id") or (jobs.get(call["group"]) or {}).get("job_id")
            if refs and job_id:
                # A host cut one 60-frame read off after 16 images: read at most READ_CHUNK frames per call.
                # No `delivery`: the read shows the images inline, which is how the frames get viewed. A host that
                # answers with a download link instead is told to save and fetch it.
                read = [{"tool": "read_research_data_artifacts",
                         "arguments": {"job_id": job_id, "object_refs": refs[start:start + READ_CHUNK]}}
                        for start in range(0, len(refs), READ_CHUNK)]
    for group, job in jobs.items():
        operation = group.rsplit("/", 1)[-1]
        if operation not in placed and job.get("job_id") and job.get("status") in static_host.PENDING:
            pending.append(f"{operation}={job['job_id']}")
    return {"envelopes": envelopes, "pending": pending, "usable": usable, "source_unavailable": gone, "read": read,
            "duration_s": duration}


def observed_anything(current: dict[str, Any], media: dict[str, Any] | None) -> bool:
    """Whether any source brought something to analyse: frames, transcript words or whole-video notes.

    A gone video once came back as every media job `completed_partial` and empty, with no flag saying the source
    was unavailable, and a viewing that failed too: the run printed `observed` and the brief was built from
    nothing. A transcript export's finished transcript with no words is its answer, so it counts."""
    if media is not None and media["usable"]:
        return True
    viewer = current["viewer"]
    if not (viewer.get("active") and viewer.get("status") == "completed" and viewer.get("persisted")):
        return False
    try:
        reading = viewer_response.read(Path(viewer["persisted"]).read_bytes())
    except (OSError, ValueError):
        return False
    return bool(viewer_response.items(reading["run"]) or viewer_response.transcript_cues(reading))


def fall_back(current: dict[str, Any], failed: str, code: str | None) -> int | None:
    """Switch to the order table's fallback after `failed`; None when there is none."""
    current["tried"].append(failed)
    order = observation_order.load_order()
    source, reason = observation_order.choose(order, platform=current["platform"], duration_s=current["duration_s"],
                                              failed=current["tried"], failure_code=code, mode=current["mode"],
                                              cards=current.get("cards") or [])
    if source in {"whole_video", "combined"} and current["viewer"].get("active"):
        # Never a second paid whole-video analysis in one run.
        source, reason = None, "a whole-video viewing already ran in this run"
    current.setdefault("fallback_notes", []).append(f"{failed} failed ({code or 'no usable evidence'}); "
                                                     + (f"falling back to {source}" if source else reason))
    if source is None:
        save_state(current)
        return None
    current["source"] = source
    save_state(current)
    acv_timing.set_source(static_host.run_dir() / "analysis", source)
    return begin(current, note=f"{failed} returned no usable evidence ({code or 'nothing usable'}); trying {source} "
                               f"as the observation order says.")


def settle(current: dict[str, Any]) -> int:
    """Everything this source started is terminal (or out of time): fall back or hand over the evidence."""
    media = finish_media(current["mode"]) if current["media"].get("active") else None
    if media is not None and current.get("duration_s") is None and media["duration_s"] is not None:
        # The media call reports the duration: a fallback reads it, so an over-long video never starts a viewing.
        current["duration_s"] = media["duration_s"]
        save_state(current)
    viewer = current["viewer"]
    viewer_ok = viewer.get("active") and viewer.get("status") == "completed"
    if current["source"] == "server_frames" and media is not None and not media["usable"]:
        code = "source_unavailable" if media["source_unavailable"] else "media_unavailable"
        moved = fall_back(current, "server_frames", code)
        if moved is not None:
            return moved
    if current["source"] == "whole_video" and not viewer_ok:
        code = ((viewer.get("error") or {}).get("code") if viewer.get("status") == "error"
                else ("still_running" if viewer.get("status") in viewer_response.PENDING else viewer.get("status")))
        moved = fall_back(current, "whole_video", code)
        if moved is not None:
            return moved
    flags = []
    if media is not None:
        flags += [f"--envelope {path}" for path in media["envelopes"]]
        flags += [f"--deferred-incomplete {item}" for item in media["pending"]]
    if viewer.get("active") and viewer.get("persisted"):
        flags.append(f"--viewer {viewer['persisted']}")
    duration = current.get("duration_s")
    if duration is None and media is not None:
        duration = media["duration_s"]
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        # Given with --duration-s or read from a result: the evidence records it even when no envelope passed to the
        # builder carries it (a whole-video run needs it for the hook window and the promise).
        flags.append(f"--duration-s {duration:g}")
    # One line per limitation, however many times a round recorded it.
    flags += [f"--limitation {collect_media.quote(text)}" for text in dict.fromkeys(current.get("limitations") or [])]
    current["done"] = True
    save_state(current)
    nothing = not observed_anything(current, media)
    say(json.dumps({"status": "nothing_observed" if nothing else "observed", "source": current["source"],
                    "tried": current["tried"], "whole_video": viewer.get("status") if viewer.get("active") else None,
                    "media_pending": media["pending"] if media else []}, ensure_ascii=False))
    for line in dict.fromkeys(current.get("fallback_notes") or []):
        say("Fallback: " + line)
    if nothing:
        say("Every observation source came back empty: no frames, no transcript words and no whole-video notes. "
            "There is nothing to analyse, so do not build a report or describe the video's content. Follow "
            "*Stops and gaps* in the Skill: tell the creator in one or two sentences that this video could not be "
            "read (it may be deleted, private or limited to some regions), ask for another public link or the video "
            "file, and stop.")
        return 0
    if viewer.get("active") and not viewer_ok:
        say("The whole-video viewing did not complete, so its notes are unavailable; the evidence builder records "
            "that. Say so beside the claims it weakens, never as a backend failure.")
    if media and media["pending"]:
        say("Some media jobs were still running when waiting stopped. They are unfinished, not failed: say that "
            "step was still running, never a backend failure.")
    say("Pass these to build_content_evidence.py, plus one --envelope for each other snapshot/envelope-*.json this "
        "run persisted: " + " ".join(flags))
    if media and media["read"]:
        reads = media["read"]
        say(("Frames: make this one read now. " if len(reads) == 1 else
             f"Frames: make these {len(reads)} reads now, one after another, each at most {READ_CHUNK} frames so "
             "the host shows every image. ")
            + "If a result shows you the images, they are viewed: do not save or stage them, and go on to "
            "build_content_evidence.py after the last read. Only if a read returns a download link instead, save "
            "and fetch it the way the Skill says for read_research_data_artifacts, then open each image's path "
            "before any visual claim:")
        for item in reads:
            say("read: " + json.dumps(item, ensure_ascii=False))
    elif viewer_ok:
        say("No frames were taken: what is visible comes from the whole-video notes, which are reported "
            "observations, not frames.")
    elif current["mode"] == "transcript_export":
        say("A transcript export takes no frames. A finished transcript with no words (music only) is the answer: "
            "say the video has no speech to export, never that fetching it failed.")
    else:
        say("No frames arrived: keep the missing-visual-evidence limit and read the transcript and measurements only.")
    return 0


def resume(args: argparse.Namespace) -> int:
    current = state()
    if not current:
        raise ValueError("no observation was started in this run; run observe_video.py without --placed first")
    if current.get("done"):
        say("This observation is already complete; build the evidence with the arguments printed before.")
        return 0
    awaiting = current.get("awaiting") or []
    for entry in awaiting:
        if entry["tool"] in {START_TOOL, POLL_TOOL}:
            read_viewer(current, Path(entry["file"]), entry["tool"])
    if any(entry["tool"] == MEDIA_TOOL for entry in awaiting):
        collect_media.take_saved(args.result_id)
        media_state = collect_media.state()
        media_state["rounds"] = int(media_state.get("rounds") or 0) + 1
        collect_media.save_state(media_state)
    handed_at = current.get("handed_at")
    current["awaiting"] = []
    save_state(current)

    viewer = current["viewer"]
    # A finished result whose download must be asked for again is read again whatever the time: those readings are
    # bounded by MAX_REDELIVERIES.
    viewer_waiting = bool(viewer.get("active") and not viewer.get("done")
                          and (viewer.get("redeliver")
                               or (seconds_since(viewer.get("started_at")) < VIEWER_BUDGET_S
                                   and int(viewer.get("polls") or 0) < MAX_POLLS)))
    media_waiting = False
    if current["media"].get("active") and not current["media"].get("done"):
        media_state = collect_media.state()
        pending = media_pending(current)
        media_waiting = bool(pending and collect_media.waited_s(media_state) < collect_media.WAIT_BUDGET_S
                             and int(media_state.get("rounds") or 0) < collect_media.MAX_ROUNDS)
        if not media_waiting:
            current["media"]["done"] = True
    start_viewer = False
    retry = viewer.pop("legacy_retry", None)
    if retry == START_TOOL:
        start_viewer = True
    if current.get("viewer_deferred"):
        verdict, code = viewer_gate(current, media_in_flight=media_waiting)
        if verdict == "start":
            activate_viewer(current)
            start_viewer = True
        elif verdict == "wait" and not media_waiting:
            return duration_round(current, "")
        elif verdict == "refuse":
            refuse_viewer(current, code)
        save_state(current)
    if start_viewer:
        note = ("This server does not take wait_s / delivery yet: starting the viewing with the original arguments."
                if retry == START_TOOL else
                f"The video runs {current['duration_s']:g}s, within the whole-video limit: starting the viewing")
        hand_over_calls(current, start_viewer=True, poll_viewer=False, media=media_waiting,
                        note=note + (" The media jobs are still running." if media_waiting else ""))
        return 0
    if viewer_waiting and not media_waiting and not viewer.get("redeliver") and not retry:
        # Nothing else is running and the tool came back sooner than the interval (it did not wait): wait the rest
        # here rather than spend a model turn on a reading that comes back running.
        remaining = POLL_INTERVAL_S - seconds_since(handed_at)
        remaining = min(remaining, VIEWER_BUDGET_S - seconds_since(viewer.get("started_at")), args.poll_sleep_s)
        if remaining > 0:
            time.sleep(remaining)
    save_state(current)
    if viewer_waiting or media_waiting:
        parts = []
        if viewer_waiting:
            parts.append("the whole-video result's download could not be used; reading it again"
                         if viewer.get("redeliver") else
                         "reading the whole-video analysis again with its original arguments" if retry else
                         f"the whole-video analysis is {viewer.get('status') or 'starting'}")
        if media_waiting:
            parts.append(f"{media_pending(current)} media job(s) are still running")
        hand_over_calls(current, start_viewer=False, poll_viewer=viewer_waiting and bool(viewer.get("analysis_id")),
                        media=media_waiting, note="Still running: " + "; ".join(parts) + ". Keep waiting.")
        return 0
    return settle(current)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the original public video url, or kabo-file:<id>")
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--duration-s", type=float, help="the video's duration, when already known")
    parser.add_argument("--placed", action="store_true")
    parser.add_argument("--id", dest="result_id", help="the result id of the last collect_video_media call")
    parser.add_argument("--observe-source", choices=observation_order.PUBLIC_SOURCES,
                        help="test and bake-off only: force one observation source")
    parser.add_argument("--poll-sleep-s", type=float, default=POLL_INTERVAL_S, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    collect_media.bind_run_to_cwd()
    try:
        static_host.run_dir()
        if args.placed:
            return resume(args)
        current = state()
        if current and not current.get("done"):
            say("This observation was already started; make the calls printed earlier, or run with --placed.")
            return 0
        return start(args)
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as error:
        say(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
