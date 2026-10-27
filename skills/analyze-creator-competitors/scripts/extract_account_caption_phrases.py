#!/usr/bin/env python3
"""Extract the subject's recurring content forms from captions and YouTube titles.

The contract is "phrases that recur in the Creator's own captions": derive them from the recent
public sample, never from one caption or a model-written list. Uses the validator's filter (two or
more terms, not a call to action), keeps phrases seen in at least two captions, and drops a trailing
bare episode number from a series title. Caption and title samples qualify independently;
title phrases supplement rather than replace the legacy caption result.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from persist_connector_json import load_json_object
from validate_discovery_intents import _is_cta_or_deictic, _normalized


SCHEMA_VERSION = "competitor-caption-phrases.v1"
MAX_PHRASES = 8
MIN_DF = 2
MAX_TERMS = 4


def load(path: Path) -> Any:
    return load_json_object(path)


def caption_texts(value: Any, found: list[str] | None = None) -> list[str]:
    found = found if found is not None else []
    if isinstance(value, dict):
        caption = value.get("caption")
        if isinstance(caption, str) and caption.strip():
            found.append(caption)
        elif isinstance(caption, dict):
            text = caption.get("text")
            if isinstance(text, str) and text.strip():
                found.append(text)
        edges = value.get("edge_media_to_caption")
        if isinstance(edges, dict):
            for edge in edges.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                node = edge.get("node")
                if not isinstance(node, dict):
                    continue
                text = node.get("text")
                if isinstance(text, str) and text.strip():
                    found.append(text)
        for key, child in value.items():
            if key in {"caption", "edge_media_to_caption"}:
                continue
            caption_texts(child, found)
    elif isinstance(value, list):
        for child in value:
            caption_texts(child, found)
    return found


def text_observations(value: Any, video_ref: str | None = None):
    """Yield literal caption/title observations with a shared YouTube video identity.

    Keep descriptions/transcripts and arbitrary report titles outside this contract.
    One video's two fields must not manufacture two supporting videos.
    """
    if isinstance(value, dict):
        canonical_video = (
            isinstance(value.get("channel_id"), str)
            and re.fullmatch(r"UC[\w-]{22}", value["channel_id"])
            and isinstance(value.get("id"), str)
            and re.fullmatch(r"[\w-]{11}", value["id"])
        )
        if canonical_video:
            video_ref = f"{value['channel_id']}:{value['id']}"
        caption = value.get("caption")
        text = caption.get("text") if isinstance(caption, dict) else caption
        if isinstance(text, str) and text.strip():
            yield "caption", text, video_ref
        edges = value.get("edge_media_to_caption")
        if isinstance(edges, dict):
            for edge in edges.get("edges") or []:
                node = edge.get("node") if isinstance(edge, dict) else None
                text = node.get("text") if isinstance(node, dict) else None
                if isinstance(text, str) and text.strip():
                    yield "caption", text, video_ref
        title = value.get("title")
        if canonical_video and isinstance(title, str) and title.strip():
            yield "title", title, video_ref
        for key, child in value.items():
            if key not in {"caption", "edge_media_to_caption"}:
                yield from text_observations(child, video_ref)
    elif isinstance(value, list):
        for child in value:
            yield from text_observations(child, video_ref)


def content_texts(value: Any) -> list[str]:
    """Preserve caption context and add canonical titles, without duplicate text."""
    captions = caption_texts(value)
    titles = [text for source, text, _ref in text_observations(value) if source == "title"]
    seen: set[str] = set()
    texts: list[str] = []
    for text in [*captions, *titles]:
        key = _normalized(text)
        if key not in seen:
            seen.add(key)
            texts.append(text)
    return texts


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def strip_trailing_digits(tokens: list[str]) -> list[str]:
    while tokens and tokens[-1].isdigit():
        tokens = tokens[:-1]
    return tokens


def phrases_from_caption(text: str) -> list[str]:
    tokens = strip_trailing_digits(_normalized(first_line(text)).split())
    if len(tokens) < 2 or len(tokens) > MAX_TERMS:
        return []
    phrase = " ".join(tokens)
    if _is_cta_or_deictic(phrase):
        return []
    phrases = [phrase]
    if len(tokens) >= 3:
        prefix = " ".join(tokens[:2])
        if not _is_cta_or_deictic(prefix):
            phrases.append(prefix)
    return phrases


def extract(envelopes: list[Any], *, count_basis: str = "distinct_captions") -> dict[str, Any]:
    if count_basis not in {"distinct_captions", "post_captions"}:
        raise ValueError("Unknown caption count basis")
    samples: dict[str, list[tuple[str, str]]] = {"caption": [], "title": []}
    seen_texts: dict[str, set[str]] = {"caption": set(), "title": set()}
    seen_videos: set[tuple[str, str, str]] = set()
    for envelope in envelopes:
        for source, text, video_ref in text_observations(envelope):
            key = _normalized(text)
            if count_basis == "distinct_captions" and key in seen_texts[source]:
                continue
            if video_ref is not None:
                identity = (source, video_ref, key)
                if identity in seen_videos:
                    continue
                seen_videos.add(identity)
            seen_texts[source].add(key)
            # Preserve legacy text dedup in discovery and per-post counts in Lite.
            observation_ref = video_ref or (
                f"text:{key}" if count_basis == "distinct_captions"
                else f"observation:{source}:{len(samples[source])}"
            )
            samples[source].append((text, observation_ref))
    results = {
        source: extract_caption_sample(
            [text for text, _ref in sample], allow_single=count_basis == "distinct_captions"
        )
        for source, sample in samples.items()
    }
    if not samples["title"]:
        return results["caption"]
    if not samples["caption"]:
        return results["title"]
    # The existing eight caption hints keep their order and capacity. Titles have
    # their own eight-hint bound; a shared top-eight would evict legacy evidence.
    ranked = list(dict.fromkeys([
        *results["caption"]["caption_phrases"], *results["title"]["caption_phrases"]
    ]))
    support: dict[str, set[str]] = {phrase: set() for phrase in ranked}
    for sample in samples.values():
        for text, observation_ref in sample:
            for phrase in phrases_from_caption(text):
                if phrase in support:
                    support[phrase].add(observation_ref)
    return {
        "schema_version": SCHEMA_VERSION,
        "caption_phrases": ranked,
        "phrase_caption_counts": {phrase: len(support[phrase]) for phrase in ranked},
        "source_caption_count": len({
            (observation_ref, _normalized(text))
            for sample in samples.values() for text, observation_ref in sample
        }),
        "source_text_counts": {source: len(sample) for source, sample in samples.items()},
        "phrase_sources": {
            phrase: [source for source, result in results.items() if phrase in result["caption_phrases"]]
            for phrase in ranked
        },
    }


def extract_caption_sample(captions: list[str], *, allow_single: bool = False) -> dict[str, Any]:
    """Count one observation per supplied caption; callers deduplicate post IDs.

    Discovery's extract() first deduplicates caption text and permits a lone form.
    Per-post frequency callers preserve equal captions from different posts and
    keep allow_single=False so one post is never described as repetition.
    """
    captions = [text for text in captions if isinstance(text, str) and text.strip()]
    counts: Counter[str] = Counter()
    for text in captions:
        for phrase in dict.fromkeys(phrases_from_caption(text)):
            counts[phrase] += 1
    ranked = [
        phrase
        for phrase, count in counts.most_common()
        if count >= MIN_DF
    ][:MAX_PHRASES]
    # A lone completed get_post still names the form. list_reels may fail
    # (measured 2026-09-14 on one case: baseline-proxy timed out) and DF>=2
    # then drops the only caption. One usable caption keeps its form line.
    if allow_single and not ranked and len(captions) == 1:
        ranked = [phrase for phrase, _count in counts.most_common()][:MAX_PHRASES]
    return {
        "schema_version": SCHEMA_VERSION,
        "caption_phrases": ranked,
        "phrase_caption_counts": {phrase: counts[phrase] for phrase in ranked},
        "source_caption_count": len(captions),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("envelopes", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count-basis", choices=["distinct_captions", "post_captions"], default="distinct_captions",
                        help="post_captions expects one caption per already-deduplicated post; never enables the single-form hint")
    parser.add_argument(
        "--into",
        type=Path,
        help="the competitor Request to write the phrases onto (subject.caption_phrases), so they are never retyped",
    )
    args = parser.parse_args()
    try:
        envelopes = [load(path) for path in args.envelopes]
        result = extract(envelopes, count_basis=args.count_basis)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.into is not None:
            request = json.loads(args.into.read_text(encoding="utf-8"))
            if not isinstance(request, dict) or not isinstance(request.get("subject"), dict):
                raise ValueError(f"{args.into} has no subject object: write the Request first")
            # The Creator's literal wording, in order; none extracted means none attached.
            if result["caption_phrases"]:
                request["subject"]["caption_phrases"] = result["caption_phrases"]
            else:
                request["subject"].pop("caption_phrases", None)
            args.into.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", **result}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
