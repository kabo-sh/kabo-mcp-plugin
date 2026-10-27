#!/usr/bin/env python3
"""Project the Competitor discovery and eligibility gate inputs out of what the run already retrieved."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
from persist_connector_json import load_json_object
from select_accounts import candidate_author, canonical_handle


def load(path: Path) -> dict[str, Any]:
    value = load_json_object(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def expand_profile_envelopes(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept one file per account, or one `{results:[...]}` batch.

    SKILL already batches `resolve_profile`. Do not require a second split script.
    """
    expanded: list[dict[str, Any]] = []
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            continue
        results = envelope.get("results")
        if isinstance(results, list) and results:
            expanded.extend(item for item in results if isinstance(item, dict))
            continue
        expanded.append(envelope)
    return expanded


def text(item: dict[str, Any]) -> str:
    values = []
    for key in ("title", "caption", "description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return "\n".join(values)


def subject(request: dict[str, Any]) -> dict[str, Any]:
    source = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    locale = request.get("locale") if isinstance(request.get("locale"), dict) else {}
    return {
        "name": str(source.get("name") or ""),
        "description": str(source.get("description") or ""),
        # The Gate measures "same category" differently for product and creator subjects; without this
        # field that rubric branch is undecidable and the model has to guess.
        "kind": source.get("kind") or "creator",
        "market": source.get("market"),
        "audience": source.get("audience"),
        "region": locale.get("region"),
        "language": locale.get("language"),
    }


# The seed post's caption, as far as the Gate reads it.
SEED_CAPTION_CHARS = 300


def seed_caption(envelope: dict[str, Any] | None) -> str | None:
    """The caption of the post the run started from, as `get_post` returns it."""
    data = (envelope or {}).get("data") if isinstance((envelope or {}).get("data"), dict) else {}
    post = data.get("post") if isinstance(data.get("post"), dict) else {}
    edges = ((post.get("edge_media_to_caption") or {}).get("edges")) or []
    texts = [((edge or {}).get("node") or {}).get("text") for edge in edges if isinstance(edge, dict)]
    caption = "\n".join(t for t in texts if isinstance(t, str) and t.strip())
    if not caption and isinstance(post.get("caption"), (str, dict)):
        caption = post["caption"] if isinstance(post["caption"], str) else str(post["caption"].get("text") or "")
    caption = " ".join(caption.split())
    return caption[:SEED_CAPTION_CHARS] or None


def discovery_subject(request: dict[str, Any], seed: dict[str, Any] | None) -> dict[str, Any]:
    """The subject as the discovery Gate reads it: with the content form it compares against.

    Without these the Gate scored the subject's topic, not its form (one video-started case, 2026-09-19: the
    accounts that keep making the seed video's kind of Reel lost to same-topic accounts every run).
    `caption_phrases` is the subject's own recurring wording (already on the Request); `seed_caption`
    is the caption of the one video the user started from.
    """
    row = subject(request)
    source = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    phrases = [str(p) for p in source.get("caption_phrases") or [] if isinstance(p, str) and p.strip()]
    if phrases:
        row["caption_phrases"] = phrases
    if source.get("seed_content_ref"):
        caption = seed_caption(seed)
        if caption:
            row["seed_caption"] = caption
    return row


def integer(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def author_facts(author: dict[str, Any]) -> dict[str, Any]:
    """The public account fields the discovery rows already carried, when the route returned them."""
    facts: dict[str, Any] = {}
    followers = integer(author.get("follower_count"))
    posts = integer(author.get("post_count"))
    if followers is not None:
        facts["followers"] = followers
    if posts is not None:
        facts["post_count"] = posts
    if author.get("is_verified") is True:
        facts["verified"] = True
    if author.get("is_private") is True:
        facts["private"] = True
    return facts


def post_metrics(item: dict[str, Any]) -> dict[str, int]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    plays = integer(metrics.get("play_count"))
    if plays is None:
        plays = integer(metrics.get("view_count"))
    row = {"plays": plays, "likes": integer(metrics.get("like_count")),
           "comments": integer(metrics.get("comment_count"))}
    return {key: value for key, value in row.items() if value is not None}


def post_routes(item: dict[str, Any]) -> list[str]:
    """Which intent lane and rank returned this post, as `route/intent#rank`."""
    labels: list[str] = []
    for source in item.get("sources") or []:
        if not isinstance(source, dict):
            continue
        label = str(source.get("route") or "?")
        if source.get("intent_id"):
            label += f"/{source['intent_id']}"
        rank = integer(source.get("rank"))
        if rank is not None:
            label += f"#{rank}"
        if label not in labels:
            labels.append(label)
    return labels


def post_row(item: dict[str, Any]) -> dict[str, Any]:
    """One candidate post as the Gate reads it: its own words plus everything discovery returned with them."""
    row: dict[str, Any] = {"text": text(item)}
    ref = item.get("content_id") or item.get("id")
    if isinstance(ref, str) and ref.strip():
        row["ref"] = ref.strip()
    published = item.get("published_at")
    if isinstance(published, str) and published.strip():
        row["date"] = published.strip()[:10]
    row.update(post_metrics(item))
    membership = item.get("window_membership")
    if isinstance(membership, str) and membership.strip():
        row["window"] = membership.strip()
    routes = post_routes(item)
    if routes:
        row["routes"] = routes
    return row


def discovery(request: dict[str, Any], candidates: dict[str, Any],
              seed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Group the discovery rows by account, keeping what the driver already holds about each one.

    The Gate used to read the raw discovery rows in the model's own context. Projecting a handle, a
    display name and a caption dropped the published date, the play/like/comment counts, the lane and
    rank the post came back on, and the account's own follower and post counts — and with one post per
    account in the pool, a dozen accounts showing the same kind of caption became indistinguishable
    (one video-started case, 2026-09-19). Every field here is already in the persisted Candidate Set: no extra
    connector call, and captions are kept whole.
    """
    source = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    subject_ref = canonical_handle(str(source.get("account_ref") or "")) or None
    grouped: dict[str, dict[str, Any]] = {}
    posts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates.get("items") or []:
        author = candidate_author(item)
        handle = author.get("handle")
        if not isinstance(handle, str) or not handle.strip():
            continue
        ref = canonical_handle(handle)
        row = grouped.setdefault(ref, {"handle": ref, "display_name": author.get("full_name")})
        if not row.get("display_name") and author.get("full_name"):
            row["display_name"] = author["full_name"]
        for key, value in author_facts(author).items():
            row.setdefault(key, value)
        post = post_row(item)
        if post not in posts[ref]:
            posts[ref].append(post)
    authors = []
    for ref in sorted(grouped):
        row = {key: value for key, value in grouped[ref].items() if value is not None and value != ""}
        if subject_ref and ref == subject_ref:
            row["is_subject"] = True
        row["posts"] = posts[ref]
        authors.append(row)
    return {
        "schema_version": "competitor-discovery-gate-input.v1",
        "request_id": str(request["request_id"]),
        "subject": discovery_subject(request, seed),
        "authors": authors,
    }


def author_line(row: dict[str, Any]) -> str:
    facts = []
    if row.get("followers") is not None:
        facts.append(f"{row['followers']} followers")
    if row.get("post_count") is not None:
        facts.append(f"{row['post_count']} posts")
    if row.get("verified"):
        facts.append("verified")
    if row.get("private"):
        facts.append("private")
    if row.get("is_subject"):
        facts.append("the subject itself")
    return " · ".join(facts)


def post_line(post: dict[str, Any]) -> str:
    facts = []
    if post.get("date"):
        facts.append(str(post["date"]))
    for key, unit in (("plays", "plays"), ("likes", "likes"), ("comments", "comments")):
        if post.get(key) is not None:
            facts.append(f"{post[key]} {unit}")
    if post.get("window") and post["window"] != "within_window":
        facts.append(str(post["window"]))
    if post.get("routes"):
        facts.append(" ".join(str(value) for value in post["routes"]))
    if post.get("ref"):
        facts.append(str(post["ref"]))
    body = " / ".join(part.strip() for part in str(post.get("text") or "").splitlines() if part.strip())
    return " · ".join([*facts, body]) if body else " · ".join(facts)


def discovery_table(result: dict[str, Any]) -> str:
    """The discovery projection as numbered author lines: what the Instagram Gate scores.

    One line per author, still: the number the Gate scores stays at the start of it. Each post on that
    line carries its date, counts, lane and id ahead of its own words, so two accounts that posted the
    same kind of caption are no longer the same row.
    """
    lines = [json.dumps({"request_id": result["request_id"], "subject": result["subject"]}, ensure_ascii=False)]
    for index, row in enumerate(result["authors"], start=1):
        name = row["handle"] + (f" | {row['display_name']}" if row.get("display_name") else "")
        facts = author_line(row)
        head = f"{index}. [{name}]" + (f" {facts}" if facts else "")
        posts = " || ".join(post_line(post) for post in row.get("posts") or [])
        # `||` separates the posts from each other and, when the account itself had fields, from those.
        lines.append((head + (" || " if facts else " ") + posts) if posts else head)
    return "\n".join(lines)


def profile_row(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else None
    if profile is not None:
        handle = canonical_handle(str(profile.get("username") or ""))
        return {
            "handle": handle,
            "display_name": profile.get("full_name"),
            "description": profile.get("biography"),
            "category": profile.get("category_name") or profile.get("business_category_name"),
            "external_url": profile.get("external_url"),
        }
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    return {
        "handle": canonical_handle(str(row.get("id") or "")),
        "display_name": row.get("title"),
        "description": row.get("description"),
        "category": None,
        "external_url": row.get("source_url"),
    }


def eligibility(request: dict[str, Any], discovery_selection: dict[str, Any], envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    envelopes = expand_profile_envelopes(envelopes)
    selected = [canonical_handle(str(value)) for value in discovery_selection.get("selected_handles") or []]
    reserves = [canonical_handle(str(value)) for value in discovery_selection.get("reserve_handles") or []]
    allowed = selected + reserves
    profiles = {row["handle"]: row for row in (profile_row(value) for value in envelopes) if row["handle"]}
    discovery_authors = {
        canonical_handle(str(row.get("handle") or "")): row
        for row in discovery_selection.get("authors") or []
        if isinstance(row, dict) and row.get("handle")
    }
    pinned = set(discovery_selection.get("provided_handles") or [])
    missing = sorted(set(selected) - set(profiles) - pinned)
    unknown = sorted(set(profiles) - set(allowed))
    replacements = sorted(set(profiles) & set(reserves))
    if unknown or len(replacements) < len(missing) or len(set(profiles) | pinned) < len(selected):
        raise ValueError(
            "profile envelopes must cover the selected budget with frozen reserves; "
            f"missing={missing}, replacements={replacements}, unknown={unknown}"
        )
    return {
        "schema_version": "competitor-eligibility-input.v1",
        "request_id": str(request["request_id"]),
        "subject": subject(request),
        "profiles": [
            {
                **profiles[ref],
                "visible_content": list(discovery_authors.get(ref, {}).get("visible_content") or []),
            }
            for ref in allowed if ref in profiles
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    discover = sub.add_parser("discovery")
    discover.add_argument("--request", type=Path, required=True)
    discover.add_argument("--candidates", type=Path, required=True)
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--print", action="store_true", help="also print the projection to stdout")
    discover.add_argument("--table", action="store_true", help="also print numbered author lines for the score table")
    discover.add_argument("--seed-envelope", type=Path, help="the get_post Envelope the run started from, if any")
    eligible = sub.add_parser("eligibility")
    eligible.add_argument("--request", type=Path, required=True)
    eligible.add_argument("--discovery", type=Path, required=True)
    eligible.add_argument("--profile-envelope", type=Path, action="append", required=True)
    eligible.add_argument("--output", type=Path, required=True)
    eligible.add_argument("--print", action="store_true", help="also print the projection to stdout")
    args = parser.parse_args()
    try:
        request = load(args.request)
        if args.operation == "discovery":
            seed = load(args.seed_envelope) if args.seed_envelope and args.seed_envelope.is_file() else None
            result = discovery(request, load(args.candidates), seed)
        else:
            result = eligibility(request, load(args.discovery), [load(path) for path in args.profile_envelope])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "path": str(args.output)}))
        if args.print:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        if args.operation == "discovery" and args.table:
            print(discovery_table(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
