#!/usr/bin/env python3
"""Set up one analysis of a link or an attached file and start observing it, in one command.

    cd '<run directory>' && python3 begin_analysis.py --url '<link>' | --file-ref 'kabo-file:<id>'
        --subject-state <state> --mode <diagnosis|content_read|craft_teardown|transcript_export>
        [--platform <platform>] [--question '<the creator's words>' | --question-file <file>]
        [--focus <id>[,<id>]] [--ask identify_track] [--confirmed-by-user] [--duration-s <seconds>]
    python3 begin_analysis.py --workspace '<user-workspace>' <the same arguments>

Run it from the reserved run directory, after the run was declared (`start_skill_run`), because the observation it
starts is the first fetch. Where the host has no `start_skill_run`, there is nothing to declare and wait for: with
`--workspace` it reserves the run itself first, exactly as `static_host.py init --workspace` does, prints
`Run directory: <path>` on its first line and goes on inside that run, so setup is one command. Everything is checked
before the run is reserved, so a refused command leaves no run behind. It does, in order, what four separate steps did
and still do on their own:

1. the request (`analysis/video-analysis-request.json`), exactly as prepare_link_request.py writes it;
2. the creator's words, verbatim, in `analysis/question.txt` (empty for a bare link);
3. the method cards chosen from those words (`analysis/method.json`), exactly as select_method.py chooses them
   before the fetch, and the brief's sections 5-7 for them (`analysis/rules.md`, prepare_analysis.write_rules),
   which depend on the request alone and are read while the evidence arrives;
4. the observation: observe_video.py's first run, whose output it prints unchanged (the hand-over calls, the
   result files and the one resume command; the resume command is observe_video.py's own).

Before that output come at most two lines of its own: the run directory (with `--workspace` only) and, for a mode with
a brief, where sections 5-7 are to be read (`references/diagnosis-rules.md` when this run's rules are the default
diagnosis's, already in context where the host preloads it; otherwise `analysis/rules.md`).

Everything is checked before anything is written: a card id problem exits 2 with select_method.py's message (correct
`--focus` once and run the same command again), any other problem exits 1, and in both cases nothing was written and
nothing was fetched. Once the request exists it is never written again: a second run with the same request goes on to
the observation, which refuses to start twice, and once the observation is complete a second run is refused.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    parser.add_argument("--workspace", type=Path,
                        help="reserve this request's run in the workspace first (static_host.py init), where no run "
                             "was reserved and declared before")
    args = parser.parse_args(argv)
    try:
        if args.workspace is not None:
            # Checked in full before anything is reserved: a refused command leaves no run behind, and the corrected
            # command reserves the one run.
            prepared(args, "unreserved")
            run = static_host.init(args.workspace)
            # This run, not one an earlier command left in the environment.
            os.environ["KABO_STATIC_RUN_DIR"] = str(run)
            print(f"Run directory: {run}", flush=True)
        else:
            collect_media.bind_run_to_cwd()
            run = static_host.run_dir()
        os.chdir(run)
        question, method, text = prepared(args, run.name)
        if observe_video.state().get("done"):
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
    return observe_video.main(observe)


if __name__ == "__main__":
    raise SystemExit(main())
