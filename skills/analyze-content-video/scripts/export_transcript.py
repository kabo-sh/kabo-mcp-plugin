#!/usr/bin/env python3
"""Write the transcript the evidence already carries out as files a creator can open.

The words are fetched, read and cited by the analysis, then thrown away. A run leaves behind a
verdict about the video and nothing the creator can hand to an editor, paste into a description
or translate. This writes the two formats that are actually asked for: a plain `.txt`, and a
`.srt` when the evidence carries timing.

The refusals are the load-bearing part.

A subtitle file needs an end for every cue and the evidence carries only `start_s`, so each end is
read off the following cue. That is exact -- it is where the next line begins, not a guess about
how long this one was spoken. The final cue has no follower, and that is the single place a timing
could be invented: it is taken from the probed media duration when there is one, from the
platform-declared duration when there is not, and only then from the median gap of the cues before
it. Which of the three was used is recorded in the summary every time, because "derived" and
"observed" are different claims about the same number.

Where there is no timing at all -- the Instagram transcript path returns plain text with no cues --
no `.srt` is written and the summary says why. A subtitle file with invented timings looks correct
in a player and is wrong everywhere it matters: it desynchronises silently, and a creator who
uploads one has published something they cannot tell is broken.

An empty file is never written. A transcript that did not arrive is a refusal with the status that
caused it, not a zero-byte `.txt` that reads as "this video had nothing to say".

    python3 export_transcript.py <content_evidence.json> <out_dir> [--stem transcript]
                                 [--formats txt,srt] [--summary FILE]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


# The last cue's end, when the evidence carries no duration at all, falls back to the typical gap
# between the cues before it. One cue has no gaps to take a median of, so that case has no
# derivation left and the srt is refused rather than closed on a number nobody measured.
MIN_CUE_SECONDS = 0.001


def transcript_of(evidence: dict) -> dict:
    return evidence.get("transcript") or {}


def media_duration(evidence: dict) -> tuple[float | None, str]:
    """The best end for the final cue, and which of the three sources it came from."""
    media = evidence.get("media") or {}
    probed = media.get("duration_s")
    if isinstance(probed, (int, float)) and probed > 0:
        return float(probed), media.get("duration_source") or "media_duration_s"
    declared = (media.get("declared") or {}).get("duration_s")
    if isinstance(declared, (int, float)) and declared > 0:
        return float(declared), "platform_declared"
    return None, "unavailable"


def normalised_cues(transcript: dict) -> list[dict]:
    """Cues in playing order, with same-start cues joined.

    Rolling captions repeat a start second across consecutive fragments. Left alone those become
    zero-length subtitle entries, which players either drop or flash for a single frame; joined,
    they are the one line that was actually on screen at that second.
    """
    raw = transcript.get("cues") or []
    usable = [
        {"start_s": float(cue["start_s"]), "text": str(cue["text"]).strip()}
        for cue in raw
        if isinstance(cue, dict)
        and isinstance(cue.get("start_s"), (int, float))
        and str(cue.get("text") or "").strip()
    ]
    usable.sort(key=lambda cue: cue["start_s"])
    merged: list[dict] = []
    for cue in usable:
        if merged and merged[-1]["start_s"] == cue["start_s"]:
            merged[-1]["text"] = f"{merged[-1]['text']} {cue['text']}"
        else:
            merged.append(dict(cue))
    return merged


def final_end(cues: list[dict], duration: float | None, source: str) -> tuple[float | None, str]:
    """Where the last cue stops, and on what basis."""
    last = cues[-1]["start_s"]
    if duration is not None and duration > last:
        return duration, f"observed:{source}"
    gaps = [
        cues[index + 1]["start_s"] - cues[index]["start_s"]
        for index in range(len(cues) - 1)
        if cues[index + 1]["start_s"] > cues[index]["start_s"]
    ]
    if gaps:
        return last + statistics.median(gaps), "derived:median_cue_gap"
    return None, "unavailable"


def spans(cues: list[dict], duration: float | None, source: str) -> tuple[list[dict], str]:
    """Each cue as start, end and text. Ends come from the next cue; only the last is derived."""
    end_s, basis = final_end(cues, duration, source)
    if end_s is None:
        return [], basis
    out = []
    for index, cue in enumerate(cues):
        stop = cues[index + 1]["start_s"] if index + 1 < len(cues) else end_s
        out.append({
            "start_s": cue["start_s"],
            "end_s": max(stop, cue["start_s"] + MIN_CUE_SECONDS),
            "text": cue["text"],
        })
    return out, basis


def srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_srt(entries: list[dict]) -> str:
    blocks = [
        f"{index}\n{srt_timestamp(entry['start_s'])} --> {srt_timestamp(entry['end_s'])}\n"
        f"{entry['text']}"
        for index, entry in enumerate(entries, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def render_txt(transcript: dict, cues: list[dict]) -> str:
    """One cue per line, or the untimed text exactly as it was carried.

    Flattening cues into a paragraph loses where each line began, which is the only structure a
    timed transcript has once the timestamps are gone.
    """
    if cues:
        return "\n".join(cue["text"] for cue in cues) + "\n"
    return (transcript.get("plain_text") or "").strip() + "\n"


def export(evidence: dict, out_dir: Path, stem: str, formats: set[str]) -> dict:
    transcript = transcript_of(evidence)
    status = transcript.get("status")
    summary: dict = {
        "evidence_ref": evidence.get("evidence_id"),
        "transcript_status": status,
        "granularity": transcript.get("granularity"),
        "language": transcript.get("language"),
        "written": [],
        "refused": [],
    }

    if status != "available":
        summary["refused"] = [
            {"format": fmt, "reason": f"transcript_status:{status}",
             "detail": transcript.get("status_basis")}
            for fmt in sorted(formats)
        ]
        return summary

    cues = normalised_cues(transcript)
    plain = (transcript.get("plain_text") or "").strip()
    if not cues and not plain:
        # SKILL.md states this case: `available` with neither track is an unavailable transcript.
        summary["refused"] = [
            {"format": fmt, "reason": "no_text_in_evidence",
             "detail": "status is available but neither cues nor plain_text carried any text"}
            for fmt in sorted(formats)
        ]
        return summary

    summary["cue_count"] = len(cues)
    out_dir.mkdir(parents=True, exist_ok=True)

    if "txt" in formats:
        path = out_dir / f"{stem}.txt"
        body = render_txt(transcript, cues)
        path.write_text(body, encoding="utf-8")
        summary["written"].append({
            "format": "txt", "path": path.name, "characters": len(body),
            "source": "cues" if cues else "plain_text",
        })

    if "srt" in formats:
        if not cues:
            summary["refused"].append({
                "format": "srt", "reason": "no_timing_in_evidence",
                "detail": "this transcript path returns plain text only; timings are not invented",
            })
        else:
            duration, source = media_duration(evidence)
            entries, basis = spans(cues, duration, source)
            if not entries:
                summary["refused"].append({
                    "format": "srt", "reason": "final_cue_end_unavailable",
                    "detail": "no media duration and too few cues to derive one",
                })
            else:
                path = out_dir / f"{stem}.srt"
                path.write_text(render_srt(entries), encoding="utf-8")
                summary["written"].append({
                    "format": "srt", "path": path.name, "entries": len(entries),
                    "final_cue_end_basis": basis,
                })

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--stem", default="transcript",
                        help="base name for the written files (default: transcript)")
    parser.add_argument("--formats", default="txt,srt",
                        help="comma-separated subset of txt,srt (default: both)")
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args()

    formats = {part.strip().lower() for part in args.formats.split(",") if part.strip()}
    unknown = formats - {"txt", "srt"}
    if unknown:
        print(f"ERROR: unknown format {sorted(unknown)}", file=sys.stderr)
        return 2

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    summary = export(evidence, args.out_dir, args.stem, formats)

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["written"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
