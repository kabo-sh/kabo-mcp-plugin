"""The report's own words in the creator's language: labels, the measurement line, the listen line and the closing
paragraph of a quick first read.

The creator's language is `creator_view.language`, a BCP 47 tag; its primary subtag picks the strings. Chinese and
English keep their wording in the renderer and the measurement-basis module; `references/report-locales.json`
holds every other language the report localizes, and the listen line for all of them. A language it does not list
renders in English.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import observation_order  # noqa: E402

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


def rendered(view: Any) -> bool:
    """Whether the report comes out in the view's own language: Chinese, English or a listed language. Any other
    language renders the report's own words in English, which the reply still has to translate."""
    tag = str(record(view).get("language") or "").strip().lower().replace("_", "-")
    primary = tag.split("-")[0]
    return primary in ("zh", "en") or primary in LOCALES


def labels(language: str) -> dict | None:
    return record(LOCALES.get(language)).get("labels")


def note_words(language: str) -> dict:
    return LOCALES[language]["note"]


# What the line may ask the creator to listen for, in the order it names them.
LISTEN_ITEMS = ("music_fit", "track_identity", "sung_or_spoken", "voice_timbre", "sfx_quality")
# A stretch of other sound shorter than this is a sliver between words, not a music bed.
MIN_SIGNAL_S = 3.0  # a short pause with room tone is not a music bed
MIN_SIGNAL_SHARE = 0.15


def listen_items(audio: Any) -> list[str]:
    """The ear-only questions this measurement leaves open, read from its own readings.

    The voice's timbre only when speech was recognised and not read as sung; sung or spoken only when words were
    heard over music; the music's fit and which track it is only when a bed under the voice, or other sound than
    speech for at least 3 s and 15% of the video, is present; the effects only when accents were measured on the cuts."""
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
    try:
        duration = float(audio.get("duration_s") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    other = seconds("non_speech_signal")
    music = (over_music or bool(checks & {"wordless_sound", "bed_identity"})
             or (other >= MIN_SIGNAL_S and other >= MIN_SIGNAL_SHARE * duration))
    # Onsets and cuts exist in almost every edit; ask about effects only when accents were measured on the cuts.
    effects = "accents_on_cuts" in checks
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


# What a quick first read heard, by the transcript it kept: the platform's captions (whole), speech recognition over
# the whole video, over its opening only, or nothing.
QUICK_SPEECH = ("captions", "full", "partial", "none")
# Every language the closing paragraph is written in.
QUICK_LANGUAGES = tuple(code for code, entry in _CATALOG.items() if "quick" in entry)


def quick_read(evidence: Any) -> dict | None:
    """The facts a quick first read of a long video states and its offer needs, from the evidence alone; None for any
    other run. Quick means the server sampled the frames (`frames.sampling.mode` quick): a small set of frames at fixed
    moments across a video longer than `observation_order.QUICK_ABOVE_S`."""
    evidence = record(evidence)
    frames = record(evidence.get("frames"))
    sampling = record(frames.get("sampling"))
    if sampling.get("mode") != "quick" or frames.get("status") != "available" or not frames.get("items"):
        return None
    duration = sampling.get("duration_s") or record(evidence.get("media")).get("duration_s")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        return None
    transcript = record(evidence.get("transcript"))
    covered = record(transcript.get("coverage")).get("covered_s")
    heard = None
    if transcript.get("status") != "available":
        speech = "none"
    elif isinstance(covered, list) and len(covered) == 2:
        speech, heard = "partial", max(1, round(float(covered[1]) / 60))
    elif transcript.get("origin") in ("platform_captions", "provider_transcript"):
        speech = "captions"
    else:
        speech = "full"
    return {"duration_s": duration, "minutes": max(1, round(float(duration) / 60)), "frames": len(frames["items"]),
            "speech": speech, "heard_minutes": heard, "eta_minutes": observation_order.offer_minutes(duration)}


def quick_paragraph(quick: Any, language: str) -> str:
    """The closing paragraph of a quick first read in a language from references/report-locales.json (English for
    any other): what was seen and heard, then the offer of a full analysis with its time and its one more credit."""
    quick = record(quick)
    if quick.get("speech") not in QUICK_SPEECH or not quick.get("minutes"):
        return ""
    words = record(record(_CATALOG.get(language)).get("quick")) or _CATALOG["en"]["quick"]
    speech = words["speech"][quick["speech"]].replace("{heard}", str(quick.get("heard_minutes") or ""))
    return (words["line"].replace("{minutes}", str(quick["minutes"])).replace("{frames}", str(quick.get("frames")))
            .replace("{speech}", speech).replace("{eta}", str(quick.get("eta_minutes"))))
