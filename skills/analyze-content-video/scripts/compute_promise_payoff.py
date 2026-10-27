#!/usr/bin/env python3
"""Measure how long a video takes to pay off what it promised.

This is the one causal frame that reproduced across all three products read for V3 — one of them
names it outright, twice, in the study transcript; another reaches for it without naming it,
faulting an opening that describes instead of opening a loop and burying the three takeaways at
the end. Both ends already exist in this Skill's dimension vocabulary as
`first_frame_promise` and `payoff`. What was missing is the distance between them.

The split of labour follows the rest of the module. Where the promise is stated is decidable: it
is the first thing said or shown inside the declared hook window, and the evidence carries both
tracks on one timeline. Where it is paid off is not decidable — a payoff is a meaning, not a
pattern — so this refuses to guess. The model names the cue it believes pays off; this checks that
the cue exists, that it comes after the promise, and reports the gap. A number nobody can dispute,
computed over a judgement somebody made.

    python3 compute_promise_payoff.py <content_evidence.json> [--payoff-cue N] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def hook_window(evidence: dict) -> float | None:
    """The declared hook window, or None when the evidence does not carry one.

    This used to fall back to 3.0 whenever `sampling_plan` was absent, which is the exact
    mistake SKILL.md warns about two paragraphs above the field: a Short lives or dies in
    about three seconds, long-form has fifteen to thirty. A frameless run carries no
    sampling plan at all, so that fallback judged every long video's promise over a window
    four to ten times too short -- and reported the result as if it had been measured.

    None is not a degraded number; it is the absence of one. The caller says so out loud
    rather than computing over a window nobody declared.
    """
    plan = ((evidence.get("frames") or {}).get("sampling_plan")) or {}
    window = plan.get("hook_window_s")
    return float(window) if isinstance(window, (int, float)) else None


def promise_anchor(evidence: dict, window: float) -> dict:
    """The first thing the viewer is told, spoken or on screen, inside the hook window."""
    cues = ((evidence.get("transcript") or {}).get("cues")) or []
    spoken = [
        {"index": i, "start_s": c["start_s"], "text": c["text"]}
        for i, c in enumerate(cues)
        if isinstance(c.get("start_s"), (int, float)) and c["start_s"] <= window and c.get("text")
    ]
    if spoken:
        first = min(spoken, key=lambda c: c["start_s"])
        return {"status": "located", "source": "transcript_cue", "cue_index": first["index"],
                "at_s": first["start_s"], "text": first["text"]}

    transcript = evidence.get("transcript") or {}
    if transcript.get("status") == "available" and not cues:
        # The defect this module already carries a scar from: a transcript recorded as present
        # whose words never reached the object.
        return {"status": "unavailable", "reason":
                "the transcript is recorded as available but no cue text reached the evidence "
                "object, so what was said in the hook window cannot be read"}
    return {"status": "unavailable", "reason":
            f"nothing is spoken inside the {window}s hook window, and this evidence carries no "
            "on-screen text track to read a written promise from"}


def compute(evidence: dict, payoff_cue: int | None) -> dict:
    window = hook_window(evidence)
    cues = ((evidence.get("transcript") or {}).get("cues")) or []
    if window is None:
        # No declared window, no measurement. Reporting a distance computed over a guessed
        # window would put an invented number in the one place this module refuses to invent
        # them -- and it would look measured, which is worse than looking absent.
        return {
            "rule_version": "promise-payoff.v1",
            "hook_window_s": None,
            # The reason has to cover both shapes this returns None for: no sampling plan at
            # all, and a plan that carries no usable `hook_window_s`. Naming only the first
            # sends whoever reads it looking for a missing object that is right there.
            "promise": {"status": "unavailable", "reason":
                        "this evidence declares no valid hook window, so there is no span this "
                        "video's opening can be judged over"},
            "payoff": {"status": "not_assessable",
                       "reason": "there is no declared hook window to locate a promise inside"},
            "transcript_origin": (evidence.get("transcript") or {}).get("origin"),
        }
    promise = promise_anchor(evidence, window)
    result = {
        "rule_version": "promise-payoff.v1",
        "hook_window_s": window,
        "promise": promise,
        "transcript_origin": (evidence.get("transcript") or {}).get("origin"),
    }

    if promise["status"] != "located":
        result["payoff"] = {"status": "not_assessable",
                            "reason": "there is no located promise to pay off"}
        return result

    if payoff_cue is None:
        # Hand back the timeline the judgement has to be made over, and say plainly that the
        # judgement has not been made. A distance reported without a named payoff would be an
        # invented number in the one place this module refuses to invent them.
        result["payoff"] = {
            "status": "not_located",
            "reason": "no payoff cue was named; a payoff is a meaning and is not derived here",
            "candidates": [{"cue_index": i, "start_s": c.get("start_s"), "text": c.get("text")}
                           for i, c in enumerate(cues) if i > promise["cue_index"]],
        }
        return result

    if not 0 <= payoff_cue < len(cues):
        raise ValueError(f"payoff cue {payoff_cue} is outside the {len(cues)} cues in this evidence")
    payoff = cues[payoff_cue]
    if payoff_cue <= promise["cue_index"]:
        raise ValueError(
            f"payoff cue {payoff_cue} is not after the promise at cue {promise['cue_index']}"
        )

    gap = round(float(payoff["start_s"]) - float(promise["at_s"]), 3)
    result["payoff"] = {"status": "located", "cue_index": payoff_cue,
                        "at_s": payoff["start_s"], "text": payoff.get("text")}
    result["gap_s"] = gap
    result["share_of_video"] = (
        round(gap / evidence["media"]["duration_s"], 3)
        if isinstance((evidence.get("media") or {}).get("duration_s"), (int, float))
        and evidence["media"]["duration_s"] else None
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--payoff-cue", type=int, default=None,
                        help="index of the cue the analysis judges to pay the promise off")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    try:
        result = compute(evidence, args.payoff_cue)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
