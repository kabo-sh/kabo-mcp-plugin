#!/usr/bin/env python3
"""Dependency-free validation of the packaged provided-Snapshot input contract."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from analyze_public_snapshot import normalized_items, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_KEYS = {
    "$schema", "$id", "title", "description", "type", "required", "properties",
    "additionalProperties", "const", "enum", "minLength", "format", "minItems",
    "uniqueItems", "items", "minimum",
}


def timestamp(value: str) -> datetime:
    """Require a timezone-bearing RFC3339 timestamp and compare its UTC instant."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        raise ValueError("timestamps must include RFC3339 date, time and timezone")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def schema_check(value: Any, schema: dict[str, Any], at: str) -> None:
    """Evaluate exactly the keywords used by the two bundled input schemas."""
    unsupported = set(schema) - SCHEMA_KEYS
    if unsupported:
        raise ValueError(f"{at}: unsupported schema keywords {sorted(unsupported)}")
    kinds = schema.get("type")
    if kinds:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        checks = {
            "object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "null": value is None,
            "boolean": type(value) is bool, "integer": type(value) is int,
            "number": type(value) in (int, float) and math.isfinite(value),
        }
        if any(kind not in checks for kind in kinds) or not any(checks[kind] for kind in kinds):
            raise ValueError(f"{at}: expected {kinds}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{at}: wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{at}: value outside enum")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(f"{at}: missing {sorted(missing)}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, member in value.items():
            if key in properties:
                schema_check(member, properties[key], f"{at}.{key}")
            elif additional is False:
                raise ValueError(f"{at}: unexpected field {key}")
            elif isinstance(additional, dict):
                schema_check(member, additional, f"{at}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{at}: too few items")
        if schema.get("uniqueItems") and len({json.dumps(row, sort_keys=True) for row in value}) != len(value):
            raise ValueError(f"{at}: duplicate items")
        if "items" in schema:
            for index, member in enumerate(value):
                schema_check(member, schema["items"], f"{at}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{at}: string too short")
        if "format" in schema:
            if schema["format"] != "date-time":
                raise ValueError(f"{at}: unsupported schema format")
            timestamp(value)
    if "minimum" in schema and type(value) in (int, float) and value < schema["minimum"]:
        raise ValueError(f"{at}: below minimum")


def skill_name() -> str | None:
    """This Skill's own name, from the `name` field of its SKILL.md frontmatter."""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    found = re.search(r"^name:\s*[\"']?([a-z0-9-]+)", front, re.MULTILINE)
    return found.group(1) if found else None


def validate(request: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Reject incompatible supplied evidence before any analysis or collection."""
    for value, name in ((request, "trend-research-request"), (snapshot, "public-content-snapshot")):
        schema = json.loads((ROOT / "references" / f"{name}.schema.json").read_text(encoding="utf-8"))
        schema_check(value, schema, name)
    # 这份副本只属于 YouTube 趋势 Skill；名字对不上（被改名或拷错）时拒绝，而不是猜平台。
    platform = "youtube" if skill_name() == "research-youtube-trends" else None
    if not platform or snapshot["platform"] != platform or request["platforms"] != [platform]:
        raise ValueError("Request and Snapshot must both match this skill's platform")
    if request["mode"] == "momentum":
        raise ValueError("one supplied Snapshot cannot establish momentum")
    scope = snapshot["scope"]
    if timestamp(request["window"]["since"]) != timestamp(scope["window"]["start"]) or timestamp(
        request["window"]["until"]
    ) != timestamp(scope["window"]["end"]):
        raise ValueError("Request window must match the supplied Snapshot")
    for key in ("region", "language"):
        if request["locale"][key] != scope.get(key):
            raise ValueError(f"Request locale.{key} must match the supplied Snapshot")
    _, start, end, creators = validate_snapshot(snapshot)
    items, _ = normalized_items(snapshot, start, end, creators)
    formats = {row["format"] for row in items}
    if any(not value.strip() for value in request["formats"]):
        raise ValueError("Request formats cannot contain blank values")
    # Observed rows prove format membership, not exhaustive coverage. A Request
    # may include a format with no returned rows; do not narrow that scope.
    # But an observed format outside the Request would be analyzed out of scope.
    aliases = {"reel": "instagram_reel", "feed": "instagram_feed"} if platform == "instagram" else {}
    known_formats = {aliases.get(value, value) for value in formats if value != "unknown"}
    requested_formats = {aliases.get(value, value) for value in request["formats"]}
    # Canonical aliases are compared only; bytes are never rewritten. Unknown
    # evidence remains unknown and the Analyzer excludes it from format cohorts.
    if not known_formats.issubset(requested_formats):
        raise ValueError("Request formats must include the supplied Snapshot formats")


def main() -> int:
    """Validate read-only inputs and emit one receipt without creating artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        validate(request, snapshot)
        print(json.dumps({"status": "ok", "platform": snapshot["platform"], "items": len(snapshot["items"])}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
