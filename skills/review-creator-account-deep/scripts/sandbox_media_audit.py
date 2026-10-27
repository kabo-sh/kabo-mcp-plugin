#!/usr/bin/env python3
"""Read-only metadata projection for an authorized, current-turn audit artifact.

No network, credentials, logs, conclusions, media decoding, or input writes.
This is not a host attestation: source origin must be independently established.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 64, 2 * 1024**2, 8 * 1024**2
OPERATIONS = {"collect_public_metadata", "fetch_transcript", "extract_keyframes"}
ALIASES = {"extract_keyframes", "extract_keyframes_hosted_media", "extract_keyframes_hosted_stream"}
STATUS = {"completed", "completed_partial", "failed", "unsupported", "blocked_setup"}
JOB_STATUS = {"completed", "failed", "cancelled"}
ORIGINS = {"platform_captions", "provider_transcript", "speech_recognition", "public_platform_fallback",
           "public_embed_metadata", "media_probe", "frame_extraction", "hosted_media", "hosted_stream"}
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA = re.compile(r"^[a-f0-9]{64}$")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode())

def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0

def operation(value):
    return "extract_keyframes" if isinstance(value, str) and value in ALIASES else value if isinstance(value, str) else None

def envelope(doc):
    if not isinstance(doc, dict):
        raise ValueError("invalid_source_shape")
    item = doc.get("envelope", doc)
    if not isinstance(item, dict):
        raise ValueError("missing_terminal_envelope")
    job = doc.get("job_id") or item.get("job_id")
    if not isinstance(job, str) or not UUID.fullmatch(job):
        raise ValueError("missing_valid_job_identity")
    if item.get("job_id") != job:
        raise ValueError("wrapper_envelope_job_mismatch")
    if item.get("connector_id") != "public-video-media" or operation(item.get("operation")) not in OPERATIONS:
        raise ValueError("source_scope_mismatch")
    if "envelope" in doc:
        if "connector_id" in doc and doc["connector_id"] != item["connector_id"]:
            raise ValueError("wrapper_envelope_connector_mismatch")
        if "operation" in doc and operation(doc["operation"]) != operation(item["operation"]):
            raise ValueError("wrapper_envelope_operation_mismatch")
    if item.get("status") not in STATUS or ("envelope" in doc and doc.get("status") not in JOB_STATUS):
        raise ValueError("source_not_terminal")
    if "envelope" in doc and (doc["status"] == "cancelled" or (doc["status"] == "failed" and item["status"] != "failed")):
        raise ValueError("wrapper_envelope_status_mismatch")
    return job, item

class Reader:
    def __init__(self, root):
        candidate = Path(root)
        if any(p.is_symlink() for p in (candidate, *candidate.parents)):
            raise ValueError("source_root_symlink")
        self.root = candidate.resolve(strict=True)
        self.files, self.total = {}, 0

    def read(self, relative):
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".json":
            raise ValueError("source_path_invalid")
        path = self.root / relative
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve(strict=True).is_relative_to(self.root):
            raise ValueError("source_path_outside_root")
        path = path.resolve(strict=True)
        if path in self.files:
            return self.files[path]
        if len(self.files) >= MAX_FILES:
            raise ValueError("source_budget_exceeded")
        remaining = MAX_TOTAL_BYTES - self.total
        read_limit = min(MAX_FILE_BYTES, remaining)
        if path.stat().st_size > read_limit:
            raise ValueError("source_budget_exceeded")
        with path.open("rb") as source:
            data = source.read(read_limit + 1)
        if len(data) > MAX_FILE_BYTES or self.total + len(data) > MAX_TOTAL_BYTES:
            raise ValueError("source_budget_exceeded")
        value = json.loads(data)
        result = value, {"file_bytes": len(data), "file_sha256": digest(data)}
        self.files[path] = result
        self.total += len(data)
        return result

def frames_metadata(doc, item):
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    frames = data.get("frames") if isinstance(data.get("frames"), list) else []
    artifacts = doc.get("artifacts", data.get("artifacts", []))
    artifacts = artifacts if isinstance(artifacts, list) else []
    result, invalid = [], 0
    for frame in frames:
        if not isinstance(frame, dict):
            invalid += 1
            continue
        ref, sha, size, sec = (frame.get(k) for k in ("object_ref", "sha256", "bytes", "t_seconds"))
        if not (isinstance(ref, str) and 0 < len(ref) <= 2048 and isinstance(sha, str) and SHA.fullmatch(sha)
                and type(size) is int and size > 0 and number(sec)):
            invalid += 1
            continue
        matching = [a for a in artifacts if isinstance(a, dict) and a.get("object_ref") == ref]
        artifact_match = (len(matching) == 1 and matching[0].get("kind") == "keyframes"
                          and matching[0].get("sha256") == sha and matching[0].get("bytes") == size)
        result.append({"timestamp_seconds": sec, "frame_sha256": sha, "frame_bytes": size,
                       "object_ref_sha256": digest(ref.encode()), "artifact_matches": artifact_match})
    for row in result:
        row["unique_timestamp"] = sum(isinstance(f, dict) and f.get("t_seconds") == row["timestamp_seconds"] for f in frames) == 1
    return result, invalid

def project(reader, plan_path, sources_path, manifest_path=None):
    plan, plan_meta = reader.read(plan_path)
    if not isinstance(plan, dict) or plan.get("schema_version") != "media-job-plan.v1" or not ID.fullmatch(str(plan.get("analysis_id", ""))):
        raise ValueError("invalid_plan_identity")
    slots = {}
    for row in plan.get("jobs", []):
        if not isinstance(row, dict) or not ID.fullmatch(str(row.get("content_id", ""))):
            raise ValueError("invalid_plan_content_identity")
        for op in row.get("operations", []):
            if not isinstance(op, dict) or op.get("operation") not in OPERATIONS or not isinstance(op.get("params"), dict):
                raise ValueError("invalid_plan_operation")
            key = row["content_id"], op["operation"]
            if key in slots:
                raise ValueError("duplicate_plan_slot")
            slots[key] = op["params"]
    if not slots or len(slots) > 60:
        raise ValueError("invalid_plan_size")
    sources, sources_meta = reader.read(sources_path)
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 60
            or any(not isinstance(s, dict) or set(s) - {"terminal", "request_projection"}
                   or not isinstance(s.get("terminal"), str)
                   or ("request_projection" in s and not isinstance(s["request_projection"], str)) for s in sources)):
        raise ValueError("invalid_source_file_list")
    terminal, projections, rejected = {}, {}, 0
    for destination, key in ((terminal, "terminal"), (projections, "request_projection")):
        for path in dict.fromkeys(s[key] for s in sources if key in s):
            doc, meta = reader.read(path)
            try:
                job, item = envelope(doc)
            except ValueError:
                rejected += 1
                continue
            destination.setdefault(job, []).append((doc, item, meta))
    rows, covered = [], set()
    for job, candidates in sorted(terminal.items()):
        if len(candidates) != 1:
            rows.append({"job_id": job, "binding": "unknown", "gap": "ambiguous_terminal_copies"})
            continue
        doc, item, meta = candidates[0]
        op = operation(item["operation"])
        copies = projections.get(job, [])
        matched_slots = []
        projection_meta = None
        if len(copies) == 1:
            projected_doc, projected, projection_meta = copies[0]
            request = projected.get("request")
            if (isinstance(request, dict) and operation(projected["operation"]) == op
                    and isinstance(item.get("raw_sha256"), str) and SHA.fullmatch(item["raw_sha256"])
                    and projected.get("raw_sha256") == item.get("raw_sha256")
                    and projected.get("status") == item.get("status")
                    and canonical_hash(projected.get("data")) == canonical_hash(item.get("data"))):
                matched_slots = [key for key, params in slots.items() if key[1] == op and canonical_hash(params) == canonical_hash(request)]
        match = matched_slots[0] if len(matched_slots) == 1 else None
        if match:
            covered.add(match)
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        limitations = item.get("limitations") if isinstance(item.get("limitations"), list) else []
        frames, invalid_frames = frames_metadata(doc, item) if op == "extract_keyframes" else ([], 0)
        row = {"job_id": job, "planned_operation": op, "actual_operation": item["operation"],
               "job_status": doc["status"] if "envelope" in doc else None,
               "terminal_status": item["status"], "partial": item["status"] == "completed_partial",
               "binding": "request_projection_matches" if match else "unknown",
               "content_id": match[0] if match else None, "source": meta,
               "request_projection_source": projection_meta, "raw_sha256": item.get("raw_sha256") if isinstance(item.get("raw_sha256"), str) and SHA.fullmatch(item["raw_sha256"]) else None,
               "limitations_count": len(limitations), "limitations_sha256": canonical_hash(limitations),
               "origin": data.get("origin") if isinstance(data.get("origin"), str) and data["origin"] in ORIGINS else "unknown",
               "frames": frames, "invalid_frame_count": invalid_frames,
               "data_sha256": canonical_hash(item.get("data"))}
        if op == "fetch_transcript":
            cues = data.get("cues", [])
            row["cue_count"] = len(cues) if isinstance(cues, list) else None
        rows.append(row)
    counts = {}
    for row in rows:
        content = row.get("content_id")
        if content:
            key = content, row["planned_operation"]
            counts[key] = counts.get(key, 0) + 1
    missing = [{"content_id": content, "operation": op, "gap": "request_bound_terminal_absent"}
               for content, op in slots if (content, op) not in covered]
    ambiguous = [{"content_id": content, "operation": op, "gap": "multiple_issued_job_attempts"}
                 for (content, op), count in counts.items() if count > 1]
    manifest = {"presence": "absent"}
    if manifest_path:
        value, meta = reader.read(manifest_path)
        manifest = {"presence": "present", **meta,
                    "status": value.get("status") if isinstance(value, dict) and value.get("status") in {"ok", "failed", "running", "reserved"} else "unknown"}
    return {"schema_version": "media-audit-metadata.v1", "analysis_id": plan["analysis_id"],
            "plan": plan_meta, "source_file_list": sources_meta, "planned_slot_count": len(slots), "terminal_jobs": rows,
            "missing_slots": missing, "multiple_job_slots": ambiguous, "rejected_source_count": rejected,
            "manifest": manifest, "source_files_read": len(reader.files), "source_bytes_read": reader.total,
            "source_origin_attested": False, "image_delivery_proven": False, "complete_case_pass": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--sources", required=True, help="JSON array of explicit terminal/request_projection paths, no claims")
    parser.add_argument("--manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reader = Reader(args.root)
    result = project(reader, args.plan, args.sources, args.manifest)
    output = Path(args.output)
    if (output.name != "media-audit.json" or ".." in output.parts
            or any(p.is_symlink() for p in (output, *output.parents))
            or not (output.parent == Path("/out/deliver")
                    or output.parent.resolve().is_relative_to(reader.root))
            or output.resolve() in reader.files):
        raise ValueError("output_path_invalid")
    encoded = (json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    if len(encoded) > MAX_FILE_BYTES:
        raise ValueError("audit_artifact_budget_exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as target:
        target.write(encoded)
    print(json.dumps({"written": True, "artifact_bytes": len(encoded),
                      "planned_slots": result["planned_slot_count"], "complete_case_pass": False}))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        raise SystemExit("audit_projection_failed")
