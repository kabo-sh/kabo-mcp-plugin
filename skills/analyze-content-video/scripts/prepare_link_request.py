"""Prepare the existing request schema from a host-read post; never guess nested source fields.

Three inputs: linked-media packets (`--envelope`), `--url <public link>` with `--platform` for a link the creator
gave, or `--file-ref kabo-file:<id>` with `--platform` for a video the creator attached in Kabo. With `--mode`, the
call ceiling defaults to what that mode's observation uses (MODE_CALLS); `--max-connector-calls` overrides it. The media tool reads that stored file the way it reads a link, so the request is
a connector request (`acquisition: public_url`, the reference as its `url`, the file id as its content id); a
file on the creator's own machine is a `local_file` request instead and is never uploaded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.dont_write_bytecode = True  # sibling imports must not leave __pycache__ in the Skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_media  # noqa: E402
import public_video_sources  # noqa: E402


# The tool-call ceiling each mode's observation of one video usually needs: the media call and its readings,
# a whole-video viewing, frame reads and metadata; an own-published diagnosis adds the baseline. A declared ceiling, not billing.
MODE_CALLS = {"diagnosis": 12, "craft_teardown": 12, "content_read": 8, "transcript_export": 6}
BASELINE_CALLS = 3


def default_budget(mode: str | None, subject: str) -> int | None:
    if mode is None:
        return None
    return MODE_CALLS[mode] + (BASELINE_CALLS if mode == "diagnosis" and subject == "own_published" else 0)


def public_only_request_errors(request: dict) -> list[str]:
    """Unknown ownership is an explicit public-only request, never another subject state."""
    source = request.get("source") or {}
    if source.get("subject_state") != "unknown":
        return []
    errors = []
    if source.get("acquisition") != "public_url" or not source.get("url"):
        errors.append("unknown ownership requires an explicit public_url source" + (
            ": `unknown` is the public-link-only scope, so a file on this machine is never `unknown`. Ask whose "
            "video it is, or choose `third_party` for someone else's video and `own_unpublished` or "
            "`own_published` for the creator's own cut, then write the request again"
            if source.get("acquisition") == "local_file" else ""))
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


def prepare_url(url: str, platform: str, subject: str, budget: int, confirmed: bool, request_id: str) -> dict:
    """The request for a public link the creator gave: its id when the link itself names one, else null."""
    check_budget(budget)
    if platform not in public_video_sources.platform_ids():
        raise ValueError("--platform names the platform of the link: " + ", ".join(public_video_sources.platform_ids()))
    if subject == "own_unpublished":
        raise ValueError("a public link cannot identify an unpublished draft")
    link = str(url).strip()
    if collect_media.is_file_ref(link):
        raise ValueError("a kabo-file:<id> reference goes with --file-ref, not --url")
    if not link.lower().startswith("https://"):
        raise ValueError("--url takes the public https link exactly as the creator gave it")
    found = public_video_sources.match_url(link)
    if found is not None and found["platform"] != platform:
        raise ValueError(f"the link is a {found['platform']} link, but --platform says {platform}")
    # A short link has no id until the server resolves it: keep null; the evidence builder takes it from this run's results, never a guess.
    content_id = public_video_sources.content_id_from_url(platform, link)
    return request_for(platform, link, content_id, None, subject, budget, confirmed, request_id)


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
    parser.add_argument("--url", help="the public video link exactly as the creator gave it")
    parser.add_argument("--platform", help="with --file-ref or --url: the platform the video is on or for")
    parser.add_argument("--subject-state", choices=["own_unpublished", "own_published", "third_party", "unknown"],
                        required=True)
    parser.add_argument("--mode", choices=sorted(MODE_CALLS),
                        help="the analysis mode; sets the default --max-connector-calls")
    parser.add_argument("--max-connector-calls", type=int)
    parser.add_argument("--confirmed-by-user", action="store_true")
    # Run from the run directory, the request's place is fixed; a command that left the flag out once stopped a run.
    parser.add_argument("--output", type=Path, default=Path("analysis/video-analysis-request.json"))
    args = parser.parse_args()
    if args.max_connector_calls is None:
        args.max_connector_calls = default_budget(args.mode, args.subject_state)
        if args.max_connector_calls is None:
            parser.error("give --mode (for its default call ceiling) or --max-connector-calls")
    try:
        # Resolved first: a relative `analysis/video-analysis-request.json` has no grandparent name of its own.
        request_id = args.output.resolve().parent.parent.name
        if sum(bool(item) for item in (args.file_ref, args.url, args.envelope)) > 1:
            raise ValueError("--url, --file-ref and --envelope each describe the video; give one of them")
        if args.file_ref:
            request = prepare_file(args.file_ref, args.platform, args.subject_state, args.max_connector_calls,
                                   args.confirmed_by_user, request_id)
        elif args.url:
            request = prepare_url(args.url, args.platform, args.subject_state, args.max_connector_calls,
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
