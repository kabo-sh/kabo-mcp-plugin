#!/usr/bin/env python3
"""Turn the model's numbered account lines into a `tiktok-competitor-discovery-gate.v1`.

The TikTok discovery Gate is the model reading every projected account, naming its relationship and
scoring four fits. Written as JSON, each account retyped its 19-digit `account_ref`, the relationship
and four named fields — about 50 output tokens a line, 1.8k–3.2k per run (17–30 s, 2026-09-19). Here
each account is one line,

    <n> <relationship> <category_fit> <audience_job_fit> <sustained_focus> <locale_fit>

where `n` is the account's 1-based position in the printed table and the relationship is `direct`,
`adjacent`, `media` or `excluded` (or its first letter; `x` for excluded). This script checks that
every account is classified exactly once with integers 0–100 and writes the same Gate JSON
`select_tiktok_accounts.py` always read, with each `account_ref` taken from the projection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

FIELDS = ("category_fit", "audience_job_fit", "sustained_focus", "locale_fit")
RELATIONSHIPS = {"direct": "direct", "d": "direct", "adjacent": "adjacent", "a": "adjacent",
                 "media": "media", "m": "media", "excluded": "excluded", "x": "excluded", "e": "excluded"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def build(projection: dict[str, Any], lines: str) -> dict[str, Any]:
    if projection.get("schema_version") != "tiktok-competitor-discovery-input.v1":
        raise ValueError("input must be tiktok-competitor-discovery-input.v1")
    accounts = projection.get("items")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("the projection has no accounts to classify")
    rows: dict[int, dict[str, Any]] = {}
    for line_no, raw in enumerate(lines.splitlines(), start=1):
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue
        tokens = text.replace(",", " ").replace("\t", " ").split()
        if len(tokens) != 2 + len(FIELDS):
            raise ValueError(f"line {line_no}: expected `n relationship {' '.join(FIELDS)}`, got {text!r}")
        head = tokens[0].rstrip(".")
        if not head.isdigit() or not 1 <= int(head) <= len(accounts):
            raise ValueError(f"line {line_no}: account number {tokens[0]!r} is not between 1 and {len(accounts)}")
        n = int(head)
        if n in rows:
            raise ValueError(f"line {line_no}: account {n} is classified twice")
        relationship = RELATIONSHIPS.get(tokens[1].lower())
        if relationship is None:
            raise ValueError(f"line {line_no}: relationship {tokens[1]!r} is not direct, adjacent, media or excluded")
        row: dict[str, Any] = {"account_ref": str(accounts[n - 1]["account_ref"]), "relationship": relationship}
        for field, token in zip(FIELDS, tokens[2:]):
            if not token.isdigit() or not 0 <= int(token) <= 100:
                raise ValueError(f"line {line_no}: {field} {token!r} is not an integer 0–100")
            row[field] = int(token)
        rows[n] = row
    missing = [n for n in range(1, len(accounts) + 1) if n not in rows]
    if missing:
        preview = ", ".join(map(str, missing[:20])) + (" …" if len(missing) > 20 else "")
        raise ValueError(f"{len(missing)} account(s) not classified: {preview}; classify every numbered line exactly once")
    return {
        "schema_version": "tiktok-competitor-discovery-gate.v1",
        "request_id": str(projection.get("request_id") or ""),
        "items": [rows[n] for n in range(1, len(accounts) + 1)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="tiktok-competitor-discovery-input.json")
    parser.add_argument("--scores", type=Path, required=True, help="numbered account lines")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        gate = build(load(args.input), args.scores.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "accounts": len(gate["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
