"""Prepare the existing request schema from a host-read post; never guess nested source fields."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def public_only_request_errors(request: dict) -> list[str]:
    """Unknown ownership is an explicit public-only request, never another subject state."""
    source = request.get("source") or {}
    if source.get("subject_state") != "unknown":
        return []
    errors = []
    if source.get("acquisition") != "public_url" or not source.get("url"):
        errors.append("unknown ownership requires an explicit public_url source")
    if "owner_data" not in source or source["owner_data"] is not None:
        errors.append("unknown ownership requires owner_data=null")
    if (request.get("acquire") or {}).get("owner_metrics") != "skip":
        errors.append("unknown ownership requires owner_metrics=skip")
    if request.get("baseline") is not None:
        errors.append("unknown ownership cannot use an owner baseline")
    return errors


def prepare(bundles: list[dict], subject: str, budget: int, confirmed: bool, request_id: str) -> dict:
    if type(budget) is not int or not 0 <= budget <= 100:
        raise ValueError("max-connector-calls must be an integer between 0 and 100")
    bundles = [candidate for body in bundles for candidate in (body, body.get("linked_media", {}))
               if isinstance(candidate, dict) and candidate.get("schema_version") == "linked-media-evidence.v1"]
    if not bundles:
        raise ValueError("no linked-media-evidence.v1 input: complete link reading before preparation")
    sources = {(b.get("identity", {}).get("platform"), b.get("original_url"), b.get("post_id"),
                b.get("media_type")) for b in bundles}
    if len(sources) != 1:
        raise ValueError("linked evidence describes more than one post")
    platform, url, content_id, media_type = sources.pop()
    if platform not in {"tiktok", "instagram", "youtube"} or not url or not content_id:
        raise ValueError("linked evidence does not identify a supported post")
    if subject not in {"own_published", "third_party", "unknown"}:
        raise ValueError("a public link cannot identify an unpublished draft")
    request = {
        "schema_version": "video-analysis-request.v1", "request_id": request_id,
        "source": {"acquisition": "public_url", "subject_state": subject, "platform": platform,
                   "url": url, "content_id": content_id, "declared_format": media_type,
                   "owner_data": None},
        "acquire": dict.fromkeys(("media", "transcript", "frames", "owner_metrics"),
                                 "skip" if budget == 0 else "best_effort"),
        "budget": {"max_connector_calls": budget, "max_provider_credits": None,
                   "confirmed_by_user": confirmed,
                   "per_call": {"timeout_seconds": 60, "max_response_bytes": 50_000_000}},
        "failure_policy": {"on_missing_capability": "return_partial", "fatal_capabilities": []},
    }
    if subject == "unknown":
        request["acquire"]["owner_metrics"] = "skip"
    return request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", type=Path, action="append", default=[])
    parser.add_argument("--subject-state", choices=["own_published", "third_party", "unknown"], required=True)
    parser.add_argument("--max-connector-calls", type=int, required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        bodies = [json.loads(p.read_text()) for p in args.envelope]
        request = prepare(bodies,
                          args.subject_state, args.max_connector_calls, args.confirmed_by_user,
                          args.output.parent.parent.name)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(request, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    print(json.dumps({"status": "ok", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
