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
# 复盘的三个时点；band 是「算作这个时点」的观测区间（小时），用来给别的作品取同龄基线。
# 每天只看一次账号，所以 24 小时时点的区间放宽到 24–48 小时：一天一次的观测正好有一次落在里面。
CHECKPOINTS = {"1h": (1.0, 3.0), "24h": (24.0, 48.0), "7d": (168.0, 192.0)}
CHECKPOINT_ORDER = ("1h", "24h", "7d")
# 默认只做 24 小时复盘；1 小时与 7 天是可选时点（due --with-optional）。
LATE_AFTER_HOURS = 48.0
# 发布满 72 小时的作品才算播放基本稳定，用于内容支柱表现和账号常规水平。
SETTLED_HOURS = 72.0
# 画像里的主打内容最多取 4 项作为支柱（与后台画像的上限一致）。
MAX_PILLARS = 4
# 照片、图文不是视频，没有播放量，不进素材库。
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
    # 只打印目录：三个 Skill 都会调用它，其中两个无人值守，这里不能带任何要对创作者说的话。
    directory = library_path(args.workspace, args.platform, args.handle)
    say({"library": str(directory), "exists": (directory / "library.json").exists()})


def cmd_history_request(args):
    """The exact collect_account_history arguments for this account; pass them to the tool unchanged."""
    if args.channel_id and args.platform != "youtube":
        fail("--channel-id is only for YouTube")
    account = {"channel_id": args.channel_id} if args.channel_id else {"handle": normalize_handle(args.handle)}
    full = args.depth == "full"
    # 建库那一次读得多（账号常规水平与同龄基线的样本更稳），每天的复盘只需要最近的作品。
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
            owner = creators[0]  # YouTube 的频道名与自定义链接可能不同；只读了一个账号时它就是本人
        if owner is None:
            fail(f"The snapshot holds no posts from @{handle}; check the handle and platform")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "reviews").mkdir(exist_ok=True)
        # 绑定时间取服务端抓取时间：此后发布的作品才进入复盘。
        write_json(directory / "library.json", {
            "format": LIBRARY_FORMAT, "platform": platform, "handle": handle,
            "creator_id": owner.get("creator_id"), "bound_at": iso(observed), "fresh": False,
            "niche": None, "pillars": [], "followers": [], "profile": {}, "updated_at": iso(observed),
        })
    library, store = load_library(directory)
    if library["platform"] != platform:
        fail(f"This library is for {library['platform']}, not {platform}")
    if library.get("fresh") and any(post.get("observations") for post in (store.get("posts") or {}).values()):
        # 库里已有上一次的读数，说明宿主保留了文件：此后的复盘有历史可比。
        library["fresh"] = False
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


