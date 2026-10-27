#!/usr/bin/env python3
"""Assemble VideoAnalysis from the judgment the model wrote and what this run already computed.

The model used to write the whole object. Measured 2026-09-23 on a real Instagram run that was
15.3 KB of JSON and 152 seconds of model output, for a report of 3.5 KB -- and about a fifth of it
was lineage the run already knew (ids, refs, statuses) plus a `deterministic` block byte for byte
identical to what `compute_deterministic.py` had written minutes earlier. Nothing checked that
copy: `validate_video_analysis.py` reads the analysis, the evidence and the request, never
`deterministic.json`, so a retyped verdict could disagree with the computed one and pass. Here the
computed block is loaded, not retyped, and the question stops existing.

What stays the model's, and is never generated here: every observation, hypothesis and revision,
what worked and what did not, and any limitation or assumption this run's evidence does not
already state. The script adds what the evidence entails, preserving the model's wording. At the
output boundary it qualifies exact, unambiguous observation IDs used as revision citations.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

SCHEMA_VERSION = "video-analysis.v1"
PLATFORM_PREFIX = {"youtube": "yt", "instagram": "ig", "tiktok": "tt"}
# Keys this script owns. A judgment that carries them is already a whole analysis (see `main`).
COMPOSED = (
    "schema_version", "analysis_id", "subject_state", "request_ref", "evidence_ref",
    "content_ref", "evidence_completeness", "deterministic", "reproducibility",
)
# Keys only the model can fill, in the order the schema lists them.
JUDGED = (
    "observations", "hypotheses", "revisions", "what_worked", "what_did_not_work",
)
PARTIAL_FIELDS = (*JUDGED, "unavailable_dimensions", "must_not_assume", "limitations", *COMPOSED)
CONTENT_REF_KEYS = ("platform", "content_id", "permalink")


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"{path} does not exist; write it before composing the analysis")
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must hold a JSON object")
    return value


def record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def judgment_schema(evidence_refs: list[str] | None = None, reference_index: Path | None = None) -> dict[str, Any]:
    """Project the author contract without duplicating the final analysis schema."""
    schema = load(Path(__file__).resolve().parents[1] / "references/video-analysis.schema.json")
    fields = (*JUDGED, "unavailable_dimensions", "must_not_assume", "limitations")
    properties = {key: copy.deepcopy(schema["properties"][key]) for key in fields}
    for block, field in (("evidence_completeness", "account_baseline"),
                         ("reproducibility", "analyst_model")):
        properties[block] = {
            "type": "object", "additionalProperties": False,
            "properties": {field: copy.deepcopy(schema["properties"][block]["properties"][field])},
        }
    projected = {"$schema": schema["$schema"], "title": "Video judgment",
                 "type": "object", "required": ["observations"],
                 "additionalProperties": False, "properties": properties}
    if evidence_refs is not None:
        # Refs stay in the index: inlined per field, this output outgrows what hosts print whole.
        # The preflight checks exact refs; observation IDs do not exist until authoring.
        name = reference_index.name if reference_index is not None else "the reference index"
        citation = {"type": "string", "description": (
            f"One exact entry of evidence_refs in {name} ({len(evidence_refs)} entries), copied verbatim, "
            "or observations.<observation_id> of an observation in this judgment.")}
        for field in ("observations", "revisions"):
            properties[field]["items"]["properties"]["evidence_refs"]["items"] = copy.deepcopy(citation)
        projected["examples"] = [{"observations": [{
            "observation_id": "obs-1", "dimension": "spoken_hook", "statement": "<what the evidence shows>",
            "basis": "transcript", "evidence_refs": [f"<one exact entry from {name}>"], "confidence": "medium"}]}]
    return projected


def reference_handles(evidence: dict[str, Any], judgment: dict[str, Any] | None = None) -> set[str]:
    # Load the existing validator beside this script, including when imported by a caller
    # whose sys.path does not contain the Skill. There is only one reference resolver.
    spec = importlib.util.spec_from_file_location(
        "video_reference_validator", Path(__file__).with_name("validate_video_analysis.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evidence_handles(evidence, judgment)


def alias_blocking_refs(evidence: dict[str, Any]) -> set[str]:
    refs = reference_handles(evidence)
    # An unavailable image ID must not be reinterpreted as an observation alias.
    refs.update(item["image_id"] for item in record(evidence.get("images")).get("items") or []
                if isinstance(item, dict) and isinstance(item.get("image_id"), str))
    return refs


def bound_evidence(evidence_path: Path, index_path: Path) -> tuple[dict[str, Any], list[str]]:
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    if not isinstance(evidence, dict) or not isinstance(evidence.get("evidence_id"), str) or not evidence["evidence_id"]:
        raise SystemExit("evidence must be an identified JSON object")
    index = load(index_path)
    expected = sorted(reference_handles(evidence))
    if (index.get("schema_version") != "content-evidence-references.v1"
            or index.get("evidence_id") != evidence.get("evidence_id")
            or index.get("evidence_sha256") != hashlib.sha256(evidence_bytes).hexdigest()
            or index.get("evidence_refs") != expected):
        raise SystemExit("reference index does not match this exact evidence; stop, do not repair or replace it")
    return evidence, expected


def judgment_reference_issues(judgment: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, str]]:
    # Only authored citation errors are correctable. Shapes, evidence/index I/O and internal
    # errors propagate normally; never turn a data or execution fault into a successful pause.
    validate_judgment(judgment)
    handles = reference_handles(evidence, judgment)
    issues = []
    for field in ("observations", "revisions"):
        for index, item in enumerate(judgment.get(field) or []):
            for position, ref in enumerate(item.get("evidence_refs") or []):
                if ref not in handles:
                    issues.append({"field": f"{field}[{index}].evidence_refs[{position}]",
                                   "invalid_ref": ref, "message": "not a legal reference in this evidence and judgment"})
    return issues


def grounding_review(judgment: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Expose validated author text and its source modalities, never a visual verdict."""
    refs = {ref for field in ("observations", "revisions")
            for item in judgment.get(field) or [] for ref in item.get("evidence_refs") or []}
    sources = []
    for frame in record(evidence.get("frames")).get("items") or []:
        if frame["frame_id"] in refs:
            sources.append({"ref": frame["frame_id"], "kind": "frame", "source": copy.deepcopy(frame)})
    for image in record(evidence.get("images")).get("items") or []:
        if image.get("image_id") in refs:
            sources.append({"ref": image["image_id"], "kind": "image", "source": copy.deepcopy(image)})
    for index, cue in enumerate(record(evidence.get("transcript")).get("cues") or []):
        ref = f"transcript.cue[{index}]"
        if ref in refs:
            sources.append({"ref": ref, "kind": "recorded_speech", "source": copy.deepcopy(cue)})
    for index, observation in enumerate(judgment.get("observations") or []):
        ref = f"observations.{observation['observation_id']}"
        if ref in refs:
            sources.append({"ref": ref, "kind": "authored_observation",
                            "path": f"observations[{index}]", "source": copy.deepcopy(observation)})
    return {"schema_version": "video-grounding-review.v1", "semantic_status": "not_verified_by_script",
            "creator_view_covered": False,
            "scope": "Review the existing judgment against the same-source images already displayed. A legal frame ref or timestamp does not prove object recognition, first appearance or continuous coverage; a cue start is recorded speech, not a visual boundary. This projection does not inspect a future creator view.",
            "authored_judgment": copy.deepcopy(judgment), "referenced_sources": sources,
            "other_legal_refs": sorted(refs - {row["ref"] for row in sources}),
            "packet_end": {"judgment_fields": list(judgment),
                           "observations": len(judgment.get("observations") or []),
                           "source_refs": [row["ref"] for row in sources]}}


