#!/usr/bin/env python3
"""Attach the Creator's saved account profile to the TrendResearchRequest.

The model saves the Creator's saved account profile as a file: the complete `get_creator_profile`
result read with `include: ["content_profile"]`, or that result's `structuredContent` object. Its
signature content, content language, audience size and formats
steer the search plan and which candidates are eligible, so they reach the Request here, copied by
this script and never retyped by the model: a seed term retyped with a tidied word or a translation
retrieves nothing, and a language guessed from the chat would turn a retrieval label into a filter.

  python3 scripts/attach_creator_profile.py --request trend-research-request.json \\
    --profile creator-profile-source.json --platform tiktok

What is written under `creator_profile` (and nothing else is touched):

- `content_language`: the profile's primary language, only when its confidence is high. It is a
  retrieval label for writing intents. It is never copied into `locale.language`, which the Gate
  scores `locale_fit` against and would turn into a hard filter.
- `accepted_languages`: the profile's accepted languages as given (possibly empty).
- `audience_count`: the account's audience size, when the platform reports one. It stays in the
  Request for the eligibility filter and is never printed for the model.
- `formats`: the formats the account actually published (short_video / long_video).
- `signature_content`: at most four items, heaviest first (ties by id). Position + 1 is the number
  the relevance Gate shows for an item, so the order is fixed here and nowhere else.

Nothing is written, and the Request keeps its bytes, when the profile names another platform or has
no signature content (fields the model typed into those five slots are still removed: they come
from a profile file only). A handle in the Request that names another account is an error, because the
profile would then describe someone else.

The module also carries what the other profile-aware steps share: the seed matching the query-plan
validators apply and the one hand-over again, without `include`, of calls Kabo refused only for it.
Standard library only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterator

PROFILE_SOURCE = "creator-profile-source.json"
PLATFORMS = ("instagram", "tiktok", "youtube")
INTAKE_FIELDS = ("content_language", "accepted_languages", "audience_count", "formats", "signature_content")
FORMATS = ("short_video", "long_video")
SIGNATURE_LIMIT = 4
SEED_LIMIT = 5
EXAMPLE_TITLES = 2
EXAMPLE_IDS = 3
ACCEPTED_LIMIT = 5

# Scripts written without spaces between words (Han, Kana, Thai, Lao, Khmer, Myanmar), as the
# query-plan validators define them: a seed in them is matched as a substring of the query with its
# spaces removed, because a searcher types such a phrase as one unbroken run.
UNSPACED_SCRIPT = re.compile(
    "[฀-໿က-႟ក-៿぀-ヿㇰ-ㇿ"
    "㐀-䶿一-鿿豈-﫿ｦ-ﾟ\U00020000-\U0002fa1f]"
)
# A YouTube channel id. The Request may name the Creator by channel id while the profile names the
# handle; the two cannot be compared, so such a pair is never called a conflict.
CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")


class ProfileError(ValueError):
    """The profile file cannot be used for this Request."""


# --------------------------------------------------------------------------- reading the profile


def unwrap_tool_result(value: Any) -> Any:
    """The account read inside a complete MCP tool result; any other value as it is.

    This host never fetches for scripts: the model saves `get_creator_profile`'s result as the
    host returned it, so the file is either the whole CallToolResult or its `structuredContent`.
    An error result holds no profile and is refused rather than read as an empty one, so a refused
    or failed read never passes for an account without signature content.
    """
    if not isinstance(value, dict) or not ({"structuredContent", "isError", "content"} & value.keys()):
        return value
    if "account" in value:
        return value
    if value.get("isError"):
        raise ProfileError("the profile file holds a failed get_creator_profile result (isError), not a profile: "
                           "start without --profile")
    structured = value.get("structuredContent")
    if structured is None:
        # 有的宿主只导出 content：单个 text 块里是同一份 JSON（与 static_host.complete_result 同一读法）。
        blocks = value.get("content")
        if (isinstance(blocks, list) and len(blocks) == 1 and isinstance(blocks[0], dict)
                and blocks[0].get("type") == "text" and isinstance(blocks[0].get("text"), str)):
            try:
                structured = json.loads(blocks[0]["text"])
            except json.JSONDecodeError:
                structured = None
    if not isinstance(structured, dict):
        raise ProfileError("the profile file is a tool result without a structured account read: save the complete "
                           "get_creator_profile result")
    return structured


def read_profile(value: Any) -> dict[str, Any]:
    """The account read in the profile file, when it has the shape this script maps from.

    Only the full account read is accepted: its `account` says whose profile it is. A bare
    content profile carries no handle, so nothing could check that it belongs to this Creator.
    """
    value = unwrap_tool_result(value)
    if not isinstance(value, dict):
        raise ProfileError("the profile file must hold one JSON object")
    account = value.get("account")
    if not isinstance(account, dict):
        raise ProfileError("the profile file must be the account read with its content profile included: it has no "
                           "`account` object, so it cannot say whose profile it is")
    if account.get("platform") not in PLATFORMS:
        raise ProfileError(f"the profile's account.platform must be one of {', '.join(PLATFORMS)}")
    if not isinstance(account.get("handle"), str) or not account["handle"].strip():
        raise ProfileError("the profile's account.handle must be a non-empty string")
    if "contentProfile" not in value:
        raise ProfileError("the profile file has no `contentProfile` field: read the account again with its content "
                           "profile included")
    content = value.get("contentProfile")
    if content is not None and not isinstance(content, dict):
        raise ProfileError("the profile's contentProfile must be an object or null")
    return value


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProfileError(f"{path} is not readable JSON ({error})") from error
    return read_profile(value)


def handle_key(value: Any) -> str:
    return str(value or "").strip().lstrip("@").casefold()


def _text(value: Any, limit: int | None = None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    return text[:limit] if limit else text


def _strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        text = _text(entry)
        if text is not None and text not in out:
            out.append(text)
    return out[:limit]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _signature_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    fields = {key: _text(item.get(key)) for key in ("id", "name", "topic", "approach")}
    if any(value is None for value in fields.values()):
        return None
    representative = [row for row in item.get("representativeContent") or [] if isinstance(row, dict)]
    hashtags = []
    for tag in _strings(item.get("seedHashtags"), SEED_LIMIT * 2):
        folded = tag.lstrip("#").strip().casefold()
        if folded and folded not in hashtags:
            hashtags.append(folded)
    weight = _number(item.get("weight"))
    return {
        **fields,
        "seed_terms": _strings(item.get("seedTerms"), SEED_LIMIT),
        "seed_hashtags": hashtags[:SEED_LIMIT],
        "example_titles": [title for title in (_text(row.get("title")) for row in representative)
                           if title is not None][:EXAMPLE_TITLES],
        "example_content_ids": [cid for cid in (_text(row.get("contentId")) for row in representative)
                                if cid is not None][:EXAMPLE_IDS],
        # The Request schema bounds a weight to 0..1 (the profile's weights sum to 1); a value outside
        # would make the attached Request fail its own schema.
        "weight": min(max(weight, 0.0), 1.0) if weight is not None else 0.0,
    }


def projection(profile: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """The Request fields this profile writes, or None with the reason nothing is written."""
    content = profile.get("contentProfile")
    if not isinstance(content, dict):
        return None, "no_content_profile"
    account = profile["account"]
    if content.get("platform") not in (None, account.get("platform")):
        return None, "content_profile_names_another_platform"
    items = [_signature_item(item) for item in content.get("signatureContent") or []]
    items = [item for item in items if item is not None]
    if not items:
        return None, f"no_signature_content ({content.get('signatureContentStatus') or 'none listed'})"
    items.sort(key=lambda item: (-item["weight"], item["id"]))
    fields: dict[str, Any] = {}
    language = content.get("language") if isinstance(content.get("language"), dict) else {}
    primary = _text(language.get("primary"))
    if language.get("confidence") == "high" and primary is not None and not primary.casefold().startswith("und"):
        fields["content_language"] = primary
    fields["accepted_languages"] = _strings(language.get("accepted"), ACCEPTED_LIMIT)
    audience = account.get("audienceCount")
    if isinstance(audience, int) and not isinstance(audience, bool) and audience >= 0:
        fields["audience_count"] = audience
    formats = []
    for row in content.get("formats") or []:
        if not isinstance(row, dict) or row.get("format") not in FORMATS:
            continue
        count = row.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count > 0 and row["format"] not in formats:
            formats.append(row["format"])
    if formats:
        fields["formats"] = formats
    fields["signature_content"] = items[:SIGNATURE_LIMIT]
    return fields, "attached"


# --------------------------------------------------------------------------- the Request


def creator_of(request: dict[str, Any]) -> dict[str, Any]:
    creator = request.get("creator_profile")
    return creator if isinstance(creator, dict) else {}


def signature_content(request: dict[str, Any]) -> list[dict[str, Any]]:
    """The Request's attached signature content, in Gate-number order; empty when none was attached."""
    items = creator_of(request).get("signature_content")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def attached(request: dict[str, Any]) -> bool:
    return bool(signature_content(request))


