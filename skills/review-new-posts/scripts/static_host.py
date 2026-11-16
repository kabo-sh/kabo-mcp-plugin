#!/usr/bin/env python3
"""Explicit local evidence adapter for bundled Skills; no model loop.

The only network access is `fetch`: one GET per signed storage.googleapis.com link that a Kabo tool
result returned, checked against the declared bytes and sha256 before anything is written.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parent.parent
MAX_BYTES = 32 * 1024 * 1024
# Total-size cap for one artifact download: at most 120 refs per request; transcripts and extracted frames are far below it; beyond it, request in batches.
MAX_ARTIFACT_TOTAL = 4 * MAX_BYTES
PENDING = {"queued", "running", "pending", "in_progress", "accepted"}
# Download delivery: accept only the GCS signed link given in a Kabo tool result; GET only, never follow redirects.
# This is the only network access in a Skill script (Kabo Skills spec KS7.3).
DOWNLOAD_HOST = "storage.googleapis.com"
DOWNLOAD_PREFIX = "https://" + DOWNLOAD_HOST + "/"
DOWNLOAD_TIMEOUT = 60
# Cap on the number of frames in a frame-extraction request, added to the arguments by job-call; empty means nothing is added.
FRAME_CAPS = {}
# Closed set of types an artifact download may declare -> file extension to write. Text is written as .txt, the same as stage's inline text: .json would be read in by
# persist_envelope as an envelope candidate. Anything outside the set (including application/octet-stream) is not written.
ARTIFACT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
                  "text/vtt": ".txt", "application/json": ".txt"}
ARTIFACT_REF_META = "kabo.sh/object_ref"
# After the link of a synchronous data result expires, re-sign by evidence_ref: read back the stored envelope, without re-running and without using quota.
RESIGN_TOOL = "get_research_data_download"


# The data operations this Skill uses map one-to-one to /mcp-pub tool names; only results of these tools are accepted as evidence.
CONNECTOR_TOOLS = {
    "instagram-discovery/resolve_profile": "instagram_resolve_profile",
    "instagram-discovery/search_accounts": "instagram_search_accounts",
    "instagram-discovery/list_posts": "instagram_list_posts",
    "instagram-discovery/list_reels": "instagram_list_reels",
    "youtube-public/get_channel": "youtube_get_channel",
    "youtube-public/list_channel_uploads": "youtube_list_channel_uploads",
    "tiktok-public/list_account_posts": "tiktok_list_account_posts",
    "instagram-discovery/list_comments": "instagram_list_comments",
    "youtube-public/list_comments": "youtube_list_comments",
    "tiktok-discovery/list_comments": "tiktok_discovery_list_comments",
}
# Aggregate tools return results carrying schema_version directly, and the arguments are given directly in each tool's own input structure.
AGGREGATE_TOOLS = set()
# The schema_version of aggregate tool output (inline and the downloaded copy have the same shape); the shape is decided by it, not by connector_id.
AGGREGATE_SCHEMAS = {}
# The terminal state and product bytes of an async task are returned by this tool and can likewise be saved as evidence.
JOB_TOOLS = {"get_research_data_job"}
# Composite fetch tool handed to the model (KS9): the backend finishes the account home page and history paging in one go, with input kept as is at the top level.
# Each of its calls[] entries is validated and written to disk against the data tools declared in CONNECTOR_TOOLS above.
HANDED_COMPOSITES = {"collect_account_history"}
# This Skill uses no route aliases and has no business-level tool that returns a fixed projection.
ROUTE_ALIASES: dict[str, set[str]] = {}
PROJECTIONS: dict[str, str] = {}


def run_dir():
    raw = os.environ.get("KABO_STATIC_RUN_DIR")
    if raw:
        run = Path(raw).resolve(strict=True)
    else:
        # The host does not necessarily keep environment variables between commands; commands all run inside the run directory, so search upward from the current directory for this run's marker.
        here = Path.cwd().resolve()
        run = next((path for path in (here, *here.parents) if (path / ".static-run.json").is_file()), None)
        if run is None:
            raise ValueError("Set KABO_STATIC_RUN_DIR to this request's reserved directory, or run the command from inside it")
    if not (run / ".static-run.json").is_file():
        raise ValueError("Not a reserved static Skill run")
    # Some hosts keep only files between two executions and not empty directories (the Web Agent sandbox workspace): the empty subdirectories created by init
    # are gone by the next step. Complete them on every entry into the run directory; existing ones are left untouched.
    for name in ("snapshot", "snapshot/.host-evidence", "analysis", "report", "owner", "host-results"):
        (run / name).mkdir(mode=0o700, parents=True, exist_ok=True)
    return run


def require_target(target):
    run = run_dir()
    target = Path(target).resolve()
    if run not in target.parents:
        raise ValueError("Evidence destination must belong to the current run")
    return target


def public_calls(call):
    # The driver script still describes one fetch round internally as data_connector_run / batch_run; when handed to the model they are replaced one by one with named tools,
    # and batch requests are split into separate calls. Tools not declared by this Skill (including registry tools) are always rejected.
    tool, args = call["tool"], call["arguments"]
    if tool == "data_connector_batch_run":
        return [mapped for request in args["requests"] for mapped in public_calls(
            {"tool": "data_connector_run", "arguments": request})]
    if tool == "data_connector_run":
        key = args["connector_id"] + "/" + args["operation"]
        name = CONNECTOR_TOOLS.get(key)
        if name is None:
            raise ValueError("No reviewed public MCP tool for " + key)
        return [{"tool": name, "arguments": {"parameters": args["params"], "delivery": "download"}}]
    if tool in HANDED_COMPOSITES:
        # The whole composite result is delivered by download: after fetch downloads it, it is split item by item and written (split_composite).
        return [{"tool": tool, "arguments": {**args, "delivery": "download"}}]
    if tool not in AGGREGATE_TOOLS | JOB_TOOLS:
        raise ValueError("Unsupported public MCP operation: " + tool)
    if tool in JOB_TOOLS:
        # The task final-state envelope and artifacts (including frames) are all delivered by download: inline images cannot enter the exportable tool result on some hosts
        # (observed on Claude Code 2.1.308); frames are written by fetch and then opened with the host's own image-viewing tool. The readiness query has no such argument.
        return [{"tool": tool, "arguments": {**args, "delivery": "download"}}]
    if tool in AGGREGATE_SCHEMAS:
        # An aggregate tool's delivery only adds a full copy for the script to download, and items stay inline;
        # when the host truncates an inline result, the script gets the full data from this copy.
        return [{"tool": tool, "arguments": {**args, "delivery": "download"}}]
    return [call]


def init(workspace):
    base = Path(workspace).resolve(strict=True) / ".kabo-runs"
    if SKILL == base or SKILL in base.parents:
        raise ValueError("Runs must be outside the installed Skill")
    base.mkdir(mode=0o700, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(6)
    run = base / name
    run.mkdir(mode=0o700)
    # host-results/ holds the raw tool results exported by the host; they are the input to fetch / stage. It is kept separate from the envelopes written by placement,
    # and persist_envelope.py does not read it when counting what is already placed.
    for name in ("snapshot", "analysis", "report", "owner", "host-results"):
        (run / name).mkdir(mode=0o700)
    (run / "snapshot/.host-evidence").mkdir(mode=0o700)
    write_new(run / ".static-run.json", json.dumps({"format": "kabo.static-run.v1", "skill": SKILL.name}).encode())
    return run


def write_new(path, body):
    # Exclusive write: retries and concurrency must not overwrite existing evidence.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)


def complete_result(tool, raw, extra_blocks=False):
    # Shared full-result reading for stage and fetch: size, tool name, MCP wrapper, error results, and locating the evidence object.
    if len(raw) > MAX_BYTES:
        raise ValueError("Tool result exceeds the evidence limit")
    if tool not in {RESIGN_TOOL} | set(CONNECTOR_TOOLS.values()) | AGGREGATE_TOOLS | JOB_TOOLS:
        raise ValueError("Not a declared evidence tool")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Complete MCP result must be an object")
    if value.get("isError") and "structuredContent" not in value:
        # A plain-text error is not JSON; carry the tool's error through verbatim so the model can tell an input error from a transient failure.
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        text = " ".join(block["text"] for block in blocks
                        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)).strip()
        try:
            json.loads(text)
        except ValueError:
            raise ValueError("MCP error contains no terminal connector evidence: " + (text[:300] or "no message")) from None
    structured = value.get("structuredContent", value)
    if "content" in value and "structuredContent" not in value:
        blocks = value["content"]
        # In download mode an artifact result may be followed by fallback body blocks after the JSON text; only fetch recognises them.
        if (not isinstance(blocks, list) or not blocks or (len(blocks) != 1 and not extra_blocks) or
                not isinstance(blocks[0], dict) or blocks[0].get("type") != "text" or
                not isinstance(blocks[0].get("text"), str)):
            raise ValueError("Complete structured result is required")
        structured = json.loads(blocks[0]["text"])
    if not isinstance(structured, dict):
        raise ValueError("Complete structured result is required")
    # While a task has not reached a final state the envelope is null; give the poll hint first rather than reporting "evidence object incomplete".
    if structured.get("envelope", {}) is None and structured.get("status") in PENDING:
        raise ValueError("Poll the data job before staging terminal evidence")
    envelope = structured["envelope"] if "envelope" in structured else structured.get("result", structured)
    if not isinstance(envelope, dict):
        raise ValueError("Complete evidence object is required")
    if value.get("isError") and not (envelope.get("status") == "failed" and
                                    isinstance(envelope.get("connector_id"), str) and
                                    isinstance(envelope.get("operation"), str) and
                                    isinstance(envelope.get("limitations"), list)):
        raise ValueError("MCP error contains no terminal connector evidence")
    return value, structured, envelope


def check_envelope(tool, envelope):
    # For a task still queued or running, give the correct hint first; do not let the operation-name or field checks below block it first.
    if envelope.get("status") in PENDING:
        raise ValueError("Poll the data job before staging terminal evidence")
    operation = next((key for key, name in CONNECTOR_TOOLS.items() if name == tool), None)
    if operation:
        connector, expected = operation.split("/")
        actual = envelope.get("connector_id", "") + "/" + envelope.get("operation", "")
        if actual != operation and actual not in ROUTE_ALIASES.get(operation, ()):
            raise ValueError("Tool result does not match its declared operation")
        # A failure envelope or a download-ready result carries no data; if it does, it must be the projection declared by this tool.
        projected = envelope.get("data")
        if tool in PROJECTIONS and "data" in envelope and not (
                isinstance(projected, dict) and projected.get("projection") == PROJECTIONS[tool]):
            raise ValueError("Tool result does not carry its declared projection")
        if not isinstance(envelope.get("limitations"), list) or not isinstance(envelope.get("status"), str):
            raise ValueError("Incomplete connector envelope")
    if tool == RESIGN_TOOL:
        # The re-sign reads back the envelope recorded by that call itself, and the envelope records the route that actually answered; only data operations declared by this Skill are accepted.
        actual = envelope.get("connector_id", "") + "/" + envelope.get("operation", "")
        declared = next((key for key in CONNECTOR_TOOLS if actual == key or actual in ROUTE_ALIASES.get(key, ())), None)
        if declared is None:
            raise ValueError("Re-signed result is not from one of this Skill's data tools")
        if CONNECTOR_TOOLS[declared] in PROJECTIONS:
            # Projection happens after storage: what re-signing returns is the raw envelope of the answering route, not the projection.
            name = CONNECTOR_TOOLS[declared]
            raise ValueError(f"A re-signed {name} result is its route's raw envelope, not the projection; "
                             f"call {name} again with delivery \"download\" and fetch that result")
        if not isinstance(envelope.get("limitations"), list) or not isinstance(envelope.get("status"), str):
            raise ValueError("Incomplete connector envelope")
    if tool == "get_research_data_job":
        actual = envelope.get("connector_id", "") + "/" + envelope.get("operation", "")
        if actual not in CONNECTOR_TOOLS:
            raise ValueError("Job returned an undeclared data operation")
    if tool in AGGREGATE_SCHEMAS and envelope.get("schema_version") != AGGREGATE_SCHEMAS[tool]:
        raise ValueError("Tool result does not carry its declared schema")
    if not operation and tool not in ("get_research_data_job", RESIGN_TOOL) and not envelope.get("schema_version") and tool != "read_research_data_artifacts":
        raise ValueError("Tool result has no supported evidence schema")
    data = envelope.get("data")
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        import re
        claimed = re.search(r"\bFound\s+(\d+)\b", str(envelope.get("summary", "")), re.I)
        if claimed and int(claimed[1]) > 0 and not data["rows"]:
            raise ValueError("Truncated evidence has no claimed rows")


def evidence_id():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + secrets.token_hex(6)


def block_body(artifact, block):
    # Decode the inline artifact body (the whole stage result, or a fallback block marked with object_ref in download mode) and determine the extension.
    body_key = "text" if block["type"] == "text" else "data"
    if not isinstance(block.get(body_key), str):
        raise ValueError("Artifact body must be a string")
    body = (block["text"].encode() if block["type"] == "text"
            else base64.b64decode(block["data"], validate=True))
    check_artifact(artifact, body)
    extension = ".txt"
    if block["type"] == "image":
        mime = artifact.get("content_type")
        extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime)
        if extension is None or block.get("mimeType") != mime:
            raise ValueError("Unsupported or mismatched image content type")
    return body, extension


def check_artifact(artifact, body):
    if hashlib.sha256(body).hexdigest() != artifact.get("sha256") or artifact.get("bytes", len(body)) != len(body):
        raise ValueError("Artifact checksum mismatch")


def artifact_meta(artifact, job_id, **extra):
    # The download descriptor contains a signed link and does not go into the sidecar file; the other registered fields (object_ref, sha256, bytes...) are kept as before.
    return {**{key: item for key, item in artifact.items() if key != "download"}, "job_id": job_id, **extra}


def store(tool, envelope, payloads):
    destination = run_dir() / "snapshot/.host-evidence"
    require_target(destination / "pending.json")
    if len(payloads) == 1 and payloads[0][0].endswith(".json"):
        fingerprint = hashlib.sha256(payloads[0][1]).hexdigest()
        for previous in destination.glob("*.meta"):
            metadata = json.loads(previous.read_text())
            if metadata.get("tool") == tool and metadata.get("sha256") == fingerprint:
                if hashlib.sha256(previous.with_suffix(".json").read_bytes()).hexdigest() != fingerprint:
                    raise ValueError("Previously staged evidence was altered")
                return {"staged": 0, "duplicate": True, "directory": str(destination)}
    for name, body, extra in payloads:
        target = destination / name
        meta = {**extra, "sha256": hashlib.sha256(body).hexdigest(), "tool": tool,
                "staged_at": datetime.now(timezone.utc).isoformat()}
        if "connector_id" in envelope:
            meta.update(connector_id=envelope["connector_id"], operation=envelope["operation"])
        elif "schema_version" in envelope:
            meta["schema_version"] = envelope["schema_version"]
        write_new(target, body)
        write_new(target.with_suffix(".meta"), json.dumps(meta).encode())
    return {"staged": len(payloads), "directory": str(destination)}


# The only way out when an artifact in download mode has no usable file: fetch and stage say the same sentence and do not point back to each other.
# The host saves inline images into its own session directory (observed on Claude Code 2.1.308); that is not a dependable interface, so explicitly say not to assemble paths from it.
REREAD_INLINE = ("call read_research_data_artifacts again for those object_refs without delivery, export the complete "
                 "result through the host and run static_host.py stage on it; never rebuild it from the host's own "
                 "session or tool-result folders")
REREAD = ("Items marked not_found are missing evidence: record them as gaps. For the other unavailable items, "
          + REREAD_INLINE)


def artifact_downloads(structured):
    artifacts = structured.get("artifacts")
    return [item["download"] for item in artifacts if isinstance(item, dict) and "download" in item] if isinstance(artifacts, list) else []


def typed_result(envelope):
    # Typed output of aggregate tools (collect_*, enrich_*): carries schema_version and no connector_id. Its download is only a full copy for the script;
    # items stay fully inline, so the inline copy can be staged as well.
    return "connector_id" not in envelope and isinstance(envelope.get("schema_version"), str)


def download_mode(structured):
    # Require fetch only when a ready link actually exists; when all are unavailable fetch cannot get a file either, and requiring it would make the two commands point back at each other.
    return any(isinstance(item, dict) and item.get("status") == "ready"
               for item in [structured.get("download"), *artifact_downloads(structured)])


def stage(tool, raw):
    if tool in COMPOSITE_TOOLS:
        return stage_composite(tool, raw)
    return store(*staged(tool, raw))


def staged(tool, raw):
    # Validation and shaping for stage, without writing to disk: when a composite result is split into items, validate all of them first, then write together.
    value, structured, envelope = complete_result(tool, raw)
    if envelope.get("schema_version") == COMPOSITE_SCHEMA:
        raise ValueError("A composite result must be staged with its composite tool name")
    # A download-ready result omits data; saving it as inline evidence would produce an envelope with no data. Aggregate tools are the exception: inline stays complete as before.
    if download_mode(structured) and not typed_result(envelope):
        raise ValueError("This result carries a download instead of inline data; run static_host.py fetch on it")
    # The host dropped download when saving and kept only the summary (status completed but no data): it would only fail in a later script after ingestion, and this round already counts as placed,
    # so the full result with the download added later would never be read (plugin run, TikTok chart). Reject here and point back to the full result.
    if (envelope.get("status") in ("completed", "completed_partial") and "data" not in envelope
            and not typed_result(envelope) and tool != "read_research_data_artifacts"):
        raise ValueError("This result has a completed status but no data: it is a summary of a download, not the "
                         "evidence. Save the tool's complete result, including its download, and run "
                         "static_host.py fetch on it")
    if typed_result(envelope):
        # The download descriptor contains a signed link and is not written to disk; with it removed, the object is the same as the downloaded one.
        envelope = {key: item for key, item in envelope.items() if key != "download"}
    # An artifact result in download mode carries no inline body (fallback blocks are recognised only by fetch); with no ready link, point to an inline re-read.
    if artifact_downloads(structured):
        raise ValueError("This artifact result has no ready download and no inline bodies to stage. " + REREAD)
    check_envelope(tool, envelope)
    identifier = evidence_id()
    payloads = []
    if tool == "read_research_data_artifacts":
        artifacts = structured.get("artifacts", [])
        raw_blocks = value.get("content", [])
        if (not isinstance(artifacts, list) or not isinstance(raw_blocks, list) or
                not all(isinstance(item, dict) for item in artifacts) or
                not all(isinstance(item, dict) for item in raw_blocks)):
            raise ValueError("Artifact bodies and metadata must be complete and paired")
        blocks = [item for item in raw_blocks if item.get("type") in {"text", "image"}]
        if not artifacts or len(artifacts) != len(blocks) or not structured.get("job_id"):
            raise ValueError("Artifact bodies and metadata must be complete and paired")
        for index, (artifact, block) in enumerate(zip(artifacts, blocks)):
            body, extension = block_body(artifact, block)
            payloads.append((f"{identifier}-{index}{extension}", body, artifact_meta(artifact, structured["job_id"])))
    else:
        payloads.append((identifier + ".json", json.dumps(envelope, ensure_ascii=False).encode(), {}))
    return tool, envelope, payloads


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # A signed link points to exactly one object; any 3xx is treated as a failure, so a link can never lead the script to another host.
    def redirect_request(self, *args, **kwargs):
        return None


def hashed_capath(path):
    # OpenSSL reads certificate links from a directory only in the form <8 hex digits>.<number>; a non-empty directory without such files is equivalent to having no trust store.
    try:
        with os.scandir(path) as entries:
            return any(re.fullmatch(r"[0-9a-f]{8}\.\d+", entry.name) for entry in entries)
    except (OSError, TypeError):
        return False


def tls_context():
    # On macOS, when Python installed from python.org has not run Install Certificates, the default trust store is empty and every HTTPS download fails with a certificate error
    # (plugin run T-20261028-04). Switch to certifi or the system CA bundle only when the default trust store truly does not exist; certificates are still validated as usual;
    # if a candidate cannot be read or has the wrong format, try the next one.
    # On Windows the default context reads the system certificate store, so an empty file path does not mean there is no trust store; keep the default.
    if sys.platform == "win32":
        return None
    paths = ssl.get_default_verify_paths()
    if (paths.cafile and os.path.isfile(paths.cafile)) or hashed_capath(paths.capath):
        return None
    candidates = []
    try:
        import certifi
        candidates.append(certifi.where())
    except Exception:
        pass
    candidates += ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            return ssl.create_default_context(cafile=path)
        except (OSError, ssl.SSLError):
            continue
    return None


def build_opener():
    # Tests replace this function in-process to inject a fake HTTPS handler; no command-line entry point can change it.
    context = tls_context()
    handlers = [NoRedirect()] + ([urllib.request.HTTPSHandler(context=context)] if context else [])
    return urllib.request.build_opener(*handlers)


def renew_hint(tool, envelope):
    # Three paths after a link expires: for tasks and artifacts, simply read again; for synchronous data results, re-sign by evidence_ref,
    # without re-running or using quota, and the new link's sha256 and bytes may differ from the old ones, so validate only against the newly returned values; an aggregate tool's inline result is already complete.
    if tool in JOB_TOOLS:
        return f"Call {tool} again with delivery \"download\" (it only reads; nothing is re-run), then run fetch right away"
    if typed_result(envelope):
        return ("This tool's inline result is complete: export it through the host and run static_host.py stage "
                f"--tool {tool} on it (calling the tool again would re-run it)")
    original = tool
    if tool == RESIGN_TOOL:
        # The re-sign tool takes only evidence_ref (additionalProperties: false); calling it again with delivery is rejected and re-runs nothing;
        # the last fallback is the original data tool of the route that actually answered in the envelope. ROUTE_ALIASES exists only in some copies, so the shared section cannot reference it directly.
        actual = f"{envelope.get('connector_id', '')}/{envelope.get('operation', '')}"
        aliases = globals().get("ROUTE_ALIASES", {})
        original = next((name for key, name in CONNECTOR_TOOLS.items()
                         if actual == key or actual in aliases.get(key, ())), "the original data tool")
    ref = envelope.get("evidence_ref")
    # What re-signing a projection tool returns is the raw envelope of the answering route, not the projection; the only option is to call the original tool once more.
    if isinstance(ref, str) and ref and original not in PROJECTIONS:
        return ("Call get_research_data_download with {\"evidence_ref\": " + json.dumps(ref) + "} (no allowance cost; "
                "nothing is re-run), then run fetch --tool get_research_data_download on its complete result right "
                "away; it checks the new sha256 and bytes, which can differ from this link's. If get_research_data_download "
                f"itself fails, call {original} again with the same parameters and delivery \"download\" (this re-runs it), "
                "then run fetch right away")
    return (f"Call {original} again with the same parameters and delivery \"download\" (for a data tool this re-runs "
            "it, the only way to get a new link), then run fetch right away")


def expired(descriptor):
    # If expires_at has passed there is no need to send the request: the conclusion is the same as GCS returning 400/403. If the time format is wrong, leave it to the download itself to decide.
    try:
        stamp = datetime.fromisoformat(str(descriptor.get("expires_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return stamp.tzinfo is not None and stamp <= datetime.now(timezone.utc)


def download(tool, descriptor, kind, hint):
    """GET one Kabo-issued signed link; return its bytes only if size, sha256 and content type all match."""
    url, digest, size = descriptor.get("url"), descriptor.get("sha256"), descriptor.get("bytes")
    if (descriptor.get("kind") != kind or not isinstance(url, str) or not isinstance(digest, str) or
            len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) or
            isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_BYTES):
        raise ValueError("Download descriptor is incomplete or over the evidence limit")
    if expired(descriptor):
        raise ValueError("Download link expired (expires_at has passed). " + hint)
    # Accept only the GCS signed link given in a Kabo tool result: protocol and host must match verbatim (no port, no username) and contain no whitespace or control characters.
    if (not url.startswith(DOWNLOAD_PREFIX) or urlsplit(url).netloc != DOWNLOAD_HOST or
            any(ord(char) <= 32 or ord(char) == 127 for char in url)):
        raise ValueError("Download link is not a Kabo signed storage link; refusing to fetch it")
    request = urllib.request.Request(url, method="GET", headers={"Accept-Encoding": "identity"})
    # Errors state only the category and status code: exception text may carry the link, signature or object name, so it is never relayed.
    hasher, chunks, total = hashlib.sha256(), [], 0
    try:
        with build_opener().open(request, timeout=DOWNLOAD_TIMEOUT) as response:
            status = response.status
            # The signed link is issued for the declared type (response-content-type) and GCS returns this header as is; a mismatch means the thing fetched is not that artifact.
            # When the header is absent, do not block: the size and sha256 already pin the bytes.
            served = response.headers.get("Content-Type") if status == 200 else None
            if served and served.split(";")[0].strip().lower() != str(descriptor.get("content_type")).lower():
                status = "type"
            while status == 200 and total <= size:
                chunk = response.read(min(1024 * 1024, size + 1 - total))
                if not chunk:
                    break
                hasher.update(chunk)
                chunks.append(chunk)
                total += len(chunk)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except Exception as error:
        # stage does not accept artifact results in download mode (it would point back to fetch); when the script cannot reach the network the artifact can only be re-read inline, otherwise the two commands point back at each other.
        fallback = (REREAD_INLINE if kind == "artifact" else
                    "export the complete tool result through the host and run static_host.py stage instead")
        # Stating only the exception type cannot distinguish a sandbox with no network, a proxy, or a certificate problem (T-20261029-12 R2 saw only URLError), so include reason; it contains no signed link.
        reason = str(error.reason)[:160] if isinstance(error, urllib.error.URLError) else ""
        reason = "" if "http" in reason.lower() else reason  # keep the signed link out of the output
        label = f"{type(error).__name__}: {reason}" if reason else type(error).__name__
        raise ValueError(f"Download failed ({label}); if this host blocks network access for scripts, "
                         + fallback) from None
    if status == "type":
        raise ValueError("Download content type does not match the declared content_type; nothing was written")
    if 300 <= status < 400:
        raise ValueError(f"Download was redirected (HTTP {status}); redirects are not followed")
    if status in (400, 401, 403):
        raise ValueError(f"Download link expired or was refused (HTTP {status}). " + hint)
    if status != 200:
        raise ValueError(f"Download failed (HTTP {status}). " + hint)
    if total != size:
        raise ValueError("Download size does not match the declared bytes; nothing was written")
    if hasher.hexdigest() != digest:
        raise ValueError("Download sha256 does not match the declared value; nothing was written")
    return b"".join(chunks)


def summary(descriptor, status="fetched"):
    return {"kind": descriptor.get("kind"), "sha256": descriptor.get("sha256"), "bytes": descriptor.get("bytes"),
            "status": status}


def no_download(tool, descriptors):
    reasons = sorted({str(item.get("reason")) for item in descriptors if isinstance(item, dict) and item.get("reason")})
    return {"fetched": 0, "download": reasons or "absent",
            "next": ("No ready download in this result. Fall back: export the complete tool result through the host "
                     f"and run static_host.py stage --tool {tool} --input <file>")}


def fetch(tool, raw):
    """Download the complete evidence a Kabo tool result links to, then store it the way stage does."""
    if tool in COMPOSITE_TOOLS:
        return fetch_composite(tool, raw)
    value, structured, envelope = complete_result(tool, raw, extra_blocks=True)
    if tool == "read_research_data_artifacts":
        return fetch_artifacts(tool, value, structured)
    descriptor = structured.get("download")
    if not (isinstance(descriptor, dict) and descriptor.get("status") == "ready"):
        if envelope.get("status") in PENDING:
            raise ValueError("Poll the data job before staging terminal evidence")
        return no_download(tool, [descriptor])
    if descriptor.get("content_type") != "application/json":
        raise ValueError("Envelope download must be JSON")
    full = json.loads(download(tool, descriptor, "envelope", renew_hint(tool, envelope)).decode("utf-8"))
    if not isinstance(full, dict):
        raise ValueError("Downloaded evidence must be an object")
    # What is downloaded is this call's own envelope (with only data added); for aggregate tools it is the whole output with download removed;
    # if the identity fields do not match, the wrong file was fetched.
    for key in ("connector_id", "operation", "status", "evidence_ref", "raw_sha256", "schema_version"):
        if key in envelope and full.get(key) != envelope[key]:
            raise ValueError("Downloaded evidence does not match this tool result")
    check_envelope(tool, full)
    body = json.dumps(full, ensure_ascii=False).encode()
    result = store(tool, full, [(evidence_id() + ".json", body, {"delivery": "download"})])
    return {**result, "fetched": [summary(descriptor)]}


def fetch_artifacts(tool, value, structured):
    artifacts, job_id = structured.get("artifacts"), structured.get("job_id")
    if (not isinstance(artifacts, list) or not artifacts or not isinstance(job_id, str) or not job_id or
            not all(isinstance(item, dict) for item in artifacts)):
        raise ValueError("Artifact metadata must be complete")
    # Items whose signing failed fall back to the inline body, paired by the object_ref in _meta rather than by position (fallback reads may fail item by item).
    fallback = {}
    for block in value.get("content") if isinstance(value.get("content"), list) else []:
        meta = block.get("_meta") if isinstance(block, dict) else None
        ref = meta.get(ARTIFACT_REF_META) if isinstance(meta, dict) else None
        if isinstance(ref, str) and block.get("type") in {"text", "image"}:
            if ref in fallback:
                raise ValueError("Artifact bodies and metadata must be complete and paired")
            fallback[ref] = block
    identifier, payloads, fetched, missing, images, total = evidence_id(), [], [], [], [], 0
    # Download and validate everything first, write once at the end: if any item fails to match, no partial evidence is left behind.
    for index, artifact in enumerate(artifacts):
        descriptor = artifact.get("download")
        if isinstance(descriptor, dict) and descriptor.get("status") == "ready":
            extension = ARTIFACT_TYPES.get(descriptor.get("content_type"))
            if extension is None:
                raise ValueError("Unsupported artifact content type")
            if (descriptor.get("sha256") != artifact.get("sha256") or descriptor.get("bytes") != artifact.get("bytes") or
                    descriptor.get("content_type") != artifact.get("content_type")):
                raise ValueError("Download does not match its artifact record")
            total += descriptor["bytes"] if isinstance(descriptor.get("bytes"), int) else 0
            if total > MAX_ARTIFACT_TOTAL:
                raise ValueError("Artifact downloads exceed the evidence limit; request fewer object_refs per call")
            body = download(tool, descriptor, "artifact", renew_hint(tool, structured))
            check_artifact(artifact, body)
            payloads.append((f"{identifier}-{index}{extension}", body, artifact_meta(artifact, job_id, delivery="download")))
            fetched.append({"index": index, "file": f"{identifier}-{index}{extension}", **summary(descriptor)})
            if extension != ".txt":
                images.append(index)
        elif artifact.get("object_ref") in fallback:
            body, extension = block_body(artifact, fallback[artifact["object_ref"]])
            payloads.append((f"{identifier}-{index}{extension}", body, artifact_meta(artifact, job_id)))
            fetched.append({"index": index, "file": f"{identifier}-{index}{extension}", "kind": "artifact",
                            "sha256": artifact.get("sha256"),
                            "bytes": artifact.get("bytes"), "status": "inline"})
            if extension != ".txt":
                images.append(index)
        else:
            reason = descriptor.get("reason") if isinstance(descriptor, dict) else None
            missing.append({"index": index, "status": "unavailable", "reason": reason or "absent"})
    if not payloads:
        if artifact_downloads(structured):
            return {"fetched": 0, "missing": missing, "next": "Nothing could be fetched. " + REREAD}
        return no_download(tool, [item.get("download") for item in artifacts])
    result = {**store(tool, structured, payloads), "fetched": fetched}
    # Downloaded frames exist only on disk and the model cannot see the pixels; give absolute paths so the model opens them with the host's own image-viewing or file-reading tool.
    for item in fetched:
        item["path"] = str(Path(result["directory"]) / item["file"])
    if images:
        result["view"] = ("Downloaded images are files, not yet seen: open each image's path with the host's own "
                          "file or image viewer before describing it")
    if missing:
        result["missing"] = missing
        result["next"] = "Items in missing have no file. " + REREAD
    return result


# Composite fetch tool (kabo-composite-fetch.v1, docs/skills-spec.md KS8): the backend finishes a multi-round fetch in one call,
# calls[] is every single-tool call the backend actually issued, and calls[i].result is exactly the same as the result envelope of a single /mcp-pub data tool.
# On write, items are split apart: each item goes through the same validation and naming as stage according to calls[i].tool (<id>.json + <id>.meta, bodies byte-identical),
# the sidecar additionally records composite_tool / composite_id / composite_index / composite_group / composite_parameters;
# finally a whole-run record <composite_id>.json + .meta is written (sidecar tool is the composite tool, schema_version is COMPOSITE_RECORD),
# and the driver reads its summary / coverage / limitations and the per-item evidence ids with composite_records().
# If any item fails validation, nothing is written for the whole run. This section is identical in every Skill's copy (scripts/shared-copies.test.mjs).
COMPOSITE_SCHEMA = "kabo-composite-fetch.v1"
COMPOSITE_RECORD = "kabo-composite-fetch.record.v1"
COMPOSITE_TOOLS = {"collect_account_history", "collect_tiktok_video_candidates", "collect_youtube_recent_videos",
                   "render_official_pages", "collect_video_media"}


def failed_composite(value):
    # When every item fails, the composite result as a whole is status: failed, and /mcp-pub also sets isError, following the research-chain basis, but still carries the full composite result:
    # an item-level failure is the final state of the fetched object (e.g. upstream refuses the download), is written to disk as usual, and is left to the driver to degrade by gap; only an error without a composite result is reported verbatim.
    structured = value.get("structuredContent")
    if structured is None:
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        try:
            structured = json.loads(blocks[0]["text"]) if blocks and isinstance(blocks[0], dict) else None
        except (KeyError, TypeError, ValueError):
            return False
    return (isinstance(structured, dict) and structured.get("schema_version") == COMPOSITE_SCHEMA and
            structured.get("status") == "failed" and isinstance(structured.get("calls"), list))


def composite_result(tool, raw):
    # Reading the whole composite result follows the same rules as complete_result: size, tool name, MCP wrapper; a composite tool is an error result only when a domain function raises,
    # while failures and gaps are collected in status / limitations, so an error result always has its error carried through verbatim and nothing is written to disk.
    if len(raw) > MAX_BYTES:
        raise ValueError("Tool result exceeds the evidence limit")
    if tool not in COMPOSITE_TOOLS:
        raise ValueError("Not a declared evidence tool")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Complete MCP result must be an object")
    if value.get("isError") and not failed_composite(value):
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        text = " ".join(block["text"] for block in blocks
                        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)).strip()
        raise ValueError(f"{tool} failed and returned no composite result: " + (text[:300] or "no message"))
    structured = value.get("structuredContent", value)
    if "content" in value and "structuredContent" not in value:
        blocks = value["content"]
        if (not isinstance(blocks, list) or not blocks or not isinstance(blocks[0], dict) or
                blocks[0].get("type") != "text" or not isinstance(blocks[0].get("text"), str)):
            raise ValueError("Complete structured result is required")
        structured = json.loads(blocks[0]["text"])
    if isinstance(structured, dict) and "schema_version" not in structured and isinstance(structured.get("result"), dict):
        structured = structured["result"]
    if not isinstance(structured, dict) or structured.get("schema_version") != COMPOSITE_SCHEMA:
        raise ValueError("Tool result has no supported evidence schema")
    if structured.get("tool") != tool:
        raise ValueError("Tool result does not match its declared operation")
    return structured


def previous_evidence(tool, body):
    # The same criterion as store's deduplication (same tool, same sha256): the evidence id of the copy already written; if it was modified, reject.
    destination = run_dir() / "snapshot/.host-evidence"
    fingerprint = hashlib.sha256(body).hexdigest()
    for previous in sorted(destination.glob("*.meta")):
        metadata = json.loads(previous.read_text())
        if metadata.get("tool") == tool and metadata.get("sha256") == fingerprint:
            if hashlib.sha256(previous.with_suffix(".json").read_bytes()).hexdigest() != fingerprint:
                raise ValueError("Previously staged evidence was altered")
            return previous.stem
    return None


def split_composite(tool, composite, extra, refetch=""):
    calls = composite.get("calls")
    if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls):
        raise ValueError("Composite result must carry its calls" + refetch)
    # Validate and shape every item as a single-tool stage first, and write only after all pass: no partial evidence is left behind.
    prepared = []
    for index, call in enumerate(calls):
        name, result = call.get("tool"), call.get("result")
        label = name if isinstance(name, str) else "?"
        try:
            if not isinstance(name, str) or name in COMPOSITE_TOOLS or not isinstance(result, dict):
                raise ValueError("each call needs a single data tool name and its result envelope")
            name, envelope, payloads = staged(name, json.dumps(result, ensure_ascii=False).encode())
            if len(payloads) != 1 or not payloads[0][0].endswith(".json"):
                raise ValueError("a composite call must be one data envelope")
            previous_evidence(name, payloads[0][1])
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"calls[{index}] ({label}): {error}; nothing was written" + refetch) from None
        prepared.append((name, envelope, payloads))
    record_id, entries, written, duplicates = evidence_id(), [], 0, 0
    for index, (call, (name, envelope, payloads)) in enumerate(zip(calls, prepared)):
        marks = {**extra, "composite_tool": tool, "composite_id": record_id, "composite_index": index,
                 "composite_group": call.get("group"), "composite_parameters": call.get("parameters")}
        file, body, meta = payloads[0]
        result = store(name, envelope, [(file, body, {**meta, **marks})])
        stored = previous_evidence(name, body) if result.get("duplicate") else Path(file).stem
        written += result["staged"]
        entries.append({"index": index, "tool": name, "group": call.get("group"), "status": envelope.get("status"),
                        "evidence_id": stored})
        duplicates += 1 if result.get("duplicate") else 0
    # The record contains only deterministic content: writing the same composite again is byte-identical to last time, and store's deduplication points back to the earlier copy.
    record = {"schema_version": COMPOSITE_RECORD, "tool": tool, "status": composite.get("status"),
              "summary": composite.get("summary"), "coverage": composite.get("coverage"),
              "limitations": composite.get("limitations"), "calls": entries}
    body = json.dumps(record, ensure_ascii=False).encode()
    result = store(tool, record, [(record_id + ".json", body, {**extra, "composite_calls": len(entries)})])
    if result.get("duplicate"):
        record_id = previous_evidence(tool, body)
    directory = run_dir() / "snapshot/.host-evidence"
    return {"composite": tool, "status": composite.get("status"), "record": str(directory / (record_id + ".json")),
            "staged": written, "duplicate": duplicates,
            "directory": str(directory), "calls": entries}


def stage_composite(tool, raw):
    composite = composite_result(tool, raw)
    ready = download_mode(composite)
    refetch = f"; run static_host.py fetch --tool {tool} on the complete result instead" if ready else ""
    # The download descriptor contains a signed link and is not written to disk; with it removed, the object is the same as the downloaded one.
    composite = {key: item for key, item in composite.items() if key != "download"}
    return split_composite(tool, composite, {}, refetch)


def fetch_composite(tool, raw):
    composite = composite_result(tool, raw)
    descriptor = composite.get("download")
    if not (isinstance(descriptor, dict) and descriptor.get("status") == "ready"):
        return no_download(tool, [descriptor])
    if descriptor.get("content_type") != "application/json":
        raise ValueError("Envelope download must be JSON")
    hint = (f"If this result still carries complete calls, export it through the host and run static_host.py stage "
            f"--tool {tool} on it; otherwise call {tool} again with the same parameters and delivery \"download\" "
            "(this re-runs it), then run fetch right away")
    full = json.loads(download(tool, descriptor, "envelope", hint).decode("utf-8"))
    # The downloaded bytes are the whole output with download removed; if the identity fields do not match, the wrong file was fetched.
    if (not isinstance(full, dict) or full.get("schema_version") != COMPOSITE_SCHEMA or full.get("tool") != tool or
            ("status" in composite and full.get("status") != composite["status"])):
        raise ValueError("Downloaded evidence does not match this tool result")
    full = {key: item for key, item in full.items() if key != "download"}
    return {**split_composite(tool, full, {"delivery": "download"}), "fetched": [summary(descriptor)]}


# Fetch a download by result ID (kabo ADR-0084 "2026-11-04"): in a download-ready result, the signed-link path contains a 22-character result ID
# (`research-export/v1/<result_id>.json`). The model passes only the ID and no longer copies the whole result; the script fetches the same bytes from Kabo by ID,
# validates them against the sha256 and length in the response headers, and writes them to disk like fetch. The ID and the signed link are the same bearer ticket with the same expiry time (10 minutes).
# This section is identical in every Skill's copy (scripts/shared-copies.test.mjs).
RESULT_URL = "https://kabo.sh/v1/research-downloads/"
RESULT_ID = re.compile(r"[A-Za-z0-9_-]{22}")
RESULT_ID_IN_URL = re.compile(r"/research-export/v1/([A-Za-z0-9_-]{22})\.json(?:\?|$)")


def result_id_of(text):
    """The result id the model gave: the id itself (a trailing `.json` too), or a download url that contains one."""
    text = str(text).strip().strip("'\"")
    bare = text[:-len(".json")] if text.endswith(".json") else text
    if RESULT_ID.fullmatch(bare.rsplit("/", 1)[-1]):
        return bare.rsplit("/", 1)[-1]
    found = RESULT_ID_IN_URL.search(text)
    if found:
        return found.group(1)
    raise ValueError("A result id is the 22 letters, digits, - or _ between research-export/v1/ and .json in the "
                     "result's download url")


def download_result(result_id):
    """GET the bytes Kabo holds under one result id, with their sha256, only if both match its headers."""
    request = urllib.request.Request(RESULT_URL + result_id, method="GET", headers={"Accept-Encoding": "identity"})
    hasher, chunks, total = hashlib.sha256(), [], 0
    try:
        with build_opener().open(request, timeout=DOWNLOAD_TIMEOUT) as response:
            status = response.status
            size = response.headers.get("Content-Length")
            digest = str(response.headers.get("X-Content-SHA256") or "")
            if status == 200 and (not str(size or "").isdigit() or int(size) > MAX_BYTES or
                                  not re.fullmatch(r"[0-9a-f]{64}", digest)):
                status = "headers"
            while status == 200 and total <= int(size):
                chunk = response.read(min(1024 * 1024, int(size) + 1 - total))
                if not chunk:
                    break
                hasher.update(chunk)
                chunks.append(chunk)
                total += len(chunk)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except Exception as error:
        reason = str(error.reason)[:160] if isinstance(error, urllib.error.URLError) else ""
        reason = "" if "http" in reason.lower() else reason
        label = f"{type(error).__name__}: {reason}" if reason else type(error).__name__
        raise ValueError(f"Download failed ({label}); if this host blocks network access for scripts, save the "
                         "complete tool result to a file and run static_host.py fetch --input <file> on it") from None
    if status == 404:
        raise ValueError("no result under this id: it expired (ids last 10 minutes) or was mistyped. If that call was "
                         "a data tool (not a lookup_* tool) and its result has an evidence_ref, call "
                         "get_research_data_download with it (no new fetch, no allowance) and use the id in its new "
                         "download url; otherwise make the same call again and use the id from its new result")
    if status == "headers":
        raise ValueError("Kabo did not return the size and sha256 for this id; nothing was written")
    if status != 200:
        raise ValueError(f"Download failed (HTTP {status}); try again, or make the same call again for a new id")
    if total != int(size) or hasher.hexdigest() != digest:
        raise ValueError("Download does not match its declared size and sha256; nothing was written")
    return b"".join(chunks), digest


def fetch_id(tool, text):
    """`fetch` for a result given by its id: download, check, and store it the way fetch does."""
    # Aggregate tools (collect_* / enrich_*) exist only in some copies; the shared section cannot reference them directly, so follow the renew_hint approach.
    aggregates = set(globals().get("AGGREGATE_TOOLS", ()))
    if tool not in COMPOSITE_TOOLS | {RESIGN_TOOL} | set(CONNECTOR_TOOLS.values()) | JOB_TOOLS | aggregates:
        raise ValueError("Not a declared evidence tool")
    if tool == "read_research_data_artifacts":
        raise ValueError("Artifact results have no result id; save the complete result and run fetch on it")
    raw, digest = download_result(result_id_of(text))
    full = json.loads(raw.decode("utf-8"))
    if not isinstance(full, dict):
        raise ValueError("Downloaded evidence must be an object")
    descriptor = {"kind": "envelope", "sha256": digest, "bytes": len(raw)}
    if tool in COMPOSITE_TOOLS:
        if full.get("schema_version") != COMPOSITE_SCHEMA or full.get("tool") != tool:
            raise ValueError(f"This id holds no {tool} result; check that the id belongs to that call")
        full = {key: item for key, item in full.items() if key != "download"}
        return {**split_composite(tool, full, {"delivery": "download"}), "fetched": [summary(descriptor)]}
    if full.get("schema_version") == COMPOSITE_SCHEMA:
        raise ValueError("This id holds a composite result; pass the composite tool's name")
    schema = globals().get("AGGREGATE_SCHEMAS", {}).get(tool)
    if schema and full.get("schema_version") != schema:
        raise ValueError(f"This id holds no {tool} result; check that the id belongs to that call")
    if tool in aggregates:
        full = {key: item for key, item in full.items() if key != "download"}
    try:
        check_envelope(tool, full)
    except ValueError as error:
        raise ValueError(f"{error}; check that the id belongs to the {tool} call") from None
    body = json.dumps(full, ensure_ascii=False).encode()
    result = store(tool, full, [(evidence_id() + ".json", body, {"delivery": "download"})])
    return {**result, "fetched": [summary(descriptor)]}


def composite_records(tool=None):
    """This run's staged composite records, oldest first; each call carries the absolute path of its envelope."""
    directory = run_dir() / "snapshot/.host-evidence"
    found = []
    for meta_path in directory.glob("*.meta"):
        metadata = json.loads(meta_path.read_text())
        if metadata.get("schema_version") != COMPOSITE_RECORD or (tool is not None and metadata.get("tool") != tool):
            continue
        body = meta_path.with_suffix(".json").read_bytes()
        if hashlib.sha256(body).hexdigest() != metadata.get("sha256"):
            raise ValueError("Previously staged evidence was altered")
        record = {**json.loads(body), "id": meta_path.stem, "staged_at": metadata.get("staged_at")}
        for call in record["calls"]:
            call["path"] = str(directory / (call["evidence_id"] + ".json"))
        found.append(record)
    return sorted(found, key=lambda record: (str(record["staged_at"]), record["id"]))


