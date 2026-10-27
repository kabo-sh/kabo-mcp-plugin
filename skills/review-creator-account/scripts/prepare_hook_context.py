#!/usr/bin/env python3
"""Compact method input for an existing research synthesis; no media or model call."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from hook_core.context import prepare_context
from hook_core.common import HookError, envelope, read_json, write_json

PURPOSES = {
    "account_review": "Add one practical opening experiment to the existing test recommendations. Use the creator's own available material; confirm unprovided assets.",
    "deep_review": "Use the existing watched-video frames/cues to describe available opening evidence, then give a concrete opening change in existing craft/next-shoot fields. Method inventory is not a video observation.",
    "trends": "Turn the already selected short-video mechanism into a feasible opening in the existing angle/differentiation fields. Do not alter ranking or fetch media.",
    "competitors": "Add a feasible opening variation to existing differentiation/idea handoff. Keep competitor evidence and audience-comment claims on their original sources.",
}


def build_research_context(platform: str, purpose: str, pattern_ids: list[str] | None = None) -> dict:
    if platform not in ("instagram", "youtube", "tiktok") or purpose not in PURPOSES:
        raise ValueError("use a supported platform and research purpose")
    context = prepare_context({})
    if pattern_ids is not None and (not 1 <= len(pattern_ids) <= 3 or len(set(pattern_ids)) != len(pattern_ids)
                                  or set(pattern_ids) - {p["id"] for p in context["pattern_candidates"]}):
        raise ValueError("select one to three unique known pattern IDs")
    keys = (("id", "name", "route", "overlay", "visual", "sound", "joint_expression", "material_requirements", "applicability", "exceptions")
            if pattern_ids is not None else ("id", "name", "material_requirements"))
    modes = [{key: p[key] for key in keys} for p in context["pattern_candidates"]
             if platform in p["applicability"]["platforms"] and (pattern_ids is None or p["id"] in pattern_ids)]
    # Historical links are lookup context, never new current-task evidence.
    references = []
    for mode in modes if pattern_ids is not None else []:
        matches = [r for r in context["reference_examples"] if mode["id"] in r["pattern_ids"]]
        matching_platform = [r for r in matches if r["platform"] == platform]
        if matching_platform or matches:
            references.append({"pattern_id": mode["id"], **(matching_platform or matches)[0]})
    return {"contract_version": context["contract_version"], "core_version": context["core_version"],
            "kind": "HookResearchContext", "basis": context["basis"], "material_basis": context["material_basis"],
            "platform": platform, "purpose": purpose, "pattern_candidates": modes,
            "reference_examples": references, "provenance": context["provenance"],
            "consumption": PURPOSES[purpose],
            "scope": "Short-video method reference; assets unconfirmed. No additional viewing/listening evidence or long-video timing rule.",
            "details": f"Read selected IDs via {Path(__file__).resolve()} --pattern-id in the same synthesis.",
            "media_execution": "not_requested"}


def build_research_context_ref(platform: str, purpose: str) -> dict:
    """Keep existing compact business inputs compact; details are read on demand."""
    context = build_research_context(platform, purpose)
    return {"basis": context["basis"], "material_basis": context["material_basis"], "purpose": purpose,
            "pattern_catalog": {p["id"]: p["name"] for p in context["pattern_candidates"]},
            "details": "Read selected IDs using prepare_hook_context.py --pattern-id in this synthesis."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("instagram", "youtube", "tiktok"))
    parser.add_argument("--purpose", required=True, choices=tuple(PURPOSES))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pattern-id", action="append")
    args = parser.parse_args()
    try:
        result = build_research_context(args.platform, args.purpose, args.pattern_id)
        if args.output:
            if args.output.exists():
                if read_json(args.output) != result:
                    raise ValueError("existing context differs from this configuration; preserve it and use a fresh run")
            else:
                write_json(args.output, result)
    except (HookError, ValueError, OSError) as error:
        print(json.dumps(envelope("HookFailure", status="failed", code=getattr(error, "code", "invalid_request"), message=str(error))), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
