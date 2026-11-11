"""Bounded candidate authoring and deterministic assembly; never calls a model."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

BATCH_SIZE = 10
PLAN = "idea_work_plan.json"
SCHEMA = "idea-batches.v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(path, value):
    # 原子替换：中断后重复同批可恢复，不能留下半份状态。
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


def assemble(state):
    slots = ranges(state)
    if len(state["submissions"]) != len(slots):
        raise ValueError("Missing batches; no IdeaSet or report may be delivered")
    report = state["submissions"][str(len(slots))].get("report")
    if not isinstance(report, dict):
        raise ValueError("Last batch requires report fields")
    return {**state["metadata"], **report, "ideas": [x for i in range(1, len(slots) + 1)
                                                   for x in state["submissions"][str(i)]["ideas"]]}


def append_batch(run_dir, payload):
    # 主入口持有文件锁；相同内容重放不新增创作次数，冲突不能覆盖。
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
        entry["report"] = report
    elif "report" in payload:
        raise ValueError("Report fields belong only to the final batch")
    previous = state["submissions"].get(str(batch_id))
    timing = json.loads((run_dir / "stage_timing.json").read_text())
    if (timing.get("core") or {}).get("generation_attempts", 0) or (timing.get("core") or {}).get("rendered"):
        raise ValueError("Core has started; use its one aggregate revision, not batch replacement")
    if previous is not None and previous != entry:
        raise ValueError("Conflicting batch replay; accepted candidates cannot be replaced")
    state["submissions"][str(batch_id)] = entry
    save(run_dir / PLAN, state)
    info = progress(state, run_dir)
    if not info["missing_batches"]:
        save(run_dir / "idea_set.json", assemble(state))
    return {"status": "ready_for_core" if not info["missing_batches"] else "awaiting_batches",
            "stage": "batch", "delivery_ready": False, "idempotent_replay": previous is not None,
            "next_action": "Run core now, then validated export and exact file emission." if not info["missing_batches"]
                           else "Author the next batch now. Accepted fragments are not a deliverable. Do not answer yet.", **info}


def check_core_plan(run_dir, core):
    if not (run_dir / PLAN).exists():
        return
    state = load_plan(run_dir)
    if state["submissions"]:
        # 保留完整旧IdeaSet入口；一旦采用分片，不能用手写半份绕过缺批门。
        assemble(state)
        core["initial_authoring_submissions"] = len(state["submissions"])
        core["aggregate_validation_attempts"] = int(core.get("generation_attempts", 0)) + 1
        core["authoring_pass_accounting"] = "Initial batches plus at most one aggregate revision; not two model calls"
