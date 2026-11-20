#!/usr/bin/env python3
"""Assemble the one analysis brief the model reads before it writes a judgment.

    python3 prepare_analysis.py --run <run dir> --mode <diagnosis|content_read|craft_teardown>
        --question-file <file with the creator's words> [--focus id1,id2]

Reads `analysis/content_evidence.json` (whatever observation source produced it), runs the existing
deterministic steps, re-checks the method cards chosen before the fetch against the evidence that arrived (the
topic cards in `analysis/method.json`, or `--focus` when given), and writes `analysis/method.json` and
`analysis/brief.md` with seven fixed sections:

    ## 1. Creator question / ## 2. Mode / ## 3. Evidence index / ## 4. Deterministic results /
    ## 5. Method / ## 6. Judgment rules / ## 7. Output contract

Sections 1, 2, 6 and 7 depend only on the mode, the question and the focus, never on which source observed the
video. Section 5 depends on the cards selected: a requested topic card the evidence cannot support is skipped
(section 3 names the skip), so section 5 is byte-identical across sources whenever the same cards are selected.
Everything else source-dependent lives in sections 3 and 4. This is the only place a brief is assembled.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import acv_timing  # noqa: E402
import observation_order  # noqa: E402
import select_method  # noqa: E402
import transcript_checks  # noqa: E402

BRIEF_TEXTS = SKILL / "references" / "analysis-brief.md"
BRIEF_SECTION = re.compile(r"^<!-- section: ([a-z-]+) -->\n", re.M)


def brief_text(name: str) -> str:
    """One section of `references/analysis-brief.md`: from its marker line to the next marker or the end."""
    text = BRIEF_TEXTS.read_text(encoding="utf-8")
    marks = list(BRIEF_SECTION.finditer(text))
    for index, mark in enumerate(marks):
        if mark.group(1) == name:
            return text[mark.end():marks[index + 1].start() if index + 1 < len(marks) else len(text)]
    raise KeyError(f"analysis-brief.md has no section {name!r}")


MODES = ("diagnosis", "content_read", "craft_teardown")
MODE_TEXT = {
    "diagnosis": "Diagnosis: how this post did and what to keep, recut or replace next, from its own timestamped "
                 "evidence. It ends in the validated report `report/VIDEO_DIAGNOSIS.md`.",
    "content_read": "Content read: what the video shows, says and is about, answered in the chat from the "
                    "evidence. It is not a diagnosis and writes no report.",
    "craft_teardown": "Craft teardown: how the video was made, in steps one person can follow, answered in "
                      "`report/craft-teardown.md` and shaped by the creator's question.",
}
OUTPUT_SECTION = {"diagnosis": "output-diagnosis", "content_read": "output-content-read",
                  "craft_teardown": "output-craft-teardown"}
# A kind of request that adds its own instruction to section 7 (select_method.py records it as `ask`).
ASK_SECTION = {"identify_track": "output-identify-track"}
ASK_TEXT = {"identify_track": "Find the track: which song or sound the video uses, named only from the metadata, "
                              "on-screen text and speech. No sound card and no whole-video viewing."}
NEXT = {
    "diagnosis": "write analysis/video_judgment.json as its section 7 says",
    "content_read": "answer the creator in the chat as its section 7 says",
    "craft_teardown": "write report/craft-teardown.md as its section 7 says",
}
# The measured signals worth a line in the index; the rest of media.probed stays in the evidence file.
PROBED_SUMMARY = ("shots", "silence", "freeze", "framing")
# A sound cue in a transcript: a bracketed tag such as [Music] (in any language) or a music note.
SOUND_MARKER = re.compile(r"\[[^\[\]\n]{1,40}\]|[\u266a\u266b\u266c]")
# Whole-video note aspects that are about what was heard ("Audio Integration", "Audio Quality", "Voice", ...).
SOUND_ASPECT = re.compile(r"audio|sound|music|voice|vocal|speech|narrat|song|\bmix|sfx", re.IGNORECASE)
# How far from a note's start a measured cut is shown beside it: the viewer's times are its own estimates.
NEAR_CUT_S = 2.0
REASON_TEXT = {"sound_marker_only": "sound marker only", "generic_line": "generic line, likely invented over music",
               "past_end": "starts after the video ends"}
STOP_TEXT = ("Nothing was observed: no frames, no transcript words, no whole-video notes and no images arrived ("
             + observation_order.SOURCE_UNAVAILABLE_MARK + ") Follow *Stops and gaps* in the Skill: send the creator "
             "this statement, in their language, and nothing more, then stop: "
             + observation_order.SOURCE_UNAVAILABLE_REPLY + " Do not write a judgment, a report or an answer about "
             "the video's content.")
LATE_STOP_TEXT = ("Nothing to look at and no post metadata arrived before the observation deadline. Tell the creator "
                  "plainly, in their language, that the video's frames and words did not arrive in time (the "
                  "platform was slow to deliver it), offer to try again later or to analyse the video file, and stop. "
                  "Do not call it a failure and do not describe the video's content.")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def seconds(value: Any) -> str:
    return f"{float(value):g}s" if isinstance(value, (int, float)) else "time unknown"


def one_line(text: Any) -> str:
    return " ".join(str(text).split())


def run_script(*argv: str, cwd: Path) -> None:
    done = subprocess.run([sys.executable, "-B", str(SCRIPTS / argv[0]), *argv[1:]], cwd=cwd,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{argv[0]} failed: " + ((done.stdout + done.stderr).strip()[-600:] or "no output"))


def deterministic(run: Path, mode: str, evidence: dict[str, Any], request: dict[str, Any]) -> list[str]:
    """Run the existing deterministic steps for the mode and return section 4's lines."""
    if mode != "diagnosis":
        return ["No deterministic step runs for this mode. Measured signals are in section 3."]
    subject = (request.get("source") or {}).get("subject_state")
    if subject not in {"own_unpublished", "own_published", "third_party", "unknown"}:
        raise ValueError("the request names no subject_state; write analysis/video-analysis-request.json first")
    run_script("compute_deterministic.py", "analysis/content_evidence.json", "--subject-state", subject,
               "--output", "analysis/deterministic.json", cwd=run)
    lines = ["The model narrates these blocks; it never decides or retypes them.", "",
             "### Stage verdicts (`analysis/deterministic.json`)", "", "```json",
             json.dumps(load(run / "analysis/deterministic.json"), ensure_ascii=False, indent=1), "```", ""]
    try:
        run_script("compute_promise_payoff.py", "analysis/content_evidence.json",
                   "--output", "analysis/promise_payoff.json", cwd=run)
        lines += ["### Promise and payoff (`analysis/promise_payoff.json`)", "",
                  "It anchors the promise; the payoff is your judgment. To measure the gap, name the cue that pays "
                  "it off: `cd '<run directory>' && python3 <skill directory>/scripts/compute_promise_payoff.py analysis/content_evidence.json "
                  "--payoff-cue <i> --output analysis/promise_payoff.json`; it rewrites this file, so the gap it "
                  "measures may be cited. Never report a distance it did not compute.", "", "```json",
                  json.dumps(load(run / "analysis/promise_payoff.json"), ensure_ascii=False, indent=1), "```", ""]
    except RuntimeError as error:
        lines += ["### Promise and payoff", "", f"Not computed: {one_line(error)[:300]}", ""]
    platform = (evidence.get("content_ref") or {}).get("platform")
    try:
        import prepare_video_hook
        catalog = prepare_video_hook.build(platform)
        lines += ["### Short-video opening patterns (method, not evidence)", "",
                  "For a change to a short video's opening only. Pick one to three whose material the creator has "
                  "and read them in full: `cd '<run directory>' && python3 <skill directory>/scripts/prepare_video_hook.py "
                  f"--platform {platform} --pattern-id <id> [--pattern-id <id>] --output analysis/hook-patterns.json`. "
                  "Write each new opening as one decision: first frame, first sound and the question they raise, "
                  "plus the first words when spoken. Pattern ids and names stay internal.", ""]
        lines += [f"- `{pattern['id']}` {pattern['name']} — needs: {', '.join(pattern['material_requirements'])}"
                  for pattern in catalog["pattern_candidates"]]
        lines.append("")
    except (ValueError, KeyError, OSError) as error:
        lines += ["### Short-video opening patterns", "", f"Unavailable: {one_line(error)}", ""]
    return lines


