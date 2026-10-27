#!/usr/bin/env python3
"""Deterministic discovery and post-eligibility account selection for Competitor research."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from competitor_gate_contract import discovery_roles, discovery_scores, eligibility_roles
from persist_connector_json import load_json_object


def load(path: Path) -> dict[str, Any]:
    value = load_json_object(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def resolve_discover_request_id(
    gate: dict[str, Any],
    request: dict[str, Any] | None,
    cli_request_id: str | None,
) -> str:
    """Bind discover to the frozen request/gate id.

    Agents type `--request-id` by hand and miss. When the request file and
    gate already agree, that frozen id wins. The CLI value is only a fallback
    when both artifacts omit it.
    """
    frozen: list[str] = []
    if request is not None:
        request_id = request.get("request_id")
        if isinstance(request_id, str) and request_id.strip():
            frozen.append(request_id.strip())
    gate_id = gate.get("request_id")
    if isinstance(gate_id, str) and gate_id.strip():
        frozen.append(gate_id.strip())
    unique = list(dict.fromkeys(frozen))
    if len(unique) > 1:
        raise ValueError("gate request_id does not match request file request_id")
    if unique:
        return unique[0]
    if isinstance(cli_request_id, str) and cli_request_id.strip():
        return cli_request_id.strip()
    raise ValueError(
        "pass --request competitor-research-request.json; "
        "request_id is read from that file or the gate"
    )


def canonical_handle(value: str) -> str:
    stripped = value.strip().removeprefix("@")
    # YouTube channel IDs are case-sensitive; Instagram-style handles are not.
    if re.fullmatch(r"UC[\w-]{22}", stripped):
        return stripped
    return stripped.casefold()


def candidate_author(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Instagram author or YouTube channel for account selection."""
    author = item.get("author") if isinstance(item.get("author"), dict) else None
    if author is not None:
        return author
    channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
    channel_id = channel.get("id")
    if not isinstance(channel_id, str) or not channel_id.strip():
        return {}
    normalized = {"id": channel_id, "handle": channel_id}
    if isinstance(channel.get("title"), str) and channel["title"].strip():
        normalized["full_name"] = channel["title"]
    return normalized


def has_visible_content(item: dict[str, Any]) -> bool:
    """Return whether discovery supplied any semantic content for an item."""
    return any(
        isinstance(item.get(key), str) and bool(item[key].strip())
        for key in ("title", "caption", "description")
    )


