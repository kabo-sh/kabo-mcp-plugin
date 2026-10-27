#!/usr/bin/env python3
"""Reject a YouTube Trend recall that silently lost either required search route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def validate(plan: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    intents = plan.get("intents")
    routes = candidates.get("coverage", {}).get("routes")
    if not isinstance(intents, list) or not isinstance(routes, list):
        raise ValueError("plan intents and candidate coverage.routes must be arrays")

    failed: list[dict[str, str]] = []
    for intent in intents:
        intent_id = intent.get("intent_id") if isinstance(intent, dict) else None
        if not isinstance(intent_id, str):
            raise ValueError("every plan intent must have an intent_id")
        for required_route in ("relevance", "view_count"):
            matches = [
                route
                for route in routes
                if isinstance(route, dict)
                and route.get("intent_id") == intent_id
                and route.get("route") == required_route
            ]
            if len(matches) != 1:
                failed.append({"intent_id": intent_id, "route": required_route, "reason": "missing"})
                continue
            route = matches[0]
            rows = route.get("rows")
            if route.get("status") != "completed" or type(rows) is not int or rows < 1:
                failed.append(
                    {
                        "intent_id": intent_id,
                        "route": required_route,
                        "reason": str(route.get("stop_reason") or route.get("status") or "empty"),
                    }
                )
    if failed:
        raise ValueError(f"required YouTube recall route failed: {failed}")
    return {"valid": True, "intents": len(intents), "required_routes": len(intents) * 2}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate(load(args.plan), load(args.candidates))
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"valid": False, "error": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