def late_lines(evidence: dict[str, Any]) -> list[str]:
    """The limitation lines the observation deadline left: what did not arrive in time."""
    return [str(text) for text in evidence.get("limitations") or []
            if str(text).startswith(observation_order.DEADLINE_MARK)]


def gone(evidence: dict[str, Any]) -> bool:
    """Whether the evidence carries the one marker for a video the backend could not fetch at all."""
    return observation_order.SOURCE_UNAVAILABLE_MARK in (evidence.get("limitations") or [])


def observed_nothing(evidence: dict[str, Any]) -> bool:
    """True when no source brought anything to analyse: no frames, no transcript words, no notes, no images.

    When the observation deadline stopped the fetch, the post's own metadata (title, caption, public counts) is
    something to analyse: the run goes on from it and says plainly what did not arrive in time."""
    if (late_lines(evidence) and not gone(evidence)
            and (evidence.get("content_metadata") or {}).get("status") == "available"):
        return False
    if (evidence.get("frames") or {}).get("status") == "available":
        return False
    transcript = evidence.get("transcript") or {}
    if transcript.get("status") == "available" and (
            transcript.get("plain_text") or transcript_checks.worded_cues(transcript.get("cues") or [])):
        return False
    if (evidence.get("viewer_observations") or {}).get("items"):
        return False
    return not any(item.get("status") == "available" for item in (evidence.get("images") or {}).get("items") or []
                   if isinstance(item, dict))


