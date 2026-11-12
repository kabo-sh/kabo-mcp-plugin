#!/usr/bin/env python3
"""A creator's own content library for post reviews and recaps, plus the small state of the daily picks.

One directory per account (`<workspace>/kabo-library/<platform>-<handle>/`) keeps:
  library.json  account, binding time, niche and content pillars read from Kabo's profile, follower readings
  posts.json    every own video post seen, with each public-metric observation and its age
  picks.json    the days the daily picks were checked and what was shown, so a pick never repeats
  reviews/      the 24 h review reports (and the optional 1 h / 7 d ones)
  recaps/       the daily account recaps

The script reshapes and counts; it never judges. In the first session the assistant proposes content
pillars from the posts, the creator confirms them, and they are declared to Kabo once
(update_content_preferences, declare_pillars); from then on Kabo holds them and this library is only a
cache. The daily "for you" videos come only from get_for_you_videos.
Review wording and recommendations belong to the model. Metrics come only from
public-content-snapshot.v1 files that build_public_snapshot.py assembled from staged Kabo evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent

LIBRARY_FORMAT = "kabo.creator-library.v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
METRICS = ("views", "likes", "comments", "shares", "saves")
# The three review time points; band is the observation range (hours) that counts as this time point, used
# to take an equal-age baseline from other posts.
# The account is looked at once a day, so the 24-hour band is widened to 24-48 hours: one observation per
# day lands in it exactly once.
CHECKPOINTS = {"1h": (1.0, 3.0), "24h": (24.0, 48.0), "7d": (168.0, 192.0)}
CHECKPOINT_ORDER = ("1h", "24h", "7d")
# By default only the 24-hour review runs; 1 hour and 7 days are optional time points (due --with-optional).
LATE_AFTER_HOURS = 48.0
# Only posts at least 72 hours old count as having stable views, used for content-pillar performance and
# the account's typical level.
SETTLED_HOURS = 72.0
# At most 4 signature-content items from the profile are taken as pillars (same cap as the backend profile).
MAX_PILLARS = 4
# Photos and image posts are not videos and have no view counts, so they do not enter the library.
NON_VIDEO_FORMATS = {"instagram_feed", "tiktok_photo"}
USABLE_STATUSES = {"completed", "completed_partial"}
PROFILE_OPERATIONS = {"resolve_profile", "get_channel"}
CONTENT_OPERATIONS = {"list_posts", "list_reels", "list_channel_uploads", "list_account_posts"}


def fail(message):
    raise ValueError(message)


def now_utc():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        fail(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    # Write a temp file first, then replace: if a scheduled task is interrupted, no half-written JSON is left
    # behind.
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def say(value):
    print(json.dumps(value, ensure_ascii=False, indent=1))


def normalize_handle(raw):
    handle = str(raw or "").strip().lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9._-]{1,64}", handle):
        fail("Handle must be the account's public username, without spaces")
    return handle


def library_path(workspace, platform, handle):
    if platform not in PLATFORMS:
        fail("Platform must be one of: " + ", ".join(PLATFORMS))
    return Path(workspace).expanduser().resolve() / "kabo-library" / f"{platform}-{normalize_handle(handle)}"


def load_library(directory):
    directory = Path(directory)
    library = read_json(directory / "library.json")
    if library.get("format") != LIBRARY_FORMAT:
        fail("Not a Kabo creator library: " + str(directory))
    posts = read_json(directory / "posts.json", {"posts": {}})
    return library, posts


def metric_value(item, name):
    entry = (item.get("metrics") or {}).get(name) or {}
    if entry.get("status") in ("available", "zero") and isinstance(entry.get("value"), (int, float)):
        return float(entry["value"])
    return None


def publish_time(platform, item):
    """Publish time and where it came from; TikTok sometimes returns a date with no time."""
    published = parse_time(item.get("published_at"))
    if published is None:
        return None, "missing"
    if platform == "tiktok" and published.hour == 0 and published.minute == 0 and published.second == 0:
        # The high 32 bits of a TikTok video id are the creation time. A scheduled video is created early, so it is
        # used only when it falls on the same day.
        try:
            created = datetime.fromtimestamp(int(item["content_id"]) >> 32, tz=timezone.utc)
        except (KeyError, ValueError, OverflowError, OSError):
            return published, "date_only"
        if created.date() == published.date():
            return created, "video_id"
        return published, "date_only"
    return published, "platform"


def age_anchor(post):
    # A date-only publish time cannot be used for an hourly age, so use the time it was first seen instead, and
    # say so in the output.
    if post.get("published_at_source") == "date_only":
        return parse_time(post.get("first_seen_at")), "first_seen"
    return parse_time(post.get("published_at")), "published"


def latest(post):
    observations = post.get("observations") or []
    return observations[-1] if observations else None


def median(values):
    values = [value for value in values if isinstance(value, (int, float))]
    return statistics.median(values) if values else None


def views_words(value):
    """Views as the creator should read them: a whole number with thousands separators (1,231,293,530)."""
    return f"{int(round(value)):,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def times_words(value):
    """A multiple with at most two decimals and no trailing zeros (1.8, 2, 0.45)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return f"{round(value, 2):.2f}".rstrip("0").rstrip(".")


def share_words(share):
    # Say the share in terms the creator understands: use a fraction when it is close to a common one,
    # otherwise a percentage.
    if not isinstance(share, (int, float)) or isinstance(share, bool) or share <= 0:
        return None
    for value, words in ((0.25, "about a quarter"), (1 / 3, "about a third"), (0.5, "about half"),
                         (2 / 3, "about two thirds"), (0.75, "about three quarters")):
        if abs(share - value) <= 0.03:
            return words
    return f"about {round(share * 100)}%"


def ratio(value, base):
    if value is None or not base:
        return None
    return round(value / base, 2)


# ---------------------------------------------------------------- fetch requests and snapshot

def cmd_path(args):
    # Print the directory only: all three Skills call it and two of them run unattended, so it cannot carry
    # anything to be said to the creator.
    directory = library_path(args.workspace, args.platform, args.handle)
    say({"library": str(directory), "exists": (directory / "library.json").exists()})


def connect_key(platform, handle, binding_version):
    """Idempotency key for connect_public_account: the same for a retry of one request, different for another request.

    Key = library:<platform>:<lowercase handle>:<binding_version of the binding being replaced, or new for a first binding>. With only the account in the key,
    "bind A -> switch to B -> switch back to A" would send different requests under the same key, and the backend rejects it permanently as a conflict (Codex measured @MrBeast).
    Maximum length 8+9+1+64+1+36=119, under the contract limit of 128; character set A-Za-z0-9._:-."""
    version = str(binding_version or "new").lower()
    if version != "new" and not re.fullmatch(r"[0-9a-f-]{36}", version):
        fail("--expected-binding-version must be the bindingVersion uuid from list_connected_accounts")
    key = f"library:{platform}:{normalize_handle(handle)}:{version}"
    if not (8 <= len(key) <= 128 and re.fullmatch(r"[A-Za-z0-9._:-]+", key)):
        fail("The handle cannot form a valid idempotency key")
    return key


def cmd_connect_request(args):
    """The exact connect_public_account arguments; pass them to the tool unchanged (retry with the same ones)."""
    if bool(args.expected_account_id) != bool(args.expected_binding_version):
        fail("Replacing a link needs both --expected-account-id and --expected-binding-version")
    handle = normalize_handle(args.handle)
    request = {"platform": args.platform, "handle_or_url": args.url or handle,
               "idempotency_key": connect_key(args.platform, handle, args.expected_binding_version)}
    if args.expected_account_id:
        request.update({"expected_account_id": args.expected_account_id,
                        "expected_binding_version": args.expected_binding_version})
    say(request)


def cmd_connect_result(args):
    """What to tell the creator after connect_public_account; the raw error stays in `reported` for the assistant."""
    payload, is_error = tool_payload(read_json(args.result))
    handle = "@" + normalize_handle(args.handle)
    # On success the output is {"account": {...}} (pinned in the contract), and the account id is in account.id.
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    if not is_error and first_text(account.get("id")):
        say({"linked": True, "account_id": account["id"], "binding_version": account.get("bindingVersion"),
             "tell_creator_now": f"{handle} is now linked to your Kabo."})
        return
    if needs_write_access(payload, is_error):
        line = (f"Kabo needs your permission to save to your account before I can link {handle}. Reconnect Kabo in this "
                "app and approve it. Meanwhile I'll read its videos and propose pillars.")
    else:
        line = (f"I couldn't link {handle} to your Kabo just now. I'll still read its videos and propose pillars; we can "
                "try linking again in a moment.")
    say({"linked": False, "tell_creator_now": line, "reported": reported(payload)})


def cmd_history_request(args):
    """The exact collect_account_history arguments for this account; pass them to the tool unchanged."""
    if args.channel_id and args.platform != "youtube":
        fail("--channel-id is only for YouTube")
    account = {"channel_id": args.channel_id} if args.channel_id else {"handle": normalize_handle(args.handle)}
    full = args.depth == "full"
    # Building the library reads more (a steadier sample for the account's typical level and the equal-age
    # baseline); each daily review needs only the most recent posts.
    if args.platform == "instagram":
        history = {"max_items": 100 if full else 30, "max_pages": 40 if full else 10,
                   "instagram_formats": {"posts": False, "reels": True, "balance": "fewer_rows_first"}}
    elif args.platform == "youtube":
        size = 50 if full else 30
        history = {"max_items": size * (2 if full else 1), "max_pages": 2 if full else 1, "page_size": size}
    else:
        history = {"max_items": 100 if full else 30}
    say({"platform": args.platform, "accounts": [account], "profile": True, "history": history,
         "on_identity_miss": "gap", "delivery": "download"})


def staged_envelope(call):
    return read_json(call["path"])


def cmd_snapshot(args):
    """Assemble the newest staged collect_account_history result into one public-content-snapshot.v1."""
    sys.path.insert(0, str(HERE))
    import static_host
    records = static_host.composite_records("collect_account_history")
    if not records:
        fail("No staged collect_account_history result in this run; fetch it with static_host.py first")
    record = records[-1]
    chosen, problems, profile_seen = [], [], False
    for call in record["calls"]:
        envelope = staged_envelope(call)
        operation = envelope.get("operation")
        if operation not in PROFILE_OPERATIONS | CONTENT_OPERATIONS:
            continue
        if envelope.get("status") in USABLE_STATUSES:
            chosen.append(call["path"])
            profile_seen = profile_seen or operation in PROFILE_OPERATIONS
        else:
            problems.append({"operation": operation, "status": envelope.get("status"),
                             "error_code": envelope.get("error_code")})
    if not any(read_json(path).get("operation") in CONTENT_OPERATIONS for path in chosen):
        fail("The account returned no public posts (not found, private, empty or the read failed): "
             + json.dumps(problems, ensure_ascii=False))
    builder = HERE / "build_public_snapshot.py"
    if not builder.is_file():
        fail("This Skill has no build_public_snapshot.py; build the snapshot from review-new-posts")
    command = [sys.executable, "-B", str(builder), "--platform", args.platform, "--window", "auto",
               "--derive-complete", "--output", str(args.output)]
    for path in chosen:
        command += ["--envelope", path]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        fail("Snapshot assembly failed: " + (done.stdout + done.stderr).strip()[-600:])
    result = json.loads(done.stdout.strip().splitlines()[-1])
    result.update({"collect_status": record.get("status"), "profile_read": profile_seen, "failed_reads": problems})
    say(result)


