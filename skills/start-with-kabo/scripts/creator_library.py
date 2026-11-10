#!/usr/bin/env python3
"""A creator's own content library: posts, niche and content pillars, daily picks, post reviews and recaps.

One directory per account (`<workspace>/kabo-library/<platform>-<handle>/`) keeps:
  library.json  account, binding time, niche, confirmed content pillars, follower readings, notes, schedule
  posts.json    every own video post seen, with each public-metric observation and its age
  picks.json    the daily viral picks already shown, so a pick never repeats
  reviews/      the 24 h review reports (and the optional 1 h / 7 d ones)
  recaps/       the daily account recaps

The script reshapes and counts; it never judges. Pillar names, review wording and recommendations
belong to the model. Metrics come only from public-content-snapshot.v1 files that
build_public_snapshot.py assembled from staged Kabo evidence.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent

LIBRARY_FORMAT = "kabo.creator-library.v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
METRICS = ("views", "likes", "comments", "shares", "saves")
# 复盘的三个时点；band 是「算作这个时点」的观测区间（小时），用来给别的作品取同龄基线。
# 每天只看一次账号，所以 24 小时时点的区间放宽到 24–48 小时：一天一次的观测正好有一次落在里面。
CHECKPOINTS = {"1h": (1.0, 3.0), "24h": (24.0, 48.0), "7d": (168.0, 192.0)}
CHECKPOINT_ORDER = ("1h", "24h", "7d")
# 默认只做 24 小时复盘；1 小时与 7 天是可选时点（due --with-optional）。
LATE_AFTER_HOURS = 48.0
# 发布满 72 小时的作品才算播放基本稳定，用于内容支柱表现和账号常规水平。
SETTLED_HOURS = 72.0
MIN_SETTLED_POSTS = 6
# 支柱规则：中位播放不低于账号常规水平的 0.8 倍；第二个支柱至少占 20% 播放。
PILLAR_MIN_MULTIPLE = 0.8
SECOND_PILLAR_MIN_SHARE = 0.2
MAX_PILLARS = 4
# 复刻只接 90 秒以内的口播或旁白视频。
REMAKE_MAX_SECONDS = 90
# 照片、图文不是视频，没有播放量，不进素材库。
NON_VIDEO_FORMATS = {"instagram_feed", "tiktok_photo"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
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
    # 先写临时文件再替换：定时任务被中断时不会留下半份 JSON。
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
        # TikTok 视频编号的高 32 位是创建时间。定时发布的视频创建得早，只有落在同一天才采用。
        try:
            created = datetime.fromtimestamp(int(item["content_id"]) >> 32, tz=timezone.utc)
        except (KeyError, ValueError, OverflowError, OSError):
            return published, "date_only"
        if created.date() == published.date():
            return created, "video_id"
        return published, "date_only"
    return published, "platform"


def age_anchor(post):
    # 只有日期的发布时间不能算小时级年龄，改用第一次看到它的时间，并在输出里说明。
    if post.get("published_at_source") == "date_only":
        return parse_time(post.get("first_seen_at")), "first_seen"
    return parse_time(post.get("published_at")), "published"


def latest(post):
    observations = post.get("observations") or []
    return observations[-1] if observations else None


def median(values):
    values = [value for value in values if isinstance(value, (int, float))]
    return statistics.median(values) if values else None


def ratio(value, base):
    if value is None or not base:
        return None
    return round(value / base, 2)


# ---------------------------------------------------------------- 取数请求与快照

def cmd_path(args):
    say({"library": str(library_path(args.workspace, args.platform, args.handle))})


def cmd_history_request(args):
    """The exact collect_account_history arguments for this account; pass them to the tool unchanged."""
    if args.channel_id and args.platform != "youtube":
        fail("--channel-id is only for YouTube")
    account = {"channel_id": args.channel_id} if args.channel_id else {"handle": normalize_handle(args.handle)}
    full = args.depth == "full"
    # 首次建库读得多（样本越大支柱越可靠），每天的复盘只需要最近的作品。
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
        fail("This Skill has no build_public_snapshot.py; build the snapshot from start-with-kabo or review-new-posts")
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
            owner = creators[0]  # YouTube 的频道名与自定义链接可能不同；只读了一个账号时它就是本人
        if owner is None:
            fail(f"The snapshot holds no posts from @{handle}; check the handle and platform")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reviews").mkdir(exist_ok=True)
        # 绑定时间取服务端抓取时间：此后发布的作品才进入复盘。
        write_json(directory / "library.json", {
            "format": LIBRARY_FORMAT, "platform": platform, "handle": handle,
            "creator_id": owner.get("creator_id"), "bound_at": iso(observed), "stateless": False,
            "niche": None, "pillars": [], "followers": [], "profile": {}, "updated_at": iso(observed),
        })
    library, store = load_library(directory)
    if library["platform"] != platform:
        fail(f"This library is for {library['platform']}, not {platform}")
    if library.get("bound_at") is None:
        library["bound_at"] = iso(observed - timedelta(hours=library.get("lookback_hours", 0)))
    bound = parse_time(library["bound_at"])
    posts = store.setdefault("posts", {})
    if library.get("creator_id") is None:
        # bootstrap 建的库还不知道账号编号：按账号名认领，只读了一个账号时它就是本人。
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
            continue  # 别人的作品（合拍、转发）和照片图文不进素材库
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
            # 只有绑定之后发布的作品才复盘；只有日期的按第一次看到的时间判断。
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


def cmd_posts(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    typical = median([views for _, views in settled_views(posts)])
    ordered = sorted(posts.values(), key=lambda post: post.get("published_at") or "", reverse=True)[: args.limit]
    say({"handle": library["handle"], "platform": library["platform"],
         "typical_settled_views": typical, "settled_posts": len(settled_views(posts)),
         "posts": [post_row(post, typical) for post in ordered]})


def cmd_media_request(args):
    """The collect_video_media arguments that fetch transcripts for the posts worth reading."""
    sys.path.insert(0, str(HERE))
    import static_host
    library, store = load_library(args.library)
    posts = store["posts"]
    ids = list(args.content_id or [])
    if not ids:
        # 播放最高的 4 条稳定作品，再补最近发布的、没选过的，凑满上限；一条也不重复。
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


def cluster_stats(clusters, posts):
    settled = settled_views(posts)
    total = sum(views for _, views in settled)
    typical = median([views for _, views in settled])
    rows = []
    for cluster in clusters:
        members = [posts[cid] for cid in cluster["content_ids"]]
        views = [latest(post)["views"] for post in members
                 if latest(post) and latest(post).get("views") is not None
                 and (latest(post).get("age_hours") or 0) >= SETTLED_HOURS]
        best = sorted((post for post in members if latest(post) and latest(post).get("views") is not None),
                      key=lambda post: -latest(post)["views"])[:2]
        rows.append({"id": cluster["id"], "name": cluster["name"], "posts": len(members),
                     "settled_posts": len(views), "settled_views": sum(views),
                     "view_share": round(sum(views) / total, 3) if total else None,
                     "median_views": median(views),
                     "median_multiple": ratio(median(views), typical),
                     "example_posts": [{"url": post.get("url"), "title": (post.get("title") or "")[:120],
                                        "views": latest(post)["views"]} for post in best]})
    return rows, typical, len(settled)


def choose_pillars(rows, settled_count):
    # 规则写死在这里，模型只负责给出聚类。支柱要「有效」：中位播放不低于账号常规水平的 0.8 倍，
    # 发得多但单条偏弱的聚类不算；合格的按播放占比排序取第一，第二个还要占比不低于 20%。
    need = 3 if settled_count >= 12 else 2
    sized = [row for row in rows if row["settled_posts"] >= need and row["view_share"] is not None]
    eligible = [row for row in sized if (row["median_multiple"] or 0) >= PILLAR_MIN_MULTIPLE]
    eligible.sort(key=lambda row: (-row["view_share"], -(row["median_views"] or 0)))
    chosen = eligible[:1]
    for row in eligible[1:]:
        if row["view_share"] >= SECOND_PILLAR_MIN_SHARE:
            chosen.append(row)
            break
    weak = False
    if not chosen and sized:
        # 没有一个聚类达到常规水平时，退回播放占比最高的一个，并标明它偏弱。
        chosen, weak = [max(sized, key=lambda row: row["view_share"])], True
    return [row["id"] for row in chosen], need, weak, {row["id"] for row in sized}, {row["id"] for row in eligible}


def validate_clusters(raw, posts):
    clusters = raw.get("clusters") if isinstance(raw, dict) else None
    if not isinstance(clusters, list) or not 1 <= len(clusters) <= 6:
        fail("clusters must be a list of 1 to 6 topic clusters")
    seen_ids, seen_posts = set(), set()
    for cluster in clusters:
        if not SLUG.match(str(cluster.get("id", ""))) or cluster["id"] in seen_ids:
            fail("Each cluster needs a unique id of lowercase letters, digits and hyphens")
        seen_ids.add(cluster["id"])
        check_pillar_text(cluster, "Cluster " + cluster["id"])
        ids = cluster.get("content_ids")
        if not isinstance(ids, list) or not ids:
            fail(f"Cluster {cluster['id']} needs content_ids")
        for content_id in ids:
            if content_id not in posts:
                fail(f"Unknown content_id {content_id}; use ids from creator_library.py posts")
            if content_id in seen_posts:
                fail(f"Post {content_id} is in more than one cluster")
            seen_posts.add(content_id)
    return clusters


def check_pillar_text(entry, label):
    for field in ("name", "definition"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            fail(f"{label} needs a {field}")
    queries = entry.get("search_queries")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 3 or not all(
            isinstance(query, str) and 2 <= len(query.strip()) <= 120 for query in queries):
        fail(f"{label} needs 1 to 3 search_queries of 2 to 120 characters")


def cmd_propose_pillars(args):
    """Local proposal: rank the model's topic clusters by the fixed pillar rule. Writes nothing."""
    library, store = load_library(args.library)
    posts = store["posts"]
    clusters = validate_clusters(read_json(args.clusters), posts)
    rows, typical, settled_count = cluster_stats(clusters, posts)
    chosen, need, weak, sized, eligible = choose_pillars(rows, settled_count)
    status = "ok" if settled_count >= MIN_SETTLED_POSTS else "insufficient_history"
    by_id = {cluster["id"]: cluster for cluster in clusters}
    for row in rows:
        row["definition"] = by_id[row["id"]]["definition"]
        row["search_queries"] = by_id[row["id"]]["search_queries"]
        row["recommended"] = row["id"] in chosen and status == "ok"
        if row["recommended"]:
            row["why"] = "meets the rule"
        elif row["id"] not in sized:
            row["why"] = f"fewer than {need} posts are 72 hours old with public views"
        elif row["id"] not in eligible:
            row["why"] = f"median views are under {PILLAR_MIN_MULTIPLE} times the account's typical views"
        else:
            row["why"] = f"holds under {int(SECOND_PILLAR_MIN_SHARE * 100)}% of views, so it is not a second pillar"
    rows.sort(key=lambda row: (not row["recommended"], -(row["view_share"] or 0)))
    result = {"status": status, "settled_posts": settled_count, "typical_settled_views": typical,
              "min_settled_posts_per_pillar": need, "below_typical": weak and status == "ok",
              "candidates": rows[:MAX_PILLARS], "unassigned_posts": len(posts) - sum(len(c["content_ids"]) for c in clusters)}
    if status != "ok":
        result["note"] = (f"Fewer than {MIN_SETTLED_POSTS} posts are 72 hours old with public views; performance "
                          "cannot rank pillars. Show the candidates without a recommendation and let the creator choose.")
    say(result)


