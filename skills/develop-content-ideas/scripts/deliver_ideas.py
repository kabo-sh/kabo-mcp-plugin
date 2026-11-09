#!/usr/bin/env python3
"""Export a validated, complete idea list and its stable selection map."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_idea_report import concise, ordered_ideas, validate_concise
from validate_ideas import validate_idea_set, validate_request

REPORT = "FINAL_IDEAS.md"
RECEIPT = "idea-delivery.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    # 同目录替换，避免宿主读到未写完的报告。
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            name = handle.name
            handle.write(data)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def export(run: Path) -> dict:
    # 失败后不保留上一次可被误交付的最终文件；原始产物和生成预算不变。
    report_path, receipt_path = run / REPORT, run / RECEIPT
    report_path.unlink(missing_ok=True)
    receipt_path.unlink(missing_ok=True)
    request_bytes = (run / "request.json").read_bytes()
    ideas_bytes = (run / "idea_set.json").read_bytes()
    request, ideas = json.loads(request_bytes), json.loads(ideas_bytes)
    core = json.loads((run / "stage_timing.json").read_text())["core"]
    if core.get("status") != "delivered" or core.get("rendered") is not True:
        raise ValueError("No completed core validation. Repair needs_revision in the same run; never reset its budget.")
    errors = validate_request(request, run / "request.json")
    if not errors:
        errors = validate_idea_set(ideas, request, run / "request.json")
    if errors:
        raise ValueError("; ".join(dict.fromkeys(errors)))
    if not ideas.get("ideas"):
        raise ValueError("No validated ideas to deliver; ask for the missing selection context instead.")
    report = concise(ideas, request)
    validate_concise(report, ideas, request)
    if (run / "RESULT.md").read_text(encoding="utf-8") != report:
        raise ValueError("RESULT.md differs from the validated list. Do not deliver stale or edited text.")
    data = report.encode("utf-8")
    receipt = {
        "schema_version": "idea-delivery.v1",
        "status": "validated",
        "report_path": str(report_path),
        "report_sha256": digest(data),
        "request_sha256": digest(request_bytes),
        "idea_set_sha256": digest(ideas_bytes),
        "report_language": ideas.get("report_language", request.get("report_language")),
        "count": len(ideas["ideas"]),
        "items": [{"number": item["rank"], "idea_id": item["idea_id"],
                   "title": item["working_title"]} for item in ordered_ideas(ideas)],
        "next_action": "Call emit_block with block.type=markdown and block.path=report_path. Do not rewrite the report.",
    }
    try:
        atomic_write(report_path, data)
        atomic_write(receipt_path, (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode())
    except OSError:
        report_path.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.run_dir.resolve()), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "not_deliverable", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