def note_flags(note: dict[str, Any], duration: Any, cuts: list[float]) -> str:
    """What to check before citing a whole-video note: a span past the end, a measured cut near its start."""
    flags = []
    start, end = note["start_ms"] / 1000, note["end_ms"] / 1000
    if isinstance(duration, (int, float)) and end > duration + transcript_checks.END_TOLERANCE_S:
        flags.append(f"runs past the end of the {duration:g}s video")
    near = [cut for cut in cuts if abs(cut - start) <= NEAR_CUT_S and abs(cut - start) > 0.5]
    if near:
        closest = min(near, key=lambda cut: abs(cut - start))
        flags.append(f"measured cut at {closest:g}s, {round(abs(closest - start), 2):g}s "
                     + ("after" if closest > start else "before") + " the note's start")
    return f" ({'; '.join(flags)})" if flags else ""


def transcript_lines(transcript: dict[str, Any]) -> list[str]:
    """Each transcript source this run had and every disagreement among them."""
    lines = []
    names = {"fetched": "Fetched transcript", "whole_video_viewer": "Whole-video viewer's transcript",
             "subtitle_file": "Subtitle file", "local_speech_recognition": "Local speech recognition"}
    for item in transcript.get("sources") or []:
        facts = [item.get("status"), f"{item.get('cue_count')} cues"]
        if item.get("origin"):
            facts.append(f"origin {item['origin']}")
        if item.get("language"):
            facts.append(f"declared {item['language']}")
        if item.get("detected_language"):
            facts.append(f"reads as {item['detected_language']}")
        lines.append(f"- {names.get(item.get('source'), item.get('source'))} ({'kept' if item.get('used') else 'not kept'}): "
                     + ", ".join(str(fact) for fact in facts if fact)
                     + (f" — \"{item['excerpt']}\"" if item.get("excerpt") else ""))
    if lines:
        lines.append("- On-screen text in the frames: yours to read. Compare it with the kept transcript before "
                     "quoting a line; where they disagree, the frame shows what the viewer reads.")
    lines += [f"- Conflict: {one_line(text)}" for text in transcript.get("conflicts") or []]
    return lines


