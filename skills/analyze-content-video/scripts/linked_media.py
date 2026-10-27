"""Bind host-read still images to their original connector response, without video timestamps."""
from __future__ import annotations

import base64
import hashlib
import math
from pathlib import Path

SCHEMA = "linked-media-evidence.v1"


def image_mime(body: bytes) -> str | None:
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


def bind(bundles: list[dict], envelopes: list[dict], request: dict,
         analysis_root: Path | None) -> dict | None:
    if not bundles:
        return None
    if analysis_root is None:
        raise ValueError("linked media needs this run's analysis directory (--snapshot-root)")
    if analysis_root.absolute() != analysis_root.resolve(strict=False):
        raise ValueError("linked media analysis directory must not contain symlinks")
    source = request.get("source") or {}
    result = None
    delivered: dict[int, dict] = {}
    pending: list[tuple[Path, bytes]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            raise ValueError("linked media must be an object")
        identity, provenance = bundle.get("identity") or {}, bundle.get("source") or {}
        if not isinstance(identity, dict) or not isinstance(provenance, dict):
            raise ValueError("invalid linked media identity/source")
        if (identity.get("platform") != source.get("platform")
                or bundle.get("original_url") != source.get("url")
                or str(bundle.get("post_id")) != str(source.get("content_id"))):
            raise ValueError("linked media does not identify the requested post")
        matches = [e for e in envelopes if e.get("request_id") == provenance.get("request_id")
                   and e.get("connector_id") == provenance.get("connector_id")
                   and e.get("operation") == provenance.get("operation")
                   and e.get("status") in {"completed", "completed_partial"}]
        if not provenance.get("request_id") or not matches:
            raise ValueError("load the original linked-post connector envelope before building evidence")
        envelope = matches[0]
        # Web batches may project one upstream response under distinct local evidence refs.
        comparable = lambda e: {k: v for k, v in e.items() if k not in {"evidence_ref", "linked_media"}}
        if any(comparable(e) != comparable(envelope) for e in matches[1:]):
            raise ValueError("conflicting copies of the linked-post connector response")
        if envelope.get("raw_sha256") != provenance.get("raw_sha256"):
            raise ValueError("linked media source hash differs from its connector response")
        media_type = bundle.get("media_type")
        if media_type not in {"image", "image_carousel", "video", "unknown"}:
            raise ValueError("invalid linked media type")
        count = bundle.get("returned_count")
        if type(count) is not int or not 0 <= count <= 128:
            raise ValueError("invalid returned image count")
        current = {"media_type": media_type, "returned_count": count,
                   "expected_count": None, "completeness": "unknown",
                   "source_request_id": provenance["request_id"]}
        if result is not None and result != current:
            raise ValueError("linked image batches describe different post snapshots")
        result = current
        images = bundle.get("images")
        if not isinstance(images, list) or len(images) > 4:
            raise ValueError("invalid linked image batch")
        if images and media_type not in {"image", "image_carousel"}:
            raise ValueError("non-photo linked media cannot supply still-slide evidence")
        for item in images:
            if not isinstance(item, dict):
                raise ValueError("linked image must be an object")
            index = item.get("index")
            if type(index) is not int or not 1 <= index <= count:
                raise ValueError("linked image index is outside its original positions")
            data = item.get("data")
            if not isinstance(data, str) or len(data) > 1_400_000:
                raise ValueError("linked image bytes are missing or too large")
            body = base64.b64decode(data, validate=True)
            mime = image_mime(body)
            if not mime or mime != item.get("mime_type") or len(body) > 1024 * 1024:
                raise ValueError("linked image bytes do not match the declared format/limit")
            digest = hashlib.sha256(body).hexdigest()
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
            target = analysis_root / f"linked-image-{digest}.{ext}"
            image = {"image_id": f"image-{index}-{digest[:16]}", "index": index,
                     "status": "available", "path": str(target), "sha256": digest}
            if index in delivered and delivered[index] != image:
                raise ValueError("conflicting image bytes at the same slide position")
            delivered[index] = image
            pending.append((target, body))
    # Validate every batch before writing; never replace an existing, changed image.
    for target, body in pending:
        if target.is_symlink() or (target.exists() and target.read_bytes() != body):
            raise ValueError("linked image binding would overwrite different bytes")
    analysis_root.mkdir(parents=True, exist_ok=True)
    for target, body in pending:
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(body)
            target.chmod(0o600)
    result["items"] = [delivered.get(i, {"index": i, "status": "unavailable"})
                       for i in range(1, result["returned_count"] + 1)]
    result["status"] = "available" if delivered else "unavailable"
    return result


def public_post_facts(envelopes: list[dict], source: dict) -> dict | None:
    """Project existing TikTok fields; retain native counter names and unknowns."""
    if source.get("platform") != "tiktok":
        return None
    for envelope in reversed(envelopes):
        if (envelope.get("connector_id"), envelope.get("operation")) != ("tiktok-search", "get_video"):
            continue
        if envelope.get("status") not in {"completed", "completed_partial"}:
            continue
        post = (envelope.get("data") or {}).get("video") or {}
        if str(post.get("aweme_id")) != str(source.get("content_id")):
            raise ValueError("TikTok post identity differs from the analysis request")
        metrics = []
        for name in ("play_count", "digg_count", "comment_count"):
            value = (post.get("statistics") or {}).get(name)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                metrics.append({"native_name": name, "value": value, "equals_owner_metric": None,
                                "note": "Public post counter; not reach, retention or an owner metric."})
        caption = post.get("desc")
        return {"caption": caption if isinstance(caption, str) else None,
                "metrics": metrics}
    return None
