"""Derive the report's sampling facts; extraction and citation never prove pixel viewing."""
from __future__ import annotations

import math
from typing import Any


def record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def number(value: Any, field: str, *, positive: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f"cannot derive data_note: {field} is unknown or invalid")
    return float(value)


def measurement_basis(evidence: dict, analysis: dict, view: dict) -> dict:
    """Count existing frame records and transitive card citations, without a viewing ledger."""
    platform = {"instagram": "Instagram video", "youtube": "YouTube video", "tiktok": "TikTok video"}.get(
        record(evidence.get("content_ref")).get("platform"))
    local = (record(evidence.get("media")).get("duration_source") == "local_probe"
             or any(record(step).get("step") == "local_extraction" for step in evidence.get("acquisition") or []))
    if not local and platform is None:
        raise ValueError("cannot derive data_note: the video source is not known")
    facts: dict = {"source": "Local video file" if local else platform, "viewing": "unverified"}
    frames = record(evidence.get("frames"))
    frame_ids = set()
    status = frames.get("status")
    if status == "available" and frames.get("origin") == "extracted_frames":
        items = frames.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("cannot derive data_note: the extracted-frame sample is missing")
        for item in items:
            item = record(item)
            identifier = item.get("frame_id")
            if not isinstance(identifier, str) or not identifier.strip() or identifier in frame_ids:
                raise ValueError("cannot derive data_note: frame IDs are missing or ambiguous")
            number(item.get("t_seconds"), "frame timestamp")
            frame_ids.add(identifier)
        facts.update(frame_kind="extracted", extracted_frames=len(frame_ids))
        plan = record(frames.get("sampling_plan"))
        count = plan.get("frames")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count != len(frame_ids)):
            raise ValueError("cannot derive data_note: sampling-plan frame count disagrees with frame records")
        dense = plan.get("hook_dense_window_s")
        interval = plan.get("hook_interval_s")
        if dense is not None or interval is not None:
            number(dense, "dense sampling window")
            number(interval, "dense sampling interval", positive=True)
        body = plan.get("body_interval_s")
        if body is not None or plan.get("body_degraded") is True:
            number(body, "reduced sampling interval", positive=True)
        # The plan and t_seconds may both be nominal extraction requests. Neither
        # confirms actual decoded timestamps, so no spacing enters measured facts.
    elif status == "available" and frames.get("origin") == "model_observation":
        if not frames.get("observations"):
            raise ValueError("cannot derive data_note: the reported visual descriptions are missing")
        facts["frame_kind"] = "descriptions"
    elif status in ("unavailable", "not_attempted"):
        facts["frame_kind"] = status
    else:
        raise ValueError("cannot derive data_note: the frame provenance is not known")

    observations = {}
    for observation in analysis.get("observations") or []:
        observation = record(observation)
        key = observation.get("observation_id")
        if not isinstance(key, str) or not key.strip() or key in observations:
            raise ValueError("cannot derive data_note: observation IDs are ambiguous")
        observations[key] = observation
    cited = set()
    for card in view.get("cards") or []:
        for ref in record(card).get("evidence_refs") or []:
            if isinstance(ref, str) and ref.startswith("observations."):
                key = ref[len("observations."):]
                if key not in observations:
                    raise ValueError(f"cannot derive data_note: unknown observation {key}")
                cited.update(ref for ref in observations[key].get("evidence_refs") or [] if ref in frame_ids)
            elif isinstance(ref, str) and ref in frame_ids:
                cited.add(ref)
    facts["cited_frame_refs"] = len(cited)

    transcript = record(evidence.get("transcript"))
    if transcript.get("status") == "available":
        label = {"platform_captions": "platform captions", "provider_transcript": "external transcript",
                 "speech_recognition": "machine transcript (wording unverified)",
                 "creator_supplied": "creator-supplied transcript (not checked against audio)"}.get(transcript.get("origin"))
        cues = transcript.get("cues") or []
        if not cues and not str(transcript.get("plain_text") or "").strip():
            raise ValueError("cannot derive data_note: available transcript contains no text")
        if cues:
            for cue in cues:
                cue = record(cue)
                number(cue.get("start_s"), "caption timestamp")
                if not isinstance(cue.get("text"), str) or not cue["text"].strip():
                    raise ValueError("cannot derive data_note: caption text is missing")
            facts["caption_cues"] = len(cues)
    else:
        label = {"no_speech_detected": "no speech detected", "no_audio_track": "no audio track",
                 "no_platform_captions": "platform captions unavailable", "provider_error": "transcript unavailable",
                 "not_attempted": "transcript not retrieved"}.get(transcript.get("status"))
    if label is None:
        raise ValueError("cannot derive data_note: the transcript provenance is not known")
    facts["transcript"] = label
    owner = record(evidence.get("owner_metrics")).get("status")
    if owner not in ("available", "partial", "unavailable"):
        raise ValueError("cannot derive data_note: owner-metric availability is not known")
    facts["owner_metrics"] = owner
    return facts


def measurement_note(facts: dict) -> str:
    """One English measurement line, with fixed rounding and no claim about actual viewing."""
    kind = facts["frame_kind"]
    frames = {"descriptions": "reported visual descriptions, not inspected pixels",
              "unavailable": "frames unavailable", "not_attempted": "frames not sampled"}.get(kind)
    if kind == "extracted":
        frames = f"{facts['extracted_frames']} extracted frames"
    parts = [facts["source"], frames, f"{facts['cited_frame_refs']} cited frame refs"]
    transcript = facts["transcript"]
    if "caption_cues" in facts:
        count = facts["caption_cues"]
        transcript += f" ({count} cue{'s' if count != 1 else ''})"
    parts += [transcript, f"owner metrics {facts['owner_metrics']}", "viewing unverified"]
    note = "; ".join(parts) + "."
    if len(note) > 240:
        raise ValueError("cannot derive data_note within the source-note length limit")
    return note


def canonical_note(evidence: dict, analysis: dict, view: dict) -> str:
    return measurement_note(measurement_basis(evidence, analysis, view))
