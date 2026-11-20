"""Derive the report's sampling facts: extracted frames, cited frames, transcript and owner-metric sources."""
from __future__ import annotations

import math
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # sibling imports must not leave __pycache__ in the Skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_video_sources  # noqa: E402
import report_locale  # noqa: E402


def record(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def number(value: Any, field: str, *, positive: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f"cannot derive data_note: {field} is unknown or invalid")
    return float(value)


def measurement_basis(evidence: dict, analysis: dict, view: dict) -> dict:
    """Count existing frame records and transitive card citations, without a viewing ledger."""
    # 来源写成支持清单里该平台的 label 加「video」（YouTube video、Douyin video …）。
    name = public_video_sources.label(record(evidence.get("content_ref")).get("platform"))
    platform = f"{name} video" if name else None
    local = (record(evidence.get("media")).get("duration_source") == "local_probe"
             or any(record(step).get("step") == "local_extraction" for step in evidence.get("acquisition") or []))
    if not local and platform is None:
        raise ValueError("cannot derive data_note: the video source is not known")
    facts: dict = {"source": "Local video file" if local else platform}
    frames = record(evidence.get("frames"))
    frame_ids = set()
    status = frames.get("status")
    if status == "available" and frames.get("origin") == "extracted_frames":
        items = frames.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("cannot derive data_note: the extracted-frame sample is missing")
        for item in items:
            item = record(item)
            identifier = item.get("frame_id")
            if not isinstance(identifier, str) or not identifier.strip() or identifier in frame_ids:
                raise ValueError("cannot derive data_note: frame IDs are missing or ambiguous")
            number(item.get("t_seconds"), "frame timestamp")
            frame_ids.add(identifier)
        facts.update(frame_kind="extracted", extracted_frames=len(frame_ids))
        plan = record(frames.get("sampling_plan"))
        count = plan.get("frames")
        # The planned frame count is the amount requested: when the provider cannot resolve some timestamps (e.g.
        # the last frame falls past the duration), it returns fewer;
        # fewer than planned is recorded honestly as a gap; more than planned means the frame records do not match
        # this plan.
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < len(frame_ids)):
            raise ValueError("cannot derive data_note: sampling-plan frame count disagrees with frame records")
        if count is not None and count > len(frame_ids):
            facts["requested_frames"] = count
        dense = plan.get("hook_dense_window_s")
        interval = plan.get("hook_interval_s")
        if dense is not None or interval is not None:
            number(dense, "dense sampling window")
            number(interval, "dense sampling interval", positive=True)
        body = plan.get("body_interval_s")
        # A plan with no body grid (body_frames 0) has no body interval: its frames come from the opening, the
        # closing, shot starts and dense windows, as when the default window covers a video of 50s or less. The
        # connector writes null there; local plans before this one wrote 0.0. Each laid window's interval is checked
        # instead.
        no_body = (plan.get("body_frames") == 0 and not isinstance(plan.get("body_frames"), bool)
                   and (body is None or (body == 0 and not isinstance(body, bool))))
        if (body is not None or plan.get("body_degraded") is True) and not no_body:
            number(body, "reduced sampling interval", positive=True)
        for window in plan.get("dense_windows") or []:
            window = record(window)
            if window.get("ignored") is None and window.get("frames"):
                number(window.get("interval_s"), "dense window interval", positive=True)
        # The plan and t_seconds may both be nominal extraction requests. Neither
        # confirms actual decoded timestamps, so no spacing enters measured facts.
    elif status == "available" and frames.get("origin") == "model_observation":
        if not frames.get("observations"):
            raise ValueError("cannot derive data_note: the reported visual descriptions are missing")
        facts["frame_kind"] = "descriptions"
    elif status in ("unavailable", "not_attempted"):
        facts["frame_kind"] = status
    else:
        raise ValueError("cannot derive data_note: the frame provenance is not known")

    observations = {}
    for observation in analysis.get("observations") or []:
        observation = record(observation)
        key = observation.get("observation_id")
        if not isinstance(key, str) or not key.strip() or key in observations:
            raise ValueError("cannot derive data_note: observation IDs are ambiguous")
        observations[key] = observation
    cited = set()
    for card in view.get("cards") or []:
        for ref in record(card).get("evidence_refs") or []:
            if isinstance(ref, str) and ref.startswith("observations."):
                key = ref[len("observations."):]
                if key not in observations:
                    raise ValueError(f"cannot derive data_note: unknown observation {key}")
                cited.update(ref for ref in observations[key].get("evidence_refs") or [] if ref in frame_ids)
            elif isinstance(ref, str) and ref in frame_ids:
                cited.add(ref)
    facts["cited_frame_refs"] = len(cited)

    transcript = record(evidence.get("transcript"))
    if transcript.get("status") == "available":
        label = {"platform_captions": "platform captions", "provider_transcript": "external transcript",
                 "speech_recognition": "machine transcript (wording unverified)",
                 "creator_supplied": "creator-supplied transcript (not checked against audio)"}.get(transcript.get("origin"))
        cues = transcript.get("cues") or []
        if not cues and not str(transcript.get("plain_text") or "").strip():
            raise ValueError("cannot derive data_note: available transcript contains no text")
        if cues:
            for cue in cues:
                cue = record(cue)
                number(cue.get("start_s"), "caption timestamp")
                if not isinstance(cue.get("text"), str) or not cue["text"].strip():
                    raise ValueError("cannot derive data_note: caption text is missing")
            facts["caption_cues"] = len(cues)
    else:
        label = {"no_speech_detected": "no speech detected", "no_audio_track": "no audio track",
                 "no_platform_captions": "platform captions unavailable", "provider_error": "transcript unavailable",
                 "not_attempted": "transcript not retrieved"}.get(transcript.get("status"))
    if label is None:
        raise ValueError("cannot derive data_note: the transcript provenance is not known")
    facts["transcript"] = label
    owner = record(evidence.get("owner_metrics")).get("status")
    if owner not in ("available", "partial", "unavailable"):
        raise ValueError("cannot derive data_note: owner-metric availability is not known")
    facts["owner_metrics"] = owner
    return facts


