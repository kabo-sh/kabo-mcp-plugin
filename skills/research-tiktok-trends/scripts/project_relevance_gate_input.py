#!/usr/bin/env python3
"""Project the full Trend candidate union into the minimum semantic-gate input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def visible_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "caption", "description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return "\n".join(parts)


# A row in the table is everything the Gate can see about one candidate. The platform-written summary gets
#   only a short capped position,
# placed after the author's original text so it does not compete with the author's text for the pagination
#   budget.
PLATFORM_SUMMARY_LIMIT = 160
SIGNATURE_CONTENT_LIMIT = 4
EXCLUDED_TOPICS_LIMIT = 10


def platform_summary(item: dict[str, Any]) -> str | None:
    """The platform's description of this content, kept separate from the author's own text.

    Only candidate builders that obtained platform signals write `platform_summary_source` (currently TikTok search rows with
    `include: ["content_signals"]`). This text was written by the platform and must be labeled as such in the table:
    if it were scored as the author's own words, a one-line platform-generated description would be read as the author personally spelling out the technique. No data is fetched here,
    so a candidate without a source has no summary. YouTube has only the description that comes with search results, which the author wrote
    and is already in visible_text, so no separate summary is made.
    """
    source = item.get("platform_summary_source")
    if not isinstance(source, dict):
        return None
    parts: list[str] = []
    desc = source.get("content_desc")
    if isinstance(desc, str) and " ".join(desc.split()):
        parts.append(" ".join(desc.split()))
    words = [" ".join(word.split()) for word in source.get("suggest_words") or []
             if isinstance(word, str) and word.strip()]
    if words:
        parts.append("related searches: " + ", ".join(dict.fromkeys(words)))
    if not parts:
        return None
    text = "; ".join(parts)
    if len(text) > PLATFORM_SUMMARY_LIMIT:
        text = text[:PLATFORM_SUMMARY_LIMIT - 1].rstrip() + "\u2026"
    return text


def signature_subject(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """List the creator's main content by gate number: the number is its index in the Request array + 1.

    Profile intake has already sorted the Request array (weight descending, ties by id); numbers are fixed there and not re-sorted here.
    The id is also written into the projection file so the scoring script can map the numbers the model filled in back to ids without reading the Request.
    """
    items = profile.get("signature_content")
    if items is None:
        return []
    if not isinstance(items, list) or len(items) > SIGNATURE_CONTENT_LIMIT:
        raise ValueError(f"creator_profile.signature_content must be an array of at most {SIGNATURE_CONTENT_LIMIT}")
    subject: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("every signature_content entry must be an object")
        fields = {key: item.get(key) for key in ("id", "name", "topic", "approach")}
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            raise ValueError(f"signature_content {number} needs a nonempty id, name, topic and approach")
        if fields["id"] in seen:
            raise ValueError(f"signature_content id {fields['id']} appears twice")
        seen.add(fields["id"])
        examples = [title.strip() for title in item.get("example_titles") or []
                    if isinstance(title, str) and title.strip()]
        subject.append({"number": number, "id": fields["id"], "name": fields["name"].strip(),
                        "topic": fields["topic"].strip(), "approach": fields["approach"].strip(),
                        "examples": examples})
    return subject


def excluded_subject(profile: dict[str, Any]) -> list[str]:
    """Topics the creator excludes, passed to the gate as they are.

    Eligibility filtering removes only candidates that match literally; the same topic in different wording or another language is visible only to the gate, so the topics are printed into the table header
    and the gate scores topic_relevance 0 for such entries. When there are no excluded topics, subject does not get this key, and the header is byte-for-byte unchanged.
    """
    topics = profile.get("excluded_topics")
    if topics is None:
        return []
    if not isinstance(topics, list) or len(topics) > EXCLUDED_TOPICS_LIMIT:
        raise ValueError(f"creator_profile.excluded_topics must be an array of at most {EXCLUDED_TOPICS_LIMIT}")
    if any(not isinstance(topic, str) or not topic.strip() for topic in topics):
        raise ValueError("every creator_profile.excluded_topics entry must be a nonempty string")
    return [topic.strip() for topic in topics]


def creator_label(item: dict[str, Any]) -> str | None:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
    for value in (author.get("handle"), author.get("full_name"), channel.get("title"), channel.get("id")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def project(request: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != "trend-research-request.v3":
        raise ValueError("request must be trend-research-request.v3")
    if candidates.get("schema_version") not in {
        "trend-candidate-set.v1",
        "tiktok-trend-candidate-set.v1",
        "youtube-trend-candidate-set.v1",
    }:
        raise ValueError("candidates must be an Instagram, TikTok or YouTube trend candidate set")
    items = candidates.get("items")
    if not isinstance(items, list):
        raise ValueError("candidate items must be an array")
    projected = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("every candidate item must be an object")
        key = str(item.get("content_key") or "")
        if not key or key in seen:
            raise ValueError(f"missing or duplicate candidate content_key: {key}")
        seen.add(key)
        row = {"content_key": key, "visible_text": visible_text(item)}
        label = creator_label(item)
        if label:
            row["creator_label"] = label
        summary = platform_summary(item)
        if summary:
            row["platform_summary"] = summary
        projected.append(row)
    platforms = request.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise ValueError("request platforms must contain at least one platform")
    if any(not isinstance(value, str) for value in platforms):
        raise ValueError("request platforms must contain only strings")
    platform = candidates.get("platform") if candidates.get("platform") is not None else platforms[0]
    if not isinstance(platform, str) or platform not in {"instagram", "tiktok", "youtube"}:
        raise ValueError("platform must be instagram, tiktok or youtube")
    if platform not in platforms:
        raise ValueError("candidate platform must be included in request platforms")
    locale = request.get("locale")
    if locale is None:
        locale = {}
    if not isinstance(locale, dict):
        raise ValueError("request locale must be an object")
    profile = request.get("creator_profile")
    if profile is not None and not isinstance(profile, dict):
        raise ValueError("request creator_profile must be an object")
    profile = profile or {}
    # The anchor's own format signature is the only evidence that separates
    # same-format content from merely same-subject content. Withholding it
    # leaves the Gate scoring captions against a niche noun phrase, which
    # cannot distinguish a style enumeration from a branding service ad.
    mechanisms = [
        value.strip()
        for value in (profile.get("observed_content_mechanisms") or [])
        if isinstance(value, str) and value.strip()
    ]
    handle = profile.get("handle")
    subject: dict[str, Any] = {
        "niche": str(request.get("niche") or ""),
        "region": locale.get("region"),
        "language": locale.get("language"),
    }
    if isinstance(handle, str) and handle.strip():
        subject["anchor_handle"] = handle.strip()
    if mechanisms:
        subject["anchor_mechanisms"] = mechanisms
    signature = signature_subject(profile)
    if signature:
        subject["signature_content"] = signature
    excluded = excluded_subject(profile)
    if excluded:
        subject["excluded_topics"] = excluded
    return {
        "schema_version": "trend-relevance-gate-input.v1",
        "request_id": str(request["request_id"]),
        "platform": platform,
        "subject": subject,
        "items": projected,
    }


# Leave room under a bounded host output for surrounding stage messages.
TABLE_BUDGET_BYTES = 32_000


SIGNATURE_CONTENT_RULE = ("Score one more column after creator_transferability: the number of the "
                          "subject.signature_content entry whose approach this item reproduces, or 0 when it "
                          "reproduces none of them.")
EXCLUDED_TOPICS_RULE = ("Score topic_relevance 0 for an item whose subject is one of subject.excluded_topics (topics "
                        "the Creator excluded), however it is worded and in whatever language.")
PLATFORM_SUMMARY_RULE = ("Text after \"platform summary, not by the author:\" was written by the platform, not by "
                         "the item's author: use it to tell what the item shows, never as the author's wording.")


def table_parts(output: dict[str, Any]):
    """Yield the original table records without shortening any evidence."""
    header = {key: output[key] for key in ("request_id", "platform", "subject")}
    subject = output["subject"]
    header["topic_relevance_rule"] = (
        "Score topic_relevance against subject.niche, the frozen goal of this request. "
        "Historical signature content and anchor mechanisms cannot replace that goal. "
        "Judge creator_transferability and signature_content separately: an on-topic item may match "
        "no historical class, and a class match does not make an off-topic item relevant."
    )
    if subject.get("signature_content"):
        # The model answers only by the printed number. The id stays only in the projection file for the scoring
        #   script, and the header does not print it,
        # so the model does not write the id into the number column.
        header["subject"] = {**subject, "signature_content": [
            {key: entry[key] for key in ("number", "name", "topic", "approach", "examples") if key in entry}
            for entry in subject["signature_content"]]}
        header["signature_content_rule"] = SIGNATURE_CONTENT_RULE
    if subject.get("excluded_topics"):
        header["excluded_topics_rule"] = EXCLUDED_TOPICS_RULE
    if any(row.get("platform_summary") for row in output["items"]):
        header["platform_summary_rule"] = PLATFORM_SUMMARY_RULE
    if subject.get("region") is None and subject.get("language") is None:
        # The rule sits in SKILL.md, but the Gate is scored from this table: plugins 2026-10-29 J1
        # (a Chinese ask, no market named) scored six of seven English home-workout videos 75 on
        # locale_fit against 95 for the Chinese ones. Say it where the scoring happens.
        header["locale_fit_rule"] = ("No market or content language was named: the ask's language sets only the "
                                     "reply language. Do not score locale_fit down for an item's language.")
    yield 0, json.dumps(header, ensure_ascii=False)
    for index, row in enumerate(output["items"], start=1):
        text = " / ".join(part.strip() for part in str(row.get("visible_text") or "").splitlines() if part.strip())
        queries = "; ".join(row.get("matched_queries") or [])
        summary = row.get("platform_summary")
        yield index, (f"\n{index}. [{row.get('creator_label') or '?'}]" +
                      (f" {{{queries}}}" if queries else "") + f" {text}" +
                      (f" (platform summary, not by the author: {summary})" if summary else ""))


def table(output: dict[str, Any]) -> str:
    """Keep the established small-table format byte-for-byte."""
    return "".join(text for _, text in table_parts(output))


def json_character_bytes(char: str) -> int:
    if char in ('"', "\\", "\b", "\f", "\n", "\r", "\t"):
        return 2
    if ord(char) < 32:
        return 6
    return len(char.encode("utf-8"))


def table_chunks(output: dict[str, Any], room: int):
    """Bound memory by one page while preserving every UTF-8 character in record order."""
    chars: list[str] = []
    used = 0
    first = last = None
    for index, text in table_parts(output):
        for char in text:
            size = json_character_bytes(char)
            if chars and used + size > room:
                yield "".join(chars), first, last
                chars, used, first, last = [], 0, None, None
            if index:
                first = index if first is None else first
                last = index
            chars.append(char)
            used += size
    if chars:
        yield "".join(chars), first, last


def page_frame(chunk: str, first: int | None, last: int | None, page: int,
               total: int, input_path: str, next_page: int | None) -> dict[str, Any]:
    return {
        "table_page": page,
        "total_pages": total,
        "first_candidate": first,
        "last_candidate": last,
        "table_chunk": chunk,
        "next": None if next_page is None else {
            "script": "scripts/project_relevance_gate_input.py",
            "arguments": ["--input", input_path, "--table", "--page", str(next_page)],
        },
        "instruction": ("Read every page before scoring. Concatenate table_chunk values without separators; "
                        "a numbered candidate may continue across pages. Run next.script from the same skill "
                        "directory with next.arguments until next is null. Do not recollect or score a partial table."),
    }


def render_table_page(output: dict[str, Any], input_path: str, page: int,
                      status: str, budget: int = TABLE_BUDGET_BYTES) -> str:
    if page < 1:
        raise ValueError("page must be a positive integer")
    # Two print() calls each append a newline. Include both and the status line in the budget.
    room = budget - len(status.encode("utf-8")) - 2
    small_parts: list[str] = []
    size = 0
    for _, text in table_parts(output):
        size += len(text.encode("utf-8"))
        if size > room:
            break
        small_parts.append(text)
    else:
        if page != 1:
            raise ValueError("page is outside this table (only page 1 exists)")
        return "".join(small_parts)
    del small_parts
    # Every page holds at least one character, so the total table length bounds all page numbers.
    maximum = sum(len(text) for _, text in table_parts(output)) + len(output["items"]) + 1
    worst = page_frame("", maximum, maximum, maximum, maximum, input_path, maximum)
    payload_room = room - len(json.dumps(worst, ensure_ascii=False).encode("utf-8"))
    if payload_room < 6:
        raise ValueError("table page metadata exceeds the output budget")
    total = sum(1 for _ in table_chunks(output, payload_room))
    if page > total:
        raise ValueError(f"page is outside this table (1..{total})")
    for number, (chunk, first, last) in enumerate(table_chunks(output, payload_room), 1):
        if number == page:
            result = json.dumps(page_frame(chunk, first, last, page, total, input_path,
                                           page + 1 if page < total else None), ensure_ascii=False)
            if len(result.encode("utf-8")) > room:
                raise ValueError("table page exceeds the output budget")
            return result
    raise ValueError("table page was not found")


def validate_projection(value: dict[str, Any]) -> None:
    if value.get("schema_version") != "trend-relevance-gate-input.v1":
        raise ValueError("input must be trend-relevance-gate-input.v1")
    if value.get("platform") not in {"instagram", "youtube", "tiktok"}:
        raise ValueError("input has an unsupported platform")
    if not isinstance(value.get("request_id"), str) or not value["request_id"]:
        raise ValueError("input must contain a request_id")
    if not isinstance(value.get("subject"), dict) or not isinstance(value.get("items"), list):
        raise ValueError("input must contain subject and items")
    seen: set[str] = set()
    for row in value["items"]:
        if not isinstance(row, dict) or not isinstance(row.get("content_key"), str):
            raise ValueError("every projected item must have a content_key")
        if not row["content_key"] or row["content_key"] in seen:
            raise ValueError("projected content_key must be nonempty and unique")
        if not isinstance(row.get("visible_text"), str):
            raise ValueError("every projected item must retain visible_text")
        if "matched_queries" in row and (not isinstance(row["matched_queries"], list) or
                                          any(not isinstance(query, str) for query in row["matched_queries"])):
            raise ValueError("matched_queries must be an array of strings")
        if "platform_summary" in row and (not isinstance(row["platform_summary"], str) or
                                           not row["platform_summary"].strip() or
                                           len(row["platform_summary"]) > PLATFORM_SUMMARY_LIMIT):
            raise ValueError(f"platform_summary must be a nonempty string of at most {PLATFORM_SUMMARY_LIMIT} characters")
        seen.add(row["content_key"])
    signature = value["subject"].get("signature_content")
    if signature is not None:
        if (not isinstance(signature, list) or not 1 <= len(signature) <= SIGNATURE_CONTENT_LIMIT or
                [entry.get("number") if isinstance(entry, dict) else None for entry in signature]
                != list(range(1, len(signature) + 1)) or
                any(not isinstance(entry.get("id"), str) or not entry["id"] for entry in signature) or
                len({entry["id"] for entry in signature}) != len(signature)):
            raise ValueError("subject.signature_content must number 1..k distinct ids in order")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path, help="read an existing run projection without recollection or writes")
    parser.add_argument("--page", type=int, default=1, help="read this complete table page (1-based)")
    parser.add_argument("--print", action="store_true", help="also print the projection to stdout")
    parser.add_argument("--table", action="store_true", help="print the first table page and continuation instructions")
    args = parser.parse_args()
    try:
        if args.page < 1 or (args.page != 1 and not args.table):
            raise ValueError("--page requires --table and a positive integer")
        if args.table and args.print:
            raise ValueError("choose --table or --print, so one output stays within its budget")
        if args.input:
            if not args.table or args.print or any((args.request, args.candidates, args.output)):
                raise ValueError("--input requires only --table and optional --page")
            output = load(args.input)
            validate_projection(output)
            path = args.input
        else:
            if not all((args.request, args.candidates, args.output)) or args.page != 1:
                raise ValueError("provide --request, --candidates and --output; later pages use --input")
            output = project(load(args.request), load(args.candidates))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            path = args.output
        status = json.dumps({"status": "ok", "items": len(output["items"]), "path": str(path)})
        rendered = render_table_page(output, str(path), args.page, status) if args.table else None
        print(status)
        if args.print:
            print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        if rendered is not None:
            print(rendered)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