def evidence_index(evidence: dict[str, Any], source: str | None, method: dict[str, Any],
                   request: dict[str, Any] | None = None) -> list[str]:
    lines = [f"Observation source: {source or 'unknown'}. Evidence `{evidence.get('evidence_id')}`. The complete "
             "list of legal references is `analysis/content_evidence.references.json`; the values are in "
             "`analysis/content_evidence.json`.", ""]
    late = late_lines(evidence)
    if late:
        lines += ["### Did not arrive in time", ""] + [f"- {one_line(text)}" for text in late] + [
            "- Say this plainly in the first lines of what the creator reads (the summary, or the answer's opening): "
            "what did not arrive in time, in everyday words. It is not a failure and not a missing feature of the "
            "video; never describe what did not arrive.", ""]
    for skipped in method.get("skipped") or []:
        lines.append(f"Method card `{skipped['id']}` was skipped: {skipped['reason']}.")
    if method.get("skipped"):
        lines.append("")
    ref = evidence.get("content_ref") or {}
    content = f"`{ref['content_id']}`" if ref.get("content_id") else "id unresolved (short link)"
    lines += ["### Post", "", f"- platform {ref.get('platform')}, content {content}, format "
              f"{ref.get('format')}, published {ref.get('published_at')}"]
    media = evidence.get("media") or {}
    if media.get("duration_s") is not None:
        lines.append(f"- `media.duration_s` {media['duration_s']}")
    if ((request or {}).get("source") or {}).get("acquisition") == "local_file":
        lines.append("- This is a file on this machine: it carries no caption, view counts or comments. When the "
                     "creator asks how the video performed, why it flopped or took off, ask once for the published "
                     "link (a link run reads its counts and caption); until then answer from the file and name "
                     "those numbers as missing.")
    metadata = evidence.get("content_metadata") or {}
    lines.append(f"- `content_metadata` {metadata.get('status')}")
    for field in ("title", "caption"):
        if isinstance(metadata.get(field), str) and metadata[field].strip():
            lines.append(f"- `content_metadata.{field}`: {one_line(metadata[field])}")
    if metadata.get("tags"):
        lines.append(f"- tags: {', '.join(map(str, metadata['tags']))}")
    for metric in evidence.get("public_metrics") or []:
        lines.append(f"- `public_metrics.{metric['native_name']}` = {metric.get('value')}")
    for item in evidence.get("derived") or []:
        lines.append(f"- `derived.{item['name']}` = {item.get('value')}")
    lines += [""] + sound_lines(evidence)

    frames = evidence.get("frames") or {}
    items = frames.get("items") or []
    lines += [f"### Frames ({frames.get('status')}, origin {frames.get('origin') or 'none'}, {len(items)})", ""]
    plan = frames.get("sampling_plan") or {}
    if plan.get("hook_window_s") is not None:
        body = plan.get("body_interval_s")
        windows = [w for w in plan.get("dense_windows") or [] if isinstance(w, dict)]
        spans = ", ".join(f"{w.get('start_s')}–{w.get('end_s')}s every {w.get('interval_s')}s" for w in windows)
        lines.append(f"Planned sampling (not decoded spacing): hook window {plan.get('hook_window_s')}s, "
                     + (f"body interval {body}s" if body else
                        f"no body grid: the overview shows every {plan.get('overview_stride_s')}s, with "
                        f"{plan.get('change_frames')} change and {plan.get('anchor_frames')} anchor frame(s)"
                        if plan.get("overview") else "no body grid (dense windows cover the video)")
                     + (f", dense windows {spans}" if spans else "")
                     + f"{', body degraded' if plan.get('body_degraded') else ''}.")
    overview = frames.get("overview") or {}
    if overview.get("sheets"):
        # The overview plan (acv_timing.py): every second at low resolution first, then the chosen frames.
        lines.append(f"Overview: every {overview.get('stride_s')}s of the whole video at low resolution, "
                     f"{overview.get('columns')} tiles a row and {overview.get('rows')} rows a sheet, in time order "
                     "left to right and top to bottom (tile n of a sheet is from + n x the stride). It is the only "
                     "view of the seconds between the frames below; quote on-screen text from a frame, not from it."
                     + (f" It reaches {overview['read_until_s']:g}s only." if overview.get("read_until_s") else ""))
        lines += [f"- overview `{sheet.get('sheet_id')}` {seconds(sheet.get('from_s'))}–{seconds(sheet.get('to_s'))}"
                  + (f" `{sheet['path']}`" if sheet.get("path") else "") for sheet in overview["sheets"]]
        lines.append("High-resolution frames, each with why it was chosen (change = the picture or the on-screen "
                     "text changed against the second before; anchor = the middle of a gap over 10s):")
    lines += [f"- `{item['frame_id']}` {seconds(item.get('t_seconds'))}"
              + (f" {item['source']}" if overview.get("sheets") and item.get("source") else "")
              + (f" ({item['reason']})" if item.get("reason") else "")
              + (f" `{item['path']}`" if item.get("path") else "")
              for item in items]
    if items:
        lines.append("Open the overview sheets, then the frames (the read the observation step printed, or these "
                     "paths) before any visual claim." if overview.get("sheets") else
                     "Open the frames (the read the observation step printed, or these paths) before any visual claim.")
    for observation in frames.get("observations") or []:
        lines.append(f"- reported: {one_line(json.dumps(observation, ensure_ascii=False))}")
    images = evidence.get("images") or {}
    for item in images.get("items") or []:
        lines.append(f"- image `{item.get('image_id')}` position {item.get('index')} {item.get('status')}"
                     + (f" `{item['path']}`" if item.get("path") else ""))
    lines.append("")

    transcript = evidence.get("transcript") or {}
    cues = transcript.get("cues") or []
    lines += [f"### Transcript ({transcript.get('status')}, origin {transcript.get('origin')}, "
              f"{len(cues)} cues)", "", f"Basis: {one_line(transcript.get('status_basis'))}"]
    lines += transcript_lines(transcript)
    suspect = {item["index"]: item["reason"] for item in transcript.get("suspect_cues") or []
               if isinstance(item, dict) and isinstance(item.get("index"), int)}
    lines += [f"- `transcript.cue[{index}]` {seconds(cue.get('start_s'))}: {one_line(cue.get('text'))}"
              + (f" [no evidence of speech: {REASON_TEXT.get(suspect[index], suspect[index])}]"
                 if index in suspect else "")
              for index, cue in enumerate(cues)]
    if transcript.get("plain_text") and not cues:
        lines.append(f"- `transcript.plain_text` (untimed): {one_line(transcript['plain_text'])}")
    lines.append("")

    viewer = evidence.get("viewer_observations")
    if viewer is not None:
        notes = viewer.get("items") or []
        failure = viewer.get("failure") or {}
        lines += [f"### Whole-video notes ({viewer.get('status')}, {len(notes)})", ""]
        if failure:
            lines.append(f"Viewing failure: {failure.get('code')}.")
        if notes:
            lines.append("The times are the viewer's own estimates. Where a measured cut or a frame places a moment "
                         "differently, cite the cut or the frame's time, not the note's.")
        cuts = [float(cut) for cut in ((media.get("probed") or {}).get("shots") or {}).get("cuts_at_s") or []
                if isinstance(cut, (int, float))]
        lines += [f"- `{note['id']}` {note['start_ms'] / 1000:g}–{note['end_ms'] / 1000:g}s [{note['aspect']}]: "
                  f"{one_line(note['note'])}{note_flags(note, media.get('duration_s'), cuts)}" for note in notes]
        lines.append("")

    probed = media.get("probed") or {}
    if probed:
        lines += ["### Measurements (`media.probed.*`)", ""]
        for name in PROBED_SUMMARY:
            value = probed.get(name)
            if isinstance(value, dict):
                shown = {key: item for key, item in value.items() if key != "shots" or len(json.dumps(item)) < 4000}
                lines.append(f"- `media.probed.{name}`: {json.dumps(shown, ensure_ascii=False)}")
        others = sorted(set(probed) - set(PROBED_SUMMARY))
        if others:
            lines.append(f"- also measured, read from the evidence file: {', '.join(f'`media.probed.{n}`' for n in others)}")
        lines.append("")
    if evidence.get("limitations"):
        lines += ["### Limitations already recorded", ""]
        lines += [f"- {one_line(text)}" for text in evidence["limitations"]]
        lines.append("")
    return lines


