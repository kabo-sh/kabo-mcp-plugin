#!/usr/bin/env python3
"""Read a saved whole-video viewing result (analyze_content_video / get_analysis_run) and keep only what it saw.

The whole-video viewer watches the video with its audio and returns timestamped notes, a transcript, and a
layer of scores, verdicts and advice. This run uses it as eyes and ears only: the notes anchored to a moment
(`result.dimensions[].evidence[]`) and the transcript are kept; every score, summary, verdict and piece of
advice is dropped here, in one place, so it can never reach the evidence, the brief or the report.

Accepted inputs: the tool's complete MCP result (with `structuredContent`, or one JSON text block), the bare
result object, a failed call (an MCP error result, the bare `{code, message, retryable}` failure body a host
may save instead, or the plain text a host shows for it, "MCP error -32602: ..."), or the redacted copy `observe_video.py` persists (`schema_version: acv-whole-video/v1`).

A completed result asked for with `delivery: "download"` carries a `download` object in place of `result` and
`transcript`; `download_offer` finds it, and observe_video.py downloads and checks the complete result (the
same JSON an inline answer carries) before `read` sees it.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

PERSISTED = "acv-whole-video/v1"
CONNECTOR = "kabo-video-analysis"
START_TOOL = "analyze_content_video"
POLL_TOOL = "get_analysis_run"
TERMINAL = {"completed", "failed", "cancelled"}
PENDING = {"created", "queued", "extracting", "transcribing", "analyzing"}
STATUSES = TERMINAL | PENDING
# Everything the viewer returns besides its timestamped notes and its transcript. Recorded on the evidence so a
# reader can see what was left out, never what it said.
DISCARDED_FIELDS = ["overallScore", "dimensions[].score", "dimensions[].summary", "strengths", "improvements",
                    "hooks", "titleIdeas", "viralPotential", "summary", "verdict", "contentTitle"]
RUN_KEYS = ("id", "status", "progress", "result", "transcript", "failure", "createdAt", "updatedAt", "completedAt")
# A failure body's own code is kept verbatim when it is a machine code, not prose.
CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Error codes the service is known to answer with; anything else is kept as `tool_error`.
KNOWN_CODES = ("subscription_required", "quota_exceeded", "rate_limited", "validation_error", "not_found",
               "forbidden", "authentication_required", "service_unavailable", "internal_error", "conflict")


def _int(value: Any) -> bool:
    return type(value) is int and value >= 0


def check_run(run: Any) -> dict[str, Any]:
    """The run object, or ValueError when it is not the tool's complete output (often a truncated save)."""
    if not isinstance(run, dict):
        raise ValueError("the whole-video result is not an object")
    missing = [key for key in RUN_KEYS if key not in run]
    if missing:
        raise ValueError("the whole-video result is incomplete (missing " + ", ".join(missing) + "); save the "
                         "tool's result whole, as returned")
    if not isinstance(run["id"], str) or not UUID.match(run["id"]):
        raise ValueError("the whole-video result carries no analysis id")
    if run["status"] not in STATUSES:
        raise ValueError(f"the whole-video result has an unknown status {run['status']!r}")
    transcript = run["transcript"]
    if transcript is not None:
        if not isinstance(transcript, list) or not all(
                isinstance(cue, dict) and _int(cue.get("startMs")) and _int(cue.get("endMs"))
                and isinstance(cue.get("text"), str) for cue in transcript):
            raise ValueError("the whole-video transcript is not a list of timed cues")
    result = run["result"]
    if result is not None:
        if not isinstance(result, dict) or not isinstance(result.get("dimensions"), list):
            raise ValueError("the whole-video result carries no dimensions list")
        for dimension in result["dimensions"]:
            if not isinstance(dimension, dict) or not isinstance(dimension.get("key"), str) \
                    or not isinstance(dimension.get("evidence"), list):
                raise ValueError("a whole-video dimension carries no key or evidence list")
            for item in dimension["evidence"]:
                if not (isinstance(item, dict) and _int(item.get("startMs")) and _int(item.get("endMs"))
                        and isinstance(item.get("note"), str) and item["note"].strip()):
                    raise ValueError("a whole-video note carries no time span or text")
    failure = run["failure"]
    if failure is not None and not (isinstance(failure, dict) and isinstance(failure.get("code"), str)):
        raise ValueError("the whole-video failure carries no code")
    return run


