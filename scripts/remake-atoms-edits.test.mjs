import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

// remake-viral-video 的原子项目与出片后修改（跨仓契约 v1）：脚本生成的入参必须通过钉住的
// inputSchema；下载只走工具结果给的签名链接，经进程内假 HTTPS 处理器，测试不联网。
const root = fileURLToPath(new URL("..", import.meta.url));
const script = path.join(root, "skills/remake-viral-video/scripts/static_host.py");
const scripts = path.dirname(script);
const pinned = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map(t => [t.name, t]));
const ajv = new Ajv({ allErrors: true, strict: false, logger: false, validateFormats: false });
const JOB = "11111111-1111-4111-8111-111111111111";

async function newRun(t) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-remake-atoms-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const res = spawnSync("python3", ["-B", script, "init", "--workspace", workspace], { encoding: "utf8" });
  assert.equal(res.status, 0, res.stderr);
  return res.stdout.trim();
}

function call(run, args) {
  const res = spawnSync("python3", ["-B", script, ...args], {
    cwd: run, encoding: "utf8", env: { ...process.env, KABO_STATIC_RUN_DIR: run, PYTHONDONTWRITEBYTECODE: "1" },
  });
  return { status: res.status, stderr: res.stderr, out: res.status === 0 ? JSON.parse(res.stdout) : null };
}

function valid(tool, args) {
  const check = ajv.compile(pinned.get(tool).inputSchema);
  assert.ok(check(args), `${tool}: ${JSON.stringify(check.errors)}`);
}

test("工具清单含四个新工具（权限 video）且 get_remake_video 带 handles / revisions / last_step", () => {
  for (const name of ["start_video_project", "make_video_step", "edit_remake_video", "finish_video_project"]) {
    const tool = pinned.get(name);
    assert.ok(tool, name);
    assert.deepEqual(tool.securitySchemes, [{ scopes: ["video"], type: "oauth2" }]);
    assert.ok(JSON.stringify(tool.inputSchema).includes("idempotency_key"));
  }
  const get = pinned.get("get_remake_video").outputSchema.properties;
  for (const key of ["kind", "handles", "revisions", "last_step"]) assert.ok(get[key], key);
  assert.ok(get.status.enum.includes("ready") && get.status.enum.includes("working"));
});

test("project-call / step-call / edit-call / finish-call 生成的入参通过钉住的 schema，幂等键稳定", async (t) => {
  const run = await newRun(t);
  const project = call(run, ["project-call", "--creator-video", "https://www.youtube.com/shorts/abc123", "--creator-name", "amy"]);
  assert.equal(project.status, 0, project.stderr);
  assert.equal(project.out.tool, "start_video_project");
  valid("start_video_project", project.out.arguments);
  assert.match(project.out.arguments.idempotency_key, /^remake-viral-video:[^:]+:start_video_project:[0-9a-f]{16}:a1$/);

  const steps = {
    frame: { op: "frame", inputs: { video: "creator/clip1.mp4" }, params: { t: 2.5 } },
    motion: { op: "motion", inputs: { image: "a01.png", video: "a02.mp4" }, params: { model: "fal-ai/kling-video/v3/pro/motion-control" } },
    tts: { op: "tts", inputs: {}, params: { lines: ["Hello there."] } },
    cards: { op: "text_cards", inputs: { base: "a03.mp4" }, params: { cards: [{ text: "Step one", t0: 0, t1: 2 }], style: "plain" } },
    refvideo: { op: "refvideo", inputs: { images: ["a01.png", "a04.png"] }, params: { prompt: "She waters the plants.", duration: 5 } },
  };
  for (const [name, step] of Object.entries(steps)) {
    const file = path.join(run, "project/steps", `${name}.json`);
    await writeFile(file, JSON.stringify(step));
    const res = call(run, ["step-call", "--job-id", JOB, "--step", file]);
    assert.equal(res.status, 0, `${name}: ${res.stderr}`);
    valid("make_video_step", res.out.arguments);
    const again = call(run, ["step-call", "--job-id", JOB, "--step", file]);
    assert.equal(again.out.arguments.idempotency_key, res.out.arguments.idempotency_key);
    const next = call(run, ["step-call", "--job-id", JOB, "--step", file, "--attempt", "2"]);
    assert.match(next.out.arguments.idempotency_key, /:a2$/);
  }

  await writeFile(path.join(run, "script/script.json"), JSON.stringify({ lines: [{ text: "a" }, { text: "b" }] }));
  const edits = path.join(run, "project/edits/01.json");
  await writeFile(edits, JSON.stringify([
    { kind: "lines", lines: [{ row: 1, text: "new words" }] },
    { kind: "captions", color: "#FFD400", size: 1.25 },
    { kind: "overlay", t0: 3, t1: 6, media: "a05.png", box: [0.1, 0.1, 0.4] },
    { kind: "background", t0: 0, t1: 4, plate: "a06.png" },
    { kind: "clip", t0: 8, t1: 10, clip: "a07.mp4" },
  ]));
  const edit = call(run, ["edit-call", "--job-id", JOB, "--edits", edits]);
  assert.equal(edit.status, 0, edit.stderr);
  valid("edit_remake_video", edit.out.arguments);

  const finish = call(run, ["finish-call", "--job-id", JOB, "--handle", "a07.mp4"]);
  assert.equal(finish.status, 0, finish.stderr);
  valid("finish_video_project", finish.out.arguments);
});