def sound_lines(evidence: dict[str, Any]) -> list[str]:
    """What this run has for deciding whose words the transcript holds and whether the sound was analysed."""
    lines = ["### Sound", ""]
    attribution = evidence.get("audio_attribution")
    if attribution:
        lines.append(f"- `audio_attribution`: {json.dumps(attribution, ensure_ascii=False)}")
    else:
        lines.append("- `audio_attribution` unavailable: no source in this run declares whether the sound is "
                     "original or an existing track.")
    cues = (evidence.get("transcript") or {}).get("cues") or []
    marked = [(index, SOUND_MARKER.findall(str(cue.get("text") or ""))) for index, cue in enumerate(cues)]
    marked = [(index, found) for index, found in marked if found]
    if marked:
        lines.append("- Sound markers in the transcript: " + ", ".join(
            f"`transcript.cue[{index}]` {' '.join(dict.fromkeys(found))}" for index, found in marked))
    elif cues:
        lines.append("- No sound markers (such as [Music] or a music note) in the transcript cues.")
    media = evidence.get("media") or {}
    probed = media.get("probed") or {}
    if media.get("has_audio") is False or (evidence.get("transcript") or {}).get("status") == "no_audio_track":
        lines += ["- The file has no audio track: there is no music, voice or mix to analyse. Say that, instead of "
                  "judging the sound or calling it unmeasured.", ""]
        return lines
    measured = [name for name in ("loudness", "silence") if probed.get(name)]
    notes = [item for item in ((evidence.get("viewer_observations") or {}).get("items") or [])
             if isinstance(item, dict) and SOUND_ASPECT.search(str(item.get("aspect") or ""))]
    audio = media.get("audio") if isinstance(media.get("audio"), dict) else None
    if audio and audio.get("status") in ("completed", "completed_partial"):
        lines += audio_lines(audio)
    if measured or notes or audio:
        lines.append("- Music and mix evidence: " + ", ".join(
            [f"`media.probed.{name}`" for name in measured] + (["`media.audio`"] if audio else [])
            + [f"whole-video sound note `{item['id']}`" for item in notes]))
    else:
        lines.append("- Music and mix: neither measured nor heard in a whole-video note, so they were not analysed; "
                     "any transcript is heard words only.")
    lines.append("")
    return lines


