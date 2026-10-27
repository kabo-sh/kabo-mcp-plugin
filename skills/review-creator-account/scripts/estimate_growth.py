#!/usr/bin/env python3
"""Calculate transparent conditional estimates; never select growth assumptions."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import copy
import re
import hashlib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def number(value, label, *, signed=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(value) or (not signed and value < 0):
        raise ValueError(f"{label} must be finite" + ("" if signed else " and non-negative"))
    return value


def time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def publication_quantity(record, question, kind):
    """Check a model's source interpretation, not the semantics of arbitrary prose."""
    if not isinstance(record, dict) or record.get("origin") != "user" or not isinstance(question, str):
        return None
    value, quote = record.get("posts"), record.get("quote")
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or int(value) != value
            or not isinstance(quote, str)):
        return None
    binding = record.get("binding")
    if binding is None:
        # Read compatibility for the old, complete explicit-total form only.
        # No substring search: omitted surrounding prose cannot become a total.
        literal = r"(\d+(?:\.\d+)?)\s*(?:posts?|videos?|uploads?|条|條|篇|个视频|個視頻)"
        match = re.fullmatch(literal, quote.strip(), re.I)
        whole = re.fullmatch(r"(?:publish\s+)?" + re.escape(quote.strip()), question.strip(), re.I)
        if kind != "count" or "period" in record or not match or not whole or float(match[1]) != value:
            return None
        return {"value": value, "quote": quote, "quantity_kind": "total",
                "interpretation": "legacy_explicit_total",
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()}
    if not isinstance(binding, dict) or quote != question.strip():
        return None
    quantity = binding.get("quantity_quote")
    if not isinstance(quantity, str) or not re.fullmatch(r"\d+(?:\.\d+)?", quantity):
        return None
    positions = []
    for match in re.finditer(r"(?<![\d.])" + re.escape(quantity) + r"(?![\d.])", quote):
        # Preserve the numeric token's sign, including compatibility-width minus signs.
        prefix = unicodedata.normalize("NFKC", quote[:match.start()]).rstrip()
        if prefix and (unicodedata.category(prefix[-1]) == "Pd" or prefix[-1] in "−➖"):
            continue
        positions.append(match)
    if not positions or float(quantity) != value:
        return None
    expected = "cadence" if kind == "cadence" else "total"
    if binding.get("quantity_kind") != expected:
        return None
    divisor = 1
    if expected == "cadence":
        period = record.get("period")
        period_quote = binding.get("period_quote")
        if (period not in {"day", "week"} or binding.get("period") != period
                or not isinstance(period_quote, str) or not period_quote.strip()
                or not any(not (q.start() < unit.end() and unit.start() < q.end())
                           for q in positions for unit in re.finditer(re.escape(period_quote), quote))):
            return None
        divisor = 1 if period == "day" else 7
    elif "period" in record or "period" in binding or "period_quote" in binding:
        return None
    return {"value": value / divisor, "quote": quote, "quantity_kind": expected,
            "quantity_quote": quantity, "period_quote": binding.get("period_quote"),
            "normalized_period": record.get("period"), "interpretation": "model_source_interpretation",
            "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()}


def user_quantity(record, question, kind):
    if kind == "rate":
        return legacy_stock_rate(record, question)
    return publication_quantity(record, question, kind)


def legacy_stock_rate(record, question):
    """Read the pre-existing assumed_pace contract; not a new multilingual rate interface."""
    if not isinstance(record, dict) or record.get("origin") != "user" or not isinstance(question, str):
        return None
    quote = record.get("quote")
    if not isinstance(quote, str) or not quote.strip() or quote not in question:
        return None
    units = {"day": (1, r"天|日|day"), "week": (7, r"周|週|week")}
    if record.get("period") not in units:
        return None
    divisor, unit = units[record["period"]]
    numeric = r"(-?\d+(?:\.\d+)?)"
    patterns = [rf"每(?:{unit})\s*(?:净增|淨增|增加|减少|減少)?\s*{numeric}",
                rf"{numeric}\s*(?:subscribers?|followers?|subs?)?\s*(?:per|a|/)\s*(?:{unit})\b"]
    value = record.get("amount")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if re.search(r"减少|減少", quote) and value > 0:
        return None
    matches = [float(match.group(1)) for pattern in patterns for match in re.finditer(pattern, quote, re.I)]
    if not matches or any(found != value for found in matches):
        return None
    return {"value": value / divisor, "quote": quote,
            "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()}


def estimate(data, question=None):
    if data.get("schema_version") != "growth-input.v1":
        raise ValueError("expected growth-input.v1")
    scope = data.get("scope", {})
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    for key in ("platform", "account", "metric", "semantics"):
        if not isinstance(scope.get(key), str) or not scope[key].strip():
            raise ValueError(f"scope.{key} is required")
    days = number(data.get("horizon_days"), "horizon_days")
    if days <= 0:
        raise ValueError("horizon_days must be positive")
    mode = data.get("mode")
    if mode == "content_scenario":
        return content_scenario(data, scope, days, question)
    rows = data.get("observations", [])
    if not isinstance(rows, list):
        raise ValueError("observations must be an array")
    known, missing = [], 0
    for row in rows:
        if not isinstance(row, dict) or row.get("scope") != scope:
            raise ValueError("every observation must carry the same scope")
        stamp = time(row["observed_at"])
        if not isinstance(row.get("source"), str) or not row["source"].strip():
            raise ValueError("every observation needs a source reference")
        if row.get("value") is None:
            missing += 1
            continue
        known.append((stamp, number(row["value"], "observation.value"), row))
    known.sort(key=lambda item: item[0])
    if len({item[0] for item in known}) != len(known):
        raise ValueError("duplicate observation timestamps; resolve duplicates before estimating")
    result = {"schema_version": "growth-estimate.v1", "status": "needs_input",
              "scope": scope, "mode": mode, "horizon_days": days,
              "observations": [item[2] for item in known],
              "coverage": {"available": len(known), "missing": missing},
              "estimate": None, "required_inputs": [], "assumptions": [],
              "limitations": ["Conditional arithmetic, not a calibrated forecast or probability."]}
    if mode == "observed_pace":
        if scope["semantics"] != "cumulative_stock":
            raise ValueError("observed_pace requires cumulative_stock; window totals are not a stock")
        if len(known) < 2:
            result["required_inputs"] = ["Two dated observations of the same cumulative metric."]
            return result
        first, last = known[0], known[-1]
        elapsed = (last[0] - first[0]).total_seconds() / 86400
        gain = last[1] - first[1]
        rate = gain / elapsed
        intervals = [(b[1] - a[1]) / ((b[0] - a[0]).total_seconds() / 86400)
                     for a, b in zip(known, known[1:])]
        result["basis"] = {"start": first[2], "end": last[2], "elapsed_days": elapsed,
                           "net_change": gain, "per_day": rate,
                           "interval_rates": intervals, "horizon_to_observed_window": days / elapsed}
        result["assumptions"] = ["The observed net pace continues unchanged over the requested horizon."]
        result["limitations"] += ["Missing dates are not zero growth; rates use actual elapsed time.",
                                  "Net change does not identify content effects or conversion."]
        if any(r < 0 for r in intervals) and any(r > 0 for r in intervals):
            result["limitations"].append("Observed interval changes reverse direction; the mean hides that variation.")
        baseline = last[1]
    elif mode == "assumed_pace":
        if scope["semantics"] != "cumulative_stock":
            raise ValueError("assumed_pace requires cumulative_stock")
        assumption = data.get("assumption")
        verified = user_quantity(assumption, question, "rate")
        if not known or verified is None:
            result["required_inputs"] = ["A dated baseline and an explicit net-change amount and day/week period in the original user request (--question-file)."]
            return result
        rate = verified["value"]
        baseline = known[-1][1]
        result["basis"] = {"baseline": known[-1][2], "per_day": rate, "assumption": assumption, "request_binding": verified}
        result["assumptions"] = ["The supplied per-day net change holds throughout the horizon."]
    else:
        raise ValueError("mode must be observed_pace or assumed_pace")
    raw = baseline + rate * days
    if not math.isfinite(raw):
        raise ValueError("estimate overflow")
    result["status"] = "computed"
    result["estimate"] = {"baseline": baseline, "net_change": rate * days,
                          "value": max(0, raw), "unclipped_value": raw,
                          "formula": "max(0, baseline + per_day * horizon_days)"}
    if raw < 0:
        result["limitations"].append("The linear continuation crossed zero; extrapolation ceases to describe a feasible stock.")
    return result


def content_scenario(data, scope, days, question=None):
    if scope["semantics"] != "per_content_cumulative" or scope["metric"] not in ("views", "likes", "comments"):
        raise ValueError("content_scenario supports cumulative views/likes/comments per content, not followers")
    cohort = data.get("cohort", {})
    if not isinstance(cohort.get("format"), str) or not cohort["format"].strip():
        raise ValueError("cohort.format is required")
    low = number(cohort.get("age_min_days"), "age_min_days")
    high = number(cohort.get("age_max_days"), "age_max_days")
    if high < low:
        raise ValueError("age_max_days must be at least age_min_days")
    samples = data.get("samples", [])
    if not isinstance(samples, list):
        raise ValueError("samples must be an array")
    selected, seen, missing, outside = [], set(), 0, 0
    for row in samples:
        if not isinstance(row, dict) or row.get("scope") != scope:
            raise ValueError("every content sample must carry the same scope")
        identity = row.get("content_id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("content_id must be nonempty and unique")
        seen.add(identity)
        if not isinstance(row.get("source"), str) or not row["source"].strip():
            raise ValueError("every content sample needs a source reference")
        age = (time(row["observed_at"]) - time(row["published_at"])).total_seconds() / 86400
        if age < 0:
            raise ValueError("content observation precedes publication")
        if row.get("format") != cohort["format"] or not low <= age <= high:
            outside += 1
            continue
        if row.get("value") is None:
            missing += 1
            continue
        number(row["value"], "sample.value")
        selected.append(row)
    result = {"schema_version": "growth-estimate.v1", "status": "needs_input", "scope": scope,
              "mode": "content_scenario", "horizon_days": days, "cohort": cohort,
              "samples": selected, "coverage": {"available": len(selected), "missing": missing, "outside_cohort": outside},
              "estimate": None, "required_inputs": [], "assumptions": [],
              "limitations": ["An observed content distribution is not a confidence interval or a growth rate.",
                               "Totals describe planned content at the cohort observation age, not necessarily by the horizon end."]}
    plan = data.get("plan")
    user_cadence = isinstance(plan, dict) and plan.get("origin") == "user" and "period" in plan
    verified = user_quantity(plan, question, "cadence" if user_cadence else "count")
    if user_cadence and verified is not None:
        plan = dict(plan, posts_per_period=plan["posts"], posts=verified["value"] * days)
    cadence = data.get("_snapshot_cadence")
    if isinstance(plan, dict) and plan.get("origin") == "observed_cadence" and "period" not in plan and cadence:
        verified = cadence
        plan = {"origin": "observed_cadence", "posts": cadence["per_day"] * days}
    if not selected:
        result["required_inputs"] = ["Comparable content samples with metric values, publication dates and observation dates."]
        return result
    if verified is None:
        result["required_inputs"] = [
            "Choose a supported plan: an explicit user publication count or day/week publishing frequency with --question-file, or plan.origin=observed_cadence with --snapshot pointing to the retained public-content-snapshot.v1 (at least two distinct publication dates)."
        ]
        return result
    posts = number(plan["posts"], "plan.posts")
    if plan["origin"] == "user" and not user_cadence and int(posts) != posts:
        raise ValueError("plan requires a whole publication count")
    median = statistics.median(row["value"] for row in selected)
    values = sorted(row["value"] for row in selected)
    def percentile(fraction):
        position = (len(values) - 1) * fraction
        low_index = math.floor(position)
        high_index = math.ceil(position)
        return values[low_index] + (values[high_index] - values[low_index]) * (position - low_index)
    levels = {"lower_quartile": percentile(0.25), "median": median, "upper_quartile": percentile(0.75)}
    value = median * posts
    if not math.isfinite(value) or any(not math.isfinite(level * posts) for level in levels.values()):
        raise ValueError("estimate overflow")
    if plan["origin"] == "observed_cadence":
        result["limitations"].append("Captured publication pace may be selective; continuing it is a conditional scenario, not an account growth rate.")
    ages = [(time(row["observed_at"]) - time(row["published_at"])).total_seconds() / 86400 for row in selected]
    typical_age = statistics.median(ages)
    # Items published inside the window are at most `days` old on its last day. When most
    # samples were observed older than that, the scenario's own like-for-like assumption puts
    # the deadline total below it; how far below needs trajectories this snapshot lacks.
    comparison = "lower" if typical_age > days else "not_identified"
    result["basis"] = {"median_per_content": median, "sample_size": len(selected), "plan": plan,
                       "reference_levels": levels, "quantile_method": "linear interpolation at (n - 1) * fraction",
                       "input_binding": verified, "observed_age_days": {"min": min(ages), "max": max(ages)}}
    result["assumptions"] = ["Every planned item reaches the historical cohort median at the same observation age."]
    if user_cadence:
        result["assumptions"].append("The user-stated publishing frequency continues over the publication window; equivalent posts are not a calendar schedule or a guaranteed whole-item count.")
    if plan["origin"] == "observed_cadence":
        result["assumptions"].append("The captured publication pace continues unchanged.")
    result["estimate"] = {"value": value, "formula": "median_per_content * planned_posts",
                          "sensitivity": {name: per_item * posts for name, per_item in levels.items()},
                          "measurement": f"New content at the sample observation ages ({min(ages):.1f}-{max(ages):.1f} days after each publication); not a total reached by the horizon end.",
                          "time_basis": {
                              "publication_window_days": days,
                              "content_age_days": {"min": min(ages), "max": max(ages), "median": typical_age},
                              "deadline_total": "not_identified",
                              "deadline_comparison_to_scenario": comparison,
                              "required_evidence": ["A publication schedule and comparable cumulative performance at each item's age on the deadline."]}}
    result["status"] = "computed"
    result["limitations"].append("Sensitivity totals assume every new item matches the chosen observed per-item quartile; they are not batch quantiles, forecast bounds or occurrence probabilities.")
    return result


def with_snapshot(data, snapshot, source):
    """Bind content samples to the existing public snapshot without model transcription."""
    if data.get("mode") != "content_scenario" or snapshot.get("schema_version") != "public-content-snapshot.v1":
        raise ValueError("--snapshot requires content_scenario and public-content-snapshot.v1")
    if data.get("samples"):
        raise ValueError("do not mix manually supplied samples with --snapshot")
    scope = data["scope"]
    if snapshot.get("platform") != scope["platform"]:
        raise ValueError("snapshot platform does not match the requested scope")
    creators = [row for row in snapshot.get("creators", [])
                if scope["account"] in (row.get("handle"), row.get("creator_id"))]
    if len(creators) != 1:
        raise ValueError("snapshot must identify the requested creator uniquely")
    result = copy.deepcopy(data)
    result["samples"] = []
    for item in snapshot.get("items", []):
        if item.get("creator_id") != creators[0]["creator_id"]:
            continue
        metric = item.get("metrics", {}).get(scope["metric"], {})
        value = metric.get("value") if metric.get("status") in ("available", "zero") else None
        result["samples"].append({"scope": scope, "content_id": item["content_id"],
                                  "published_at": item["published_at"], "observed_at": snapshot["observed_at"],
                                  "format": item.get("format"), "value": value,
                                  "source": f"{source}#items/{item['content_id']}"})
    if data.get("plan", {}).get("origin") == "observed_cadence":
        stamps = sorted(time(row["published_at"]) for row in result["samples"]
                        if row["format"] == data.get("cohort", {}).get("format"))
        if len(stamps) >= 2 and stamps[-1] > stamps[0]:
            elapsed = (stamps[-1] - stamps[0]).total_seconds() / 86400
            result["_snapshot_cadence"] = {"per_day": (len(stamps) - 1) / elapsed,
                "captured_posts": len(stamps), "elapsed_days": elapsed,
                "formula": "(captured_posts - 1) / elapsed_days",
                "source": source, "first_published_at": stamps[0].isoformat(), "last_published_at": stamps[-1].isoformat()}
    return result


def deadline_sentence(timing):
    if timing["deadline_comparison_to_scenario"] == "lower":
        return (f"The deadline total is not identified, but it is usually lower than this scenario: most samples were observed "
                f"older (median {timing['content_age_days']['median']:.1f} days) than any item published in the window can be by its end.")
    return "Deadline total and whether it is higher or lower than this scenario: not identified by these inputs."


def render_report(result):
    scope = result["scope"]
    title = f"Conditional estimate: {scope['account']} / {scope['metric']}"
    if result["status"] == "needs_input":
        return title + "\n\n" + "\n".join(result["required_inputs"]) + "\nNo numeric estimate or probability is available from these inputs.\n"
    estimate = result["estimate"]
    lines = [title, ""]
    if result["mode"] == "content_scenario":
        lines.append(f"**{estimate['measurement']} Conditional batch total: {estimate['value']:,.2f}.**")
        timing = estimate["time_basis"]
        lines.append(f"Publication plan: {timing['publication_window_days']:g} days. " + deadline_sentence(timing))
        lines.append("To estimate the deadline: " + " ".join(timing["required_evidence"]))
    else:
        lines.append(f"Conditional value: {estimate['value']:,.2f}")
    lines.append(f"Formula: {estimate['formula']}")
    if result["mode"] == "content_scenario":
        plan = result["basis"]["plan"]
        label = "equivalent new items" if "period" in plan else "new items"
        lines.append(f"Inputs: median {result['basis']['median_per_content']:g} per item × {plan['posts']:g} {label}.")
        if "period" in plan:
            lines.append(f"Publishing frequency: {plan['posts_per_period']:g} per {plan['period']} × {result['horizon_days']:g} days; fractional equivalent counts are not rounded to a calendar posting schedule.")
        totals = estimate["sensitivity"]
        levels = result["basis"]["reference_levels"]
        lines.append("Sensitivity choices at the SAME sample observation ages (not achieved-by-date totals):")
        for name in ("lower_quartile", "median", "upper_quartile"):
            lines.append(f"- If each new item matches the observed {name}: {levels[name]:g} per item × {result['basis']['plan']['posts']:g} = {totals[name]:,.2f}.")
    else:
        lines.append(f"Inputs: baseline {estimate['baseline']:g} + daily net change {result['basis']['per_day']:g} × {result['horizon_days']:g} days.")
    lines += ["", "Assumptions:"] + [f"- {text}" for text in result["assumptions"]]
    lines += ["", "Limits:"] + [f"- {text}" for text in result["limitations"]]
    return "\n".join(lines) + "\n"


def review_evidence(data, snapshot, source):
    """Prepare metric-specific, conditional choices from retained public evidence."""
    if data.get("schema_version") != "growth-review.v1":
        raise ValueError("expected growth-review.v1")
    scope = data.get("scope", {})
    for key in ("platform", "account"):
        if not isinstance(scope.get(key), str) or not scope[key].strip():
            raise ValueError(f"scope.{key} is required")
    days = number(data.get("horizon_days"), "horizon_days")
    if days <= 0:
        raise ValueError("horizon_days must be positive")
    metrics = data.get("metrics")
    if not isinstance(metrics, list) or not metrics or any(
        metric not in ("subscribers", "followers", "views", "likes", "comments") for metric in metrics
    ) or len(set(metrics)) != len(metrics):
        raise ValueError("metrics must contain unique supported metric names")
    # Reuse the binding validation even if only stock metrics were requested.
    probe = dict(schema_version="growth-input.v1", mode="content_scenario",
                 scope={**scope, "metric": "views", "semantics": "per_content_cumulative"},
                 horizon_days=days, cohort={}, plan={})
    bound = with_snapshot(probe, snapshot, source)
    formats = sorted({row["format"] for row in bound["samples"] if isinstance(row["format"], str) and row["format"]})
    result = dict(schema_version="growth-evidence.v1", scope=scope, horizon_days=days,
                  source=source, observed_at=snapshot["observed_at"], metrics=[],
                  coverage=copy.deepcopy(snapshot.get("coverage", {})),
                  limitations=copy.deepcopy(snapshot.get("limitations", [])))
    for metric in metrics:
        entry = dict(metric=metric, candidates=[], required_inputs=[])
        if metric in ("subscribers", "followers"):
            entry["required_inputs"] = ["Dated net-change observations, or a dated baseline with an explicit user rate. Public content views do not identify subscriber/follower conversion."]
        else:
            for format_ in formats:
                rows = [row for row in bound["samples"] if row["format"] == format_]
                ages = [(time(row["observed_at"]) - time(row["published_at"])).total_seconds() / 86400 for row in rows]
                request = dict(schema_version="growth-input.v1", mode="content_scenario",
                               scope={**scope, "metric": metric, "semantics": "per_content_cumulative"},
                               horizon_days=days, cohort=dict(format=format_, age_min_days=min(ages), age_max_days=max(ages)),
                               plan=dict(origin="observed_cadence"))
                candidate = estimate(with_snapshot(request, snapshot, source))
                entry["candidates"].append(candidate)
            if not formats:
                entry["required_inputs"] = ["Dated content samples with a known format and metric values."]
        result["metrics"].append(entry)
    return result


def render_evidence(result):
    lines = [f"Growth evidence: {result['scope']['account']} / {result['horizon_days']:g} days", "",
             "These are evidence-derived conditional choices, not forecasts or outcome probabilities.",
             "Each format uses all captured items; sample selection and mixed observation ages limit comparability."]
    for entry in result["metrics"]:
        lines += ["", f"### {entry['metric']}"]
        lines += entry["required_inputs"]
        for candidate in entry["candidates"]:
            lines.append(f"Format: {candidate['cohort']['format']}; available {candidate['coverage']['available']}, missing {candidate['coverage']['missing']}.")
            lines.append(render_report(candidate).strip())
    if result["limitations"]:
        lines += ["", "Source limitations:", json.dumps(result["limitations"], ensure_ascii=False)]
    if result["coverage"]:
        lines += ["Source coverage: " + json.dumps(result["coverage"], ensure_ascii=False)]
    lines += ["", "Explain which conditional choice fits the request and why. A missing metric does not block the others.",
              "Historical performance can inform an action target; a target is not an expected outcome. Preserve the measurement and the stated deadline comparison when explaining or reusing a scenario."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--question-file", type=Path, help="Persisted original user request; never an assistant paraphrase")
    parser.add_argument("--assess", action="store_true", help="Review requested metrics in a retained public snapshot before choosing an estimate")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        if "_snapshot_cadence" in data:
            raise ValueError("_snapshot_cadence is derived by --snapshot, never supplied in input")
        if args.assess:
            if not args.snapshot:
                raise ValueError("--assess requires --snapshot")
            result = review_evidence(data, json.loads(args.snapshot.read_text(encoding="utf-8")), str(args.snapshot))
        elif args.snapshot:
            data = with_snapshot(data, json.loads(args.snapshot.read_text(encoding="utf-8")), str(args.snapshot))
        if not args.assess:
            result = estimate(data, args.question_file.read_text(encoding="utf-8") if args.question_file else None)
    except (ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = render_evidence(result) if args.assess else render_report(result)
    args.output.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
