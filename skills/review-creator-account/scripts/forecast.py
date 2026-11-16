#!/usr/bin/env python3
"""One command from a forecast request's facts to the complete forecast reply.

The model names the target, metrics, horizon and any records the user typed; this script builds every
calculation input, selects the method from the evidence, recomputes it and composes the reply. Nothing is
hand-written as JSON, so the input contracts cannot drift between turns.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from account_analyzers import normalize_format
from compose_forecast_reply import compose
from estimate_growth import legacy_stock_rate, time, with_snapshot

STOCK_METRICS = ("subscribers", "followers")
CONTENT_METRICS = ("views", "likes", "comments")
RECORD = re.compile(r"^(?P<metric>[a-z]+)@(?P<date>\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)?)=(?P<value>-?\d+(?:\.\d+)?)$")


class Refusal(ValueError):
    """A request the script cannot turn into inputs; the message names the one thing to change."""


def read_question(path: str) -> str:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise Refusal("--question-file is empty; pass the creator's original request verbatim")
    return text


def parse_records(values: list[str], metrics: list[str]) -> dict[str, list[tuple[str, float]]]:
    records: dict[str, list[tuple[str, float]]] = {metric: [] for metric in metrics}
    for raw in values:
        match = RECORD.match(raw.strip())
        if not match:
            raise Refusal(f"--record {raw!r} must look like <metric>@<YYYY-MM-DD>=<count>, one dated count the user or a source gave")
        metric = match["metric"]
        if metric not in records:
            raise Refusal(f"--record {raw!r} names {metric!r}, which is not one of the requested --metric values")
        stamp = match["date"].replace(" ", "T")
        if "T" not in stamp:
            stamp += "T00:00:00+00:00"
        elif not re.search(r"(Z|[+-]\d{2}:?\d{2})$", stamp):
            stamp += "+00:00"
        time(stamp)
        records[metric].append((stamp, float(match["value"]) if "." in match["value"] else int(match["value"])))
    return records


def rate_assumption(quote: str | None, question: str) -> dict | None:
    """Read the user's stated net rate from an exact excerpt; the existing binding check stays authoritative."""
    if not quote:
        return None
    if quote not in question:
        raise Refusal("--rate must be copied exactly from the creator's request")
    for number in re.findall(r"-?\d+(?:\.\d+)?", quote):
        amount = float(number) if "." in number else int(number)
        for period in ("day", "week"):
            record = {"amount": amount, "period": period, "origin": "user", "quote": quote}
            if legacy_stock_rate(record, question) is not None:
                return record
    # Keep the excerpt; the calculator reports it as an unreadable rate instead of guessing one.
    return {"amount": 0, "period": "day", "origin": "user", "quote": quote}


def stock_input(scope: dict, days: float, rows: list[tuple[str, float]], source: str, rate: dict | None) -> dict:
    observations = [{"observed_at": stamp, "value": value, "source": f"{source} ({stamp[:10]})", "scope": scope}
                    for stamp, value in rows]
    if rate is not None and len(rows) < 2:
        return {"schema_version": "growth-input.v1", "mode": "assumed_pace", "scope": scope,
                "horizon_days": days, "observations": observations, "assumption": rate}
    return {"schema_version": "growth-input.v1", "mode": "observed_pace", "scope": scope,
            "horizon_days": days, "observations": observations}


def content_input(scope: dict, days: float, snapshot: dict | None, snapshot_path: str | None,
                  format_: str | None, posts: int | None, question: str) -> dict:
    data = {"schema_version": "growth-input.v1", "mode": "content_scenario", "scope": scope, "horizon_days": days}
    if posts is None:
        data["plan"] = {"origin": "observed_cadence"}
    elif posts == 1 and not re.search(r"(?<![\d.])1(?![\d.])", question):
        data["plan"] = {"origin": "request_item", "posts": 1}
    else:
        data["plan"] = {"posts": posts, "origin": "user", "quote": question.strip(),
                        "binding": {"quantity_kind": "total", "quantity_quote": str(posts)}}
    if snapshot is None:
        data["cohort"] = {"format": format_ or "video", "age_min_days": 0, "age_max_days": 0}
        data["samples"] = []
        return data
    probe = with_snapshot(dict(data, cohort={"format": format_ or "video", "age_min_days": 0, "age_max_days": 0}),
                          snapshot, snapshot_path)
    dated = [row for row in probe["samples"] if row["value"] is not None]
    if format_ is None:
        # Most captured items first; ties keep the snapshot order, so the choice is reproducible.
        counts = Counter(normalize_format(row["format"]) for row in dated)
        format_ = counts.most_common(1)[0][0] if counts else "video"
    ages = [(time(row["observed_at"]) - time(row["published_at"])).total_seconds() / 86400
            for row in dated if normalize_format(row["format"]) == normalize_format(format_)]
    # The snapshot binds the samples again inside the composer; the input keeps only the choice made here.
    data["cohort"] = {"format": format_, "age_min_days": min(ages) if ages else 0, "age_max_days": max(ages) if ages else 0}
    return data