def redact(run: dict[str, Any]) -> dict[str, Any]:
    """The same run with only what was observed: notes with their spans, and the transcript."""
    result = run.get("result")
    kept = None
    if isinstance(result, dict):
        kept = {"dimensions": [{"key": dimension["key"],
                                "evidence": [{"startMs": item["startMs"], "endMs": item["endMs"], "note": item["note"]}
                                             for item in dimension.get("evidence") or []]}
                               for dimension in result.get("dimensions") or []]}
    failure = run.get("failure")
    return {"id": run["id"], "status": run["status"], "progress": run.get("progress"),
            "failure": ({"code": failure.get("code"), "message": failure.get("message"),
                         "retryable": failure.get("retryable")} if isinstance(failure, dict) else None),
            "transcript": run.get("transcript"), "result": kept,
            "createdAt": run.get("createdAt"), "updatedAt": run.get("updatedAt"),
            "completedAt": run.get("completedAt")}


def _error_code(text: str) -> str:
    if INPUT_REJECTED.search(text):
        return "validation_error"
    lowered = text.lower()
    for code in KNOWN_CODES:
        if code in lowered:
            return code
    if "subscription" in lowered or "pro plan" in lowered or "upgrade" in lowered:
        return "subscription_required"
    return "tool_error"


def _failure_body(value: Any) -> dict[str, Any] | None:
    """{code, message, retryable} when `value` is a bare failure body rather than a run, else None."""
    if not (isinstance(value, dict) and isinstance(value.get("code"), str) and value["code"].strip()
            and "id" not in value and "status" not in value):
        return None
    message = value.get("message") if isinstance(value.get("message"), str) else ""
    code = value["code"].strip()
    return {"code": code if CODE.match(code) else _error_code(f"{code} {message}"),
            "message": message[:300] or "no message", "retryable": value.get("retryable") is True}


def _structured(value: dict[str, Any]) -> Any:
    """The run inside a saved result: its structuredContent, its one JSON text block, or the value itself."""
    if isinstance(value.get("structuredContent"), dict):
        return value["structuredContent"]
    if "content" in value and "id" not in value:
        blocks = value.get("content")
        if not (isinstance(blocks, list) and blocks and isinstance(blocks[0], dict)
                and isinstance(blocks[0].get("text"), str)):
            raise ValueError("the saved whole-video result carries no structured result")
        try:
            return json.loads(blocks[0]["text"])
        except ValueError:
            raise ValueError("the saved whole-video result carries no structured result") from None
    return value


# How an MCP server answers arguments its closed input schema does not accept: JSON-RPC InvalidParams, which the
# MCP server library turns into an error result whose text names it ("MCP error -32602: Input validation error:
# Invalid arguments for tool ...").
INVALID_PARAMS = -32602
INPUT_REJECTED = re.compile(r"-32602|input validation error|invalid arguments for tool", re.IGNORECASE)
# Some hosts show a failed call as plain text, not JSON ("MCP error -32602: Input validation error: ..."), and that
# text is what gets saved. It is read as the failure it states.
PLAIN_ERROR = re.compile(r"^\s*(?:MCP error\b|Error\b|Tool error\b|[a-z][a-z0-9_]{1,63}:\s)", re.IGNORECASE)


def plain_error(raw: bytes) -> str | None:
    """The text of a failure saved as plain text rather than JSON; None for anything else."""
    try:
        json.loads(raw)
        return None
    except ValueError:
        pass
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return text if text and PLAIN_ERROR.match(text) else None


