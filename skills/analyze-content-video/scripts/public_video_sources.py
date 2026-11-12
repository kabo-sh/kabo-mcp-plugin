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


def content_id_from_url(platform: str, url: Any) -> str | None:
    """The video id a page link names, or None (short links, unknown hosts, other platforms)."""
    entry = source(platform)
    if entry is None or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    # 主机名逐个精确比较，不做后缀匹配：清单把 www. 与 m. 都单独列出。
    if host not in entry.get("page_hosts", []):
        return None
    for pattern in entry.get("url_patterns", []):
        match = re.search(pattern, parts.path or "/")
        if match:
            return match[1]
    query = parse_qs(parts.query)
    for name in entry.get("query_id_params", []):
        for value in query.get(name, []):
            if QUERY_ID.match(value):
                return value
    return None
