"""Carry a host-read TikTok post's identity/type into its account snapshot, offline."""

from __future__ import annotations

import copy
import re
from urllib.parse import urlsplit, urlunsplit


def share_key(value: str) -> str:
    """Compare public TikTok share identities without tracking query parameters."""
    if not isinstance(value, str):
        raise ValueError("linked evidence URL must be a string")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (host == "tiktok.com" or host.endswith(".tiktok.com")):
        raise ValueError("linked evidence must identify a public TikTok URL")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("linked evidence URL has unexpected authority")
    return urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))


def link_record(evidence: dict) -> dict:
    """Accept the Web envelope only when its request and provenance bind the media."""
    if not isinstance(evidence, dict) or "linked_media" not in evidence:
        return evidence
    linked = copy.deepcopy(evidence["linked_media"])
    if not isinstance(linked, dict) or not isinstance(linked.get("source"), dict):
        raise ValueError("Web linked evidence must retain its media source")
    source = linked["source"]
    if evidence.get("status") not in ("completed", "completed_partial"):
        raise ValueError("Web linked evidence has no usable connector response")
    for key in ("connector_id", "operation", "request_id", "raw_sha256"):
        if not isinstance(evidence.get(key), str) or not evidence[key] or evidence[key] != source.get(key):
            raise ValueError("Web linked evidence source differs from its connector response")
    retrieved = evidence.get("retrieved_at")
    if not isinstance(retrieved, str) or not retrieved or source.get("retrieved_at", retrieved) != retrieved:
        raise ValueError("Web linked evidence must retain its retrieval time")
    source["retrieved_at"] = retrieved
    request = evidence.get("request")
    if not isinstance(request, dict) or share_key(request.get("url")) != share_key(linked.get("original_url")):
        raise ValueError("Web linked evidence is not bound to its connector request")
    identity = linked.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("Web linked evidence must retain its platform identity")
    # The Web host projects these fields on the outer envelope instead of the media record.
    supplied = {"original_url": linked.get("original_url"), "resource_kind": "post",
                "resource_id": linked.get("post_id"),
                "read": {"connector_id": source["connector_id"], "operation": source["operation"], "params": request}}
    if any(key in identity and identity[key] != value for key, value in supplied.items()):
        raise ValueError("Web linked evidence has conflicting request identity")
    identity.update(supplied)
    return linked


def bind_link(evidence: dict, question: str) -> tuple[str, str, str, str]:
    """Require the host envelope to describe the requested link and a resolved post."""
    evidence = link_record(evidence)
    if not isinstance(evidence, dict) or evidence.get("schema_version") != "linked-media-evidence.v1":
        raise ValueError("expected host linked-media-evidence.v1")
    original = evidence.get("original_url")
    if not isinstance(original, str) or not isinstance(evidence.get("resolved_url"), str):
        raise ValueError("linked evidence must name its original and resolved URLs")
    requested = [url.rstrip('.,;!?)]}>\"') for url in re.findall(r"https://[^\s<>]+", question)]
    def is_tiktok(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return host == "tiktok.com" or host.endswith(".tiktok.com")

    if share_key(original) not in [share_key(url) for url in requested if is_tiktok(url)]:
        raise ValueError("linked evidence is not bound to a URL in the original question")
    identity = evidence.get("identity") or {}
    source = evidence.get("source") or {}
    if not isinstance(identity, dict) or not isinstance(source, dict):
        raise ValueError("linked evidence identity/source must be objects")
    read = identity.get("read") or {}
    if not isinstance(read, dict) or not isinstance(read.get("params"), dict):
        raise ValueError("linked evidence must retain its read request")
    post_id = str(evidence.get("post_id") or "")
    resolved = urlsplit(share_key(evidence["resolved_url"]))
    match = re.fullmatch(r"/@([^/]+)/(photo|video)/(\d+)", resolved.path)
    original_post = re.search(r"/(?:photo|video)/(\d+)/?$", urlsplit(original).path)
    media_format = {"image_carousel": "tiktok_photo", "video": "tiktok_video"}.get(evidence.get("media_type"))
    if (identity.get("platform") != "tiktok" or identity.get("resource_kind") != "post"
            or str(identity.get("resource_id")) != post_id or not post_id.isdigit()
            or (original_post is not None and original_post[1] != post_id)
            or not match or match[3] != post_id or not media_format
            or (match[2] == "photo") != (media_format == "tiktok_photo")
            or share_key(identity.get("original_url", "")) != share_key(original)
            or share_key((read.get("params") or {}).get("url", "")) != share_key(original)
            or not source.get("connector_id") or source.get("connector_id") != read.get("connector_id")
            or not source.get("operation") or source.get("operation") != read.get("operation")
            or not source.get("request_id") or not source.get("retrieved_at")
            or not re.fullmatch(r"[a-f0-9]{64}", source.get("raw_sha256", ""))):
        raise ValueError("linked evidence has incomplete or conflicting post identity/type")
    return post_id, match[1], media_format, original


def bound_handle(evidence: dict, question: str, requested: str) -> str:
    """Use the resolved post owner only for the account named by that bound link."""
    _, resolved, _, original = bind_link(evidence, question)
    original_post = re.fullmatch(r"/@([^/]+)/(?:photo|video)/\d+/?", urlsplit(original).path)
    names = {resolved.casefold()}
    if original_post:
        names.add(original_post[1].casefold())
    if requested.lstrip("@").casefold() not in names:
        raise ValueError("linked post does not bind the requested account")
    return resolved


def apply_link(snapshot: dict, evidence: dict, question: str) -> dict:
    """Preserve metric evidence; change only the bound post's URL/type and provenance."""
    evidence = link_record(evidence)
    post_id, handle, media_format, original = bind_link(evidence, question)
    result = copy.deepcopy(snapshot)
    matches = [item for item in result.get("items", []) if str(item.get("content_id")) == post_id]
    if len(matches) != 1:
        raise ValueError("linked post must occur exactly once in the account snapshot")
    item = matches[0]
    creators = [creator for creator in result.get("creators", [])
                if str(creator.get("creator_id")) == str(item.get("creator_id"))]
    if len(creators) != 1 or str(creators[0].get("handle", "")).lstrip("@").casefold() != handle.casefold():
        raise ValueError("linked post does not belong to the resolved snapshot account")
    item.update(url=original, format=media_format, format_confidence="explicit", format_source="linked_media")
    result["source"]["linked_media_evidence"] = {
        "content_id": post_id, "original_url": original,
        "resolved_url": evidence["resolved_url"], "media_type": evidence["media_type"],
        "source": copy.deepcopy(evidence["source"]),
        "returned_count": evidence.get("returned_count"), "expected_count": evidence.get("expected_count"),
        "completeness": evidence.get("completeness"),
    }
    if media_format == "tiktok_photo" and evidence.get("completeness") != "complete":
        note = ("The linked post's total image count and complete image coverage are unknown."
                if evidence.get("expected_count") is None
                else "The linked post's returned images do not establish complete image coverage.")
        limitations = result["source"].setdefault("limitations", [])
        if note not in limitations:
            limitations.append(note)
    return result
