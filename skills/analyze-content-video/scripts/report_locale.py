"""The report's own words in the creator's language: labels, the measurement line and the listen line.

The creator's language is `creator_view.language`, a BCP 47 tag; its primary subtag picks the strings. Chinese and
English keep their wording in the renderer and the measurement-basis module; `references/report-locales.json`
holds every other language the report localizes, and the listen line for all of them. A language it does not list
renders in English.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CATALOG = json.loads((Path(__file__).resolve().parents[1] / "references/report-locales.json")
                      .read_text(encoding="utf-8"))["languages"]
# Languages with a complete set of labels and measurement-line words beyond zh and en.
LOCALES: dict[str, dict] = {code: entry for code, entry in _CATALOG.items() if "labels" in entry and "note" in entry}


def record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def report_language(view: Any) -> str:
    """`zh` for any Chinese tag, a listed language by its primary subtag (`pt-BR` -> `pt`), `en` otherwise."""
    tag = str(record(view).get("language") or "").strip().lower().replace("_", "-")
    primary = tag.split("-")[0]
    if primary == "zh" or tag.startswith("zh"):
        return "zh"
    return primary if primary in LOCALES else "en"


def labels(language: str) -> dict | None:
    return record(LOCALES.get(language)).get("labels")


def note_words(language: str) -> dict:
    return LOCALES[language]["note"]


def listen_note(evidence: Any, language: str) -> str | None:
    """One line telling the creator the sound was measured and not heard, or None.

    Derived from the evidence alone: a local file's sound measurement (`media.audio`) that left questions only an
    ear can answer (`listen_check`), with no whole-video viewing, which watches with the sound on, in the run."""
    audio = record(record(record(evidence).get("media")).get("audio"))
    checks = [item for item in audio.get("listen_check") or [] if isinstance(item, dict) and item.get("ask")]
    if not checks:
        return None
    if record(record(evidence).get("viewer_observations")).get("status") == "available":
        return None
    entry = record(_CATALOG.get(language)) or _CATALOG["en"]
    return entry.get("listen_note") or _CATALOG["en"]["listen_note"]