def audio_lines(audio: dict[str, Any]) -> list[str]:
    """The local sound measurement: its findings (each a measurement that cleared its threshold) and the questions
    only listening can answer. State the measurement, then the inference; a listen-check is never a finding."""
    lines = [f"- Local sound measurement (`media.audio`, {audio.get('status')}): "
             + ", ".join(audio.get("measured") or [])
             + (f"; not measured: {', '.join(item.get('measure', '') for item in audio.get('skipped') or [])}"
                if audio.get("skipped") else "")
             + (f"; stopped early at {json.dumps(audio['measured_until_s'])}" if audio.get("measured_until_s") else "")]
    findings = [item for item in audio.get("findings") or [] if isinstance(item, dict)]
    if findings:
        lines.append("  Findings (measured, threshold cleared; cite `media.audio.findings[i]`):")
        lines += [f"  - `media.audio.findings[{index}]` [{item.get('confidence')}] {one_line(item.get('claim'))}"
                  for index, item in enumerate(findings)]
    else:
        lines.append("  No sound measure cleared its threshold: say nothing about the sound beyond the numbers.")
    checks = [item for item in audio.get("listen_check") or [] if isinstance(item, dict)]
    if checks:
        lines.append("  Listen-check, for the creator to hear; never a finding: "
                     + " | ".join(one_line(item.get("ask")) for item in checks))
    return lines


def nested(text: str) -> str:
    """Card and reference text nested under a brief section: its headings move down two levels, so a card's
    own `## 1.` can never be mistaken for one of the brief's seven sections. Fenced code is left alone."""
    out, fenced = [], False
    for line in text.rstrip().split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            line = "##" + line
        out.append(line)
    return "\n".join(out)


def method_section(method: dict[str, Any], library: Path, index: dict[str, Any]) -> list[str]:
    lines = []
    skipped = [item["id"] for item in method.get("skipped") or []]
    if method.get("default_only"):
        lines += ["No topic card was asked for: the base card alone gives the default analysis.", ""]
    elif skipped:
        lines += ["The requested topic card" + ("s " if len(skipped) > 1 else " ")
                  + ", ".join(f"`{item}`" for item in skipped)
                  + (" were" if len(skipped) > 1 else " was") + " skipped for missing evidence (see the skip notice "
                  "in section 3): answer that part of the question from the cards below and name the missing "
                  "evidence instead of applying the skipped method.", ""]
    for card in method["cards"]:
        text = select_method.card_text(library, index, card["id"]).lstrip()
        if text.startswith("# "):
            # The card's own title becomes the heading that names it.
            title, _, text = text.partition("\n")
            title = title[2:].strip()
        else:
            title = card["id"]
        lines += [f"### {title} (`{card['id']}`, {card['role']} card, version {card['version']})", "",
                  nested(text.strip()), ""]
    return lines


