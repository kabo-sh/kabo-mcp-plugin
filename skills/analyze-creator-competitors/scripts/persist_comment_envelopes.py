#!/usr/bin/env python3
"""Persist list_comments envelopes and project comment text only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "competitor-audience-comments.v1"
DATA_STATUSES = frozenset({"completed", "completed_partial", "partial"})
TERMINAL_STATUSES = DATA_STATUSES | {"failed", "unsupported", "blocked_setup"}
# A comment-to-get CTA names its keyword by shape, not by a per-language verb list: the keyword is
# quoted (any quote style) or written in capitals. Single-quote pairs must not touch a letter on the
# outside, so apostrophes (I'll, don't) never open or close a quote.
QUOTE_PAIRS = (
    ('"', '"'),
    ("'", "'"),
    ("\u201c", "\u201d"),
    ("\u2018", "\u2019"),
    ("\u201e", "\u201c"),
    ("\u300c", "\u300d"),
    ("\u300e", "\u300f"),
    ("\u00ab", "\u00bb"),
)
APOSTROPHE_LIKE = frozenset({"'", "\u2019"})
QUOTED_TOKENS = tuple(
    re.compile(
        (r"(?<!\w)" if close in APOSTROPHE_LIKE else "")
        + re.escape(open_)
        + f"([^{re.escape(close)}\\n]{{1,40}})"
        + re.escape(close)
        + (r"(?!\w)" if close in APOSTROPHE_LIKE else "")
    )
    for open_, close in QUOTE_PAIRS
)
MIN_CAPITALIZED_LETTERS = 3
INVENTED_STUB_MARKERS = (
    "unavailable in local persistence",
    "envelope unavailable",
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unwrap(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    contents = raw.get("content")
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.lstrip().startswith("{"):
                return unwrap(json.loads(text))
    return raw


def envelope_list(raw: Any) -> list[dict[str, Any] | None]:
    payload = unwrap(raw)
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        # Keep empty slots: results[i] belongs to targets[i], so dropping a gap would shift
        # every later envelope onto the wrong post.
        rows = [unwrap(item) for item in payload["results"]]
        return [item if isinstance(item, dict) else None for item in rows]
    if isinstance(payload, dict) and isinstance(payload.get("runs"), dict):
        return [unwrap(item) for item in payload["runs"].values() if isinstance(item, dict)]
    if isinstance(payload, list):
        return [unwrap(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("comment source must be one envelope, results[], or runs{}")


def capitalized_words(caption: str) -> list[str]:
    """All-capital words of three or more letters (KIT, LIBRO) in any cased script."""
    return [
        word
        for word in re.findall(r"\w+", caption)
        if word.isupper() and sum(char.isalpha() for char in word) >= MIN_CAPITALIZED_LETTERS
    ]


def caption_cta_tokens(caption: str) -> set[str]:
    """Quoted or all-capital tokens a comment could echo back. Language-agnostic by shape."""
    text = caption or ""
    candidates = [match.group(1) for pattern in QUOTED_TOKENS for match in pattern.finditer(text)]
    candidates += capitalized_words(text)
    return {token.casefold() for token in (value.strip() for value in candidates) if folded_text(token)}


def folded_text(value: str) -> str:
    return re.sub(r"\W+", "", value or "", flags=re.UNICODE).casefold()


def is_cta_echo(text: str, tokens: set[str]) -> bool:
    """True only when the whole comment is the caption token. Long replies stay."""
    folded = folded_text(text)
    if not folded or not tokens:
        return False
    return any(folded == folded_text(token) for token in tokens)


def comment_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw = data.get("rows")
    if not isinstance(raw, list):
        raw = data.get("comments") if isinstance(data.get("comments"), list) else []
    rows: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        user = entry.get("user") if isinstance(entry.get("user"), dict) else {}
        author = (
            str(entry.get("author") or "").strip()
            or str(user.get("username") or "").strip()
            or str(user.get("nickname") or "").strip()
            or None
        )
        rows.append(
            {
                "id": entry.get("id") or entry.get("cid"),
                "author": author,
                "text": text,
            }
        )
    return rows


def assert_provider_envelope(envelope: dict[str, Any], *, index: int) -> None:
    summary = str(envelope.get("summary") or "").casefold()
    if any(marker in summary for marker in INVENTED_STUB_MARKERS):
        raise ValueError(
            f"envelope[{index}] looks hand-written, not a connector result: {envelope.get('summary')}"
        )
    if envelope.get("operation") not in {None, "list_comments"}:
        raise ValueError(f"envelope[{index}] operation must be list_comments")
    if not str(envelope.get("provider") or "").strip() and envelope.get("status") not in {
        "unsupported",
        "failed",
        "blocked_setup",
    }:
        raise ValueError(
            f"envelope[{index}] is missing provider; persist the connector payload, do not invent a stub"
        )
    if envelope.get("status") not in TERMINAL_STATUSES:
        raise ValueError(
            f"envelope[{index}] has an unknown or non-terminal status"
        )


ENVELOPE_ID_KEYS = ("aweme_id", "video_id", "media_id", "shortcode", "code")


def envelope_content_id(envelope: dict[str, Any]) -> str | None:
    data = envelope.get("data")
    if isinstance(data, dict):
        for key in ENVELOPE_ID_KEYS:
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def has_result_slots(raw: Any) -> bool:
    """True when the source is a `results[]` bundle, whose index i was placed for targets[i]."""
    payload = unwrap(raw)
    return isinstance(payload, dict) and isinstance(payload.get("results"), list)


def pair_envelopes(
    planned: list[Any], envelopes: list[dict[str, Any] | None], *, positional: bool
) -> list[dict[str, Any] | None]:
    """Line envelopes up with targets.

    When every fetched envelope names the post it answered, pair by that id so a gap or a
    reordered fetch cannot attach comments to the wrong post. Otherwise pair by position, which
    is only trustworthy for a `results[]` bundle (each envelope was placed at its target's
    index): there a short list means the tail was never fetched. Any other source shape must
    still hold exactly one envelope per target. More envelopes than targets is always an error.
    """
    mismatch = ValueError(
        f"planned {len(planned)} comment fetches, source has {len(envelopes)} envelopes"
    )
    if len(envelopes) > len(planned):
        raise mismatch
    present = [envelope for envelope in envelopes if envelope is not None]
    target_ids = [
        str(target.get("content_id")) if isinstance(target, dict) and target.get("content_id") else None
        for target in planned
    ]
    ids = [envelope_content_id(envelope) for envelope in present]
    if present and all(ids) and all(target_ids):
        if len(set(ids)) != len(ids):
            raise ValueError("source has two comment envelopes for the same post")
        unknown = sorted(set(ids) - set(target_ids))
        if unknown:
            # Every envelope names its post, so a post outside the plan is a persistence
            # error, not something position could repair.
            raise ValueError(f"comment envelopes for posts not in targets: {', '.join(unknown)}")
        by_id = dict(zip(ids, present))
        return [by_id.get(target_id) for target_id in target_ids]
    if not positional and len(envelopes) != len(planned):
        raise mismatch
    return list(envelopes) + [None] * (len(planned) - len(envelopes))


def persist(targets: dict[str, Any], source: Any, output: Path, envelope_dir: Path) -> dict[str, Any]:
    if targets.get("schema_version") != "competitor-comment-targets.v1":
        raise ValueError("expected competitor-comment-targets.v1")
    planned = targets.get("targets") or []
    if not isinstance(planned, list):
        raise ValueError("targets.targets must be a list")
    if not planned:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "platform": targets.get("platform"),
            "connector_id": targets.get("connector_id"),
            "operation": targets.get("operation"),
            "post_count": 0,
            "comment_count": 0,
            "texts": [],
            "posts": [],
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    envelopes = pair_envelopes(planned, envelope_list(source), positional=has_result_slots(source))
    posts: list[dict[str, Any]] = []
    texts: list[str] = []
    cta_dropped = 0
    envelope_dir.mkdir(parents=True, exist_ok=True)
    for index, (target, envelope) in enumerate(zip(planned, envelopes)):
        if not isinstance(target, dict):
            raise ValueError(f"targets.targets[{index}] must be an object")
        if envelope is None:
            # Not fetched (for example the turn's retrieval budget ran out): no comment
            # evidence for this post, but the posts that were fetched still count.
            posts.append(
                {
                    "content_id": target.get("content_id"),
                    "handle": target.get("handle"),
                    "url": target.get("url"),
                    "caption": str(target.get("caption") or ""),
                    "status": "not_fetched",
                    "rows": [],
                }
            )
            continue
        assert_provider_envelope(envelope, index=index)
        name = f"comment-envelope-{index + 1:02d}.json"
        path = envelope_dir / name
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Failure paths may carry data-shaped diagnostics; never project them as audience evidence.
        rows = comment_rows(envelope.get("data")) if envelope.get("status") in DATA_STATUSES else []
        tokens = caption_cta_tokens(str(target.get("caption") or ""))
        for row in rows:
            if is_cta_echo(row["text"], tokens):
                cta_dropped += 1
                continue
            texts.append(row["text"])
        posts.append(
            {
                "content_id": target.get("content_id"),
                "handle": target.get("handle"),
                "url": target.get("url"),
                "caption": str(target.get("caption") or ""),
                "status": envelope.get("status"),
                "limitations": envelope.get("limitations", []),
                "envelope_path": str(path),
                "rows": rows,
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "platform": targets.get("platform"),
        "connector_id": targets.get("connector_id"),
        "operation": targets.get("operation"),
        "post_count": len(posts),
        "comment_count": len(texts),
        "cta_dropped": cta_dropped,
        "texts": texts,
        "posts": posts,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("audience-comments.json"))
    parser.add_argument("--envelope-dir", type=Path)
    args = parser.parse_args()
    try:
        envelope_dir = args.envelope_dir or args.output.parent
        payload = persist(load(args.targets), load(args.source), args.output, envelope_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "ok", "comment_count": payload["comment_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
