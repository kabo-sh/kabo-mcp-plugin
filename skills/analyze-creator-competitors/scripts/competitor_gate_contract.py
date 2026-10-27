#!/usr/bin/env python3
"""Normalize compact and legacy Competitor semantic-gate contracts."""

from __future__ import annotations

from typing import Any


DISCOVERY = {
    "direct_candidate": "direct_refs",
    "adjacent_candidate": "adjacent_refs",
    "reject": "reject_refs",
}
ELIGIBILITY = {
    "direct": "direct_refs",
    "adjacent": "adjacent_refs",
    "media": "media_refs",
    "excluded": "excluded_refs",
}


def _arrays(gate: dict[str, Any], mapping: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for role, field in mapping.items():
        refs = gate.get(field)
        if not isinstance(refs, list):
            raise ValueError(f"{field} must be an array")
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                raise ValueError(f"{field} must contain non-empty strings")
            if ref in result:
                raise ValueError(f"reference appears more than once: {ref}")
            result[ref] = role
    return result


def discovery_roles(gate: dict[str, Any]) -> dict[str, str]:
    if gate.get("schema_version") == "competitor-discovery-gate.v2":
        return _arrays(gate, DISCOVERY)
    if gate.get("schema_version") != "competitor-discovery-gate.v1":
        raise ValueError("expected competitor-discovery-gate.v1 or competitor-discovery-gate.v2")
    result = {}
    for row in gate.get("authors") or []:
        ref = row.get("handle") if isinstance(row, dict) else None
        role = row.get("relevance") if isinstance(row, dict) else None
        if not isinstance(ref, str) or role not in DISCOVERY or ref in result:
            raise ValueError("invalid or duplicate legacy discovery row")
        result[ref] = role
    return result


def discovery_scores(gate: dict[str, Any]) -> dict[str, dict[str, float]]:
    if gate.get("schema_version") != "competitor-discovery-gate.v3":
        raise ValueError("expected competitor-discovery-gate.v3")
    result: dict[str, dict[str, float]] = {}
    required = {"category_fit", "audience_job_fit", "sustained_focus", "locale_fit"}
    for row in gate.get("items") or []:
        ref = row.get("handle") if isinstance(row, dict) else None
        scores = row.get("semantic_scores") if isinstance(row, dict) else None
        if not isinstance(ref, str) or not ref or ref in result or not isinstance(scores, dict):
            raise ValueError("invalid or duplicate scored discovery row")
        if set(scores) != required:
            raise ValueError(f"{ref}: semantic_scores must contain exactly {sorted(required)}")
        normalized: dict[str, float] = {}
        for name in sorted(required):
            value = scores[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise ValueError(f"{ref}: {name} must be a number from 0 to 100")
            normalized[name] = float(value)
        result[ref] = normalized
    return result


def eligibility_roles(gate: dict[str, Any]) -> dict[str, str]:
    if gate.get("schema_version") == "competitor-eligibility.v2":
        return _arrays(gate, ELIGIBILITY)
    if gate.get("schema_version") != "competitor-eligibility.v1":
        raise ValueError("expected competitor-eligibility.v1 or competitor-eligibility.v2")
    result = {}
    for row in gate.get("candidates") or []:
        ref = row.get("handle") if isinstance(row, dict) else None
        role = row.get("relationship") if isinstance(row, dict) else None
        if not isinstance(ref, str) or role not in ELIGIBILITY or ref in result:
            raise ValueError("invalid or duplicate legacy eligibility row")
        result[ref] = role
    return result