def input_rejected(raw: bytes) -> bool:
    """Whether the saved result is the server refusing the call's arguments, before any analysis ran: an MCP error
    result, or a JSON-RPC error object a host saved instead."""
    text = plain_error(raw)
    if text is not None:
        return bool(INPUT_REJECTED.search(text))
    try:
        value = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(value, dict):
        return False
    error = value.get("error") if isinstance(value.get("error"), dict) else value
    if error.get("code") == INVALID_PARAMS:
        return True
    if isinstance(error.get("message"), str) and "id" not in error and "status" not in error \
            and INPUT_REJECTED.search(error["message"]):
        return True
    if value.get("isError") and not isinstance(value.get("structuredContent"), dict):
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        text = " ".join(block.get("text", "") for block in blocks
                        if isinstance(block, dict) and isinstance(block.get("text"), str))
        return bool(INPUT_REJECTED.search(text))
    return False


# How the service says it cannot read a source (a platform or file it does not take): a failure whose code names
# it, or an input refusal that names only `source_url`. Either ends the viewing as a gap, never the run.
UNSUPPORTED = re.compile(r"unsupported|not supported|does not support", re.IGNORECASE)


def source_refused(raw: bytes) -> bool:
    """Whether the saved result refuses the source itself: an input refusal about `source_url` and none of the
    newer inputs (an older server refusing `delivery` / `wait_s` is a different answer), or a failure saying the
    source is unsupported."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if input_rejected(raw):
        return "source_url" in text and not re.search(r"\bdelivery\b|\bwait_s\b", text)
    reading = read(raw)
    error = reading["error"] or {}
    return reading["run"] is None and bool(UNSUPPORTED.search(f"{error.get('code', '')} {error.get('message', '')}"))


def failure_unsupported(failure: Any) -> bool:
    """Whether a run's own failure says the source is not supported."""
    return isinstance(failure, dict) and bool(UNSUPPORTED.search(f"{failure.get('code', '')} "
                                                                  f"{failure.get('message', '')}"))


def download_offer(raw: bytes) -> dict[str, Any] | None:
    """{"download", "id", "status"} when the saved result carries a download in place of its result and transcript;
    None for every other save, which `read` handles."""
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(value, dict) or value.get("isError") or value.get("schema_version") == PERSISTED:
        return None
    try:
        run = _structured(value)
    except ValueError:
        return None
    # The server keeps `result` and `transcript` in the answer (both are required in its published schema) and
    # sets them to null when it hands the complete result over as a download; an inline answer has them filled.
    if not isinstance(run, dict) or "download" not in run:
        return None
    if run.get("result") is not None or run.get("transcript") is not None:
        return None
    return {"download": run["download"], "id": run.get("id"), "status": run.get("status")}


def run_of(raw: bytes) -> Any:
    """The run object inside complete result bytes (a downloaded body included)."""
    value = json.loads(raw)
    return _structured(value) if isinstance(value, dict) else value


