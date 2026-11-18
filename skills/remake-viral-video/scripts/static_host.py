#!/usr/bin/env python3
"""Local upload helper for the remake-viral-video Skill; no model loop.

Commands:
  init        reserve one run directory under <workspace>/.kabo-runs/
  upload-call check one local video or photo the user gave and print the upload_file arguments
  upload      send that file's bytes to the signed upload link an upload_file result returned, then
              print the upload_file arguments that verify it

Network access: `upload` makes one POST (opens the resumable session) and one PUT (the file's
bytes) to the signed storage.googleapis.com link an upload_file result returned.
"""
from __future__ import annotations

import argparse
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


# Tool results are tiny (only links and summaries); the brief JSON is far below 32 MiB, and the finished video leaves headroom for a 60-second short video.
MAX_RESULT_BYTES = 4 * 1024 * 1024


# Download delivery: accept only the GCS signed link given in a Kabo tool result; GET only, never follow redirects (Kabo Skills spec KS7.3).
DOWNLOAD_HOST = "storage.googleapis.com"


DOWNLOAD_PREFIX = "https://" + DOWNLOAD_HOST + "/"


DOWNLOAD_TIMEOUT = 120


RUN_DIRS = ("host-results", "brief", "script", "render", "output", "project", "project/steps", "project/edits")


# Local file upload (upload_file registration + check): types and limits are the same as the Kabo user file policy; for photos remake accepts only JPEG / PNG.
UPLOAD_VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v", ".webm": "video/webm"}


UPLOAD_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


UPLOAD_VIDEO_MAX_BYTES = 200 * 1000 * 1000


UPLOAD_IMAGE_MAX_BYTES = 10 * 1000 * 1000


# A signed upload sends only the headers the server signed in; any extra header (especially Authorization) is rejected.
UPLOAD_HEADERS = frozenset({"content-type", "x-goog-resumable", "x-goog-if-generation-match", "x-goog-content-length-range"})


UPLOAD_TIMEOUT = 900


KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:._-")


KEY_LIMIT = 128


def run_dir():
    raw = os.environ.get("KABO_STATIC_RUN_DIR")
    if raw:
        run = Path(raw).resolve(strict=True)
    else:
        # The host does not necessarily keep environment variables between commands; search upward from the current directory for this run's marker.
        here = Path.cwd().resolve()
        run = next((path for path in (here, *here.parents) if (path / ".static-run.json").is_file()), None)
        if run is None:
            raise ValueError("Set KABO_STATIC_RUN_DIR to this request's reserved directory, or run the command from inside it")
    if not (run / ".static-run.json").is_file():
        raise ValueError("Not a reserved static Skill run")
    # Some hosts keep only files between two executions and not empty directories (the Web Agent sandbox workspace): the empty subdirectories created by init
    # are gone by the next step. Complete them on every entry into the run directory; existing ones are left untouched.
    for name in ("snapshot", "snapshot/.host-evidence", "analysis", "report", "owner", "host-results",
                 "project/steps", "project/edits"):
        (run / name).mkdir(mode=0o700, parents=True, exist_ok=True)
    return run