def require_judgment_references(judgment: dict[str, Any], evidence: dict[str, Any]) -> None:
    # Preserve only the existing CLI's exact, unambiguous revision-ID qualification.
    # This never invents a metric name and never rewrites the authored input.
    validate_judgment(judgment)
    legacy, _ = qualify_revision_refs(judgment, alias_blocking_refs(evidence))
    issues = judgment_reference_issues(legacy, evidence)
    if issues:
        raise SystemExit("Invalid judgment references:\n" + json.dumps(issues, ensure_ascii=False))


def validate_judgment(judgment: dict[str, Any]) -> None:
    """Reject unsupported partial input before composition can discard it.

    Shapes come from the existing analysis schema; required fields and evidence semantics
    remain the final analysis validator's job. Known script-owned fields are accepted
    for older partial judgments, but their values are rebuilt as before.
    """
    schema = load(Path(__file__).resolve().parents[1] / "references/video-analysis.schema.json")
    errors: list[str] = []
    types = {"object": dict, "array": list, "string": str, "null": type(None),
             "boolean": bool, "number": (int, float), "integer": int}

    def check(value: Any, shape: dict[str, Any], path: str) -> None:
        expected = shape.get("type")
        names = expected if isinstance(expected, list) else [expected] if expected else []
        if names and not any(isinstance(value, types[name]) and
                             not (isinstance(value, bool) and name in ("number", "integer"))
                             for name in names):
            errors.append(f"{path} must be {' or '.join(names)}")
            return
        if "enum" in shape and value not in shape["enum"]:
            errors.append(f"{path} must be one of: {', '.join(map(str, shape['enum']))}")
        if "const" in shape and value != shape["const"]:
            errors.append(f"{path} must equal {shape['const']!r}")
        if isinstance(value, dict):
            properties = shape.get("properties") or {}
            for key, child in value.items():
                if key in properties:
                    check(child, properties[key], f"{path}.{key}")
                elif shape.get("additionalProperties") is False:
                    errors.append(f"{path}.{key} is not a supported field")
        elif isinstance(value, list) and "items" in shape:
            for index, child in enumerate(value):
                check(child, shape["items"], f"{path}[{index}]")

    for key, value in judgment.items():
        if key not in PARTIAL_FIELDS:
            errors.append(f"judgment.{key} is not a supported partial-judgment field")
        else:
            check(value, schema["properties"][key], f"judgment.{key}")
    if errors:
        raise SystemExit("Invalid partial judgment:\n" + "\n".join(errors))


