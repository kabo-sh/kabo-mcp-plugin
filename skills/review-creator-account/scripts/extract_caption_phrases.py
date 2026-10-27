#!/usr/bin/env python3
"""Extract the Creator's own recurring caption wording, deterministically.

Downstream retrieval matches literally against captions other creators write. A mechanism
described in analyst prose ("single product restyled across contrasting visual identities")
retrieves nothing, while the words the Creator actually captions with ("visual styles")
retrieve the same format. Synthesis necessarily rewrites captions into prose, and when the
report language differs from the content language it also translates them, so the literal
wording has to be carried separately or it is lost before any query is planned.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# A phrase that tells the viewer to do something names the CTA, not the content.
_CTA = {
    "comment", "comments", "dm", "dms", "send", "sending", "sent", "follow", "following",
    "link", "links", "save", "saved", "share", "tag", "tagged", "click", "swipe", "subscribe",
    "join", "download", "get", "grab", "check", "watch", "drop", "reply", "type", "want",
    "wants", "wanna", "need", "needs", "let", "lets", "make", "makes", "made", "use", "using",
}
_FUNCTION = {
    "the", "a", "an", "and", "or", "but", "of", "for", "in", "on", "at", "to", "with", "from",
    "by", "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that",
    "these", "those", "there", "here", "i", "im", "ive", "ill", "id", "me", "my", "mine", "you",
    "your", "yours", "youre", "we", "our", "ours", "us", "he", "she", "they", "them", "their",
    "his", "her", "who", "what", "which", "when", "where", "why", "how", "not", "no", "yes",
    "so", "if", "then", "than", "too", "very", "just", "more", "most", "some", "any", "all",
    "one", "two", "three", "new", "next", "first", "last", "up", "down", "out", "off", "over",
    "do", "does", "did", "can", "will", "would", "should", "could", "have", "has", "had",
    "vs", "ep", "part", "day", "days",
}
_DROP = _CTA | _FUNCTION

_MAX_PHRASES = 8
_MAX_HASHTAGS = 5
_MIN_POSTS = 3


def _segments(caption: str) -> list[str]:
    """Split on punctuation and drop the trailing hashtag block; a phrase never spans them."""
    body = re.split(r"(?m)^\s*#", caption)[0]
    return re.split(r"[.!?,;:—\-\n/|()\[\]\"“”]+", body.lower())


def extract_caption_phrases(
    captions: list[str], *, max_phrases: int = _MAX_PHRASES, min_posts: int = _MIN_POSTS
) -> list[str]:
    """Rank recurring two- and three-word phrases by how many distinct posts contain them.

    Counting posts rather than raw occurrences keeps one caption that repeats a phrase from
    outranking wording the Creator uses across their catalogue.
    """
    counts: Counter[str] = Counter()
    for caption in captions:
        seen: set[str] = set()
        for segment in _segments(caption or ""):
            tokens = re.findall(r"[a-z][a-z'’]{1,}", segment)
            for size in (2, 3):
                for start in range(len(tokens) - size + 1):
                    gram = tokens[start : start + size]
                    if any(token in _DROP or len(token) < 3 for token in gram):
                        continue
                    seen.add(" ".join(gram))
        counts.update(seen)

    ranked = sorted(
        ((phrase, n) for phrase, n in counts.items() if n >= min_posts),
        key=lambda kv: (-kv[1], -len(kv[0]), kv[0]),
    )
    kept: list[str] = []
    for phrase, n in ranked:
        # A bigram adds nothing when a kept trigram already contains it with equal reach.
        if any(phrase in longer and counts[longer] >= n for longer in kept):
            continue
        kept.append(phrase)
        if len(kept) >= max_phrases:
            break
    return kept


def extract_hashtags(
    captions: list[str], *, max_tags: int = _MAX_HASHTAGS, min_posts: int = _MIN_POSTS
) -> list[str]:
    counts: Counter[str] = Counter()
    for caption in captions:
        counts.update({tag.lower() for tag in re.findall(r"#\w{3,}", caption or "")})
    # Ties must break on the tag itself; Counter.most_common would otherwise order them by
    # insertion, which varies with the process hash seed.
    ranked = sorted(((tag, n) for tag, n in counts.items() if n >= min_posts), key=lambda kv: (-kv[1], kv[0]))
    return [tag for tag, _ in ranked[:max_tags]]


def caption_texts(analysis: dict[str, Any]) -> list[str]:
    return [row.get("title") or "" for row in analysis.get("rankings") or []]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
        captions = caption_texts(analysis)
        result = {
            "caption_phrases": extract_caption_phrases(captions),
            "hashtags": extract_hashtags(captions),
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