def strip_unattached(request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Drop intake fields the model wrote by hand when no profile file was supplied.

    They are copied from the profile file only; typed by the model they would steer the plan and
    the eligibility filter from a guess.
    """
    creator = creator_of(request)
    found = [field for field in INTAKE_FIELDS if field in creator]
    if not found:
        return request, []
    updated = dict(request)
    updated["creator_profile"] = {key: value for key, value in creator.items() if key not in INTAKE_FIELDS}
    return updated, found


def attach(request: dict[str, Any], profile: dict[str, Any], platform: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The Request with the profile's fields under `creator_profile`, and a report of what happened."""
    profile = read_profile(profile)
    account = profile["account"]
    report: dict[str, Any] = {"platform": account["platform"], "handle": account["handle"]}
    if account["platform"] != platform:
        # Unused profile: the run plans as without one, so fields the model typed go as they would then.
        unused, dropped = strip_unattached(request)
        return unused, {**report, "attached": False, "reason": f"profile_is_for_{account['platform']}",
                        "dropped": dropped}
    creator = creator_of(request)
    given = creator.get("handle")
    if isinstance(given, str) and given.strip():
        comparable = not (CHANNEL_ID.match(given.strip()) or CHANNEL_ID.match(account["handle"].strip()))
        if comparable and handle_key(given) != handle_key(account["handle"]):
            raise ProfileError(f"the Request's creator_profile.handle {given!r} names another account than the profile "
                               f"({account['handle']!r}); the profile describes a different Creator. Correct the "
                               "handle or start without --profile")
    fields, reason = projection(profile)
    if fields is None:
        unused, dropped = strip_unattached(request)
        return unused, {**report, "attached": False, "reason": reason, "dropped": dropped}
    updated_creator = {key: value for key, value in creator.items() if key not in INTAKE_FIELDS}
    # The profile's owner is the Creator this scan is anchored on when the Request named none.
    updated_creator.setdefault("platform", platform)
    if not (isinstance(given, str) and given.strip()):
        updated_creator["handle"] = account["handle"].strip().lstrip("@")
    updated_creator.update(fields)
    updated = dict(request)
    updated["creator_profile"] = updated_creator
    return updated, {**report, "attached": True, "reason": reason,
                     "signature_content": len(fields["signature_content"]),
                     "content_language": fields.get("content_language")}


def write_json_atomic(path: Path, value: Any) -> None:
    handle, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temp, path)


