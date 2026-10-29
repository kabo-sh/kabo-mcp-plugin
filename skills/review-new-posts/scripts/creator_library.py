#!/usr/bin/env python3
"""A creator's own content library: posts, content pillars, daily picks and post reviews.

One directory per account (`<workspace>/kabo-library/<platform>-<handle>/`) keeps:
  library.json  account, binding time, content pillars, voice and footage notes, schedule
  posts.json    every own post seen, with each public-metric observation and its age
  picks.json    the daily viral picks already shown, so a pick never repeats
  reviews/      the 1 h / 24 h / 7 d review reports

The script reshapes and counts; it never judges. Pillar names, review wording and next-video
ideas belong to the model. Metrics come only from public-content-snapshot.v1 files that
build_public_snapshot.py assembled from staged Kabo evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True

LIBRARY_FORMAT = "kabo.creator-library.v1"
PLATFORMS = ("instagram", "tiktok", "youtube")
METRICS = ("views", "likes", "comments", "shares", "saves")
# 复盘的三个时点；band 是「算作这个时点」的观测区间（小时），用来给别的作品取同龄基线。
CHECKPOINTS = {"1h": (1.0, 3.0), "24h": (24.0, 36.0), "7d": (168.0, 216.0)}
CHECKPOINT_ORDER = ("1h", "24h", "7d")
# 发布满 72 小时的作品才算播放基本稳定，用于内容支柱表现和账号常规水平。
SETTLED_HOURS = 72.0
MIN_SETTLED_POSTS = 6
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


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


# ---------------------------------------------------------------- ingest

def cmd_path(args):
    print(json.dumps({"library": str(library_path(args.workspace, args.platform, args.handle))}))


def cmd_ingest(args):
    snapshot = read_json(args.snapshot)
    if snapshot.get("schema_version") != "public-content-snapshot.v1":
        fail("--snapshot must be a public-content-snapshot.v1 file from build_public_snapshot.py")
    platform = snapshot.get("platform")
    observed = parse_time(snapshot.get("observed_at"))
    if platform not in PLATFORMS or observed is None:
        fail("Snapshot has no platform or observed_at")
    creators = {row.get("creator_id"): row for row in snapshot.get("creators") or []}
    directory = Path(args.library)
    created = not (directory / "library.json").exists()
    if created:
        if not args.handle:
            fail("The first ingest needs --handle, the account this library belongs to")
        handle = normalize_handle(args.handle)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reviews").mkdir(exist_ok=True)
        owner = next((row for row in creators.values() if normalize_handle(row.get("handle") or "x") == handle), None)
        if owner is None:
            fail(f"The snapshot holds no posts from @{handle}; check the handle and platform")
        # 绑定时间取服务端抓取时间：此后发布的作品才进入 1 小时 / 24 小时 / 7 天复盘。
        write_json(directory / "library.json", {
            "format": LIBRARY_FORMAT, "platform": platform, "handle": handle,
            "creator_id": owner.get("creator_id"), "bound_at": iso(observed),
            "pillars": [], "clusters": [], "profile": {}, "updated_at": iso(observed),
        })
    library, store = load_library(directory)
    if library["platform"] != platform:
        fail(f"This library is for {library['platform']}, not {platform}")
    bound = parse_time(library["bound_at"])
    posts = store.setdefault("posts", {})
    new_posts, updated = [], 0
    for item in snapshot.get("items") or []:
        if item.get("creator_id") != library.get("creator_id"):
            continue  # 别人的作品（合拍、转发）不进本人素材库
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
    result = {"library": str(directory), "created": created, "observed_at": iso(observed),
              "posts_in_library": len(posts), "observations_added": updated, "new_tracked_posts": new_posts,
              "due": due_reviews(library, posts)}
    print(json.dumps(result, ensure_ascii=False))


# ---------------------------------------------------------------- posts and pillars

def settled_views(posts):
    rows = []
    for post in posts.values():
        last = latest(post)
        if last and last.get("views") is not None and (last.get("age_hours") or 0) >= SETTLED_HOURS:
            rows.append((post, last["views"]))
    return rows


def cmd_posts(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    typical = median([views for _, views in settled_views(posts)])
    ordered = sorted(posts.values(), key=lambda post: post.get("published_at") or "", reverse=True)[: args.limit]
    rows = []
    for post in ordered:
        last = latest(post) or {}
        rows.append({"content_id": post["content_id"], "published_at": post.get("published_at"),
                     "age_hours": last.get("age_hours"), "views": last.get("views"),
                     "multiple_of_typical": ratio(last.get("views"), typical), "likes": last.get("likes"),
                     "comments": last.get("comments"), "pillar_id": post.get("pillar_id"),
                     "url": post.get("url"), "title": (post.get("title") or "")[:200]})
    print(json.dumps({"handle": library["handle"], "platform": library["platform"],
                      "typical_settled_views": typical, "settled_posts": len(settled_views(posts)),
                      "posts": rows}, ensure_ascii=False, indent=1))


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
        rows.append({"id": cluster["id"], "name": cluster["name"], "posts": len(members),
                     "settled_posts": len(views), "settled_views": sum(views),
                     "view_share": round(sum(views) / total, 3) if total else None,
                     "median_views": median(views),
                     "median_multiple": ratio(median(views), typical)})
    return rows, typical, len(settled)


def choose_pillars(rows, settled_count):
    # 规则写死在这里，模型只负责给出聚类。支柱要「有效」：中位播放不低于账号常规水平的 0.8 倍，
    # 发得多但单条偏弱的聚类不算；合格的按播放占比排序取第一，第二个还要占比不低于 20%。
    need = 3 if settled_count >= 12 else 2
    sized = [row for row in rows if row["settled_posts"] >= need and row["view_share"] is not None]
    eligible = [row for row in sized if (row["median_multiple"] or 0) >= 0.8]
    eligible.sort(key=lambda row: (-row["view_share"], -(row["median_views"] or 0)))
    chosen = eligible[:1]
    for row in eligible[1:]:
        if row["view_share"] >= 0.2:
            chosen.append(row)
            break
    weak = False
    if not chosen and sized:
        # 没有一个聚类达到常规水平时，退回播放占比最高的一个，并标明它偏弱。
        chosen, weak = [max(sized, key=lambda row: row["view_share"])], True
    return [row["id"] for row in chosen], need, weak


def validate_clusters(raw, posts):
    clusters = raw.get("clusters") if isinstance(raw, dict) else None
    if not isinstance(clusters, list) or not 1 <= len(clusters) <= 6:
        fail("clusters must be a list of 1 to 6 topic clusters")
    seen_ids, seen_posts = set(), set()
    for cluster in clusters:
        if not SLUG.match(str(cluster.get("id", ""))) or cluster["id"] in seen_ids:
            fail("Each cluster needs a unique id of lowercase letters, digits and hyphens")
        seen_ids.add(cluster["id"])
        for field in ("name", "definition"):
            if not isinstance(cluster.get(field), str) or not cluster[field].strip():
                fail(f"Cluster {cluster['id']} needs a {field}")
        queries = cluster.get("search_queries")
        if not isinstance(queries, list) or not 1 <= len(queries) <= 3 or not all(
                isinstance(query, str) and 2 <= len(query.strip()) <= 120 for query in queries):
            fail(f"Cluster {cluster['id']} needs 1 to 3 search_queries of 2 to 120 characters")
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


def cmd_pillars(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    posts = store["posts"]
    clusters = validate_clusters(read_json(args.clusters), posts)
    rows, typical, settled_count = cluster_stats(clusters, posts)
    chosen, need, weak = choose_pillars(rows, settled_count)
    chosen_by = "rule"
    if args.choose:
        picked = [value.strip() for value in args.choose.split(",") if value.strip()]
        if not 1 <= len(picked) <= 2 or any(value not in {row["id"] for row in rows} for value in picked):
            fail("--choose takes one or two cluster ids from the clusters file")
        chosen, chosen_by = picked, "creator"
    status = "ok" if settled_count >= MIN_SETTLED_POSTS else "insufficient_history"
    result = {"status": status, "settled_posts": settled_count, "typical_settled_views": typical,
              "min_settled_posts_per_pillar": need, "clusters": rows, "pillars": chosen,
              "chosen_by": chosen_by, "below_typical": weak and chosen_by == "rule", "unassigned_posts": len(posts) - sum(len(c["content_ids"]) for c in clusters)}
    if status != "ok" and not args.choose:
        result["note"] = (f"Fewer than {MIN_SETTLED_POSTS} posts are 72 hours old with public views; performance "
                          "cannot rank pillars. Ask the creator which one or two clusters are their pillars and "
                          "rerun with --choose.")
        result["pillars"] = []
    if args.write and result["pillars"]:
        by_id = {cluster["id"]: cluster for cluster in clusters}
        stats = {row["id"]: row for row in rows}
        library["clusters"] = [{key: cluster[key] for key in ("id", "name", "definition", "search_queries")}
                               for cluster in clusters]
        library["pillars"] = [{"id": pid, "name": by_id[pid]["name"], "definition": by_id[pid]["definition"],
                               "search_queries": by_id[pid]["search_queries"], "evidence": stats[pid],
                               "chosen_by": chosen_by} for pid in result["pillars"]]
        for cluster in clusters:
            for content_id in cluster["content_ids"]:
                posts[content_id]["pillar_id"] = cluster["id"]
        library["updated_at"] = iso(now_utc())
        write_json(directory / "library.json", library)
        write_json(directory / "posts.json", store)
        result["written"] = True
    print(json.dumps(result, ensure_ascii=False, indent=1))


def cmd_set_pillar(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    known = {cluster["id"] for cluster in library.get("clusters") or []}
    if args.pillar_id not in known | {"other"}:
        fail("Pillar id must be one of the library's clusters or 'other'")
    post = store["posts"].get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    post["pillar_id"] = args.pillar_id
    write_json(directory / "posts.json", store)
    print(json.dumps({"content_id": args.content_id, "pillar_id": args.pillar_id}))


PROFILE_FIELDS = {"voice": str, "audience": str, "footage": list, "schedule": dict, "language": str, "notes": str}


def cmd_set_profile(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    profile = read_json(args.profile)
    if not isinstance(profile, dict) or not profile or set(profile) - set(PROFILE_FIELDS):
        fail("Profile fields: " + ", ".join(PROFILE_FIELDS))
    for key, kind in PROFILE_FIELDS.items():
        if key in profile and not isinstance(profile[key], kind):
            fail(f"Profile field {key} must be a {kind.__name__}")
    for row in profile.get("footage", []):
        # 复刻素材只收本人公开作品链接，最多 4 条，与 start_remake_video 的上限一致。
        if not isinstance(row, dict) or row.get("content_id") not in store["posts"]:
            fail("Each footage entry needs a content_id of one of the creator's own posts")
    if len(profile.get("footage", [])) > 4:
        fail("Keep at most 4 footage posts")
    library.setdefault("profile", {}).update(profile)
    for row in library["profile"].get("footage", []):
        row["url"] = store["posts"][row["content_id"]].get("url")
    library["updated_at"] = iso(now_utc())
    write_json(directory / "library.json", library)
    print(json.dumps({"profile": library["profile"]}, ensure_ascii=False))


def cmd_show(args):
    library, store = load_library(args.library)
    posts = store["posts"]
    picks = read_json(Path(args.library) / "picks.json", {"days": {}})
    tracked = [post for post in posts.values() if post.get("tracked")]
    print(json.dumps({
        "platform": library["platform"], "handle": library["handle"], "bound_at": library["bound_at"],
        "pillars": library.get("pillars"), "profile": library.get("profile"),
        "posts_in_library": len(posts), "typical_settled_views": median([v for _, v in settled_views(posts)]),
        "tracked_posts": len(tracked), "reviews_done": sum(len(post.get("reviews") or {}) for post in tracked),
        "pick_days": sorted(picks["days"])[-7:],
    }, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- reviews

def due_reviews(library, posts):
    rows = []
    for post in posts.values():
        if not post.get("tracked"):
            continue
        last = latest(post)
        age = last.get("age_hours") if last else None
        if age is None:
            continue
        done = post.get("reviews") or {}
        for index, name in enumerate(CHECKPOINT_ORDER):
            target = CHECKPOINTS[name][0]
            following = CHECKPOINTS[CHECKPOINT_ORDER[index + 1]][0] if index + 1 < len(CHECKPOINT_ORDER) else 336.0
            # 只复盘年龄落在本时点与下一时点之间的作品；错过的时点不补，复盘里如实写明。
            if name not in done and target <= age < following:
                rows.append({"content_id": post["content_id"], "checkpoint": name, "age_hours": age,
                             "age_from": last.get("age_from"), "url": post.get("url")})
    return rows


def cmd_due(args):
    library, store = load_library(args.library)
    print(json.dumps({"due": due_reviews(library, store["posts"])}, ensure_ascii=False))


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
    if args.checkpoint not in CHECKPOINTS:
        fail("Checkpoint must be 1h, 24h or 7d")
    post = posts.get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    last = latest(post) or fail("This post has no observation yet")
    others = [other for cid, other in posts.items() if cid != args.content_id]
    same_age = [(other, band_observation(other, args.checkpoint)) for other in others]
    same_age = [(other, row) for other, row in same_age if row]
    same_age_median = median([row["views"] for _, row in same_age])
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
    facts = {
        "content_id": post["content_id"], "url": post.get("url"), "title": post.get("title"),
        "checkpoint": args.checkpoint, "age_hours": last.get("age_hours"), "age_from": last.get("age_from"),
        "observed_at": last["observed_at"], "metrics": {name: last.get(name) for name in METRICS},
        "engagement_rate": engagement(last), "pillar_id": post.get("pillar_id"),
        "missed_checkpoints": [name for name in CHECKPOINT_ORDER[:CHECKPOINT_ORDER.index(args.checkpoint)]
                               if name not in (post.get("reviews") or {})],
        "same_age_baseline": {"posts": len(same_age), "median_views": same_age_median,
                              "multiple": ratio(last.get("views"), same_age_median) if len(same_age) >= 3 else None},
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
    if last.get("age_from") == "first_seen":
        facts["limits"].append("The platform gave a publish date without a time; age is counted from when the "
                               "post was first seen, so it can be up to one check interval late.")
    if last.get("views") is None:
        facts["limits"].append("The platform does not show this post's views publicly.")
    print(json.dumps(facts, ensure_ascii=False, indent=1))


def cmd_record_review(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    post = store["posts"].get(args.content_id) or fail(f"Unknown content_id {args.content_id}")
    if args.checkpoint not in CHECKPOINTS:
        fail("Checkpoint must be 1h, 24h or 7d")
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
    print(json.dumps({"recorded": args.checkpoint, "content_id": args.content_id, "report": str(target)}))


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
    print(json.dumps({"status": envelope.get("status"), "comments": rows[: args.limit],
                      "total_read": len(rows)}, ensure_ascii=False, indent=1))


def cmd_transcript(args):
    envelope = read_json(args.envelope)
    data = envelope.get("data") or {}
    text = data.get("text") if isinstance(data.get("text"), str) else " ".join(
        str(row.get("text")) for row in data.get("rows") or [] if isinstance(row, dict) and row.get("text"))
    print(json.dumps({"status": envelope.get("status"), "language": data.get("language"),
                      "text": text.strip()[:6000]}, ensure_ascii=False))


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
        row = {"file": str(body), "tool": meta.get("tool"), "operation": meta.get("operation"),
               "schema_version": meta.get("schema_version")}
        # 下载交付时工具结果里没有 data，翻页游标只在落盘的证据里；列出来供下一页调用使用。
        data = json.loads(body.read_text(encoding="utf-8")).get("data")
        if isinstance(data, dict) and "more_available" in data:
            row["more_available"] = data.get("more_available")
            if isinstance(data.get("cursor"), str):
                row["cursor"] = data["cursor"]
        rows.append(row)
    print(json.dumps({"evidence": rows}, ensure_ascii=False, indent=1))


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
    print(json.dumps({"candidate_set_id": value.get("candidate_set_id"), "platform": value.get("platform"),
                      "window": value.get("discovery_window") or value.get("window"), "status": value.get("status"),
                      "limitations": value.get("limitations"), "candidates": rows}, ensure_ascii=False, indent=1))


def cmd_pick(args):
    directory = Path(args.library)
    library, store = load_library(directory)
    pillars = [pillar["id"] for pillar in library.get("pillars") or []]
    if not pillars:
        fail("This library has no content pillars yet; run build-creator-library first")
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
        if item.get("platform") not in ("instagram", "youtube"):
            remake = "not supported for this platform"
        elif isinstance(duration, (int, float)) and duration > 90:
            remake = "not possible: longer than 90 seconds"
        else:
            # 复刻只接单人口播、90 秒以内；是否口播由复刻在收费前自己检查。
            remake = "possible if it is a single-speaker talking-head video of 90 seconds or less"
        picks.append({
            "content_key": item.get("content_key"), "url": item.get("url"), "platform": item.get("platform"),
            "author": view["author"], "pillar_id": pillar_of(item, pillars), "published_at": item.get("published_at"),
            "views": view["views"], "multiple": view["multiple"], "author_typical_views": view["typical"],
            "author_posts_compared": view["compared"], "evidence_strength": view["strength"],
            "creator_transferability": (item.get("semantic_scores") or {}).get("creator_transferability"),
            "text": " ".join(str(item.get(key) or "") for key in ("title", "caption")).strip()[:300],
            "duration_seconds": duration, "remake": remake,
        })
    result = {"date": day, "picks": picks, "candidates_passed": len(candidates), "rejected": rejected,
              "min_multiple": args.min_multiple}
    if len(picks) < args.count:
        result["note"] = (f"Only {len(picks)} candidate(s) passed; never pad the list with weaker videos. Say how "
                          "many were found and why the rest were excluded.")
    if args.write and picks:
        history["days"][day] = picks
        write_json(directory / "picks.json", history)
        result["written"] = True
    print(json.dumps(result, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("path")
    command.add_argument("--workspace", required=True)
    command.add_argument("--platform", required=True, choices=PLATFORMS)
    command.add_argument("--handle", required=True)
    command = commands.add_parser("ingest")
    command.add_argument("--library", required=True)
    command.add_argument("--snapshot", required=True)
    command.add_argument("--handle")
    command = commands.add_parser("posts")
    command.add_argument("--library", required=True)
    command.add_argument("--limit", type=int, default=40)
    command = commands.add_parser("pillars")
    command.add_argument("--library", required=True)
    command.add_argument("--clusters", required=True)
    command.add_argument("--choose")
    command.add_argument("--write", action="store_true")
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
    command = commands.add_parser("review-facts")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--checkpoint", required=True, choices=CHECKPOINT_ORDER)
    command = commands.add_parser("record-review")
    command.add_argument("--library", required=True)
    command.add_argument("--content-id", required=True)
    command.add_argument("--checkpoint", required=True, choices=CHECKPOINT_ORDER)
    command.add_argument("--report", required=True)
    command = commands.add_parser("comments")
    command.add_argument("--envelope", required=True)
    command.add_argument("--limit", type=int, default=30)
    command = commands.add_parser("transcript")
    command.add_argument("--envelope", required=True)
    command = commands.add_parser("evidence")
    command.add_argument("--dir", required=True)
    command.add_argument("--tool")
    command = commands.add_parser("candidates")
    command.add_argument("--collection", required=True)
    command = commands.add_parser("pick")
    command.add_argument("--library", required=True)
    command.add_argument("--enrichment", action="append", required=True)
    command.add_argument("--count", type=int, default=3)
    command.add_argument("--min-multiple", type=float, default=2.0)
    command.add_argument("--date")
    command.add_argument("--write", action="store_true")
    args = parser.parse_args()
    handlers = {"path": cmd_path, "ingest": cmd_ingest, "posts": cmd_posts, "pillars": cmd_pillars,
                "set-pillar": cmd_set_pillar, "set-profile": cmd_set_profile, "show": cmd_show, "due": cmd_due,
                "review-facts": cmd_review_facts, "record-review": cmd_record_review, "comments": cmd_comments,
                "transcript": cmd_transcript, "evidence": cmd_evidence, "candidates": cmd_candidates, "pick": cmd_pick}
    handlers[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("Creator library operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
