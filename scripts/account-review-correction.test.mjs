// Report-revision recovery path for review-creator-account (exposed by the 1.0.14 production regression):
// in `drive.py report --allow-authoring-correction`, compose has already written the report before the
// validator rejects it (e.g. Markdown exposes internal implementation terms). The old behavior left the
// report that failed validation in report/, so after fixing and rerunning it hit "a report already exists",
// verify-report no longer matched because the synthesis had been corrected, and the run could only fail.
// Now: on rejection, delete the report that failed validation and record a revision marker, so rerunning the
// same command after the fix produces the report (it still goes through verify-report in the end).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "review-creator-account", "scripts");

// Replace only the parts outside the report stage (reservation check, source preflight, child scripts); the
// report stage itself runs unchanged.
const harness = String.raw`
import json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import drive, connector_driver as cd

Path(drive.ANALYSIS).write_text(json.dumps({"snapshot_id": "s1", "rankings": [{"content_id": "c1"}]}))
Path(drive.SNAPSHOT).write_text(json.dumps({"schema_version": "public-content-snapshot.v1", "snapshot_id": "s1",
                                            "items": [{"content_id": "c1"}]}))
Path(drive.SYNTHESIS).write_text("{}")
drive.require_open_reservation = lambda directory: None
drive.preflight_report_sources = lambda *a: None
drive.validate_authoring = lambda *a: None
cd.state = lambda: {"envelopes": [{"file": "snapshot/envelope-01.json"}]}
attempts = {"validator": 0}

def script(name, *args, show=False):
    out = Path(args[args.index("--output-dir") + 1]) if "--output-dir" in args else Path("report")
    if name == "compose_review.py":
        out.mkdir(exist_ok=True)
        for file in ("account_review.json", "creator_profile.json", "ACCOUNT_REVIEW.md"):
            (out / file).write_text("draft")
    if name == "validate_creator_report.py":
        attempts["validator"] += 1
        if attempts["validator"] == 1:
            raise cd.StageError("validate_creator_report.py failed:\nexposes internal implementation details: ['provider']")
    return ""
cd.script = script

args = SimpleNamespace(output_dir="report", allow_authoring_correction=True)
try:
    drive.stage_report(args)
    print("FIRST: no error")
except cd.StageError as error:
    print("FIRST:", str(error).replace("\n", " "))
print("LEFT:", sorted(p.name for p in Path("report").glob("*")))
print("MARKER:", drive.AUTHORING_CORRECTION_MARKER.exists())
drive.stage_report(args)
print("FINAL:", drive.REPORT_FINAL_MARKER.exists())
`;

test("after a revision the same report command can produce the report: a report that failed validation is deleted, and verify-report still re-checks it at the end", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-acct-correction-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  const result = spawnSync("python3", ["-c", harness, scripts], {
    cwd: run, encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", KABO_STATIC_RUN_DIR: run },
  });
  const out = result.stdout + result.stderr;
  assert.equal(result.status, 0, out);
  assert.match(out, /FIRST: .*internal implementation details.*The unvalidated report was removed/);
  assert.match(out, /LEFT: \[\]/);
  assert.match(out, /MARKER: True/);
  assert.match(out, /creator_report: /);
  assert.match(out, /run drive\.py verify-report as the final step/);
  assert.match(out, /FINAL: False/);
  assert.doesNotMatch(out, /KABO_FINAL_REPLY_BEGIN/);
});

