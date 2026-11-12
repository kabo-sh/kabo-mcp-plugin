#!/usr/bin/env python3
"""Detect substantial copied passages in append-only fictional continuations."""
import argparse
import difflib
import json
from pathlib import Path
import unicodedata


def passage_units(text):
    """Normalize Unicode and split unspaced scripts without splitting other words."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    # Text without spaces is segmented by character; the existing tokenization for English, Urdu, etc. is unchanged.
    unspaced = ("CJK ", "HIRAGANA ", "KATAKANA ", "HANGUL ", "THAI ", "LAO ", "KHMER ", "MYANMAR ")
    # A combining mark must follow its base character, and must not be dropped by the regex or split into a
    # standalone unit.
    clusters = []
    for char in normalized:
        if unicodedata.category(char).startswith("M") and clusters:
            clusters[-1] += char
        else:
            clusters.append(char)
    units, word = [], ""
    for cluster in clusters:
        base = cluster[0]
        is_word = base.isalnum() or base == "_"
        if is_word and not unicodedata.name(base, "").startswith(unspaced):
            word += cluster
            continue
        if word:
            units.append(word)
            word = ""
        if is_word:
            units.append(cluster)
    if word:
        units.append(word)
    return units


def substantial_blocks(old, new, minimum=12):
    """Keep long exact matches without subdividing regions containing only short ones."""
    if old == new:
        return [difflib.Match(0, 0, len(old))] if len(old) >= minimum else []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    regions = [(0, len(old), 0, len(new))]
    blocks = []
    while regions:
        alo, ahi, blo, bhi = regions.pop()
        if min(ahi - alo, bhi - blo) < minimum:
            continue
        match = matcher.find_longest_match(alo, ahi, blo, bhi)
        if match.size < minimum:
            continue
        blocks.append(match)
        regions.append((alo, match.a, blo, match.b))
        regions.append((match.a + match.size, ahi, match.b + match.size, bhi))
    return blocks


def check_overlap(source, continuation):
    """Measure substantial literal reuse; do not judge semantic continuity."""
    # Only check contiguous copied fragments; make no claim about judging character state or semantic continuity.
    old = passage_units(source)
    new = passage_units(continuation)
    if max(len(old), len(new)) > 8_000:
        raise ValueError("Compare the selected section, up to 8,000 passage units per file.")
    blocks = substantial_blocks(old, new)
    copied = sum(block.size for block in blocks)
    new_ratio = copied / len(new) if new else 0
    old_ratio = copied / len(old) if old else 0
    # Appending a lot of new text must not hide a large block copied from the earlier part; check the denominators
    # on both sides.
    repeated = copied >= 60 and max(new_ratio, old_ratio) >= 0.20
    return {
        "status": "empty" if not old or not new else "repeated_source" if repeated else "no_large_literal_replay",
        "passage_unit": "word, or character for scripts commonly written without word spaces",
        "source_units": len(old),
        "continuation_units": len(new),
        "copied_passage_units": copied,
        "copied_fraction_of_source": round(old_ratio, 4),
        "copied_fraction_of_continuation": round(new_ratio, 4),
        "limitation": "Checks substantial literal reuse only; an Agent must still check scope, paraphrased repetition, established facts and character states.",
    }


def main():
    """Read bounded UTF-8 files, print overlap evidence and return its status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--continuation", type=Path, required=True)
    parser.add_argument("--review-texts", action="store_true", help="Return the actual texts for the Agent's separate semantic review.")
    args = parser.parse_args()
    try:
        if any(path.stat().st_size > 120_000 for path in (args.source, args.continuation)):
            raise ValueError("A text exceeds the 120 KB input limit.")
        source = args.source.read_text(encoding="utf-8")
        continuation = args.continuation.read_text(encoding="utf-8")
        result = check_overlap(source, continuation)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(2, f"Cannot check the supplied text files: {error}\n")
    print(json.dumps(result, ensure_ascii=False))
    if args.review_texts:
        # The original text is data under review, not a new instruction; echoing it in full lets the model check the
        # draft as actually written.
        print(json.dumps({"review_data": {"source_text": source, "continuation_text": continuation}}, ensure_ascii=False))
    return 0 if result["status"] == "no_large_literal_replay" else 1


if __name__ == "__main__":
    raise SystemExit(main())