# This line is relayed as is with the report: the zh view is written in Chinese, a language listed in
# references/report-locales.json in that language, and any other language in English (localized by the host per
# SKILL.md).
# The two wordings carry the same facts and the same numbers; the English wording stays unchanged character
# for character, and the validator compares it character by character per view language.
# Platforms with a common Chinese name are written by that name; the rest use their label (the YouTube,
# Instagram and TikTok wordings are unchanged).
ZH_PLATFORM_NAMES = {"douyin": "抖音", "xiaohongshu": "小红书", "kuaishou": "快手", "bilibili": "哔哩哔哩"}
ZH_WORDS = {
    "source": {**{f"{public_video_sources.label(platform)} video":
                  (f"{ZH_PLATFORM_NAMES[platform]}视频" if platform in ZH_PLATFORM_NAMES
                   else f"{public_video_sources.label(platform)} 视频")
                  for platform in public_video_sources.platform_ids()},
               "Local video file": "本地视频文件"},
    "frames": {"descriptions": "画面来自文字描述，未直接查看像素", "unavailable": "画面帧不可用",
               "not_attempted": "未抽帧"},
    "transcript": {"platform captions": "平台字幕", "external transcript": "外部转写稿",
                   "machine transcript (wording unverified)": "机器转写（措辞未核实）",
                   "creator-supplied transcript (not checked against audio)": "创作者提供的文字稿（未与音频核对）",
                   "no speech detected": "未检测到语音", "no audio track": "没有音轨",
                   "platform captions unavailable": "平台字幕不可用", "transcript unavailable": "转写不可用",
                   "transcript not retrieved": "未获取转写"},
    "owner": {"available": "可用", "partial": "部分可用", "unavailable": "不可用"},
}


def note_language(view: dict) -> str:
    """`zh` for a Chinese view (`zh`, `zh-CN`, `zh-Hant`), a listed language by its primary subtag (`pt-BR` is
    `pt`), `en` for anything else or nothing."""
    return report_locale.report_language(view)


def display_width(text: str) -> int:
    """Columns as the shape gate counts them: a full-width character is two."""
    return sum(2 if unicodedata.east_asian_width(character) in ("W", "F") else 1 for character in text)


def measurement_note(facts: dict, language: str = "en") -> str:
    """One measurement line, with fixed rounding.

    States only countable facts: how many frames were sampled, how many the report cited, and where the transcript and backend data came from. It used to end with a fixed
    "viewing unverified" note, even though the frames had been put in front of the model and the report cited them one by one, and creators still read it as
    "the picture was never looked at" (group feedback, 11-06). The frame count and citation count already show that sampled frames were used, so that note is no longer added."""
    if language == "zh":
        note = _zh_note(facts)
    elif language in report_locale.LOCALES:
        note = _localized_note(facts, report_locale.note_words(language))
    else:
        note = _en_note(facts)
    if display_width(note) > 240:
        raise ValueError("cannot derive data_note within the source-note length limit")
    return note