def common_format(snapshot: dict, platform: str, target: str, metrics: list[str], days: float) -> str:
    """The format with the most captured items that carry any requested metric; ties keep snapshot order."""
    formats: dict[str, str] = {}
    for metric in metrics:
        scope = {"platform": platform, "account": target, "metric": metric, "semantics": "per_content_cumulative"}
        probe = with_snapshot({"schema_version": "growth-input.v1", "mode": "content_scenario", "scope": scope,
                               "horizon_days": days, "cohort": {"format": "video", "age_min_days": 0, "age_max_days": 0},
                               "plan": {"origin": "observed_cadence"}}, snapshot, None)
        formats.update((row["content_id"], normalize_format(row["format"]))
                       for row in probe["samples"] if row["value"] is not None)
    counts = Counter(formats.values())
    return counts.most_common(1)[0][0] if counts else "video"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("instagram", "tiktok", "youtube"))
    parser.add_argument("--target", required=True, help="The one resolved account handle, or the post URL/ID for a post")
    parser.add_argument("--target-kind", choices=("account", "post"), default="account")
    parser.add_argument("--metric", action="append", required=True, choices=STOCK_METRICS + CONTENT_METRICS)
    parser.add_argument("--horizon-days", type=float, default=30)
    parser.add_argument("--question-file", required=True, help="The creator's original request, or - to read it from stdin")
    parser.add_argument("--record", action="append", default=[], help="<metric>@<YYYY-MM-DD>=<count>: a dated count the user or a source gave; repeatable")
    parser.add_argument("--record-source", default="creator-supplied record")
    parser.add_argument("--rate", help="Exact excerpt of the creator's stated net rate, such as '20 subscribers per week'")
    parser.add_argument("--snapshot", type=Path, help="This run's public-content snapshot, for views/likes/comments of new content")
    parser.add_argument("--format", help="Content format to compare; default: the format with the most captured items")
    parser.add_argument("--posts", type=int, help="New items the creator asked about (1 for 'this video')")
    parser.add_argument("--correct-prior", action="store_true", help="Only when an earlier answer gave unsupported numbers")
    parser.add_argument("--output", type=Path, default=Path("FORECAST_REPLY.md"))
    args = parser.parse_args()
    try:
        if args.horizon_days <= 0:
            raise Refusal("--horizon-days must be positive")
        if args.posts is not None and args.posts < 1:
            raise Refusal("--posts must be at least 1")
        if args.output.suffix.lower() != ".md":
            raise Refusal("--output must be a .md file")
        metrics = list(dict.fromkeys(args.metric))
        question = read_question(args.question_file)
        work = args.output.resolve().parent
        work.mkdir(parents=True, exist_ok=True)
        question_path = work / "forecast_question.txt"
        question_path.write_text(question, encoding="utf-8")
        records = parse_records(args.record, metrics)
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
        rate = rate_assumption(args.rate, question)
        target = args.target.strip()
        if not target:
            raise Refusal("--target is empty")
        if snapshot is not None and not isinstance(snapshot, dict):
            raise Refusal("--snapshot must be this run's saved public-content snapshot")
        content = [m for m in metrics if m in CONTENT_METRICS and args.target_kind == "account"]
        # One format for every content metric, so views and likes describe the same kind of item.
        chosen_format = args.format or (common_format(snapshot, args.platform, target, content, args.horizon_days)
                                        if snapshot is not None and content else None)
        inputs = []
        for metric in metrics:
            stock = metric in STOCK_METRICS or args.target_kind == "post"
            scope = {"platform": args.platform, "account": target, "metric": metric,
                     "semantics": "cumulative_stock" if stock else "per_content_cumulative"}
            if stock:
                data = stock_input(scope, args.horizon_days, sorted(records[metric]), args.record_source, rate)
            else:
                if records[metric]:
                    raise Refusal(f"--record for {metric} applies to one post's own count; pass --target-kind post with that post as --target")
                data = content_input(scope, args.horizon_days, snapshot, str(args.snapshot) if args.snapshot else None,
                                     chosen_format, args.posts, question)
            path = work / f"forecast_input_{metric}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            inputs.append(path)
        scope_file = {"platform": args.platform, "target": target, "request_quote": question.strip(), "reference": target}
        (work / "forecast_scope.json").write_text(json.dumps(scope_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results, report = compose(inputs, scope_file, question, snapshot, str(args.snapshot) if args.snapshot else None,
                                  args.correct_prior)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        reason = "forecast_request_invalid" if isinstance(error, Refusal) else "forecast_input_invalid"
        print(json.dumps({"status": "failed", "reason": reason, "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2
    args.output.write_text(report, encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps({"schema_version": "forecast-reply.v1", "results": results},
                                                           ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("KABO_FORECAST_REPLY_BEGIN")
    print(report, end="")
    print("KABO_FORECAST_REPLY_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