# ---------------------------------------------------------------- ingest

def cmd_ingest(args):
    snapshot = read_json(args.snapshot)
    if snapshot.get("schema_version") != "public-content-snapshot.v1":
        fail("--snapshot must be a public-content-snapshot.v1 file from build_public_snapshot.py")
    platform = snapshot.get("platform")
    observed = parse_time(snapshot.get("observed_at"))
    if platform not in PLATFORMS or observed is None:
        fail("Snapshot has no platform or observed_at")
    creators = [row for row in snapshot.get("creators") or [] if isinstance(row, dict)]
    directory = Path(args.library)
    created = not (directory / "library.json").exists()
    if created:
        if not args.handle:
            fail("The first ingest needs --handle, the account this library belongs to")
        handle = normalize_handle(args.handle)
        owner = next((row for row in creators if normalize_handle(row.get("handle") or "x") == handle), None)
        if owner is None and len(creators) == 1:
            owner = creators[0]  # A YouTube channel name can differ from its custom link; when only one account was read, it is the creator's own
        if owner is None:
            fail(f"The snapshot holds no posts from @{handle}; check the handle and platform")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reviews").mkdir(exist_ok=True)
        # The binding time is the server fetch time: only posts published afterward enter the review.
        write_json(directory / "library.json", {
            "format": LIBRARY_FORMAT, "platform": platform, "handle": handle,
            "creator_id": owner.get("creator_id"), "bound_at": iso(observed), "fresh": False,
            "niche": None, "pillars": [], "followers": [], "profile": {}, "updated_at": iso(observed),
        })
    library, store = load_library(directory)
    if library["platform"] != platform:
        fail(f"This library is for {library['platform']}, not {platform}")
    if library.get("fresh") and any(post.get("observations") for post in (store.get("posts") or {}).values()):
        # The library already holds an earlier reading, which means the host kept the file: later reviews have
        # history to compare against.
        library["fresh"] = False
    if library.get("bound_at") is None:
        library["bound_at"] = iso(observed - timedelta(hours=library.get("lookback_hours", 0)))
    bound = parse_time(library["bound_at"])
    posts = store.setdefault("posts", {})
    if library.get("creator_id") is None:
        # A library built by bootstrap does not know the account id yet: claim it by account name; when only one
        # account was read, it is the creator's own.
        claimed = next((row for row in creators if normalize_handle(row.get("handle") or "x") == library["handle"]), None)
        if claimed is None and len(creators) == 1:
            claimed = creators[0]
        if claimed is None:
            fail(f"The snapshot holds no posts from @{library['handle']}; check the handle and platform")
        library["creator_id"] = claimed.get("creator_id")
    owner = next((row for row in creators if row.get("creator_id") == library.get("creator_id")), None)
    if owner and isinstance(owner.get("followers"), (int, float)):
        readings = library.setdefault("followers", [])
        if not any(row["observed_at"] == iso(observed) for row in readings):
            readings.append({"observed_at": iso(observed), "value": int(owner["followers"])})
    new_posts, updated = [], 0
    for item in snapshot.get("items") or []:
        if item.get("creator_id") != library.get("creator_id") or item.get("format") in NON_VIDEO_FORMATS:
            continue  # Other people's posts (duets, reposts) and photo/image posts do not enter the library
        content_id = str(item["content_id"])
        post = posts.get(content_id)
        if post is None:
            published, source = publish_time(platform, item)
            post = posts[content_id] = {
                "content_id": content_id, "url": item.get("url"), "format": item.get("format"),
                "duration_seconds": item.get("duration_seconds"), "title": (item.get("title") or "")[:600],
                "published_at": iso(published) if published else None, "published_at_source": source,
                "first_seen_at": iso(observed), "pillar_id": None, "observations": [], "reviews": {},
            }
            # Only posts published after binding are reviewed; for date-only ones, judge by the time first seen.
            anchor, _ = age_anchor(post)
            post["tracked"] = bool(anchor and anchor >= bound and not created)
            if post["tracked"]:
                new_posts.append(content_id)
        anchor, anchor_kind = age_anchor(post)
        if any(row["observed_at"] == iso(observed) for row in post["observations"]):
            continue
        row = {"observed_at": iso(observed), "snapshot_id": snapshot.get("snapshot_id")}
        row["age_hours"] = round((observed - anchor).total_seconds() / 3600, 2) if anchor else None
        row["age_from"] = anchor_kind
        for name in METRICS:
            row[name] = metric_value(item, name)
        post["observations"].append(row)
        updated += 1
    library["updated_at"] = iso(observed)
    write_json(directory / "posts.json", store)
    write_json(directory / "library.json", library)
    say({"library": str(directory), "created": created, "observed_at": iso(observed),
         "posts_in_library": len(posts), "observations_added": updated, "new_tracked_posts": new_posts,
         "followers_now": (library.get("followers") or [{}])[-1].get("value"),
         "due": due_reviews(posts)})


# ---------------------------------------------------------------- posts and pillars

def settled_views(posts):
    rows = []
    for post in posts.values():
        last = latest(post)
        if last and last.get("views") is not None and (last.get("age_hours") or 0) >= SETTLED_HOURS:
            rows.append((post, last["views"]))
    return rows


def post_row(post, typical):
    last = latest(post) or {}
    return {"content_id": post["content_id"], "published_at": post.get("published_at"),
            "age_hours": last.get("age_hours"), "views": last.get("views"),
            "multiple_of_typical": ratio(last.get("views"), typical), "likes": last.get("likes"),
            "comments": last.get("comments"), "pillar_id": post.get("pillar_id"),
            "duration_seconds": post.get("duration_seconds"),
            "url": post.get("url"), "title": (post.get("title") or "")[:200]}


# The two opening sentences come from the script; the model translates them into the creator's language and
# sends one message per sentence, then asks one question (the account). What is said must be what will
# actually happen this time:
# first read the posts and settle the pillars together (proposed locally, synced to Kabo after the creator
# confirms), and the picks come from the backend's "For you".
OPENING = [
    "I'm Kabo. I find the most-watched recent videos in your kind of content and help you make your own version.",
    "First I link your account and read your recent videos. Then we agree on your content pillars, and I show you "
    "today's three picks.",
]


def cmd_opening(args):
    """The two opening messages of the first session, to be relayed as they are in the creator's language."""
    say({"tell_creator_now": OPENING, "then": "ask one question: the account (or name the one you will use)"})


