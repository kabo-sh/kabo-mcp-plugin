#!/usr/bin/env python3
"""Validate a VideoAnalysis against its evidence and request.

Structural conformance is JSON Schema's job. This checks the things a schema cannot: that every
statement points at evidence that exists, that a conclusion is not drawn from data that was never
collected, and that the branch rules for whose video it is are respected.

    python3 validate_video_analysis.py <video_analysis.json> <content_evidence.json> [<request.json>]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

NUMBER_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty-four": 24}

# "Only 18 frames were sampled", "Ten frames were sampled and three were reviewed", "sampled 15
# frames". Deliberately narrow: it matches a claim about how many frames the run took in total, and
# not "61 of 63 sampled frames" or "the seven sampled hook frames", which are legitimate subsets.
TOTAL_FRAMES_CLAIM = re.compile(
    r"(?<!of )\b([A-Za-z-]+|\d+)\s+frames?\s+(?:were|was)\s+sampled|sampled\s+(\d+)\s+frames?",
    re.IGNORECASE)
BLANKET_NO_DATA_CLAIM = re.compile(
    r"^\s*no\s+(?:usable\s+)?(?:data|evidence)\s+(?:was|were)\s+retrieved\b",
    re.IGNORECASE,
)


def claimed_frame_totals(text: str) -> list[int]:
    found = []
    for match in TOTAL_FRAMES_CLAIM.finditer(text):
        token = match.group(1) or match.group(2)
        value = int(token) if token.isdigit() else NUMBER_WORDS.get(token.lower())
        if value is not None:
            found.append(value)
    return found


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def has_retrieved_evidence(evidence: dict) -> bool:
    transcript = evidence.get("transcript") or {}
    media = evidence.get("media") or {}
    metadata = evidence.get("content_metadata") or {}
    return bool(
        evidence.get("public_metrics")
        or (evidence.get("owner_metrics") or {}).get("items")
        or (evidence.get("frames") or {}).get("items")
        or any(i.get("status") == "available" for i in (evidence.get("images") or {}).get("items") or [])
        or transcript.get("cues")
        or transcript.get("plain_text")
        or media.get("status") == "available"
        or media.get("duration_s") is not None
        # A successful metadata fetch is retrieved evidence even when the video declares no
        # tags and publishes no cover: the run learned something about the video either way,
        # and a run that learned something may not report that it learned nothing.
        or metadata.get("status") == "available"
    )


def evidence_handles(evidence: dict, analysis: dict | None = None) -> set[str]:
    """Everything an observation or revision is allowed to point at.

    Built from the evidence object rather than listed by hand. An earlier version enumerated
    `observations.obs-01` through `obs-08`, which silently capped how many observations could
    cross-reference each other; denser frame sampling now routinely produces twenty-five.
    """
    handles = {f["frame_id"] for f in (evidence.get("frames") or {}).get("items") or []}
    handles |= {i["image_id"] for i in (evidence.get("images") or {}).get("items") or []
                if i.get("status") == "available" and i.get("image_id")}
    handles |= {f"owner_metrics.{i['native_name']}" for i in (evidence.get("owner_metrics") or {}).get("items") or []}
    handles |= {i["native_name"] for i in (evidence.get("owner_metrics") or {}).get("items") or []}
    handles |= {f"public_metrics.{m['native_name']}" for m in evidence.get("public_metrics") or []}
    # Both spellings, as with owner metrics. Accepting the bare name and rejecting the qualified
    # one was an inconsistency, not a rule.
    handles |= {d["name"] for d in evidence.get("derived") or []}
    handles |= {f"derived.{d['name']}" for d in evidence.get("derived") or []}
    # Structures the evidence really carries and an analysis legitimately points at: a probed value
    # disagreeing with the platform's own, and what each connector call returned.
    handles |= {f"media.discrepancies[{i}]"
                for i in range(len((evidence.get("media") or {}).get("discrepancies") or []))}
    # Every measured signal, by name. Before the evidence carried them an analysis could only point
    # at the whole call that produced them, so "the last 5 seconds are silent" cited a connector
    # request rather than the silence span it was read from. The literal mean_volume_db below
    # predates this and stays: an older analysis that cited it must keep resolving.
    probed = (evidence.get("media") or {}).get("probed") or {}
    handles |= {f"media.probed.{name}" for name in probed}
    for name, value in probed.items():
        if isinstance(value, dict):
            handles |= {f"media.probed.{name}.{field}" for field in value}
    for name in ("silence", "freeze"):
        spans = (probed.get(name) or {}).get("spans") or []
        handles |= {f"media.probed.{name}.spans[{i}]" for i in range(len(spans))}
    handles |= {f"media.probed.shots.shots[{i}]"
                for i in range(len(((probed.get("shots") or {}).get("shots")) or []))}
    handles |= {f"media.probed.brightness.per_shot[{i}]"
                for i in range(len(((probed.get("brightness") or {}).get("per_shot")) or []))}
    for index, entry in enumerate(evidence.get("acquisition") or []):
        handles |= {f"acquisition[{index}]"}
        handles |= {f"acquisition[{index}].{field}" for field in entry}
    handles |= {
        "transcript.text_sha256", "transcript.status", "transcript.language", "transcript.segment_count",
        "transcript.character_count", "transcript.plain_text",
        "media.has_audio", "media.duration_s", "media.frames.scene_detection",
        "media.probed.mean_volume_db", "audio_attribution.uses_original_audio",
        "deterministic.hook_stage", "deterministic.sustain_stage", "deterministic.cohort",
    }
    # Only cues whose text actually reached the evidence object can be cited. Minting these from
    # segment_count let an analysis quote transcript.cue[7] having never read a word of it, and the
    # reference resolved because the index was in range.
    handles |= {f"transcript.cue[{i}]"
                for i in range(len((evidence.get("transcript") or {}).get("cues") or []))}
    handles |= {f"observations.{o['observation_id']}"
                for o in (analysis or {}).get("observations") or []}
    caption = (evidence.get("content_metadata") or {}).get("caption")
    if isinstance(caption, str) and caption.strip():
        handles.add("content_metadata.caption")
    return handles


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "references" / "video-analysis.schema.json"


def structural_errors(node, schema: dict, where: str = "") -> list[str]:
    """A deliberate subset of JSON Schema: required, enum, minItems, additionalProperties.

    `jsonschema` is not importable in the runtime this Skill actually runs under, so without this
    the only structural check lived in the test suite. An agent would get a clean validator run and
    fail at schema time on a free-form `dimension` or an empty `evidence_refs` — which is exactly
    what happened. Enums are read from the schema file rather than restated here, so the two
    cannot drift apart.
    """
    errors: list[str] = []
    if isinstance(node, dict) and isinstance(schema.get("properties"), dict):
        for field in schema.get("required") or []:
            if node.get(field) is None:
                errors.append(f"{where or 'root'} is missing required field {field}")
        if schema.get("additionalProperties") is False:
            for field in node:
                if field not in schema["properties"]:
                    errors.append(f"{where or 'root'} carries unknown field {field}")
        for field, sub in schema["properties"].items():
            if field in node and node[field] is not None:
                errors += structural_errors(node[field], sub, f"{where}.{field}" if where else field)
    elif isinstance(node, list) and isinstance(schema.get("items"), dict):
        if schema.get("minItems") and len(node) < schema["minItems"]:
            errors.append(f"{where} needs at least {schema['minItems']} entry, and has none")
        for index, item in enumerate(node):
            errors += structural_errors(item, schema["items"], f"{where}[{index}]")
    elif schema.get("enum") and node not in schema["enum"]:
        allowed = ", ".join(str(v) for v in schema["enum"])
        errors.append(f"{where} is {node!r}, which is not one of: {allowed}")
    return errors


def validate(analysis: dict, evidence: dict, request: dict | None) -> list[str]:
    errors: list[str] = []
    subject = analysis.get("subject_state")
    completeness = analysis.get("evidence_completeness") or {}
    deterministic = analysis.get("deterministic") or {}
    handles = evidence_handles(evidence, analysis)

    if SCHEMA_PATH.exists():
        errors += structural_errors(analysis, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

    # --- edit verdict: data, never a second opinion ---
    if "edit_verdict" in analysis:
        from compose_video_analysis import edit_verdict
        require(analysis["edit_verdict"] == edit_verdict(analysis),
                "edit_verdict does not match what_worked and revisions[].fix_stage; rerun compose_video_analysis.py "
                "instead of editing it by hand", errors)

    # --- identity and lineage ---
    require(analysis.get("evidence_ref") == evidence.get("evidence_id"),
            "evidence_ref does not match the evidence object", errors)
    if request is not None:
        require(subject == (request.get("source") or {}).get("subject_state"),
                "subject_state disagrees with the request", errors)
        require(analysis.get("request_ref") == request.get("request_id"),
                "request_ref does not match the request", errors)

    # --- completeness must mirror the evidence, not wishful thinking ---
    require(completeness.get("transcript") == (evidence.get("transcript") or {}).get("status"),
            "evidence_completeness.transcript disagrees with the evidence", errors)
    require(completeness.get("owner_metrics") == (evidence.get("owner_metrics") or {}).get("status"),
            "evidence_completeness.owner_metrics disagrees with the evidence", errors)

    # --- no verdict without the metric that backs it ---
    owner_available = (evidence.get("owner_metrics") or {}).get("status") != "unavailable"
    for stage in ("hook_stage", "sustain_stage"):
        block = deterministic.get(stage) or {}
        if not owner_available:
            require(block.get("verdict") == "unassessed",
                    f"{stage} claims a verdict without any owner metric", errors)
        if block.get("verdict") in {"above_baseline", "below_baseline", "at_baseline"}:
            require((deterministic.get("cohort") or {}).get("cohort_n"),
                    f"{stage} places the post against a baseline without declaring the cohort", errors)
    require("composite_score" in deterministic and deterministic["composite_score"] is None,
            "composite_score must stay null: hook and sustain were observed to diverge", errors)

    # --- a percentage of the video requires a probed duration ---
    duration = (evidence.get("media") or {}).get("duration_s")
    for measure in (deterministic.get("sustain_stage") or {}).get("measures") or []:
        if "percentage" in measure["name"]:
            require(duration is not None,
                    f"{measure['name']} reported without a probed duration", errors)
        if measure.get("source") == "evidence_derived":
            names = {d["name"]: d["value"] for d in evidence.get("derived") or []}
            require(measure.get("evidence_ref") in names,
                    f"{measure['name']} references a derived value that is not in the evidence", errors)
            require(names.get(measure.get("evidence_ref")) == measure.get("value"),
                    f"{measure['name']} disagrees with the evidence object it cites", errors)

    # --- observations must rest on evidence that exists ---
    transcript_status = (evidence.get("transcript") or {}).get("status")
    timed = (evidence.get("transcript") or {}).get("timestamps_available")
    for obs in analysis.get("observations") or []:
        for ref in obs.get("evidence_refs") or []:
            require(ref in handles, f"{obs['observation_id']} cites unknown evidence {ref}", errors)
        if obs.get("basis") == "image":
            images = {i.get("image_id") for i in (evidence.get("images") or {}).get("items") or []
                      if i.get("status") == "available" and i.get("path") and i.get("sha256")}
            require(bool(images.intersection(obs.get("evidence_refs") or [])),
                    f"{obs['observation_id']} describes an image without delivered image evidence", errors)
            require(obs.get("t_start_s") is None and obs.get("t_end_s") is None,
                    f"{obs['observation_id']} gives a still image a fabricated timestamp", errors)
        if obs.get("basis") == "transcript":
            require(transcript_status == "available",
                    f"{obs['observation_id']} draws on a transcript that was not retrieved", errors)
            if not timed:
                require(obs.get("t_start_s") is None and obs.get("t_end_s") is None,
                        f"{obs['observation_id']} anchors a plain-text transcript to a timestamp", errors)
        if obs.get("dimension") == "spoken_hook":
            require(transcript_status == "available",
                    f"{obs['observation_id']} describes speech without a transcript", errors)

    if subject == "unknown":
        from prepare_link_request import public_only_request_errors
        from compute_deterministic import compute, public_only_evidence_errors
        require(request is not None, "unknown ownership needs its explicit public-only request", errors)
        if request is not None:
            errors += public_only_request_errors(request)
        scope_errors = public_only_evidence_errors(evidence)
        errors += scope_errors
        require(completeness.get("account_baseline") == "unavailable",
                "unknown ownership cannot declare an account baseline", errors)
        if not scope_errors:
            require(deterministic == compute(evidence, None, "unknown"),
                    "unknown ownership must retain the public-only unassessed deterministic block", errors)
        require(not analysis.get("revisions"), "unknown ownership carries no source revisions", errors)

    # --- branch rules for whose video this is ---
    revisions = analysis.get("revisions") or []
    if subject == "third_party":
        require(not revisions,
                "third-party content carries no revisions: it is not the creator's to change", errors)
    if subject == "own_unpublished":
        # A draft review exists to produce changes, and one proposing none has not done its job --
        # wherever the evidence can carry a change. What that rule cannot survive is a run whose
        # evidence never arrived: every revision needs at least one evidence_ref that resolves, so
        # demanding a revision from an empty evidence object demands an invented one, and an
        # invented revision is the exact failure the rest of this file exists to prevent. A local
        # run whose media tools were absent, and whose creator supplied no subtitle file, is in that
        # state legitimately. It owes the creator the reason, which is a named unassessed dimension
        # rather than a change order resting on nothing.
        if has_retrieved_evidence(evidence):
            require(bool(revisions),
                    "a draft review that proposes no revision has not done its job", errors)
        else:
            require(bool(analysis.get("unavailable_dimensions")),
                    "this draft review proposes no revision and rests on no retrieved evidence; name the "
                    "dimensions that went unassessed in unavailable_dimensions, or the report is empty "
                    "and does not say so", errors)
        for rev in revisions:
            require(rev.get("fix_stage"),
                    f"{rev['revision_id']} omits fix_stage; a draft note must say whether it is still fixable", errors)
    if subject in {"own_unpublished", "third_party"}:
        require(not owner_available,
                "owner metrics are present for content that cannot have them", errors)
    for rev in revisions:
        for ref in rev.get("evidence_refs") or []:
            require(ref in handles, f"{rev['revision_id']} cites unknown evidence {ref}", errors)

    # --- a stated frame total must be the frame total ---
    # Rebuilding an analysis from denser sampling leaves prose behind: three fixtures kept "Only 18
    # frames were sampled" from the era when that was true, and an isolated run reading one of them
    # had to decide which of two frame counts in the same object to believe.
    sampled = len((evidence.get("frames") or {}).get("items") or [])
    if sampled:
        for field in ("limitations", "must_not_assume"):
            for index, text in enumerate(analysis.get(field) or []):
                for claimed in claimed_frame_totals(text):
                    require(claimed == sampled,
                            f"{field}[{index}] says {claimed} frames were sampled; the evidence "
                            f"carries {sampled}", errors)

    if has_retrieved_evidence(evidence):
        for index, text in enumerate(analysis.get("limitations") or []):
            require(not BLANKET_NO_DATA_CLAIM.search(text),
                    f"limitations[{index}] claims no data was retrieved although usable evidence "
                    "exists; name only the missing source", errors)

    # --- a cover that was never fetched is not a video without a cover ---
    # The connector answers `available` with empty arrays when the platform published no tags
    # and no cover, and that is a finding about the video. It answers with a failed envelope
    # when the fetch itself did not happen, and that is a fact about this run. Both arrive as
    # empty arrays, so `status` is the only thing separating them -- exactly the shape of the
    # The same available/unavailable defect, one object over. An unavailable fetch that nothing in the analysis
    # admits to reads to every downstream consumer as "this video has no cover and no tags".
    metadata = evidence.get("content_metadata")
    if isinstance(metadata, dict) and metadata.get("status") == "unavailable":
        # The admission has to name `content_metadata` itself. Matching the loose words
        # instead -- "tags", "thumbnail" -- passes on any entry that happens to contain them:
        # the shipped YouTube fixture already carries an unavailable_dimensions entry reading
        # "title, description, hashtags, thumbnail and posting time", which is Packaging's
        # scope and says nothing about whether this fetch happened. A gate that a stray word
        # satisfies is not a gate. Naming the field is also the register these limitations
        # already use -- they name connector and operation verbatim.
        admitted = any(
            "content_metadata" in text for text in (analysis.get("limitations") or [])
        )
        require(admitted,
                "content_metadata was not retrieved, but no limitation names it; an unadmitted "
                "gap reads as a video that published no tags and no cover", errors)

    # --- every acquisition entry says which kind of step it was, and carries that kind's fields ---
    # Here for the same reason as the pairing below: the schema expresses this as an if/then branch
    # and `structural_errors` carries no if/then, so it would look enforced and be enforced by
    # nobody. What it prevents is a local step wearing a connector's identifiers -- a ledger that
    # says a call was made when nothing was requested of anyone, which makes the run unreplayable
    # in the one way the ledger exists to prevent.
    for index, entry in enumerate(evidence.get("acquisition") or []):
        if not isinstance(entry, dict):
            continue
        step = entry.get("step")
        if step == "local_extraction":
            stray = sorted({"connector_id", "connector_request_id"} & set(entry))
            require(not stray,
                    f"acquisition[{index}] is a local step carrying {', '.join(stray)}; nothing was "
                    "requested of a connector and the ledger must not say otherwise", errors)
            require(bool(entry.get("tool")) and bool(entry.get("invocation_sha256")),
                    f"acquisition[{index}] is a local step with no tool or no invocation hash; it "
                    "cannot be replayed and is not a record of anything", errors)
        elif step == "connector_call":
            require(bool(entry.get("connector_id")) and bool(entry.get("connector_request_id")),
                    f"acquisition[{index}] claims a connector call with no connector and no request id",
                    errors)
        else:
            require(False,
                    f"acquisition[{index}] does not say whether it was a connector call or a local "
                    "step; an unlabelled entry defaults to being read as a call", errors)

    # --- frames.origin and frames.observations travel together, both ways ---
    # `structural_errors` is a deliberate subset of JSON Schema and carries no if/then, so the
    # schema file cannot express this pair on its own -- writing it there would look enforced
    # and be enforced by nobody, which is the failure this file exists to prevent one layer
    # down. The rule matters because each half without the other states something false:
    # `model_observation` with no observations claims a model watched the video and reports
    # nothing it saw, while observations under `extracted_frames` invite the analysis to quote
    # prose as if it were read off a frame -- and the whole point of the origin field is that
    # those two are not the same kind of evidence.
    frames = evidence.get("frames")
    if isinstance(frames, dict):
        origin = frames.get("origin")
        observations = frames.get("observations")
        if origin == "model_observation":
            require(isinstance(observations, list) and len(observations) > 0,
                    "frames.origin is model_observation but no observations reached the evidence "
                    "object; a model that watched the video and recorded nothing is not evidence",
                    errors)
        elif isinstance(observations, list) and observations:
            require(False,
                    f"frames carries observations but origin is {origin!r}; timestamped "
                    "descriptions are only admissible as model_observation, because they were "
                    "reported rather than seen", errors)

    # --- a dimension cannot be unavailable and scored at the same time ---
    # The baseline arrives from the M1 account review, not from the evidence object, so "this
    # evidence set carries no baseline" is true and yet the stage verdicts are still scored against
    # one. Two rebuilt analyses drew the wrong conclusion from that and declared the verdicts
    # unassessed while `deterministic` had scored them; an isolated run reading the object cold is
    # what caught it.
    for entry in analysis.get("unavailable_dimensions") or []:
        named = entry.get("dimension") or ""
        for stage in ("hook_stage", "sustain_stage"):
            if stage in named or stage.replace("_stage", "") + "_verdict" in named:
                require((deterministic.get(stage) or {}).get("verdict") == "unassessed",
                        f"unavailable_dimensions claims {stage} is unavailable, but deterministic "
                        f"scored it {(deterministic.get(stage) or {}).get('verdict')}", errors)

    # --- hypotheses stay hypotheses ---
    for hyp in analysis.get("hypotheses") or []:
        require(hyp.get("confidence") in {"medium", "low"},
                "a hypothesis cannot be high confidence; promote it or leave it", errors)
        require(bool(hyp.get("would_be_confirmed_by")),
                "a hypothesis without a confirming test is an opinion", errors)

    require(bool(analysis.get("must_not_assume")),
            "must_not_assume is required: the tempting wrong readings are specific to this evidence", errors)
    return errors


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    analysis = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    evidence = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    request = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 else None
    errors = validate(analysis, evidence, request)
    for error in errors:
        print(f"FAIL {error}")
    print("OK" if not errors else f"{len(errors)} problem(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
