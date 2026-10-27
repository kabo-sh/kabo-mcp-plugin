"""Bind model-authored point observations to literal per-video evidence.

Inventory membership is not proof of image viewing or of free-prose semantics.
Legacy inputs without the source marker retain their original contract.
"""
from __future__ import annotations

import math
from typing import Any

CONTRACT = "point-observations.v1"


class MissingPointObservation(ValueError):
    """An existing literal source point was pinned but not explicitly observed."""

    def __init__(self, path: str, pin: dict[str, Any], source_point: dict[str, Any],
                 registered: list[dict[str, Any]]) -> None:
        super().__init__("pin is not bound to a same-video point observation")
        self.issue = {"path": path, "pin": dict(pin), "source_point": source_point,
                      "registered_same_video_points": registered}


def finite_seconds(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def observations_seed(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind IDs only; never prefill quotes, frames or viewing claims."""
    return [{"content_id": row["content_id"], "cue_samples": [], "frame_samples": []}
            for row in source.get("watched", [])]


def _index(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        content_id = row.get("content_id")
        if not isinstance(content_id, str) or not content_id.strip() or content_id in result:
            raise ValueError(f"{label} needs unique nonblank content_ids")
        result[content_id] = row
    return result


def validate_observations(synthesis: dict[str, Any], evidence: dict[str, Any],
                          source: dict[str, Any] | None) -> dict[tuple[str, str, float], dict[str, Any]] | None:
    marker = (source or {}).get("observation_contract")
    evidence_marker = evidence.get("observation_contract")
    if evidence_marker is not None and evidence_marker != CONTRACT:
        raise ValueError("unsupported evidence observation_contract")
    if evidence_marker == CONTRACT and (source is None or marker != CONTRACT):
        raise ValueError("marked evidence requires its matching point-observations synthesis input")
    if marker is None:
        return None
    if marker != CONTRACT:
        raise ValueError("unsupported observation_contract")
    if source["analysis_id"] != evidence.get("analysis_id") or source["analysis_id"] != synthesis.get("analysis_id"):
        raise ValueError("point observations require matching source/evidence/synthesis analysis_id")
    watched = _index([row for row in evidence.get("items", []) if row.get("watched")], "watched evidence")
    carried = _index(source.get("watched", []), "synthesis input")
    rows = synthesis.get("video_observations")
    if not isinstance(rows, list):
        raise ValueError("point-observations input requires video_observations")
    observed = _index(rows, "video_observations")
    if set(watched) != set(carried) or set(watched) != set(observed):
        raise ValueError("video_observations must cover exactly the same watched content_ids")
    bound: dict[tuple[str, str, float], dict[str, Any]] = {}
    for content_id, row in observed.items():
        item = watched[content_id]
        cues = (item.get("transcript") or {}).get("cues") or []
        frames = (item.get("frames") or {}).get("items") or []
        selected_cues = carried[content_id].get("opening_cues", []) + carried[content_id].get("later_cues", [])
        if selected_cues and not row["cue_samples"]:
            raise ValueError("a video with selected timed cues requires at least one literal cue observation")
        for sample in row["cue_samples"]:
            start, end = sample["start_s"], sample["end_s"]
            if not finite_seconds(start) or (end is not None and (not finite_seconds(end) or end < start)):
                raise ValueError("cue sample must use finite ordered source seconds")
            matches = [cue for cue in cues if cue.get("start_s") == start and cue.get("text") == sample["quote"]
                       and cue.get("end_s") == end]
            if len(matches) != 1:
                raise ValueError("cue sample must match one same-video original quote/start/end")
            key = (content_id, "cue", float(start))
            if key in bound:
                raise ValueError("a pin cannot disambiguate multiple cue samples at the same start")
            bound[key] = sample
        for sample in row["frame_samples"]:
            start = sample["start_s"]
            if not sample["description"].strip():
                raise ValueError("frame sample requires a nonblank point description")
            if not finite_seconds(start) or not any(frame.get("t_seconds") == start for frame in frames):
                raise ValueError("frame sample timestamp is not in the same-video available inventory")
            key = (content_id, "frame", float(start))
            if key in bound:
                raise ValueError("duplicate frame sample")
            bound[key] = sample
    pins = [(f"{name}[{index}].pins[{point}]", pin)
            for name in ("repeated_strengths", "repeated_drags")
            for index, pattern in enumerate(synthesis.get(name, []))
            for point, pin in enumerate(pattern.get("pins", []))]
    pins += [(f"next_shoot.pins[{index}]", pin)
             for index, pin in enumerate((synthesis.get("next_shoot") or {}).get("pins", []))]
    missing: list[MissingPointObservation] = []
    for path, pin in pins:
        start = pin.get("start_s")
        if not finite_seconds(start) or (pin.get("content_id"), pin.get("kind"), float(start)) not in bound:
            # Only an exact, existing same-video source point is an authoring omission.
            # Unknown IDs, kinds or invented seconds retain the original fatal error.
            item = watched.get(pin.get("content_id"), {})
            source_point = None
            if finite_seconds(start) and pin.get("kind") == "cue":
                matches = [cue for cue in (item.get("transcript") or {}).get("cues", [])
                           if cue.get("start_s") == start]
                if len(matches) == 1:
                    source_point = {"kind": "cue", "start_s": start,
                                    "quote": matches[0]["text"], "end_s": matches[0].get("end_s")}
            elif finite_seconds(start) and pin.get("kind") == "frame":
                if any(frame.get("t_seconds") == start for frame in (item.get("frames") or {}).get("items", [])):
                    source_point = {"kind": "frame", "start_s": start,
                                    "scope": "Available timestamp only; not proof of viewing."}
            if source_point is not None:
                registered = [{"kind": kind, "start_s": second}
                              for (content_id, kind, second) in bound if content_id == pin.get("content_id")]
                missing.append(MissingPointObservation(path, pin, source_point, registered))
                continue
            raise ValueError("pin is not bound to a same-video point observation")
    # A recoverable earlier omission must not mask a later invalid source point.
    if missing:
        raise missing[0]
    return bound