test("step-call / edit-call 在付费调用前拒收路径、链接、未列出的模型与越界参数", async (t) => {
  const run = await newRun(t);
  const bad = [
    [{ op: "frame", inputs: { video: "../etc/passwd" }, params: { t: 1 } }, /workspace handle/],
    [{ op: "frame", inputs: { video: "https://storage.googleapis.com/x.mp4" }, params: { t: 1 } }, /workspace handle/],
    [{ op: "motion", inputs: { image: "a01.png", video: "a02.mp4" }, params: { model: "some/trial-model" } }, /must be one of/],
    [{ op: "shell", inputs: {}, params: {} }, /op must be one of/],
    [{ op: "still", inputs: {}, params: { prompt: "x", seed: 3 } }, /does not take params seed/],
    [{ op: "overlay", inputs: { base: "a01.mp4", media: "a02.png" }, params: { t0: 5, t1: 2 } }, /t1 must be after t0/],
    [{ op: "music", inputs: { base: "a01.mp4" }, params: { mood: "epic" } }, /calm, upbeat/],
  ];
  for (const [step, message] of bad) {
    const file = path.join(run, "project/steps/bad.json");
    await writeFile(file, JSON.stringify(step));
    const res = call(run, ["step-call", "--job-id", JOB, "--step", file]);
    assert.notEqual(res.status, 0, JSON.stringify(step));
    assert.match(res.stderr, message);
  }
  await writeFile(path.join(run, "script/script.json"), JSON.stringify({ lines: [{ text: "a" }] }));
  for (const [edits, message] of [
    [[{ kind: "lines", lines: [{ row: 4, text: "x" }] }], /past the script's 1 lines/],
    [[{ kind: "captions" }], /needs color or size/],
    [[{ kind: "captions", size: 3 }], /0.5 to 2/],
    [[{ kind: "overlay", t0: 1, t1: 2, media: "/tmp/a.png" }], /workspace handle/],
    [[], /1 to 10 edits/],
  ]) {
    const file = path.join(run, "project/edits/bad.json");
    await writeFile(file, JSON.stringify(edits));
    const res = call(run, ["edit-call", "--job-id", JOB, "--edits", file]);
    assert.notEqual(res.status, 0, JSON.stringify(edits));
    assert.match(res.stderr, message);
  }
  const res = call(run, ["finish-call", "--job-id", "not-a-uuid", "--handle", "a01.mp4"]);
  assert.match(res.stderr, /UUID/);
});

const PY = String.raw`
import hashlib, http.client, importlib.util, io, json, os, sys, urllib.request, urllib.response
sys.dont_write_bytecode = True
scripts, workspace = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("static_host", os.path.join(scripts, "static_host.py"))
host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
responses = {}
class FakeHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        code, body, ctype = responses[req.full_url]
        message = http.client.parse_headers(io.BytesIO(f"Content-Type: {ctype}\r\n\r\n".encode()))
        response = urllib.response.addinfourl(io.BytesIO(body), message, req.full_url, code)
        response.msg = "fake"
        return response
host.build_opener = lambda: urllib.request.build_opener(host.NoRedirect(), FakeHTTPS())
def descriptor(name, body, ctype):
    url = "https://storage.googleapis.com/kabo/" + name + "?X-Goog-Signature=x"
    responses[url] = (200, body, ctype)
    return {"status": "ready", "kind": "artifact", "url": url, "expires_at": "2999-01-01T00:00:00Z",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "content_type": ctype}
run = host.init(workspace)
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
JOB = "11111111-1111-4111-8111-111111111111"
out = {}
png = b"\x89PNG\r\n\x1a\n" + b"0" * 40
mp4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 40
step = {"op": "frame", "status": "done", "spend_usd": 0, "model": None,
        "output": {"handle": "a01.png", "type": "image", "download": descriptor("a01.png", png, "image/png")}}
saved = host.fetch_step(run, {"job_id": JOB, "status": "ready", "kind": "project", "last_step": step})
out["step"] = [saved["saved"], os.path.relpath(saved["path"], run), saved["handle"]]
out["step_again"] = host.fetch_step(run, {"job_id": JOB, "status": "ready", "last_step": step})["status"]
face = {"op": "motion", "status": "done", "spend_usd": 4.1, "model": "fal-ai/kling-video/v3/pro/motion-control",
        "fallback_from": "alibaba/wan-3.0/reference-to-video", "face": {"verdict": "degraded", "median": 0.5, "p10": 0.4},
        "output": {"handle": "a02.mp4", "type": "video", "seconds": 5, "download": descriptor("a02.mp4", mp4, "video/mp4")}}
saved = host.fetch_step(run, {"job_id": JOB, "status": "ready", "last_step": face})
out["face"] = [saved["face"], saved["fallback_from"], saved["spend_usd"]]
try:
    host.fetch_step(run, {"job_id": JOB, "status": "working", "last_step": {"op": "motion", "status": "running"}})
except ValueError as error:
    out["running"] = str(error)[:30]
out["failed"] = host.fetch_step(run, {"job_id": JOB, "status": "ready",
                                      "last_step": {"op": "refvideo", "status": "failed", "error": "refused"}})
# a declared image that is really something else is not kept
wrong = dict(step); wrong["output"] = {"handle": "a03.png", "type": "image", "download": descriptor("a03.png", mp4, "image/png")}
try:
    host.fetch_step(run, {"job_id": JOB, "status": "ready", "last_step": wrong})
except ValueError as error:
    out["wrong_type"] = str(error)[:80]
out["wrong_left_nothing"] = not (run / "project/outputs/a03.png").exists()
# an edit: the new revision is saved next to the first delivery
first = host.fetch_video(run, {"job_id": JOB, "status": "delivered", "video": {"download": descriptor("final.mp4", mp4, "video/mp4")}})
mp4b = mp4 + b"1"
edited = host.fetch_video(run, {"job_id": JOB, "status": "delivered", "kind": "remake",
    "video": {"download": descriptor("final_r1.mp4", mp4b, "video/mp4")},
    "revisions": [{"n": 1, "created_at": "2026-11-04T00:00:00Z", "notes": "Line 2 re-voiced; nothing else changed."}],
    "last_step": {"op": "edit", "status": "done", "spend_usd": 0.4, "face": {"verdict": "pass"}}})
out["video"] = [os.path.relpath(first["path"], run), os.path.relpath(edited["path"], run), edited["revision"],
                edited["revision_notes"], edited["last_step"]["face"]]
print(json.dumps(out))
`;

test("fetch-step 存下一步的产物并转述花费、回退模型与人脸结论；修改后的成片另存为新修订版", async (t) => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-remake-atoms-fetch-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const res = spawnSync("python3", ["-I", "-c", PY, scripts, temp], { encoding: "utf8" });
  assert.equal(res.status, 0, res.stderr);
  const out = JSON.parse(res.stdout);
  assert.deepEqual(out.step, ["step", "project/outputs/a01.png", "a01.png"]);
  assert.equal(out.step_again, "already_saved");
  assert.deepEqual(out.face, ["degraded", "alibaba/wan-3.0/reference-to-video", 4.1]);
  assert.match(out.running, /still running/);
  assert.equal(out.failed.saved, null);
  assert.equal(out.failed.error, "refused");
  assert.match(out.wrong_type, /declared image type/);
  assert.equal(out.wrong_left_nothing, true);
  assert.deepEqual(out.video, ["output/remake-11111111.mp4", "output/remake-11111111-r1.mp4", 1,
    "Line 2 re-voiced; nothing else changed.", "pass"]);
});