def qualify_revision_refs(analysis: dict[str, Any], evidence_refs: set[str]) -> tuple[dict[str, Any], int]:
    """Resolve a bare observation ID without guessing a target or changing an existing ref."""
    counts: dict[str, int] = {}
    observations = analysis.get("observations")
    for observation in observations if isinstance(observations, list) else []:
        identifier = record(observation).get("observation_id")
        if isinstance(identifier, str) and identifier:
            counts[identifier] = counts.get(identifier, 0) + 1
    aliases = {identifier: f"observations.{identifier}" for identifier, count in counts.items()
               if count == 1 and identifier not in evidence_refs
               and f"observations.{identifier}" not in evidence_refs
               and not identifier.startswith("observations.")}
    result = copy.deepcopy(analysis)
    changed = 0
    revisions = result.get("revisions")
    for revision in revisions if isinstance(revisions, list) else []:
        refs = record(revision).get("evidence_refs")
        if not isinstance(refs, list):
            continue
        for index, ref in enumerate(refs):
            if isinstance(ref, str) and ref in aliases:
                refs[index] = aliases[ref]
                changed += 1
    return result, changed


def completeness(evidence: dict[str, Any], judgment: dict[str, Any]) -> dict[str, Any]:
    """What the analysis could see, read off the evidence rather than restated.

    `media` and `frames` are a two-value enum in the analysis while the evidence has four states,
    so anything short of available is unavailable here -- the reason it was not available is in the
    acquisition ledger, which is where a reader who needs it should look.
    """
    def binary(block: str) -> str:
        return "available" if record(evidence.get(block)).get("status") == "available" else "unavailable"

    block = {
        "media": binary("media"),
        "transcript": record(evidence.get("transcript")).get("status") or "not_attempted",
        "frames": binary("frames"),
        "owner_metrics": record(evidence.get("owner_metrics")).get("status") or "unavailable",
    }
    if "images" in evidence:
        block["images"] = binary("images")
    # Whether a comparable baseline was retrieved is not a fact about this video's own evidence,
    # so it is the one member of this block the judgment supplies.
    baseline = record(judgment.get("evidence_completeness")).get("account_baseline")
    if baseline is not None:
        block["account_baseline"] = baseline
    return block