def render_result(result):
    # A single-tool result is still one line of JSON; a composite result as a whole is still valid JSON, with each individual call on its own line.
    if not (isinstance(result, dict) and "composite" in result):
        return json.dumps(result)
    head = json.dumps({key: item for key, item in result.items() if key != "calls"})
    lines = ",\n".join(json.dumps(entry) for entry in result["calls"])
    return head[:-1] + ', "calls": [' + ("\n" + lines + "\n" if lines else "") + "]}"


# Idempotency key for deferred media tools: the same run, same tool, same arguments and same attempt number yield the same key.
# When the host times out and the whole call is resent, the server hands back the original job by this key, with no new enqueue and no new charge. Reuse it only when the same call got no response; retrying after an error result,
# changed arguments, or re-running an already finished task all take the next attempt number (a failed enqueue leaves a queued job that never starts, and reusing the old key would get that job back).
KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:._-")
KEY_LIMIT = 128


def job_call(tool, raw_parameters, attempt):
    """The arguments of one deferred media call, with its idempotency_key beside `parameters`."""
    if not (tool.startswith("public_video_") and tool in CONNECTOR_TOOLS.values()):
        raise ValueError("Not a deferred media tool of this Skill: " + tool)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("--attempt must be a positive integer")
    parameters = json.loads(raw_parameters)
    if not isinstance(parameters, dict):
        raise ValueError("--parameters must be a JSON object")
    cap = FRAME_CAPS.get(tool)
    if cap is not None:
        # Add this Skill's frame cap when absent; an explicitly passed value may only be smaller.
        frames = parameters.setdefault("max_frames", cap)
        if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= cap:
            raise ValueError(f"max_frames must be an integer from 1 to {cap}")
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()[:16]
    key = "".join(char if char in KEY_CHARS else "-" for char in f"{SKILL.name}:{run_dir().name}:{tool}:{digest}:a{attempt}")
    if len(key) > KEY_LIMIT:
        # When the install directory name is too long, take a digest of the whole: still stable, just no longer readable.
        key = "kabo:" + hashlib.sha256(key.encode()).hexdigest()[:48] + f":a{attempt}"
    return {"tool": tool, "arguments": {"parameters": parameters, "delivery": "download", "idempotency_key": key}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--workspace", required=True)
    # Both subcommands read the full result only from a file or stdin, so the signed download link never appears in argv; `fetch --id` accepts only a result ID (valid for 10 minutes),
    # and the handoff has the model pass only the ID as well (docs/skills-spec.md KS7.3).
    for name in ("stage", "fetch"):
        command = commands.add_parser(name)
        command.add_argument("--tool", required=True)
        command.add_argument("--input", default="-")
    # A download-ready result is handed off by ID only (or a download link containing the ID), not stored as a file.
    command.add_argument("--id", help="the result id from the result's download url, instead of --input")
    command = commands.add_parser("job-call")
    command.add_argument("--tool", required=True)
    command.add_argument("--parameters", required=True)
    command.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    if args.command == "init":
        print(init(args.workspace))
    elif args.command == "job-call":
        print(json.dumps(job_call(args.tool, args.parameters, args.attempt), ensure_ascii=False))
    elif args.command == "fetch" and args.id:
        print(render_result(fetch_id(args.tool, args.id)))
    else:
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with open(args.input, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        print(render_result((stage if args.command == "stage" else fetch)(args.tool, raw)))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("Static evidence operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