# 开场两句由脚本给出，模型换成创作者的语言后各发一条，再问一个问题（账号）。说的必须是这次真会发生的事：
# 先读作品、一起定支柱（本地提议、创作者确认后同步到 Kabo），推荐来自后台的「为你推荐」。
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
    # 读完作品马上要对创作者说的话：条数、常规播放、最好的一条。模型只负责换成对方的语言原样转述。
    best = max(settled_views(posts), key=lambda row: row[1], default=None)
    tell = f"I read {len(posts)} of your videos."
    if typical:
        tell += f" A typical one gets about {int(round(typical))} views."
    if best and typical:
        title = (best[0].get("title") or "").strip().splitlines()[0][:60] if (best[0].get("title") or "").strip() else "your best one"
        tell += f" Your best so far, \"{title}\", has {best[1]} views, {ratio(best[1], typical)} times that."
    say({"tell_creator_now": tell, "handle": library["handle"], "platform": library["platform"],
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


# ---------------------------------------------------------------- local pillar proposal（本地提议，创作者确认后同步到 Kabo）

# 支柱的形状与长度上限照后台 update_content_preferences 的 declare_pillars（kabo#2185）：在这里先查，超限就让助手改短，
# 不等后台拒。
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

    原来写死的「中位播放 ≥ 0.8 倍、第二支柱 ≥ 20% 播放」不再由脚本裁定：这里只给各组的条数、中位播放、
    播放占比作参考，决定权在创作者；这些数字是本地对这次读到的作品的计算，不是 Kabo 的统计结论。"""
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
        # 版本冲突：重读 get_creator_profile 拿新版本，再交一次（只一次）。整份替换，重交不会叠加。
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

    宿主存下来的可能是整份 MCP 结果（structuredContent，或只有 content[0].text 里的 JSON），也可能已经是
    结构化内容本身；三种都认。"""
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

    只整理后台画像里的主打内容（signature content），不从作品里另行推导；后台没有就是没有。"""
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
    # 赛道先读顶层 niche：prepare_creator_profile 推断或创作者口述后写入的赛道在这里（kabo get_creator_profile 组装处
    # 的 niche / nicheId）；没有复盘诊断时 diagnosis 里是空的（Codex 实测 @veritasium：顶层 "Science education"，
    # diagnosis 无赛道）。顶层为空再回退到诊断里的两处。
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
            # 合并项（m_…）的 origin.baseIds 列出合并进来的原项；单项就是它自己。刷新支柱时据此把作品归到合并后的项。
            "profile_base_ids": [str(base) for base in ((item.get("origin") or {}).get("baseIds") or [item.get("id")])
                                 if isinstance(base, (str, int)) and str(base)],
            # 画像的 share 是条数占比（contentCount / 进了格式的作品数），不是播放占比。
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
            # 创作者声明的支柱（get_creator_profile 带 pillars: true 时才有这个键；没带或旧后台时为 None，不当成「没有」）。
            "declared_pillars": declared_pillars(structured),
            "update_context": {"account_id": account.get("id"), "expected_version": preferences.get("version") or 0,
                               "basis": first_text(generated or (base or {}).get("generatedAt"))},
            "note": None if candidates else ("Kabo has no content pillars for this account yet (too few comparable posts). "
                                             "Tell the creator so in one line and go on; never group the posts yourself.")}


def cmd_profile_pillars(args):
    say(read_profile(args.profile))


# ---------------------------------------------------------------- waiting on Kabo

# 后台还在生成时严格按 retry_after_seconds 再查，不缩短也不加长；总等待有上限，先到者为准。
# 宿主的单次命令与整次运行都有时限，不能无限等。两处上限按后台的真实节奏定（kabo#2176）：
# - 每日推荐：后台通常给 120 秒，补画像阶段给 300 秒。首次之后最多再查 3 次、累计最多 600 秒，
#   正好容得下两次 300 秒的补画像等待；定时运行也用这个上限，超限就随下次运行送达。
# - 画像：后台一档 60 秒，推断赛道加生成画像整条链路要几分钟。首次之后最多再查 8 次、累计最多 480 秒；
#   超限就说稍后再看，引导对话继续往下走。
# 下一次要等的时间会超出剩余额度时直接停，不提前去查（提前查只会再拿到一次 generating）。
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


def status_of(payload, is_error):
    # 宿主标了 isError（工具错误，如 validation_error、not_found）、没有 status 或 status 不是字符串的，
    # 一律按失败处理，并把原样内容带回去报告。
    status = payload.get("status")
    if is_error or not isinstance(status, str) or not status:
        return "failed"
    return status


def failure_detail(payload):
    # failure_code 是契约字段；工具错误只有 message / error，宽容读取。
    return (first_text(payload.get("failure_code")) or first_text(payload.get("message"))
            or first_text(payload.get("error")))


def needs_write_access(payload, is_error):
    # 宿主的 Kabo 授权里没有 workspace:write 时，写工具返回 Insufficient scope 的工具错误（不是某个 status）。
    # 这是授权问题，重试没用：要创作者在宿主里重新授权并批准写权限。
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
    "wait": "Still building your profile.",
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
            result["tell_creator_now"] = PROFILE_STATUS_LINES["first_wait" if args.attempt == 1 else "wait"]
        else:
            result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["gave_up"]})
    elif status == "niche_required" and not args.niche_sent:
        # 后台从公开内容推断不出赛道：问创作者一句话，原话作为 niche 重试一次。模型不能替创作者编。
        result.update({"action": "ask_niche", "tell_creator_now": PROFILE_STATUS_LINES["niche_required"],
                       # niche_not_inferred，或分析器的错误码（如 profile_private）；只作说明，不改流程。
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
        # 执行偶发（kabo#2180）：retry_after_seconds 很短，到时再调同一个工具后台会自动重跑一次复盘、回 generating。
        # 这类重试与 generating 共用同一个轮询上限（最多再查 8 次、总等待 480 秒）；后台 24 小时内至多重跑 2 次，
        # 到上限会回 retryable=false。不说成「作品不够」。
        code = failure_detail(payload)
        decision = poll_decision(payload, args.attempt, args.waited, POLL_LIMITS["profile"])
        result.update(decision)
        result["failure_code"] = code
        if decision["action"] == "wait":
            # 失败码只放在 failure_code 字段给助手看，不进对创作者说的话。
            line = PROFILE_STATUS_LINES["classification_unavailable"] if code == "classification_unavailable" else (
                PROFILE_STATUS_LINES["retrying"])
            result["tell_creator_now"] = line
        else:
            result.update({"action": "continue_without_profile", "tell_creator_now": PROFILE_STATUS_LINES["gave_up"],
                           "reported": reported(payload)})
    else:
        # failed（retryable=false 或工具错误），以及契约之外的任何 status：按失败处理，原样带回，不自己推导画像；
        # 有冷却就说大约多久后能再试。
        line = PROFILE_STATUS_LINES["failed"]
        when = about_time(payload.get("retry_after_seconds"))
        if when:
            line += " " + PROFILE_STATUS_LINES["retry_in"].format(when=when)
        result.update({"action": "continue_without_profile", "tell_creator_now": line, "retry_in": when,
                       "failure_code": failure_detail(payload), "reported": reported(payload)})
    say(result)


def cmd_bootstrap(args):
    """A new library built by review-new-posts when none exists: pillars, if any, come from the creator's Kabo profile.

    第一次运行（引导对话不再在本地建库）和不留文件的宿主每次运行都走这里。没有画像或画像没有支柱时照样建库，
    复盘与账号回顾照做，只是不带支柱小节。"""
    directory = Path(args.library)
    if (directory / "library.json").exists():
        fail("This library already exists; use it instead of rebuilding it")
    proposal = read_profile(args.profile) if args.profile else None
    # 与 refresh-pillars 同一优先级：创作者声明的支柱 → 后台统计的主打内容 → 没有。
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
    # 回看 48 小时：第一次读历史时按那次的抓取时间定绑定时间，让每条作品恰好在 24–48 小时的那一天进入一次复盘。
    # fresh 表示库里还只有这一次的读数；下一次在同一个库上读到历史时，ingest 把它改成 false。
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

    对齐规则（以后台画像为准，只按画像项的稳定 id 对，不看名字）：
    1. 画像项 id 不变（改名、改话题也一样）：沿用原来的本地 id，作品归属不动。
    2. 原项被合并：新合并项（m_…）的 origin.baseIds 含原项 id，原项的作品归到合并项。
    3. 原项被删除、隐藏、跌出前 4 项，或原合并项被拆开（对应关系不唯一）：作品置为未归类（pillar_id 为空）。
    历史读数与已记录的复盘都不动；"other" 归属保持。"""
    by_item = {str(row.get("profile_item_id")): row for row in old_pillars if row.get("profile_item_id")}
    taken, pillars, moves = set(), [], {}
    # 先给 id 不变的项保留原本地 id，再给新项按名字起 id，避免撞名。
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

    声明的支柱没有后台 id，只按名称（忽略大小写、去首尾空白）对齐；名称变了就置未归类，不做模糊匹配。"""
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
        # 读不到画像：沿用上一次的支柱，在复盘与回顾的 limits 里说明，不让整次复盘失败。
        library["pillars_refresh"] = {"ok": False, "at": when, "reason": problem or "no profile result"}
        write_json(directory / "library.json", library)
        say({"refreshed": False, "reason": library["pillars_refresh"]["reason"],
             "pillars": [row["id"] for row in library.get("pillars") or []], "pillars_read_at": library.get("pillars_read_at")})
        return
    old = library.get("pillars") or []
    sync = library.get("pillars_sync") or {}
    if sync.get("state") == "pending":
        # 本地有创作者确认、还没同步到 Kabo 的支柱：不拿后台的结果盖掉它，只补赛道；等补同步成功再以后台为准。
        niche = proposal.get("niche")
        if niche:
            library["niche"] = {"text": niche, "source": "kabo_profile"}
        library.update({"pillars_refresh": {"ok": True, "at": when}, "updated_at": when})
        write_json(directory / "library.json", library)
        say({"refreshed": False, "reason": "local pillars not yet synced to Kabo; kept as they are",
             "pillars": [row["id"] for row in old], "sync": "pending"})
        return
    # 支柱来源的优先级：创作者声明的（declaredPillars 非空）→ 后台统计的主打内容 → 没有。
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


# 会写进复盘与回顾、转述给创作者的话：不出现 library、run、host 之类的词。
AGE_WORDS = {"1h": "1 hour", "24h": "24 hours", "7d": "7 days"}
FIRST_READING_LINE = ("This is the first time I've read your account here, so there is no earlier reading to compare "
                      "with yet (no follower change either). If this app doesn't keep files between days, every report "
                      "starts like this, and a post may be reviewed again.")


def pillar_refresh_limit(library):
    state = library.get("pillars_refresh") or {}
    # 对创作者说的话：原因（state["reason"]）只留在库里给助手排障，不念出来。
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

def remake_note(platform):
    # 复刻只接 10 分钟以内的口播或旁白视频；后台推荐不给时长，是否符合条件由复刻自己在收费前检查，这里不臆测。
    if platform is None or platform in ("instagram", "youtube", "tiktok"):
        return "checked first: before a remake, Kabo checks whether this video qualifies"
    return "not supported for this platform"


# 每日推荐只取后台 get_for_you_videos 的结果：后台按「与账号同领域、语言匹配」筛选并按公开播放量排序，
# 规则以后台为准。这里只做展示上的限制：每天最多 3 条；先 7 天、再 30 天、再 24 小时；跳过以前某天展示过的、
# 创作者本人的、与已选同一作者的；不够就有几条给几条，绝不凑数。
PICK_WINDOWS = ("7d", "30d", "24h")
PICKS_PER_DAY = 3
# 按窗口的相对播放量门槛：低于该窗口第 1 名播放量 10% 的不选，没有 views 的也不选。
# 后台按播放量排序，但一个窗口里常常只有榜首一条真正出圈（实测 YouTube 7d：63,831 后面是 1,266、1,240），
# 照 rank 取前 3 会把明显没起量的视频当成推荐。只用后台给的 views，不引入作者基线倍数这类后台没有的口径；
# 每个窗口用自己的榜首算门槛，补位时也一样。过门槛的不足 3 条就不凑数。
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


# 链接里标识视频的查询参数：YouTube 的 watch 链接只靠 ?v= 区分视频。其余查询参数（igsh、si、utm_…）是分享追踪，去掉。
# 曾经整串丢掉查询参数，所有 youtube.com/watch?v=… 被当成同一条视频（Codex 实测 30 条只选出 1 条）。
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
    for key in item.get("keys") or []:  # 已记录的推荐自带 keys
        if isinstance(key, str) and key.strip():
            keys.add(key.strip())
    return keys


def platform_of(item):
    # 缺 platform 时从链接的域名认；认不出就是 None（复刻提示退回「复刻前会先检查」）。
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

    作者未知（null 或空串）时不参与「同一作者不重复」：YouTube 结果目前不给 author_handle，
    把空值当成同一个作者会只剩一条。后台若补上 author_id 就优先用它。"""
    author_id = item.get("author_id")
    if isinstance(author_id, (str, int)) and not isinstance(author_id, bool) and str(author_id).strip():
        return "id:" + str(author_id).strip()
    handle = first_text(item.get("author_handle"))
    handle = handle.lstrip("@").lower() if handle else None
    return "handle:" + handle if handle else None


def author_label(item):
    """The author as the creator should see it: a channel name for YouTube, @handle elsewhere.

    kabo#2181 起 YouTube 的 author_handle 是频道名称（视频接口不给 @handle，可能重名），不能加 @；
    Instagram / TikTok 是平台 handle，加 @。由脚本给出，模型不必自己判断加不加 @。"""
    handle = first_text(item.get("author_handle"))
    if not handle:
        return "author not supplied"
    if platform_of(item) == "youtube":
        return handle
    return "@" + handle.lstrip("@")


def own_handle_of(item):
    # 本人作品后台已排除；这里只是在给了作者名时再核一次。作者未知时不判。
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
                # 同一条视频（content_id 或归一后的链接相同）出现在多个时间窗；只看视频标识，不看作者。
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
        # 同一天再跑（定时任务重试、手动再叫）：不重选、不覆盖，原样给出已记录的那份。
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
            # 零条的日子也记下：今天已查过，同一天再跑不再触发。
            directory.mkdir(parents=True, exist_ok=True)
            history["days"][day] = picks
            write_json(directory / "picks.json", history)
            result["recorded"] = True
    elif status == "generating":
        decision = poll_decision(payload, args.attempt, args.waited, POLL_LIMITS["for_you"])
        result.update(decision)
        if decision["action"] == "wait":
            result["progress_line"] = "Kabo is still preparing today's picks for you."
        else:
            result["message"] = "Kabo is still preparing today's picks; you'll get them next time."
    elif status == "not_eligible":
        reason = first_text(payload.get("reason")) or "unknown"
        result.update({"action": "stop", "reason": reason,
                       # 距离可再次触发的秒数；没有绑定账号时为 null。
                       "retry_after_seconds": seconds(payload.get("retry_after_seconds")),
                       # 未知原因码只在 reason 字段里，不念给创作者。
                       "message": FOR_YOU_NOT_ELIGIBLE.get(reason, "Kabo can't make picks for this account right now.")})
    else:
        # failed、工具错误（validation_error、not_found），以及契约之外的任何 status：按失败处理，原样报告，不搜索、不兜底。
        # failed 不轮询（kabo#2180 起一律 retryable=false；能立即重来的情形后台直接回 generating）。
        # retry_after_seconds 是距下次可触发的秒数：换成「大约多久后再来」。旧后台的 retryable=true 加约 24 小时同样处理。
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


HANDLERS = {"path": cmd_path, "opening": cmd_opening, "posts": cmd_posts, "media-request": cmd_media_request,
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