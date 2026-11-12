#!/usr/bin/env python3
"""Read shared short-video opening methods for a change card, without new evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_video_sources  # noqa: E402
from hook_core.context import prepare_context
from hook_core.common import read_json, write_json


def build(platform: str, pattern_ids: list[str] | None = None) -> dict:
    if platform not in public_video_sources.platform_ids():
        raise ValueError("unsupported video platform")
    context = prepare_context({})
    # 只按形态（short_video）选，不按 applicability.platforms 选：那一栏记的是模式样本取自哪些平台
    # （evidence_scope 写明「Source samples, not a platform-wide effectiveness claim」），不是适用范围。
    # 十五个开场模式都是通用的短视频开场方法，支持清单里的任一平台都给同一组；knowledge.json 与方法都不改。
    # 原来三个平台在十五个模式里都列着，所以它们拿到的结果与以前逐字相同。
    modes = [p for p in context["pattern_candidates"] if p["applicability"]["form"] == "short_video"]
    if pattern_ids is not None and (not 1 <= len(pattern_ids) <= 3 or len(set(pattern_ids)) != len(pattern_ids)
                                  or set(pattern_ids) - {p["id"] for p in modes}):
        raise ValueError("select one to three unique known pattern IDs")
    keys = (("id", "name", "route", "overlay", "visual", "sound", "joint_expression", "material_requirements",
             "applicability", "exceptions")
            if pattern_ids else ("id", "name", "material_requirements"))
    # Historical sample links stay out: they are method context, never this video's evidence.
    return {"kind": "HookResearchContext", "purpose": "video_opening", "platform": platform,
            "basis": context["basis"], "material_basis": context["material_basis"],
            "pattern_candidates": [{k: p[k] for k in keys} for p in modes if not pattern_ids or p["id"] in pattern_ids],
            "provenance": context["provenance"], "media_execution": "not_requested",
            "scope": "Short-video opening methods for the next cut, not an observation of this video, "
                     "its performance, or a long-form hook window."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=public_video_sources.platform_ids())
    parser.add_argument("--pattern-id", action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(args.platform, args.pattern_id)
        if args.output.exists():
            if read_json(args.output) != result:
                raise ValueError("existing context differs; preserve it and choose a fresh output")
        else:
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
