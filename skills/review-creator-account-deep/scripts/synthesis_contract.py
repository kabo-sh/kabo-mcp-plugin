#!/usr/bin/env python3
"""Read and validate the canonical deep synthesis contract without dependencies."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any
import sys

sys.dont_write_bytecode = True
from point_observations import CONTRACT, observations_seed

REFERENCES = Path(__file__).resolve().parent.parent / "references"


class TextTooLong(ValueError):
    """Authored text exceeds a canonical maxLength; every other contract check already passed."""

    def __init__(self, violations: list[dict[str, Any]]) -> None:
        self.violations = violations
        super().__init__("; ".join(
            f"{row['path']} has invalid string length ({row['length']} > {row['max_length']} characters)"
            for row in violations))

    def shortened(self, value: dict[str, Any]) -> dict[str, Any]:
        """A copy with only the over-long fields cut to their limit, for checking every other constraint."""
        result = copy.deepcopy(value)
        for row in self.violations:
            keys = [int(index) if index else name for name, index in re.findall(r"\.([^.\[]+)|\[(\d+)\]", row["path"])]
            parent = result
            for key in keys[:-1]:
                parent = parent[key]
            parent[keys[-1]] = parent[keys[-1]][:row["max_length"]]
        return result


def synthesis_schema() -> dict[str, Any]:
    canonical = json.loads((REFERENCES / "account_deep_synthesis.schema.json").read_text(encoding="utf-8"))

    def expand(value: Any) -> Any:
        if isinstance(value, list):
            return [expand(child) for child in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            ref = value["$ref"]
            prefix = "#/$defs/"
            if set(value) != {"$ref"} or not ref.startswith(prefix) or ref[len(prefix):] not in canonical["$defs"]:
                raise ValueError(f"unsupported canonical reference: {ref}")
            return expand(copy.deepcopy(canonical["$defs"][ref[len(prefix):]]))
        return {key: expand(child) for key, child in value.items() if key != "$defs"}

    return expand(canonical)


def validate_contract(value: Any) -> None:
    supported = {"$schema", "title", "description", "type", "additionalProperties", "required",
                 "properties", "items", "minLength", "maxLength", "minItems", "maxItems", "const", "enum", "oneOf"}

    def check_vocabulary(schema: dict[str, Any]) -> None:
        unknown = set(schema) - supported
        if unknown:
            raise ValueError(f"unsupported canonical constraints: {sorted(unknown)}")
        for child in schema.get("properties", {}).values():
            check_vocabulary(child)
        if isinstance(schema.get("additionalProperties"), dict):
            check_vocabulary(schema["additionalProperties"])
        if "items" in schema:
            check_vocabulary(schema["items"])
        for child in schema.get("oneOf", []):
            check_vocabulary(child)

    def check(item: Any, schema: dict[str, Any], path: str) -> None:
        unknown = set(schema) - supported
        if unknown:
            raise ValueError(f"{path} unsupported canonical constraints: {sorted(unknown)}")
        if "oneOf" in schema:
            matches = 0
            for alternative in schema["oneOf"]:
                recorded = len(too_long)
                try:
                    check(item, alternative, path)
                    matches += 1
                except ValueError:
                    del too_long[recorded:]
            if matches != 1:
                raise ValueError(f"{path} must match exactly one canonical shape")
        expected = schema.get("type")
        valid = {"object": isinstance(item, dict), "array": isinstance(item, list),
                 "string": isinstance(item, str), "number": isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)}
        if expected is not None and not valid.get(expected, False):
            raise ValueError(f"{path} must be {expected}")
        if "const" in schema and (type(item) is not type(schema["const"]) or item != schema["const"]):
            raise ValueError(f"{path} does not match canonical value")
        if "enum" in schema and not any(type(item) is type(candidate) and item == candidate for candidate in schema["enum"]):
            raise ValueError(f"{path} is not a canonical value")
        if expected == "object":
            properties = schema.get("properties", {})
            missing = sorted(set(schema.get("required", [])) - set(item))
            if missing:
                raise ValueError(f"{path} missing required fields: {missing}")
            extra = sorted(set(item) - set(properties))
            if schema.get("additionalProperties") is False and extra:
                raise ValueError(f"{path} contains unsupported fields: {extra}")
            for key, child in item.items():
                if key in properties:
                    check(child, properties[key], f"{path}.{key}")
                elif isinstance(schema.get("additionalProperties"), dict):
                    check(child, schema["additionalProperties"], f"{path}.{key}")
        elif expected == "array":
            if len(item) < schema.get("minItems", 0) or len(item) > schema.get("maxItems", float("inf")):
                raise ValueError(f"{path} has invalid item count")
            for index, child in enumerate(item):
                check(child, schema["items"], f"{path}[{index}]")
        elif expected == "string":
            if len(item) < schema.get("minLength", 0):
                raise ValueError(f"{path} has invalid string length")
            if len(item) > schema.get("maxLength", float("inf")):
                too_long.append({"path": path, "length": len(item), "max_length": schema["maxLength"]})

    too_long: list[dict[str, Any]] = []
    schema = synthesis_schema()
    check_vocabulary(schema)
    check(value, schema, "synthesis")
    presentation = value.get("presentation")
    if value.get("output_language") != "en" and presentation is None:
        raise ValueError("non-English synthesis requires model-written presentation")
    if presentation is not None:
        for category, labels in presentation.items():
            values = labels.values() if isinstance(labels, dict) else [labels]
            if any(not text.strip() for text in values):
                raise ValueError(f"presentation.{category} must contain nonblank display text")
    if too_long:
        raise TextTooLong(too_long)


def synthesis_seed(source: dict[str, Any], language: str, stability: dict[str, Any] | None = None) -> dict[str, Any]:
    """Only bind source identity and structure; blank judgments must still be authored."""
    schema = synthesis_schema()
    analysis_id = source.get("analysis_id")
    if source.get("schema_version") != "deep-synthesis-input.v1" or not isinstance(analysis_id, str) or not analysis_id.strip():
        raise ValueError("deep synthesis input requires its original nonblank analysis_id")
    if language not in schema["properties"]["output_language"]["enum"]:
        raise ValueError("output language is not a canonical value")

    if language != "en":
        reason_keys = schema["properties"]["presentation"]["properties"]["not_watched_reason_labels"]["properties"]
        for row in source.get("unwatched", []):
            if not isinstance(row, dict) or not isinstance(row.get("reason"), str) or row["reason"] not in reason_keys:
                raise ValueError("unwatched reason is not a canonical presentation key")
    if language != "en" and stability is None:
        raise ValueError("non-English seed requires matching catalog stability")
    if stability is not None:
        if not isinstance(stability, dict) or stability.get("schema_version") != "catalog-stability.v1" or stability.get("analysis_id") != analysis_id:
            raise ValueError("catalog stability must match the synthesis input analysis_id")
        if not isinstance(stability.get("rise_fade"), list) or any(
            not isinstance(row, dict) or not isinstance(row.get("format"), str) or not row["format"].strip()
            for row in stability["rise_fade"]
        ):
            raise ValueError("catalog stability requires structured nonblank rise_fade formats")

    def blank(node: dict[str, Any]) -> Any:
        if "const" in node:
            return node["const"]
        if node.get("type") == "object":
            return {key: blank(node["properties"][key]) for key in node.get("required", [])}
        if node.get("type") == "array":
            return []
        if node.get("type") == "string":
            return ""
        raise ValueError("canonical seed field needs an explicit source value")

    seed = {key: (analysis_id if key == "analysis_id" else language if key == "output_language" else blank(schema["properties"][key]))
            for key in schema["required"]}
    marker = source.get("observation_contract")
    if marker is not None and marker != CONTRACT:
        raise ValueError("unsupported observation_contract")
    if marker == CONTRACT:
        seed["video_observations"] = observations_seed(source)
    if language != "en":
        rows = source.get("watched", []) + source.get("unwatched", [])
        formats = {row["format"]: "" for row in rows if row.get("format")}
        formats.update({row["format"]: "" for row in stability["rise_fade"]})
        seed["presentation"] = {
            "format_labels": formats,
            "role_labels": {row["role"]: "" for row in rows if row.get("role")},
            "pin_kind_labels": {"cue": "", "frame": ""},
            "seconds_unit": "",
            "metric_gap_labels": {metric: "" for metric, row in source.get("baseline_availability", {}).items()
                                  if row.get("status") == "not_carried"},
        }
        reasons = {row["reason"]: "" for row in source.get("unwatched", []) if row.get("reason")}
        if reasons:
            seed["presentation"]["not_watched_reason_labels"] = reasons
    return seed
