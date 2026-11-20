#!/usr/bin/env python3
"""Checks across the transcript sources one run can have, written once.

A run can hold up to three transcripts of the same video: the fetched one (platform captions or the media tool's
speech recognition), the whole-video viewer's, and, for a file on this machine, local speech recognition or a
subtitle file. They disagree more often than they look: speech recognition run on music invents generic lines
("Thanks for watching"), a caption track can be another language, and a fetched transcript can carry one cue
while the viewer heard nothing. Nothing here decides what was said. It marks cues that are no evidence of speech,
names the disagreements, and leaves the reading to the host, which can also compare the on-screen text in the
frames.

Used by build_content_evidence.py (which transcript to keep and what to record), prepare_analysis.py (what the
brief says) and compute_promise_payoff.py (which cues may anchor a promise).
"""
from __future__ import annotations

import re
from typing import Any

# A bracketed sound tag ([Music], (applause)) or a music note. A cue made only of these carries no words.
MARKER = re.compile(r"[\[(][^\[\]()\n]{1,40}[\])]|[♩♪♫♬]")
WORD = re.compile(r"\w", re.UNICODE)
# Lines speech recognition is known to produce on music or silence: the closing lines of the videos it was
# trained on. A cue that is nothing but one of these is no evidence that anyone said it.
GENERIC = [re.compile(pattern, re.IGNORECASE) for pattern in (
    r"^(?:thanks|thank you)(?: (?:so|very) much)?,? for watching(?: (?:this|the|my|our) video)?$",
    r"subscribe to (?:the|my|our|this) channel",
    r"^(?:please )?(?:(?:like|comment),? (?:and|&) )+subscribe",
    r"^(?:don'?t forget to|please) (?:like and )?subscribe",
    r"^see you (?:in the )?next (?:time|video|one)$",
    r"^(?:subtitles?|captions?|transcription) (?:by|from)\b",
    r"amara\.org",
)]
# Too common in real speech to flag on its own; flagged only when it is all a short transcript holds.
SOLITARY = re.compile(r"^(?:thank you|thanks|you|bye)$", re.IGNORECASE)
# A cue may start a little after the measured end: platforms round durations to the second.
END_TOLERANCE_S = 1.0

# Short function words that tell the common Latin-script languages apart. Data, not prose: each set is a
# language's own most frequent words, chosen so that no word is shared between two sets.
STOPWORDS = {
    "en": {"the", "and", "of", "you", "this", "that", "with", "for", "are", "what", "it's", "was", "have", "your"},
    "nl": {"het", "een", "niet", "ik", "jij", "dat", "wat", "zijn", "voor", "maar", "ook", "nog", "dit", "heb"},
    "de": {"der", "die", "und", "ist", "nicht", "das", "ich", "mit", "auf", "sie", "ein", "wir", "auch", "sich"},
    "es": {"el", "los", "las", "es", "por", "una", "con", "del", "pero", "como", "muy", "esto", "porque", "y"},
    "pt": {"não", "uma", "com", "pra", "mas", "você", "isso", "muito", "também", "então", "são", "os", "ao", "é"},
    "fr": {"le", "les", "est", "pas", "nous", "vous", "une", "avec", "pour", "dans", "c'est", "mais", "qui", "et"},
    "it": {"il", "che", "non", "sono", "gli", "della", "questo", "anche", "molto", "perché", "ma", "di", "ho", "lo"},
}
# Writing systems, by code point, for text that is not in the Latin script.
SCRIPTS = (
    ("ja", re.compile(r"[぀-ヿ]")),
    ("ko", re.compile(r"[가-힯]")),
    ("zh", re.compile(r"[一-鿿]")),
    ("cyrillic", re.compile(r"[Ѐ-ӿ]")),
    ("arabic", re.compile(r"[؀-ۿ]")),
    ("devanagari", re.compile(r"[ऀ-ॿ]")),
    ("thai", re.compile(r"[฀-๿]")),
)
# Language codes each writing system covers, so a declared code can be compared with a detected script.
SCRIPT_LANGUAGES = {"ja": {"ja"}, "ko": {"ko"}, "zh": {"zh", "ja", "yue"}, "cyrillic": {"ru", "uk", "bg", "sr", "kk"},
                    "arabic": {"ar", "fa", "ur"}, "devanagari": {"hi", "mr", "ne"}, "thai": {"th"}}