def init(workspace):
    base = Path(workspace).resolve(strict=True) / ".kabo-runs"
    if SKILL == base or SKILL in base.parents:
        raise ValueError("Runs must be outside the installed Skill")
    base.mkdir(mode=0o700, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(6)
    run = base / name
    run.mkdir(mode=0o700)
    # host-results/ holds the full tool results saved by the host (input to fetch); brief/ holds the downloaded brief, script/ holds the four files written by the host,
    # render/ holds submission arguments, and output/ holds the finished video.
    for name in RUN_DIRS:
        (run / name).mkdir(mode=0o700)
    write_new(run / ".static-run.json", json.dumps({"format": "kabo.static-run.v1", "skill": SKILL.name}).encode())
    return run


def write_new(path, body):
    # Exclusive write: retries and concurrency must not overwrite saved files.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)


JOB_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _key(tool, arguments, attempt):
    """Idempotency key for KS8 job-call: <skill>:<run directory name>:<tool name>:<arguments digest>:a<attempt number>."""
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("--attempt must be a positive integer")
    digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()[:16]
    key = "".join(char if char in KEY_CHARS else "-"
                  for char in f"{SKILL.name}:{run_dir().name}:{tool}:{digest}:a{attempt}")
    if len(key) > KEY_LIMIT:
        key = "kabo:" + hashlib.sha256(key.encode()).hexdigest()[:48] + f":a{attempt}"
    return key


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
    # Tests can replace this function in-process to inject a fake HTTPS handler; no command-line entry point can change it.
    context = tls_context()
    handlers = [NoRedirect()] + ([urllib.request.HTTPSHandler(context=context)] if context else [])
    return urllib.request.build_opener(*handlers)


def expired(descriptor):
    try:
        stamp = datetime.fromisoformat(str(descriptor.get("expires_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return stamp.tzinfo is not None and stamp <= datetime.now(timezone.utc)


def _local_file(path):
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"--file is not a readable file: {path}")
    ext = file.suffix.lower()
    if ext in UPLOAD_VIDEO_TYPES:
        kind, limit = "video", UPLOAD_VIDEO_MAX_BYTES
    elif ext in UPLOAD_IMAGE_TYPES:
        kind, limit = "image", UPLOAD_IMAGE_MAX_BYTES
    else:
        raise ValueError("--file must be a video (" + ", ".join(sorted(UPLOAD_VIDEO_TYPES)) + ") or a JPEG / PNG photo")
    size = file.stat().st_size
    if size <= 0:
        raise ValueError("--file is empty")
    if size > limit:
        raise ValueError(f"--file is {size / 1e6:.1f} MB; Kabo takes {kind}s of at most {limit // 1000000} MB. "
                         "Ask the user for a shorter or smaller file, or a public link")
    hasher = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return file, ext, kind, size, hasher.hexdigest()


def upload_call(path, attempt):
    """Input of upload_file (register): the file is named by its content digest (the user's file name is not sent out), and the idempotency key is bound to the file content."""
    _file, ext, kind, size, digest = _local_file(path)
    arguments = {"filename": f"{kind}-{digest[:16]}{ext}", "size_bytes": size}
    key = _key("upload_file", {**arguments, "sha256": digest}, attempt)
    return {"tool": "upload_file", "arguments": {**arguments, "idempotency_key": key}}


def _structured(raw, tool):
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError(f"The {tool} result is larger than expected")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"The complete {tool} result must be a JSON object")
    if value.get("isError") and "structuredContent" not in value:
        blocks = value.get("content") if isinstance(value.get("content"), list) else []
        text = " ".join(b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str))
        raise ValueError(f"{tool} returned an error: " + (text.strip()[:300] or "no message"))
    structured = value.get("structuredContent", value)
    if "content" in value and "structuredContent" not in value:
        blocks = value["content"]
        if not isinstance(blocks, list) or not blocks or not isinstance(blocks[0], dict) \
                or not isinstance(blocks[0].get("text"), str):
            raise ValueError(f"The complete structured {tool} result is required")
        structured = json.loads(blocks[0]["text"])
    if not isinstance(structured, dict):
        raise ValueError(f"This is not a {tool} result")
    return structured


def _signed_storage(url):
    return (isinstance(url, str) and url.startswith(DOWNLOAD_PREFIX) and urlsplit(url).netloc == DOWNLOAD_HOST
            and not any(ord(char) <= 32 or ord(char) == 127 for char in url))


UPLOAD_RESIGN = ("Call upload_file again with the same upload-call arguments (that signs a new link; the upload is not "
                 "duplicated), save its complete result and run upload on it right away")


def upload(raw, path):
    """Send a local file to the signed link given by upload_file: one POST opens a resumable session, one PUT sends the complete bytes."""
    structured = _structured(raw, "upload_file")
    file_id = structured.get("file_id")
    if not isinstance(file_id, str) or not JOB_ID_RE.match(file_id):
        raise ValueError("This upload_file result has no file_id")
    file, _ext, _kind, size, _digest = _local_file(path)
    ref = f"kabo-file:{file_id.lower()}"
    if structured.get("status") == "ready":
        # The same file has already been uploaded and verified (same-key replay); no need to upload again.
        return {"status": "ready", "file_ref": ref,
                "next": f"Use {ref} wherever this file goes (a reference, creator video or photo, or reference image)"}
    instruction = structured.get("upload")
    if structured.get("status") != "upload_required" or not isinstance(instruction, dict):
        raise ValueError("This upload_file result has no upload instruction")
    url, headers = instruction.get("url"), instruction.get("headers") or {}
    if str(instruction.get("method", "")).upper() != "POST" or not _signed_storage(url):
        raise ValueError("The upload link is not a Kabo signed storage link; refusing to use it")
    if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                            or k.lower() not in UPLOAD_HEADERS for k, v in headers.items()):
        raise ValueError("The upload instruction asks for headers other than the signed ones; refusing to use it")
    if expired({"expires_at": instruction.get("expires_at")}):
        raise ValueError("The upload link expired. " + UPLOAD_RESIGN)
    opener = build_opener()
    # Errors state only the category and status code: exception text may carry the link, signature or object name, so it is never relayed.
    try:
        with opener.open(urllib.request.Request(url, data=b"", method="POST", headers=headers),
                         timeout=DOWNLOAD_TIMEOUT) as response:
            status, session = response.status, response.headers.get("Location")
    except urllib.error.HTTPError as error:
        status, session = error.code, None
        error.close()
    except Exception as error:
        raise ValueError(f"Opening the upload failed ({type(error).__name__}). If this host blocks network access "
                         "for scripts, say the local file cannot be sent from here and ask for a public link") from None
    if status in (400, 401, 403):
        raise ValueError(f"The upload link expired or was refused (HTTP {status}). " + UPLOAD_RESIGN)
    if status == 412:
        raise ValueError("This upload was already sent. Call upload_file with only this file_id")
    if status not in (200, 201) or not _signed_storage(session):
        raise ValueError(f"Opening the upload failed (HTTP {status}). " + UPLOAD_RESIGN)
    try:
        with file.open("rb") as stream:
            request = urllib.request.Request(session, data=stream, method="PUT",
                                             headers={"Content-Length": str(size)})
            with opener.open(request, timeout=UPLOAD_TIMEOUT) as response:
                status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except Exception as error:
        raise ValueError(f"Sending the file failed ({type(error).__name__}). " + UPLOAD_RESIGN) from None
    if status not in (200, 201):
        raise ValueError(f"Sending the file failed (HTTP {status}). " + UPLOAD_RESIGN)
    return {"status": "uploaded", "tool": "upload_file", "arguments": {"file_id": file_id.lower()},
            "next": f"Call upload_file with only this file_id; once it says ready, use {ref} wherever this "
                    "file goes"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--workspace", required=True)
    command = commands.add_parser("upload-call")
    command.add_argument("--file", required=True)
    command.add_argument("--attempt", type=int, default=1)
    # The signed upload link is read only from the complete result file or stdin, never from argv.
    command = commands.add_parser("upload")
    command.add_argument("--file", required=True)
    command.add_argument("--input", default="-")
    args = parser.parse_args()
    if args.command == "init":
        print(init(args.workspace))
    elif args.command == "upload-call":
        print(json.dumps(upload_call(args.file, args.attempt), ensure_ascii=False))
    else:
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_RESULT_BYTES + 1)
        else:
            with open(args.input, "rb") as stream:
                raw = stream.read(MAX_RESULT_BYTES + 1)
        print(json.dumps(upload(raw, args.file), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("Remake run operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
