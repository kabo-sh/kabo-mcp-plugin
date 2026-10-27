#!/usr/bin/env python3
"""Read public view/like/comment metrics under platform-native keys."""

from __future__ import annotations

from typing import Any

PUBLIC_METRIC_STATUSES = frozenset({"available", "zero"})
PUBLIC_METRIC_ALIASES = {
    "views": ("views", "view_count", "viewCount", "play_count", "plays"),
    "likes": ("likes", "like_count", "likeCount"),
    "comments": ("comments", "comment_count", "commentCount"),
}


def public_metric_entry(metrics: Any, name: str) -> dict[str, Any] | None:
    """Read a public metric by canonical name. Platform native keys count as the same metric."""
    if not isinstance(metrics, dict):
        return None
    for key in PUBLIC_METRIC_ALIASES.get(name, (name,)):
        entry = metrics.get(key)
        if isinstance(entry, dict) and entry.get("status") in PUBLIC_METRIC_STATUSES:
            return entry
    return None