def attach_file(request_path: Path, profile_path: Path | None, platform: str) -> dict[str, Any]:
    """Update the Request file in place; it is rewritten only when its content changes."""
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ProfileError(f"{request_path} must hold the Request object")
    if profile_path is None:
        updated, dropped = strip_unattached(request)
        report: dict[str, Any] = {"attached": False, "reason": "no_profile_file", "dropped": dropped}
    else:
        updated, report = attach(request, load_profile(profile_path), platform)
    if updated != request:
        write_json_atomic(request_path, updated)
    return report


# --------------------------------------------------------------------------- the profile, shown


def describe(profile: dict[str, Any], platform: str) -> list[str]:
    """What the model reads before writing the plan: language, formats and the signature content.

    Never the audience size: the eligibility filter reads it from the Request, and the plan has no
    use for a private-looking number in the model's context.
    """
    profile = read_profile(profile)
    account = profile["account"]
    if account["platform"] != platform:
        return [f"creator profile: for {account['platform']}, not {platform}; it is not used in this run"]
    fields, reason = projection(profile)
    lines = [f"creator profile: @{account['handle'].lstrip('@')} on {platform}"]
    if fields is None:
        lines.append(f"creator profile: no signature content to attach ({reason}); plan as without a profile")
        return lines
    language = fields.get("content_language")
    lines.append("content language: " + (language if language else "not settled (write intents in the language "
                                                                       "the Creator's own seed terms use)"))
    lines.append("accepted languages: " + (", ".join(fields["accepted_languages"]) or "none listed"))
    if "formats" in fields:
        lines.append("formats: " + ", ".join(fields["formats"]))
    for number, item in enumerate(fields["signature_content"], start=1):
        seeds = item["seed_terms"] + [f"#{tag}" for tag in item["seed_hashtags"]]
        lines.append(f"signature content {number} ({item['id']}, weight {item['weight']:.2f}): {item['name']} — "
                     f"{item['topic']}; approach: {item['approach']}; seeds: {json.dumps(seeds, ensure_ascii=False)}")
    return lines