def cmd_posts(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    typical = median([views for _, views in settled_views(posts)])
    ordered = sorted(posts.values(), key=lambda post: post.get("published_at") or "", reverse=True)[: args.limit]
    # What is said to the creator right after the posts are read: count, typical views, best one. The model
    # only translates it into the other person's language and relays it as is.
    best = max(settled_views(posts), key=lambda row: row[1], default=None)
    tell = f"I read {len(posts)} of your videos."
    if typical:
        tell += f" A typical one gets about {views_words(typical)} views."
    if best and typical:
        title = (best[0].get("title") or "").strip().splitlines()[0][:60] if (best[0].get("title") or "").strip() else "your best one"
        tell += f" Your best so far, \"{title}\", has {views_words(best[1])} views, {times_words(ratio(best[1], typical))} times that."
    result = {"handle": library["handle"], "platform": library["platform"],
              "typical_settled_views": typical, "settled_posts": len(settled_views(posts)),
              "posts": [post_row(post, typical) for post in ordered]}
    # This sentence is said only once, after the posts are read (--tell); later post listings do not repeat it
    # (in a measured run the same sentence was sent twice).
    if args.tell:
        result = {"tell_creator_now": tell, **result}
    say(result)


def cmd_media_request(args):
    """The collect_video_media arguments that fetch transcripts for the posts worth reading."""
    sys.path.insert(0, str(HERE))
    import static_host
    library, store = load_library(args.library)
    posts = store["posts"]
    ids = list(args.content_id or [])
    if not ids:
        # The 4 stable posts with the most views, then fill up to the cap with recently published ones not yet
        # chosen; no duplicates.
        top = [row[0]["content_id"] for row in sorted(settled_views(posts), key=lambda row: -row[1])[:4]]
        recent = [post["content_id"] for post in sorted(posts.values(), key=lambda post: post.get("published_at") or "", reverse=True)]
        ids = top + [cid for cid in recent if cid not in top]
    unique = list(dict.fromkeys(ids))[: args.limit]
    requests = [{"content_id": cid, "operation": "fetch_transcript", "parameters": {"url": posts[cid]["url"]}}
                for cid in unique if cid in posts and posts[cid].get("url")]
    if not requests:
        fail("No post with a link to read a transcript from")
    run_key = "lib:" + hashlib.sha256(str(static_host.run_dir()).encode()).hexdigest()[:24]
    say({"requests": requests, "run_key": run_key, "wait_s": 100, "delivery": "download"})


def transcript_text(envelope):
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    cues = [str(cue.get("text")).strip() for cue in data.get("cues") or []
            if isinstance(cue, dict) and isinstance(cue.get("text"), str) and cue["text"].strip()]
    if cues:
        return " ".join(cues)
    for key in ("plain_text", "text"):
        if isinstance(data.get(key), str) and data[key].strip():
            return data[key].strip()
    rows = [str(row.get("text")) for row in data.get("rows") or [] if isinstance(row, dict) and row.get("text")]
    return " ".join(rows).strip()


def cmd_transcripts(args):
    """Transcript text of the newest staged collect_video_media result, one entry per post."""
    sys.path.insert(0, str(HERE))
    import static_host
    records = static_host.composite_records("collect_video_media")
    if not records:
        fail("No staged collect_video_media result in this run; fetch it with static_host.py first")
    record = records[-1]
    out = []
    for call in record["calls"]:
        if call.get("tool") != "public_video_fetch_transcript":
            continue
        envelope = staged_envelope(call)
        text = transcript_text(envelope) if envelope.get("status") in USABLE_STATUSES else ""
        content_id = str(call.get("group") or "").rsplit("/", 1)[0]
        data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
        out.append({"content_id": content_id, "status": envelope.get("status"), "language": data.get("language"),
                    "text": text[: args.chars], "has_speech": bool(text)})
    coverage = record.get("coverage") if isinstance(record.get("coverage"), dict) else {}
    say({"status": record.get("status"), "pending": coverage.get("pending"), "transcripts": out})


# ---------------------------------------------------------------- local pillar proposal (proposed locally,
# synced to Kabo after the creator confirms)

# The shape and length limits of pillars follow the backend update_content_preferences declare_pillars
# (kabo#2185): check here first and have the assistant shorten anything over the limit,
# without waiting for the backend to reject it.
DECLARED_LIMITS = {"name": 60, "definition": 200, "phrase": 60, "phrases": 3}


def pillar_problems(entry, label):
    problems = []
    name = entry.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= DECLARED_LIMITS["name"]:
        problems.append(f"{label}: name must be 1 to {DECLARED_LIMITS['name']} characters")
    definition = entry.get("definition")
    if not isinstance(definition, str) or not 1 <= len(definition.strip()) <= DECLARED_LIMITS["definition"]:
        problems.append(f"{label}: definition must be 1 to {DECLARED_LIMITS['definition']} characters")
    phrases = entry.get("search_phrases")
    if not isinstance(phrases, list) or not 1 <= len(phrases) <= DECLARED_LIMITS["phrases"] or not all(
            isinstance(phrase, str) and 1 <= len(phrase.strip()) <= DECLARED_LIMITS["phrase"] for phrase in phrases):
        problems.append(f"{label}: search_phrases must be 1 to {DECLARED_LIMITS['phrases']} phrases of 1 to "
                        f"{DECLARED_LIMITS['phrase']} characters")
    return problems


def check_pillar_set(pillars, posts, require_ids=True):
    if not isinstance(pillars, list) or not 1 <= len(pillars) <= MAX_PILLARS:
        fail(f"List 1 to {MAX_PILLARS} pillars")
    problems, names = [], set()
    for index, entry in enumerate(pillars, 1):
        if not isinstance(entry, dict):
            fail(f"Pillar {index} must be an object")
        label = f"Pillar {index} ({entry.get('name')!r})"
        problems += pillar_problems(entry, label)
        key = str(entry.get("name") or "").strip().casefold()
        if key in names:
            problems.append(f"{label}: two pillars have the same name (case is ignored)")
        names.add(key)
        for content_id in entry.get("content_ids") or []:
            if content_id not in posts:
                problems.append(f"{label}: unknown content_id {content_id}; use ids from creator_library.py posts")
    if problems:
        fail("Fix these before showing or saving the pillars: " + "; ".join(problems))


def cmd_propose_pillars(args):
    """Numbers for the assistant's own grouping of the posts. Writes nothing and recommends nothing.

    The previously hard-coded rule "median views >= 0.8x, second pillar >= 20% of views" is no longer decided by the script: it only gives each group's post count, median views, and
    share of views for reference, and the decision is the creator's; these numbers are local calculations over the posts read this time, not Kabo's statistical conclusions."""
    library, store = load_library(args.library)
    posts = store["posts"]
    raw = read_json(args.clusters)
    clusters = raw.get("clusters") if isinstance(raw, dict) else None
    check_pillar_set(clusters, posts)
    seen = set()
    for cluster in clusters:
        for content_id in cluster.get("content_ids") or []:
            if content_id in seen:
                fail(f"Post {content_id} is in more than one group")
            seen.add(content_id)
    settled = settled_views(posts)
    total = sum(views for _, views in settled)
    typical = median([views for _, views in settled])
    rows = []
    for cluster in clusters:
        members = [posts[cid] for cid in cluster.get("content_ids") or []]
        views = [latest(post)["views"] for post in members if latest(post) and latest(post).get("views") is not None
                 and (latest(post).get("age_hours") or 0) >= SETTLED_HOURS]
        best = sorted((post for post in members if latest(post) and latest(post).get("views") is not None),
                      key=lambda post: -latest(post)["views"])[:2]
        rows.append({"name": cluster["name"].strip(), "definition": cluster["definition"].strip(),
                     "search_phrases": [phrase.strip() for phrase in cluster["search_phrases"]],
                     "posts": len(members), "settled_posts": len(views), "median_views": median(views),
                     "median_multiple_of_typical": ratio(median(views), typical),
                     "share_of_views": round(sum(views) / total, 3) if total and views else None,
                     "say_line": (f"{len(members)} of your videos"
                                  + (f", about {times_words(ratio(median(views), typical))} times your usual views"
                                     if times_words(ratio(median(views), typical)) else "") + "."),
                     "example_posts": [{"url": post.get("url"), "title": (post.get("title") or "")[:120],
                                        "views": latest(post)["views"]} for post in best]})
    say({"typical_settled_views": typical, "settled_posts": len(settled), "groups": rows,
         "unassigned_posts": len(posts) - len(seen),
         "note": ("Reference numbers from the posts read in this run, not Kabo's statistics and not a verdict. A group "
                  "whose median is well under the account's typical views, or that holds a small share of views, may "
                  "be weaker; say so once if it helps, and let the creator decide.")})


def pillar_key(name):
    return str(name or "").strip().casefold()


def cmd_save_pillars(args):
    """Save the pillars the creator confirmed to the library, marked as not yet synced to Kabo."""
    directory = Path(args.library)
    library, store = load_library(directory)
    posts = store["posts"]
    raw = read_json(args.file)
    if raw.get("confirmed") is not True:
        fail("The creator has not confirmed these pillars: write confirmed: true only after they agreed")
    pillars = raw.get("pillars")
    check_pillar_set(pillars, posts)
    old_ids = {pillar_key(row.get("name")): row["id"] for row in library.get("pillars") or []}
    taken, saved = set(), []
    for entry in pillars:
        local = old_ids.get(pillar_key(entry["name"])) or slug_of(entry["name"], taken | set(old_ids.values()))
        taken.add(local)
        saved.append({"id": local, "name": entry["name"].strip(), "definition": entry["definition"].strip(),
                      "search_phrases": [phrase.strip() for phrase in entry["search_phrases"]],
                      "source": "creator_declared"})
    keep = {row["id"] for row in saved}
    for post in posts.values():
        if post.get("pillar_id") not in (None, "other") and post["pillar_id"] not in keep:
            post["pillar_id"] = None
    by_name = {pillar_key(row["name"]): row["id"] for row in saved}
    for entry in pillars:
        for content_id in entry.get("content_ids") or []:
            posts[content_id]["pillar_id"] = by_name[pillar_key(entry["name"])]
    when = iso(now_utc())
    library.update({"pillars": saved, "pillars_source": "local_unsynced", "pillars_read_at": when,
                    "pillars_sync": {"state": "pending", "at": when}, "updated_at": when})
    write_json(directory / "library.json", library)
    write_json(directory / "posts.json", store)
    say({"saved": True, "pillars": [row["id"] for row in saved], "sync": "pending",
         "then": "sync to Kabo: get_creator_profile with pillars true, then declare-request and update_content_preferences"})


def cmd_declare_request(args):
    """The exact update_content_preferences arguments that save the library's pillars to Kabo (whole-set replace)."""
    library, _ = load_library(args.library)
    profile = read_profile(args.profile)
    context = profile["update_context"]
    if not context.get("account_id"):
        fail("The profile result names no account; read get_creator_profile for the linked account first")
    pillars = library.get("pillars") or []
    if library.get("pillars_source") not in ("local_unsynced", "kabo_declared"):
        fail("The library holds no pillars the creator declared; nothing to sync")
    say({"account_id": context["account_id"], "expected_version": context["expected_version"],
         "action": "declare_pillars",
         "pillars": [{"name": row["name"], "definition": row["definition"], "searchPhrases": row["search_phrases"]}
                     for row in pillars]})


SYNC_LINES = {
    "synced": "Your content pillars are saved in your Kabo account.",
    "failed": "Your content pillars are saved on this computer for now; I couldn't save them to your Kabo account yet.",
    "no_write_access": (" Kabo needs your permission to save to your account: reconnect Kabo in this app and approve "
                        "it, and I'll save them next time."),
}


def cmd_record_sync(args):
    """Record the update_content_preferences result: synced, retry once after a conflict, or still only local."""
    directory = Path(args.library)
    library, _ = load_library(directory)
    payload, is_error = tool_payload(read_json(args.result))
    when = iso(now_utc())
    text = json.dumps(payload, ensure_ascii=False).lower()
    if not is_error and isinstance(payload.get("effectiveContentProfile"), dict):
        library.update({"pillars_source": "kabo_declared", "pillars_sync": {"state": "synced", "at": when},
                        "updated_at": when})
        write_json(directory / "library.json", library)
        say({"sync": "synced", "tell_creator_now": SYNC_LINES["synced"]})
        return
    if ("conflict" in text or "preferences_changed" in text) and not args.retried:
        # Version conflict: re-read get_creator_profile to get the new version, then submit again (only once). It
        # replaces the whole set, so resubmitting does not accumulate.
        say({"sync": "conflict", "action": "reread_and_retry",
             "then": "read get_creator_profile again, rerun declare-request, call update_content_preferences once more, "
                     "then record-sync with --retried"})
        return
    reason = failure_detail(payload) or ("tool error" if is_error else "unexpected answer")
    library["pillars_sync"] = {"state": "pending", "at": when, "reason": reason[:300]}
    library["pillars_source"] = "local_unsynced"
    library["updated_at"] = when
    write_json(directory / "library.json", library)
    line = SYNC_LINES["failed"] + (SYNC_LINES["no_write_access"] if needs_write_access(payload, is_error) else "")
    say({"sync": "pending", "reason": reason[:300], "tell_creator_now": line})


def first_text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def slug_of(text, taken):
    base = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:30].strip("-") or "pillar"
    slug, number = base, 2
    while slug in taken:
        slug, number = f"{base}-{number}", number + 1
    return slug


def tool_payload(value):
    """The structured answer inside a saved MCP tool result, and whether the host marked it as an error.

    What the host saved may be the whole MCP result (structuredContent, or JSON only in content[0].text), or it may already be
    the structured content itself; all three are accepted."""
    if not isinstance(value, dict):
        return {}, False
    is_error = value.get("isError") is True
    if isinstance(value.get("structuredContent"), dict):
        return value["structuredContent"], is_error
    if isinstance(value.get("content"), list):
        text = next((part.get("text") for part in value["content"] if isinstance(part, dict) and isinstance(part.get("text"), str)), None)
        try:
            parsed = json.loads(text) if text is not None else None
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed, is_error
        return ({"message": text} if text else {}), is_error
    return value, is_error


def reference_line(name, count, share, multiple):
    """One plain line for the "What your numbers show" block, e.g. 'Hooks: 15 of your recent videos, about a third;
    they get about 1.8 times your usual views.' Avoids words like sample / baseline; the numbers are formatted here."""
    parts = []
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        parts.append(f"{count} of your recent videos" + (f", {share_words(share)}" if share_words(share) else ""))
    elif share_words(share):
        parts.append(f"{share_words(share)} of your recent videos")
    if times_words(multiple):
        parts.append(f"they get about {times_words(multiple)} times your usual views")
    return f"{name}: " + "; ".join(parts) + "." if parts else f"{name}."