def _en_note(facts: dict) -> str:
    kind = facts["frame_kind"]
    frames = {"descriptions": "reported visual descriptions, not inspected pixels",
              "unavailable": "frames unavailable", "not_attempted": "frames not sampled"}.get(kind)
    if kind == "extracted":
        frames = f"{facts['extracted_frames']} extracted frames"
        if "requested_frames" in facts:
            frames += f" of {facts['requested_frames']} requested"
    parts = [facts["source"], frames, f"{facts['cited_frame_refs']} cited frame refs"]
    transcript = facts["transcript"]
    if "caption_cues" in facts:
        count = facts["caption_cues"]
        transcript += f" ({count} cue{'s' if count != 1 else ''})"
    parts += [transcript, f"owner metrics {facts['owner_metrics']}"]
    return "; ".join(parts) + "."


def _zh_note(facts: dict) -> str:
    kind = facts["frame_kind"]
    frames = ZH_WORDS["frames"].get(kind)
    if kind == "extracted":
        frames = f"抽取 {facts['extracted_frames']} 帧"
        if "requested_frames" in facts:
            frames += f"（请求 {facts['requested_frames']} 帧）"
    parts = [ZH_WORDS["source"][facts["source"]], frames, f"报告引用 {facts['cited_frame_refs']} 帧"]
    transcript = ZH_WORDS["transcript"][facts["transcript"]]
    if "caption_cues" in facts:
        transcript += f"（{facts['caption_cues']} 条）"
    parts += [transcript, f"后台数据{ZH_WORDS['owner'][facts['owner_metrics']]}"]
    return "；".join(parts) + "。"


def source_platform(source: str) -> str | None:
    """The platform label inside an English source name ("YouTube video" -> "YouTube"); None for a local file."""
    return source[:-len(" video")] if source.endswith(" video") else None


def _localized_note(facts: dict, words: dict) -> str:
    """The same facts and numbers as the English line, in a language from references/report-locales.json."""
    kind = facts["frame_kind"]
    frames = words["frames"].get(kind)
    if kind == "extracted":
        frames = words["frames_extracted"].format(n=facts["extracted_frames"])
        if "requested_frames" in facts:
            frames += words["frames_requested"].format(m=facts["requested_frames"])
    platform = source_platform(facts["source"])
    source = words["source_platform"].format(platform=platform) if platform else words["source_local"]
    parts = [source, frames, words["cited"].format(n=facts["cited_frame_refs"])]
    transcript = words["transcript"][facts["transcript"]]
    if "caption_cues" in facts:
        count = facts["caption_cues"]
        transcript += (words["cues_one"] if count == 1 else words["cues_other"]).format(n=count)
    parts += [transcript, words["owner"].format(status=words["owner_status"][facts["owner_metrics"]])]
    return words["separator"].join(parts) + words["end"]


def image_note(available: int, returned: int, total: Any, completeness: str, owner: str, language: str) -> str:
    """The image-post line in a language from references/report-locales.json (zh and en stay in the builder)."""
    words = report_locale.note_words(language)
    unknown = words["unknown"]
    return words["image"].format(available=available, returned=returned,
                                 total=unknown if total == "unknown" else total,
                                 completeness=unknown if completeness == "unknown" else completeness,
                                 owner=words["owner_status"].get(owner, owner))


def canonical_note(evidence: dict, analysis: dict, view: dict) -> str:
    return measurement_note(measurement_basis(evidence, analysis, view), note_language(view))


def note_matches(note, evidence: dict, analysis: dict, view: dict) -> bool:
    """New results write data_note in the view language; earlier versions wrote an English line for every view
    other than en (zh included, and every language now localized), and replay accepts both.
    Lines from before 1.0.32 had an extra trailing "viewing unverified" segment (Chinese and English forms), which
    replay of old results accepts as well; no localized line other than zh ever carried it."""
    facts = measurement_basis(evidence, analysis, view)
    language = note_language(view)
    current = {measurement_note(facts, language)}
    older = set()
    if language != "en":
        try:
            older.add(measurement_note(facts, "en"))
        except ValueError:
            pass
    before_1_0_32 = older | (current if language in ("zh", "en") else set())
    legacy = {line[:-1] + ("；画面查看未核实。" if line.endswith("。") else "; viewing unverified.") for line in before_1_0_32}
    return note in current | older | legacy
