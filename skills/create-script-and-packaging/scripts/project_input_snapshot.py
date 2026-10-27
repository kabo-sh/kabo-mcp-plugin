#!/usr/bin/env python3
"""Write a ScriptPackage's input_snapshot from the request and the SelectedIdea it names.

The snapshot freezes what the package was written against: the selected idea's ids, title and
promise, the confirmed audience and action, the request's platform, format and language, and the
idea's context refs, evidence refs, must_differ rules, required assets and risks. Every one of those
already sits in a file. The model used to retype them into the package; the validator caught a
changed title or promise but not a dropped risk or a required asset nobody carried forward.

Here the model writes the package without worrying about the snapshot, then:

  python3 scripts/project_input_snapshot.py --request script-package-request.json \\
    --into script_package.json [--evidence-basis hypothesis]

The evidence basis is `source_backed` when the idea carries evidence refs, and otherwise
`brief_based`, or `hypothesis` when you pass it: the one judgment here that is yours.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

UNBACKED = ("brief_based", "hypothesis")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must hold a JSON object")
    return value


def selected_idea(request: dict[str, Any], request_path: Path) -> dict[str, Any]:
    reference = request.get("selected_idea") or {}
    relative = reference.get("path") if isinstance(reference, dict) else None
    if not isinstance(relative, str) or not relative:
        raise ValueError("the request names no selected_idea.path")
    path = Path(relative)
    path = path if path.is_absolute() else request_path.parent / path
    if not path.is_file():
        raise ValueError(f"the SelectedIdea {relative} does not exist yet: build or copy it first")
    return load(path)


def project(request: dict[str, Any], selected: dict[str, Any], evidence_basis: str | None = None) -> dict[str, Any]:
    idea = selected.get("idea")
    constraints = selected.get("confirmed_constraints")
    if not isinstance(idea, dict) or not isinstance(constraints, dict):
        raise ValueError("the SelectedIdea has no idea or confirmed_constraints object")
    evidence_refs = list(idea.get("evidence_refs") or [])
    if evidence_refs:
        if evidence_basis not in (None, "source_backed"):
            raise ValueError(f"the idea carries evidence refs, so its basis is source_backed, not {evidence_basis}")
        basis = "source_backed"
    else:
        if evidence_basis == "source_backed":
            raise ValueError("the idea carries no evidence refs, so it cannot be source_backed")
        basis = evidence_basis or "brief_based"
    snapshot = {
        "selected_idea_id": selected.get("selected_idea_id"),
        "source_candidate_id": selected.get("source_candidate_id"),
        "working_title": idea.get("working_title"),
        "content_promise": idea.get("content_promise"),
        "audience": constraints.get("audience"),
        "desired_audience_action": constraints.get("desired_audience_action"),
        "platform": request.get("platform"),
        "format": (request.get("content_format") or {}).get("kind"),
        "language": request.get("language"),
        "evidence_basis": basis,
        "source_context_refs": list(idea.get("source_context_refs") or []),
        "evidence_refs": evidence_refs,
        "must_differ": list(idea.get("must_differ") or []),
        "required_assets": list(idea.get("required_assets") or []),
        "risks": list(idea.get("risks") or []),
    }

    if request.get("supplemental_evidence") is not None:
        supplemental = request["supplemental_evidence"]
        if not isinstance(supplemental, dict):
            raise ValueError("supplemental_evidence must be an object or null")
        snapshot["supplemental_evidence"] = dict(supplemental)
    if request.get("duration_plan") is not None:
        duration_plan = request["duration_plan"]
        if not isinstance(duration_plan, dict):
            raise ValueError("duration_plan must be an object")
        import copy
        snapshot["duration_plan"] = copy.deepcopy(duration_plan)
    return snapshot

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--into", type=Path, help="script_package.json to write input_snapshot into")
    parser.add_argument("--output", type=Path, help="also write the snapshot alone here")
    parser.add_argument("--evidence-basis", choices=["source_backed", *UNBACKED],
                        help="only for an idea without evidence refs: hypothesis instead of brief_based")
    args = parser.parse_args()
    try:
        if args.into is None and args.output is None:
            raise ValueError("pass --into script_package.json, --output, or both")
        request = load(args.request)
        snapshot = project(request, selected_idea(request, args.request.resolve()), args.evidence_basis)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.into:
            package = load(args.into)
            package["input_snapshot"] = snapshot
            args.into.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "evidence_basis": snapshot["evidence_basis"],
                      "selected_idea_id": snapshot["selected_idea_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
