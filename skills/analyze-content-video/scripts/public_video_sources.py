"""Read the public-video support list this Skill ships in references/public-video-sources.v1.json.

The list says which platforms single-video analysis accepts, the evidence-id prefix of each, how its
links name a video, and which public counts it publishes. Scripts read it instead of keeping their
own platform tables.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

# 清单是 kabo 生成的 public-video-sources.v1（仓库根 contracts/ 下钉一份，本 Skill 的 references/ 下放逐字相同的
# 副本，Skill 单独安装时也带着它）。这里只读，不在运行时下载或改写。
SOURCES_FILE = Path(__file__).resolve().parents[1] / "references" / "public-video-sources.v1.json"
SCHEMA_VERSION = "public-video-sources.v1"
METRICS = ("views", "likes", "comments", "shares", "saves")
# 查询参数里的视频 id 只收这些字符：参数值是用户链接里的任意文本，不能原样当 id。
QUERY_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


@lru_cache(maxsize=1)
def _sources() -> dict[str, dict[str, Any]]:
    document = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{SOURCES_FILE.name} is not a {SCHEMA_VERSION} support list")
    table: dict[str, dict[str, Any]] = {}
    for source in document.get("sources") or []:
        identifier = source.get("id") if isinstance(source, dict) else None
        if not isinstance(identifier, str) or not identifier or identifier in table:
            raise ValueError(f"{SOURCES_FILE.name} has a missing or repeated platform id")
        table[identifier] = source
    if not table:
        raise ValueError(f"{SOURCES_FILE.name} lists no platforms")
    return table


def platform_ids() -> tuple[str, ...]:
    """Every accepted platform id, in the list's order."""
    return tuple(_sources())


def source(platform: str) -> dict[str, Any] | None:
    return _sources().get(platform) if isinstance(platform, str) else None


def content_id_prefix(platform: str) -> str | None:
    entry = source(platform)
    return entry.get("content_id_prefix") if entry else None


def label(platform: str) -> str | None:
    entry = source(platform)
    return entry.get("label") if entry else None


def publishes(platform: str, metric: str) -> bool:
    """Whether the platform publishes this public count. Unknown platforms and metrics publish nothing."""
    entry = source(platform)
    return bool(entry and (entry.get("public_metrics") or {}).get(metric) is True)


def media_call_metadata_labels() -> list[str]:
    """Labels of the platforms whose metadata comes from the media call's metadata operation."""
    return [entry["label"] for entry in _sources().values() if entry.get("metadata_route") == "media_call"]


def match_url(url: Any) -> dict[str, Any] | None:
    """Which listed platform a link belongs to, and its video id when the link itself carries one.

    Returns ``{"platform", "kind": "video", "id"}``, ``{"platform", "kind": "short_link", "id": None}``
    (the server must resolve it first) or None (not a listed video page).
    """
    # 与 kabo 的 matchPublicVideoSource 同一套口径（packages/creator/src/observation/public-video-sources.ts）：
    # 只认 https、无内嵌凭据、默认端口；主机逐个精确比较，不做后缀匹配；按 url_patterns 依次试，第一个捕获组是 id，
    # 没有捕获组（或捕获组没参与匹配）的那条从 query_id_params 取 id，同名参数出现不止一次就不认；
    # 都不匹配时，命中 short_link_path_patterns 的是要先解析的分享链接，否则不是视频页。认不出来不猜。
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or port is not None:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    for identifier, entry in _sources().items():
        if host in entry.get("short_link_hosts", []):
            return {"platform": identifier, "kind": "short_link", "id": None}
        if host not in entry.get("page_hosts", []):
            continue
        query = parse_qs(parts.query, keep_blank_values=True)
        for pattern in entry.get("url_patterns", []):
            match = re.search(pattern, path)
            if not match:
                continue
            found = match.group(1) if match.re.groups else None
            if found is None:
                candidates = [query[name][0] for name in entry.get("query_id_params", [])
                              if len(query.get(name, [])) == 1]
                found = next((value for value in candidates if QUERY_ID.match(value)), None)
            if found:
                return {"platform": identifier, "kind": "video", "id": found}
        if any(re.search(pattern, path) for pattern in entry.get("short_link_path_patterns", [])):
            return {"platform": identifier, "kind": "short_link", "id": None}
        return None
    return None


def content_id_from_url(platform: str, url: Any) -> str | None:
    """The video id a page link of this platform names, or None (short links, other hosts, other platforms)."""
    found = match_url(url)
    return found["id"] if found and found["platform"] == platform and found["kind"] == "video" else None
