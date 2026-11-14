#!/usr/bin/env python3
"""Check a finished draft against the facts the creator supplied, before delivery.

The facts file is written before the draft: the creator's own words (`source_text`), every fact
taken from them (dates and relative days, numbers, names, directions, story events, settings) with
the exact words the draft must keep, and every factual claim the draft makes about real people,
companies, products, history or science together with where it comes from. The check is
mechanical: a kept word that is missing from the draft, a fact that is not in the creator's words,
or a real-world claim with no stated basis is reported for correction. It cannot judge truth.

Usage:
  python3 check_user_facts.py --facts facts.json --draft draft.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

CLAIM_BASES = {"creator", "evidence", "opinion", "question"}


def squeeze(value: str) -> str:
    return " ".join(value.casefold().split())


def numbers(value: str) -> list[str]:
    """Digit groups, so 3, 3.5 and 2,400 survive any language and spacing."""
    return re.findall(r"\d+(?:[.,]\d+)*", value)


def contains_word(text: str, word: str) -> bool:
    """Whole-word match for letters, plain substring for scripts without spaces."""
    word = squeeze(word)
    if not word:
        return False
    if re.fullmatch(r"[\w\s'’-]+", word) and re.search(r"[a-z]", word):
        return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None
    return word in text


def check(facts: dict[str, Any], draft: str) -> list[str]:
    errors: list[str] = []
    source = facts.get("source_text")
    if not isinstance(source, str) or not source.strip():
        return ["source_text must hold the creator's own words, copied exactly"]
    source_s, draft_s = squeeze(source), squeeze(draft)
    if not draft_s:
        return ["the draft is empty"]
    items = facts.get("facts")
    if not isinstance(items, list):
        return ["facts must be a list (use [] only when the creator supplied no facts)"]
    for index, fact in enumerate(items):
        label = f"facts[{index}]"
        if not isinstance(fact, dict):
            errors.append(f"{label} must be an object")
            continue
        span = fact.get("source")
        if not isinstance(span, str) or squeeze(span) not in source_s or not span.strip():
            errors.append(f"{label}.source must be copied exactly from source_text")
            continue
        if fact.get("omitted") is True:
            if not str(fact.get("reason") or "").strip():
                errors.append(f"{label} is omitted without a reason")
            continue
        keep = fact.get("keep")
        rendered = fact.get("rendered")
        if not isinstance(keep, list) or not keep or not all(isinstance(word, str) and word.strip() for word in keep):
            errors.append(f"{label}.keep must list the exact words of this fact the draft has to carry")
            continue
        for word in keep:
            if squeeze(word) not in squeeze(span):
                errors.append(f"{label}.keep {word!r} is not part of its source {span!r}")
            elif rendered is None and not contains_word(draft_s, word):
                errors.append(f"{label}: the draft changed or dropped {word!r} from the creator's {span!r}; "
                              "restore it exactly (for example tomorrow stays tomorrow, up stays up)")
        if rendered is not None:
            # A translated draft carries the fact in its own words: the rendered span must be in the
            # draft and keep every number of the source.
            if not isinstance(rendered, str) or squeeze(rendered) not in draft_s:
                errors.append(f"{label}.rendered must be copied exactly from the draft")
            else:
                missing = [n for n in numbers(span) if n not in numbers(rendered)]
                if missing:
                    errors.append(f"{label}: the draft's rendering {rendered!r} lost the number(s) {missing}")
    claims = facts.get("claims", [])
    if not isinstance(claims, list):
        errors.append("claims must be a list")
        claims = []
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{label} must be an object")
            continue
        text, basis = claim.get("text"), claim.get("basis")
        if not isinstance(text, str) or squeeze(text) not in draft_s or not text.strip():
            errors.append(f"{label}.text must be copied exactly from the draft")
            continue
        if basis not in CLAIM_BASES:
            errors.append(f"{label} ({text!r}) has no basis: use creator, evidence, opinion or question; "
                          "otherwise remove the claim or turn it into a question or a [verify: …] placeholder")
        elif basis == "creator" and (not str(claim.get("support") or "").strip()
                                     or squeeze(str(claim["support"])) not in source_s):
            errors.append(f"{label}: basis creator needs support copied exactly from source_text")
        elif basis == "evidence" and not str(claim.get("ref") or "").strip():
            errors.append(f"{label}: basis evidence needs the evidence ref it comes from")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args()
    try:
        facts = json.loads(args.facts.read_text(encoding="utf-8"))
        draft = args.draft.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "errors": [str(error)]}, ensure_ascii=False))
        return 1
    if not isinstance(facts, dict):
        print(json.dumps({"status": "invalid_input", "errors": ["facts file must hold a JSON object"]}))
        return 1
    errors = check(facts, draft)
    status = "ok" if not errors else "needs_correction"
    result: dict[str, Any] = {"status": status, "errors": errors}
    if errors:
        result["next_action"] = ("Correct the draft (not the facts file) so every creator fact is kept exactly and "
                                 "every real-world claim has a basis, then rerun this check before delivery.")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