def declared_pillars(structured):
    rows = structured.get("declaredPillars")
    if not isinstance(rows, list):
        return None
    out = []
    for row in rows:
        if not isinstance(row, dict) or not first_text(row.get("name")):
            continue
        phrases = [phrase.strip() for phrase in row.get("searchPhrases") or [] if isinstance(phrase, str) and phrase.strip()]
        out.append({"name": row["name"].strip(), "definition": first_text(row.get("definition")) or row["name"].strip(),
                    "search_phrases": phrases, "source": "creator_declared"})
    return out


def read_profile(path):
    """Niche and content pillars from the creator's Kabo profile (get_creator_profile with effective: true).

    Only organizes the signature content in the backend profile and does not derive anything separately from the posts; if the backend has none, there is none."""
    structured, is_error = tool_payload(read_json(path))
    if is_error:
        fail("get_creator_profile was refused: " + json.dumps(structured, ensure_ascii=False)[:300])
    effective = structured.get("effectiveContentProfile") if isinstance(structured.get("effectiveContentProfile"), dict) else None
    base = structured.get("contentProfile") if isinstance(structured.get("contentProfile"), dict) else None
    source = effective or base
    account = structured.get("account") if isinstance(structured.get("account"), dict) else {}
    diagnosis = structured.get("diagnosis") if isinstance(structured.get("diagnosis"), dict) else {}
    insight = diagnosis.get("insight") if isinstance(diagnosis.get("insight"), dict) else {}
    review = ((diagnosis.get("accountReview") or {}).get("sections") or {}).get("niche") or {}
    # Read the top-level niche first: the niche written by prepare_creator_profile's inference or the creator's
    # own words is here (where kabo get_creator_profile assembles
    # niche / nicheId); with no review diagnosis, diagnosis is empty (Codex measured @veritasium: top level
    # "Science education",
    # diagnosis has no niche). When the top level is empty, fall back to the two places in diagnosis.
    niche = (first_text(structured.get("niche")) or first_text(insight.get("niche"))
             or first_text(review.get("label")) or first_text(review.get("summary")))
    items = [item for item in ((source or {}).get("signatureContent") or []) if isinstance(item, dict)]
    items.sort(key=lambda item: -(item.get("share") if isinstance(item.get("share"), (int, float)) else 0))
    taken, candidates = set(), []
    for item in items[:MAX_PILLARS]:
        name = first_text(item.get("name"))
        if not name:
            continue
        slug = slug_of(name, taken)
        taken.add(slug)
        definition = " - ".join(part for part in (first_text(item.get("topic")), first_text(item.get("approach"))) if part)
        share = item.get("share") if isinstance(item.get("share"), (int, float)) else None
        candidates.append({
            "id": slug, "name": name[:60], "definition": (definition or name)[:300], "source": "kabo_profile",
            "profile_item_id": item.get("id"),
            # A merged item's (m_...) origin.baseIds lists the original items merged into it; a single item is itself.
            # When refreshing pillars, posts are assigned to the merged item accordingly.
            "profile_base_ids": [str(base) for base in ((item.get("origin") or {}).get("baseIds") or [item.get("id")])
                                 if isinstance(base, (str, int)) and str(base)],
            # The profile's share is a share of counts (contentCount / number of posts that entered a format), not a
            # share of views.
            "say_line": reference_line(name[:60], item.get("contentCount"), share, item.get("medianMultiplier")),
            "evidence": {"share_of_posts": share, "median_multiple": item.get("medianMultiplier"),
                         "content_count": item.get("contentCount"),
                         "examples": [{"url": row.get("sourceUrl"), "title": row.get("title"), "views": row.get("views"),
                                       "multiplier": row.get("multiplier")}
                                      for row in (item.get("representativeContent") or [])[:2] if isinstance(row, dict)]}})
    preferences = (effective or {}).get("preferences") if isinstance((effective or {}).get("preferences"), dict) else {}
    generated = ((effective or {}).get("base") or {}).get("generatedAt") if isinstance((effective or {}).get("base"), dict) else None
    advice = []
    status = (source or {}).get("signatureContentStatus")
    if status == "no_qualifying_group" and candidates:
        advice.append("Kabo's status no_qualifying_group means fewer than two groups cleared its bar. The one shown "
                      "did clear it (at least 3 comparable posts with a median above the account's typical views): "
                      "present it as a valid pillar.")
    return {"status": "ok" if candidates else "no_signature_content", "niche": niche, "advice": advice,
            "signature_status": status,
            "profile_edited": bool((effective or {}).get("edited")),
            "language": (source or {}).get("language", {}).get("primary") if isinstance((source or {}).get("language"), dict) else None,
            "candidates": candidates,
            "hidden_by_creator": [row.get("name") for row in (effective or {}).get("hiddenSignatureContent") or [] if isinstance(row, dict)],
            # Pillars declared by the creator (this key exists only when get_creator_profile is called with pillars:
            # true; when not requested or on an old backend it is None, which is not treated as "none").
            "declared_pillars": declared_pillars(structured),
            "update_context": {"account_id": account.get("id"), "expected_version": preferences.get("version") or 0,
                               "basis": first_text(generated or (base or {}).get("generatedAt"))},
            "note": None if candidates else ("Kabo has no content pillars for this account yet (too few comparable posts). "
                                             "Tell the creator so in one line and go on; never group the posts yourself.")}


def cmd_profile_pillars(args):
    say(read_profile(args.profile))


# ---------------------------------------------------------------- waiting on Kabo

# While the backend is still generating, re-query strictly per retry_after_seconds, neither shortening nor
# lengthening it; the total wait has a cap, whichever comes first.
# The host limits both a single command and the whole run, so waiting cannot be unbounded. The two caps
# follow the backend's real pace (kabo#2176):
# - Daily picks: the backend usually gives 120 seconds, and 300 seconds during profile fill. At most 3 more
# queries after the first, cumulative at most 600 seconds,
#   which exactly fits two 300-second profile-fill waits; scheduled runs use this cap too, and anything
# over the limit is delivered with the next run.
# - Profile: the backend uses a 60-second tier, and the whole chain of inferring the niche plus generating
# the profile takes several minutes. At most 8 more queries after the first, cumulative at most 480
# seconds;
#   over the limit, say to look again later and let the onboarding conversation continue.
# When the next wait would exceed the remaining budget, stop directly and do not query early (an early
# query would only get another generating).
POLL_LIMITS = {"for_you": {"max_retries": 3, "max_wait": 600, "default_wait": 120},
               "profile": {"max_retries": 8, "max_wait": 480, "default_wait": 60}}


def seconds(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def poll_decision(payload, attempt, waited, limits):
    """Whether to call the tool again after a `generating` answer, and how long to wait first."""
    if attempt < 1 or waited < 0:
        fail("--attempt starts at 1 and --waited at 0")
    wait = int(round(seconds(payload.get("retry_after_seconds")) or limits["default_wait"]))
    if attempt > limits["max_retries"] or waited + wait > limits["max_wait"]:
        return {"action": "stop", "waited_seconds": waited, "calls": attempt}
    return {"action": "wait", "wait_seconds": wait, "then": "call the same tool again with the same arguments",
            "next_flags": {"--attempt": attempt + 1, "--waited": waited + wait}}


# What is said to the creator while waiting: say it once on entering the wait, add at most one more
# sentence on the 3rd call (when the wait has clearly grown), at most two sentences in total.
# Other polls say nothing and explicitly tell the assistant with say_to_creator: false that nothing needs
# to be said this time (in a measured run the same sentence was sent 6 times).
STILL_WORKING = "Still working on it."


def wait_line(attempt, first):
    if attempt == 1:
        return first
    if attempt == 3:
        return STILL_WORKING
    return None


def status_of(payload, is_error):
    # Results the host marked isError (tool errors such as validation_error, not_found), with no status, or
    # with a non-string status
    # are all handled as failures, with the original content returned for reporting.
    status = payload.get("status")
    if is_error or not isinstance(status, str) or not status:
        return "failed"
    return status


def failure_detail(payload):
    # failure_code is a contract field; tool errors only have message / error, so read them leniently.
    return (first_text(payload.get("failure_code")) or first_text(payload.get("message"))
            or first_text(payload.get("error")))


def needs_write_access(payload, is_error):
    # When the host's Kabo authorization has no workspace:write, the write tool returns an Insufficient scope
    # tool error (not a status).
    # This is an authorization problem and retrying is useless: the creator must re-authorize in the host and
    # approve write permission.
    text = " ".join(str(payload.get(key) or "") for key in ("failure_code", "error", "message", "code")).lower()
    return is_error and ("insufficient_scope" in text or "insufficient scope" in text)


def about_time(value):
    """A cooldown in seconds as plain words for the creator ("about 3 hours"); None when there is none."""
    wait = seconds(value)
    if wait is None:
        return None
    if wait < 90 * 60:
        return f"about {max(1, round(wait / 60))} minutes"
    hours = round(wait / 3600)
    return f"about {hours} hour" + ("s" if hours != 1 else "")


def reported(payload):
    keys = ("status", "failure_code", "retryable", "retry_after_seconds", "reason", "error", "message")
    return {key: payload.get(key) for key in keys if key in payload} or payload


PROFILE_STATUS_LINES = {
    "first_wait": "Kabo is building your profile from your public videos. This usually takes a few minutes.",
    "gave_up": ("Your profile is not ready yet, so I can't show your content pillars now. I'll go on with the rest; "
                "ask me for your content pillars later."),
    "insufficient_posts": ("You don't have enough videos yet for Kabo to find your content pillars, so there are none for "
                           "now. I'll go on with the rest."),
    "niche_required": "Kabo can't tell your niche from your public videos yet.",
    "niche_question": "In one sentence, what is your content about?",
    "niche_still_required": ("Kabo still can't place your content, so there are no content pillars for now. "
                             "I'll go on with the rest."),
    "failed": "Kabo could not build your profile this time, so I can't show your content pillars now. I'll go on with the rest.",
    "retry_in": "You can ask for your content pillars again in {when}.",
    "retrying": "Kabo didn't finish organizing your profile this time and is trying again.",
    "classification_unavailable": ("Kabo read your videos but couldn't sort them into content pillars this time; "
                                   "it is trying again."),
    "needs_write_access": ("Kabo needs your permission to save to your account, and this app hasn't given it yet. "
                           "Reconnect Kabo in this app and approve it, then tell me to try again."),
    "no_write_access": ("Without that permission I can't save your content pillars to Kabo for now. I'll go on with "
                        "the rest; today's picks don't need it."),
}


def cmd_profile_status(args):
    """What to do with a saved prepare_creator_profile result: read the profile, wait, ask the niche, or go on without it."""
    payload, is_error = tool_payload(read_json(args.result))
    status = status_of(payload, is_error)
    result = {"status": status}
    if status == "failed" and needs_write_access(payload, is_error):
        if args.write_retried:
            result.update({"action": "continue_without_profile", "reason": "insufficient_scope",
                           "tell_creator_now": PROFILE_STATUS_LINES["no_write_access"], "reported": reported(payload)})
        else:
            result.update({"action": "ask_write_access", "reason": "insufficient_scope",
                           "tell_creator_now": PROFILE_STATUS_LINES["needs_write_access"],
                           "then": "if the creator says they approved it, call prepare_creator_profile again with the same "
                                   "arguments and run profile-status with --attempt 1 --waited 0 --write-retried; if they "
                                   "do not, send no_write_access_line and go on without a profile",
                           "no_write_access_line": PROFILE_STATUS_LINES["no_write_access"], "reported": reported(payload)})
    elif status == "ready":
        result.update({"action": "read_profile",
                       "then": "call get_creator_profile with include content_profile and effective true"})
    elif status == "generating":
        decision = poll_decision(payload, args.attempt, args.waited, POLL_LIMITS["profile"])
        result.update(decision)
        if decision["action"] == "wait":
            line = wait_line(args.attempt, PROFILE_STATUS_LINES["first_wait"])
            result.update({"tell_creator_now": line} if line else {"say_to_creator": False})
        else:
            result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["gave_up"]})
    elif status == "niche_required" and not args.niche_sent:
        # The backend cannot infer a niche from public content: ask the creator one sentence and retry once with
        # their own words as niche. The model must not make one up for the creator.
        result.update({"action": "ask_niche", "tell_creator_now": PROFILE_STATUS_LINES["niche_required"],
                       # niche_not_inferred, or an analyzer error code (such as profile_private); explanation only, does not
                       # change the flow.
                       "failure_code": failure_detail(payload),
                       "question": PROFILE_STATUS_LINES["niche_question"],
                       "then": "call prepare_creator_profile again with the same account_id and niche set to the "
                               "creator's own words, then run profile-status with --attempt 1 --waited 0 --niche-sent"})
    elif status == "niche_required":
        result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["niche_still_required"],
                       "failure_code": failure_detail(payload)})
    elif status == "insufficient_posts":
        result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["insufficient_posts"],
                       "retry_after_seconds": seconds(payload.get("retry_after_seconds"))})
    elif status == "failed" and not is_error and payload.get("retryable") is True:
        # Occasional execution failure (kabo#2180): retry_after_seconds is very short, and calling the same tool
        # again at that time makes the backend rerun the review automatically and return generating.
        # Such retries share the same polling cap as generating (at most 8 more queries, total wait 480 seconds);
        # the backend reruns at most 2 times within 24 hours,
        # and returns retryable=false at the limit. Do not describe it as "not enough posts".
        code = failure_detail(payload)
        decision = poll_decision(payload, args.attempt, args.waited, POLL_LIMITS["profile"])
        result.update(decision)
        result["failure_code"] = code
        if decision["action"] == "wait":
            # The failure code goes only in the failure_code field for the assistant, not into what is said to the
            # creator.
            line = PROFILE_STATUS_LINES["classification_unavailable"] if code == "classification_unavailable" else (
                PROFILE_STATUS_LINES["retrying"])
            result["tell_creator_now"] = line
        else:
            result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["gave_up"],
                           "reported": reported(payload)})
    else:
        # failed (retryable=false or a tool error) and any status outside the contract: handled as failure,
        # returned as is, with no self-derived profile;
        # if there is a cooldown, say roughly how long until a retry is possible.
        line = PROFILE_STATUS_LINES["failed"]
        when = about_time(payload.get("retry_after_seconds"))
        if when:
            line += " " + PROFILE_STATUS_LINES["retry_in"].format(when=when)
        result.update({"action": "continue_without_profile", "tell_creator_now": line, "retry_in": when,
                       "failure_code": failure_detail(payload), "reported": reported(payload)})
    say(result)


