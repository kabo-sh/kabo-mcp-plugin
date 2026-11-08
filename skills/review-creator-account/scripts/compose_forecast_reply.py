#!/usr/bin/env python3
"""Compose a complete forecast handoff by recomputing each supplied input."""
import argparse
import json
from pathlib import Path

from estimate_growth import estimate, render_report, with_snapshot


def compose(inputs, resolved_scope, question=None, snapshot=None, snapshot_source=None, correct_prior=False):
    required = {"platform", "target", "request_quote", "reference"}
    if not isinstance(resolved_scope, dict) or set(resolved_scope) != required or any(
        not isinstance(resolved_scope[key], str) or not resolved_scope[key].strip() for key in required
    ):
        raise ValueError("Scope needs platform, target, verbatim target-setting request_quote and resolved reference")
    results = []
    target = (resolved_scope["platform"], resolved_scope["target"])
    seen = set()
    for source in inputs:
        data = json.loads(source.read_text(encoding="utf-8"))
        if "_snapshot_cadence" in data:
            raise ValueError("_snapshot_cadence must come from the original snapshot")
        if snapshot is not None and data.get("mode") == "content_scenario":
            data = with_snapshot(data, snapshot, snapshot_source)
        result = estimate(data, question)
        scope = result["scope"]
        identity = (scope["platform"], scope["account"])
        if target != identity:
            raise ValueError("One handoff must keep one resolved target; do not combine an account and a post")
        key = (scope["metric"], result["horizon_days"])
        if key in seen:
            raise ValueError("Duplicate metric and horizon; resolve the conflicting inputs")
        seen.add(key)
        results.append(result)
    if not results:
        raise ValueError("At least one calculation input is required")
    lines = [f"# Requested outlook for {target[1]} ({target[0]})", ""]
    if correct_prior:
        lines += ["Earlier unsupported numeric forecasts or odds should not be treated as measured predictions.", ""]
    for result in results:
        lines += [f"## {result['scope']['metric']} / {result['horizon_days']:g}-day horizon", "", render_report(result).strip(), ""]
    lines += ["Occurrence probabilities are unavailable from these calculations. More records may enable conditional arithmetic, not calibrated percentage chances.", ""]
    return results, "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--scope-file", type=Path, required=True)
    parser.add_argument("--question-file", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--correct-prior", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="Complete Markdown handoff")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".md":
        parser.error("--output must be a .md file")
    sources = {p.resolve() for p in [*args.input, args.scope_file, args.question_file, args.snapshot] if p is not None}
    if any(p.resolve() in sources for p in [args.output, args.output.with_suffix(".json")]):
        parser.error("Output artifacts must not overwrite input evidence")
    try:
        results, report = compose(
            args.input,
            json.loads(args.scope_file.read_text(encoding="utf-8")),
            args.question_file.read_text(encoding="utf-8") if args.question_file else None,
            json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None,
            str(args.snapshot) if args.snapshot else None,
            args.correct_prior,
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    args.output.write_text(report, encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps({"schema_version": "forecast-reply.v1", "results": results}, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("KABO_FORECAST_REPLY_BEGIN")
    print(report, end="")
    print("KABO_FORECAST_REPLY_END")


if __name__ == "__main__":
    main()
