#!/usr/bin/env python3
"""Project a validated AccountReviewReport V3 into compact Idea context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_VERSION = "account-review-report.v3"
FORBIDDEN_KEYS = {
    "schema_version", "report_id", "profile_id", "status", "snapshot_id",
    "source_mode", "content_id", "title", "url",
}


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def require_non_empty_format_classification(value: Any, label: str) -> None:
    classification = require_object(value, label)
    for field in ("confidence_counts", "source_counts"):
        if field not in classification:
            raise ValueError(f"{label} missing {field}")
        counts = require_object(classification[field], f"{label}.{field}")
        if not counts:
            raise ValueError(f"{label}.{field} must not be empty")


def project_metric_summaries(metrics: Any, label: str) -> dict[str, Any]:
    source = require_object(metrics, label)
    result: dict[str, Any] = {}
    for metric, summary_value in source.items():
        summary = require_object(summary_value, f"{label}.{metric}")
        for key in ("available_n", "median", "mean"):
            if key not in summary:
                raise ValueError(f"{label}.{metric} missing {key}")
        result[metric] = {
            "available_n": summary["available_n"],
            "median": summary["median"],
            "mean": summary["mean"],
        }
    return result


def project_baselines(rows: Any) -> list[dict[str, Any]]:
    result = []
    for index, value in enumerate(require_list(rows, "baselines")):
        row = require_object(value, f"baselines[{index}]")
        for key in ("format", "maturity_days", "sample_size", "metrics"):
            if key not in row:
                raise ValueError(f"baselines[{index}] missing {key}")
        projected = {
            "format": row["format"],
            "maturity_days": row["maturity_days"],
            "sample_size": row["sample_size"],
            "metrics": project_metric_summaries(row["metrics"], f"baselines[{index}].metrics"),
        }
        if "format_classification" in row:
            projected["format_classification"] = dict(require_object(
                row["format_classification"], f"baselines[{index}].format_classification"
            ))
        result.append(projected)
    return result


def project_patterns(rows: Any, label: str) -> list[dict[str, Any]]:
    result = []
    for index, value in enumerate(require_list(rows, label)):
        row = require_object(value, f"{label}[{index}]")
        for key in ("pattern", "explanation", "examples"):
            if key not in row:
                raise ValueError(f"{label}[{index}] missing {key}")
        signals = []
        for example_index, example_value in enumerate(require_list(row["examples"], f"{label}[{index}].examples")):
            example = require_object(example_value, f"{label}[{index}].examples[{example_index}]")
            for key in ("format", "metrics", "view_multiple_vs_format_median"):
                if key not in example:
                    raise ValueError(f"{label}[{index}].examples[{example_index}] missing {key}")
            metrics = require_object(example["metrics"], f"{label}[{index}].examples[{example_index}].metrics")
            signal = {
                "format": example["format"],
                "metrics": dict(metrics),
                "view_multiple_vs_format_median": example["view_multiple_vs_format_median"],
            }
            for field in ("format_confidence", "format_source"):
                if field in example:
                    signal[field] = example[field]
            signals.append(signal)
        result.append({
            "pattern": row["pattern"],
            "explanation": row["explanation"],
            "performance_signals": signals,
        })
    return result


def project_recommendations(value: Any) -> dict[str, list[dict[str, Any]]]:
    source = require_object(value, "recommendations")
    result: dict[str, list[dict[str, Any]]] = {}
    for group in ("continue", "stop", "test"):
        actions = []
        for index, action_value in enumerate(require_list(source.get(group), f"recommendations.{group}")):
            action = require_object(action_value, f"recommendations.{group}[{index}]")
            if "action" not in action:
                raise ValueError(f"recommendations.{group}[{index}] missing action")
            selected = {"action": action["action"]}
            if action.get("success_metric") is not None:
                selected["success_metric"] = action["success_metric"]
            actions.append(selected)
        result[group] = actions
    return result


def find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(FORBIDDEN_KEYS & set(value))
        for child in value.values():
            found.update(find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_forbidden_keys(child))
    return found


def require_public_youtube_format_provenance(
    report: dict[str, Any], scope: dict[str, Any], coverage: dict[str, Any]
) -> None:
    """Fail closed when public YouTube evidence loses its classification provenance."""
    source_mode = str(scope.get("source_mode") or "").casefold()
    if str(scope.get("platform") or "").casefold() != "youtube" or not source_mode.startswith("public"):
        return
    if "format_classification" not in coverage:
        raise ValueError("public YouTube data_coverage missing format_classification")
    require_non_empty_format_classification(
        coverage["format_classification"],
        "data_coverage.format_classification",
    )
    for index, value in enumerate(require_list(report["baselines"], "baselines")):
        baseline = require_object(value, f"baselines[{index}]")
        if "format_classification" not in baseline:
            raise ValueError(f"public YouTube baselines[{index}] missing format_classification")
        require_non_empty_format_classification(
            baseline["format_classification"],
            f"baselines[{index}].format_classification",
        )
    for label in ("what_works", "what_hurts"):
        for pattern_index, pattern_value in enumerate(require_list(report[label], label)):
            pattern = require_object(pattern_value, f"{label}[{pattern_index}]")
            examples = require_list(pattern.get("examples"), f"{label}[{pattern_index}].examples")
            for example_index, example_value in enumerate(examples):
                example = require_object(
                    example_value,
                    f"{label}[{pattern_index}].examples[{example_index}]",
                )
                for field in ("format_confidence", "format_source"):
                    if not isinstance(example.get(field), str) or not example[field].strip():
                        raise ValueError(
                            f"public YouTube {label}[{pattern_index}].examples[{example_index}] "
                            f"missing {field}"
                        )


def project(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != REPORT_VERSION:
        raise ValueError(f"report must be {REPORT_VERSION}")
    if report.get("status") not in {"complete", "partial", "blocked"}:
        raise ValueError("report status must be complete, partial, or blocked")
    if report["status"] == "blocked":
        raise ValueError("blocked AccountReviewReport cannot produce Idea context")
    for key in (
        "scope", "data_coverage", "diagnosis", "baselines", "what_works",
        "what_hurts", "recommendations", "data_gaps",
    ):
        if key not in report:
            raise ValueError(f"report missing {key}")

    scope = require_object(report["scope"], "scope")
    window = require_object(scope.get("window"), "scope.window")
    coverage = require_object(report["data_coverage"], "data_coverage")
    for key in ("platform", "observed_at"):
        if key not in scope:
            raise ValueError(f"scope missing {key}")
    for key in ("start", "end"):
        if key not in window:
            raise ValueError(f"scope.window missing {key}")
    for key in ("content_total", "formats", "metric_available_counts"):
        if key not in coverage:
            raise ValueError(f"data_coverage missing {key}")
    require_public_youtube_format_provenance(report, scope, coverage)

    projected_coverage = {
        "content_total": coverage["content_total"],
        "formats": dict(require_object(coverage["formats"], "data_coverage.formats")),
        "metric_available_counts": dict(require_object(
            coverage["metric_available_counts"],
            "data_coverage.metric_available_counts",
        )),
    }
    if "format_classification" in coverage:
        projected_coverage["format_classification"] = dict(require_object(
            coverage["format_classification"], "data_coverage.format_classification"
        ))

    result = {
        "account": {
            "platform": scope["platform"],
            "window": {"start": window["start"], "end": window["end"]},
            "observed_at": scope["observed_at"],
            "coverage": projected_coverage,
            "baselines": project_baselines(report["baselines"]),
            "diagnosis": report["diagnosis"],
            "what_works": project_patterns(report["what_works"], "what_works"),
            "what_hurts": project_patterns(report["what_hurts"], "what_hurts"),
            "recommendations": project_recommendations(report["recommendations"]),
            "data_gaps": list(require_list(report["data_gaps"], "data_gaps")),
        }
    }
    leaked = find_forbidden_keys(result)
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
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
