#!/usr/bin/env python3
"""Write planned Instagram profile-search envelopes from a real connector payload.

A 0.4.12 live run: search_profiles completed twice and returned local-market
product accounts, but the agent hand-wrote failed stubs
("unavailable in local persistence"). Merge then saw empty files and dropped
the route. This script is the only supported write path: it accepts a provider
envelope or a batch `results[]`, rejects invented stubs, and writes one file
per planned call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

INVENTED_STUB_MARKERS = (
    "unavailable in local persistence",
    "envelope unavailable",
)


def load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def unwrap(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    contents = raw.get("content")
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.lstrip().startswith("{"):
                return unwrap(json.loads(text))
    return raw


def envelope_list(raw: Any) -> list[dict[str, Any]]:
    payload = unwrap(raw)
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        rows = [unwrap(item) for item in payload["results"]]
        return [item for item in rows if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("profile discovery source must be one envelope or {results: [...]}")


def assert_provider_envelope(envelope: dict[str, Any], *, index: int) -> None:
    summary = str(envelope.get("summary") or "").casefold()
    if any(marker in summary for marker in INVENTED_STUB_MARKERS):
        raise ValueError(
            f"envelope[{index}] looks hand-written, not a connector result: {envelope.get('summary')}"
        )
    if envelope.get("operation") not in {None, "search_profiles"}:
        raise ValueError(f"envelope[{index}] operation must be search_profiles")
    if envelope.get("connector_id") not in {None, "instagram-discovery"}:
        raise ValueError(f"envelope[{index}] connector_id must be instagram-discovery")
    if (not str(envelope.get("provider") or "").strip()
            and envelope.get("status") not in {"failed", "unsupported", "blocked_setup"}):
        raise ValueError(
            f"envelope[{index}] is missing provider; persist the connector payload, do not invent a stub"
        )
    # connector wire 使用 completed_partial，历史/复合结果使用 partial；保存时不改写状态。
    if envelope.get("status") not in {"completed", "completed_partial", "partial", "failed", "unsupported", "blocked_setup"}:
        raise ValueError(f"envelope[{index}] status must be completed, completed_partial, partial, failed, unsupported, or blocked_setup")


def persist(plan: dict[str, Any], source: Any, output_dir: Path) -> list[Path]:
    if plan.get("schema_version") != "competitor-profile-discovery-plan.v1":
        raise ValueError("expected competitor-profile-discovery-plan.v1")
    calls = plan.get("calls") or []
    if not isinstance(calls, list) or not calls:
        raise ValueError("plan.calls must be a non-empty list")
    envelopes = envelope_list(source)
    if len(envelopes) != len(calls):
        search_only = [
            item
            for item in envelopes
            if item.get("operation") in {None, "search_profiles"}
        ]
        if len(search_only) == len(calls):
            envelopes = search_only
        else:
            raise ValueError(
                f"planned {len(calls)} profile searches, source has {len(envelopes)} envelopes. "
                "Pass only the search_profiles batch as profile-discovery-source.json "
                "(one envelope per planned call). Do not pass resolve_profile results to this script."
            )
    written: list[Path] = []
    for index, (call, envelope) in enumerate(zip(calls, envelopes)):
        assert_provider_envelope(envelope, index=index)
        name = str(call.get("envelope") or "").strip()
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"plan.calls[{index}].envelope is unsafe: {name}")
        path = output_dir / name
        path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for planned envelope files. Defaults to the plan's directory so merge can find them.",
    )
    args = parser.parse_args()
    if args.output_dir is None:
        args.output_dir = args.plan.parent
    try:
        written = persist(load(args.plan), load(args.source), args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "ok", "written": [str(path) for path in written]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
