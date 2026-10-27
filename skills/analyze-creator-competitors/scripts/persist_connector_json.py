#!/usr/bin/env python3
"""Copy a connector payload without going through an editor that truncates at 4 KiB."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

TRUNCATED_HINT = (
    "recopy the raw connector output through persist_connector_json.py; "
    "do not apply_patch, echo, or python -c a connector payload"
)


def sibling_b64_paths(source: Path) -> list[Path]:
    return [source.with_name(source.name + ".b64"), source.with_suffix(".b64")]


def decode_b64(path: Path) -> bytes:
    return base64.b64decode(path.read_bytes(), validate=False)


def unwrap_connector_payload(raw: Any) -> Any:
    """Return the inner JSON object from an MCP tool wrapper.

    Collector and connector calls often persist the whole MCP envelope
    (`structuredContent` or `content[].text`). Downstream scripts want the
    typed object. Recurse so a text blob that itself is a wrapper still
    unwraps. A text field that starts like JSON but does not parse is a
    truncated 4 KiB write, not a non-JSON payload — fail closed.
    """
    if not isinstance(raw, dict):
        return raw
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        return unwrap_connector_payload(structured)
    contents = raw.get("content")
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.lstrip().startswith("{"):
                try:
                    return unwrap_connector_payload(json.loads(text))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"connector payload text is truncated or invalid JSON; {TRUNCATED_HINT} ({exc})"
                    ) from exc
    return raw


def load_json_object(source: Path) -> Any:
    raw = source.read_bytes()
    if not raw.strip():
        for candidate in sibling_b64_paths(source):
            if candidate.is_file():
                recovered = decode_b64(candidate)
                if recovered.strip():
                    raw = recovered
                    break
        else:
            raise ValueError(f"{source} is empty; persist the connector payload, do not create a placeholder")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        for candidate in sibling_b64_paths(source):
            if not candidate.is_file():
                continue
            try:
                value = json.loads(decode_b64(candidate).decode("utf-8"))
                break
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                continue
        else:
            raise ValueError(f"{source} is truncated or invalid JSON; {TRUNCATED_HINT} ({exc})") from exc
    return unwrap_connector_payload(value)


def persist(source: Path, dest: Path) -> dict[str, Any]:
    value = load_json_object(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "ok", "bytes": dest.stat().st_size, "path": str(dest)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("dest", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(persist(args.source, args.dest), ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
