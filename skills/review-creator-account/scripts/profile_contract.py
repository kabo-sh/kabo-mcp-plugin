#!/usr/bin/env python3
"""Use the canonical CreatorProfile contract for synthesis and early composition checks."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

REFERENCES = Path(__file__).resolve().parent.parent / "references"


def profile_schema() -> dict[str, Any]:
    return json.loads((REFERENCES / "creator_profile.schema.json").read_text(encoding="utf-8"))


def synthesis_schema() -> dict[str, Any]:
    """Expand only local canonical profile references so the model receives the full closed shape."""
    schema = json.loads((REFERENCES / "account_review_synthesis.schema.json").read_text(encoding="utf-8"))
    canonical = profile_schema()

    def expand(value: Any) -> Any:
        if isinstance(value, list):
            return [expand(child) for child in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref", "")
        prefix = "creator_profile.schema.json#/properties/"
        if reference.startswith(prefix):
            name = reference[len(prefix):]
            if set(value) != {"$ref"} or name not in canonical["properties"]:
                raise ValueError(f"invalid canonical profile reference: {reference}")
            return copy.deepcopy(canonical["properties"][name])
        return {key: expand(child) for key, child in value.items()}

    return expand(schema)


def validate_profile(profile: Any, *, synthesis_fields: bool = False) -> None:
    """Validate the dependency-free vocabulary used by the canonical profile; fail on new constraints."""
    supported = {"$schema", "$id", "title", "description", "type", "additionalProperties", "required",
                 "properties", "items", "uniqueItems", "minLength", "maxLength", "minItems", "maxItems",
                 "const", "enum"}

    def check(value: Any, schema: dict[str, Any], location: str) -> None:
        unknown_constraints = set(schema) - supported
        if unknown_constraints:
            raise ValueError(f"{location} unsupported canonical constraints: {sorted(unknown_constraints)}")
        expected = schema.get("type")
        types = {"object": dict, "array": list, "string": str}
        if expected is not None and (expected not in types or not isinstance(value, types[expected])):
            raise ValueError(f"{location} must be {expected}")
        if "const" in schema and value != schema["const"]:
            raise ValueError(f"{location} does not match canonical value")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{location} is not a canonical value")
        if expected is None:
            if set(schema) - {"description", "title", "const", "enum"}:
                raise ValueError(f"{location} requires a supported canonical type")
            return
        if expected == "object":
            properties = schema.get("properties", {})
            unknown = sorted(set(value) - set(properties))
            if schema.get("additionalProperties") is False and unknown:
                raise ValueError(f"{location} contains unsupported fields: {unknown}")
            missing = sorted(set(schema.get("required", [])) - set(value))
            if missing:
                raise ValueError(f"{location} missing required fields: {missing}")
            for key, child in value.items():
                if key in properties:
                    check(child, properties[key], f"{location}.{key}")
        elif expected == "array":
            if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
                raise ValueError(f"{location} has invalid item count")
            if schema.get("uniqueItems") and any(child in value[:index] for index, child in enumerate(value)):
                raise ValueError(f"{location} contains duplicate items")
            for index, child in enumerate(value):
                check(child, schema["items"], f"{location}[{index}]")
        elif len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise ValueError(f"{location} has invalid string length")

    schema = synthesis_schema()["properties"]["profile"] if synthesis_fields else profile_schema()
    check(profile, schema, "profile")


if __name__ == "__main__":
    print(json.dumps(synthesis_schema(), ensure_ascii=False, indent=2))
