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


# What the line may ask the creator to listen for, in the order it names them.
LISTEN_ITEMS = ("music_fit", "track_identity", "sung_or_spoken", "voice_timbre", "sfx_quality")
# A stretch of other sound shorter than this is a sliver between words, not a music bed.
MIN_SIGNAL_S = 1.0


def listen_items(audio: Any) -> list[str]:
    """The ear-only questions this measurement leaves open, read from its own readings.

    The voice's timbre only when speech was recognised and not read as sung; sung or spoken only when words were
    heard over music; the music's fit and which track it is only when other sound than speech, or a bed under the
    voice, is present; the effects only when there are cuts or sound onsets."""
    audio = record(audio)
    voice = record(audio.get("voice"))
    checks = {item.get("id") for item in audio.get("listen_check") or [] if isinstance(item, dict)}
    segments = [item for item in audio.get("segments") or [] if isinstance(item, dict)]

    def seconds(label: str) -> float:
        total = 0.0
        for item in segments:
            if item.get("label") == label:
                try:
                    total += float(item.get("end_s")) - float(item.get("start_s"))
                except (TypeError, ValueError):
                    continue
        return total

    speech_s = voice.get("speech_s")
    speech_s = float(speech_s) if isinstance(speech_s, (int, float)) else seconds("speech")
    sung = voice.get("reading") == "words may be sung" or bool(checks & {"sung_or_spoken", "unclear_words"})
    over_music = speech_s > 0 and (sung or voice.get("reading") == "bed under the voice")
    music = (over_music or seconds("non_speech_signal") >= MIN_SIGNAL_S
             or bool(checks & {"wordless_sound", "bed_identity"}))
    onsets = record(audio.get("onsets")).get("count")
    cuts = record(audio.get("cut_alignment")).get("cuts")
    effects = ((isinstance(onsets, (int, float)) and onsets > 0) or (isinstance(cuts, (int, float)) and cuts > 0)
               or "accents_on_cuts" in checks)
    applies = {"music_fit": music, "track_identity": music, "sung_or_spoken": over_music,
               "voice_timbre": speech_s > 0 and not sung, "sfx_quality": effects}
    return [item for item in LISTEN_ITEMS if applies[item]]


def listen_note(evidence: Any, language: str) -> str | None:
    """One line telling the creator the sound was measured and not heard, naming only what applies, or None.

    Derived from the evidence alone: a local file's sound measurement (`media.audio`) that left questions only an
    ear can answer (`listen_check`), with no whole-video viewing, which watches with the sound on, in the run. The
    line names only the items `listen_items` finds in the measurement; with none, there is no line."""
    audio = record(record(record(evidence).get("media")).get("audio"))
    checks = [item for item in audio.get("listen_check") or [] if isinstance(item, dict) and item.get("ask")]
    if not checks:
        return None
    if record(record(evidence).get("viewer_observations")).get("status") == "available":
        return None
    items = listen_items(audio)
    if not items:
        return None
    words = record(record(_CATALOG.get(language)).get("listen")) or _CATALOG["en"]["listen"]
    phrases = [words["items"][item] for item in items]
    joined = phrases[0] if len(phrases) == 1 else words["sep"].join(phrases[:-1]) + words["last_sep"] + phrases[-1]
    return words["line"].replace("{items}", joined)
