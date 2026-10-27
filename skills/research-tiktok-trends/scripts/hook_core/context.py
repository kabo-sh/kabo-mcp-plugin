"""Prepare a shared method context for an existing research synthesis without remeasuring media."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import HookError, digest, envelope, implementation_digest, read_json, source_file
from .knowledge import ROOT, load_knowledge, select_patterns


def provenance() -> dict:
    return {"implementation_sha256": implementation_digest(),
            "knowledge_sha256": digest(ROOT / "references/hook-core/knowledge.json")}


def pinned_file(path, sha) -> Path:
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise HookError("invalid_request", "pin the input JSON file with its exact SHA-256")
    source = source_file(path)
    if source.stat().st_size > 8 * 1024 * 1024:
        raise HookError("context_budget_exceeded", "context/evidence JSON exceeds 8 MiB")
    if digest(source) != sha:
        raise HookError("artifact_mismatch", "input JSON differs from its supplied pin")
    return source


def measured_input(path, sha, directory=None) -> tuple[Path, dict]:
    from .bundle import verify_evidence_bundle
    source = pinned_file(path, sha)
    request = {"evidence_file": str(source)}
    if directory is not None:
        request["evidence_dir"] = directory
    verify_evidence_bundle(request)
    evidence = read_json(source)
    if digest(source) != sha:
        raise HookError("source_changed", "evidence changed during context preparation")
    return source, evidence


def prepare_context(request: dict) -> dict:
    """Keep method choices and optional existing-video diagnosis in one result."""
    media_fields = {"expressions", "observations", "pattern_ids", "reference_query"}
    has_media = request.get("evidence_file") is not None
    if not has_media and ("evidence_sha256" in request or "evidence_dir" in request or media_fields & request.keys()):
        raise HookError("invalid_request", "observed-media fields require an actual pinned evidence bundle")
    patterns = select_patterns(request.get("materials", []), route=request.get("route"))
    material_basis = "declared" if "materials" in request else "unconfirmed"
    if material_basis == "unconfirmed":
        # Method inventory is conditional: never declare reference assets available
        # to a creator merely because the current business brief omits materials.
        patterns["patterns"] = [p for p in load_knowledge()["patterns"]
                                if request.get("route") is None or p["route"] in (request["route"], "overlay")]
    # Historical sample links are not shipped here: this Skill never shows them to the creator.
    examples: list[dict] = []
    source, measurements, recognition, diagnosis = None, None, None, None
    if has_media:
        from .diagnosis import diagnose_expression
        path, evidence = measured_input(request["evidence_file"], request.get("evidence_sha256"), request.get("evidence_dir"))
        source = {"media_sha256": evidence["source"]["sha256"], "source_id": evidence["source"]["source_id"],
                  "evidence_file": str(path), "evidence_sha256": request["evidence_sha256"],
                  "evidence_dir": str(Path(request.get("evidence_dir", path.parent)).expanduser().resolve())}
        measurements = {key: evidence.get(key) for key in ("status", "coverage", "timebase", "audio", "loudness", "tail")}
        # Keep the actual artifact refs and recognition records; no generated captions.
        measurements["frames"] = evidence["frames"]
        recognition = evidence.get("recognition", {})
        diagnosis = diagnose_expression({"evidence": evidence, "available_materials": request.get("materials", []),
                                         **{key: request[key] for key in media_fields if key in request}})
    result = envelope("HookContext", status=diagnosis["status"] if diagnosis else "method_reference",
                    basis="measured_media" if has_media else "method_only", provenance=provenance(),
                    source=source, pattern_candidates=patterns["patterns"],
                    reference_examples=examples,
                    material_basis=material_basis,
                    selection_status=patterns["selection_status"], measurements=measurements,
                    recognition=recognition, diagnosis=diagnosis,
                    use_scope="Shared input to existing business synthesis; each owner chooses its report and workflow.",
                    execution_scope="No retrieval, decoding, OCR, ASR, repair or model invocation in this action.")
    if len((json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()) > 8 * 1024 * 1024:
        raise HookError("context_budget_exceeded", "prepared consumption JSON exceeds 8 MiB; no successful artifact produced")
    return result


