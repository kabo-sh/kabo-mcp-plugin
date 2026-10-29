#!/usr/bin/env python3
"""Keep the candidates a Creator with a saved account profile could learn from; write the rest down.

With the Creator's account profile attached to the Request (`creator_profile.signature_content`,
`audience_count`, `formats`), a candidate set holds content no recommendation should lead with: the
Creator's own posts, photo posts on a video scan, the other video format, paid ads, and accounts far
larger or smaller than the Creator's. This script removes those and keeps everything it cannot judge.

  python3 scripts/filter_candidate_eligibility.py --request trend-research-request.json \\
    --candidates tiktok-trend-candidate-set.json --output tiktok-trend-candidate-set-eligible.json \\
    --platform tiktok

Rules, applied per candidate:

- own content: the candidate's author is the Creator (handle; on YouTube the channel id), or the
  candidate is one of the Creator's own example posts the profile lists. The profile names a YouTube
  Creator by handle while a YouTube candidate carries only its channel id and title, so there the
  example posts are often the only own content the filter can recognise.
- photo post: a TikTok item whose duration is 0 seconds (a photo carousel). The account profile counts
  formats by the same rule, so a post it leaves out of the Creator's formats is left out here too.
- format mismatch: the duration says short_video (180 s or less) or long_video, and the Creator
  publishes only the other one. No duration, no judgment.
- advertisement: the platform marks the item as an ad.
- audience out of range: the author's followers are outside 0.3–3 times the Creator's audience.
  No follower count, no judgment.

Language is never a reason: it is a retrieval label, and a filter on it would drop the cross-language
content the Creator's format often reaches first.

When fewer than 20 candidates remain, candidates removed only for their audience size come back,
closest audience ratio first, until 20 remain; the audit names each. The output is the input candidate
set with `items` reduced (in their original order) and an `eligibility` audit added; every other field,
`candidate_set_id` included, is unchanged, so a backend that holds the full set by its id still
resolves every kept `content_key`. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

RULE_VERSION = "candidate-eligibility.v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
AUDIENCE_RANGE = (0.3, 3.0)
MINIMUM_KEPT = 20
SHORT_VIDEO_MAX_SECONDS = 180
AUDIENCE_ONLY = ["audience_out_of_range"]


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def handle_key(value: Any) -> str:
    return str(value or "").strip().lstrip("@").casefold()


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def author_keys(item: dict[str, Any], platform: str) -> set[str]:
    if platform == "youtube":
        channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
        return {key for key in (handle_key(channel.get("id")),) if key}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    return {key for key in (handle_key(author.get("handle")),) if key}


def content_ids(item: dict[str, Any]) -> set[str]:
    """The ids a candidate is known by: its content_key's id part and the platform id fields."""
    ids = set()
    key = str(item.get("content_key") or "")
    if ":" in key:
        ids.add(key.split(":", 1)[1])
    for field in ("content_id", "video_id"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            ids.add(value.strip())
    return {value for value in ids if value}


def followers(item: dict[str, Any]) -> int | None:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    for key in ("followers", "follower_count"):
        value = _count(author.get(key))
        if value is not None:
            return value
    return None


def duration(item: dict[str, Any], platform: str) -> float | None:
    if platform == "instagram":
        signals = item.get("media_signals") if isinstance(item.get("media_signals"), dict) else {}
        return _seconds(signals.get("duration_seconds"))
    return _seconds(item.get("duration_seconds"))


def format_of(item: dict[str, Any], platform: str) -> str | None:
    seconds = duration(item, platform)
    if seconds is None:
        return None
    if platform == "tiktok" and seconds == 0:
        return "photo"
    return "short_video" if seconds <= SHORT_VIDEO_MAX_SECONDS else "long_video"


def creator_fields(request: dict[str, Any]) -> dict[str, Any]:
    creator = request.get("creator_profile") if isinstance(request.get("creator_profile"), dict) else {}
    formats = [value for value in creator.get("formats") or [] if value in ("short_video", "long_video")]
    signature = [item for item in creator.get("signature_content") or [] if isinstance(item, dict)]
    own_ids = {str(value).strip() for item in signature for value in item.get("example_content_ids") or []
               if isinstance(value, str) and value.strip()}
    return {"handle": handle_key(creator.get("handle")), "audience": _count(creator.get("audience_count")),
            "formats": formats, "own_ids": own_ids, "attached": bool(signature)}


def judge(item: dict[str, Any], platform: str, creator: dict[str, Any]) -> tuple[list[str], float | None]:
    """The reasons this candidate is ineligible (empty when it stays) and its audience ratio."""
    reasons: list[str] = []
    if ((creator["handle"] and creator["handle"] in author_keys(item, platform))
            or creator["own_ids"] & content_ids(item)):
        reasons.append("own_content")
    shape = format_of(item, platform)
    if shape == "photo":
        reasons.append("photo_post")
    elif shape is not None and creator["formats"] and shape not in creator["formats"]:
        reasons.append("format_mismatch")
    if item.get("is_ad") is True:
        reasons.append("advertisement")
    ratio = None
    count = followers(item)
    if count is not None and creator["audience"]:
        ratio = count / creator["audience"]
        if not AUDIENCE_RANGE[0] <= ratio <= AUDIENCE_RANGE[1]:
            reasons.append("audience_out_of_range")
    return reasons, ratio


def filter_set(request: dict[str, Any], candidates: dict[str, Any], platform: str) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(PLATFORMS)}")
    items = candidates.get("items")
    if not isinstance(items, list):
        raise ValueError("candidate items must be an array")
    creator = creator_fields(request)
    audit: dict[str, Any] = {"rule_version": RULE_VERSION, "applied": creator["attached"],
                             "input_items": len(items)}
    if not creator["attached"]:
        # No profile attached: nothing to judge against. The set passes through unchanged.
        return {**candidates, "eligibility": {**audit, "kept_items": len(items), "excluded": [], "backfilled": []}}
    verdicts = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{position}] must be an object")
        reasons, ratio = judge(item, platform, creator)
        verdicts.append((position, item, reasons, ratio))
    kept = {position for position, _, reasons, _ in verdicts if not reasons}
    backfill = sorted((row for row in verdicts if row[2] == AUDIENCE_ONLY),
                      key=lambda row: (abs(math.log(row[3])) if row[3] else math.inf, str(row[1].get("content_key"))))
    backfilled = []
    for position, item, _, ratio in backfill:
        if len(kept) >= MINIMUM_KEPT:
            break
        kept.add(position)
        backfilled.append({"content_key": item.get("content_key"), "audience_ratio": round(ratio, 4)})
    excluded = [{"content_key": item.get("content_key"), "reasons": reasons}
                for position, item, reasons, _ in verdicts if reasons and position not in kept]
    audit.update({
        "kept_items": len(kept),
        "minimum_kept": MINIMUM_KEPT,
        "audience_count": creator["audience"],
        "audience_range": list(AUDIENCE_RANGE),
        "formats": creator["formats"],
        "excluded": excluded,
        "backfilled": backfilled,
        "unjudged": {
            "audience": sum(1 for _, item, _, _ in verdicts if followers(item) is None),
            "format": sum(1 for _, item, _, _ in verdicts if format_of(item, platform) is None),
        },
    })
    return {**candidates, "items": [item for position, item, _, _ in verdicts if position in kept],
            "eligibility": audit}


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    args = parser.parse_args()
    try:
        result = filter_set(load(args.request), load(args.candidates), args.platform)
        write_json_atomic(args.output, result)
        audit = result["eligibility"]
        print(json.dumps({"status": "ok", "path": str(args.output), "input_items": audit["input_items"],
                          "kept_items": audit["kept_items"], "excluded": len(audit["excluded"]),
                          "backfilled": len(audit["backfilled"])}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