def first_text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def slug_of(text, taken):
    base = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:30].strip("-") or "pillar"
    slug, number = base, 2
    while slug in taken:
        slug, number = f"{base}-{number}", number + 1
    return slug


def read_profile(path):
    """Niche and pillar candidates from the saved Kabo profile (get_creator_profile with effective: true)."""
    value = read_json(path)
    structured = value.get("structuredContent", value) if isinstance(value, dict) else {}
    if "content" in structured and "structuredContent" not in value and isinstance(structured.get("content"), list):
        try:
            structured = json.loads(structured["content"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError):
            fail("--profile is not a complete get_creator_profile result")
    effective = structured.get("effectiveContentProfile") if isinstance(structured.get("effectiveContentProfile"), dict) else None
    base = structured.get("contentProfile") if isinstance(structured.get("contentProfile"), dict) else None
    source = effective or base
    account = structured.get("account") if isinstance(structured.get("account"), dict) else {}
    diagnosis = structured.get("diagnosis") if isinstance(structured.get("diagnosis"), dict) else {}
    insight = diagnosis.get("insight") if isinstance(diagnosis.get("insight"), dict) else {}
    review = ((diagnosis.get("accountReview") or {}).get("sections") or {}).get("niche") or {}
    niche = first_text(insight.get("niche")) or first_text(review.get("label")) or first_text(review.get("summary"))
    items = [item for item in ((source or {}).get("signatureContent") or []) if isinstance(item, dict)]
    items.sort(key=lambda item: -(item.get("share") if isinstance(item.get("share"), (int, float)) else 0))
    taken, candidates = set(), []
    for item in items[:MAX_PILLARS]:
        name = first_text(item.get("name"))
        if not name:
            continue
        slug = slug_of(name, taken)
        taken.add(slug)
        terms = [term.strip() for term in item.get("seedTerms") or [] if isinstance(term, str) and 2 <= len(term.strip()) <= 120]
        definition = " - ".join(part for part in (first_text(item.get("topic")), first_text(item.get("approach"))) if part)
        share = item.get("share") if isinstance(item.get("share"), (int, float)) else None
        candidates.append({
            "id": slug, "name": name[:60], "definition": (definition or name)[:300],
            "search_queries": (terms[:3] or [name[:120]]), "source": "kabo_profile",
            "profile_item_id": item.get("id"),
            "evidence": {"share": share, "median_multiple": item.get("medianMultiplier"),
                         "content_count": item.get("contentCount"),
                         "examples": [{"url": row.get("sourceUrl"), "title": row.get("title"), "views": row.get("views"),
                                       "multiplier": row.get("multiplier")}
                                      for row in (item.get("representativeContent") or [])[:2] if isinstance(row, dict)]}})
    preferences = (effective or {}).get("preferences") if isinstance((effective or {}).get("preferences"), dict) else {}
    generated = ((effective or {}).get("base") or {}).get("generatedAt") if isinstance((effective or {}).get("base"), dict) else None
    return {"status": "ok" if candidates else "no_signature_content", "niche": niche,
         "profile_edited": bool((effective or {}).get("edited")),
         "language": (source or {}).get("language", {}).get("primary") if isinstance((source or {}).get("language"), dict) else None,
         "candidates": candidates,
         "hidden_by_creator": [row.get("name") for row in (effective or {}).get("hiddenSignatureContent") or [] if isinstance(row, dict)],
         "update_context": {"account_id": account.get("id"), "expected_version": preferences.get("version", 0),
                            "basis": first_text(generated or (base or {}).get("generatedAt"))},
         "note": None if candidates else "Kabo has no signature content for this account yet; compute pillars from the posts."}


def cmd_profile_pillars(args):
    say(read_profile(args.profile))


def cmd_bootstrap(args):
    """A minimal library for hosts that keep no files: pillars come from the creator's saved Kabo profile."""
    directory = Path(args.library)
    if (directory / "library.json").exists():
        fail("This library already exists; use it instead of rebuilding it")
    proposal = read_profile(args.profile)
    if proposal["status"] != "ok":
        fail("Kabo has no saved content pillars for this account, so there is nothing to rebuild from; "
             "run start-with-kabo in a host that keeps files")
    handle, when = normalize_handle(args.handle), now_utc()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reviews").mkdir(exist_ok=True)
    pillars = [{key: row[key] for key in ("id", "name", "definition", "search_queries", "source", "profile_item_id",
                                          "evidence") if key in row} for row in proposal["candidates"]]
    # 回看 48 小时：第一次读历史时按那次的抓取时间定绑定时间，让每条作品恰好在 24–48 小时的那一天进入一次复盘。
    write_json(directory / "library.json", {
        "format": LIBRARY_FORMAT, "platform": args.platform, "handle": handle, "creator_id": None,
        "bound_at": None, "lookback_hours": 48, "stateless": True,
        "niche": {"text": proposal["niche"] or "", "source": "kabo_profile"}, "pillars": pillars,
        "pillars_confirmed_at": iso(when), "pillars_confirmed_by": "saved_profile", "kabo_profile_synced": True,
        "followers": [], "profile": {"language": proposal["language"]} if proposal["language"] else {},
        "updated_at": iso(when)})
    write_json(directory / "posts.json", {"posts": {}})
    say({"library": str(directory), "stateless": True, "pillars": [row["id"] for row in pillars],
         "limit": "History-dependent features are limited: no repeat protection across days and no same-age comparison."})


def cmd_save_pillars(args):
    """Save the niche and the pillars the creator confirmed. The only command that writes pillars."""
    directory = Path(args.library)
    library, store = load_library(directory)
    posts = store["posts"]
    raw = read_json(args.file)
    pillars = raw.get("pillars")
    if not isinstance(pillars, list) or not 1 <= len(pillars) <= MAX_PILLARS:
        fail(f"pillars must list 1 to {MAX_PILLARS} confirmed pillars")
    niche = first_text(raw.get("niche"))
    if not niche or len(niche) > 200:
        fail("niche must be one line of at most 200 characters")
    if raw.get("niche_source") not in ("kabo_profile", "posts", "creator"):
        fail("niche_source must be kabo_profile, posts or creator")
    if raw.get("confirmed") is not True:
        fail("The creator has not confirmed this set: write confirmed: true only after they agreed to it")
    seen, saved = set(), []
    for pillar in pillars:
        if not SLUG.match(str(pillar.get("id", ""))) or pillar["id"] in seen:
            fail("Each pillar needs a unique id of lowercase letters, digits and hyphens")
        seen.add(pillar["id"])
        check_pillar_text(pillar, "Pillar " + pillar["id"])
        if pillar.get("source") not in ("kabo_profile", "local_posts", "creator"):
            fail(f"Pillar {pillar['id']} needs a source: kabo_profile, local_posts or creator")
        for content_id in pillar.get("content_ids") or []:
            if content_id not in posts:
                fail(f"Unknown content_id {content_id}")
        saved.append({key: pillar[key] for key in ("id", "name", "definition", "search_queries", "source",
                                                  "profile_item_id", "evidence") if key in pillar})
    when = iso(now_utc())
    previous = {row["id"] for row in library.get("pillars") or []}
    for post in posts.values():
        # 被换掉的旧支柱不留悬空归属；「other」和新支柱的归属保持。
        if post.get("pillar_id") in previous and post["pillar_id"] not in seen:
            post["pillar_id"] = None
    for pillar in pillars:
        for content_id in pillar.get("content_ids") or []:
            posts[content_id]["pillar_id"] = pillar["id"]
    library.update({"niche": {"text": niche, "source": raw["niche_source"]}, "pillars": saved,
                    "pillars_confirmed_at": when, "pillars_confirmed_by": "creator",
                    "kabo_profile_synced": bool(raw.get("kabo_synced")), "updated_at": when})
    write_json(directory / "library.json", library)
    write_json(directory / "posts.json", store)
    say({"saved": True, "niche": library["niche"], "pillars": [row["id"] for row in saved],
         "posts_assigned": sum(1 for post in posts.values() if post.get("pillar_id") in seen)})


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


PROFILE_FIELDS = {"voice": str, "audience": str, "schedule": dict, "language": str, "notes": str}


def cmd_set_profile(args):
    directory = Path(args.library)
    library, _ = load_library(directory)
    profile = read_json(args.profile)
    if not isinstance(profile, dict) or not profile or set(profile) - set(PROFILE_FIELDS):
        fail("Profile fields: " + ", ".join(PROFILE_FIELDS))
    for key, kind in PROFILE_FIELDS.items():
        if key in profile and not isinstance(profile[key], kind):
            fail(f"Profile field {key} must be a {kind.__name__}")
    library.setdefault("profile", {}).update(profile)
    library["updated_at"] = iso(now_utc())
    write_json(directory / "library.json", library)
    say({"profile": library["profile"]})


def cmd_show(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    picks = read_json(Path(args.library) / "picks.json", {"days": {}})
    tracked = [post for post in posts.values() if post.get("tracked")]
    followers = library.get("followers") or []
    say({"platform": library["platform"], "handle": library["handle"], "bound_at": library["bound_at"],
         "stateless": bool(library.get("stateless")), "niche": library.get("niche"),
         "pillars": library.get("pillars"), "pillars_confirmed_by": library.get("pillars_confirmed_by"),
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
        facts["limits"].append(f"Fewer than 3 earlier posts were measured at the {args.checkpoint} mark, so "
                               "there is no same-age comparison yet; typical_settled compares against lifetime "
                               "views of posts at least 72 hours old, which is not the same age.")
    elif not at_mark:
        facts["limits"].append(f"This post was not measured at the {args.checkpoint} mark (its first reading came "
                               "later), so the same-age comparison is not possible; say the review is late.")
    if args.checkpoint == "24h" and last.get("age_hours", 0) >= LATE_AFTER_HOURS:
        facts["limits"].append("This review is late: the post is already past 48 hours old.")
    if last.get("age_from") == "first_seen":
        facts["limits"].append("The platform gave a publish date without a time; age is counted from when the "
                               "post was first seen, so it can be up to one check interval late.")
    if last.get("views") is None:
        facts["limits"].append("The platform does not show this post's views publicly.")
    if library.get("stateless"):
        facts["limits"].append("This host keeps no files between runs, so earlier readings of the creator's posts are "
                               "missing: no same-age comparison, and a post may be reviewed again on a later day.")
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
    if library.get("stateless"):
        limits.append("This host keeps no files between runs: no follower change and no history beyond this read.")
    readings = library.get("followers") or []
    followers = {"available": False, "now": readings[-1]["value"] if readings else None}
    if len(readings) >= 2:
        newest = parse_time(readings[-1]["observed_at"])
        # 取一天以前最近的一次读数作对比；没有满一天的读数就取最早的一次，并标明间隔。
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
        limits.append("This library has no confirmed pillars, so there is no per-pillar reading.")
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
    # 文件名以暂存时间开头，按名字排序就是调用顺序。
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

def enrichment_items(path):
    value = read_json(path)
    if value.get("schema_version") not in ("trend-enrichment.v1", "youtube-trend-enrichment.v1"):
        fail(f"{path} is not a staged enrich_instagram_shortlist or enrich_youtube_shortlist result")
    return [item for item in value.get("items") or [] if isinstance(item, dict)]


def candidate_view(item):
    """Instagram and YouTube enrichment items in one shape."""
    # Instagram 用 outlier / author / play_count，YouTube 用 account_breakout / channel / views。
    outlier = item.get("outlier") or item.get("account_breakout") or {}
    author = item.get("author") or {}
    channel = item.get("channel") or {}
    metrics = item.get("metrics") or {}
    multiple = outlier.get("multiple")
    return {
        "author": author.get("handle") or channel.get("title") or channel.get("id"),
        "multiple": multiple if isinstance(multiple, (int, float)) else None,
        "typical": outlier.get("cohort_median"),
        "compared": outlier.get("cohort_size", outlier.get("comparable_count")),
        "strength": outlier.get("evidence_strength"),
        "views": metrics.get("play_count", metrics.get("views")),
    }


def pillar_of(item, pillars):
    # 采集时 intent_id 写成「支柱 id.序号」，据此把候选归回支柱。
    for source in item.get("sources") or []:
        intent = str(source.get("intent_id") or "")
        pillar = intent.rsplit(".", 1)[0]
        if pillar in pillars:
            return pillar
    return None


def cmd_pick_request(args):
    """The exact collect_*_trend_candidates arguments for today's search; pass them to the tool unchanged."""
    library, _ = load_library(args.library)
    pillars = library.get("pillars") or []
    if not pillars:
        fail("This library has no confirmed content pillars yet; run start-with-kabo first")
    language = (library.get("profile") or {}).get("language") or args.language
    platform = args.platform or library["platform"]
    if platform == "instagram":
        # 每个支柱的第一条检索词优先，再轮流补第二、第三条，一共最多 6 条意图。
        intents = []
        for round_index in range(3):
            for pillar in pillars:
                queries = pillar["search_queries"]
                if round_index < len(queries) and len(intents) < 6:
                    intents.append({"intent_id": f"{pillar['id']}.{round_index + 1}", "search_query": queries[round_index]})
        request = {"platform": "instagram", "window": "last-week", "intents": intents, "delivery": "download"}
    elif platform == "youtube":
        # YouTube 检索有全站每日上限：最多 2 条意图，各取支柱的第一条检索词。
        until = now_utc().replace(microsecond=0)
        request = {"platform": "youtube", "published_after": iso(until - timedelta(days=7)), "published_before": iso(until),
                   "intents": [{"intent_id": f"{pillar['id']}.1", "query": pillar["search_queries"][0]} for pillar in pillars[:2]],
                   "delivery": "download"}
    else:
        fail("Daily picks search Instagram, and YouTube for YouTube creators")
    if language:
        request["language"] = language
    say(request)


def cmd_candidates(args):
    value = read_json(args.collection)
    if value.get("schema_version") not in ("trend-candidate-set.v1", "youtube-trend-candidate-set.v1"):
        fail("--collection must be a staged collect_instagram_trend_candidates or collect_youtube_trend_candidates result")
    rows = []
    for item in value.get("items") or []:
        metrics = item.get("metrics") or {}
        author = item.get("author") or {}
        channel = item.get("channel") or {}
        rows.append({"content_key": item.get("content_key"),
                     "intents": sorted({str(source.get("intent_id")) for source in item.get("sources") or []}),
                     "author": author.get("handle") or channel.get("title"),
                     "author_followers": author.get("follower_count"),
                     "views": metrics.get("play_count", metrics.get("views")),
                     "published_at": item.get("published_at"), "duration_seconds": item.get("duration_seconds"),
                     "text": " ".join(str(item.get(key) or "") for key in ("title", "caption", "description")).strip()[:240]})
    say({"candidate_set_id": value.get("candidate_set_id"), "platform": value.get("platform"),
         "window": value.get("discovery_window") or value.get("window"), "status": value.get("status"),
         "limitations": value.get("limitations"), "candidates": rows})


def remake_note(platform, duration):
    # 复刻只接 90 秒以内的口播或旁白视频；是不是口播由复刻自己在收费前检查。
    if platform not in ("instagram", "youtube"):
        return "not supported for this platform"
    if isinstance(duration, (int, float)) and duration > REMAKE_MAX_SECONDS:
        return f"not possible: longer than {REMAKE_MAX_SECONDS} seconds"
    if not isinstance(duration, (int, float)):
        return f"unknown length: possible only if it is a talking-head or voice-over video of {REMAKE_MAX_SECONDS} seconds or less"
    return f"possible only if it is a talking-head or voice-over video ({int(duration)} seconds long)"


def cmd_pick(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    pillars = [pillar["id"] for pillar in library.get("pillars") or []]
    if not pillars:
        fail("This library has no confirmed content pillars yet; run start-with-kabo first")
    history = read_json(directory / "picks.json", {"days": {}})
    shown = {row.get("content_key") for rows in history["days"].values() for row in rows} | {
        row.get("url") for rows in history["days"].values() for row in rows}
    day = args.date or now_utc().date().isoformat()
    if day in history["days"] and args.write:
        fail(f"Picks for {day} are already recorded")
    own = library["handle"]
    candidates, rejected = [], {"already_shown": 0, "own_post": 0, "below_multiple": 0, "no_pillar": 0,
                                "weak_or_missing_baseline": 0}
    for path in args.enrichment:
        for item in enrichment_items(path):
            view = candidate_view(item)
            if item.get("content_key") in shown or item.get("url") in shown:
                rejected["already_shown"] += 1
            elif str(view["author"] or "").lstrip("@").lower() == own:
                rejected["own_post"] += 1
            # 只有样本够的倍数才算爆款证据（与趋势技能同一口径：moderate 或 strong）。
            elif view["multiple"] is None or view["strength"] not in ("moderate", "strong"):
                rejected["weak_or_missing_baseline"] += 1
            elif view["multiple"] < args.min_multiple:
                rejected["below_multiple"] += 1
            elif pillar_of(item, pillars) is None:
                rejected["no_pillar"] += 1
            else:
                candidates.append(item)
    candidates.sort(key=lambda item: -(item.get("final_score") or 0))
    chosen, authors = [], set()

    def take(item):
        author = candidate_view(item)["author"]
        if any(item is row for row in chosen) or (author and author in authors):
            return False
        chosen.append(item)
        authors.add(author)
        return True

    # 先保证每个支柱至少一条（按支柱顺序），再按综合得分补满。
    for pillar in pillars:
        if len(chosen) >= args.count:
            break
        for item in candidates:
            if pillar_of(item, pillars) == pillar and take(item):
                break
    for item in candidates:
        if len(chosen) >= args.count:
            break
        take(item)
    picks = []
    for item in chosen[: args.count]:
        view = candidate_view(item)
        duration = item.get("duration_seconds")
        picks.append({
            "content_key": item.get("content_key"), "url": item.get("url"), "platform": item.get("platform"),
            "author": view["author"], "pillar_id": pillar_of(item, pillars), "published_at": item.get("published_at"),
            "views": view["views"], "multiple": view["multiple"], "author_typical_views": view["typical"],
            "author_posts_compared": view["compared"], "evidence_strength": view["strength"],
            "creator_transferability": (item.get("semantic_scores") or {}).get("creator_transferability"),
            "text": " ".join(str(item.get(key) or "") for key in ("title", "caption")).strip()[:300],
            "duration_seconds": duration, "remake": remake_note(item.get("platform"), duration),
        })
    result = {"date": day, "picks": picks, "candidates_passed": len(candidates), "rejected": rejected,
              "min_multiple": args.min_multiple}
    if library.get("stateless"):
        result["limits"] = ["This host keeps no files between runs, so a video shown on an earlier day can come back."]
    if len(picks) < args.count:
        result["note"] = (f"Only {len(picks)} candidate(s) passed; never pad the list with weaker videos. Say how "
                          "many were found and why the rest were excluded.")
    if args.write and picks:
        history["days"][day] = picks
        write_json(directory / "picks.json", history)
        result["written"] = True
    say(result)


def cmd_picks(args):
    """The picks already recorded for one day, to show again instead of searching again."""
    history = read_json(Path(args.library) / "picks.json", {"days": {}})
    day = args.date or now_utc().date().isoformat()
    say({"date": day, "picks": history["days"].get(day), "recorded_days": sorted(history["days"])[-7:]})


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("path")
    command.add_argument("--workspace", required=True)
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    command = commands.add_parser("history-request")
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle")
    command.add_argument("--channel-id")
    command.add_argument("--depth", choices=("full", "daily"), default="daily")
    command = commands.add_parser("snapshot")
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--output", required=True)
    command = commands.add_parser("ingest")
    command.add_argument("--library", required=True)
    command.add_argument("--snapshot", required=True)
    command.add_argument("--handle")
    command = commands.add_parser("posts")
    command.add_argument("--library", required=True)
    command.add_argument("--limit", type=int, default=40)
    command = commands.add_parser("media-request")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", action="append")
    command.add_argument("--limit", type=int, default=8)
    command = commands.add_parser("transcripts")
    command.add_argument("--chars", type=int, default=1500)
    command = commands.add_parser("propose-pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--clusters", required=True)
    command = commands.add_parser("profile-pillars")
    command.add_argument("--profile", required=True)
    command = commands.add_parser("save-pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--file", required=True)
    command = commands.add_parser("set-pillar")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--pillar-id", required=True)
    command = commands.add_parser("set-profile")
    command.add_argument("--library", required=True)
    command.add_argument("--profile", required=True)
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
    command = commands.add_parser("candidates")
    command.add_argument("--collection", required=True)
    command = commands.add_parser("pick-request")
    command.add_argument("--library", required=True)
    command.add_argument("--platform", choices=("instagram", "youtube"))
    command.add_argument("--language")
    command = commands.add_parser("bootstrap")
    command.add_argument("--library", required=True)
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    command.add_argument("--profile", required=True)
    command = commands.add_parser("pick")
    command.add_argument("--library", required=True)
    command.add_argument("--enrichment", action="append", required=True)
    command.add_argument("--count", type=int, default=3)
    command.add_argument("--min-multiple", type=float, default=2.0)
    command.add_argument("--date")
    command.add_argument("--write", action="store_true")
    command = commands.add_parser("picks")
    command.add_argument("--library", required=True)
    command.add_argument("--date")
    return parser


HANDLERS = {"path": cmd_path, "history-request": cmd_history_request, "snapshot": cmd_snapshot,
            "ingest": cmd_ingest, "posts": cmd_posts, "media-request": cmd_media_request,
            "transcripts": cmd_transcripts, "propose-pillars": cmd_propose_pillars,
            "profile-pillars": cmd_profile_pillars, "save-pillars": cmd_save_pillars,
            "set-pillar": cmd_set_pillar, "set-profile": cmd_set_profile, "show": cmd_show, "due": cmd_due,
            "review-facts": cmd_review_facts, "record-review": cmd_record_review, "recap": cmd_recap,
            "record-recap": cmd_record_recap, "comments": cmd_comments, "evidence": cmd_evidence,
            "candidates": cmd_candidates, "pick": cmd_pick, "picks": cmd_picks,
            "pick-request": cmd_pick_request, "bootstrap": cmd_bootstrap}


def main():
    args = build_parser().parse_args()
    HANDLERS[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("Creator library operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
