#!/usr/bin/env python3
"""Expand a WatchSet into the public-video-media requests, in the order they are issued.

Does not call any tool. `batches` groups the requests (`batch_ceiling` per group, at least two
each); the groups only fix the issue order. Every request is sent as its own individual call to
the named public tool for its operation, never as one batch call: a batch that fails as a whole
erases the evidence of every request in it. The grouping is kept so the plan's shape, and every
script that reads it, stays unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "media-job-plan.v1"
CONNECTOR_ID = "public-video-media"
OPERATIONS = (
    "collect_public_metadata",
    "fetch_transcript",
    "extract_keyframes",
)
# 后台默认的时长自适应采样（duration_scaled）先给开头 0–2.5 秒每 0.5 秒一帧，正文从第 3 秒起，
# 结尾 2 秒再给 4 帧；帧数上限只摊薄正文，不动开头。下游只读开头：watch_media.py 让模型看
# 3 秒以内最多 5 张，作者包也只列 3 秒以内的帧（其余帧要模型先看过再用 --frame-object-ref 补，
# 而 Web 每回合最多 60 张图，开头已占 50 张）。12 帧 = 开头 6 + 正文 2（含第 3 秒那一帧）+ 结尾 4：
# 3 秒以内的帧与 60 帧时逐张相同，另给结尾和一张中段作余量；正文被拉稀时信封照常写明
# body_degraded 与间隔。不选 10：正文一帧都排不上时 body_degraded 为 false，「没看中段」就无人声明。
# 以前是 {"fps": 1, "max_frames": 60}：fps 不带 sampling 时后台忽略；60 帧里下游只用开头那几张，
# 其余帧只是让组合结果变大、抽帧变慢。static_host.py job-call 的上限 60 不变。
KEYFRAME_PARAMS = {"sampling": "duration_scaled", "max_frames": 12}
# Requests per group in the issue order. The bounds come from the old batch interface
# (two to four requests per batch); they no longer limit any call, since each request is
# its own call, and are kept so existing plans keep their shape.
MAX_BATCH_REQUESTS = 4
MIN_BATCH_REQUESTS = 2


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _operations(url: str) -> list[dict[str, Any]]:
    return [
        {"operation": "collect_public_metadata", "params": {"url": url}},
        {"operation": "fetch_transcript", "params": {"url": url}},
        {
            "operation": "extract_keyframes",
            "params": {"url": url, **KEYFRAME_PARAMS},
        },
    ]


def _pack(requests: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Fewest groups the ceiling allows, sizes spread evenly (at least two per group)."""
    if not requests:
        return []
    count = -(-len(requests) // MAX_BATCH_REQUESTS)
    size, extra = divmod(len(requests), count)
    chunks: list[list[dict[str, Any]]] = []
    start = 0
    for number in range(count):
        end = start + size + (1 if number < extra else 0)
        chunks.append(requests[start:end])
        start = end
    return chunks


def plan_media_jobs(watch_set: dict[str, Any]) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in watch_set.get("selected") or []:
        if not isinstance(raw, dict):
            continue
        content_id = str(raw.get("content_id") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not content_id:
            continue
        if not url:
            skipped.append({"content_id": content_id, "reason": "missing_url"})
            continue
        jobs.append(
            {
                "content_id": content_id,
                "url": url,
                "role": raw.get("role"),
                "format": raw.get("format"),
                "operations": _operations(url),
            }
        )

    requests = [
        {
            "content_id": job["content_id"],
            "url": job["url"],
            "connector_id": CONNECTOR_ID,
            "operation": operation["operation"],
            "params": operation["params"],
        }
        for job in jobs
        for operation in job["operations"]
    ]
    batches = [
        {"index": number, "requests": chunk}
        for number, chunk in enumerate(_pack(requests), start=1)
    ]

    empty_reason = None
    if not jobs:
        if watch_set.get("empty_reason") == "no_watchable_videos":
            empty_reason = "no_watchable_videos"
        else:
            empty_reason = "watch_set_empty"

    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": str(watch_set.get("analysis_id") or "").strip(),
        "connector_id": CONNECTOR_ID,
        "jobs": jobs,
        "batches": batches,
        "batch_ceiling": MAX_BATCH_REQUESTS,
        "skipped": skipped,
        "empty_reason": empty_reason if not jobs else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("watch_set", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    watch_set = load_json(args.watch_set)
    payload = plan_media_jobs(watch_set)
    if not payload["analysis_id"]:
        raise ValueError("watch_set.json is missing analysis_id")
    write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
