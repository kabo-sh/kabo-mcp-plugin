#!/usr/bin/env python3
"""Turn the model's numbered score lines into a `trend-relevance-gate.v3`.

The Gate is the model reading every projected item and scoring it. Writing that judgment as one
JSON object per item (~110 characters each, 60–160 items) is most of the output a trend run
generates, and observed runs replaced the reading with a keyword script to avoid typing it. The
judgment is unchanged here; only its transport is shorter: one line per projected item,

    <n> <topic_relevance> <locale_fit> [<creator_transferability> [<signature_content>]]

where `n` is the item's 1-based position in the printed projection table. This script checks that
every item is scored exactly once, that each score is an integer 0–100, and that
`creator_transferability` is present exactly when the Gate input carries an anchor, then writes the
same Gate JSON the downstream builders already read.

Gate 输入带创作者的主打内容（`subject.signature_content`，编号 1..k）时，每行多一列：
这条候选复现的是第几个主打内容，都不像填 0。Gate 行据此记下该主打内容在 Request 里的 id
（`signature_content_id`，填 0 时为 null）。不带主打内容时，行格式与 Gate JSON 都和原来一样。
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


class ScoreInputError(ValueError):
    """Only a model-authored score line is invalid; source/data faults are not this class."""


class FrozenGateError(ValueError):
    """A frozen judgment changed; always fatal, never an authoring correction."""


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def subject_of(gate_input: dict[str, Any]) -> dict[str, Any]:
    return gate_input.get("subject") if isinstance(gate_input.get("subject"), dict) else {}


def signature_ids(gate_input: dict[str, Any]) -> list[str]:
    """Request ids of the signature content in Gate-number order (number = position + 1)."""
    entries = subject_of(gate_input).get("signature_content")
    if not isinstance(entries, list):
        return []
    return [str(entry["id"]) for entry in entries if isinstance(entry, dict) and entry.get("id")]


def has_anchor(gate_input: dict[str, Any]) -> bool:
    # 主打内容是创作者自己作品的逐类描述，和 handle 一样能说明「这个创作者是谁」，
    # 所以带了主打内容就必须打 creator_transferability。
    subject = subject_of(gate_input)
    return bool(subject.get("anchor_handle") or subject.get("anchor_mechanisms") or signature_ids(gate_input))


def score(token: str, line_no: int) -> int:
    try:
        value = int(token)
    except ValueError as error:
        raise ScoreInputError(f"line {line_no}: score {token!r} is not an integer") from error
    if not 0 <= value <= 100:
        raise ScoreInputError(f"line {line_no}: score {value} is outside 0–100")
    return value


def signature_number(token: str, line_no: int, count: int) -> int:
    try:
        value = int(token)
    except ValueError as error:
        raise ScoreInputError(f"line {line_no}: signature_content {token!r} is not an integer") from error
    if not 0 <= value <= count:
        raise ScoreInputError(f"line {line_no}: signature_content {value} is outside 0–{count} "
                              f"(0 = none of the {count} listed)")
    return value


def build(gate_input: dict[str, Any], lines: str) -> dict[str, Any]:
    if gate_input.get("schema_version") != "trend-relevance-gate-input.v1":
        raise ValueError("input must be trend-relevance-gate-input.v1")
    items = gate_input.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("gate input has no items to score")
    anchored = has_anchor(gate_input)
    ids = signature_ids(gate_input)
    expected = (3 if anchored else 2) + (1 if ids else 0)
    scored: dict[int, dict[str, int]] = {}
    chosen: dict[int, str | None] = {}
    for line_no, raw in enumerate(lines.splitlines(), start=1):
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue
        tokens = text.replace(",", " ").replace("\t", " ").split()
        if len(tokens) != 1 + expected:
            want = ("n topic locale transfer signature_content" if ids else
                    "n topic locale transfer" if anchored else "n topic locale (no transfer: the input has no anchor)")
            raise ScoreInputError(f"line {line_no}: expected `{want}`, got {text!r}")
        n = int(tokens[0].rstrip('.')) if tokens[0].rstrip('.').isdigit() else None
        if n is None or not 1 <= n <= len(items):
            raise ScoreInputError(f"line {line_no}: item number {tokens[0]!r} is not between 1 and {len(items)}")
        if n in scored:
            raise ScoreInputError(f"line {line_no}: item {n} is scored twice")
        scores = {"topic_relevance": score(tokens[1], line_no), "locale_fit": score(tokens[2], line_no)}
        if anchored:
            scores["creator_transferability"] = score(tokens[3], line_no)
        if ids:
            number = signature_number(tokens[4], line_no, len(ids))
            chosen[n] = ids[number - 1] if number else None
        scored[n] = scores
    missing = [n for n in range(1, len(items) + 1) if n not in scored]
    if missing:
        preview = ", ".join(map(str, missing[:20])) + (" …" if len(missing) > 20 else "")
        raise ScoreInputError(f"{len(missing)} item(s) not scored: {preview}; score every numbered line exactly once")
    return {
        "schema_version": "trend-relevance-gate.v3",
        "request_id": str(gate_input.get("request_id") or ""),
        "platform": gate_input.get("platform"),
        "items": [
            {"content_key": str(item["content_key"]), "semantic_scores": scored[index],
             **({"signature_content_id": chosen[index]} if ids else {})}
            for index, item in enumerate(items, start=1)
        ],
    }


def assert_open_run() -> None:
    manifest = Path("run-manifest.json")
    if manifest.exists() and load(manifest).get("status") != "running":
        raise ValueError("this run is terminal or has no valid running manifest; correction cannot reopen it")


def stage_contract(gate_input: dict[str, Any], scores_file: str, stage: str, driver: str) -> dict[str, Any]:
    from project_relevance_gate_input import validate_projection
    assert_open_run()
    validate_projection(gate_input)
    if not gate_input["items"]:
        raise ValueError("gate input has no items to score")
    columns = ["n", "topic_relevance", "locale_fit"]
    if has_anchor(gate_input):
        columns.append("creator_transferability")
    if signature_ids(gate_input):
        columns.append("signature_content")
    return {"gate_scoring": {"scores_file": scores_file, "columns": columns, "header": False,
                             "items": len(gate_input["items"])},
            "next_stage": {"script": "scripts/drive.py", "arguments": [stage],
                           "run_id": Path.cwd().name,
                           "command": f"cd {shlex.quote(str(Path.cwd()))} && python3 {shlex.quote(str(Path(driver).resolve()))} {stage}"}}


def preflight_scores(specs: list[tuple[str, str, str]], *, frozen: bool, frozen_message: str) -> list[str]:
    """No writes/fetches: validate all sources, then frozen consistency, then authored lines.

    Frozen or outstanding data work never becomes an authoring correction. Missing files,
    projection/schema errors and unexpected exceptions propagate to the driver's fatal path.
    """
    from project_relevance_gate_input import validate_projection
    assert_open_run()
    inputs = []
    for input_file, scores_file, gate_file in specs:
        projected = load(Path(input_file))
        validate_projection(projected)
        if not projected["items"]:
            raise ValueError("gate input has no items to score")
        lines = Path(scores_file).read_text(encoding="utf-8")
        # Load every frozen artifact before entering any authored-error recovery path.
        previous = load(Path(gate_file)) if frozen else None
        inputs.append((projected, lines, previous, scores_file))
    if frozen:
        for projected, lines, previous, _ in inputs:
            try:
                current = build(projected, lines)
            except ScoreInputError as error:
                raise FrozenGateError(f"{frozen_message}: {error}") from error
            if current != previous:
                raise FrozenGateError(frozen_message)
        return []
    errors = []
    for projected, lines, _, scores_file in inputs:
        try:
            build(projected, lines)
        except ScoreInputError as error:
            errors.append(f"{scores_file}: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="trend-relevance-gate-input.json")
    parser.add_argument("--scores", type=Path, required=True, help="numbered score lines")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        gate = build(load(args.input), args.scores.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "items": len(gate["items"]), "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        label = "ValueError" if isinstance(error, ScoreInputError) else type(error).__name__
        print(json.dumps({"status": "failed", "error": f"{label}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