def unavailable_dimensions(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Which dimensions the evidence rules out. Each one is a status, not a reading of the video."""
    entries: list[dict[str, Any]] = []
    transcript = record(evidence.get("transcript")).get("status")
    if transcript != "available":
        entries.append({
            "dimension": "spoken_hook",
            "reason": f"The transcript is {transcript}, so nothing said on the audio track was read.",
            "would_require": "A subtitle track from the platform, or the creator's own subtitle file for this cut.",
        })
    # `unavailable`, not "anything but available". The validator reads owner metrics as present
    # whenever the status is not `unavailable` (so a `partial` export still scores the stages), and
    # it also refuses an analysis that calls a dimension unavailable while the verdict scored it.
    # Generating this entry on `partial` would make the two contradict each other every time, and
    # the judgment cannot take it back -- the script wrote it.
    if record(evidence.get("owner_metrics")).get("status") == "unavailable":
        entries.append({
            "dimension": "hook_stage and sustain_stage retention",
            "reason": "No owner Insights export was supplied, so the 3-second hold, average watch time, "
                      "reach and shares are unavailable and both stage verdicts stay unassessed.",
            "would_require": "The creator's own Insights export for this post.",
        })
    if record(evidence.get("content_metadata")).get("thumbnails"):
        # The cover URL is retrieved; its pixels are not. Judging a cover from its address is the
        # exact claim this Skill refuses, so the dimension is declared absent rather than guessed.
        entries.append({
            "dimension": "cover appearance",
            "reason": "Only the cover URL was retrieved; no cover pixels were viewed, so its look is not judged.",
            "would_require": "The cover image itself.",
        })
    return entries


def entailed_assumptions(evidence: dict[str, Any]) -> list[str]:
    """The wrong readings this run's own gaps invite. Each is entailed by a status or a counter."""
    lines: list[str] = []
    metrics = {m.get("native_name"): m.get("value") for m in evidence.get("public_metrics") or []
               if isinstance(m, dict)}
    # 旧信封的 GraphQL 名，或 lookup_instagram_post 投影的字段路径（build_content_evidence 的 native_name）。
    # 只有 IG+FB 合并播放数时同样不是触达；分母取 IG 自身的播放数优先。
    plays = next((metrics[name] for name in ("video_play_count", "metrics.plays_instagram", "metrics.plays_combined")
                  if isinstance(metrics.get(name), (int, float))), None)
    likes = metrics.get("edge_media_preview_like.count", metrics.get("metrics.likes"))
    if isinstance(plays, (int, float)):
        rate = (f"; {likes} likes over {plays} plays is not an engagement rate"
                if isinstance(likes, (int, float)) else "")
        lines.append(f"A public play count is not reach and not an audience{rate}.")
    if record(evidence.get("owner_metrics")).get("status") == "unavailable":
        lines.append("No retention curve was available, so nothing here locates where viewers left.")
    if record(evidence.get("transcript")).get("status") != "available":
        lines.append("Nothing said on the audio track was read; no claim is made about the spoken content.")
    if record(evidence.get("content_metadata")).get("thumbnails"):
        lines.append("The cover image was not viewed; nothing here judges whether it works.")
    return lines


def ordered_unique(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for line in group:
            if isinstance(line, str) and line.strip() and line not in seen:
                seen.add(line)
                out.append(line)
    return out


def compose(judgment: dict[str, Any], evidence: dict[str, Any], deterministic: dict[str, Any],
            request: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    require_judgment_references(judgment, evidence)
    ref = record(evidence.get("content_ref"))
    platform = str(ref.get("platform") or "")
    if platform not in PLATFORM_PREFIX:
        raise SystemExit(f"the evidence names platform {platform!r}, which has no analysis id prefix")
    run_id = record(evidence.get("reproducibility")).get("run_id") or "unknown"
    missing = [key for key in ("observations",) if not judgment.get(key)]
    if missing:
        raise SystemExit(
            f"the judgment is missing {', '.join(missing)}: this script fills the lineage, the "
            f"verdict block and what the evidence entails, never the reading of the video"
        )
    analysis: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": f"va-{PLATFORM_PREFIX[platform]}-{ref.get('content_id')}-{run_id}",
        "subject_state": record(request.get("source")).get("subject_state"),
        "request_ref": request.get("request_id"),
        "evidence_ref": evidence.get("evidence_id"),
        # The evidence ref carries more than identity; the analysis carries only identity.
        "content_ref": {key: ref.get(key) for key in CONTENT_REF_KEYS},
        "evidence_completeness": completeness(evidence, judgment),
        "deterministic": deterministic,
        "reproducibility": {
            "run_id": run_id,
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "rule_version": deterministic.get("rule_version"),
            "analyst_model": record(judgment.get("reproducibility")).get("analyst_model"),
        },
    }
    for key in JUDGED:
        if judgment.get(key) is not None:
            analysis[key] = judgment[key]
    analysis["unavailable_dimensions"] = ordered_dimensions(
        unavailable_dimensions(evidence), judgment.get("unavailable_dimensions") or [])
    # The evidence's own sentences first and verbatim. Rewriting them is what
    # `validate_video_analysis.py` had to grow a check for: a run once turned "no data was
    # retrieved" from one failed call into a statement about the whole run.
    analysis["must_not_assume"] = ordered_unique(
        entailed_assumptions(evidence), judgment.get("must_not_assume") or [])
    analysis["limitations"] = ordered_unique(
        [str(line) for line in evidence.get("limitations") or []],
        judgment.get("limitations") or [])
    if (record(evidence.get("content_metadata")).get("status") == "unavailable"
            and not any("content_metadata" in line for line in analysis["limitations"])):
        analysis["limitations"].append(
            "content_metadata is unavailable in this run; missing metadata is not evidence "
            "that the post has no tags or cover.")
    return analysis


def edit_verdict(analysis: dict[str, Any]) -> dict[str, Any]:
    """Keep / recut / replace as data: the same mapping hosts used to re-derive from prose.

    keep = what_worked; replace = every reshoot revision; recut = every other revision, including
    one that names no fix_stage (counted in unstaged_revisions so a reader knows it was assumed).
    """
    revisions = [row for row in analysis.get("revisions") or [] if isinstance(row, dict)]
    return {
        "keep": [line for line in analysis.get("what_worked") or [] if isinstance(line, str)],
        "recut": [str(row.get("proposed_change") or "") for row in revisions if row.get("fix_stage") != "reshoot"],
        "replace": [str(row.get("proposed_change") or "") for row in revisions if row.get("fix_stage") == "reshoot"],
        "unstaged_revisions": sum(1 for row in revisions if row.get("fix_stage") is None),
    }


def ordered_dimensions(entailed: list[dict[str, Any]], judged: list[Any]) -> list[dict[str, Any]]:
    """Entailed dimensions first; a judgment may add one the evidence does not imply, never replace."""
    out = list(entailed)
    named = {entry.get("dimension") for entry in entailed}
    for entry in judged:
        if isinstance(entry, dict) and entry.get("dimension") not in named:
            out.append(entry)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose VideoAnalysis from the judgment and this run's computed evidence")
    parser.add_argument("--print-judgment-schema", action="store_true",
                        help="Print the author schema; optionally bind it to exact evidence and reference index")
    parser.add_argument("--check-judgment-refs", action="store_true",
                        help="Read-only preflight of authored references before the final pipeline")
    parser.add_argument("--reference-index", type=Path)
    for name in ("judgment", "evidence", "deterministic", "request", "output"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--generated-at", default=None,
                        help="ISO instant recorded as when the analysis was produced; defaults to now")
    args = parser.parse_args()
    if args.print_judgment_schema or args.check_judgment_refs:
        if args.print_judgment_schema and args.check_judgment_refs:
            parser.error("choose one author contract mode")
        if any(getattr(args, name) is not None for name in
               ("deterministic", "request", "output", "generated_at")):
            parser.error("author contract modes do not compose or write an analysis")
        if (args.evidence is None) != (args.reference_index is None):
            parser.error("--evidence and --reference-index must be supplied together")
        if args.print_judgment_schema:
            if args.judgment is not None:
                parser.error("--judgment is not an input to the pre-author schema")
            refs = bound_evidence(args.evidence, args.reference_index)[1] if args.evidence else None
            print(json.dumps(judgment_schema(refs, args.reference_index), indent=2, ensure_ascii=False))
            return 0
        if args.judgment is None or args.evidence is None:
            parser.error("reference preflight requires --judgment, --evidence and --reference-index")
        evidence, refs = bound_evidence(args.evidence, args.reference_index)
        judgment = load(args.judgment)
        issues = judgment_reference_issues(judgment, evidence)
        result = {"status": "needs_correction" if issues else "ready",
                  "artifact": str(args.judgment), "issues": issues, "legal_source_refs": refs}
        if not issues:
            result["grounding_review"] = grounding_review(judgment, evidence)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.reference_index is not None:
        parser.error("--reference-index belongs to an author contract mode")
    for name in ("judgment", "evidence", "deterministic", "request", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required when composing an analysis")

    judgment = load(args.judgment)
    evidence = load(args.evidence)
    # A whole analysis keeps its lineage. A run that already has one -- a
    # replay, or a judgment written before this step existed -- must not have its own lineage
    # rewritten underneath it just because it was handed to a composer.
    if all(key in judgment for key in COMPOSED) and judgment.get("observations"):
        analysis = judgment
        composed = False
    else:
        analysis = compose(judgment, evidence, load(args.deterministic), load(args.request),
                           generated_at=args.generated_at)
        composed = True
    analysis, qualified = qualify_revision_refs(analysis, alias_blocking_refs(evidence))
    if composed:
        # A whole analysis handed in is passed through as it is; a composed one carries the verdict.
        analysis["edit_verdict"] = edit_verdict(analysis)
    args.output.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not composed:
        print(json.dumps({"status": "ok", "output": str(args.output), "composed": False,
                          "reason": "the judgment is already a complete analysis",
                          "qualified_revision_refs": qualified}))
        return 0
    print(json.dumps({
        "status": "ok", "output": str(args.output), "composed": True,
        "qualified_revision_refs": qualified,
        "analysis_id": analysis["analysis_id"],
        "observations": len(analysis.get("observations") or []),
        "unavailable_dimensions": len(analysis["unavailable_dimensions"]),
        "must_not_assume": len(analysis["must_not_assume"]),
        "limitations": len(analysis["limitations"]),
        "verdict": {key: analysis["deterministic"].get(key) for key in ("hook_stage", "sustain_stage")},
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