# --------------------------------------------------------------------------- seed matching


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _tokens(text: str) -> list[str]:
    out = []
    for raw in _fold(text).replace("#", " ").split():
        start, end = 0, len(raw)
        while start < end and unicodedata.category(raw[start])[0] in "PS":
            start += 1
        while end > start and unicodedata.category(raw[end - 1])[0] in "PS":
            end -= 1
        if start < end:
            out.append(raw[start:end])
    return out


def _unspaced(text: str) -> str:
    return re.sub(r"[\s#]+", "", _fold(text))


def _contiguous(needle: list[str], hay: list[str]) -> bool:
    size = len(needle)
    return size > 0 and any(hay[i:i + size] == needle for i in range(len(hay) - size + 1))


def contains_seed(query: str, seed: str) -> bool:
    """Whether the query carries the seed term verbatim (casefolded; whole words in spaced scripts)."""
    if not isinstance(seed, str) or not seed.strip():
        return False
    if UNSPACED_SCRIPT.search(seed) or UNSPACED_SCRIPT.search(query):
        needle = _unspaced(seed)
        return bool(needle) and needle in _unspaced(query)
    return _contiguous(_tokens(seed), _tokens(query))


def contains_hashtag(query: str, tag: str) -> bool:
    """Whether the query carries the hashtag, written as one word or as its words in a row."""
    if not isinstance(tag, str) or not tag.strip("# "):
        return False
    needle = _unspaced(tag)
    if UNSPACED_SCRIPT.search(needle) or UNSPACED_SCRIPT.search(query):
        return needle in _unspaced(query)
    tokens = _tokens(query)
    return any("".join(tokens[i:j]) == needle for i in range(len(tokens)) for j in range(i + 1, len(tokens) + 1))


def hits(query: str, item: dict[str, Any]) -> bool:
    return (any(contains_seed(query, term) for term in item.get("seed_terms") or [])
            or any(contains_hashtag(query, tag) for tag in item.get("seed_hashtags") or []))


def _seeds_named(number: int, item: dict[str, Any]) -> str:
    seeds = list(item.get("seed_terms") or []) + [f"#{tag}" for tag in item.get("seed_hashtags") or []]
    return f"{number} {item.get('name')!r} (seeds {json.dumps(seeds, ensure_ascii=False)})"


def _assign(queries: list[str], items: list[tuple[int, dict[str, Any]]]) -> bool:
    """Whether each item can take a different query that carries one of its seeds."""
    taken: dict[int, int] = {}

    def place(position: int, seen: set[int]) -> bool:
        for q, query in enumerate(queries):
            if q in seen or not hits(query, items[position][1]):
                continue
            seen.add(q)
            if q not in taken or place(taken[q], seen):
                taken[q] = position
                return True
        return False

    return all(place(position, set()) for position in range(len(items)))


def check_plan(queries: list[str], request: dict[str, Any], *, per_intent: str) -> dict[str, Any] | None:
    """Require the plan to search for the Creator's signature content in the Creator's own seed words.

    `per_intent="covering"` (Instagram, up to six intents): every intent carries a seed of some
    signature content, and together they reach min(count, 4) of them. `per_intent="top_two"`
    (TikTok and YouTube, two intents): the intents go to the two heaviest items, one each, and
    every intent carries a seed of the item it belongs to. Items without seeds cannot be searched
    for verbatim and are left out of the count. Returns what was checked, or None without a profile.
    """
    numbered = [(number, item) for number, item in enumerate(signature_content(request), start=1)
                if item.get("seed_terms") or item.get("seed_hashtags")]
    if not signature_content(request):
        return None
    if not numbered:
        return {"signature_content_checked": 0}
    if per_intent == "top_two":
        wanted = numbered[:2]
    else:
        wanted = numbered[:SIGNATURE_LIMIT]
    for index, query in enumerate(queries):
        if not any(hits(query, item) for _, item in wanted):
            raise ValueError(f"intents[{index}].search_query {query!r} carries no seed term of the signature content "
                             "it belongs to; copy one verbatim from: "
                             + "; ".join(_seeds_named(number, item) for number, item in wanted))
    if per_intent == "top_two":
        if len(queries) < len(wanted):
            raise ValueError(f"write {len(wanted)} intents, one for each of the two heaviest signature content items: "
                             + "; ".join(_seeds_named(number, item) for number, item in wanted))
        if not _assign(queries, wanted):
            raise ValueError("the intents must belong to different signature content items, one each, and carry that "
                             "item's seed verbatim: " + "; ".join(_seeds_named(number, item) for number, item in wanted))
    else:
        covered = [number for number, item in wanted if any(hits(query, item) for query in queries)]
        if len(covered) < len(wanted):
            missing = [(number, item) for number, item in wanted if number not in covered]
            raise ValueError(f"the intents reach {len(covered)} of {len(wanted)} signature content items; give each "
                             "missing item an intent carrying one of its seeds verbatim: "
                             + "; ".join(_seeds_named(number, item) for number, item in missing))
    return {"signature_content_checked": len(wanted)}