def cmd_bootstrap(args):
    """A new library built by review-new-posts when none exists: pillars, if any, come from the creator's Kabo profile.

    The first run (onboarding no longer builds the library locally) and every run on a host that keeps no files go through here. With no profile or a profile with no pillars, the library is still built,
    and the review and account recap still run, just without the pillar section."""
    directory = Path(args.library)
    if (directory / "library.json").exists():
        fail("This library already exists; use it instead of rebuilding it")
    proposal = read_profile(args.profile) if args.profile else None
    # Same priority as refresh-pillars: pillars declared by the creator -> signature content from backend
    # statistics -> none.
    declared = (proposal or {}).get("declared_pillars") or []
    candidates = declared or (proposal or {}).get("candidates") or []
    handle, when = normalize_handle(args.handle), now_utc()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reviews").mkdir(exist_ok=True)
    taken = set()
    pillars = []
    for row in candidates:
        local = row.get("id") or slug_of(row["name"], taken)
        taken.add(local)
        pillars.append(pillar_record({**row, "id": local}))
    niche = (proposal or {}).get("niche")
    language = (proposal or {}).get("language")
    # Look back 48 hours: on the first history read, the binding time is set from that read's fetch time, so
    # each post enters the review exactly once on its day in the 24-48 hour band.
    # fresh means the library still holds only this one reading; the next time history is read on the same
    # library, ingest sets it to false.
    write_json(directory / "library.json", {
        "format": LIBRARY_FORMAT, "platform": args.platform, "handle": handle, "creator_id": None,
        "bound_at": None, "lookback_hours": 48, "fresh": True,
        "niche": {"text": niche, "source": "kabo_profile"} if niche else None, "pillars": pillars,
        "pillars_read_at": iso(when) if pillars else None,
        "pillars_source": ("kabo_declared" if declared else "kabo_profile") if pillars else None,
        **({"pillars_sync": {"state": "synced", "at": iso(when)}} if declared else {}),
        "pillars_refresh": {"ok": proposal is not None, "at": iso(when),
                            **({} if proposal is not None else {"reason": "no profile result"})},
        "followers": [], "profile": {"language": language} if language else {},
        "updated_at": iso(when)})
    write_json(directory / "posts.json", {"posts": {}})
    result = {"library": str(directory), "fresh": True, "pillars": [row["id"] for row in pillars],
              "limit": FIRST_READING_LINE}
    if not pillars:
        result["note"] = ("No content pillars from Kabo for this account, so the reviews and the recap have no pillar "
                          "section. Do not make pillars up.")
    say(result)


PILLAR_KEYS = ("id", "name", "definition", "search_phrases", "source", "profile_item_id", "profile_base_ids", "evidence")


def pillar_record(row):
    return {key: row[key] for key in PILLAR_KEYS if key in row}


def align_pillars(old_pillars, candidates):
    """New local pillars from Kabo's profile, and where each old local pillar id now goes (None: unassigned).

    Alignment rules (the backend profile is authoritative; match only by the profile item's stable id, never by name):
    1. Profile item id unchanged (even if renamed or its topic changed): keep the original local id; post assignments do not move.
    2. Original item merged: the new merged item (m_...) has origin.baseIds containing the original item id, and the original item's posts go to the merged item.
    3. Original item deleted, hidden, or dropped out of the top 4, or an original merged item split (the correspondence is not unique): posts become unassigned (pillar_id empty).
    Historical readings and recorded reviews are untouched; "other" assignments stay."""
    by_item = {str(row.get("profile_item_id")): row for row in old_pillars if row.get("profile_item_id")}
    taken, pillars, moves = set(), [], {}
    # First keep the original local id for items whose id is unchanged, then derive ids for new items from
    # their names, to avoid name collisions.
    kept = {}
    for row in candidates:
        old = by_item.get(str(row.get("profile_item_id")))
        if old:
            kept[id(row)] = old["id"]
            taken.add(old["id"])
    for row in candidates:
        local = kept.get(id(row)) or slug_of(row["name"], taken)
        taken.add(local)
        pillars.append(pillar_record({**row, "id": local}))
    for old in old_pillars:
        item = str(old.get("profile_item_id") or "")
        target = next((new["id"] for new in pillars if item and new.get("profile_item_id") == item), None)
        if target is None and item:
            target = next((new["id"] for new in pillars if item in (new.get("profile_base_ids") or [])), None)
        moves[old["id"]] = target
    return pillars, moves


def align_declared(old_pillars, declared):
    """Declared pillars have no stable id: match by name, ignoring case. A renamed pillar's posts become unassigned.

    Declared pillars have no backend id and are matched only by name (case-insensitive, leading/trailing whitespace stripped); if the name changes they become unassigned, with no fuzzy matching."""
    by_name = {pillar_key(row.get("name")): row["id"] for row in old_pillars}
    taken, pillars = set(), []
    for row in declared:
        local = by_name.get(pillar_key(row["name"]))
        if local in taken:
            local = None
        local = local or slug_of(row["name"], taken | set(by_name.values()))
        taken.add(local)
        pillars.append({"id": local, **{key: row[key] for key in ("name", "definition", "search_phrases", "source")}})
    names = {pillar_key(row["name"]): row["id"] for row in pillars}
    moves = {row["id"]: names.get(pillar_key(row.get("name"))) for row in old_pillars}
    return pillars, moves


def cmd_refresh_pillars(args):
    """Refresh the library's niche and pillars from this run's get_creator_profile result (Kabo's profile wins)."""
    directory = Path(args.library)
    library, store = load_library(directory)
    when = iso(now_utc())
    proposal, problem = None, args.unavailable
    if args.profile and not problem:
        try:
            proposal = read_profile(args.profile)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            problem = str(error)[:300]
    if proposal is None:
        # Profile unreadable: keep the previous pillars, explain in the limits of the review and recap, and do not
        # let the whole review fail.
        library["pillars_refresh"] = {"ok": False, "at": when, "reason": problem or "no profile result"}
        write_json(directory / "library.json", library)
        say({"refreshed": False, "reason": library["pillars_refresh"]["reason"],
             "pillars": [row["id"] for row in library.get("pillars") or []], "pillars_read_at": library.get("pillars_read_at")})
        return
    old = library.get("pillars") or []
    sync = library.get("pillars_sync") or {}
    if sync.get("state") == "pending":
        # Local pillars confirmed by the creator but not yet synced to Kabo: do not overwrite them with the backend
        # result, only fill in the niche; once the catch-up sync succeeds, the backend is authoritative again.
        niche = proposal.get("niche")
        if niche:
            library["niche"] = {"text": niche, "source": "kabo_profile"}
        library.update({"pillars_refresh": {"ok": True, "at": when}, "updated_at": when})
        write_json(directory / "library.json", library)
        say({"refreshed": False, "reason": "local pillars not yet synced to Kabo; kept as they are",
             "pillars": [row["id"] for row in old], "sync": "pending"})
        return
    # Priority of pillar sources: declared by the creator (declaredPillars non-empty) -> signature content from
    # backend statistics -> none.
    declared = proposal.get("declared_pillars")
    if declared:
        pillars, moves = align_declared(old, declared)
        source = "kabo_declared"
    else:
        pillars, moves = align_pillars(old, proposal["candidates"])
        source = "kabo_profile" if pillars else None
    moved = {"kept": 0, "moved": 0, "unassigned": 0}
    for post in store.get("posts", {}).values():
        current = post.get("pillar_id")
        if current in (None, "other") or current not in moves:
            continue
        target = moves[current]
        if target == current:
            moved["kept"] += 1
        elif target:
            moved["moved"] += 1
        else:
            moved["unassigned"] += 1
        post["pillar_id"] = target
    niche = proposal.get("niche")
    library.update({"niche": {"text": niche, "source": "kabo_profile"} if niche else None, "pillars": pillars,
                    "pillars_read_at": when, "pillars_source": source,
                    "pillars_refresh": {"ok": True, "at": when}, "updated_at": when})
    if source == "kabo_declared":
        library["pillars_sync"] = {"state": "synced", "at": (library.get("pillars_sync") or {}).get("at") or when}
    if proposal.get("language"):
        library.setdefault("profile", {})["language"] = proposal["language"]
    write_json(directory / "library.json", library)
    write_json(directory / "posts.json", store)
    say({"refreshed": True, "pillars": [row["id"] for row in pillars], "posts": moved,
         "pillar_moves": {old_id: target for old_id, target in moves.items() if target != old_id}})


