#!/usr/bin/env python3
"""Set up one analysis of a link or an attached file and start observing it, in one command.

    python3 begin_analysis.py --workspace '<user-workspace>' --url '<link>' | --file-ref 'kabo-file:<id>'
        --subject-state <state> --mode <diagnosis|content_read|craft_teardown|transcript_export>
        [--platform <platform>] [--question '<the creator's words>' | --question-file <file>]
        [--focus <id>[,<id>]] [--ask identify_track] [--confirmed-by-user] [--duration-s <seconds>] [--depth deep]
    cd '<run directory>' && python3 begin_analysis.py <the same arguments without --workspace>

The first command of an analysis of a link or an attached file, on every host. With `--workspace` it reserves the
run itself, exactly as `static_host.py init --workspace` does, prints `Run directory: <path>` on its first line and
goes on inside that run. Without it, it runs inside a run reserved earlier (a run directory or KABO_STATIC_RUN_DIR).
Everything is checked before the run is reserved, so a refused command leaves no run behind.

The script itself fetches nothing: the observation's first run only prints the hand-over calls (and the resume
command). Who makes those calls depends on the host. On a host with the Kabo tool `start_skill_run` the model makes
them, so right after the run directory is printed it calls `start_skill_run` (the credit check, `run_id` the run
directory's last path segment) and waits for its answer before making any printed call; the line after the run
directory says so. On a host without it (Kabo Web) the host makes the printed calls itself inside this command.

It does, in order, what four separate steps did and still do on their own:

1. the request (`analysis/video-analysis-request.json`), exactly as prepare_link_request.py writes it;
2. the creator's words, verbatim, in `analysis/question.txt` (empty for a bare link);
3. the method cards chosen from those words (`analysis/method.json`), exactly as select_method.py chooses them
   before the fetch, and the brief's sections 5-7 for them (`analysis/rules.md`, prepare_analysis.write_rules),
   which depend on the request alone and are read while the evidence arrives;
4. the observation: observe_video.py's first run, whose output it prints unchanged (the hand-over calls, the
   result files and the one resume command; the resume command is observe_video.py's own).

Before that output come at most three lines of its own: with `--workspace` the run directory and the credit-check
line, and, for a mode with a brief, where sections 5-7 are to be read (prepare_analysis.rules_line):
`references/diagnosis-rules.md` when this run's rules are the default diagnosis's (already in context where the host
preloads it), that file plus the topic cards the brief prints when they differ from it only by those cards
(prepare_analysis.topic_cards), otherwise `analysis/rules.md`.

Everything is checked before anything is written: an argument problem (a card id, a missing, unknown or conflicting
flag) exits 2 with one JSON line saying what to correct (correct it once and run the same command again), any other
problem exits 1, and in both cases nothing was written, nothing was reserved and nothing was fetched. Once the
request exists it is never written again: a second run with the same request (without `--workspace`, inside the
run) goes on to the observation, which refuses to start twice, and once the observation is complete a second run is
refused. The exception is a deep run that stopped waiting (`deep_pending`): the same command, inside the run and
without `--workspace`, continues it.

`--depth deep` is the full analysis of a long video, only once the creator accepted the offer a quick first read
ended with; it is a new run of its own (observe_video.py's docstring says what changes).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import collect_media  # noqa: E402
import observation_order  # noqa: E402
import observe_video  # noqa: E402
import prepare_analysis  # noqa: E402
import prepare_link_request  # noqa: E402
import public_video_sources  # noqa: E402
import select_method  # noqa: E402
import static_host  # noqa: E402

REQUEST = Path("analysis/video-analysis-request.json")
QUESTION = Path("analysis/question.txt")
METHOD = Path("analysis/method.json")


def request_for(args: argparse.Namespace, run_name: str) -> dict:
    """The request prepare_link_request.py writes for the same arguments; the platform of a link the support list
    knows is read from the link itself when not given."""
    budget = args.max_connector_calls
    if budget is None:
        budget = prepare_link_request.default_budget(args.mode, args.subject_state)
    if args.file_ref:
        return prepare_link_request.prepare_file(args.file_ref, args.platform, args.subject_state, budget,
                                                 args.confirmed_by_user, run_name)
    platform = args.platform
    if platform is None:
        found = public_video_sources.match_url(str(args.url).strip())
        if found is None:
            raise ValueError("--platform names the platform of the link: "
                             + ", ".join(public_video_sources.platform_ids()))
        platform = found["platform"]
    return prepare_link_request.prepare_url(args.url, platform, args.subject_state, budget, args.confirmed_by_user,
                                            run_name)


def prepared(args: argparse.Namespace, run_name: str) -> tuple[str, dict, str]:
    """The creator's words, the method cards and the request text for this run; raises on any problem."""
    question = (args.question_file.read_text(encoding="utf-8") if args.question_file is not None
                else args.question)
    request = request_for(args, run_name)
    index = select_method.load_index(select_method.LIBRARY)
    method = select_method.select(index, args.mode, select_method.parse_focus(args.focus), None, args.ask)
    return question, method, json.dumps(request, ensure_ascii=False, indent=2) + "\n"


