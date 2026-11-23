#!/usr/bin/env python3
"""Run the existing six diagnosis report steps in order, stopping at the first failure.

This is the final business phase, after the host has read the evidence and the author has saved
video_judgment.json and creator_view.json. It does not fetch, judge, change evidence, finalize a
host run or retry a failed step. The host's normal final wrapper owns that one transition.

    python3 finish_diagnosis.py --run-dir <run> [--check [--finish-if-ready]]

`--check` runs the same steps on scratch copies and writes nothing in the run: it prints every
violation the creator view has against the delivery gates (field, limit and value), so the one
correction of `analysis/creator_view.json` happens before the final step instead of ending the run.
Its exit code carries the verdict, so `--check && finish` never finishes an uncorrected view: 0 is
`ready`, 3 is `needs_correction` (correct the view; not a failure) and 1 is a failed step.
`--check --finish-if-ready` saves the separate final command: when the check is `ready` it runs the final step in
the same call and prints exactly what the final step prints (the report, then its `creator_report:` line); on any
other verdict it prints the check's verdict and writes nothing, as `--check` alone does.
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


# What each view gate needs from an earlier one: a gate whose input could not be produced is not run, and the check
# says so, so the one correction is made knowing which gates have not yet looked at the view.
NEEDS = {"render_video_report.py": "build_creator_result.py", "validate_creator_shape.py": "build_creator_result.py",
         "validate_creator_report.py": "render_video_report.py"}
# What each view gate checks, in the words of the view contract, so a violation reads as the field to change.
GATE_TEXT = {"build_creator_result.py": "the view's required fields and next_actions",
             "render_video_report.py": "rendering the report from the view",
             "validate_creator_shape.py": "card order, field limits, citations and wording against the analysis",
             "validate_creator_report.py": "internal names in the rendered report"}
CORRECTION_TEXT = (
    "Correct analysis/creator_view.json once, for every violation above together: each names the field and, for a "
    "length, its limit (the view contract printed with the reference check has every limit; count display columns, "
    "a full-width character is two). Rewrite a field that is too long whole, shorter, rather than trimming its end; cite only "
    "the `observations.<id>` references the contract lists. The judgment stays as saved. Then run this check once "
    "more; advance to the final step only on status ready.")


def check(run: Path, *, quiet_ready: bool = False) -> int:
    """Every gate of the final step, on scratch copies; the run itself is left untouched. `quiet_ready` prints
    nothing on `ready`, so a finish in the same call prints only what the final step prints.

    A view gate that fails does not end the check: every later gate whose input exists still runs, so the
    violations are listed together for the view's one correction instead of one gate at a time."""
    failed_steps: dict[str, list[str]] = {}
    not_run: list[str] = []
    with tempfile.TemporaryDirectory(prefix="acv-check-") as scratch:
        scratch_dir = Path(scratch)
        for command in commands(run, scratch_dir / "video_analysis.json", scratch_dir / "creator-task-result.json",
                                scratch_dir / REPORT):
            step = Path(command[2]).name
            if NEEDS.get(step) in failed_steps or NEEDS.get(step) in not_run:
                not_run.append(step)
                continue
            done = subprocess.run(command, cwd=run, capture_output=True, text=True)
            if not done.returncode:
                continue
            found = violations(done.stdout + "\n" + done.stderr)
            if step not in VIEW_STEPS or not view_can_fix(found):
                print(json.dumps({"status": "failed", "step": step, "errors": found}, ensure_ascii=False, indent=1))
                return FAILED
            failed_steps[step] = found
    if failed_steps:
        verdict: dict = {"status": "needs_correction", "step": next(iter(failed_steps)),
                         "violations": [line for found in failed_steps.values() for line in found]}
        if len(failed_steps) > 1:
            verdict["gates"] = {step: GATE_TEXT[step] for step in failed_steps}
        if not_run:
            verdict["gates_not_run"] = not_run
        print(json.dumps(verdict, ensure_ascii=False, indent=1))
        print(CORRECTION_TEXT + (" The gates in gates_not_run could not run until the view builds; they check "
                                 + "; ".join(GATE_TEXT[step] for step in not_run) + ": recheck those against the "
                                 "view contract before you save." if not_run else ""))
        return NEEDS_CORRECTION
    if not quiet_ready:
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
    parser.add_argument("--finish-if-ready", action="store_true",
                        help="with --check: when the check is ready, run the final step in the same call and print "
                             "exactly what it prints")
    args = parser.parse_args()
    if args.finish_if_ready and not args.check:
        parser.error("--finish-if-ready goes with --check")
    run = args.run_dir.resolve()
    if not (run / "analysis").is_dir():
        parser.error("--run-dir must name the existing reserved run containing analysis/")
    if not args.check:
        return finish(run)
    verdict = check(run, quiet_ready=args.finish_if_ready)
    return finish(run) if args.finish_if_ready and verdict == READY else verdict


if __name__ == "__main__":
    raise SystemExit(main())