def output_section(mode: str, ask: str | None = None) -> list[str]:
    lines = [nested(brief_text(OUTPUT_SECTION[mode])), ""]
    if ask in ASK_SECTION:
        lines += [nested(brief_text(ASK_SECTION[ask])), ""]
    if mode == "diagnosis":
        done = subprocess.run([sys.executable, "-B", str(SCRIPTS / "compose_video_analysis.py"),
                               "--print-judgment-schema"], capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError("compose_video_analysis.py --print-judgment-schema failed")
        lines += ["```json", done.stdout.rstrip(), "```", ""]
    elif mode == "craft_teardown":
        text = (SKILL / "references" / "craft-teardown.md").read_text(encoding="utf-8")
        start = text.index("## What may not be claimed")
        end = text.find("## What this mode writes", start)
        lines += [nested(text[start:end if end > 0 else None]), ""]
    return lines


def brief(question: str, mode: str, focus: list[str], method: dict[str, Any], library: Path,
          index: dict[str, Any], evidence_lines: list[str], deterministic_lines: list[str],
          subject_state: str = "unknown") -> str:
    ask = method.get("ask")
    sections = [
        ("1. Creator question", [question.strip() or "(no words beyond the link: a default analysis)", ""]),
        ("2. Mode", [MODE_TEXT[mode], "", "Focus: " + (", ".join(f"`{item}`" for item in focus) if focus
                                                    else "none (default analysis)"), ""]
         + ([ASK_TEXT[ask], ""] if ask in ASK_TEXT else [])),
        ("3. Evidence index", [f"Whose video: `{subject_state}` (from `analysis/video-analysis-request.json`; "
                               "`unknown` and `third_party` get no source revisions and no owner metrics).", "",
                               *evidence_lines]),
        ("4. Deterministic results", deterministic_lines),
        ("5. Method", method_section(method, library, index)),
        ("6. Judgment rules", [nested(brief_text("judgment-rules")), ""]),
        ("7. Output contract", output_section(mode, ask)),
    ]
    out = ["# Analysis brief", "", "Read this whole before writing anything. It is the only analysis "
           "instruction for this run.", ""]
    for title, lines in sections:
        out += [f"## {title}", "", *lines]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--question-file", type=Path, required=True)
    parser.add_argument("--focus", help="zero to two topic card ids, comma-separated; by default the topic cards "
                        "select_method.py chose before the fetch (analysis/method.json)")
    parser.add_argument("--library", type=Path, default=select_method.LIBRARY, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    run = args.run.resolve()
    analysis = run / "analysis"
    started = acv_timing.now()
    try:
        evidence = load(analysis / "content_evidence.json")
        request = load(analysis / "video-analysis-request.json")
        question = args.question_file.read_text(encoding="utf-8")
        index = select_method.load_index(args.library)
        focus = select_method.parse_focus(args.focus)
        chosen = analysis / "method.json"
        earlier = load(chosen) if chosen.is_file() else {}
        if args.focus is None and earlier:
            # The cards chosen from the request before the fetch; this run checks them against the evidence.
            focus = select_method.requested_focus(earlier)
        if observed_nothing(evidence):
            stop = LATE_STOP_TEXT if late_lines(evidence) and not gone(evidence) else STOP_TEXT
            print(json.dumps({"status": "refused", "error": stop}, ensure_ascii=False))
            return 2
        ask = earlier.get("ask") if earlier.get("ask") in select_method.ASKS else None
        method = select_method.select(index, args.mode, focus, evidence, ask)
    except select_method.SelectionError as error:
        print(json.dumps({"status": "refused", "error": str(error)}, ensure_ascii=False))
        return 2
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    try:
        (analysis / "method.json").write_text(json.dumps(method, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        source = acv_timing.load(analysis).get("observation_source")
        text = brief(question, args.mode, focus, method, args.library, index,
                     evidence_index(evidence, source, method, request), deterministic(run, args.mode, evidence, request),
                     subject_state=str((request.get("source") or {}).get("subject_state") or "unknown"))
        (analysis / "brief.md").write_text(text, encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    acv_timing.append(analysis, "prepare", started)
    print(json.dumps({"status": "ready", "brief": "analysis/brief.md", "cards": [card["id"] for card in method["cards"]],
                      "skipped": method["skipped"]}, ensure_ascii=False))
    print(f"Read analysis/brief.md whole now, then {NEXT[args.mode]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