# --------------------------------------------------------------------------- include, refused by Kabo

# What the model is told under a hand-over whose calls carry `include`. Kabo validates tool input
# against its own contract: one that predates `include` refuses the call (invalid input, no data,
# nothing to stage), and this host has no fetch of its own to notice and replay it.
INCLUDE_HINT = ("If Kabo refuses any call above only for its `include` parameter (an invalid-input error with no "
                "data), do not retry it by hand: make the other calls as usual, then run this same command with "
                "--without-include instead of --placed. It hands those calls over once more without `include`.")


def _call_includes(call: dict[str, Any]) -> bool:
    arguments = call.get("arguments") or {}
    if call.get("tool") == "data_connector_run":
        return isinstance((arguments.get("params") or {}).get("include"), list)
    return isinstance(arguments.get("include"), list)


def without_include(call: dict[str, Any]) -> dict[str, Any]:
    arguments = dict(call.get("arguments") or {})
    if call.get("tool") == "data_connector_run":
        arguments["params"] = {key: value for key, value in (arguments.get("params") or {}).items() if key != "include"}
    else:
        arguments.pop("include", None)
    return {**call, "arguments": arguments}


def operation_of(call: dict[str, Any]) -> str:
    arguments = call.get("arguments") or {}
    return str(arguments.get("operation") or call.get("tool") or "")


@contextlib.contextmanager
def include_fallback(cd: Any, args: Any) -> Iterator[None]:
    """While active, calls Kabo refused only for `include` are handed over once more without it.

    The skill's calls ask for the extra fields with `include`. This host never fetches: each round
    is handed to the model as `call:` lines, so the refusal is seen by the model, not by a script.
    The model reports it by running the same stage with `--without-include`; the open round's
    calls that carry `include` are then handed over again without it, under the same round, so
    the round's key, hand-over time, placement and budget stay those of the original calls (the
    calls of that round that were answered are not made twice). An operation refused once is
    handed over without `include` for the rest of the run.
    """
    original_hand_over, original_round = cd.hand_over, cd.fetch_round

    def refused() -> set[str]:
        return set(cd.state().get("include_refused") or [])

    def sent(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        gone = refused()
        return [without_include(call) if _call_includes(call) and operation_of(call) in gone else call
                for call in calls]

    def hand_over(calls: list[dict[str, Any]], why: str = "") -> None:
        printed = sent(calls)
        try:
            original_hand_over(printed, why)
        except SystemExit:
            if any(_call_includes(call) for call in printed):
                cd.say(INCLUDE_HINT)
            raise

    def fetch_round(calls: list[dict[str, Any]], round_args: Any, place_responses: Any, *rest: Any,
                    **options: Any) -> bool:
        current = cd.state()
        key = cd.round_key(calls)
        if getattr(round_args, "without_include", False) and key not in (current.get("rounds") or []):
            pending = [call for call in sent(calls) if _call_includes(call)]
            if key not in (current.get("handed") or {}) or not pending:
                raise cd.StageError("--without-include answers a hand-over whose calls carried `include` and were "
                                    "refused for it; nothing like that is open. Run the command the stage named, "
                                    "with --placed once its calls were made")
            operations = sorted({*refused(), *(operation_of(call) for call in pending)})
            cd.save_state(include_refused=operations)
            cd.say(f"[drive] Kabo refused `include` on {', '.join(operations)}; handing those calls over once more "
                   "without it (the extra profile fields are missing for their results)")
            round_args.without_include = False
            original_hand_over([without_include(call) for call in pending])
        return original_round(calls, round_args, place_responses, *rest, **options)

    cd.hand_over, cd.fetch_round = hand_over, fetch_round
    try:
        yield
    finally:
        cd.hand_over, cd.fetch_round = original_hand_over, original_round


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", type=Path, required=True, help="the TrendResearchRequest to update in place")
    parser.add_argument("--profile", type=Path, help="the Creator's saved account profile; omitted, hand-written "
                                                     "profile fields are removed")
    parser.add_argument("--platform", choices=PLATFORMS, required=True, help="this skill's platform")
    args = parser.parse_args()
    try:
        report = attach_file(args.request, args.profile, args.platform)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
