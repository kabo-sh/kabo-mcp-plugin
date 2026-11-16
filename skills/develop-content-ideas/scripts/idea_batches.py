"""Bounded candidate authoring and deterministic assembly; never calls a model."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from validate_ideas import IDEA_SET_SCHEMA, load as load_schema, schema_ref, validate_schema_value

GATE_LISTS = ("selection_missing", "production_missing", "blocked_reasons")

BATCH_SIZE = 10
PLAN = "idea_work_plan.json"
SCHEMA = "idea-batches.v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(path, value):
    # Atomic replace: replaying the same batch after an interruption recovers without leaving half-written state.
    temp = path.with_suffix(".tmp")
    temp.write_bytes(canonical(value) + b"\n")
    os.replace(temp, path)


def create_plan(run_dir, request):
    count = request["idea_count"]
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError("Batch count must be between 1 and 20")
    state = {"schema_version": SCHEMA, "request_sha256": digest((run_dir / "request.json").read_bytes()),
             "count": count, "batch_size": BATCH_SIZE, "submissions": {},
             "metadata": {"schema_version": "idea-set.v3-candidate1",
                          "idea_set_id": "ideas-" + request["request_id"],
                          "request_id": request["request_id"], "created_at": request["created_at"],
                          "task_intent": request["task_intent"], "source_mode": request["source_mode"],
                          "report_language": request.get("report_language", "zh-CN")}}
    if (run_dir / PLAN).exists():
        raise ValueError("Existing authoring plan cannot be reset")
    save(run_dir / PLAN, state)
    return state


def load_plan(run_dir):
    state = json.loads((run_dir / PLAN).read_text())
    if state["schema_version"] != SCHEMA or state["request_sha256"] != digest((run_dir / "request.json").read_bytes()):
        raise ValueError("Authoring plan request digest mismatch; do not reuse another run")
    return state


def ranges(state):
    return [list(range(start, min(start + BATCH_SIZE, state["count"] + 1)))
            for start in range(1, state["count"] + 1, BATCH_SIZE)]


def progress(state, run_dir):
    slots = ranges(state)
    missing = [i for i in range(1, len(slots) + 1) if str(i) not in state["submissions"]]
    next_id = missing[0] if missing else None
    return {"work_plan": PLAN, "request_sha256": state["request_sha256"], "target_count": state["count"],
            "batch_size": BATCH_SIZE, "missing_batches": missing, "next_batch": next_id,
            "next_numbers": slots[next_id - 1] if next_id else [],
            "next_idea_ids": [f"idea-{n:03d}" for n in slots[next_id - 1]] if next_id else [],
            "accepted_titles": [{"idea_id": x["idea_id"], "title": x.get("working_title")}
                                for key in sorted(state["submissions"], key=int)
                                for x in state["submissions"][key]["ideas"]],
            "authoring_submissions": len(state["submissions"]),
            "planned_initial_authoring_passes": len(slots), "aggregate_revision_remaining": 1,
            "next_command": ["python3", str(Path(__file__).with_name("run_ideas_stages.py")),
                             "batch" if missing else "core", "--run-dir", str(run_dir)] +
                            (["--input", f"batch-{next_id}.json"] if missing else []),
            "submission_template": {"request_sha256": state["request_sha256"], "batch_id": next_id,
                                    "ideas": "Author the candidate objects for next_numbers; IDs and ranks are filled by the script.",
                                    "report": "Last batch only: author status, overview, gates, interaction, evidence_summary and optional translations. Other root metadata is filled from request."} if missing else None}


def promote_top_choice(idea_set):
    """The script owns ranks: put overview.recommended_candidate_ids[0] at rank 1.

    Batches are authored before the aggregate recommendation exists, so slot
    order cannot know the top choice. Rank 1 renders as the "shoot first" idea;
    moving that candidate (others keep their relative order) keeps the report
    consistent instead of asking the model to rewrite a 15-20 item file.
    Returns the adjustment or None.
    """
    ideas = idea_set.get("ideas")
    overview = idea_set.get("overview")
    top = overview.get("recommended_candidate_ids") if isinstance(overview, dict) else None
    if not isinstance(ideas, list) or not isinstance(top, list) or not top or not isinstance(top[0], str):
        return None
    if not all(isinstance(x, dict) for x in ideas):
        return None
    ordered = sorted(ideas, key=lambda x: x.get("rank") if type(x.get("rank")) is int else 10**9)
    chosen = next((x for x in ordered if x.get("idea_id") == top[0]), None)
    if chosen is None or chosen is ordered[0]:
        return None
    previous = chosen.get("rank")
    ordered = [chosen] + [x for x in ordered if x is not chosen]
    idea_set["ideas"] = [{**x, "rank": number} for number, x in enumerate(ordered, 1)]
    return {"idea_id": top[0], "from_rank": previous, "to_rank": 1,
            "note": "First recommended candidate moved to rank 1; other candidates keep their relative order."}


def assemble(state, adjustments=None):
    slots = ranges(state)
    if len(state["submissions"]) != len(slots):
        raise ValueError("Missing batches; no IdeaSet or report may be delivered")
    report = state["submissions"][str(len(slots))].get("report")
    if not isinstance(report, dict):
        raise ValueError("Last batch requires report fields")
    idea_set = {**state["metadata"], **report, "ideas": [x for i in range(1, len(slots) + 1)
                                                         for x in state["submissions"][str(i)]["ideas"]]}
    moved = promote_top_choice(idea_set)
    if moved and adjustments is not None:
        adjustments.append(moved)
    return idea_set


def _schema():
    return load_schema(IDEA_SET_SCHEMA)


def _issue(where, failure, **extra):
    path, _, message = failure.partition(": ")
    field = path.removeprefix("$").lstrip(".")
    return {**extra, "path": field, "message": message,
            "error": f"{where}{'.' + field if field and not field.startswith('[') else field}: {message}"}


def batch_issues(state, batch_id, normalized, report):
    """Schema-check one batch before accepting it, so errors stay small and local."""
    schema = _schema()
    candidate = schema_ref(schema, "#/$defs/ideaCandidate")
    issues = []
    for index, item in enumerate(normalized):
        for failure in validate_schema_value(item, candidate, schema, "$"):
            issues.append(_issue(f"ideas[{index}] ({item['idea_id']})", failure,
                                 idea_id=item["idea_id"], batch_index=index))
    if report is not None:
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or []) - set(state["metadata"]) - {"ideas"}
        for field in sorted(required - set(report)):
            issues.append({"path": f"report.{field}", "message": "missing required report field",
                           "error": f"report: missing required property {field!r}"})
        for field, value in report.items():
            if field not in properties:
                issues.append({"path": f"report.{field}", "message": "not an IdeaSet report field",
                               "error": f"report: additional property {field!r} is not allowed; allowed: "
                                        f"{sorted(set(properties) - set(state['metadata']) - {'ideas'})}"})
                continue
            for failure in validate_schema_value(value, properties[field], schema, "$"):
                issues.append(_issue(f"report.{field}", failure))
        known = {f"idea-{n:03d}" for n in range(1, state["count"] + 1)}
        overview = report.get("overview")
        recommended = overview.get("recommended_candidate_ids") if isinstance(overview, dict) else None
        for position, value in enumerate(recommended if isinstance(recommended, list) else []):
            if value not in known:
                issues.append({"path": f"report.overview.recommended_candidate_ids[{position}]",
                               "message": "unknown idea_id",
                               "error": f"report.overview.recommended_candidate_ids[{position}]={value!r} is not one of "
                                        f"idea-001..idea-{state['count']:03d}"})
    return issues


def append_batch(run_dir, payload):
    # The entry point holds the file lock; replaying identical content adds no authoring attempt, conflicts never overwrite.
    state = load_plan(run_dir)
    if not isinstance(payload, dict) or set(payload) - {"request_sha256", "batch_id", "ideas", "report"}:
        raise ValueError("Batch must contain only request_sha256, batch_id, ideas and optional report")
    if payload.get("request_sha256") != state["request_sha256"]:
        raise ValueError("Batch request digest mismatch")
    batch_id = payload.get("batch_id")
    slots = ranges(state)
    if type(batch_id) is not int or not 1 <= batch_id <= len(slots):
        raise ValueError("Unknown batch_id")
    ideas = payload.get("ideas")
    if not isinstance(ideas, list) or len(ideas) != len(slots[batch_id - 1]):
        raise ValueError("Batch must contain exactly its planned number of candidates, at most ten")
    normalized = []
    for number, item in zip(slots[batch_id - 1], ideas):
        if not isinstance(item, dict):
            raise ValueError("Each candidate must be an object")
        identity = {"rank": number, "idea_id": f"idea-{number:03d}"}
        if any(k in item and item[k] != v for k, v in identity.items()):
            raise ValueError("Candidate ID/rank conflicts with its global slot")
        normalized.append({**item, **identity})
    entry = {"ideas": normalized}
    if batch_id == len(slots):
        report = payload.get("report")
        if not isinstance(report, dict) or set(report) & (set(state["metadata"]) | {"ideas"}):
            raise ValueError("Last batch needs report fields, without deterministic metadata or ideas")
        # Production 2026-11-13: the final batch omitted gates.blocked_reasons and the host could not
        # repair the stored batch file, so the user received nothing. An omitted gate list means "none";
        # status rules (e.g. a blocked status still needs a non-empty blocked_reasons) are still checked.
        gates = report.get("gates")
        if isinstance(gates, dict):
            report = {**report, "gates": {key: [] for key in GATE_LISTS if key not in gates} | gates}
        entry["report"] = report
    elif "report" in payload:
        raise ValueError("Report fields belong only to the final batch")
    previous = state["submissions"].get(str(batch_id))
    timing = json.loads((run_dir / "stage_timing.json").read_text())
    if (timing.get("core") or {}).get("generation_attempts", 0) or (timing.get("core") or {}).get("rendered"):
        raise ValueError("Core has started; use its one aggregate revision, not batch replacement")
    if previous is not None and previous != entry:
        raise ValueError("Conflicting batch replay; accepted candidates cannot be replaced")
    if previous is None:
        issues = batch_issues(state, batch_id, normalized, entry.get("report"))
        if issues:
            info = progress(state, run_dir)
            return {"status": "needs_revision", "stage": "batch", "delivery_ready": False, "accepted": False,
                    "batch_id": batch_id, "errors": [x["error"] for x in issues], "error_details": issues,
                    "next_action": (f"Nothing from batch {batch_id} was accepted; earlier batches are kept. "
                                    f"Fix exactly the listed fields in batch-{batch_id}.json (same batch_id, same "
                                    "candidates otherwise) and rerun the same batch command. Do not answer yet."),
                    **{k: info[k] for k in ("work_plan", "request_sha256", "target_count", "missing_batches")},
                    "next_command": ["python3", str(Path(__file__).with_name("run_ideas_stages.py")), "batch",
                                     "--run-dir", str(run_dir), "--input", f"batch-{batch_id}.json"]}
    state["submissions"][str(batch_id)] = entry
    save(run_dir / PLAN, state)
    info = progress(state, run_dir)
    adjustments = []
    if not info["missing_batches"]:
        save(run_dir / "idea_set.json", assemble(state, adjustments))
    if info["missing_batches"]:
        ids = info["next_idea_ids"]
        next_action = (
            f"Batch {batch_id} accepted; {len(info['missing_batches'])} of {info['planned_initial_authoring_passes']} "
            f"batches still missing. The task is NOT finished: in this same turn, author batch-{info['next_batch']}.json "
            f"for {ids[0]}..{ids[-1]} and run next_command. Ending the turn or replying to the user while status is "
            "awaiting_batches is a failed run: the user receives no ideas. Accepted fragments are not a deliverable.")
    else:
        next_action = "Run core now, then validated export and exact file emission."
    result = {"status": "ready_for_core" if not info["missing_batches"] else "awaiting_batches",
              "stage": "batch", "delivery_ready": False, "idempotent_replay": previous is not None,
              "turn_complete": False, "next_action": next_action, **info}
    if adjustments:
        result["rank_adjustment"] = adjustments[0]
    return result


def check_core_plan(run_dir, core):
    if not (run_dir / PLAN).exists():
        return
    state = load_plan(run_dir)
    if state["submissions"]:
        # Keep the legacy complete-IdeaSet entry; once batches are used, a hand-written partial file cannot bypass the missing-batch gate.
        assemble(state)
        core["initial_authoring_submissions"] = len(state["submissions"])
        core["aggregate_validation_attempts"] = int(core.get("generation_attempts", 0)) + 1
        core["authoring_pass_accounting"] = "Initial batches plus at most one aggregate revision; not two model calls"
