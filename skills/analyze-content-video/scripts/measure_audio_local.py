#!/usr/bin/env python3
"""Measure the sound of a video that is on this machine, on one timeline, and say only what clears a threshold.

A local file is never uploaded, so nobody listens to it whole. What can still be done here is measure it: how loud
it is and how that moves, where it is silent, where words are and what sits under them, whether it has a pulse, and
whether the cuts land on sound. Every measure carries the threshold it was read against and a confidence tier, and a
reading below its threshold stays a number in the block and never becomes a finding. What a measure cannot say --
the genre, the mood and whether it fits, which track it is, whether it is trending or licensed, how the voice sounds,
how good an effect is -- goes to a `listen_check` list for the creator, never to the findings.

    python3 measure_audio_local.py --media FILE --artifact analysis/local-media.json
        [--transcript analysis/local-transcript.json] [--deadline-s 40]

Run it after the frame command (extract_local_frames.py): it adds `media.audio` to that command's artifact for the
same file, and reads the cuts that command found (`frames.sampling_plan.shot_detection.cuts_at_s`). Run first, it
writes a frame-less artifact of the same shape; a later frame command then replaces the artifact, so measure again.

**Two passes, ffmpeg first.** One ffmpeg pass over the sound alone gives loudness (EBU R128: integrated, range, true
peak, momentary and short-term over time), silences, full-scale samples and a 50 ms level series -- everything the
speech map, the voice-and-bed comparison and the level findings need, with nothing but ffmpeg. A second pass decodes
samples for numpy: onsets, pulse, the cut alignment, the stereo width and the voice's clarity. Without numpy (or with
KABO_ACV_NO_NUMPY=1) that pass is skipped and `skipped` names what it would have measured.

**It stops itself before the host does**, like every local command here: at `--deadline-s` it keeps what each pass
read, names the second it reached in `measured_until_s`, and says the rest was not read -- unmeasured, not quiet.
Exit 2: no such file or bad arguments; exit 4: the host denies that location; exit 1: nothing could be measured.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # sibling imports must not leave __pycache__ in the Skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acv_timing  # noqa: E402
import extract_local_frames as local_frames  # noqa: E402

SCHEMA_VERSION = "local-audio.v1"
AUDIO_OPERATIONS = frozenset({"measure_audio_levels", "measure_audio_samples"})
DEFAULT_DEADLINE_S = 40.0
# Seconds kept back from the deadline for the numbers and the artifact write.
FINISH_MARGIN_S = 1.5
MIN_PASS_S = 2.0
# The sample pass reads at most this much of the file: past it, numpy's arrays would outgrow a laptop's memory.
MAX_SAMPLE_S = 900.0
SAMPLE_RATE = 16000
RMS_FRAME_S = 0.05
ENVELOPE_S = 0.01
GRID_S = RMS_FRAME_S
# Onsets: a 64 ms window every 16 ms.
FFT_SIZE = 1024
HOP = 256

# Every threshold in one place, copied into the block so a reader sees what a finding was measured against.
# Calibrated on twelve published shorts with human-checked sound facts (speech, singing, music, silence, the
# first frame, loudness): zero wrong claims was the target, and a threshold that produced one was moved or removed.
THRESHOLDS = {
    "silence_floor_db": -40.0,
    "silence_min_s": 0.4,
    "feed_target_lufs": -14.0,
    "quiet_below_lufs": -20.0,
    "loud_above_lufs": -10.0,
    "true_peak_max_dbtp": -1.0,
    "full_scale_share_min": 0.0005,
    "weak_opening_s": 2.0,
    "weak_opening_db": 6.0,
    "level_jump_db": 8.0,
    "level_jump_hold_s": 3,
    "dead_air_edge_s": 0.4,
    "dead_air_inside_s": 1.0,
    "long_pause_in_speech_s": 1.0,
    "wordless_opening_s": 1.5,
    "wordless_gap_s": 2.0,
    "min_speech_s": 8.0,
    "sung_floor_within_db": 8.0,
    "bed_present_within_db": 12.0,
    "bed_absent_below_db": 15.0,
    "duck_db": 6.0,
    "wide_side_to_mid_db": -12.0,
    "speech_like_modulation": 0.5,
    "sung_modulation_below": 0.45,
    "pulse_strong": 0.35,
    "pulse_contrast": 0.2,
    "cuts_min": 6,
    "cut_tolerance_frames": 2,
    "cut_alignment_share_min": 0.6,
    "cut_alignment_margin": 0.25,
    "cut_alignment_p_max": 0.01,
    "dull_voice_hf_share_max": 0.001,
    "hf_split_hz": 4000,
    "noisy_floor_dbfs": -50.0,
    "hum_prominence_db": 15.0,
    "unclear_words_logprob": -0.8,
}
T = THRESHOLDS
# What no measurement here can settle: the creator listens for these; they are never findings.
LISTEN_CHECK = [
    {"id": "genre_mood_fit", "ask": "What the music is (genre, mood) and whether it fits the video's turn and payoff."},
    {"id": "track_identity", "ask": "Which track it is, whether it is trending, and whether it is licensed for this use."},
    {"id": "voice_timbre", "ask": "How the voice sounds: warmth, energy, accent, whether it is synthetic."},
    {"id": "sfx_quality", "ask": "Whether any sound effects are there, and whether each one helps or is noise."},
]


def number(value, digits: int = 2):
    return None if value is None or not math.isfinite(value) else round(float(value), digits)


def db_mean(values: list[float]) -> float | None:
    """Energy mean of dB values: averaging the decibels themselves would let a pause drag a loud second down."""
    finite = [value for value in values if value is not None and math.isfinite(value)]
    if not finite:
        return None
    return 10 * math.log10(sum(10 ** (value / 10) for value in finite) / len(finite))


def percentile(values: list[float], fraction: float) -> float | None:
    ordered = sorted(value for value in values if value is not None and math.isfinite(value))
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))]


def modulation(np, envelope, spans: list[tuple[float, float]]) -> float | None:
    """How much of the level's movement inside these spans is at syllable rate (2-8 Hz): the median, over 2 s
    windows of a 10 ms amplitude envelope, of the 2-8 Hz share of the envelope's fluctuation above 0.5 Hz.

    Speech rises and falls with its syllables and scores high; sustained sung vowels or a pad score low. Beat-driven
    music can score high too, so a high score says "could be speech", never "is speech". It needs the 10 ms
    envelope, which only the numpy pass has: a 50 ms level series aliases and scores everything high.
    """
    if np is None or envelope is None:
        return None
    size, scores = int(round(2.0 / ENVELOPE_S)), []
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, ENVELOPE_S)
    band, above = (freqs >= 2) & (freqs <= 8), freqs > 0.5
    for start_s, end_s in spans:
        first, last = int(start_s / ENVELOPE_S), min(len(envelope), int(end_s / ENVELOPE_S))
        for begin in range(first, last - size + 1, size // 2):
            piece = envelope[begin:begin + size]
            mean = float(piece.mean())
            if mean <= 1e-6:
                continue
            power = np.abs(np.fft.rfft((piece / mean - 1) * window)) ** 2
            total = float(power[above].sum())
            if total > 0:
                scores.append(float(power[band].sum()) / total)
    return number(float(np.median(scores)), 3) if scores else None


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


# ---------------------------------------------------------------------------------------------------------------
# Pass 1: ffmpeg only.

FRAME_LINE = re.compile(r"Parsed_ebur128_0 .*?t:\s*([\d.]+)\s+TARGET:\S+\s+LUFS\s+M:\s*(-?[\d.]+)\s+S:\s*(-?[\d.]+)"
                        r"\s+I:\s*(-?[\d.]+)\s+LUFS\s+LRA:\s*([\d.]+)\s+LU(?:.*?TPK:\s*([-\d. inf]+?)\s*dBFS)?")
RMS_LINE = re.compile(r"Parsed_ametadata_7 .*?lavfi\.astats\.Overall\.RMS_level=(\S+)")
RMS_TIME = re.compile(r"Parsed_ametadata_7 .*?pts_time:([\d.]+)")


def level_chain() -> str:
    """The pass-1 filter chain; the parser below reads each filter by its position, so the order is fixed."""
    return (f"ebur128=peak=true,silencedetect=n={T['silence_floor_db']:g}dB:d={T['silence_min_s']:g},"
            "aformat=sample_fmts=s16,"
            "astats=measure_perchannel=none:measure_overall=Peak_level+Peak_count+Number_of_samples,"
            f"aresample={SAMPLE_RATE},asetnsamples=n={int(SAMPLE_RATE * RMS_FRAME_S)}:p=0,"
            "astats=metadata=1:reset=1:measure_perchannel=none:measure_overall=RMS_level,"
            "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level")


def parse_level_log(log: str, read_s: float) -> dict:
    momentary: list[tuple[float, float]] = []
    short: list[tuple[float, float]] = []
    last_i = last_lra = None
    true_peak = None
    for match in FRAME_LINE.finditer(log):
        at, m_value, s_value, i_value, lra = (float(match.group(k)) for k in range(1, 6))
        momentary.append((at, m_value))
        short.append((at, s_value))
        last_i, last_lra = i_value, lra
        for part in (match.group(6) or "").split():
            peak = local_frames.as_float(part)
            if peak is not None:
                true_peak = peak if true_peak is None else max(true_peak, peak)
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else ""
    integrated = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", summary)
    lra = re.search(r"LRA:\s*([\d.]+)\s*LU", summary)
    peak = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
    rms: list[float] = []
    for line in log.splitlines():
        hit = RMS_LINE.search(line)
        if hit:
            value = local_frames.as_float(hit.group(1))
            rms.append(value if value is not None else -120.0)
    clip = {}
    for key, name in (("sample_peak_dbfs", "Peak level dB"), ("peak_count", "Peak count"),
                      ("samples", "Number of samples")):
        hit = re.search(r"Parsed_astats_3 .*?" + name + r":\s*(-?[\d.]+|-inf)", log)
        clip[key] = local_frames.as_float(hit.group(1)) if hit else None
    silences = local_frames.parse_spans(log, "silence_start", r"silence_end:\s*([\d.]+)", read_s)
    return {
        "momentary": momentary, "short": short, "rms": rms,
        "integrated": float(integrated.group(1)) if integrated else last_i,
        "lra": float(lra.group(1)) if lra else last_lra,
        "true_peak": (local_frames.as_float(peak.group(1)) if peak else None) if summary else true_peak,
        "clip": clip, "silences": silences,
    }


def per_second(momentary: list[tuple[float, float]], read_s: float) -> list[float | None]:
    """Momentary loudness (400 ms windows every 100 ms) averaged by energy into whole seconds."""
    buckets: list[list[float]] = [[] for _ in range(max(1, math.ceil(read_s - 1e-9)))]
    for at, value in momentary:
        index = min(len(buckets) - 1, int(max(0.0, at - 0.05)))
        buckets[index].append(max(value, -120.0))
    return [number(db_mean(bucket), 1) for bucket in buckets]


# ---------------------------------------------------------------------------------------------------------------
# The speech map.

def transcript_spans(transcript: dict | None, media_sha: str) -> tuple[list[tuple[float, float]] | None, dict]:
    """Speech spans from the transcript artifact: word timings where present, cue timings otherwise.

    None means the words were not read (no transcript, another file's, or one that stopped early before any cue),
    and the map then cannot say speech from music. An empty list means the whole file was read and no words heard.
    """
    info: dict = {"source": None, "origin": None, "covered_until_s": None, "mean_avg_logprob": None,
                  "mean_no_speech_prob": None}
    if not isinstance(transcript, dict):
        return None, info
    origin = transcript.get("origin")
    if origin == "speech_recognition" and transcript.get("source_file_sha256") not in (None, media_sha):
        info["source"] = "ignored: written for another file"
        return None, info
    info["origin"] = origin
    status = transcript.get("status")
    if status in ("no_speech_detected",) and transcript.get("complete", True):
        info["source"] = "transcript (no speech heard)"
        return [], info
    cues = [cue for cue in transcript.get("cues") or [] if isinstance(cue, dict)]
    if status != "available" or not cues:
        return None, info
    spans: list[tuple[float, float]] = []
    for cue in cues:
        words = [word for word in cue.get("words") or [] if isinstance(word, dict)]
        for item in words or [cue]:
            start, end = item.get("start_s"), item.get("end_s")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                spans.append((float(start), float(end)))
    spans.sort()
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start - merged[-1][1] < T["silence_min_s"]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    info["source"] = "transcript word timings" if any(cue.get("words") for cue in cues) else "transcript cue timings"
    if transcript.get("complete") is False and isinstance(transcript.get("transcribed_until_s"), (int, float)):
        info["covered_until_s"] = float(transcript["transcribed_until_s"])
    for key, name in (("avg_logprob", "mean_avg_logprob"), ("no_speech_prob", "mean_no_speech_prob")):
        values = [float(cue[key]) for cue in cues if isinstance(cue.get(key), (int, float))]
        info[name] = number(sum(values) / len(values), 3) if values else None
    return [(start, end) for start, end in merged], info


def build_labels(read_s: float, silences: list[dict], speech: list[tuple[float, float]] | None,
                 covered_until_s: float | None) -> list[str]:
    count = max(1, int(round(read_s / GRID_S)))
    unknown = "sound_unclassified"
    labels = ["non_speech_signal" if speech is not None else unknown] * count
    if speech is not None and covered_until_s is not None:
        for index in range(min(count, int(covered_until_s / GRID_S)), count):
            labels[index] = unknown
    for start, end in speech or []:
        for index in range(max(0, int(start / GRID_S)), min(count, int(math.ceil(end / GRID_S)))):
            if labels[index] != unknown:
                labels[index] = "speech"
    for span in silences:
        start, end = span.get("start_s"), span.get("end_s")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            # Rounded inwards, so the sound between two silences keeps at least one cell: a click 14 ms long
            # between two silent seconds is still sound, not part of one long silence.
            first = 0 if start <= 0 else int(math.ceil(start / GRID_S - 1e-9))
            last = count if end >= read_s - 1e-6 else int(math.floor(end / GRID_S + 1e-9))
            for index in range(max(0, first), min(count, last)):
                labels[index] = "silence"
    return labels


def segments_from(labels: list[str]) -> list[dict]:
    segments: list[dict] = []
    for index, label in enumerate(labels):
        if segments and segments[-1]["label"] == label:
            segments[-1]["end_s"] = round((index + 1) * GRID_S, 2)
        else:
            segments.append({"start_s": round(index * GRID_S, 2), "end_s": round((index + 1) * GRID_S, 2),
                             "label": label})
    # A sliver shorter than 0.2s after speech or other sound is the timings' jitter, not a segment. Silence is
    # measured, so a sliver beside it stays: it is the sound that broke the silence.
    tidy: list[dict] = []
    for segment in segments:
        if (tidy and segment["end_s"] - segment["start_s"] < 0.2 and segment["label"] != "silence"
                and tidy[-1]["label"] != "silence"):
            tidy[-1]["end_s"] = segment["end_s"]
            continue
        if tidy and tidy[-1]["label"] == segment["label"]:
            tidy[-1]["end_s"] = segment["end_s"]
            continue
        tidy.append(dict(segment))
    for segment in tidy:
        segment["duration_s"] = round(segment["end_s"] - segment["start_s"], 2)
    return tidy


# ---------------------------------------------------------------------------------------------------------------
# Pass 2: numpy.

def decode_samples(media: Path, channels: int, deadline: float) -> tuple[bytes, str, str]:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-vn", "-sn", "-dn", "-i", str(media),
            "-map", "0:a:0", "-t", f"{MAX_SAMPLE_S:g}", "-ac", str(channels), "-ar", str(SAMPLE_RATE),
            "-f", "f32le", "-"]
    left = deadline - time.monotonic()
    if left < MIN_PASS_S:
        return b"", "failed", "not started: this command's time budget was already used up"
    try:
        result = subprocess.run(args, capture_output=True, timeout=left, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as error:
        return error.output or b"", "completed_partial", "stopped early: this command's time budget was used up"
    except (OSError, subprocess.SubprocessError) as error:
        return b"", "failed", str(error)[:300]
    if result.returncode != 0:
        return b"", "failed", result.stderr.decode("utf-8", "replace").strip()[-300:]
    return result.stdout, "completed", ""


def sample_measures(np, raw: bytes, channels: int, labels: list[str], cuts: list[float] | None,
                    fps: float | None, cuts_on_grid: bool) -> dict:
    data = np.frombuffer(raw[: len(raw) // (4 * channels) * 4 * channels], dtype=np.float32)
    frames = data.reshape(-1, channels) if channels > 1 else data.reshape(-1, 1)
    mono = frames.mean(axis=1)
    read_s = len(mono) / SAMPLE_RATE
    out: dict = {"read_s": round(read_s, 3)}
    if len(mono) < FFT_SIZE * 4:
        return out

    def label_at(seconds: float) -> str:
        index = int(seconds / GRID_S)
        return labels[index] if 0 <= index < len(labels) else "sound_unclassified"

    window = np.hanning(FFT_SIZE).astype(np.float32)
    count = 1 + (len(mono) - FFT_SIZE) // HOP
    freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
    high = freqs >= T["hf_split_hz"]
    flux = np.zeros(count, dtype=np.float32)
    hf_share = np.zeros(count, dtype=np.float32)
    energy = np.zeros(count, dtype=np.float32)
    previous = None
    for begin in range(0, count, 2048):
        stop = min(count, begin + 2048)
        index = np.arange(begin, stop)[:, None] * HOP + np.arange(FFT_SIZE)[None, :]
        spectrum = np.abs(np.fft.rfft(mono[index] * window, axis=1))
        power = spectrum ** 2
        total = power.sum(axis=1) + 1e-12
        energy[begin:stop] = total
        hf_share[begin:stop] = power[:, high].sum(axis=1) / total
        compressed = np.log1p(100.0 * spectrum)
        chunk = np.vstack([previous[None, :] if previous is not None else compressed[:1], compressed])
        flux[begin:stop] = np.maximum(0.0, np.diff(chunk, axis=0)).sum(axis=1)
        previous = compressed[-1]
    hop_s = HOP / SAMPLE_RATE
    times = (np.arange(count) * HOP + FFT_SIZE / 2) / SAMPLE_RATE
    smooth = max(1, int(round(0.4 / hop_s)))
    baseline = np.convolve(flux, np.ones(smooth) / smooth, mode="same")
    envelope = np.maximum(0.0, flux - baseline)

    # Onsets: local maxima within 80 ms standing a standard deviation above the envelope's mean.
    reach = max(1, int(round(0.08 / hop_s)))
    level = envelope.mean() + envelope.std()
    padded = np.pad(envelope, reach, mode="constant")
    local_max = np.ones(count, dtype=bool)
    for shift in range(1, 2 * reach + 1):
        if shift == reach:
            continue
        local_max &= envelope >= padded[shift:shift + count]
    onset_index = np.nonzero(local_max & (envelope > level))[0]
    onsets = times[onset_index]
    out["onsets"] = {"count": int(len(onsets)), "per_second": number(len(onsets) / read_s, 2),
                     "method": "spectral flux, 64 ms window every 16 ms; peaks 1 sd above the mean"}

    # Pulse: the onset envelope's autocorrelation between 40 and 200 beats a minute.
    centred = envelope - envelope.mean()
    size = 1 << int(math.ceil(math.log2(2 * len(centred))))
    spectrum = np.fft.rfft(centred, size)
    autocorr = np.fft.irfft(spectrum * np.conj(spectrum), size)[: len(centred)]
    pulse: dict = {"strength": None, "contrast": None, "bpm": None}
    if autocorr[0] > 0:
        autocorr = autocorr / autocorr[0]
        low, high_lag = int(round(0.3 / hop_s)), int(round(1.5 / hop_s))
        if high_lag < len(autocorr):
            window_ac = autocorr[low:high_lag + 1]
            best = int(np.argmax(window_ac))
            strength = float(window_ac[best])
            contrast = strength - float(np.median(window_ac))
            bpm = 60.0 / ((low + best) * hop_s)
            while bpm < 70:
                bpm *= 2
            while bpm > 180:
                bpm /= 2
            pulse = {"strength": number(strength, 3), "contrast": number(contrast, 3), "bpm": round(bpm)}
    out["pulse"] = pulse

    # Voice clarity and stereo width, read in the speech spans the map already holds.
    span_labels = np.array([label_at(at) for at in times])
    speech = span_labels == "speech"
    clarity: dict = {"hf_share_in_speech": None, "hum": None}
    if speech.sum() * hop_s >= T["min_speech_s"]:
        clarity["hf_share_in_speech"] = number(float((hf_share[speech] * energy[speech]).sum()
                                                     / (energy[speech].sum() + 1e-12)), 4)
    # Mains hum: a 50 or 60 Hz line (and its first harmonic) standing out of its neighbours in the quietest second
    # fifth of the file, at 1 Hz resolution.
    seconds = int(read_s)
    if seconds >= 4:
        blocks = mono[: seconds * SAMPLE_RATE].reshape(seconds, SAMPLE_RATE)
        rms = np.sqrt((blocks ** 2).mean(axis=1)) + 1e-12
        quiet = blocks[np.argsort(rms)[: max(2, seconds // 5)]]
        spectrum = (np.abs(np.fft.rfft(quiet * np.hanning(SAMPLE_RATE), axis=1)) ** 2).mean(axis=0)
        floor = 10 * math.log10(float((quiet ** 2).mean()) + 1e-12)

        def prominence(hz: int) -> float:
            around = np.r_[spectrum[hz - 8:hz - 2], spectrum[hz + 3:hz + 9]]
            return 10 * math.log10(float(spectrum[hz - 1:hz + 2].max()) / (float(np.median(around)) + 1e-20))

        hum = {mains: number(min(prominence(mains), prominence(2 * mains)), 1) for mains in (50, 60)}
        clarity["hum"] = {"prominence_db_50hz": hum[50], "prominence_db_60hz": hum[60],
                          "quiet_seconds_dbfs": number(floor, 1)}
    out["clarity"] = clarity

    if frames.shape[1] >= 2:
        left, right = frames[:, 0], frames[:, 1]
        grid = int(SAMPLE_RATE * GRID_S)
        usable = len(left) // grid * grid
        mid_e = (((left[:usable] + right[:usable]) / 2) ** 2).reshape(-1, grid).mean(axis=1)
        side_e = (((left[:usable] - right[:usable]) / 2) ** 2).reshape(-1, grid).mean(axis=1)
        grid_labels = np.array(labels[: len(mid_e)] + ["sound_unclassified"] * max(0, len(mid_e) - len(labels)))

        def ratio(mask) -> float | None:
            if mask.sum() * GRID_S < 2.0 or mid_e[mask].sum() <= 0:
                return None
            return number(10 * math.log10(float(side_e[mask].sum()) / float(mid_e[mask].sum()) + 1e-12), 1)

        out["stereo"] = {"side_to_mid_db_in_speech": ratio(grid_labels == "speech"),
                         "side_to_mid_db_without_speech": ratio(grid_labels == "non_speech_signal"),
                         "side_to_mid_db_overall": ratio(grid_labels != "silence")}
    else:
        out["stereo"] = None

    step = int(SAMPLE_RATE * ENVELOPE_S)
    out["_envelope"] = np.sqrt((mono[: len(mono) // step * step].reshape(-1, step) ** 2).mean(axis=1)) + 1e-6
    out["cut_alignment"] = cut_alignment(np, cuts, onsets, envelope, times, read_s, fps, cuts_on_grid, label_at,
                                         pulse)
    return out


def binomial_tail(hits: int, trials: int, chance: float) -> float:
    chance = min(max(chance, 1e-9), 1 - 1e-9)
    return sum(math.comb(trials, k) * chance ** k * (1 - chance) ** (trials - k) for k in range(hits, trials + 1))


def cut_alignment(np, cuts, onsets, envelope, times, read_s, fps, cuts_on_grid, label_at, pulse) -> dict:
    record: dict = {"status": "not_assessed", "reason": None}
    if cuts is None:
        record["reason"] = "no cut list in the artifact: run the frame command first"
        return record
    rate = fps if fps and fps > 0 else 30.0
    tolerance = T["cut_tolerance_frames"] / rate + HOP / SAMPLE_RATE / 2 + (0.1 if cuts_on_grid else 0.0)
    unique: list[float] = []
    for cut in sorted(cuts):
        if 0.5 < cut < read_s - 0.5 and (not unique or cut - unique[-1] > 0.1):
            unique.append(cut)
    # A cut inside speech meets the start of a word whether or not anyone timed it: those say nothing about beats.
    outside = [cut for cut in unique if label_at(cut) != "speech"]
    record.update({"cuts": len(unique), "cuts_outside_speech": len(outside), "tolerance_s": round(tolerance, 3)})
    if len(outside) < T["cuts_min"]:
        record["reason"] = (f"fewer than {T['cuts_min']} cuts outside speech" if len(unique) >= T["cuts_min"]
                            else f"fewer than {T['cuts_min']} cuts")
        return record
    if len(onsets) == 0:
        record["reason"] = "no onsets found"
        return record

    def share(points) -> float:
        points = np.asarray(points)
        nearest = np.abs(onsets[None, :] - points[:, None]).min(axis=1)
        return float((nearest <= tolerance).mean())

    observed = share(outside)
    span = read_s - 1.0
    shifted = [share(0.5 + (np.asarray(outside) - 0.5 + span * k / 200) % span) for k in range(1, 200)]
    chance = float(np.mean(shifted))
    hits = int(round(observed * len(outside)))
    record.update({"status": "measured", "share_on_onset": round(observed, 3), "chance_share": round(chance, 3),
                   "p_value": number(binomial_tail(hits, len(outside), chance), 4)})
    strengths = [float(envelope[np.abs(times - cut).argmin()]) for cut in outside]
    record["onset_strength_at_cuts_vs_median"] = number(
        float(np.median(strengths)) / (float(np.median(envelope[envelope > 0])) + 1e-12), 2)
    return record


# ---------------------------------------------------------------------------------------------------------------
# Readings and findings.

def finding(identifier: str, measure: str, claim: str, confidence: str, value=None, threshold=None,
            at_s: float | None = None, end_s: float | None = None) -> dict:
    item = {"id": identifier, "measure": measure, "claim": claim, "confidence": confidence,
            "value": value, "threshold": threshold}
    if at_s is not None:
        item["at_s"] = round(at_s, 2)
    if end_s is not None:
        item["end_s"] = round(end_s, 2)
    return item


def level_jumps(series: list[float | None], silent_floor: float, speech_share) -> list[dict]:
    """Sustained steps in the per-second level, read only over whole seconds (a last partial second is not a
    step). A step with speech on both sides is a voice getting louder or softer between sentences, not a change
    between sections, and is left out."""
    hold = int(T["level_jump_hold_s"])
    values = [value if value is not None else -120.0 for value in series]
    jumps = []
    index = hold
    while index <= len(values) - 1:
        before = values[max(0, index - hold):index]
        after = values[index:index + hold]
        if len(before) < 2 or len(after) < 2 or (speech_share(index - len(before), index) >= 0.8
                                                  and speech_share(index, index + len(after)) >= 0.8):
            index += 1
            continue
        before_level, after_level = statistics.median(before), statistics.median(after)
        change = after_level - before_level
        if abs(change) >= T["level_jump_db"] and max(before_level, after_level) > silent_floor:
            jumps.append({"at_s": float(index), "change_db": round(change, 1), "from_lufs": round(before_level, 1),
                          "to_lufs": round(after_level, 1), "held_s": len(after)})
            index += hold
            continue
        index += 1
    return jumps


def readings(levels: dict, read_s: float, labels: list[str], speech_info: dict, samples: dict | None,
             duration_s: float, np=None) -> tuple[dict, list[dict], list[dict]]:
    """The block's measures, the findings that clear a threshold, and the extra listen-checks they raise."""
    findings: list[dict] = []
    checks: list[dict] = []
    integrated, lra, true_peak = levels["integrated"], levels["lra"], levels["true_peak"]
    series = per_second(levels["momentary"], read_s)
    short = {int(round(at)): value for at, value in levels["short"] if at >= 3 and abs(at - round(at)) < 0.051}
    rms = levels["rms"]
    grid = len(labels)

    def rms_where(label: str) -> list[float]:
        return [value for index, value in enumerate(rms[:grid]) if labels[index] == label]

    whole_file = read_s >= duration_s - 0.5
    # Loudness.
    if integrated is not None and integrated > -69 and whole_file:
        target = T["feed_target_lufs"]
        if integrated < T["quiet_below_lufs"]:
            findings.append(finding(
                "too_quiet", "loudness.integrated_lufs",
                f"Integrated loudness is {integrated:.1f} LUFS, {target - integrated:.1f} LU under the {target:g} LUFS "
                "most feeds play at: on this master, the quiet passages will come up when the platform normalises.",
                "high", integrated, T["quiet_below_lufs"]))
        elif integrated > T["loud_above_lufs"]:
            findings.append(finding(
                "too_loud", "loudness.integrated_lufs",
                f"Integrated loudness is {integrated:.1f} LUFS, {integrated - target:.1f} LU over the {target:g} LUFS "
                "most feeds play at: the platform will turn it down, so the extra level buys nothing.",
                "high", integrated, T["loud_above_lufs"]))
    if true_peak is not None and true_peak > T["true_peak_max_dbtp"]:
        findings.append(finding(
            "true_peak", "loudness.true_peak_dbtp",
            f"True peak reaches {true_peak:+.1f} dBTP, above {T['true_peak_max_dbtp']:g}: a platform re-encode can "
            "turn that into audible distortion.", "high" if true_peak > 0 else "medium",
            true_peak, T["true_peak_max_dbtp"]))
    clip = levels["clip"]
    full_scale_share = None
    if clip.get("samples") and clip.get("peak_count") is not None and (clip.get("sample_peak_dbfs") or -99) >= -0.01:
        full_scale_share = clip["peak_count"] / clip["samples"]
        if full_scale_share >= T["full_scale_share_min"]:
            findings.append(finding(
                "clipping", "loudness.full_scale_samples",
                f"Decoded to 16-bit, {int(clip['peak_count'])} samples ({full_scale_share:.2%} of the track) hit "
                "full scale: played back as delivered, those peaks clip.", "medium", round(full_scale_share, 5),
                T["full_scale_share_min"]))
    opening = [value for value in series[: int(T["weak_opening_s"])] if value is not None]
    rest = [value for value in series[int(T["weak_opening_s"]):] if value is not None and value > -70]
    opening_level, rest_level = db_mean(opening), (percentile(rest, 0.5) if rest else None)
    if opening_level is not None and rest_level is not None and rest_level - opening_level >= T["weak_opening_db"]:
        findings.append(finding(
            "weak_opening", "loudness.series_1s",
            f"The first {T['weak_opening_s']:g} s are {rest_level - opening_level:.0f} dB quieter than the rest "
            f"({opening_level:.0f} vs {rest_level:.0f} LUFS momentary): the opening leans on the picture.",
            "high", round(rest_level - opening_level, 1), T["weak_opening_db"], 0.0, T["weak_opening_s"]))
    def speech_share(first_s: int, last_s: int) -> float:
        cells = labels[int(first_s / GRID_S):int(last_s / GRID_S)]
        return sum(1 for label in cells if label == "speech") / len(cells) if cells else 0.0

    jumps = level_jumps(series[:int(read_s)], T["silence_floor_db"] + 5, speech_share)
    for jump in jumps:
        if jump["at_s"] < T["weak_opening_s"] + 1 and any(item["id"] == "weak_opening" for item in findings):
            continue
        direction = "rises" if jump["change_db"] > 0 else "drops"
        findings.append(finding(
            "level_jump", "loudness.series_1s",
            f"The level {direction} {abs(jump['change_db']):.0f} dB at {clock(jump['at_s'])} "
            f"(from about {jump['from_lufs']:.0f} to {jump['to_lufs']:.0f} LUFS, held for the next "
            f"{jump['held_s']} s).", "high", jump["change_db"], T["level_jump_db"], jump["at_s"]))
    loudness = {
        "integrated_lufs": number(integrated, 1), "range_lu": number(lra, 1), "true_peak_dbtp": number(true_peak, 1),
        "sample_peak_dbfs": number(clip.get("sample_peak_dbfs"), 2),
        "full_scale_samples": int(clip["peak_count"]) if full_scale_share is not None else 0,
        "opening_lufs": number(opening_level, 1), "body_median_lufs": number(rest_level, 1),
        "series_1s": {"interval_s": 1.0, "start_s": 0.0, "momentary_mean_lufs": series,
                      "short_term_lufs": [short.get(second) for second in range(len(series))]},
        "level_jumps": jumps,
    }

    # The speech map.
    segments = segments_from(labels)
    words_read = speech_info.get("source") is not None and not str(speech_info["source"]).startswith("ignored")
    speech_s = sum(segment["duration_s"] for segment in segments if segment["label"] == "speech")
    silences = [segment for segment in segments if segment["label"] == "silence"]
    for segment in silences:
        edge = segment["start_s"] <= 0.05 or segment["end_s"] >= read_s - 0.1
        if edge and segment["duration_s"] >= T["dead_air_edge_s"] and (segment["start_s"] <= 0.05 or whole_file):
            where = "opens on" if segment["start_s"] <= 0.05 else "ends on"
            findings.append(finding(
                "dead_air", "segments.silence",
                f"The video {where} {segment['duration_s']:.1f} s of silence "
                f"({clock(segment['start_s'])}–{clock(segment['end_s'])}).", "high",
                segment["duration_s"], T["dead_air_edge_s"], segment["start_s"], segment["end_s"]))
        elif not edge:
            index = segments.index(segment)
            inside_speech = (0 < index < len(segments) - 1 and segments[index - 1]["label"] == "speech"
                             and segments[index + 1]["label"] == "speech")
            limit = T["long_pause_in_speech_s"] if inside_speech else T["dead_air_inside_s"]
            if segment["duration_s"] >= limit:
                findings.append(finding(
                    "long_pause" if inside_speech else "dead_air", "segments.silence",
                    f"{segment['duration_s']:.1f} s of silence at {clock(segment['start_s'])}"
                    + (" between two spoken lines." if inside_speech else "."), "high",
                    segment["duration_s"], limit, segment["start_s"], segment["end_s"]))
    if words_read and speech_info.get("covered_until_s") is None:
        if speech_s == 0 and read_s > 1:
            findings.append(finding(
                "no_words", "segments.speech",
                "Speech recognition heard no words anywhere in the file: the sound is music, ambience or effects "
                "throughout (which of these is a listen-check).", "high", 0, None))
            checks.append({"id": "wordless_sound", "ask": "The whole track is without words: music, ambience or "
                                                          "effects, and is it the sound you meant?"})
    speech_segments = [segment for segment in segments if segment["label"] == "speech"]
    envelope = (samples or {}).get("_envelope")
    speech_modulation = modulation(np, envelope, [(item["start_s"], item["end_s"]) for item in speech_segments])
    pulse = (samples or {}).get("pulse") or {}
    strong_pulse = ((pulse.get("strength") or 0) >= T["pulse_strong"]
                    and (pulse.get("contrast") or 0) >= T["pulse_contrast"])
    unclear = (speech_info.get("mean_avg_logprob") is not None
               and speech_info["mean_avg_logprob"] < T["unclear_words_logprob"])
    wordless_gaps: list[dict] = []
    if words_read and speech_info.get("covered_until_s") is None and speech_segments:
        first = speech_segments[0]["start_s"]
        head = [segment for segment in segments if segment["end_s"] <= first + 0.01
                and segment["label"] == "non_speech_signal"]
        sounded = sum(segment["duration_s"] for segment in head)
        head_modulation = modulation(np, envelope, [(0.0, first)])
        # A stretch the recogniser heard no words in, but whose level moves at syllable rate, may be speech it
        # missed under music: it is not called wordless.
        if (first >= T["wordless_opening_s"] and sounded >= T["wordless_opening_s"] * 0.8
                and head_modulation is not None and head_modulation < T["speech_like_modulation"]):
            findings.append(finding(
                "wordless_opening", "segments", f"The first words come at {clock(first)}; before that the "
                "track is sound without words.", "medium", round(first, 2), T["wordless_opening_s"], 0.0, first))
        for index, segment in enumerate(segments[1:-1], start=1):
            if (segment["label"] == "non_speech_signal" and segment["duration_s"] >= T["wordless_gap_s"]
                    and segments[index - 1]["label"] == "speech" and segments[index + 1]["label"] == "speech"):
                score = modulation(np, envelope, [(segment["start_s"], segment["end_s"])])
                segment["modulation"] = score
                if score is not None and score < T["speech_like_modulation"]:
                    wordless_gaps.append(segment)
                    findings.append(finding(
                        "wordless_gap", "segments", f"{segment['duration_s']:.1f} s without words at "
                        f"{clock(segment['start_s'])}–{clock(segment['end_s'])}, with sound under it.", "medium",
                        segment["duration_s"], T["wordless_gap_s"], segment["start_s"], segment["end_s"]))
                else:
                    checks.append({"id": "missed_words", "ask": f"{clock(segment['start_s'])}–"
                                   f"{clock(segment['end_s'])}: no words were recognised"
                                   + (", but the level moves like speech" if score is not None else "")
                                   + ". Is someone talking there?"})

    # Voice and bed.
    voice: dict = {"speech_s": round(speech_s, 1), "speech_level_dbfs": None, "floor_under_speech_db": None,
                   "speech_modulation": speech_modulation, "level_in_wordless_gaps_dbfs": None,
                   "rise_when_voice_stops_db": None, "reading": None}
    speech_rms = [value for value in rms_where("speech") if value > -100]
    bed = False
    if speech_s >= T["min_speech_s"] and speech_rms:
        median, floor = percentile(speech_rms, 0.5), percentile(speech_rms, 0.05)
        gap = median - floor
        voice.update({"speech_level_dbfs": number(db_mean(speech_rms), 1), "floor_under_speech_db": number(-gap, 1)})
        gap_rms = [value for segment in wordless_gaps
                   for value in rms[int(segment["start_s"] / GRID_S):int(segment["end_s"] / GRID_S)] if value > -100]
        if gap_rms:
            voice["level_in_wordless_gaps_dbfs"] = number(db_mean(gap_rms), 1)
            voice["rise_when_voice_stops_db"] = number(db_mean(gap_rms) - floor, 1)
        sung = (unclear or gap < T["sung_floor_within_db"]
                or (speech_modulation is not None and speech_modulation < T["sung_modulation_below"]))
        if sung:
            # Words with no gaps between them, whose level does not move like syllables, or that the recogniser
            # was unsure of, may be sung: the "bed" under them is then the song itself, and a voice-over-bed
            # finding would be wrong.
            voice["reading"] = "words may be sung"
            checks.append({"id": "sung_or_spoken", "ask": "Are the words spoken over music, or sung as part of "
                                                          "the track?"})
        elif gap <= T["bed_present_within_db"]:
            bed = True
            voice["reading"] = "bed under the voice"
            findings.append(finding(
                "bed_under_voice", "voice.floor_under_speech_db",
                f"A continuous sound sits about {gap:.0f} dB under the voice: between words the level never falls "
                "further than that.", "medium", round(-gap, 1), -T["bed_present_within_db"]))
            checks.append({"id": "bed_identity", "ask": "The continuous sound under the voice: music, room tone or "
                                                        "ambience, and is it the level you want?"})
            rise = voice["rise_when_voice_stops_db"]
            if rise is not None and rise >= T["duck_db"]:
                findings.append(finding(
                    "ducking", "voice.rise_when_voice_stops_db",
                    f"The sound under the voice comes up about {rise:.0f} dB in the gaps between lines: it is "
                    "ducked under speech.", "medium", rise, T["duck_db"]))
        elif gap >= T["bed_absent_below_db"]:
            voice["reading"] = "no bed under the voice"
            findings.append(finding(
                "no_bed_under_voice", "voice.floor_under_speech_db",
                f"Nothing continuous plays under the voice: between words the level falls about {gap:.0f} dB.",
                "medium", round(-gap, 1), -T["bed_absent_below_db"]))
    stereo = (samples or {}).get("stereo") or {}
    side = stereo.get("side_to_mid_db_in_speech")
    if bed and side is not None and side >= T["wide_side_to_mid_db"]:
        findings.append(finding(
            "wide_under_voice", "stereo.side_to_mid_db_in_speech",
            f"While the voice plays, the stereo side signal is only {abs(side):.0f} dB under the centre: the sound "
            "under the voice is wide, as music or ambience usually is.", "medium", side, T["wide_side_to_mid_db"]))

    # Pulse and cuts.
    if strong_pulse:
        findings.append(finding(
            "pulse", "pulse.strength",
            f"The sound has a regular pulse at about {pulse['bpm']} BPM (or half or double that).", "medium",
            pulse["strength"], T["pulse_strong"]))
    alignment = (samples or {}).get("cut_alignment") or {}
    if alignment.get("status") == "measured":
        share, chance = alignment["share_on_onset"], alignment["chance_share"]
        if (share >= T["cut_alignment_share_min"] and share - chance >= T["cut_alignment_margin"]
                and alignment.get("p_value") is not None and alignment["p_value"] <= T["cut_alignment_p_max"]):
            what = "on the beat" if strong_pulse else "on a sound accent (a beat, a hit or an effect)"
            findings.append(finding(
                "cuts_on_sound", "cut_alignment.share_on_onset",
                f"{share:.0%} of the {alignment['cuts_outside_speech']} cuts outside speech land {what}, within "
                f"{alignment['tolerance_s'] * 1000:.0f} ms, against {chance:.0%} by chance.", "medium",
                share, T["cut_alignment_share_min"]))
            if not strong_pulse:
                checks.append({"id": "accents_on_cuts", "ask": "The cuts land on sound accents: are those effects "
                                                               "you added, and does each one earn its place?"})

    # Voice clarity.
    clarity = dict((samples or {}).get("clarity") or {})
    clarity["mean_avg_logprob"] = speech_info.get("mean_avg_logprob")
    clarity["mean_no_speech_prob"] = speech_info.get("mean_no_speech_prob")
    pauses = [value for index, value in enumerate(rms[:grid])
              if labels[index] == "silence" and 0 < index and value > -119]
    clarity["noise_floor_in_pauses_dbfs"] = number(percentile(pauses, 0.5), 1) if pauses else None
    hf = clarity.get("hf_share_in_speech")
    if hf is not None and hf < T["dull_voice_hf_share_max"] and not strong_pulse:
        findings.append(finding(
            "dull_voice", "clarity.hf_share_in_speech",
            f"Only {hf:.1%} of the voice's energy is above {T['hf_split_hz'] / 1000:g} kHz: it is likely to sound "
            "dull or muffled.", "medium", hf, T["dull_voice_hf_share_max"]))
    hum = clarity.get("hum") or {}
    for mains in (50, 60):
        prominence = hum.get(f"prominence_db_{mains}hz")
        if prominence is not None and prominence >= T["hum_prominence_db"]:
            findings.append(finding(
                "hum", "clarity.hum", f"A {mains} Hz hum (and its harmonic) stands {prominence:.0f} dB out of the "
                "quietest stretches: mains hum in the recording.", "medium", prominence, T["hum_prominence_db"]))
    if unclear:
        checks.append({"id": "unclear_words", "ask": "The recogniser was unsure of the words "
                                                     f"(mean log-probability {speech_info['mean_avg_logprob']:.2f}): "
                                                     "are they clear, or sung?"})
    blocks = {"loudness": loudness, "segments": segments, "voice": voice, "clarity": clarity}
    return blocks, findings, checks


# ---------------------------------------------------------------------------------------------------------------

def cut_list(artifact: dict) -> tuple[list[float] | None, str | None, bool]:
    """The cuts the frame command found: the full-rate list, else the measurement's 0.1 s grid, else shot frames."""
    frames = artifact.get("frames") or {}
    detection = (frames.get("sampling_plan") or {}).get("shot_detection") or {}
    if isinstance(detection.get("cuts_at_s"), list):
        return [float(cut) for cut in detection["cuts_at_s"] if isinstance(cut, (int, float))], \
            "frames.sampling_plan.shot_detection.cuts_at_s", False
    signals = ((artifact.get("media") or {}).get("signals") or {}).get("shots") or {}
    if isinstance(signals.get("cuts_at_s"), list):
        return [float(cut) for cut in signals["cuts_at_s"] if isinstance(cut, (int, float))], \
            "media.signals.shots.cuts_at_s (0.1 s grid)", True
    starts = [item["t_seconds"] - local_frames.SHOT_START_OFFSET_S for item in frames.get("items") or []
              if isinstance(item, dict) and item.get("source") == "shot_start"
              and isinstance(item.get("t_seconds"), (int, float))]
    if starts:
        return starts, "frames.items shot_start frames (cuts near other frames may be missing)", False
    return None, None, False


def frame_rate(facts: dict) -> float | None:
    text = str((facts.get("encoding") or {}).get("frame_rate") or "")
    try:
        top, _, bottom = text.partition("/")
        value = float(top) / float(bottom or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def load_numpy():
    if os.environ.get("KABO_ACV_NO_NUMPY") == "1":
        return None
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def new_artifact(media: Path, facts: dict, input_sha256: str, probe_step: dict, duration: float) -> dict:
    """The frame command's artifact with no frames written, for a measurement that runs first."""
    plan = local_frames.plan_frames(duration, 3.0, 1.0, 2, local_frames.DEFAULT_MAX_FRAMES)
    timestamps = plan.pop("_timestamps")
    plan.pop("_kinds")
    return {"schema_version": "local-media-extraction.v1", "generated_at": local_frames.now(),
            "media_path": media.name, "content_id": media.stem, "input_sha256": input_sha256, "tools": {},
            "steps": [probe_step], "media": facts,
            "frames": {"status": "not_attempted", "selection": "duration_scaled_v1", "sampling_plan": plan,
                       "requested_timestamps": timestamps, "items": [], "skipped": [], "contact_sheets": []},
            "limitations": []}


def add_audio(artifact: dict, block: dict, steps: list, notes: list) -> None:
    """Put the measurement into the artifact, replacing an earlier one and only the notes that one added."""
    media = artifact["media"]
    earlier = media.get("audio") if isinstance(media.get("audio"), dict) else {}
    stale = set(earlier.get("notes") or [])
    artifact["steps"] = [step for step in artifact["steps"] if step.get("operation") not in AUDIO_OPERATIONS] + steps
    artifact["limitations"] = [text for text in artifact["limitations"] if text not in stale] + notes
    media["audio"] = {**block, "notes": notes}
    artifact["generated_at"] = local_frames.now()


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description="Measure the sound of a video on this machine.")
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--transcript", type=Path,
                        help="The local transcript artifact; default local-transcript.json beside --artifact.")
    parser.add_argument("--deadline-s", type=float, default=DEFAULT_DEADLINE_S)
    args = parser.parse_args(argv)
    if not args.deadline_s > 0:
        print("ERROR: --deadline-s must be positive", file=sys.stderr)
        return 2
    deadline = started + args.deadline_s - FINISH_MARGIN_S
    acv_timing.open_for_artifact(args.artifact)

    media = args.media.expanduser()
    if not media.is_absolute():
        print(f"ERROR: --media must be an absolute path; got {media}", file=sys.stderr)
        return 2
    state, why = local_frames.readability(media)
    if state != "ok":
        print(f"ERROR: {why}", file=sys.stderr)
        return 4 if state == "denied" else 2
    probe_step, payload = local_frames.probe(media)
    if probe_step["status"] != "completed":
        print("ERROR: the file's properties could not be read on this machine", file=sys.stderr)
        return 1
    facts = local_frames.read_media_facts(payload)
    duration = facts.pop("_exact_duration_s")
    if duration is None or duration <= 0:
        print("ERROR: this file states no duration, so there is no timeline to measure on", file=sys.stderr)
        return 1
    input_sha256 = local_frames.file_digest(media)
    artifact, problem = local_frames.earlier_artifact(args.artifact, input_sha256)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 2
    if artifact is None:
        artifact = new_artifact(media, facts, input_sha256, probe_step, duration)

    notes: list[str] = []
    steps: list[dict] = []
    if not facts["has_audio"]:
        add_audio(artifact, {"schema_version": SCHEMA_VERSION, "status": "no_audio_track", "measured": [],
                             "unavailable": [], "skipped": [], "findings": [], "listen_check": []},
                  [], ["The file carries no audio track, so its sound was not measured: there is none."])
        local_frames.write_artifact(args.artifact, artifact)
        print(json.dumps({"artifact": str(args.artifact), "status": "no_audio_track"}, indent=2))
        return 0

    level_args = ["-nostdin", "-hide_banner", "-nostats", "-progress", "pipe:1", "-vn", "-sn", "-dn",
                  "-i", str(media), "-map", "0:a:0", "-af", level_chain(), "-f", "null", "-"]
    begun = local_frames.now()
    status, log, reached, note = local_frames.run_pass(level_args, deadline)
    step = {"step": "local_extraction", "operation": "measure_audio_levels", "tool": "ffmpeg",
            "tool_version": local_frames.tool_version("ffmpeg"),
            "invocation_sha256": local_frames.invocation_digest(level_args, media), "started_at": begun,
            "status": status}
    if note:
        step["note"] = note
    steps.append(step)
    if status == "failed":
        notes.append("This command's time ran out before the sound could be read; raise --deadline-s where the host "
                     "allows. Treat the sound as unmeasured." if "time budget" in note else
                     "The sound could not be measured on this machine; treat it as unmeasured.")
        add_audio(artifact, {"schema_version": SCHEMA_VERSION, "status": "unavailable", "measured": [],
                             "unavailable": ["loudness", "segments", "voice", "pulse", "cut_alignment", "clarity"],
                             "skipped": [], "findings": [], "listen_check": []}, steps, notes)
        local_frames.write_artifact(args.artifact, artifact)
        print(json.dumps({"artifact": str(args.artifact), "status": "unavailable", "note": note}, indent=2))
        return 1
    read_s = duration if reached is None else min(duration, reached)
    levels = parse_level_log(log, read_s)
    if levels["momentary"]:
        read_s = max(read_s, min(duration, levels["momentary"][-1][0]))
    until: dict = {}
    if read_s < duration - 0.5:
        until["levels"] = round(read_s, 2)
        notes.append(f"Loudness, silences and the speech map cover the first {read_s:.1f}s of {duration:.1f}s only: "
                     "the measurement stopped there to stay inside this command's time. Past that second the sound "
                     "was not read -- unmeasured, not quiet.")

    transcript_path = args.transcript or args.artifact.parent / "local-transcript.json"
    try:
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        transcript = None
    speech, speech_info = transcript_spans(transcript, input_sha256)
    if speech is None:
        notes.append("No transcript of this file was available, so the map cannot tell speech from other sound: "
                     "run local speech recognition first, then measure again.")
    elif speech_info.get("origin") == "creator_supplied":
        notes.append("Speech spans come from the creator's subtitle file, whose timings were never checked against "
                     "this cut; read the speech map as approximate.")
    labels = build_labels(read_s, levels["silences"], speech, speech_info.get("covered_until_s"))

    np = load_numpy()
    samples = None
    skipped: list[dict] = []
    sample_groups = ["onsets", "pulse", "cut_alignment", "stereo", "clarity.hf_share_in_speech", "clarity.hum",
                     "voice.speech_modulation"]
    cuts, cut_source, cuts_on_grid = cut_list(artifact)
    if np is None:
        skipped = [{"measure": group, "reason": "numpy is not installed here"} for group in sample_groups]
        notes.append("numpy is not installed on this machine, so onsets, pulse, the cut alignment, stereo width, "
                     "voice clarity and the syllable-rate test (which wordless stretches and sung words need) were "
                     "not measured; loudness, silences, the speech map and voice-over-bed were.")
    else:
        channels = min(2, (facts.get("encoding") or {}).get("audio_channels") or 1)
        begun = local_frames.now()
        raw, sample_status, sample_note = decode_samples(media, channels, deadline)
        step = {"step": "local_extraction", "operation": "measure_audio_samples", "tool": "ffmpeg",
                "tool_version": local_frames.tool_version("ffmpeg"),
                "invocation_sha256": local_frames.invocation_digest(["decode", str(media), str(channels)], media),
                "started_at": begun, "status": sample_status if raw else "failed"}
        if sample_note:
            step["note"] = sample_note
        steps.append(step)
        if raw:
            samples = sample_measures(np, raw, channels, labels, cuts, frame_rate(facts), cuts_on_grid)
            sample_s = samples.get("read_s") or 0.0
            if sample_s < duration - 0.5:
                until["samples"] = round(sample_s, 2)
                why = (f"they read at most {MAX_SAMPLE_S:g}s of a file" if sample_s >= MAX_SAMPLE_S - 0.5
                       else "this command's time ran out")
                notes.append(f"Onsets, pulse, cut alignment, stereo width and voice clarity cover the first "
                             f"{sample_s:.1f}s only ({why}); past that they were not measured.")
        else:
            skipped = [{"measure": group, "reason": sample_note or "the samples could not be decoded"}
                       for group in sample_groups]
            if "time budget" in sample_note:
                until["samples"] = 0.0
            notes.append("The samples could not be decoded in time, so onsets, pulse, the cut alignment, stereo "
                         "width and voice clarity were not measured.")

    blocks, findings, checks = readings(levels, read_s, labels, speech_info, samples, duration, np)
    measured = ["loudness", "segments", "voice"]
    if samples:
        blocks["pulse"] = samples.get("pulse")
        blocks["onsets"] = samples.get("onsets")
        blocks["stereo"] = samples.get("stereo")
        alignment = samples.get("cut_alignment") or {}
        alignment["cut_source"] = cut_source
        blocks["cut_alignment"] = alignment
        measured += ["pulse", "onsets", "stereo", "cut_alignment", "clarity"]
    else:
        measured.append("clarity")
    block = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed_partial" if until else "completed",
        "measured": measured,
        "unavailable": [],
        "skipped": skipped,
        "duration_s": round(duration, 3),
        "speech_source": speech_info,
        **blocks,
        "findings": findings,
        "listen_check": LISTEN_CHECK + checks,
        "thresholds": THRESHOLDS,
    }
    if until:
        block["measured_until_s"] = until
    add_audio(artifact, block, steps, notes)
    local_frames.write_artifact(args.artifact, artifact)
    print(json.dumps({"artifact": str(args.artifact), "status": block["status"], "measured": measured,
                      "skipped": [item["measure"] for item in skipped], "measured_until_s": until or None,
                      "findings": [f"{item['id']}: {item['claim']}" for item in findings],
                      "listen_check": [item["id"] for item in block["listen_check"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