# Text that is written into the review and recap and relayed to the creator: it must not contain words like
# library, run, host.
AGE_WORDS = {"1h": "1 hour", "24h": "24 hours", "7d": "7 days"}
FIRST_READING_LINE = ("This is the first time I've read your account here, so there is no earlier reading to compare "
                      "with yet (no follower change either). If this app doesn't keep files between days, every report "
                      "starts like this, and a post may be reviewed again.")


def pillar_refresh_limit(library):
    state = library.get("pillars_refresh") or {}
    # What is said to the creator: the reason (state["reason"]) stays in the library for the assistant to
    # troubleshoot and is not read out.
    if state.get("ok") is False:
        if library.get("pillars"):
            day = str(library.get("pillars_read_at") or "")[:10]
            return "I couldn't get your latest content pillars from Kabo today, so this uses the ones from " + (day or "last time") + "."
        return "I couldn't get your content pillars from Kabo today."
    return None


def cmd_set_pillar(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    known = {pillar["id"] for pillar in library.get("pillars") or []}
    if args.pillar_id not in known | {"other"}:
        fail("Pillar id must be one of the library's pillars or 'other'")
    post = store["posts"].get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    post["pillar_id"] = args.pillar_id
    write_json(directory / "posts.json", store)
    say({"content_id": args.content_id, "pillar_id": args.pillar_id})


def cmd_show(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    picks = read_picks(Path(args.library))
    tracked = [post for post in posts.values() if post.get("tracked")]
    followers = library.get("followers") or []
    say({"platform": library["platform"], "handle": library["handle"], "bound_at": library["bound_at"],
         "fresh": bool(library.get("fresh")), "niche": library.get("niche"),
         "pillars": library.get("pillars"), "pillars_source": library.get("pillars_source"),
         "pillars_read_at": library.get("pillars_read_at"), "pillars_refresh": library.get("pillars_refresh"),
         "pillars_sync": library.get("pillars_sync"),
         "profile": library.get("profile"), "posts_in_library": len(posts),
         "typical_settled_views": median([v for _, v in settled_views(posts)]),
         "followers_now": followers[-1] if followers else None,
         "tracked_posts": len(tracked), "reviews_done": sum(len(post.get("reviews") or {}) for post in tracked),
         "pick_days": sorted(picks["days"])[-7:]})


# ---------------------------------------------------------------- reviews

def due_reviews(posts, optional=False):
    """Reviews to make now. 24 h by default; 1 h and 7 d only with optional=True."""
    rows = []
    for post in posts.values():
        if not post.get("tracked"):
            continue
        last = latest(post)
        age = last.get("age_hours") if last else None
        if age is None:
            continue
        done = post.get("reviews") or {}
        wanted = []
        if "24h" not in done and age >= CHECKPOINTS["24h"][0]:
            wanted.append("24h")
        if optional:
            if "1h" not in done and "24h" not in done and CHECKPOINTS["1h"][0] <= age < CHECKPOINTS["24h"][0]:
                wanted.append("1h")
            if "7d" not in done and age >= CHECKPOINTS["7d"][0]:
                wanted.append("7d")
        for name in wanted:
            rows.append({"content_id": post["content_id"], "checkpoint": name, "age_hours": age,
                         "late": name == "24h" and age >= LATE_AFTER_HOURS,
                         "age_from": last.get("age_from"), "url": post.get("url")})
    rows.sort(key=lambda row: -row["age_hours"])
    return rows


def cmd_due(args):
    _, store = load_library(args.library)
    say({"due": due_reviews(store["posts"], args.with_optional)})


def band_observation(post, name):
    low, high = CHECKPOINTS[name]
    for row in post.get("observations") or []:
        age = row.get("age_hours")
        if age is not None and low <= age < high and row.get("views") is not None:
            return row
    return None


def engagement(row):
    views = row.get("views")
    if not views:
        return None
    parts = [row.get(name) for name in ("likes", "comments", "shares", "saves") if row.get(name) is not None]
    return round(sum(parts) / views, 4) if parts else None


def cmd_review_facts(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    post = posts.get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    last = latest(post) or fail("This post has no observation yet")
    others = [other for cid, other in posts.items() if cid != args.content_id]
    same_age = [(other, band_observation(other, args.checkpoint)) for other in others]
    same_age = [(other, row) for other, row in same_age if row]
    same_age_median = median([row["views"] for _, row in same_age])
    at_mark = band_observation(post, args.checkpoint)
    settled = [(other, views) for other, views in settled_views(posts) if other["content_id"] != args.content_id]
    typical = median([views for _, views in settled])
    typical_engagement = median([engagement(latest(other)) for other, _ in settled])
    previous = None
    for row in reversed(post["observations"][:-1]):
        if row.get("views") is not None and row.get("age_hours") is not None:
            previous = row
            break
    pace = None
    if previous and last.get("views") is not None and last["age_hours"] > previous["age_hours"]:
        pace = round((last["views"] - previous["views"]) / (last["age_hours"] - previous["age_hours"]), 1)
    pillar_rows = [(other, views) for other, views in settled
                   if post.get("pillar_id") and other.get("pillar_id") == post.get("pillar_id")]
    comparable = bool(at_mark) and len(same_age) >= 3
    facts = {
        "content_id": post["content_id"], "url": post.get("url"), "title": post.get("title"),
        "checkpoint": args.checkpoint, "age_hours": last.get("age_hours"), "age_from": last.get("age_from"),
        "observed_at": last["observed_at"], "metrics": {name: last.get(name) for name in METRICS},
        "metrics_at_checkpoint": ({name: at_mark.get(name) for name in METRICS} | {"age_hours": at_mark["age_hours"]}
                                  if at_mark else None),
        "engagement_rate": engagement(last), "pillar_id": post.get("pillar_id"),
        "same_age_baseline": {"posts": len(same_age), "median_views": same_age_median,
                              "multiple": ratio(at_mark["views"], same_age_median) if comparable else None},
        "typical_settled": {"posts": len(settled), "median_views": typical,
                            "share_reached": ratio(last.get("views"), typical),
                            "median_engagement_rate": typical_engagement},
        "pillar_settled": {"posts": len(pillar_rows), "median_views": median([v for _, v in pillar_rows])},
        "views_per_hour_since_previous_check": pace,
        "limits": [],
    }
    if len(same_age) < 3:
        facts["limits"].append(f"Fewer than 3 of your earlier posts were checked at {AGE_WORDS[args.checkpoint]} old, "
                               "so this compares with the total views of your posts that are at least 3 days old, "
                               "not with posts at the same age.")
    elif not at_mark:
        facts["limits"].append(f"This post was first checked after it was {AGE_WORDS[args.checkpoint]} old, so it "
                               "can't be compared with your other posts at the same age; this review is late.")
    if args.checkpoint == "24h" and last.get("age_hours", 0) >= LATE_AFTER_HOURS:
        facts["limits"].append("This review is late: the post is already past 48 hours old.")
    if last.get("age_from") == "first_seen":
        facts["limits"].append("The platform shows only the day this was posted, not the time, so its age is counted "
                               "from when I first saw it and can be up to a day off.")
    if last.get("views") is None:
        facts["limits"].append("The platform does not show this post's views publicly.")
    if pillar_refresh_limit(library):
        facts["limits"].append(pillar_refresh_limit(library))
    if library.get("fresh"):
        facts["limits"].append(FIRST_READING_LINE)
    say(facts)


def cmd_record_review(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    post = store["posts"].get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    if args.checkpoint in (post.get("reviews") or {}):
        fail(f"The {args.checkpoint} review of {args.content_id} is already recorded")
    report = Path(args.report).resolve()
    if not report.is_file() or report.stat().st_size == 0:
        fail("--report must be the written review file")
    target = directory / "reviews" / f"{args.content_id}-{args.checkpoint}.md"
    target.parent.mkdir(exist_ok=True)
    if report != target.resolve():
        target.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    last = latest(post)
    post.setdefault("reviews", {})[args.checkpoint] = {
        "recorded_at": iso(now_utc()), "observed_at": last["observed_at"], "age_hours": last.get("age_hours"),
        "views": last.get("views"), "report": str(target.relative_to(directory)),
    }
    write_json(directory / "posts.json", store)
    say({"recorded": args.checkpoint, "content_id": args.content_id, "report": str(target)})


# ---------------------------------------------------------------- account recap

def cmd_recap(args):
    """Facts for the daily account recap: followers, the last 7 days against typical, each pillar."""
    library, store = load_library(args.library)
    posts = store["posts"]
    day = args.date or now_utc().date().isoformat()
    settled = settled_views(posts)
    typical = median([views for _, views in settled])
    total = sum(views for _, views in settled)
    limits = []
    if pillar_refresh_limit(library):
        limits.append(pillar_refresh_limit(library))
    if library.get("fresh"):
        limits.append(FIRST_READING_LINE)
    readings = library.get("followers") or []
    followers = {"available": False, "now": readings[-1]["value"] if readings else None}
    if len(readings) >= 2:
        newest = parse_time(readings[-1]["observed_at"])
        # Take the most recent reading from at least a day earlier for comparison; if there is no reading a full
        # day old, take the earliest one and state the interval.
        older = [row for row in readings[:-1] if (newest - parse_time(row["observed_at"])) >= timedelta(hours=20)]
        base = older[-1] if older else readings[0]
        gap_hours = round((newest - parse_time(base["observed_at"])).total_seconds() / 3600, 1)
        followers.update({"available": True, "previous": base["value"], "change": readings[-1]["value"] - base["value"],
                          "since_hours": gap_hours})
    else:
        limits.append("Only one follower reading exists, so there is no follower change yet.")
    recent, gathering = [], 0
    for post in posts.values():
        last = latest(post)
        if not last or last.get("age_hours") is None or last["age_hours"] > 168:
            continue
        recent.append(post_row(post, typical))
        if last["age_hours"] < SETTLED_HOURS:
            gathering += 1
    recent.sort(key=lambda row: row["published_at"] or "", reverse=True)
    recent_settled = [row["views"] for row in recent if (row["age_hours"] or 0) >= SETTLED_HOURS and row["views"] is not None]
    as_of = parse_time(library.get("updated_at"))
    pillar_rows = []
    for pillar in library.get("pillars") or []:
        members = [post for post in posts.values() if post.get("pillar_id") == pillar["id"]]
        mine = sorted(((post, views) for post, views in settled if post.get("pillar_id") == pillar["id"]),
                      key=lambda row: row[0].get("published_at") or "")
        views = [row[1] for row in mine]
        dated = sorted(post["published_at"] for post in members if post.get("published_at"))
        newest = parse_time(dated[-1]) if dated else None
        recent_three = [row[1] for row in mine[-3:]]
        earlier = [row[1] for row in mine[:-3]]
        pillar_rows.append({
            "id": pillar["id"], "name": pillar["name"], "posts": len(members), "settled_posts": len(views),
            "median_views": median(views), "median_multiple": ratio(median(views), typical),
            "view_share": round(sum(views) / total, 3) if total and views else None,
            "posts_last_7_days": sum(1 for post in members if (latest(post) or {}).get("age_hours") is not None
                                     and latest(post)["age_hours"] <= 168),
            "days_since_last_post": round((as_of - newest).total_seconds() / 86400, 1) if newest and as_of else None,
            "latest_three_median_views": median(recent_three) if len(recent_three) == 3 else None,
            "earlier_median_views": median(earlier) if len(earlier) >= 3 else None})
    if not library.get("pillars"):
        limits.append("You have no content pillars saved yet, so there is no section per pillar.")
    unassigned = sum(1 for row in recent if not row["pillar_id"])
    say({"date": day, "handle": library["handle"], "platform": library["platform"], "followers": followers,
         "typical_settled_views": typical, "settled_posts": len(settled),
         "last_7_days": {"posts": recent, "count": len(recent), "still_gathering_views": gathering,
                         "settled_median_views": median(recent_settled),
                         "settled_median_multiple": ratio(median(recent_settled), typical)},
         "pillars": pillar_rows, "recent_posts_without_pillar": unassigned, "limits": limits})


def cmd_record_recap(args):
    directory = Path(args.library)
    load_library(directory)
    report = Path(args.report).resolve()
    if not report.is_file() or report.stat().st_size == 0:
        fail("--report must be the written recap file")
    day = args.date or now_utc().date().isoformat()
    target = directory / "recaps" / f"{day}.md"
    target.parent.mkdir(exist_ok=True)
    if report != target.resolve():
        target.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    say({"recorded": day, "report": str(target)})


# ---------------------------------------------------------------- evidence text

def rows_of(envelope):
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if isinstance(data, dict):
        for key in ("rows", "comments", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def text_of(row):
    for path in (("text",), ("comment", "text"), ("snippet", "textDisplay"), ("snippet", "textOriginal"),
                 ("snippet", "topLevelComment", "snippet", "textOriginal"), ("node", "text")):
        value = row
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def likes_of(row):
    for key in ("like_count", "digg_count", "likes", "comment_like_count"):
        if isinstance(row.get(key), (int, float)):
            return row[key]
    snippet = row.get("snippet") if isinstance(row.get("snippet"), dict) else {}
    top = ((snippet.get("topLevelComment") or {}).get("snippet") or {}) if isinstance(snippet, dict) else {}
    value = top.get("likeCount", snippet.get("likeCount"))
    return value if isinstance(value, (int, float)) else None


def cmd_comments(args):
    envelope = read_json(args.envelope)
    rows = []
    for row in rows_of(envelope):
        if isinstance(row, dict) and text_of(row):
            rows.append({"text": text_of(row)[:400], "likes": likes_of(row)})
    rows.sort(key=lambda row: -(row["likes"] or 0))
    say({"status": envelope.get("status"), "comments": rows[: args.limit], "total_read": len(rows)})


def cmd_evidence(args):
    """Staged evidence files in staging order, with the tool that produced each one."""
    directory = Path(args.dir)
    rows = []
    # File names start with the staging time, so sorting by name gives call order.
    for meta_path in sorted(directory.glob("*.meta")):
        body = meta_path.with_suffix(".json")
        if not body.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if args.tool and meta.get("tool") != args.tool:
            continue
        rows.append({"file": str(body), "tool": meta.get("tool"), "operation": meta.get("operation"),
                     "schema_version": meta.get("schema_version")})
    say({"evidence": rows})


# ---------------------------------------------------------------- daily picks

def remake_note(platform):
    # Remake accepts only talking-head or voice-over videos under 10 minutes; backend picks give no duration,
    # and whether one qualifies is checked by remake itself before charging, so nothing is guessed here.
    if platform is None or platform in ("instagram", "youtube", "tiktok"):
        return "checked first: before a remake, Kabo checks whether this video qualifies"
    return "not supported for this platform"


# Daily picks take only the get_for_you_videos result from the backend: the backend filters by "same field
# as the account, matching language" and sorts by public views,
# and the backend decides the rules. Only display limits are applied here: at most 3 per day; 7 days first,
# then 30 days, then 24 hours; skip those shown on an earlier day,
# the creator's own, and the same author as one already chosen; if there are not enough, give as many as
# there are and never pad.
PICK_WINDOWS = ("7d", "30d", "24h")
PICKS_PER_DAY = 3
# Per-window relative views threshold: anything below 10% of that window's #1 views is not selected, and
# neither is anything without views.
# The backend sorts by views, but often only the top entry in a window truly broke out (measured YouTube
# 7d: 63,831 followed by 1,266, 1,240),
# and taking the first 3 by rank would recommend videos that clearly did not take off. Use only the views
# the backend gives and do not introduce bases the backend lacks, such as a multiple of the author's
# baseline;
# each window computes its threshold from its own top entry, including when filling in. If fewer than 3
# pass the threshold, do not pad.
VIEWS_FLOOR_SHARE = 0.10

FOR_YOU_NOT_ELIGIBLE = {
    "no_linked_account": "No account is linked in Kabo yet, so there are no picks. Ask me to get you started to link one.",
    "no_public_videos": "Kabo found no public videos on your account yet, so it can't pick videos in your niche. Picks start once you have posted.",
    "profile_insufficient": "Kabo doesn't know your niche well enough yet to pick videos for you; it needs more of your posts.",
    "language_unknown": "Kabo couldn't tell which language your videos are in, so it can't match picks to your audience yet.",
    "unavailable": "Daily picks are not available for this account yet.",
}


def read_picks(directory):
    value = read_json(Path(directory) / "picks.json", {"days": {}})
    days = value.get("days") if isinstance(value, dict) and isinstance(value.get("days"), dict) else {}
    return {"days": {day: [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
                     for day, rows in days.items()}}


# The query parameter in a link that identifies the video: a YouTube watch link is distinguished only by
# ?v=. Other query parameters (igsh, si, utm_...) are share tracking and are removed.
# Previously the whole query string was dropped, so all youtube.com/watch?v=... links were treated as the
# same video (Codex measured: only 1 selected out of 30).
URL_ID_PARAMS = ("v",)


def normalize_url(raw):
    text = first_text(raw)
    if not text:
        return None
    parts = urllib.parse.urlsplit(text)
    host = (parts.hostname or "").lower()
    if host.startswith("www.") or host.startswith("m."):
        host = host.split(".", 1)[1]
    path = parts.path.rstrip("/")
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query) if key in URL_ID_PARAMS and value]
    if not host:
        return text
    return f"{host}{path}" + (("?" + urllib.parse.urlencode(sorted(query))) if query else "")


def video_keys(item):
    """Every key that identifies one video; empty values never become keys."""
    keys = set()
    content_id = item.get("content_id")
    if isinstance(content_id, (str, int)) and not isinstance(content_id, bool) and str(content_id).strip():
        keys.add("id:" + str(content_id).strip())
    url = normalize_url(item.get("url"))
    if url:
        keys.add("url:" + url)
    for key in item.get("keys") or []:  # Recorded picks carry their own keys
        if isinstance(key, str) and key.strip():
            keys.add(key.strip())
    return keys


def platform_of(item):
    # When platform is missing, infer it from the link domain; if it cannot be inferred it is None (the remake
    # hint falls back to "will check before remaking").
    named = (first_text(item.get("platform")) or "").lower()
    if named:
        return named
    host = (urllib.parse.urlsplit(first_text(item.get("url")) or "").hostname or "").lower()
    for platform, hosts in (("instagram", ("instagram.com",)), ("tiktok", ("tiktok.com",)),
                            ("youtube", ("youtube.com", "youtu.be"))):
        if any(host == name or host.endswith("." + name) for name in hosts):
            return platform
    return None


def author_of(item):
    """The key that says two picks share an author: author_id first, then author_handle; None when neither is given.

    An unknown author (null or empty string) does not take part in "no repeated author": YouTube results currently give no author_handle,
    and treating empty values as the same author would leave only one pick. If the backend adds author_id, it takes priority."""
    author_id = item.get("author_id")
    if isinstance(author_id, (str, int)) and not isinstance(author_id, bool) and str(author_id).strip():
        return "id:" + str(author_id).strip()
    handle = first_text(item.get("author_handle"))
    handle = handle.lstrip("@").lower() if handle else None
    return "handle:" + handle if handle else None


def author_label(item):
    """The author as the creator should see it: a channel name for YouTube, @handle elsewhere.

    Since kabo#2181 the YouTube author_handle is the channel name (the video endpoint gives no @handle, and names can collide), so no @ is added;
    Instagram / TikTok use the platform handle, with @ added. The script supplies this, so the model need not decide whether to add @."""
    handle = first_text(item.get("author_handle"))
    if not handle:
        return "author not supplied"
    if platform_of(item) == "youtube":
        return handle
    return "@" + handle.lstrip("@")


def own_handle_of(item):
    # The backend already excludes the creator's own posts; this only re-checks when an author name is given.
    # When the author is unknown, no judgment is made.
    handle = first_text(item.get("author_handle"))
    if not handle:
        return None
    return handle.lstrip("@").lower() or None


def window_items(payload, name):
    windows = payload.get("windows") if isinstance(payload.get("windows"), dict) else {}
    rows = windows.get(name)
    if isinstance(rows, dict) and isinstance(rows.get("items"), list):
        rows = rows["items"]
    rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def order(pair):
        index, row = pair
        rank = row.get("rank")
        ranked = isinstance(rank, (int, float)) and not isinstance(rank, bool)
        return (0, rank, index) if ranked else (1, 0, index)
    return [row for _, row in sorted(enumerate(rows), key=order)]


def select_picks(payload, shown, own_handle, count):
    """Up to `count` picks: 7d by Kabo's rank first, then 30d, then 24h; never padded."""
    chosen, used_keys, authors = [], set(), set()
    skipped = {"shown_on_earlier_day": 0, "own_post": 0, "same_author": 0, "same_video_in_another_window": 0,
               "no_link": 0, "below_views_floor": 0}
    sizes, floors = {}, {}
    for window in PICK_WINDOWS:
        rows = window_items(payload, window)
        sizes[window] = len(rows)
        counted = [row["views"] for row in rows if seconds(row.get("views")) is not None]
        top = max(counted) if counted else None
        floor = top * VIEWS_FLOOR_SHARE if top is not None else None
        floors[window] = {"top_views": top, "min_views": int(-(-floor // 1)) if floor is not None else None}
        for row in rows:
            if len(chosen) >= count:
                break
            keys = video_keys(row)
            author = author_of(row)
            views = row.get("views")
            if not normalize_url(row.get("url")):
                skipped["no_link"] += 1
            elif seconds(views) is None or views < floor:
                skipped["below_views_floor"] += 1
            elif keys & used_keys:
                # The same video (same content_id or same normalized link) appearing in several time windows; look only at
                # the video identifier, not the author.
                skipped["same_video_in_another_window"] += 1
            elif keys & shown:
                skipped["shown_on_earlier_day"] += 1
            elif own_handle and own_handle_of(row) == own_handle:
                skipped["own_post"] += 1
            elif author and author in authors:
                skipped["same_author"] += 1
            else:
                used_keys |= keys
                if author:
                    authors.add(author)
                views = row.get("views")
                chosen.append({
                    "window": window, "rank": row.get("rank"),
                    "views": views if isinstance(views, (int, float)) and not isinstance(views, bool) else None,
                    "reason": first_text(row.get("reason")), "url": first_text(row.get("url")),
                    "platform": platform_of(row), "format": first_text(row.get("format")),
                    "title": (first_text(row.get("title")) or first_text(row.get("caption")) or "")[:300],
                    "author": author_label(row), "author_handle": first_text(row.get("author_handle")),
                    "author_id": str(row["author_id"]) if row.get("author_id") not in (None, "") else None,
                    "published_at": first_text(row.get("published_at")),
                    "content_id": str(row["content_id"]) if row.get("content_id") not in (None, "") else None,
                    "remake": remake_note(platform_of(row)),
                    "keys": sorted(keys)})
    return chosen, skipped, sizes, floors


def cmd_for_you(args):
    """Today's picks from a saved get_for_you_videos result; records the day once the result is ready."""
    directory = Path(args.library)
    day = args.date or now_utc().date().isoformat()
    history = read_picks(directory)
    if day in history["days"]:
        # Running again the same day (scheduled-task retry, manual rerun): do not reselect or overwrite, give the
        # already recorded set as is.
        say({"status": "ready", "action": "deliver", "date": day, "already_recorded": True,
             "picks": history["days"][day], "found": len(history["days"][day])})
        return
    payload, is_error = tool_payload(read_json(args.result))
    status = status_of(payload, is_error)
    result = {"status": status, "date": day}
    if status == "ready":
        shown = {key for other, rows in history["days"].items() if other != day for row in rows for key in video_keys(row)}
        own = normalize_handle(args.handle) if args.handle else None
        picks, skipped, sizes, floors = select_picks(payload, shown, own, args.count)
        result.update({"action": "deliver", "picks": picks, "found": len(picks), "wanted": args.count,
                       "skipped": skipped, "window_sizes": sizes, "views_floor": floors,
                       **{key: payload.get(key) for key in ("generated_at", "expires_at", "next_refresh_at")}})
        if len(picks) < args.count:
            result["note"] = (f"Only {len(picks)} of {args.count} could be shown today; never pad the list. Say how many "
                              "there are, and why in plain words from `skipped` when it explains it.")
            if skipped["below_views_floor"]:
                result["note"] += (" The others had far fewer views than the top video of their list (under "
                                   f"{int(VIEWS_FLOOR_SHARE * 100)}% of it, see `views_floor`), so they were not picked.")
        if args.write:
            # Days with zero picks are recorded too: it was already checked today, and running again the same day does
            # not trigger again.
            directory.mkdir(parents=True, exist_ok=True)
            history["days"][day] = picks
            write_json(directory / "picks.json", history)
            result["recorded"] = True
    elif status == "generating":
        decision = poll_decision(payload, args.attempt, args.waited, POLL_LIMITS["for_you"])
        result.update(decision)
        if decision["action"] == "wait":
            line = wait_line(args.attempt, "Kabo is preparing today's picks for you. This can take a few minutes.")
            result.update({"progress_line": line} if line else {"say_to_creator": False})
        else:
            result["message"] = "Kabo is still preparing today's picks; you'll get them next time."
    elif status == "not_eligible":
        reason = first_text(payload.get("reason")) or "unknown"
        result.update({"action": "stop", "reason": reason,
                       # Seconds until it can be triggered again; null when no account is bound.
                       "retry_after_seconds": seconds(payload.get("retry_after_seconds")),
                       # Unknown reason codes appear only in the reason field and are not read out to the creator.
                       "message": FOR_YOU_NOT_ELIGIBLE.get(reason, "Kabo can't make picks for this account right now.")})
    else:
        # failed, tool errors (validation_error, not_found), and any status outside the contract: handled as
        # failure, reported as is, with no searching and no fallback.
        # failed is never polled (since kabo#2180 it is always retryable=false; cases that can be retried
        # immediately get generating directly from the backend).
        # retry_after_seconds is the seconds until it can next be triggered: turn it into "roughly how long until
        # you come back". An old backend's retryable=true plus about 24 hours is handled the same way.
        retryable = payload.get("retryable") is True
        detail = failure_detail(payload)
        when = about_time(payload.get("retry_after_seconds"))
        if status != "failed":
            message = "Kabo couldn't make today's picks."
        else:
            message = "Kabo couldn't make today's picks."
            message += f" New picks can be made in {when}." if when else " I'll try again next time."
        result.update({"action": "stop", "retryable": retryable, "failure_code": detail, "retry_in": when,
                       "message": message, "reported": reported(payload)})
    say(result)


def cmd_picks(args):
    """Whether one day was already checked and what it showed, to show again instead of asking Kabo again."""
    history = read_picks(args.library)
    day = args.date or now_utc().date().isoformat()
    say({"date": day, "checked": day in history["days"], "picks": history["days"].get(day),
         "recorded_days": sorted(history["days"])[-7:]})


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("path")
    command.add_argument("--workspace", required=True)
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    commands.add_parser("opening")
    command = commands.add_parser("profile-status")
    command.add_argument("--result", required=True)
    command.add_argument("--attempt", type=int, default=1)
    command.add_argument("--waited", type=int, default=0)
    command.add_argument("--niche-sent", action="store_true")
    command.add_argument("--write-retried", action="store_true")
    command = commands.add_parser("posts")
    command.add_argument("--library", required=True)
    command.add_argument("--limit", type=int, default=40)
    command.add_argument("--tell", action="store_true")
    command = commands.add_parser("connect-request")
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    command.add_argument("--url")
    command.add_argument("--expected-account-id")
    command.add_argument("--expected-binding-version")
    command = commands.add_parser("connect-result")
    command.add_argument("--result", required=True)
    command.add_argument("--handle", required=True)
    command = commands.add_parser("media-request")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", action="append")
    command.add_argument("--limit", type=int, default=8)
    command = commands.add_parser("transcripts")
    command.add_argument("--chars", type=int, default=1500)
    command = commands.add_parser("propose-pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--clusters", required=True)
    command = commands.add_parser("save-pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--file", required=True)
    command = commands.add_parser("declare-request")
    command.add_argument("--library", required=True)
    command.add_argument("--profile", required=True)
    command = commands.add_parser("record-sync")
    command.add_argument("--library", required=True)
    command.add_argument("--result", required=True)
    command.add_argument("--retried", action="store_true")
    command = commands.add_parser("profile-pillars")
    command.add_argument("--profile", required=True)
    command = commands.add_parser("for-you")
    command.add_argument("--library", required=True)
    command.add_argument("--result", required=True)
    command.add_argument("--handle")
    command.add_argument("--date")
    command.add_argument("--count", type=int, default=PICKS_PER_DAY)
    command.add_argument("--attempt", type=int, default=1)
    command.add_argument("--waited", type=int, default=0)
    command.add_argument("--write", action="store_true")
    command = commands.add_parser("picks")
    command.add_argument("--library", required=True)
    command.add_argument("--date")
    command = commands.add_parser("history-request")
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle")
    command.add_argument("--channel-id")
    command.add_argument("--depth", choices=("full", "daily"), default="daily")
    command = commands.add_parser("snapshot")
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--output", required=True)
    command = commands.add_parser("bootstrap")
    command.add_argument("--library", required=True)
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    command.add_argument("--profile")
    command = commands.add_parser("ingest")
    command.add_argument("--library", required=True)
    command.add_argument("--snapshot", required=True)
    command.add_argument("--handle")
    command = commands.add_parser("refresh-pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--profile")
    command.add_argument("--unavailable")
    command = commands.add_parser("set-pillar")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--pillar-id", required=True)
    command = commands.add_parser("show")
    command.add_argument("--library", required=True)
    command = commands.add_parser("due")
    command.add_argument("--library", required=True)
    command.add_argument("--with-optional", action="store_true")
    command = commands.add_parser("review-facts")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--checkpoint", required=True, choices=CHECKPOINT_ORDER)
    command = commands.add_parser("record-review")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--checkpoint", required=True, choices=CHECKPOINT_ORDER)
    command.add_argument("--report", required=True)
    command = commands.add_parser("recap")
    command.add_argument("--library", required=True)
    command.add_argument("--date")
    command = commands.add_parser("record-recap")
    command.add_argument("--library", required=True)
    command.add_argument("--report", required=True)
    command.add_argument("--date")
    command = commands.add_parser("comments")
    command.add_argument("--envelope", required=True)
    command.add_argument("--limit", type=int, default=30)
    command = commands.add_parser("evidence")
    command.add_argument("--dir", required=True)
    command.add_argument("--tool")
    return parser


HANDLERS = {"path": cmd_path, "opening": cmd_opening, "posts": cmd_posts, "connect-request": cmd_connect_request,
            "connect-result": cmd_connect_result, "media-request": cmd_media_request,
            "transcripts": cmd_transcripts, "propose-pillars": cmd_propose_pillars, "save-pillars": cmd_save_pillars,
            "declare-request": cmd_declare_request, "record-sync": cmd_record_sync, "profile-status": cmd_profile_status,
            "profile-pillars": cmd_profile_pillars, "for-you": cmd_for_you, "picks": cmd_picks,
            "history-request": cmd_history_request, "snapshot": cmd_snapshot, "bootstrap": cmd_bootstrap,
            "ingest": cmd_ingest, "refresh-pillars": cmd_refresh_pillars, "set-pillar": cmd_set_pillar, "show": cmd_show, "due": cmd_due,
            "review-facts": cmd_review_facts, "record-review": cmd_record_review, "recap": cmd_recap,
            "record-recap": cmd_record_recap, "comments": cmd_comments, "evidence": cmd_evidence}


def main():
    args = build_parser().parse_args()
    HANDLERS[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("Creator library operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)