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

# The list is kabo's generated public-video-sources.v1 (one copy pinned under the repository's contracts/, and a
# byte-identical copy under this Skill's references/ so a standalone Skill install carries it). It is only read
# here, never downloaded or rewritten at run time.
SOURCES_FILE = Path(__file__).resolve().parents[1] / "references" / "public-video-sources.v1.json"
SCHEMA_VERSION = "public-video-sources.v1"
METRICS = ("views", "likes", "comments", "shares", "saves")
# A video id taken from a query parameter may contain only these characters: the value is arbitrary text from the
# user's link and cannot be used as an id as is.
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
    # The same rules as kabo's matchPublicVideoSource (packages/creator/src/observation/public-video-sources.ts):
    # https only, no embedded credentials, default port; hosts compared exactly, never by suffix; url_patterns
    # tried in order, the first capture group is the id, and a pattern without one (or whose group did not take
    # part in the match) takes the id from query_id_params, refusing a parameter that appears more than once.
    # When nothing matches, a short_link_path_patterns hit is a share link to resolve first; otherwise it is not
    # a video page. Nothing unrecognised is guessed.
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
