#!/usr/bin/env python3
"""Run the existing six diagnosis report steps in order, stopping at the first failure.

This is the final business phase, after the host has read the evidence and the author has saved
video_judgment.json and creator_view.json. It does not fetch, judge, change evidence, finalize a
host run or retry a failed step. The host's normal final wrapper owns that one transition.

    python3 finish_diagnosis.py --run-dir <run> [--check]

`--check` runs the same steps on scratch copies and writes nothing in the run: it prints every
violation the creator view has against the delivery gates (field, limit and value), so the one
correction of `analysis/creator_view.json` happens before the final step instead of ending the run.
Its exit code carries the verdict, so `--check && finish` never finishes an uncorrected view: 0 is
`ready`, 3 is `needs_correction` (correct the view; not a failure) and 1 is a failed step.
The final step renders the report beside its final name and moves it into place only after every
gate passed, so a failed finish leaves no `report/VIDEO_DIAGNOSIS.md` behind.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acv_timing  # noqa: E402

REPORT = "VIDEO_DIAGNOSIS.md"
# --check exit codes: ready, a failed step, and a view that needs its one correction.
READY, FAILED, NEEDS_CORRECTION = 0, 1, 3
# Failures in these steps come from the authored creator_view, which may be corrected once after --check; the first two steps fail on the judgment itself.
VIEW_STEPS = {"build_creator_result.py", "render_video_report.py", "validate_creator_shape.py",
              "validate_creator_report.py"}

# A failure in a view step that no edit of creator_view.json can fix: the derived lines cannot be derived from the
# evidence, the recorded measurement basis disagrees, or the analysis and evidence files themselves are broken.
# Such a failure is a failed step, so it does not spend the run's one view correction.
NOT_VIEW_FIXABLE = ("cannot derive data_note", "disagrees with the recorded measurement basis",
                    "analysis.observations", "analysis has duplicate observation_id", "content_evidence.json",
                    "video-analysis-request.json")
# ...except a card citing an observation the analysis does not hold, which the view fixes by citing a real one.
VIEW_FIXABLE = ("unknown observation",)


def view_can_fix(found: list[str]) -> bool:
    """False when any message is one that correcting the creator view cannot clear."""
    return not any(any(mark in message for mark in NOT_VIEW_FIXABLE)
                   and not any(mark in message for mark in VIEW_FIXABLE) for message in found)


def commands(run: Path, analysis_out: Path, result_out: Path, report_out: Path) -> list[list[str]]:
    scripts = Path(__file__).resolve().parent
    analysis = run / "analysis"
    steps = [
        ["compose_video_analysis.py", "--judgment", analysis / "video_judgment.json",
         "--evidence", analysis / "content_evidence.json", "--deterministic", analysis / "deterministic.json",
         "--request", analysis / "video-analysis-request.json", "--output", analysis_out],
        ["validate_video_analysis.py", analysis_out, analysis / "content_evidence.json",
         analysis / "video-analysis-request.json"],
        ["build_creator_result.py", "--creator-view", analysis / "creator_view.json",
         "--analysis", analysis_out, "--evidence", analysis / "content_evidence.json",
         "--request", analysis / "video-analysis-request.json", "--output", result_out],
        ["render_video_report.py", result_out, report_out],
        ["validate_creator_shape.py", result_out, analysis_out, analysis / "content_evidence.json"],
        ["validate_creator_report.py", report_out],
    ]
    return [[sys.executable, "-B", str(scripts / step[0]), *map(str, step[1:])] for step in steps]


def violations(output: str) -> list[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    errors = [line[len("ERROR:"):].strip() for line in lines if line.startswith("ERROR:")]
    return errors or lines[-5:]


def check(run: Path) -> int:
    """Every gate of the final step, on scratch copies; the run itself is left untouched."""
    with tempfile.TemporaryDirectory(prefix="acv-check-") as scratch:
        scratch_dir = Path(scratch)
        for command in commands(run, scratch_dir / "video_analysis.json", scratch_dir / "creator-task-result.json",
                                scratch_dir / REPORT):
            step = Path(command[2]).name
            done = subprocess.run(command, cwd=run, capture_output=True, text=True)
            if done.returncode:
                found = violations(done.stdout + "\n" + done.stderr)
                if step in VIEW_STEPS and view_can_fix(found):
                    print(json.dumps({"status": "needs_correction", "step": step, "violations": found},
                                     ensure_ascii=False, indent=1))
                    print("Correct analysis/creator_view.json once for every violation above, then run this check "
                          "once more. Advance to the final step only on status ready.")
                    return NEEDS_CORRECTION
                print(json.dumps({"status": "failed", "step": step, "errors": found}, ensure_ascii=False, indent=1))
                return FAILED
    print(json.dumps({"status": "ready"}))
    print("Run the final step now: the same command without --check.")
    return READY


def finish(run: Path) -> int:
    analysis, report = run / "analysis", run / "report"
    report.mkdir(exist_ok=True)
    final = report / REPORT
    pending = report / f".{REPORT}.pending"
    # Timing only measures: judge runs from the end of prepare to here, validate is this script's own span. A
    # retried finish replaces both entries rather than adding a second pair.
    started = acv_timing.now()
    prepared = acv_timing.last_end(analysis, "prepare")
    if prepared:
        acv_timing.replace(analysis, "judge", prepared, started)
    for command in commands(run, analysis / "video_analysis.json", analysis / "creator-task-result.json", pending):
        result = subprocess.run(command, cwd=run)
        if result.returncode:
            # A failed gate leaves no report file behind: unvalidated output must never be read as the report.
            for leftover in (pending, final):
                leftover.unlink(missing_ok=True)
            print(f"Diagnosis report stopped at {Path(command[2]).name}; no later step ran and no report was "
                  "written.", file=sys.stderr)
            acv_timing.replace(analysis, "validate", started)
            return result.returncode if result.returncode > 0 else 1
    os.replace(pending, final)
    acv_timing.replace(analysis, "validate", started)
    acv_timing.record_reply(analysis, f"report/{REPORT}", len(final.read_text(encoding="utf-8").strip()))
    emitted = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parent / "validate_creator_report.py"),
                              str(final), "--emit-report"], cwd=run)
    return emitted.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true",
                        help="run every gate on scratch copies and print each violation; write nothing. "
                             "Exit 0 is ready, 3 is needs_correction (correct the view, not a failure), "
                             "1 is a failed step")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not (run / "analysis").is_dir():
        parser.error("--run-dir must name the existing reserved run containing analysis/")
    return check(run) if args.check else finish(run)


if __name__ == "__main__":
    raise SystemExit(main())
