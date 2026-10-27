#!/usr/bin/env python3
"""Project saved comment responses into idea evidence without semantic analysis or network requests."""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse


def has_comment_text(row):
    """Attachment placeholders are not readable audience feedback."""
    text = row.get("text")
    return isinstance(text, str) and bool(text.strip()) and not re.fullmatch(
        r"(?:\s*\[(?:photo|image|sticker|gif)\]\s*)+", text, flags=re.I
    )


def project(paths, base):
    """Project one video's saved pages, preserving provenance and sampling limits."""
    sources, comments, seen, videos = [], [], {}, set()
    if not paths:
        raise ValueError('At least one comment envelope is required')
    limits = [
        'Reply counts do not mean the reply text was retrieved; use only the text and attachment references actually returned.',
        'The comment sample does not represent the whole audience; praise, jokes and like counts do not establish demand for a topic.',
    ]
    for path in paths:
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError('Comment evidence must stay inside its run directory')
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('Expected an envelope object')
        connector = value.get('connector_id')
        operation = value.get('operation')
        allowed = ('list_comments', 'list_comment_replies') if connector == 'tiktok-discovery' else ('list_comments',)
        if connector not in ('youtube-public', 'tiktok-discovery') or operation not in allowed:
            raise ValueError('Expected a native YouTube or TikTok comments envelope')
        if value.get('schema_version') != '1.0' or value.get('status') not in ('completed', 'completed_partial'):
            raise ValueError('Comment collection did not complete')
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in ('evidence_ref', 'retrieved_at')):
            raise ValueError('Missing evidence identity or retrieval time')
        observed = datetime.fromisoformat(value['retrieved_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('Retrieval time must carry a timezone')
        data = value.get('data')
        if not isinstance(data, dict):
            raise ValueError('Expected comment data object')
        rows = data.get('rows')
        if not isinstance(rows, list):
            raise ValueError('Expected comment rows')
        projected_rows = []
        parent_id = data.get('parent_comment_id')
        if operation == 'list_comment_replies' and (not isinstance(parent_id, str) or not re.fullmatch(r'[0-9]{1,32}', parent_id)):
            raise ValueError('Reply page is missing its parent comment identity')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Expected comment row object')
            if operation == 'list_comment_replies' and row.get('parent_comment_id') != parent_id:
                raise ValueError('Reply parent does not match the requested thread')
            projected_rows.append(row)
            replies = row.get('inline_replies') or []
            if not isinstance(replies, list):
                raise ValueError('Expected inline reply array')
            for reply in replies:
                if not isinstance(reply, dict):
                    raise ValueError('Expected reply object')
                if reply.get('parent_comment_id') != row.get('id'):
                    raise ValueError('Inline reply parent does not match its comment')
                projected_rows.append(reply)
        for row in projected_rows:
            comment_id = row.get('id')
            has_media = connector == 'tiktok-discovery' and (row.get('images') or row.get('image_status') == 'referenced_without_url')
            if not isinstance(comment_id, str) or not comment_id or (not isinstance(row.get('text'), str) and not (row.get('text') is None and has_media)):
                raise ValueError('Comment is missing identity or text')
            if not isinstance(row.get('source_url'), str):
                raise ValueError('Expected comment source URL')
            parsed = urlparse(row['source_url'])
            if connector == 'youtube-public':
                video_id = parse_qs(parsed.query).get('v', [''])[0]
                if parsed.scheme != 'https' or parsed.hostname not in ('youtube.com', 'www.youtube.com') or parsed.path != '/watch' or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                    raise ValueError('Expected an explicit YouTube video source URL')
                ref = 'https://www.youtube.com/watch?' + urlencode({'v': video_id, 'lc': comment_id})
            else:
                match = re.fullmatch(r'/(?:@[^/]+/)?video/([0-9]{1,32})/?', parsed.path)
                if parsed.scheme != 'https' or parsed.hostname not in ('tiktok.com', 'www.tiktok.com') or not match:
                    raise ValueError('Expected an explicit TikTok video source URL')
                video_id = match.group(1)
                if data.get('aweme_id') != video_id or not re.fullmatch(r'[0-9]{1,32}', comment_id):
                    raise ValueError('TikTok comment identity does not match its video')
                # 标识不伪装成可跳到单条评论的网页链接。报告同时给原视频 URL。
                ref = 'tiktok:' + video_id + ':comment:' + comment_id
            videos.add((connector, video_id))
            if ref in seen:
                if seen[ref] != row:
                    limits.append('A duplicate comment changed in content or status; keep the first observation rather than merging versions into a fabricated comment.')
                continue
            seen[ref] = row
            comments.append({'ref': ref, 'id': comment_id, 'video_id': video_id, 'text': row['text'], **({key: row[key] for key in ('images', 'image_status', 'parent_comment_id') if key in row} if connector == 'tiktok-discovery' else {}), 'source_url': row['source_url'], 'published_at': row.get('published_at'), 'retrieved_at': value['retrieved_at'], 'evidence_ref': value['evidence_ref']})
        page = data.get('page') or {}
        if not isinstance(page, dict):
            raise ValueError('Expected pagination object')
        if page.get('next_cursor') or page.get('next_page_token') or (connector == 'tiktok-discovery' and page.get('has_more') is True):
            limits.append('The response has more pages; this evidence does not cover the complete comment section.')
        if value['status'] == 'completed_partial':
            limits.append('The source collection is marked partially complete; do not claim the sample is complete.')
        source_limits = value.get('limitations') or []
        if not isinstance(source_limits, list) or any(not isinstance(x, str) for x in source_limits):
            raise ValueError('Expected string limitations')
        limits.extend(source_limits)
        sources.append({'path': os.path.relpath(path, base), 'sha256': hashlib.sha256(raw).hexdigest(), 'evidence_ref': value['evidence_ref'], 'retrieved_at': value['retrieved_at'], 'status': value['status'], 'row_count': len(rows)})
    if any(connector == 'tiktok-discovery' for connector, _ in videos):
        limits.append('TikTok pages may overlap or change over time. Deduplicate by comment ID; the last page does not establish a complete thread. Image URLs do not mean the images were downloaded or analyzed, and inline replies are previews only.')
    if len(videos) > 1:
        raise ValueError('Comment-only shortlist must use one explicitly selected video per batch')
    return {'schema_version': 'comment-idea-context.v1', 'report_id': 'comments:' + hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()[:24], 'sources': sources, 'comments': comments, 'limitations': list(dict.fromkeys(limits))}


def video_identity(url):
    """Normalize explicit video URLs only; never infer identity from a handle."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        identifier = (parsed.path.strip("/") if parsed.hostname == "youtu.be" else
                      parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch" else
                      parsed.path.split("/")[-1] if parsed.path.startswith(("/shorts/", "/live/")) else "")
        return ("youtube", identifier) if re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier) else None
    if parsed.hostname in {"tiktok.com", "www.tiktok.com"}:
        match = re.fullmatch(r"/(?:@[^/]+/)?video/([0-9]{1,32})/?", parsed.path)
        return ("tiktok", match.group(1)) if match else None
    return None


def validate_target(artifact, brief):
    """Reject a projection from a different explicitly requested video."""
    targets = {identity for url in re.findall(r"https://[^\s<>]+", brief or "")
               if (identity := video_identity(url.rstrip(".,;!?，。；！？)）]"))) is not None}
    actual = {video_identity(row["source_url"]) for row in artifact["comments"]}
    if targets and actual and actual != targets:
        raise ValueError("Comment evidence does not match the explicit video URL in the request; use one video per batch")


def validate_projection(artifact, base):
    """Recompute from immutable envelopes; a hand-edited projection is not evidence."""
    # 解析一次并全程复用：下面的 path 是解析过的，交给 project() 的 base 必须同样解析过，
    # 否则 project() 里的 relpath 两端形态不一致（如 macOS 的 /var 与 /private/var），
    # 会把合法的 run 内路径算成 '../../..' 串，令重算结果与原投影不等。
    resolved_base = base.resolve()
    paths = []
    for source in artifact.get('sources') or []:
        path = (base / source['path']).resolve()
        if not path.is_relative_to(resolved_base):
            raise ValueError('Comment evidence must stay inside its run directory')
        paths.append(path)
    if not paths or artifact != project(paths, resolved_base):
        raise ValueError('Comment context does not match its source envelopes')


def main():
    """Write a new projection without overwriting evidence or existing outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("envelopes", nargs="+", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        result = project([path.resolve() for path in args.envelopes], output.parent)
        # Do not overwrite immutable evidence, including an input or an existing projection.
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
