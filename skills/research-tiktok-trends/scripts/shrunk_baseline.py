#!/usr/bin/env python3
"""Shrunk account baselines and multiples: rule content-profile.v1, standard library only.

An account's usual reach is the median of ln(1 + views) over its own mature posts of one format.
A median from a handful of posts swings with any one of them, so it is pulled toward a prior by
k pseudo-posts:  m_hat = (n * m + k * mu0) / (n + k).  A post's multiple is
exp(ln(1 + views) - m_hat); 2 or more is a breakout. The prior mu0 is an argument: the caller decides
where it comes from (this package uses the median of the round's author medians, `round_authors`).

  python3 scripts/shrunk_baseline.py --samples samples.json --format short_video --prior-log-median 8.5

prints the baseline for one format of one account (null below three mature posts).
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# 口径常量与 content-profile.v1 的 golden 制品逐项一致；测试对拍制品副本，改任何一项都得先升规则版本。
RULE_VERSION = "content-profile.v1"
FORMULA_VERSION = "shrunk-log-median.v1"
K = 5
MATURITY_DAYS = {"short_video": 7, "long_video": 14}
MIN_SAMPLE = 3
BREAKOUT_MULTIPLE = 2
SHORT_VIDEO_MAX_SECONDS = 180
FORMATS = ("short_video", "long_video")
DAY_MS = 86_400_000


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def views_of(value: Any) -> float | None:
    """A usable platform count: finite and non-negative. Missing is None, never 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def log_view(views: float) -> float:
    return math.log(1.0 + views)


def median(values: list[float]) -> float | None:
    """偶数个时取中间两个的均值；与 golden 的 median 公式一致。"""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def classify_format(platform: str, duration_seconds: Any = None, is_video: Any = None,
                    shorts_tagged: Any = None) -> str:
    """short_video / long_video / excluded, by the same rule the account profile counts formats with.

    TikTok duration 0 is a photo post and Instagram non-video is a photo or carousel: both are left
    out of every baseline. Without a duration Instagram and TikTok default to short_video; YouTube is
    short only when tagged #shorts.
    """
    seconds = views_of(duration_seconds)
    if platform == "tiktok" and seconds == 0:
        return "excluded"
    if platform == "instagram" and is_video is False:
        return "excluded"
    if seconds is not None:
        return "short_video" if seconds <= SHORT_VIDEO_MAX_SECONDS else "long_video"
    if platform == "youtube":
        return "short_video" if shorts_tagged is True else "long_video"
    return "short_video"


def is_mature(published_at: Any, observed_at: Any, content_format: str) -> bool:
    published, observed = parse_time(published_at), parse_time(observed_at)
    if published is None or observed is None or content_format not in MATURITY_DAYS:
        return False
    # 按毫秒比，恰好满 maturityDays 天算成熟（golden 的 exactly_seven_days_is_mature）。
    elapsed_ms = (observed - published).total_seconds() * 1000
    return elapsed_ms >= MATURITY_DAYS[content_format] * DAY_MS


def mature_logs(samples: Iterable[dict[str, Any]], content_format: str) -> list[float]:
    """ln(1 + views) of every sample that may enter this format's baseline.

    A sample is `{format, published_at, observed_at, views, views_basis}`. Only platform counts
    (`views_basis == "platform_count"`) of this format that have matured enter; a missing count is
    skipped, never read as 0.
    """
    logs = []
    for sample in samples:
        if not isinstance(sample, dict) or sample.get("format") != content_format:
            continue
        if sample.get("views_basis", "platform_count") != "platform_count":
            continue
        views = views_of(sample.get("views"))
        if views is None or not is_mature(sample.get("published_at"), sample.get("observed_at"), content_format):
            continue
        logs.append(log_view(views))
    return logs


def shrink(logs: list[float], prior_log_median: float) -> float:
    n = len(logs)
    m = median(logs)
    return (n * m + K * prior_log_median) / (n + K)


def baseline(samples: Iterable[dict[str, Any]], content_format: str, prior_log_median: float) -> dict[str, Any] | None:
    """The shrunk baseline of one account and format, or None below MIN_SAMPLE mature posts."""
    if content_format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    if views_of(prior_log_median) is None:
        raise ValueError("prior_log_median must be a finite non-negative log median")
    logs = mature_logs(samples, content_format)
    if len(logs) < MIN_SAMPLE:
        return None
    m = median(logs)
    m_hat = shrink(logs, prior_log_median)
    return {
        "n": len(logs),
        "k": K,
        "maturityDays": MATURITY_DAYS[content_format],
        "logMedian": m,
        "shrunkLogMedian": m_hat,
        "rawMedianViews": math.exp(m) - 1.0,
        "shrunkMedianViews": math.exp(m_hat) - 1.0,
        "priorMedianViews": math.exp(prior_log_median) - 1.0,
    }


def multiple(views: Any, shrunk_log_median: float) -> dict[str, Any] | None:
    count = views_of(views)
    if count is None:
        return None
    value = math.exp(log_view(count) - shrunk_log_median)
    return {"multiple": value, "breakout": value >= BREAKOUT_MULTIPLE}


def round_authors_prior(author_logs: Iterable[list[float]]) -> float | None:
    """本轮各作者对数中位数的中位数（prior source `round_authors`）；没有任何作者有样本时为 None。"""
    medians = [median(logs) for logs in author_logs if logs]
    return median([value for value in medians if value is not None])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=Path, required=True, help="JSON array of samples")
    parser.add_argument("--format", choices=FORMATS, required=True)
    parser.add_argument("--prior-log-median", type=float, required=True)
    args = parser.parse_args()
    try:
        samples = json.loads(args.samples.read_text(encoding="utf-8"))
        if not isinstance(samples, list):
            raise ValueError("samples must be a JSON array")
        print(json.dumps(baseline(samples, args.format, args.prior_log_median), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
