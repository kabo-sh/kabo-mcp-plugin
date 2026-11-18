"""Prepare the existing request schema from a host-read post; never guess nested source fields.

Two inputs: linked-media packets (`--envelope`), or `--file-ref kabo-file:<id>` with `--platform` for a video
the creator attached in Kabo. The media tool reads that stored file the way it reads a link, so the request is
a connector request (`acquisition: public_url`, the reference as its `url`, the file id as its content id); a
file on the creator's own machine is a `local_file` request instead and is never uploaded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_media  # noqa: E402
import public_video_sources  # noqa: E402


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


def request_for(platform: str, url: str, content_id: str, media_type, subject: str, budget: int, confirmed: bool,
                request_id: str) -> dict:
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


def check_budget(budget: int) -> None:
    if type(budget) is not int or not 0 <= budget <= 100:
        raise ValueError("max-connector-calls must be an integer between 0 and 100")


def prepare_file(file_ref: str, platform: str, subject: str, budget: int, confirmed: bool, request_id: str) -> dict:
    """The request for a video the creator attached in Kabo (kabo-file:<id>)."""
    check_budget(budget)
    ref = collect_media.video_source(file_ref)
    if not collect_media.is_file_ref(ref):
        raise ValueError("--file-ref takes kabo-file:<id>, the attached video's reference")
    # The platform the video was posted on or is made for; the file itself names none.
    if platform not in public_video_sources.platform_ids():
        raise ValueError("--platform names the platform the attached video is for: "
                         + ", ".join(public_video_sources.platform_ids()))
    return request_for(platform, ref, ref.split(":", 1)[1], "video", subject, budget, confirmed, request_id)


def prepare(bundles: list[dict], subject: str, budget: int, confirmed: bool, request_id: str) -> dict:
    check_budget(budget)
    bundles = [candidate for body in bundles for candidate in (body, body.get("linked_media", {}))
               if isinstance(candidate, dict) and candidate.get("schema_version") == "linked-media-evidence.v1"]
    if not bundles:
        raise ValueError("no linked-media-evidence.v1 input: complete link reading before preparation")
    sources = {(b.get("identity", {}).get("platform"), b.get("original_url"), b.get("post_id"),
                b.get("media_type")) for b in bundles}
    if len(sources) != 1:
        raise ValueError("linked evidence describes more than one post")
    platform, url, content_id, media_type = sources.pop()
    # Which platforms are accepted comes only from the support list, not from a second copy here.
    if platform not in public_video_sources.platform_ids() or not url or not content_id:
        raise ValueError("linked evidence does not identify a supported post")
    if subject not in {"own_published", "third_party", "unknown"}:
        raise ValueError("a public link cannot identify an unpublished draft")
    return request_for(platform, url, content_id, media_type, subject, budget, confirmed, request_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", type=Path, action="append", default=[])
    parser.add_argument("--file-ref", help="kabo-file:<id> of a video the creator attached in Kabo")
    parser.add_argument("--platform", help="with --file-ref: the platform the video is for")
    parser.add_argument("--subject-state", choices=["own_unpublished", "own_published", "third_party", "unknown"],
                        required=True)
    parser.add_argument("--max-connector-calls", type=int, required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request_id = args.output.parent.parent.name
        if args.file_ref:
            if args.envelope:
                raise ValueError("--file-ref and --envelope describe two different copies of a video; give one")
            request = prepare_file(args.file_ref, args.platform, args.subject_state, args.max_connector_calls,
                                   args.confirmed_by_user, request_id)
        else:
            bodies = [json.loads(p.read_text()) for p in args.envelope]
            request = prepare(bodies, args.subject_state, args.max_connector_calls, args.confirmed_by_user,
                              request_id)
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