def read(raw: bytes) -> dict[str, Any]:
    """{"run": redacted run | None, "error": {code, message, retryable} | None, "raw_sha256", "polls",
    "idempotency_key", "source_url"} from the saved bytes. Raises ValueError for an unusable save."""
    digest = hashlib.sha256(raw).hexdigest()
    base = {"raw_sha256": digest, "polls": 0, "idempotency_key": None, "source_url": None}
    text = plain_error(raw)
    if text is not None:
        return {**base, "run": None, "error": {"code": _error_code(text), "message": text[:300], "retryable": False}}
    try:
        value = json.loads(raw)
    except ValueError:
        raise ValueError("the saved whole-video result is not JSON; save the tool's result whole, as returned") from None
    if isinstance(value, dict) and value.get("schema_version") == PERSISTED:
        run = value.get("response")
        return {**base, "raw_sha256": value.get("raw_sha256") or digest, "polls": int(value.get("polls") or 0),
                "idempotency_key": value.get("idempotency_key"), "source_url": value.get("source_url"),
                "run": redact(check_run(run)) if run is not None else None, "error": value.get("error")}
    if not isinstance(value, dict):
        raise ValueError("the saved whole-video result is not an object")
    # A failed tool call, in either form a host saves it: the bare failure body, or the MCP error result (whose
    # text may itself be that body).
    failure = _failure_body(value)
    if failure is None and isinstance(value.get("error"), dict) and "id" not in value.get("error", {}):
        # A JSON-RPC error object a host saved in place of a tool result.
        rpc = value["error"]
        message = rpc.get("message") if isinstance(rpc.get("message"), str) else ""
        failure = {"code": "validation_error" if rpc.get("code") == INVALID_PARAMS else _error_code(message),
                   "message": message[:300] or "no message", "retryable": False}
    if failure is not None:
        return {**base, "run": None, "error": failure}
    if value.get("isError") and not isinstance(value.get("structuredContent"), dict):
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        text = " ".join(block.get("text", "") for block in blocks
                        if isinstance(block, dict) and isinstance(block.get("text"), str)).strip()
        try:
            failure = _failure_body(json.loads(text))
        except ValueError:
            failure = None
        return {**base, "run": None,
                "error": failure or {"code": _error_code(text), "message": text[:300] or "no message",
                                     "retryable": False}}
    return {**base, "run": redact(check_run(_structured(value))), "error": None}


def items(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Timestamped notes in time order, with stable ids V01, V02, ..."""
    if not isinstance(run, dict) or not isinstance(run.get("result"), dict):
        return []
    found = []
    for dimension in run["result"].get("dimensions") or []:
        for item in dimension.get("evidence") or []:
            found.append({"start_ms": item["startMs"], "end_ms": item["endMs"], "aspect": dimension["key"],
                          "note": item["note"]})
    found.sort(key=lambda item: (item["start_ms"], item["end_ms"]))
    width = max(2, len(str(len(found))))
    return [{"id": f"V{index:0{width}d}", **item} for index, item in enumerate(found, start=1)]


def observations(viewer: dict[str, Any] | None, *, closing: bool = True) -> dict[str, Any]:
    """The `viewer_observations` block of ContentEvidence."""
    block: dict[str, Any] = {"status": "not_attempted", "source": "whole_video", "analysis_id": None,
                             "failure": None, "items": [], "discarded_fields": list(DISCARDED_FIELDS)}
    if viewer is None:
        return block
    run, error = viewer.get("run"), viewer.get("error")
    if run is None:
        block.update(status="unavailable",
                     failure={"code": str((error or {}).get("code") or "tool_error"),
                              "retryable": bool((error or {}).get("retryable"))})
        return block
    block["analysis_id"] = run["id"]
    if run["status"] in PENDING:
        block["status"] = "pending"
        return block
    if run["status"] != "completed":
        failure = run.get("failure") or {}
        block.update(status="unavailable", failure={"code": str(failure.get("code") or run["status"]),
                                                    "retryable": bool(failure.get("retryable"))})
        return block
    found = items(run)
    block.update(status="available" if found else "unavailable", items=found)
    if not found:
        block["failure"] = {"code": "no_observations", "retryable": False}
    return block


def transcript_cues(viewer: dict[str, Any] | None) -> list[dict[str, Any]]:
    run = (viewer or {}).get("run")
    if not isinstance(run, dict) or run.get("status") != "completed":
        return []
    return [{"start_ms": cue["startMs"], "text": cue["text"]} for cue in run.get("transcript") or []]


def acquisition_status(viewer: dict[str, Any]) -> str:
    run = viewer.get("run")
    if run is None:
        return "failed"
    if run["status"] == "completed":
        return "completed"
    if run["status"] in PENDING:
        return "deferred_incomplete"
    return "failed"