class Parser(argparse.ArgumentParser):
    """argparse, but a refused command line is one JSON line on stdout that says what to correct, as every other
    refusal of this script is, with the same exit code 2."""

    def error(self, message: str) -> None:  # type: ignore[override]
        print(json.dumps({"status": "refused", "error": f"{message}. Nothing was reserved, written or fetched: "
                          "correct the arguments (SKILL.md, analysis step 2) and run the same command again"},
                         ensure_ascii=False))
        raise SystemExit(2)


def credit_line(run: Path) -> str:
    """The line after the run directory: where the host has start_skill_run, the model makes the printed calls, and
    the run is declared (the credit check) before the first of them."""
    return ("Credit check: where the Kabo tool start_skill_run exists, call it now (skill_id analyze-content-video, "
            f"run_id {run.name}) and wait for its answer before making any call printed below; if it fails with "
            "credits_exhausted, tell the creator and stop. This command fetched nothing itself.")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="the public video link exactly as the creator gave it")
    source.add_argument("--file-ref", help="kabo-file:<id> of a video the creator attached in Kabo")
    parser.add_argument("--platform", help="the platform the video is on or for; read from a known link when left out")
    parser.add_argument("--subject-state", required=True,
                        choices=["own_unpublished", "own_published", "third_party", "unknown"])
    parser.add_argument("--mode", required=True, choices=observe_video.MODES)
    words = parser.add_mutually_exclusive_group()
    words.add_argument("--question", default="", help="the creator's own words, verbatim; empty for a bare link")
    words.add_argument("--question-file", type=Path, help="a file holding the creator's words, instead of --question")
    parser.add_argument("--focus", help="zero to two topic card ids, comma-separated")
    parser.add_argument("--ask", choices=select_method.ASKS, help="identify_track for a find-the-song request")
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--max-connector-calls", type=int)
    parser.add_argument("--duration-s", type=float, help="the video's duration, when already known")
    parser.add_argument("--depth", choices=observation_order.DEPTHS,
                        help="deep: the full analysis of a long video, only once the creator accepted it")
    parser.add_argument("--workspace", type=Path,
                        help="reserve this request's run in the workspace first (static_host.py init): the first "
                             "command of every request")
    args = parser.parse_args(argv)
    try:
        if args.workspace is not None:
            # Checked in full before anything is reserved: a refused command leaves no run behind, and the corrected
            # command reserves the one run.
            prepared(args, "unreserved")
            if not args.workspace.is_dir():
                raise ValueError(f"--workspace takes an existing directory to keep this request's run in (the "
                                 f"creator's workspace, or the current directory); {str(args.workspace)!r} is none")
            run = static_host.init(args.workspace)
            # This run, not one an earlier command left in the environment.
            os.environ["KABO_STATIC_RUN_DIR"] = str(run)
            print(f"Run directory: {run}", flush=True)
            print(credit_line(run), flush=True)
        else:
            collect_media.bind_run_to_cwd()
            try:
                run = static_host.run_dir()
            except ValueError:
                raise ValueError("no run is reserved here: begin with --workspace '<user-workspace>' and the same "
                                 "arguments, from any directory (it reserves the run); without --workspace this runs "
                                 "only inside a reserved run directory") from None
        os.chdir(run)
        question, method, text = prepared(args, run.name)
        if observe_video.state().get("done"):
            # A deep analysis after a quick first read is a new run (a new request), never this one again.
            raise ValueError("this run's observation is already complete: never observe twice; go on from what it "
                             "printed (build the evidence)")
        if REQUEST.is_file() and REQUEST.read_text(encoding="utf-8") != text:
            raise ValueError("this run already holds another request; reserve no second run, and continue it with "
                             "observe_video.py as SKILL.md says")
    except select_method.SelectionError as error:
        print(json.dumps({"status": "refused", "error": str(error)}, ensure_ascii=False))
        return 2
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    try:
        if not REQUEST.is_file():
            with REQUEST.open("x", encoding="utf-8") as stream:
                stream.write(text)
        QUESTION.write_text(question, encoding="utf-8")
        METHOD.write_text(json.dumps(method, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if prepare_analysis.write_rules(run / "analysis", args.mode, select_method.parse_focus(args.focus),
                                        args.ask) is not None:
            print(prepare_analysis.rules_line(prepare_analysis.rules_source(run / "analysis"), now=False), flush=True)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    observe = ["--url", args.url if args.url is not None else args.file_ref, "--mode", args.mode]
    if args.duration_s is not None:
        observe += ["--duration-s", str(args.duration_s)]
    if args.depth is not None:
        observe += ["--depth", args.depth]
    return observe_video.main(observe)


if __name__ == "__main__":
    raise SystemExit(main())
