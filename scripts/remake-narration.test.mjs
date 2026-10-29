import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills/remake-viral-video/scripts");

// 旁白（voice-over）的本地脚本：画面检查、preview / 看图返工的提交参数、分页下载。
// 下载经进程内的假 HTTPS 处理器，测试不联网。
const PY = String.raw`
import base64, hashlib, http.client, importlib.util, io, json, os, sys, urllib.request, urllib.response
sys.dont_write_bytecode = True

scripts, workspace = sys.argv[1], sys.argv[2]
def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(scripts, name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
host, docs = load("static_host"), load("check_documents")
out = {}

responses = {}
class FakeHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        code, body, ctype = responses[req.full_url]
        message = http.client.parse_headers(io.BytesIO(f"Content-Type: {ctype}\r\n\r\n".encode()))
        response = urllib.response.addinfourl(io.BytesIO(body), message, req.full_url, code)
        response.msg = "fake"
        return response
host.build_opener = lambda: urllib.request.build_opener(host.NoRedirect(), FakeHTTPS())

def descriptor(name, body, ctype, kind="artifact"):
    url = "https://storage.googleapis.com/kabo/" + name + "?X-Goog-Signature=x"
    responses[url] = (200, body, ctype)
    return {"status": "ready", "kind": kind, "url": url, "expires_at": "2999-01-01T00:00:00Z",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "content_type": ctype}

run = host.init(workspace)
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
JOB = "11111111-1111-4111-8111-111111111111"

# 1. a voice-over brief has no jobs template
brief = {"work/brief_input.json": json.dumps({"reference": {"type": "narration"}}),
         "work/script.draft.json": "{}", "work/decisions.draft.json": json.dumps({"picture_system": "", "pictures": []})}
bundle = json.dumps({"schema": host.BRIEF_SCHEMA, "job_id": JOB, "files": brief}).encode()
saved = host.fetch_brief(run, {"status": "waiting_script", "job_id": JOB,
                               "brief": {"download": descriptor("brief.json", bundle, "application/json", "envelope")}})
out["brief_files"] = sorted(saved["files"])

# 2. the picture plan
script = {"lines": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}
errors = []
docs.check_pictures({"picture_system": "drawn", "pictures": [
    {"lines": [0], "make": {"kind": "composition", "markup": "<div class=\"clip\"><img src=\"data:image/png;base64,AA\"></div>"}},
    {"lines": [1], "make": {"kind": "generated"}}]}, script, errors)
out["picture_errors"] = errors
errors = []
docs.check_pictures({"picture_system": "drawn", "pictures": [
    {"lines": [0, 1], "make": {"kind": "composition", "markup": "<div class=\"clip\"><img class=\"clip\" src=\"result.png\"></div>",
                               "images": {"result.png": {"prompt": "a portrait"}}}},
    {"lines": [2], "make": {"kind": "generated", "prompt": "a desk", "motion": "push in"}}]}, script, errors)
out["picture_ok"] = errors

# 3. render arguments: voice-over has no talking model; preview and beat_review calls
docs.check = lambda run: {"status": "ready", "errors": [], "warnings": [], "kind": "narration"}
for name in docs.DOCUMENTS.values():
    (run / name).write_text("{}", encoding="utf-8")
(run / "script/script.json").write_text(json.dumps({"lines": [{"text": "a"}, {"text": "b"}]}))
plain = docs.render_args(run, None, None)
out["render"] = sorted(json.loads(open(plain["render_arguments"]).read()))
pv = docs.render_args(run, None, None, preview="stills")
out["preview"] = json.loads(open(pv["render_arguments"]).read())["preview"]
(run / "script/beat_review.json").write_text(json.dumps({"lines": [{"line": 0, "ok": True}, {"line": 1, "ok": False, "note": "empty map"}]}))
rv = docs.render_args(run, None, None, beat_review=str(run / "script/beat_review.json"))
out["review_keys"] = sorted(json.loads(open(rv["render_arguments"]).read()))
for bad, kwargs in (("talking", {"model": "vivix/vivix-a1"}), ("both", {"preview": "pictures", "beat_review": "x"})):
    try:
        docs.render_args(run, kwargs.get("model"), None, kwargs.get("preview"), kwargs.get("beat_review"))
        out["refused_" + bad] = False
    except ValueError:
        out["refused_" + bad] = True
(run / "script/beat_review.json").write_text(json.dumps({"lines": [{"line": 0, "ok": True}]}))
try:
    docs.render_args(run, None, None, beat_review=str(run / "script/beat_review.json"))
    out["refused_incomplete"] = False
except ValueError:
    out["refused_incomplete"] = True
(run / "script/beat_review.json").write_text(json.dumps({"lines": [{"line": 0, "ok": True}, {"line": 1, "ok": False}]}))
try:
    docs.render_args(run, None, None, beat_review=str(run / "script/beat_review.json"))
    out["refused_no_note"] = False
except ValueError:
    out["refused_no_note"] = True

# 4. preview pages ride in the brief envelope
jpeg = b"\xff\xd8\xff\xe0" + b"0" * 60
def envelope(name, extra):
    body = json.dumps({"schema": host.BRIEF_SCHEMA, "job_id": JOB, "files": brief, **extra}).encode()
    return {"status": "waiting_script", "job_id": JOB,
            "brief": {"download": descriptor(name, body, "application/json", "envelope")}}
preview = {"status": "done", "pages": [
    {"download": descriptor("p1.jpg", jpeg, "image/jpeg")}, {"download": descriptor("p2.jpg", jpeg, "image/jpeg")}],
    "stills": {}, "rows": [{"row": 0, "lines": [0]}, {"row": 1, "lines": [1], "error": "lint: left"}], "spend_usd": 0.04}
first = host.fetch_preview(run, envelope("e1.json", {"preview": preview}))
second = host.fetch_preview(run, envelope("e2.json", {"preview": preview}))
out["preview_pages"] = [os.path.relpath(p, run) for p in first["pages"] + second["pages"]]
out["preview_errors"] = first["errors"]
try:
    host.fetch_preview(run, envelope("e3.json", {"preview": {"status": "running"}}))
except ValueError as error:
    out["preview_running"] = str(error)[:40]
# the same brief with a fresh preview inside is not a new brief
out["same_brief"] = host.fetch(json.dumps(envelope("e4.json", {"preview": preview})).encode())["status"]

# 5. the picture review
review_files = {name: "{}" for name in host.REVIEW_FILES}
rbody = json.dumps({"schema": host.BRIEF_SCHEMA, "job_id": JOB, "files": review_files,
                    "review": {"sheets": [{"download": descriptor("s1.jpg", jpeg, "image/jpeg")}]}}).encode()
review = {"status": "waiting_script", "job_id": JOB,
          "brief": {"download": descriptor("rbrief.json", rbody, "application/json", "envelope")}}
# a page that fails its check leaves nothing behind, so the fetch can run again
bad_sheet = dict(descriptor("s0.jpg", jpeg, "image/jpeg")); bad_sheet["sha256"] = "0" * 64
bbody = json.dumps({"schema": host.BRIEF_SCHEMA, "job_id": JOB, "files": review_files,
                    "review": {"sheets": [{"download": bad_sheet}]}}).encode()
try:
    host.fetch(json.dumps({"status": "waiting_script", "job_id": JOB,
        "brief": {"download": descriptor("bbrief.json", bbody, "application/json", "envelope")}}).encode())
except ValueError:
    pass
out["review_left_nothing"] = not (run / "review").exists() and not list(run.glob(".review-staging-*"))
saved = host.fetch(json.dumps(review).encode())
out["review"] = [saved["saved"], [os.path.relpath(p, run) for p in saved["pages"]], sorted(saved["files"])]
try:
    host.fetch(json.dumps(review).encode())
    out["review_twice"] = False
except ValueError:
    out["review_twice"] = True
print(json.dumps(out))
`;

