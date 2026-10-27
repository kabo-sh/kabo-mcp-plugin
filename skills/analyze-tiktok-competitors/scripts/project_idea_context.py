#!/usr/bin/env python3
"""Select the minimal Idea context from one validated CompetitorResearchReport V3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FIELDS = (
    "pattern", "mechanism", "audience_problem", "content_promise", "angle",
    "recommended_formats", "why_now", "creator_fit", "differentiation",
    "must_avoid", "proof_points",
)
FORBIDDEN = {
    "seed_id", "report_id", "schema_version", "url", "evidence_id",
    "evidence_refs", "calculation_ref", "confidence", "freshness", "status",
}


def project(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "competitor-research-report.v3":
        raise ValueError("report must be competitor-research-report.v3")
    items = []
    for pattern in report.get("patterns") or []:
        if not isinstance(pattern, dict):
            raise ValueError("every pattern must be an object")
        selected = {field: pattern[field] for field in FIELDS}
        selected["gaps"] = [
            gap["summary"] for gap in report.get("gaps") or []
            if isinstance(gap, dict) and set(gap.get("content_refs") or []) & set(pattern.get("content_refs") or [])
        ]
        items.append(selected)
    result = {"competitor": items}
    leaked = FORBIDDEN & set().union(*(set(item) for item in items)) if items else set()
    if leaked:
        raise ValueError(f"Idea context leaked forbidden fields: {sorted(leaked)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = project(json.loads(args.report.read_text(encoding="utf-8")))
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