def visible_content(items: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in items:
        for key in ("title", "caption", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip() and value.strip() not in values:
                values.append(value.strip())
    return values


def normalized_route(value: Any) -> str | None:
    return {
        "search": "search",
        "relevance": "search",
        "popular": "popular",
        "view_count": "popular",
        "profiles": "profiles",
    }.get(value)


def timestamp(value: Any) -> float:
    if not isinstance(value, str) or not value.strip():
        return float("-inf")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def semantic_total(scores: dict[str, float]) -> float:
    return (
        scores["category_fit"] * 0.4
        + scores["audience_job_fit"] * 0.3
        + scores["sustained_focus"] * 0.2
        + scores["locale_fit"] * 0.1
    )


def scored_candidate_tier(scores: dict[str, float], total: float) -> int | None:
    """Keep product matches ahead of workflow-only fallback candidates."""
    if (
        scores["category_fit"] >= 40
        and scores["audience_job_fit"] >= 35
        and total >= 50
    ):
        return 0
    if (
        scores["category_fit"] >= 10
        and scores["audience_job_fit"] >= 70
        and scores["sustained_focus"] >= 50
        and total >= 40
    ):
        return 1
    return None


def tie_percentile(values: list[float], target: float) -> float:
    if not values:
        return 0.0
    below = sum(value < target for value in values)
    equal = sum(value == target for value in values)
    return round((below + 0.5 * equal) / len(values) * 100, 6)


def named_lane_prefers_profiles(request: dict[str, Any] | None) -> bool:
    """Fill the six seats from profile-search first when the request already named a market.

    Search/Popular reward accounts that posted more generic category content.
    Complementary profile-search is the local-language product recall lane.
    Measured 2026-09-14: local-market product accounts entered the pool via
    profile-search but lost the six seats to English Search/Popular agencies.
    Caption phrases do not flip this: profile-search on a form phrase often
    returns accounts named after the phrase, not same-form creators.
    """
    if not isinstance(request, dict):
        return False
    subject = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    # Products only. Profile search matches names and bios, which is how a local seller is found;
    # for a creator it finds people who describe themselves the same way, with no sign they still
    # post. On one creator case (2026-09-18/19): every roster was six profile-only accounts, and in
    # four of nine runs most of them had nothing in the window, leaving the Report without patterns.
    if subject.get("kind") != "product":
        return False
    locale = request.get("locale") if isinstance(request.get("locale"), dict) else {}
    market = subject.get("market") or locale.get("region")
    return isinstance(market, str) and bool(market.strip())


def discover(
    candidates: dict[str, Any],
    gate: dict[str, Any],
    request_id: str,
    subject_handles: set[str],
    target: int = 6,
    reserves: int = 2,
    strategy: str = "auto",
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if candidates.get("schema_version") not in {"trend-candidate-set.v1", "youtube-trend-candidate-set.v1"}:
        raise ValueError("expected trend-candidate-set.v1 or youtube-trend-candidate-set.v1")
    if gate.get("schema_version") == "competitor-discovery-gate-input.v1":
        raise ValueError(
            "this file is competitor-discovery-gate-input; pass --gate "
            "competitor-discovery-gate.json (the scored gate). "
            "Do not pass --gate-input"
        )
    if target < 1 or target > 6 or reserves < 0 or reserves > 2:
        raise ValueError("target must be 1..6 and reserves 0..2")
    if strategy not in {"auto", "legacy-v1", "comparable-v2", "evidence-score-v3"}:
        raise ValueError("unsupported discovery selection strategy")
    if gate.get("request_id") != request_id:
        raise ValueError("gate request_id does not match selection request_id")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates.get("items") or []:
        author = candidate_author(item)
        handle = author.get("handle")
        if isinstance(handle, str) and handle.strip():
            grouped[canonical_handle(handle)].append(item)
    if not grouped:
        raise ValueError("candidate set contains no resolvable author handles")

    scored = gate.get("schema_version") == "competitor-discovery-gate.v3"
    if strategy == "auto":
        strategy = "evidence-score-v3" if scored else "comparable-v2"
    if scored != (strategy == "evidence-score-v3"):
        raise ValueError("evidence-score-v3 requires competitor-discovery-gate.v3; legacy strategies require v1/v2")
    score_by_handle: dict[str, dict[str, float]] = {}
    if scored:
        for ref, values in discovery_scores(gate).items():
            handle = canonical_handle(ref)
            if handle in score_by_handle:
                raise ValueError(f"discovery gate contains duplicate canonical handle: {handle}")
            score_by_handle[handle] = values
    role_by_handle: dict[str, str] = {}
    if not scored:
        for ref, role in discovery_roles(gate).items():
            handle = canonical_handle(ref)
            if handle in role_by_handle:
                raise ValueError(f"discovery gate contains duplicate canonical handle: {handle}")
            role_by_handle[handle] = role
    gate_handles = set(score_by_handle or role_by_handle)
    if named_lane_prefers_profiles(request):
        profile_handles = {
            handle
            for handle, items in grouped.items()
            if any(
                isinstance(source, dict) and normalized_route(source.get("route")) == "profiles"
                for item in items
                for source in (item.get("sources") or [])
            )
        }
        ungated = sorted(profile_handles - gate_handles)
        if ungated:
            raise ValueError(
                "profile-search authors must be scored in the discovery gate before selection; "
                f"ungated={ungated}. Merge complementary search_profiles into the candidate set, "
                "then score every author."
            )
    missing_gate_handles = sorted(set(grouped) - gate_handles)
    for handle in missing_gate_handles:
        role_by_handle[handle] = "reject"

    rows = []
    subjects = {canonical_handle(value) for value in subject_handles}
    for handle, items in grouped.items():
        sources = [source for item in items for source in (item.get("sources") or []) if isinstance(source, dict)]
        intents = {source.get("intent_id") for source in sources if isinstance(source.get("intent_id"), str)}
        routes = {
            normalized
            for source in sources
            if (normalized := normalized_route(source.get("route"))) is not None
        }
        ranks = [source["rank"] for source in sources if isinstance(source.get("rank"), int)]
        published = [item.get("published_at") for item in items if isinstance(item.get("published_at"), str)]
        plays = []
        for item in items:
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            play_count = metrics.get("play_count", metrics.get("views"))
            if isinstance(play_count, (int, float)) and not isinstance(play_count, bool):
                plays.append(play_count)
        semantic_scores = score_by_handle.get(handle)
        semantic_score = semantic_total(semantic_scores) if semantic_scores else None
        gate_role = role_by_handle.get(handle)
        missing_visible_content = not any(has_visible_content(item) for item in items)
        if missing_visible_content:
            gate_role = "reject"
        elif semantic_scores is not None:
            semantic_tier = scored_candidate_tier(semantic_scores, semantic_score)
            gate_role = (
                "scored_candidate"
                if semantic_tier is not None
                else "reject"
            )
        author: dict[str, Any] = {}
        for item in items:
            item_author = candidate_author(item)
            if not item_author:
                continue
            for key, value in item_author.items():
                if key not in author and value is not None:
                    author[key] = value
        is_subject = handle in subjects
        rejected = gate_role == "reject"
        if is_subject:
            decision = "excluded_subject"
            reason = "The handle belongs to the research subject."
        elif missing_visible_content:
            decision = "rejected_missing_visible_content"
            reason = "No visible title, caption or description was available for semantic competitor classification."
        elif rejected:
            decision = "rejected_by_discovery_gate"
            reason = "Classified by the semantic discovery gate."
        else:
            decision = "not_selected_capacity"
            reason = "Classified by the semantic discovery gate."
        rows.append({
            "handle": handle,
            "relevance": "subject" if is_subject else gate_role,
            **({"semantic_scores": semantic_scores, "semantic_score": round(semantic_score, 6)} if semantic_scores is not None and semantic_score is not None else {}),
            "content_refs": sorted({str(item["content_key"]) for item in items}),
            "visible_content": visible_content(items),
            "matched_intents": len(intents),
            "source_routes": sorted(routes),
            "content_count": len(items),
            "author_summary": {
                key: author[key]
                for key in ("id", "handle", "full_name", "is_verified", "follower_count", "post_count", "is_private")
                if key in author
            },
            "newest_published_at": max(published, key=timestamp) if published else None,
            "max_play_count": max(plays) if plays else None,
            "best_source_rank": min(ranks) if ranks else None,
            "discovery_rank": None,
            "decision": decision,
            "reason": reason,
        })

    if strategy == "evidence-score-v3":
        eligible_rows = [row for row in rows if row["decision"] == "not_selected_capacity"]
        intent_values = [float(row["matched_intents"]) for row in eligible_rows]
        route_values = [float(len(row["source_routes"])) for row in eligible_rows]
        recurrence_values = [float(row["content_count"]) for row in eligible_rows]
        rank_values = [float(-(row["best_source_rank"] or 10**9)) for row in eligible_rows]
        semantic_values = [float(row["semantic_score"]) for row in eligible_rows]
        for row in eligible_rows:
            retrieval_score = (
                tie_percentile(intent_values, float(row["matched_intents"])) * 0.4
                + tie_percentile(route_values, float(len(row["source_routes"]))) * 0.25
                + tie_percentile(recurrence_values, float(row["content_count"])) * 0.2
                + tie_percentile(rank_values, float(-(row["best_source_rank"] or 10**9))) * 0.15
            )
            row["retrieval_score"] = round(retrieval_score, 6)
            # Both terms need one scale before the 75/25 weighting. Gate semantic scores sit in a narrow
            # 78-95 band while retrieval percentiles span 0-100, so adding raw values would let the 25%
            # retrieval term dominate and bury strong single-intent accounts under weak multi-route ones.
            row["selection_score"] = round(
                tie_percentile(semantic_values, float(row["semantic_score"])) * 0.75
                + retrieval_score * 0.25,
                6,
            )
    prefer_profiles = named_lane_prefers_profiles(request)

    def selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
        if strategy == "evidence-score-v3":
            tier = scored_candidate_tier(row["semantic_scores"], row["semantic_score"])
            if tier is None:
                raise ValueError(f"selected scored candidate has no semantic tier: {row['handle']}")
            if prefer_profiles:
                lane = 0 if "profiles" in row["source_routes"] else 1
                return (tier, lane, -row["selection_score"], row["handle"])
            return (tier, -row["selection_score"], row["handle"])
        shared = (
            {"direct_candidate": 0, "adjacent_candidate": 1}[row["relevance"]],
            -row["matched_intents"],
        )
        if strategy == "legacy-v1":
            return shared + (
                -row["content_count"],
                -(row["max_play_count"] if row["max_play_count"] is not None else -1),
                -timestamp(row["newest_published_at"]),
                row["best_source_rank"] if row["best_source_rank"] is not None else 10**9,
                row["handle"],
            )
        return shared + (
            -len(row["source_routes"]),
            -row["content_count"],
            row["best_source_rank"] if row["best_source_rank"] is not None else 10**9,
            row["handle"],
        )

    ranked = sorted(
        (row for row in rows if row["decision"] == "not_selected_capacity"),
        key=selection_key,
    )
    for index, row in enumerate(ranked, 1):
        row["discovery_rank"] = index
        if index <= target:
            row["decision"] = "selected_for_profile"
            row["reason"] = "Passed the semantic discovery gate and ranked within the six-account profile budget."
        elif index <= target + reserves:
            row["decision"] = "reserve"
            row["reason"] = "Passed the semantic discovery gate and is held as a reserve if profile eligibility leaves fewer than three usable competitors."
        else:
            row["decision"] = "not_selected_capacity"
            row["reason"] = "Passed the semantic discovery gate but ranked below the six-account profile target and two-account reserve cap."
    return {
        "schema_version": "competitor-discovery-selection.v1",
        "request_id": request_id,
        "selection_strategy": strategy,
        "selected_handles": [row["handle"] for row in ranked[:target]],
        "reserve_handles": [row["handle"] for row in ranked[target:target + reserves]],
        "authors": sorted(rows, key=lambda row: (row["discovery_rank"] is None, row["discovery_rank"] or 10**9, row["handle"])),
    }


def finalize(
    discovery: dict[str, Any],
    eligibility: dict[str, Any],
    limit: int = 6,
    media_cap: int = 1,
    eligibility_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if discovery.get("schema_version") != "competitor-discovery-selection.v1":
        raise ValueError("expected competitor-discovery-selection.v1")
    ranks = {
        canonical_handle(row["handle"]): row["discovery_rank"]
        for row in discovery.get("authors") or []
        if isinstance(row.get("discovery_rank"), int)
    }
    candidates = [
        {"handle": ref, "relationship": role, "eligible": role != "excluded"}
        for ref, role in eligibility_roles(eligibility).items()
    ]
    candidate_handles = {canonical_handle(row["handle"]) for row in candidates}
    if eligibility_input is not None:
        if eligibility_input.get("schema_version") != "competitor-eligibility-input.v1":
            raise ValueError("eligibility input must be competitor-eligibility-input.v1")
        subject = eligibility_input.get("subject") if isinstance(eligibility_input.get("subject"), dict) else {}
        if subject.get("kind") not in {"product", "creator"}:
            raise ValueError("eligibility input must declare subject.kind as product or creator")
        input_handles = {
            canonical_handle(str(row.get("handle") or ""))
            for row in eligibility_input.get("profiles") or []
            if isinstance(row, dict) and row.get("handle")
        }
        if candidate_handles != input_handles:
            missing_input = sorted(input_handles - candidate_handles)
            unknown_input = sorted(candidate_handles - input_handles)
            raise ValueError(
                "eligibility must classify every profiled account exactly once; "
                f"missing={missing_input}, unknown={unknown_input}"
            )
    selected_handles = {canonical_handle(value) for value in discovery.get("selected_handles") or []}
    reserve_handles = {canonical_handle(value) for value in discovery.get("reserve_handles") or []}
    pinned = set(discovery.get("provided_handles") or [])
    missing = sorted(selected_handles - candidate_handles - pinned)
    replacements = sorted(candidate_handles & reserve_handles)
    unknown = sorted(candidate_handles - selected_handles - reserve_handles)
    if len(replacements) < len(missing) or len(candidate_handles | pinned) < len(selected_handles):
        raise ValueError(
            "eligibility must cover the selected profile budget with frozen reserves; "
            f"missing={missing}, replacements={replacements}"
        )
    if unknown:
        raise ValueError(f"eligibility contains authors outside discovery selection: {unknown}")
    # Roles come from the evidence Gate only: on a product question the platform the product runs on
    # is classified `media` there, so the one-account media cap bounds it without a handle list.
    eligible = [
        row for row in candidates
        if row.get("eligible") is True
        and row.get("relationship") in {"direct", "adjacent", "media"}
    ]
    eligible.sort(key=lambda row: (canonical_handle(row["handle"]) not in pinned, {"direct": 0, "adjacent": 1, "media": 2}[row["relationship"]], ranks[canonical_handle(row["handle"])]))
    limit = max(limit, len(pinned))
    included = []
    media_used = 0
    for row in eligible:
        if len(included) >= limit:
            break
        if row["relationship"] == "media" and canonical_handle(row["handle"]) not in pinned:
            if media_used >= media_cap:
                continue
            media_used += 1
        included.append(row)
    included_handles = {canonical_handle(row["handle"]) for row in included}
    audit = []
    for row in sorted(candidates, key=lambda item: ranks[canonical_handle(item["handle"])]):
        handle = canonical_handle(row["handle"])
        if handle in included_handles:
            decision = "included"
            reason = ("Explicitly requested account with verified eligibility." if handle in pinned else
                      "Included by relationship priority and discovery rank within the six-account content budget.")
        elif not row.get("eligible") or row.get("relationship") == "excluded":
            decision = "excluded_by_eligibility"
            reason = str(row.get("reason") or "Profile evidence did not support competitor eligibility.")
        elif row.get("relationship") == "media" and media_used >= media_cap:
            decision = "not_selected_media_cap"
            reason = "Eligible media reference exceeded the one-account media cap."
        else:
            decision = "not_selected_capacity"
            reason = "Eligible account ranked below the six-account content retrieval capacity."
        row_audit = {
            "handle": handle,
            "relationship": row["relationship"],
            "eligible": bool(row["eligible"]),
            "discovery_rank": ranks[handle],
            "decision": decision,
            "reason": reason,
        }
        audit.append(row_audit)
    for handle in sorted(selected_handles - candidate_handles, key=lambda value: ranks[value]):
        audit.append({
            "handle": handle,
            "relationship": "excluded",
            "eligible": False,
            "discovery_rank": ranks[handle],
            "decision": "excluded_profile_unavailable",
            "reason": ("The requested public profile was unavailable; no substitute was used." if handle in pinned else
                       "The selected public profile was unavailable and was replaced by a frozen reserve."),
        })
    audit.sort(key=lambda row: (row["discovery_rank"], row["handle"]))
    result = {
        "schema_version": "competitor-account-selection.v1",
        "request_id": str(eligibility["request_id"]),
        "included_handles": [canonical_handle(row["handle"]) for row in included],
        "audit": audit,
    }
    return result


def _selection_fingerprint(selection: dict[str, Any]) -> dict[str, Any]:
    audit = []
    for row in selection.get("audit") or []:
        if not isinstance(row, dict):
            continue
        item = {
            "handle": canonical_handle(str(row.get("handle") or "")),
            "relationship": row.get("relationship"),
            "eligible": bool(row.get("eligible")),
            "discovery_rank": row.get("discovery_rank"),
            "decision": row.get("decision"),
        }
        if row.get("axis_role"):
            item["axis_role"] = row.get("axis_role")
        audit.append(item)
    audit.sort(key=lambda row: (row.get("discovery_rank") or 0, row["handle"]))
    return {
        "included_handles": [canonical_handle(str(value)) for value in selection.get("included_handles") or []],
        "audit": audit,
        "limitations": list(selection.get("limitations") or []),
    }


def assert_selection_matches_finalize(
    selection: dict[str, Any],
    discovery: dict[str, Any],
    eligibility: dict[str, Any],
    eligibility_input: dict[str, Any] | None = None,
) -> None:
    """Refuse a hand-written six-account roster. A live 0.4.7 run skipped finalize."""
    if not isinstance(selection, dict) or selection.get("schema_version") != "competitor-account-selection.v1":
        raise ValueError("expected competitor-account-selection.v1")
    if discovery is None or eligibility is None or eligibility_input is None:
        raise ValueError(
            "selection must be produced by select_accounts.py finalize; "
            "pass --discovery, --eligibility and --eligibility-input"
        )
    expected = finalize(discovery, eligibility, eligibility_input=eligibility_input)
    got = _selection_fingerprint(selection)
    want = _selection_fingerprint(expected)
    if got != want:
        raise ValueError(
            "selection does not match select_accounts.py finalize; "
            f"got included_handles={got['included_handles']}, "
            f"expected={want['included_handles']}. "
            "Do not hand-write competitor-account-selection.json."
        )


def roster_summary(result: dict[str, Any]) -> dict[str, Any]:
    """The handles the next step needs, so the selection file does not have to be read back."""
    summary: dict[str, Any] = {}
    for key in ("selected_handles", "reserve_handles", "included_handles"):
        if isinstance(result.get(key), list):
            summary[key] = result[key]
    audit = result.get("audit")
    if isinstance(result.get("included_handles"), list) and isinstance(audit, list):
        summary["relationships"] = {
            str(row.get("handle")): row.get("relationship")
            for row in audit
            if isinstance(row, dict) and row.get("handle") in result["included_handles"]
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    discovery_parser = subparsers.add_parser("discover")
    discovery_parser.add_argument("--candidates", type=Path, required=True)
    discovery_parser.add_argument("--gate", type=Path, required=True)
    discovery_parser.add_argument("--request", type=Path)
    discovery_parser.add_argument("--request-id")
    discovery_parser.add_argument("--gate-input", type=Path, help=argparse.SUPPRESS)
    discovery_parser.add_argument("--subject-handle", action="append", default=[])
    discovery_parser.add_argument(
        "--strategy",
        choices=("auto", "legacy-v1", "comparable-v2", "evidence-score-v3"),
        default="auto",
    )
    discovery_parser.add_argument("--output", type=Path, required=True)
    final_parser = subparsers.add_parser("finalize")
    final_parser.add_argument("--discovery", type=Path, required=True)
    final_parser.add_argument("--eligibility", type=Path, required=True)
    final_parser.add_argument("--eligibility-input", type=Path)
    final_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "discover":
            if args.gate_input is not None:
                raise ValueError(
                    "--gate-input is not a discover flag; pass --gate "
                    "competitor-discovery-gate.json (the scored gate). "
                    "competitor-discovery-gate-input.json is only the "
                    "project_gate_inputs.py output"
                )
            gate = load(args.gate)
            request = load(args.request) if args.request else None
            result = discover(
                load(args.candidates),
                gate,
                resolve_discover_request_id(gate, request, args.request_id),
                set(args.subject_handle),
                strategy=args.strategy,
                request=request,
            )
        else:
            result = finalize(
                load(args.discovery),
                load(args.eligibility),
                eligibility_input=load(args.eligibility_input) if args.eligibility_input else None,
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "path": str(args.output), **roster_summary(result)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