def marker_only(text: Any) -> bool:
    """True when the cue holds only sound tags or music notes, no words."""
    return not WORD.search(MARKER.sub(" ", str(text or "")))


def generic_line(text: Any, *, short_transcript: bool = False) -> bool:
    """True when the cue is a line speech recognition typically invents over music or silence."""
    plain = " ".join(re.sub(r"[.!?…\"']+", " ", MARKER.sub(" ", str(text or ""))).split())
    if not plain:
        return False
    if any(pattern.search(plain) for pattern in GENERIC):
        return True
    return short_transcript and bool(SOLITARY.match(plain))


def suspect_cues(cues: list[dict[str, Any]], duration_s: float | None = None) -> list[dict[str, Any]]:
    """[{index, reason}] for cues that are no evidence of speech: sound tags only, a generic invented line, or a
    start past the end of the video."""
    worded = [cue for cue in cues if not marker_only(cue.get("text"))]
    short = len(worded) <= 2
    found = []
    for index, cue in enumerate(cues):
        start = cue.get("start_s")
        if marker_only(cue.get("text")):
            found.append({"index": index, "reason": "sound_marker_only"})
        elif generic_line(cue.get("text"), short_transcript=short):
            found.append({"index": index, "reason": "generic_line"})
        elif isinstance(duration_s, (int, float)) and isinstance(start, (int, float)) \
                and start > duration_s + END_TOLERANCE_S:
            found.append({"index": index, "reason": "past_end"})
    return found


def worded_cues(cues: list[dict[str, Any]], duration_s: float | None = None) -> list[dict[str, Any]]:
    """The cues that may stand for speech: every cue `suspect_cues` does not mark."""
    marked = {item["index"] for item in suspect_cues(cues, duration_s)}
    return [cue for index, cue in enumerate(cues) if index not in marked]


def language_of(text: Any) -> str | None:
    """A language code (or, outside the Latin script, the writing system's main code) when the text says so
    clearly; None when it is too short or mixed to tell."""
    text = str(text or "")
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 12:
        return None
    for code, pattern in SCRIPTS:
        if len(pattern.findall(text)) >= len(letters) * 0.3:
            return code
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower())
    counts = {code: sum(1 for word in words if word in vocabulary) for code, vocabulary in STOPWORDS.items()}
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    best, runner_up = ranked[0], ranked[1]
    # Three hits and a clear lead: a few shared-looking words in a short line decide nothing.
    if best[1] >= 3 and best[1] >= 2 * max(1, runner_up[1]):
        return best[0]
    return None


def same_language(declared: Any, detected: str | None) -> bool | None:
    """Whether a declared language code and a detected one agree; None when either is unknown."""
    if not isinstance(declared, str) or not declared.strip() or not detected:
        return None
    primary = declared.strip().lower().replace("_", "-").split("-")[0]
    if detected in SCRIPT_LANGUAGES:
        return primary in SCRIPT_LANGUAGES[detected]
    return primary == detected


def _tokens(cues: list[dict[str, Any]]) -> set[str]:
    text = " ".join(str(cue.get("text") or "") for cue in cues).lower()
    words = set(re.findall(r"[^\W\d_]{2,}", text))
    # Scripts written without spaces compare by character.
    words |= {char for char in text if "぀" <= char <= "鿿" or "가" <= char <= "힯"}
    return words


