#!/usr/bin/env python3
"""Bind two persisted Instagram candidate sets to their lanes by the window each lane asked for.

Both lanes return the same schema, so `persist_envelope.py` can only tell them apart by the order the
responses arrived. That forced the two collector calls to run one after the other (each ~50 s,
measured 2026-09-17). Each lane's generated input names its window (`last-month`, `last-year`) and
the collector echoes that window on its result, so the binding does not need order: call both lanes
at once, persist the two results under neutral names, and let this script name them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def bind(relevance_input: dict[str, Any], reach_input: dict[str, Any], sets: list[tuple[Path, dict[str, Any]]]) -> dict[str, Path]:
    wanted = {"relevance": relevance_input.get("window"), "reach": reach_input.get("window")}
    if not all(isinstance(value, str) and value for value in wanted.values()):
        raise ValueError("both lane inputs must name a window")
    if wanted["relevance"] == wanted["reach"]:
        raise ValueError("the two lanes ask for the same window, so their results cannot be told apart")
    if len(sets) != 2:
        raise ValueError("pass exactly the two persisted candidate sets")
    bound: dict[str, Path] = {}
    for path, candidate_set in sets:
        if candidate_set.get("schema_version") != "trend-candidate-set.v1":
            raise ValueError(f"{path}: not a trend-candidate-set.v1")
        lane = next((name for name, window in wanted.items() if candidate_set.get("window") == window), None)
        if lane is None:
            raise ValueError(f"{path}: window {candidate_set.get('window')!r} matches neither lane {wanted}")
        if lane in bound:
            raise ValueError(f"both persisted sets carry the {lane} lane's window {wanted[lane]!r}")
        bound[lane] = path
    return bound


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--relevance-input", type=Path, required=True)
    parser.add_argument("--reach-input", type=Path, required=True)
    parser.add_argument("--set", type=Path, action="append", required=True, help="one persisted candidate set; pass twice")
    parser.add_argument("--relevance-output", type=Path, required=True)
    parser.add_argument("--reach-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        bound = bind(load(args.relevance_input), load(args.reach_input), [(path, load(path)) for path in args.set])
        for lane, target in (("relevance", args.relevance_output), ("reach", args.reach_output)):
            if bound[lane].resolve() != target.resolve():
                shutil.copyfile(bound[lane], target)
        print(json.dumps({"status": "ok", "relevance": str(bound["relevance"]), "reach": str(bound["reach"])}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