test("remake-viral-video 旁白：画面检查、preview / review 参数与分页下载", async (t) => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-remake-narration-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const res = spawnSync("python3", ["-I", "-c", PY, scripts, temp], { encoding: "utf8" });
  assert.equal(res.status, 0, res.stderr);
  const out = JSON.parse(res.stdout);
  assert.deepEqual(out.brief_files, ["work/brief_input.json", "work/decisions.draft.json", "work/script.draft.json"]);
  assert.equal(out.picture_errors.length, 3);
  assert.match(out.picture_errors[0], /data:/);
  assert.match(out.picture_errors[1], /needs prompt/);
  assert.match(out.picture_errors[2], /script lines \[2\]/);
  assert.deepEqual(out.picture_ok, []);
  assert.deepEqual(out.render, ["files", "job_id"]);
  assert.equal(out.preview, "stills");
  assert.deepEqual(out.review_keys, ["beat_review", "files", "job_id"]);
  assert.equal(out.refused_talking, true);
  assert.equal(out.refused_both, true);
  assert.equal(out.refused_no_note, true);
  assert.equal(out.refused_incomplete, true);
  assert.deepEqual(out.preview_pages, ["preview/1/page_01.jpg", "preview/1/page_02.jpg", "preview/2/page_01.jpg", "preview/2/page_02.jpg"]);
  assert.deepEqual(out.preview_errors, [{ row: 1, lines: [1], error: "lint: left" }]);
  assert.match(out.preview_running, /still rendering/);
  assert.equal(out.same_brief, "already_saved");
  assert.deepEqual(out.review, ["review", ["review/pages/page_01.jpg"],
    ["production/review/beats/beat_review.template.json", "work/decisions.json", "work/script.json"]]);
  assert.equal(out.review_twice, true);
  assert.equal(out.review_left_nothing, true);
});