def overlap(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float | None:
    """Shared words over all words of the two cue lists (0..1); None when either has no words."""
    one, two = _tokens(first), _tokens(second)
    if not one or not two:
        return None
    return len(one & two) / len(one | two)


def excerpt(cues: list[dict[str, Any]], limit: int = 160) -> str | None:
    text = " / ".join(" ".join(str(cue.get("text") or "").split()) for cue in cues[:3])
    if not text:
        return None
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def source_entry(source: str, status: str, cues: list[dict[str, Any]], *, used: bool, declared: Any = None,
                 origin: Any = None) -> dict[str, Any]:
    """One `transcript.sources[]` entry."""
    worded = [cue for cue in cues if not marker_only(cue.get("text"))]
    return {"source": source, "used": used, "status": status, "origin": origin if isinstance(origin, str) else None,
            "cue_count": len(cues), "worded_cue_count": len(worded),
            "language": declared if isinstance(declared, str) and declared else None,
            "detected_language": language_of(" ".join(str(cue.get("text") or "") for cue in worded)),
            "excerpt": excerpt(worded)}


def _cue_list(indices: list[int]) -> str:
    return ", ".join(f"cue[{index}]" for index in indices)


def conflicts(fetched: list[dict[str, Any]] | None, viewer: list[dict[str, Any]] | None, *,
              fetched_language: Any = None, viewer_heard: bool = False, duration_s: float | None = None,
              metadata_text: str | None = None, used: list[dict[str, Any]] | None = None,
              used_label: str = "the transcript") -> list[str]:
    """Sentences naming each disagreement among the sources, for the evidence's limitations and the brief.

    `fetched` and `viewer` are the two cue lists (None when that source did not run); `viewer_heard` is true when
    a viewing completed, so an empty viewer list means it heard no words. `used` is the kept transcript, whose cues
    the suspect-cue sentences index."""
    found: list[str] = []
    fetched_worded = worded_cues(fetched or [], duration_s)
    if fetched is not None and viewer is not None and viewer_heard:
        if not viewer and fetched and len(fetched_worded) <= 1:
            found.append(f"The fetched transcript holds {len(fetched)} cue(s) "
                         f"({excerpt(fetched) or 'no words'}) while the whole-video viewer heard no words: treat "
                         "those lines as speech recognition run on music or silence, not as anything said.")
        elif viewer and fetched_worded:
            shared = overlap(fetched_worded, viewer)
            if shared is not None and shared < 0.2:
                found.append(f"The fetched transcript and the whole-video viewer's transcript disagree (about "
                             f"{round(shared * 100)}% shared words): fetched \"{excerpt(fetched_worded)}\", viewer "
                             f"\"{excerpt(viewer)}\". Check the on-screen text in the frames before quoting either.")
            fetched_detected = language_of(" ".join(str(cue.get("text") or "") for cue in fetched_worded))
            viewer_detected = language_of(" ".join(str(cue.get("text") or "") for cue in viewer))
            if fetched_detected and viewer_detected and fetched_detected != viewer_detected:
                found.append(f"The fetched transcript reads as {fetched_detected} while the whole-video viewer heard "
                             f"{viewer_detected}: the fetched track may be another language's.")
    if fetched_worded:
        detected = language_of(" ".join(str(cue.get("text") or "") for cue in fetched_worded))
        if same_language(fetched_language, detected) is False:
            found.append(f"The fetched transcript is declared {fetched_language} but its words read as {detected}.")
        context = language_of(metadata_text)
        language = detected or (fetched_language.split("-")[0].lower()
                                if isinstance(fetched_language, str) and fetched_language else None)
        if context and language and context != language and same_language(language, context) is not True:
            found.append(f"The fetched transcript reads as {language} while the title and caption read as {context}: "
                         "it may be another language's track. Compare it with the words on screen in the frames "
                         "before quoting it.")
    marked = suspect_cues(used or [], duration_s)
    for reason, sentence in (
            ("generic_line", "{cues} {verb} a generic line speech recognition often invents over music or silence: "
                             "not evidence that anyone said it."),
            ("past_end", "{cues} {verb} after the end of the video ({duration}s): the transcript may belong to a "
                         "longer version or another recording."),
            ("sound_marker_only", "{cues} {verb} only a sound marker, no words.")):
        indices = [item["index"] for item in marked if item["reason"] == reason]
        if indices and not (reason == "sound_marker_only" and len(indices) < len(used or [])):
            found.append(f"In {used_label}, " + sentence.format(
                cues=_cue_list(indices), verb="is" if len(indices) == 1 else "are",
                duration=f"{duration_s:g}" if isinstance(duration_s, (int, float)) else "?"))
    return found
