#!/usr/bin/env python3
"""Compute the deterministic block of a VideoAnalysis from evidence and an optional account baseline.

The model narrates; it does not decide verdicts. Given the same ContentEvidence, the same baseline
and the same RULE_VERSION, this produces byte-identical output — which is what makes the block
worth calling deterministic.

    python3 compute_deterministic.py <content_evidence.json> [--baseline <account_review.json>]
                                     [--subject-state own_published] [--output <file>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RULE_VERSION = "video-verdict.v1"

# A verdict flips only outside this relative band. Without it, a fractional difference from a
# 19-post median would read as a real gap.
AT_BASELINE_RELATIVE_BAND = 0.05

# Hook stage uses skip rate, where lower is better. Sustain uses watch time, where higher is better.
HIGHER_IS_BETTER = {"ig_reels_avg_watch_time": True, "reels_skip_rate": False}


def available(evidence: dict) -> dict:
    result = {}
    for item in evidence["owner_metrics"]["items"]:
        if item["status"] != "available":
            continue
        result[item["native_name"]] = item
        if item.get("canonical_name"):
            result[item["canonical_name"]] = item
    return result


def verdict_for(value: float | None, baseline: float | None, higher_is_better: bool) -> str:
    if value is None or baseline in (None, 0):
        return "unassessed"
    delta = (value - baseline) / abs(baseline)
    if abs(delta) <= AT_BASELINE_RELATIVE_BAND:
        return "at_baseline"
    better = delta > 0 if higher_is_better else delta < 0
    return "above_baseline" if better else "below_baseline"


def read_baseline(path: Path | None) -> dict | None:
    """Take the mature cohort from an M1 account review. This module never recomputes a baseline."""
    if path is None:
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    cohort = (report.get("baseline") or {}).get("cohorts", {}).get("mature_reels")
    if not cohort:
        return None
    metrics = cohort.get("metrics", {})
    return {
        "report_id": report.get("report_id"),
        "format": "REELS",
        "maturity_days": (report.get("baseline") or {}).get("maturity_days"),
        "sample_size": cohort.get("sample_size"),
        "skip_rate_percent": metrics.get("skip_rate_percent"),
        "average_watch_time_seconds": metrics.get("average_watch_time_seconds"),
    }


def public_only_evidence_errors(evidence: dict) -> list[str]:
    """The public evidence builder emits no owner metrics or owner-derived values."""
    owner = evidence.get("owner_metrics") or {}
    errors = []
    if (owner.get("status") != "unavailable" or owner.get("source_mode") != "unavailable"
            or owner.get("items") != [] or owner.get("account_ref") is not None
            or owner.get("snapshot_sha256") is not None):
        errors.append("unknown ownership cannot consume owner metrics")
    public_derived = {"caption_length_characters", "caption_hashtag_count"}
    if any(not isinstance(item, dict) or item.get("name") not in public_derived
           for item in evidence.get("derived") or []):
        errors.append("unknown ownership cannot consume owner or unrecognized derived metrics")
    return errors


def compute_known_subject(evidence: dict, baseline: dict | None, subject_state: str) -> dict:
    metrics = available(evidence)
    derived = {d["name"]: d for d in evidence.get("derived") or []}
    owner_status = evidence["owner_metrics"]["status"]

    cohort = None
    if baseline:
        cohort = {
            "format": baseline["format"],
            "maturity_days": baseline["maturity_days"],
            "is_mature": True,
            "baseline_ref": f"m1/example_run/account_review.json#baseline.cohorts.mature_reels",
            "cohort_n": baseline["sample_size"],
        }

    # ---- hook stage ----
    skip = metrics.get("reels_skip_rate")
    if owner_status == "unavailable" or skip is None:
        hook = {
            "status": "unavailable", "metric": None, "value": None, "unit": None,
            "baseline_value": None, "verdict": "unassessed",
            "note": ("Skip rate is an owner metric and it does not exist yet: the video has not been "
                     "published. Nothing here may be presented as a performance prediction."
                     if subject_state == "own_unpublished" else
                     "No hook-stage retention metric is present in this owner evidence. Thumbnail "
                     "impressions CTR measures packaging clicks and must not be relabeled as video hook retention."
                     if subject_state == "own_published" else
                     "Skip rate is an owner metric. It does not exist for content the creator does not "
                     "own, and no public counter may stand in for it."),
        }
    else:
        base = (baseline or {}).get("skip_rate_percent")
        hook = {
            "status": "measured", "metric": "reels_skip_rate", "value": skip["value"], "unit": "percent",
            "baseline_value": base,
            "verdict": verdict_for(skip["value"], base, HIGHER_IS_BETTER["reels_skip_rate"]),
            "note": (f"Lower is better. {skip['value']}% against a mature-Reel median of {base}% over "
                     f"{baseline['sample_size']} posts." if base is not None else
                     "Measured, but no account baseline was supplied, so it cannot be placed."),
        }

    # ---- sustain stage ----
    measures = []
    avg = metrics.get("ig_reels_avg_watch_time")
    base_watch = (baseline or {}).get("average_watch_time_seconds")
    if avg is not None:
        measures.append({
            "name": "avg_watch_time_absolute", "source": "computed_here", "evidence_ref": None,
            "value": round(avg["value"] / 1000, 3), "baseline_value": base_watch,
            "note": ("seconds; derived from the owner metric ig_reels_avg_watch_time, whose population "
                     "the provider does not document"),
        })
    youtube_avg = metrics.get("average_view_duration_seconds") or metrics.get("averageViewDuration")
    youtube_avg_baseline = (derived.get("mature_same_format_cohort_median_average_view_duration_seconds") or {}).get("value")
    if youtube_avg is not None:
        measures.append({
            "name": "average_view_duration_seconds", "source": "computed_here", "evidence_ref": None,
            "value": youtube_avg["value"], "baseline_value": youtube_avg_baseline,
            "note": "seconds; YouTube owner metric for the shared reporting window",
        })
    youtube_percentage = metrics.get("average_percentage_viewed") or metrics.get("averageViewPercentage")
    youtube_percentage_baseline = (derived.get("mature_same_format_cohort_median_average_percentage_viewed") or {}).get("value")
    if youtube_percentage is not None:
        measures.append({
            "name": "average_percentage_viewed", "source": "computed_here", "evidence_ref": None,
            "value": youtube_percentage["value"], "baseline_value": youtube_percentage_baseline,
            "note": "percent; YouTube owner metric for the shared reporting window",
        })
    for name in ("avg_percentage_viewed__provider_avg", "avg_percentage_viewed__per_view"):
        if name in derived:
            measures.append({
                "name": name, "source": "evidence_derived", "evidence_ref": name,
                "value": derived[name]["value"], "baseline_value": None,
                "note": ("percent; formula and denominator caveat live in the evidence object"
                         if "provider_avg" in name else
                         "percent; no account baseline exists because the owner export carries no duration"),
            })

    if not measures:
        sustain = {
            "status": "unavailable", "measures": [], "verdict": "unassessed",
            "note": ("Watch time and retention do not exist for unpublished media."
                     if subject_state == "own_unpublished" else
                     "Watch time and retention are owner metrics and are unavailable for this subject."),
        }
    else:
        absolute = next((m for m in measures if m["name"] == "avg_watch_time_absolute"), None)
        youtube_absolute = next((m for m in measures if m["name"] == "average_view_duration_seconds"), None)
        verdict_measure = absolute or youtube_absolute
        verdict_baseline = base_watch if absolute else (
            youtube_absolute.get("baseline_value") if youtube_absolute else None)
        v = verdict_for(verdict_measure["value"] if verdict_measure else None, verdict_baseline, True)
        sustain = {
            "status": "measured", "measures": measures, "verdict": v,
            "note": ("Verdict is taken on absolute watch time, the only measure with an account baseline. "
                     "The percentage measures come from the evidence object and are unassessed against "
                     "the account." if absolute and base_watch is not None else
                     "Verdict is taken on YouTube average view duration against the mature same-format "
                     "cohort median carried by ContentEvidence." if youtube_absolute and verdict_baseline is not None else
                     "Measured, but no account baseline was supplied, so it cannot be placed."),
        }

    return {
        "rule_version": RULE_VERSION,
        "cohort": cohort,
        "hook_stage": hook,
        "sustain_stage": sustain,
        "composite_score": None,
    }



def compute(evidence: dict, baseline: dict | None, subject_state: str) -> dict:
    if subject_state not in {"own_unpublished", "own_published", "third_party", "unknown"}:
        raise ValueError("an explicit supported subject_state is required")
    if subject_state != "unknown":
        return compute_known_subject(evidence, baseline, subject_state)
    errors = public_only_evidence_errors(evidence)
    if baseline is not None:
        errors.append("unknown ownership cannot consume an owner baseline")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "rule_version": RULE_VERSION,
        "cohort": None,
        "hook_stage": {
            "status": "unavailable", "metric": None, "value": None, "unit": None,
            "baseline_value": None, "verdict": "unassessed",
            "note": "Ownership is undeclared; this public-only analysis has no owner retention data. "
                    "Public counters cannot substitute for it.",
        },
        "sustain_stage": {
            "status": "unavailable", "measures": [], "verdict": "unassessed",
            "note": "Ownership is undeclared; watch time and retention were not obtained in this "
                    "public-only scope.",
        },
        "composite_score": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence")
    ap.add_argument("--baseline")
    ap.add_argument("--subject-state", required=True,
                    choices=["own_unpublished", "own_published", "third_party", "unknown"])
    ap.add_argument("--output")
    args = ap.parse_args()

    if args.subject_state == "unknown" and args.baseline is not None:
        ap.error("unknown ownership cannot consume an owner baseline")

    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    baseline = read_baseline(Path(args.baseline) if args.baseline else None)
    block = compute(evidence, baseline, args.subject_state)
    text = json.dumps(block, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
