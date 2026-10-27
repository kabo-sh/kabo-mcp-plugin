#!/usr/bin/env python3
"""Attach the Creator's own caption phrases from the account review to the TrendResearchRequest.

Caption phrases are the Creator's literal wording, and discovery types them into a search box: a
phrase retyped with a tidied word, a translation or a dropped accent retrieves nothing. SKILL.md
used to tell the model to copy them over verbatim. This script does the copy, so the request carries
exactly what `content_profile.caption_phrases` in the review's creator-profile.v3 holds, in its
order and its original language, and nothing when the review supplied none.

  python3 scripts/attach_caption_phrases.py --creator-profile creator_profile.json \\
    --request trend-research-request.json

Run it before collection starts; the Request is immutable after that. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def phrases_of(profile: dict[str, Any]) -> list[str]:
    content = profile.get("content_profile")
    if not isinstance(content, dict):
        return []
    value = content.get("caption_phrases")
    if not isinstance(value, list):
        return []
    return [phrase for phrase in value if isinstance(phrase, str) and phrase.strip()]


def attach(request: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    phrases = phrases_of(profile)
    creator = request.get("creator_profile")
    creator = dict(creator) if isinstance(creator, dict) else {}
    if phrases:
        creator["observed_caption_phrases"] = phrases
    else:
        # The review supplied none: the field is left out rather than invented or emptied.
        creator.pop("observed_caption_phrases", None)
    updated = dict(request)
    if creator:
        updated["creator_profile"] = creator
    return updated, phrases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--creator-profile", type=Path, required=True, help="the account review's creator-profile.v3")
    parser.add_argument("--request", type=Path, required=True, help="the TrendResearchRequest to update in place")
    args = parser.parse_args()
    try:
        profile = json.loads(args.creator_profile.read_text(encoding="utf-8"))
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(profile, dict) or not isinstance(request, dict):
            raise ValueError("both files must hold a JSON object")
        updated, phrases = attach(request, profile)
        handle, temp = tempfile.mkstemp(prefix=args.request.name + ".", dir=args.request.parent)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp, args.request)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "request": str(args.request), "caption_phrases": phrases}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