test("the first final delivery, the idempotent re-check and the post-revision re-check all deliver the full body, and a validation failure cannot produce the delivery marker", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-acct-delivery-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  const source = String.raw`
import contextlib, hashlib, io, json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import drive, connector_driver as cd
Path(drive.ANALYSIS).write_text(json.dumps({"snapshot_id":"s", "rankings":[{"content_id":"c"}]}))
Path(drive.SNAPSHOT).write_text(json.dumps({"schema_version":"public-content-snapshot.v1", "snapshot_id":"s", "items":[{"content_id":"c"}]}))
Path(drive.SYNTHESIS).write_text("{}")
drive.require_open_reservation = lambda directory: None
drive.preflight_report_sources = lambda *a: None
drive.validate_authoring = lambda *a: None
drive.close_unwrapped_reservation = lambda: None
cd.state = lambda: {"envelopes":[{"file":"snapshot/envelope-01.json"}]}
checks=[]
body="# Observations / 观察\n\nScope: cumulative counts, not equal-age performance.\n\n## Evidence\n\n[Example](https://example.com/post) (200 views; unequal windows)\n\n## Next step\n\nCompare matched periods. Success criterion: paid orders / inquiries.\n"
fail=False
def script(name, *args, show=False):
    if name == "compose_review.py":
        out=Path(args[args.index("--output-dir")+1]);out.mkdir(exist_ok=True)
        for file in ("account_review.json","creator_profile.json"):(out/file).write_text("{}")
        (out/"ACCOUNT_REVIEW.md").write_text(body)
    else:
        checks.append(name)
        if fail:raise cd.StageError("validator rejected source binding")
    return ""
cd.script=script
def capture(call):
    out=io.StringIO()
    with contextlib.redirect_stdout(out):call()
    text=out.getvalue()
    assert text.count("KABO_FINAL_REPLY_BEGIN") == text.count("KABO_FINAL_REPLY_END") == 1, text
    assert text.split("KABO_FINAL_REPLY_BEGIN\n",1)[1].split("\nKABO_FINAL_REPLY_END",1)[0] == body.rstrip()
    assert text.rstrip().endswith("creator_report: " + str(Path("report/ACCOUNT_REVIEW.md").resolve()))
    assert "Final-reply checklist:" not in text, "do not leak an internal checklist into creator replies"
    assert "validate_delivery.py" not in text, "delivery must not add a step after the existing final command"
capture(lambda: drive.stage_report(SimpleNamespace(output_dir="report",allow_authoring_correction=True)))
assert checks == ["validate_artifacts.py","validate_creator_report.py"]
capture(lambda: drive.stage_verify_report(SimpleNamespace(output_dir="report")))
assert len(checks) == 2, "cached verification must not rerun validators"
drive.REPORT_FINAL_MARKER.unlink()
drive.AUTHORING_CORRECTION_MARKER.write_text("needs_revision\n")
capture(lambda: drive.stage_verify_report(SimpleNamespace(output_dir="report")))
assert len(checks) == 4
# Recovery of a finished run only reads the bytes matching the verified digest and reassembles the body piece by piece, without re-running validation or changing state.
report = Path("report/ACCOUNT_REVIEW.md")
before = (report.read_bytes(), drive.REPORT_FINAL_MARKER.read_bytes())
parts=[];offset=0
while True:
    out=io.StringIO()
    with contextlib.redirect_stdout(out):drive.read_final_report(SimpleNamespace(output_dir="report",offset=offset,limit=17))
    chunk=json.loads(out.getvalue());parts.append(chunk["text"])
    assert len(chunk["text"]) <= 17
    offset=chunk["next_offset"]
    if offset is None:break
assert "".join(parts) == body
assert before == (report.read_bytes(), drive.REPORT_FINAL_MARKER.read_bytes())
assert len(checks) == 4
for offset, limit in [(-1,17),(0,2049),(len(body)+1,17)]:
    try:drive.read_final_report(SimpleNamespace(output_dir="report",offset=offset,limit=limit))
    except cd.StageError:pass
    else:raise AssertionError("invalid readback range accepted")
report.write_text(body + "changed")
try:drive.read_final_report(SimpleNamespace(output_dir="report",offset=0,limit=17))
except cd.StageError:pass
else:raise AssertionError("changed report accepted")
report.write_text(body)
# When closing after a revision fails to persist, the final delivery marker or path must not be emitted first.
drive.REPORT_FINAL_MARKER.unlink()
def fail_close():raise cd.StageError("manifest write failed")
drive.close_unwrapped_reservation=fail_close
out=io.StringIO()
with contextlib.redirect_stdout(out):
    try:drive.stage_verify_report(SimpleNamespace(output_dir="report"))
    except cd.StageError:pass
    else:raise AssertionError("reservation closure failure swallowed")
assert "KABO_FINAL_REPLY_BEGIN" not in out.getvalue()
assert "creator_report:" not in out.getvalue()
assert not drive.REPORT_FINAL_MARKER.exists()
drive.close_unwrapped_reservation=lambda: None
fail=True
out=io.StringIO()
with contextlib.redirect_stdout(out):
    try:drive.stage_verify_report(SimpleNamespace(output_dir="report"))
    except cd.StageError:pass
    else:raise AssertionError("failed validation must stop")
assert "KABO_FINAL_REPLY_BEGIN" not in out.getvalue()
`;
  const result = spawnSync("python3", ["-c", source, scripts], {
    cwd: run, encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", KABO_STATIC_RUN_DIR: run },
  });
  assert.equal(result.status, 0, result.stdout + result.stderr);
});
