"""Golden vectors for the overview frame plan, shared with the server (analyze-content-video/scripts/acv_timing.py).

The connector (kabo packages/creator/src/adapters/connectors/public-video-media.ts, `overview: true`) and the local
extractor (extract_local_frames.py) must pick the same seconds for the same inputs. The inputs that differ between
machines (the decoded luma grids, the detected cuts) are fixed here as data, so both sides compute from the same
numbers:

- `scores`: consecutive 64x64 luma grids and the (picture, text) change units each side must compute from them;
- `plans`: a duration, a frame budget, cuts, dense windows and the per-second change units, and the frames (second,
  kind, reason) and plan counters each side must produce.

The same file sits beside the connector's test as `public-video-media-overview.parity.json`; both tests pin its
sha256, so a change on one side fails until the other side has the same file.

    python3 -B scripts/acv-overview-parity.py           # verify the stored vectors against this repository's code
    python3 -B scripts/acv-overview-parity.py --write   # regenerate them (then copy the file to the server's test)
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "analyze-content-video" / "scripts"))
import acv_timing  # noqa: E402
import extract_local_frames  # noqa: E402

FIXTURE = ROOT / "scripts" / "fixtures" / "acv-overview-parity.json"
DEFAULT_WINDOW = {"start_s": 0.0, "end_s": 50.0, "interval_s": 0.5}
PLAN_KEYS = ("frames", "hook_frames", "body_frames", "body_interval_s", "body_degraded", "shot_start_frames",
             "dense_window_frames", "dense_windows", "dropped_for_budget", "dropped_as_duplicate", "budget_priority",
             "overview", "overview_stride_s", "change_candidates", "change_frames", "anchor_frames")


def grids() -> list[bytes]:
    """Five grids: a scene, the same scene with sensor noise, that brighter, then a caption in its bottom band, a cut."""
    rnd = random.Random(7)
    size = acv_timing.LUMA_GRID_PX
    scene = bytes(min(255, 40 + (x * 2 + y) + rnd.randint(0, 6)) for y in range(size) for x in range(size))
    noisy = bytes(max(0, min(255, value + rnd.randint(-2, 2))) for value in scene)
    brighter = bytes(min(255, value + 12) for value in noisy)
    caption = bytearray(brighter)
    for y in range(50, 54):
        for x in range(8, 56):
            caption[y * size + x] = 235 if (x // 2) % 2 else 20
    cut = bytes(rnd.randint(0, 255) for _ in range(size * size))
    return [scene, noisy, brighter, bytes(caption), cut]


def units_for(duration: float, seed: int, short_by: int = 0) -> tuple[list[list[int]], list[float]]:
    """Per-second change units and cuts that look like an edited video: about one cut in 12 seconds, one caption
    change in 9, and noise below the threshold the rest of the time."""
    rnd = random.Random(seed)
    layout = acv_timing.overview_layout(duration)
    units: list[list[int]] = []
    cuts: list[float] = []
    for index in range(max(1, layout["tiles"] - short_by)):
        roll = rnd.random()
        if index == 0:
            units.append([0, 0])
        elif roll < 0.08:
            units.append([rnd.randint(300, 900), rnd.randint(100, 800)])
            cuts.append(round(index * layout["stride_s"] - rnd.uniform(0.05, 0.95), 3))
        elif roll < 0.2:
            units.append([rnd.randint(5, 60), rnd.randint(100, 400)])
        else:
            units.append([rnd.randint(0, 60), rnd.randint(0, 90)])
    return units, cuts


def plan_for(case: dict, units: list[list[int]] | None) -> dict:
    stride = acv_timing.overview_layout(case["duration_s"])["stride_s"]
    return extract_local_frames.plan_frames(
        case["duration_s"], 3.0, 1.0, 2, case["budget"], cuts=case["cuts"], dense_windows=case["dense_windows"],
        overview_units=None if units is None else [tuple(pair) for pair in units], overview_stride_s=stride)


def expected(plan: dict) -> dict:
    frames = [[at, kind, (reason or {}).get("reason")]
              for at, kind, reason in zip(plan["_timestamps"], plan["_kinds"], plan["_reasons"])]
    return {"frames": frames, "plan": {key: plan[key] for key in PLAN_KEYS if key in plan}}


def build() -> dict:
    sequence = grids()
    document = {
        "about": "Shared golden vectors for the overview frame plan (kabo-mcp-plugin scripts/acv-overview-parity.py "
                 "writes them; kabo public-video-media.test.ts and acv-overview-parity.test.mjs read them).",
        "scores": {"grid_px": acv_timing.LUMA_GRID_PX,
                   "grids_base64": [base64.b64encode(grid).decode() for grid in sequence],
                   "units": [list(pair) for pair in acv_timing.change_units(b"".join(sequence))]},
        "units": {},
        "plans": [],
    }
    durations = [(30.0, 1), (50.0, 2), (50.4, 3), (76.2, 4), (120.0, 5), (185.5, 6), (600.0, 7), (1800.0, 8),
                 (3600.4, 9)]
    for duration, seed in durations:
        units, cuts = units_for(duration, seed, short_by=1 if duration == 185.5 else 0)
        key = f"{duration:g}"
        document["units"][key] = units
        card = {"start_s": round(duration * 0.4, 3), "end_s": round(duration * 0.4 + 8, 3), "interval_s": 0.5}
        variants = [(120, cuts, [DEFAULT_WINDOW]), (120, None, [DEFAULT_WINDOW]), (120, cuts, [card, DEFAULT_WINDOW]),
                    (120, cuts, [])]
        if duration in (600.0, 1800.0):
            variants.append((40, cuts, [DEFAULT_WINDOW]))
        for budget, chosen_cuts, windows in variants:
            case = {"units": key, "duration_s": duration, "budget": budget, "cuts": chosen_cuts,
                    "dense_windows": windows}
            case["expect"] = expected(plan_for(case, units))
            document["plans"].append(case)
    return document


def verify(document: dict) -> list[str]:
    problems = []
    sequence = [base64.b64decode(text) for text in document["scores"]["grids_base64"]]
    if [list(pair) for pair in acv_timing.change_units(b"".join(sequence))] != document["scores"]["units"]:
        problems.append("change units differ from the stored scores")
    for index, case in enumerate(document["plans"]):
        units = document["units"][case["units"]]
        got = expected(plan_for(case, units))
        if got != case["expect"]:
            problems.append(f"plan {index} ({case['duration_s']}s, budget {case['budget']}) differs")
        if case["duration_s"] <= acv_timing.OVERVIEW_ABOVE_S and expected(plan_for(case, None)) != got:
            problems.append(f"plan {index}: a video up to {acv_timing.OVERVIEW_ABOVE_S:g}s changed with the overview")
    return problems


def main() -> int:
    if "--write" in sys.argv:
        FIXTURE.write_text(json.dumps(build(), separators=(",", ":")) + "\n", encoding="utf-8")
        print(hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        return 0
    problems = verify(json.loads(FIXTURE.read_text(encoding="utf-8")))
    for problem in problems:
        print(problem)
    print(f"sha256 {hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
