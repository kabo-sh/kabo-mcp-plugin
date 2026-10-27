#!/usr/bin/env python3
"""Build a complete, validated audit manifest for one Script package run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import sys
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
import render_script_package
import validate_script_package


SKILL_ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def skill_identity() -> dict[str, str]:
    """Read this Skill's id and version from the SKILL.md frontmatter.

    manifest.json 已按 Kabo Skills 规范删除，版本号改记在 frontmatter 的 metadata.version；
    这里只认 name 与 metadata 下的 version 两行，不引入 YAML 依赖。
    """
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    lines = text.split("\n")
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if not lines or lines[0].strip() != "---" or end is None:
        raise ValueError("SKILL.md has no frontmatter")
    front = lines[1:end]
    identity: dict[str, str] = {}
    in_metadata = False
    for line in front:
        if not line.strip():
            continue
        indented = line[:1] in (" ", "\t")
        key, _, value = line.strip().partition(":")
        value = value.strip().strip('"').strip("'")
        if not indented:
            in_metadata = key == "metadata"
            if key == "name":
                identity["name"] = value
        elif in_metadata and key == "version":
            identity["version"] = value
    if not identity.get("name") or not identity.get("version"):
        raise ValueError("SKILL.md frontmatter needs name and metadata.version")
    return identity


def write_private(path: Path, value: str) -> None:
    """Create/truncate a private artifact without a world-readable permission window."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            handle.write(value)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def run_relative_file(path: Path, run_root: Path, label: str) -> tuple[Path, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {path}")
    try:
        # Both sides resolved. The left one always is, so comparing it against an unresolved root
        # asks whether a resolved path sits under an unresolved one, and the answer is no as soon
        # as any parent of the run directory is a symlink: on macOS /var is /private/var, so a run
        # rooted under /var had every file inside it reported as escaping its own run root. The
        # same correction is in plan-content-calendar's build_content_calendar.
        relative = resolved.relative_to(run_root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes --run-root: {path}") from error
    logical = relative.as_posix()
    if not logical or logical == ".":
        raise ValueError(f"{label} has no run-root-relative path")
    return resolved, logical


def output_relative_path(path: Path, run_root: Path) -> tuple[Path, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(run_root.resolve())  # see run_relative_file
    except ValueError as error:
        raise ValueError(f"manifest output escapes --run-root: {path}") from error
    logical = relative.as_posix()
    if not logical or logical == ".":
        raise ValueError("manifest output has no run-root-relative path")
    return resolved, logical


def file_record(resolved: Path, logical: str) -> dict[str, Any]:
    content = resolved.read_bytes()
    return {
        "path": logical,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def resolve_reference(request_path: Path, ref: dict[str, Any], label: str) -> Path:
    """Resolve an explicitly typed artifact reference relative to its request."""
    if not isinstance(ref, dict):
        raise ValueError(f"{label} must be an artifact reference object")
    value = ref.get("path")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}.path is required")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else request_path.parent / candidate


def referenced_sources(request: dict[str, Any], request_path: Path, run_root: Path) -> list[tuple[str, Path]]:
    """Collect source files, including captured supplementary inputs."""
    selected = request.get("selected_idea")
    if not isinstance(selected, dict):
        raise ValueError("request.selected_idea is required")
    values: list[tuple[str, Path]] = [
        ("selected_idea", resolve_reference(request_path, selected, "selected_idea"))
    ]
    for field in ("creator_profile", "source_script_package"):
        ref = request.get(field)
        if ref is not None:
            if not isinstance(ref, dict):
                raise ValueError(f"request.{field} must be an artifact reference or null")
            values.append((field, resolve_reference(request_path, ref, field)))
    if request.get('supplemental_evidence') is not None:
        ref = request['supplemental_evidence']
        path = resolve_reference(request_path, ref, 'supplemental_evidence')
        path, _ = run_relative_file(path, run_root, 'supplemental_evidence')
        artifact = load(path)
        values.append(('supplemental_evidence', path))
        values.append(('supplemental_evidence_input', resolve_reference(path, artifact.get('input'), 'supplemental_evidence.input')))
    videos = request.get("video_analysis_sources") or []
    if not isinstance(videos, list):
        raise ValueError("request.video_analysis_sources must be an array")
    for index, ref in enumerate(videos):
        if not isinstance(ref, dict):
            raise ValueError(f"video_analysis_sources[{index}] must be an artifact reference")
        label = f"video_analysis_sources[{index}]"
        values.append((label, resolve_reference(request_path, ref, label)))
    return values


def checked_records(
    values: list[tuple[str, Path]],
    run_root: Path,
    seen: dict[str, str],
) -> list[dict[str, Any]]:
    records = []
    for label, path in values:
        resolved, logical = run_relative_file(path, run_root, label)
        previous = seen.get(logical)
        if previous is not None:
            raise ValueError(f"duplicate run path {logical!r}: {previous} and {label}")
        seen[logical] = label
        records.append(file_record(resolved, logical))
    return records


def build(
    request_path: Path,
    package_path: Path,
    concise_path: Path,
    full_path: Path,
    *,
    run_root: Path,
    output_path: Path,
    run_id: str,
    runtime: str,
    model: str,
) -> dict[str, Any]:
    """Build the native artifact after validating its inputs."""
    run_root = run_root.resolve()
    if not run_root.is_dir():
        raise ValueError(f"--run-root is not a directory: {run_root}")
    for field, value in (("run_id", run_id), ("runtime", runtime), ("model", model)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")

    request_resolved, request_logical = run_relative_file(request_path, run_root, "request")
    package_resolved, _ = run_relative_file(package_path, run_root, "package")
    concise_resolved, _ = run_relative_file(concise_path, run_root, "concise report")
    full_resolved, _ = run_relative_file(full_path, run_root, "full report")
    _, output_logical = output_relative_path(output_path, run_root)

    request = load(request_resolved)
    package = load(package_resolved)
    seen: dict[str, str] = {request_logical: "request"}
    source_records = [file_record(request_resolved, request_logical)]
    source_records.extend(
        checked_records(
            referenced_sources(request, request_resolved, run_root),
            run_root,
            seen,
        )
    )
    artifact_records = checked_records(
        [
            ("package", package_resolved),
            ("concise report", concise_resolved),
            ("full report", full_resolved),
        ],
        run_root,
        seen,
    )
    if output_logical in seen:
        raise ValueError(
            f"manifest output path {output_logical!r} collides with {seen[output_logical]}"
        )

    errors = validate_script_package.validate_package(package, request, request_resolved, run_root=run_root)
    if errors:
        raise ValueError("package validation failed: " + "; ".join(errors))

    expected_concise = render_script_package.concise(package)
    expected_full = render_script_package.full(package)
    if concise_resolved.read_text(encoding="utf-8") != expected_concise:
        raise ValueError("concise report differs from the deterministic package projection")
    if full_resolved.read_text(encoding="utf-8") != expected_full:
        raise ValueError("full report differs from the deterministic package projection")

    fallback_values = (package.get("provenance") or {}).get("fallback") or []
    if not isinstance(fallback_values, list) or not all(
        isinstance(item, str) and item.strip() for item in fallback_values
    ):
        raise ValueError("package provenance.fallback must contain only non-empty strings")
    fallbacks = list(dict.fromkeys(fallback_values))
    plugin_manifest = skill_identity()
    manifest = {
        "schema_version": "script-run-manifest.v1",
        "run_id": run_id,
        "request_id": package["request_id"],
        "package_id": package["package_id"],
        "skill": {
            "id": plugin_manifest["name"],
            "version": plugin_manifest["version"],
        },
        "runtime": {"host": runtime, "model": model},
        "validation": {
            "status": "passed",
            "validator": "scripts/validate_script_package.py",
        },
        "source_contributions": source_records,
        "fallbacks": fallbacks,
        "artifacts": artifact_records,
    }
    manifest_errors: list[str] = []
    validate_script_package.validate_json_schema(
        manifest,
        validate_script_package.RUN_MANIFEST_SCHEMA,
        "run manifest",
        manifest_errors,
    )
    if manifest_errors:
        raise ValueError("run manifest schema validation failed: " + "; ".join(manifest_errors))
    return manifest


STANDARD_NAME = "run-manifest.json"
LEGACY_NAME = "run_manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--concise", type=Path, required=True)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, help="default: <run-root>/run-manifest.json")
    args = parser.parse_args()
    # Every Kabo run directory keeps its run record as `run-manifest.json`; the legacy underscore
    # name some runs still pass is written under the standard name beside it.
    if args.output is None:
        args.output = args.run_root / STANDARD_NAME
    elif args.output.name == LEGACY_NAME:
        args.output = args.output.with_name(STANDARD_NAME)
    try:
        manifest = build(
            args.request,
            args.package,
            args.concise,
            args.full,
            run_root=args.run_root,
            output_path=args.output,
            run_id=args.run_id,
            runtime=args.runtime,
            model=args.model,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_private(
            args.output,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
