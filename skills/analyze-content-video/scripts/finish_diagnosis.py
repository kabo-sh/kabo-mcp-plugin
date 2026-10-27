#!/usr/bin/env python3
"""Run the existing six diagnosis report steps in order, stopping at the first failure.

This is the final business phase, after the host has read the evidence and the author has saved
video_judgment.json and creator_view.json. It does not fetch, judge, change evidence, finalize a
host run or retry a failed step. The host's normal final wrapper owns that one transition.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def commands(run: Path) -> list[list[str]]:
    scripts = Path(__file__).resolve().parent
    analysis, report = run / "analysis", run / "report"
    steps = [
        ["compose_video_analysis.py", "--judgment", analysis / "video_judgment.json",
         "--evidence", analysis / "content_evidence.json", "--deterministic", analysis / "deterministic.json",
         "--request", analysis / "video-analysis-request.json", "--output", analysis / "video_analysis.json"],
        ["validate_video_analysis.py", analysis / "video_analysis.json", analysis / "content_evidence.json",
         analysis / "video-analysis-request.json"],
        ["build_creator_result.py", "--creator-view", analysis / "creator_view.json",
         "--analysis", analysis / "video_analysis.json", "--evidence", analysis / "content_evidence.json",
         "--request", analysis / "video-analysis-request.json", "--output", analysis / "creator-task-result.json"],
        ["render_video_report.py", analysis / "creator-task-result.json", report / "VIDEO_DIAGNOSIS.md"],
        ["validate_creator_shape.py", analysis / "creator-task-result.json", analysis / "video_analysis.json",
         analysis / "content_evidence.json"],
        ["validate_creator_report.py", report / "VIDEO_DIAGNOSIS.md", "--emit-report"],
    ]
    return [[sys.executable, "-B", str(scripts / step[0]), *map(str, step[1:])] for step in steps]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not (run / "analysis").is_dir():
        parser.error("--run-dir must name the existing reserved run containing analysis/")
    (run / "report").mkdir(exist_ok=True)
    for command in commands(run):
        result = subprocess.run(command, cwd=run)
        if result.returncode:
            print(f"Diagnosis report stopped at {Path(command[2]).name}; no later step ran.", file=sys.stderr)
            return result.returncode if result.returncode > 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
