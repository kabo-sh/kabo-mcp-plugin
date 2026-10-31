#!/usr/bin/env python3
"""Share the recommendation seats across the Creator's signature content items.

With a saved account profile attached, the Request lists the Creator's signature content (their own
recurring kinds of content, each with a weight) and the Gate says, per candidate, which item it
reproduces (`signature_content_id`, or null for none). This script fills a fixed number of seats so
every item the Creator is known for gets its share of what is recommended:

  python3 scripts/allocate_signature_content.py --platform tiktok --request trend-research-request.json \\
    --gate trend-relevance-gate.json --candidates tiktok-trend-candidate-set-eligible.json \\
    --enrichment tiktok-trend-enrichment.json --output signature-content-allocation.json

Rules (rule version `signature-allocation.v1`):

- Seats per item: the largest remainder method over the weights, at least one seat per item.
  `quotas()` is the only implementation; the TikTok shortlist calls this same function.
- Only candidates the Gate kept and matched to an item compete for that item's seats. Within an item
  they rank by the mean of two percentiles across the pool: the account-relative multiple (TikTok the
  shrunk multiple, Instagram `outlier`, YouTube `account_breakout`) and public plays. A candidate
  without a multiple ranks by plays alone. A candidate in one of the Creator's accepted languages gets
  +0.05: language is a retrieval label, so it breaks near-ties and never removes a candidate.
- Within an item, maximal marginal relevance (lambda 0.7) against the seats already given to that item;
  similarity is the largest of same author 1.0, same sound 0.8 and the hashtag Jaccard index.
- One seat per author across all items.
- An item without enough candidates gives its seats to the other items first (one at a time, heaviest
  item first), then to candidates that matched no item. Seats nobody can fill are the `shortfall`.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trend_gate_contract import classifications, signature_content_ids  # noqa: E402

SCHEMA = "signature-content-allocation.v1"
RULE_VERSION = "signature-allocation.v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
DEFAULT_SEATS = 12
MMR_LAMBDA = 0.7
LANGUAGE_BONUS = 0.05
SAME_AUTHOR = 1.0
SAME_SOUND = 0.8
HASHTAG = re.compile(r"#(\w+)", re.UNICODE)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


# --------------------------------------------------------------------------- seats


def quotas(entries: list[tuple[str, float]], total: int) -> dict[str, int]:
    """每个主打内容分几个名额：先每类 1 个，剩下的按权重用最大余数法分。

    名额函数只此一份：TikTok 的 shortlist 预分配与这里的最终分配都调它，所以同一组权重与名额数
    在两处得到同一个结果。余数相同时先给权重大的，再按 Request 里的顺序。名额比类数少时，
    只有权重最大的那几类各得 1 个。
    """
    ids = [str(entry_id) for entry_id, _ in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("signature content ids must be unique")
    result = {entry_id: 0 for entry_id in ids}
    if total <= 0 or not ids:
        return result
    weights = [w if isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) and w > 0 else 0.0
               for _, w in entries]
    order = sorted(range(len(ids)), key=lambda index: (-weights[index], index))
    if total < len(ids):
        for index in order[:total]:
            result[ids[index]] = 1
        return result
    for entry_id in ids:
        result[entry_id] = 1
    rest = total - len(ids)
    weight_sum = sum(weights)
    shares = [w / weight_sum * rest if weight_sum > 0 else rest / len(ids) for w in weights]
    floors = [math.floor(share) for share in shares]
    for index, value in enumerate(floors):
        result[ids[index]] += value
    left = rest - sum(floors)
    by_remainder = sorted(range(len(ids)), key=lambda index: (-(shares[index] - floors[index]), -weights[index], index))
    for index in by_remainder[:left]:
        result[ids[index]] += 1
    return result


def similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    values = [0.0]
    if left.get("author") and left["author"] == right.get("author"):
        values.append(SAME_AUTHOR)
    if left.get("sound") and left["sound"] == right.get("sound"):
        values.append(SAME_SOUND)
    a, b = left.get("hashtags") or frozenset(), right.get("hashtags") or frozenset()
    if a and b:
        values.append(len(a & b) / len(a | b))
    return max(values)


def _pick(pool: list[dict[str, Any]], chosen: list[dict[str, Any]], authors: set[str],
          taken: set[str]) -> dict[str, Any] | None:
    best: tuple[tuple[float, float, str], dict[str, Any]] | None = None
    for candidate in pool:
        if candidate["key"] in taken or (candidate.get("author") and candidate["author"] in authors):
            continue
        penalty = max((similarity(candidate, other) for other in chosen), default=0.0)
        value = MMR_LAMBDA * candidate["score"] - (1 - MMR_LAMBDA) * penalty
        rank = (-value, -candidate["score"], candidate["key"])
        if best is None or rank < best[0]:
            best = (rank, candidate)
    return best[1] if best else None


def select(candidates: list[dict[str, Any]], entries: list[tuple[str, float]], total: int) -> dict[str, Any]:
    """Fill `total` seats. Each candidate is `{key, class, author, sound, hashtags, score}`.

    `class` is the signature content id the Gate gave it, or None when it matched no item. Returns
    `{slots, per_content, shortfall}` with slots in the order they were filled.
    """
    order = [str(entry_id) for entry_id, _ in entries]
    quota = quotas(entries, total)
    by_class: dict[str | None, list[dict[str, Any]]] = {entry_id: [] for entry_id in order}
    by_class[None] = []
    for candidate in candidates:
        cls = candidate.get("class")
        if cls is not None and cls not in quota:
            raise ValueError(f"candidate {candidate['key']} names unknown signature content {cls}")
        by_class[cls].append(candidate)
    chosen: dict[str | None, list[dict[str, Any]]] = {cls: [] for cls in by_class}
    authors: set[str] = set()
    taken: set[str] = set()
    slots: list[tuple[dict[str, Any], str | None]] = []

    def take(cls: str | None) -> bool:
        candidate = _pick(by_class[cls], chosen[cls], authors, taken)
        if candidate is None:
            return False
        chosen[cls].append(candidate)
        taken.add(candidate["key"])
        if candidate.get("author"):
            authors.add(candidate["author"])
        slots.append((candidate, cls))
        return True

    for cls in order:
        for _ in range(quota[cls]):
            if not take(cls):
                break
    # 某类凑不满，空出来的名额先轮流让给其他类（权重大的先拿），再让给哪类都不像的候选。
    spare = total - len(slots)
    progress = True
    while spare > 0 and progress:
        progress = False
        for cls in order:
            if spare and take(cls):
                spare -= 1
                progress = True
    while spare > 0 and take(None):
        spare -= 1
    filled = {entry_id: sum(1 for _, cls in slots if cls == entry_id) for entry_id in order}
    return {
        "slots": [{"content_key": candidate["key"], "signature_content_id": cls, "rank": rank}
                  for rank, (candidate, cls) in enumerate(slots, start=1)],
        "per_content": {entry_id: {"quota": quota[entry_id], "filled": filled[entry_id]} for entry_id in order},
        "shortfall": total - len(slots),
    }


# --------------------------------------------------------------------------- inputs


def signature_entries(request: dict[str, Any]) -> list[tuple[str, float]]:
    creator = request.get("creator_profile") if isinstance(request.get("creator_profile"), dict) else {}
    entries = []
    for item in creator.get("signature_content") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            weight = item.get("weight")
            entries.append((item["id"], float(weight) if isinstance(weight, (int, float)) and not isinstance(weight, bool) else 0.0))
    return entries


def language_tag(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return re.split(r"[-_]", value.strip().casefold(), maxsplit=1)[0] or None


def accepted_languages(request: dict[str, Any]) -> set[str]:
    creator = request.get("creator_profile") if isinstance(request.get("creator_profile"), dict) else {}
    return {tag for tag in (language_tag(value) for value in creator.get("accepted_languages") or []) if tag}


def language_bonus(language: Any, accepted: set[str]) -> float:
    tag = language_tag(language)
    return LANGUAGE_BONUS if tag and tag in accepted else 0.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def author_of(item: dict[str, Any], platform: str) -> str:
    if platform == "youtube":
        channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
        return str(channel.get("id") or "").strip()
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    return str(author.get("handle") or "").strip().lstrip("@").casefold()


def views_of(item: dict[str, Any], platform: str) -> float | None:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    names = ("play_count", "views") if platform == "instagram" else ("views",)
    for name in names:
        value = _number(metrics.get(name))
        if value is not None:
            return value
    return None


def multiple_of(item: dict[str, Any], platform: str) -> float | None:
    if platform == "youtube":
        proof = item.get("account_breakout") if isinstance(item.get("account_breakout"), dict) else {}
        return _number(proof.get("multiple"))
    outlier = item.get("outlier") if isinstance(item.get("outlier"), dict) else {}
    if platform == "tiktok":
        # TikTok 用作者收缩倍数：原始倍数在作者样本少时会被一两条作品带偏。
        shrunk = outlier.get("shrunk") if isinstance(outlier.get("shrunk"), dict) else {}
        return _number(shrunk.get("multiple"))
    return _number(outlier.get("multiple"))


def sound_of(item: dict[str, Any], platform: str) -> str | None:
    if platform == "instagram":
        signals = item.get("media_signals") if isinstance(item.get("media_signals"), dict) else {}
        value = signals.get("audio_id")
    else:
        value = item.get("sound_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def hashtags_of(item: dict[str, Any]) -> frozenset[str]:
    tags = item.get("hashtags")
    if isinstance(tags, list):
        return frozenset(str(tag).strip().lstrip("#").casefold() for tag in tags if str(tag).strip().lstrip("#"))
    text = " ".join(str(item.get(field) or "") for field in ("caption", "title", "description"))
    return frozenset(tag.casefold() for tag in HASHTAG.findall(text))


def percentiles(values: dict[str, float | None]) -> dict[str, float | None]:
    """Mid-rank percentile in [0, 1] among the values present; None stays None."""
    present = sorted(value for value in values.values() if value is not None)
    result: dict[str, float | None] = {}
    for key, value in values.items():
        if value is None:
            result[key] = None
            continue
        below = sum(1 for other in present if other < value)
        equal = sum(1 for other in present if other == value)
        result[key] = (below + 0.5 * equal) / len(present)
    return result


def build(request: dict[str, Any], gate: dict[str, Any], candidates: dict[str, Any], enrichment: dict[str, Any],
          platform: str, seats: int = DEFAULT_SEATS) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(PLATFORMS)}")
    if not 1 <= seats <= 50:
        raise ValueError("seats must be between 1 and 50")
    entries = signature_entries(request)
    if not entries:
        raise ValueError("the Request carries no creator_profile.signature_content to allocate")
    matched = signature_content_ids(gate)
    # Gate 一行都没有时（这轮没有候选）照常输出全是 shortfall 的分配，空结果仍要走到报告；
    # 有行却没有这一列，才是没按画像打分。
    if not matched and gate.get("items"):
        raise ValueError("the Gate has no signature_content column; score the fifth number and run rank again")
    known = {entry_id for entry_id, _ in entries}
    unknown = sorted({value for value in matched.values() if value is not None} - known)
    if unknown:
        raise ValueError(f"the Gate names signature content the Request does not list: {unknown}")
    roles = classifications(gate, enrichment.get("applied_policy"))
    signals = {str(item.get("content_key")): item for item in candidates.get("items") or [] if isinstance(item, dict)}
    accepted = accepted_languages(request)
    pool = []
    for item in enrichment.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("content_key") or "")
        # 闸门没判过的条目（理论上服务端只回 shortlist 里的）不知道像哪个主打内容，不占名额；
        # 这时候 enrichment 已经花过了，为它停掉整个 rank 不划算。
        if roles.get(key, "reject") == "reject":
            continue
        merged = {**signals.get(key, {}), **item}
        pool.append((key, merged))
    if len({key for key, _ in pool}) != len(pool):
        raise ValueError("duplicate enrichment content_key")
    heat = percentiles({key: views_of(item, platform) for key, item in pool})
    breakout = percentiles({key: multiple_of(item, platform) for key, item in pool})
    rows = []
    for key, item in pool:
        parts = [value for value in (breakout[key], heat[key]) if value is not None]
        score = sum(parts) / len(parts) if parts else 0.0
        rows.append({"key": key, "class": matched.get(key), "author": author_of(item, platform),
                     "sound": sound_of(item, platform), "hashtags": hashtags_of(item),
                     "score": score + language_bonus(item.get("language"), accepted)})
    result = select(rows, entries, seats)
    return {"schema": SCHEMA, "rule_version": RULE_VERSION, **result}


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--enrichment", type=Path, required=True)
    parser.add_argument("--seats", type=int, default=DEFAULT_SEATS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(load(args.request), load(args.gate), load(args.candidates), load(args.enrichment),
                       args.platform, args.seats)
        write_json_atomic(args.output, result)
        print(json.dumps({"status": "ok", "path": str(args.output), "rule_version": RULE_VERSION,
                          "per_content": result["per_content"], "shortfall": result["shortfall"]}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
