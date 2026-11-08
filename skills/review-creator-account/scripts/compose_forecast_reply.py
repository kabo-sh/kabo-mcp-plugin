#!/usr/bin/env python3
"""Compose a complete forecast handoff by recomputing each supplied input."""
import argparse
import json
import hashlib
from pathlib import Path

from estimate_growth import estimate, render_report, with_snapshot
from delivery_language import DeliveryLanguage


def compose(inputs, resolved_scope, question=None, snapshot=None, snapshot_source=None, correct_prior=False,
            missing_metrics=(), horizon_days=None, report_language="en", translations=None):
    """重算独立指标并检查目标一致，保留可算结果与缺失输入。"""
    required = {"platform", "target", "request_quote", "reference"}
    if not isinstance(resolved_scope, dict):
        raise ValueError("forecast_scope.json must be an object with platform, target, request_quote and reference")
    # 明确指出缺失、额外及类型错误字段，避免模型反复重写本来正确的值。
    missing = sorted(required - set(resolved_scope))
    extra = sorted(set(resolved_scope) - required)
    invalid = sorted(key for key in required & set(resolved_scope)
                     if not isinstance(resolved_scope[key], str) or not resolved_scope[key].strip())
    problems = []
    if missing:
        problems.append("missing fields: " + ", ".join(missing))
    if extra:
        problems.append("unexpected fields: " + ", ".join(extra))
    if invalid:
        problems.append("must be nonempty strings: " + ", ".join(invalid))
    if problems:
        raise ValueError("forecast_scope.json: " + "; ".join(problems)
                         + ". Keep exactly platform, target, request_quote and reference. "
                         "Pass horizon_days in calculation inputs or --horizon-days, not in the scope file.")
    if missing_metrics and (len(set(missing_metrics)) != len(missing_metrics) or any(
        metric not in ("subscribers", "followers", "views", "likes", "comments") for metric in missing_metrics
    )):
        raise ValueError("Missing metrics must be unique cumulative subscribers, followers, views, likes or comments")
    if horizon_days is not None and not missing_metrics:
        raise ValueError("--horizon-days is only used with --missing-metric; actual inputs carry their own horizon")
    documents = [json.loads(source.read_text(encoding="utf-8")) for source in inputs]
    # 缺测量时由同一已解析范围构造合法合同；不补造日期、观测或增长假设。
    documents.extend({
        "schema_version": "growth-input.v1", "mode": "observed_pace", "horizon_days": horizon_days,
        "scope": {"platform": resolved_scope["platform"], "account": resolved_scope["target"],
                  "metric": metric, "semantics": "cumulative_stock"}, "observations": [],
    } for metric in missing_metrics)
    results = []
    target = (resolved_scope["platform"], resolved_scope["target"])
    seen = set()
    for data in documents:
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
    t = DeliveryLanguage(report_language, translations)
    lines = [t("# Requested outlook for {0} ({1})", target[1], target[0]), ""]
    if correct_prior:
        lines += [t("Earlier unsupported numeric forecasts or odds should not be treated as measured predictions."), ""]
    for result in results:
        lines += [t("## {0} / {1:g}-day horizon", t(result["scope"]["metric"]), result["horizon_days"]), "", render_report(result, t).strip(), ""]
    lines += [t("Occurrence probabilities are unavailable from these calculations. More records may enable conditional arithmetic, not calibrated percentage chances."), ""]
    t.validate()
    return results, "\n".join(lines)


def main():
    """校验命令输入和输出路径，写出可直接交付的完整预测回复。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--missing-metric", action="append", default=[],
                        help="Cumulative metric with no usable dated observations or user rate; repeat for each missing metric")
    parser.add_argument("--horizon-days", type=float, help="Resolved requested horizon for missing metrics only")
    parser.add_argument("--scope-file", type=Path, required=True)
    parser.add_argument("--question-file", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--correct-prior", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="Complete Markdown handoff")
    parser.add_argument("--report-language", default="en", help="Requested reply language, independent of history or host locale")
    parser.add_argument("--translations-file", type=Path, help="Non-English template translations; all substitutions remain script-bound")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".md":
        parser.error("--output must be a .md file")
    sources = {p.resolve() for p in [*args.input, args.scope_file, args.question_file, args.snapshot, args.translations_file] if p is not None}
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
            args.missing_metric,
            args.horizon_days,
            args.report_language,
            json.loads(args.translations_file.read_text(encoding="utf-8")) if args.translations_file else None,
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    args.output.write_text(report, encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps({"schema_version": "forecast-reply.v1", "report_language": args.report_language, "results": results}, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"delivery_ready": True, "response_mode": "verbatim", "report_language": args.report_language,
                      "characters": len(report), "sha256": hashlib.sha256(report.encode()).hexdigest()}, ensure_ascii=False))
    print("The final answer is already written in the requested language. Copy the entire payload below, "
          "without the markers. Do not introduce, translate, shorten, recalculate or append another answer.")
    print("KABO_FORECAST_REPLY_BEGIN")
    print(report, end="")
    print("KABO_FORECAST_REPLY_END")


if __name__ == "__main__":
    main()
