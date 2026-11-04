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

test("工具清单含四个新工具（权限 video）；get_remake_video 带 project（handles / revisions / last_step）与 cancel", () => {
  for (const name of ["start_video_project", "make_video_step", "edit_remake_video", "finish_video_project"]) {
    const tool = pinned.get(name);
    assert.ok(tool, name);
    assert.deepEqual(tool.securitySchemes, [{ scopes: ["video"], type: "oauth2" }]);
    assert.ok(JSON.stringify(tool.inputSchema).includes("idempotency_key"));
  }
  const get = pinned.get("get_remake_video");
  const project = get.outputSchema.properties.project.properties;
  for (const key of ["kind", "handles", "revisions", "last_step", "lines"]) assert.ok(project[key], key);
  assert.ok(project.status.enum.includes("ready") && project.status.enum.includes("working"));
  assert.ok(get.inputSchema.properties.project && get.inputSchema.properties.cancel);
  for (const op of ["trim", "mux", "extract_audio", "voice_change", "text_cards", "music", "persona"])
    assert.ok(pinned.get("make_video_step").inputSchema.properties.op.enum.includes(op), op);
});

test("project-call / step-call / edit-call / finish-call 生成的入参通过钉住的 schema，幂等键稳定", async (t) => {
  const run = await newRun(t);
  const project = call(run, ["project-call", "--creator-video", "https://www.youtube.com/shorts/abc123", "--creator-name", "amy"]);
  assert.equal(project.status, 0, project.stderr);
  assert.equal(project.out.tool, "start_video_project");
  valid("start_video_project", project.out.arguments);
  assert.match(project.out.arguments.idempotency_key, /^remake-viral-video:[^:]+:start_video_project:[0-9a-f]{16}:a1$/);
  for (const args of [
    // 无人出镜参考改走项目：参考进 reference_video_urls
    ["--instagram-handle", "amy", "--reference-video", "https://www.tiktok.com/@brand/video/7412345678901234567"],
    // 不含本人的生成视频：项目里没有创作者
    [],
    // 只有照片 + 产品图
    ["--creator-photo", "https://example.com/me.jpg", "--creator-name", "me", "--reference-image", "https://example.com/p.png"],
    // 往已有项目追加素材
    ["--job-id", JOB, "--reference-image", "https://example.com/p2.png"],
  ]) {
    const res = call(run, ["project-call", ...args]);
    assert.equal(res.status, 0, `${args.join(" ")}: ${res.stderr}`);
    valid("start_video_project", res.out.arguments);
  }
  for (const [args, message] of [
    [["--job-id", JOB], /at least one/],
    [["--job-id", JOB, "--instagram-handle", "amy", "--reference-image", "https://example.com/p.png"], /only --creator-photo/],
    [["--creator-video", "https://www.youtube.com/shorts/abc123", "--creator-name", "amy", "--reference-video", "https://youtu.be/abc123"], /also a creator video/],
    [["--reference-image", "file:///etc/passwd"], /--reference-image must be a public http/],
    [["--creator-photo", "https://example.com/me.jpg"], /--creator-name is required/],
  ]) {
    const res = call(run, ["project-call", ...args]);
    assert.notEqual(res.status, 0, args.join(" "));
    assert.match(res.stderr, message);
  }

  const steps = {
    frame: { op: "frame", inputs: { video: "creator/clip1.mp4" }, params: { t: 2.5 } },
    motion: { op: "motion", inputs: { image: "a01.png", video: "a02.mp4" }, params: { model: "fal-ai/kling-video/v3/pro/motion-control" } },
    tts: { op: "tts", inputs: {}, params: { lines: ["Hello there."] } },
    cards: { op: "text_cards", inputs: { base: "a03.mp4" }, params: { cards: [{ text: "Step one", t0: 0, t1: 2 }], style: "plain" } },
    refvideo: { op: "refvideo", inputs: { images: ["a01.png", "input/img_01.png"] }, params: { prompt: "She waters the plants.", duration: 5 } },
    trim: { op: "trim", inputs: { media: "input/ref_01.mp4" }, params: { t0: 0, t1: 4.5 } },
    mux: { op: "mux", inputs: { video: "a05.mp4", audio: "a06.wav" }, params: { mode: "replace" } },
    extract: { op: "extract_audio", inputs: { video: "input/ref_01.mp4" }, params: {} },
    voice: { op: "voice_change", inputs: { media: "a06.wav" }, params: { voice: "creator" } },
    preset: { op: "tts", inputs: {}, params: { lines: ["Hi."], voice: "536d3a5e000945adb7038665781a4aca" } },
    persona: { op: "persona", inputs: {}, params: { description: "an invented man in his twenties, curly hair, green hoodie", seed_images: ["input/img_01.png"] } },
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
    [{ op: "tts", inputs: {}, params: { lines: ["Hi."], voice: "someone-else" } }, /stock voices/],
    [{ op: "persona", inputs: {}, params: { description: "looks exactly like @somecelebrity" } }, /invented person/],
    [{ op: "persona", inputs: {}, params: { description: "a presenter", seed_images: ["creator/creator-1.jpg"] } }, /not of a real person/],
    [{ op: "persona", inputs: {}, params: {} }, /needs params description/],
    [{ op: "mux", inputs: { video: "a01.mp4", audio: "a02.wav" }, params: { mode: "replace", gain_db: 9 } }, /-30 to 6/],
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
def project(status, step=None, revisions=(), spend=None):
    return {"job_id": JOB, "status": "delivered", "project": {"job_id": JOB, "status": status, "kind": "project",
            "retry_after_s": None, "message": None, "handles": [], "revisions": list(revisions), "last_step": step,
            "spend_usd": spend, "failure_reason": None}}
def step(op, handle=None, body=None, ctype=None, **extra):
    base = {"op": op, "status": "done", "spend_usd": 0, "model": None, "fallback_from": None, "face": None,
            "error": None, "message": None, "notes": None, "output": None}
    if handle:
        base["output"] = {"handle": handle, "file": {"download": descriptor(handle.replace("/", "_"), body, ctype)}}
    base.update(extra)
    return base
frame = step("frame", "a01.png", png, "image/png")
saved = host.fetch_step(run, project("ready", frame))
out["step"] = [saved["saved"], os.path.relpath(saved["path"], run), saved["handle"], saved["type"]]
out["step_again"] = host.fetch_step(run, project("ready", frame))["status"]
motion = step("motion", "a02.mp4", mp4, "video/mp4", spend_usd=4.1, model="fal-ai/kling-video/v3/pro/motion-control",
              fallback_from="alibaba/wan-3.0/reference-to-video", face={"verdict": "degraded", "median": 0.5, "p10": 0.4})
# the step tools return the project object at the top level
top = project("ready", motion)["project"]
saved = host.fetch_step(run, top)
out["face"] = [saved["face"], saved["fallback_from"], saved["spend_usd"]]
try:
    host.fetch_step(run, project("working", dict(motion, status="running", output=None)))
except ValueError as error:
    out["running"] = str(error)[:30]
out["failed"] = host.fetch_step(run, project("ready", step("refvideo", status="failed", error="provider_refused",
                                                           message="The provider refused the picture.")))
wrong = step("frame", "a03.png", mp4, "image/png")
try:
    host.fetch_step(run, project("ready", wrong))
except ValueError as error:
    out["wrong_type"] = str(error)[:80]
out["wrong_left_nothing"] = not (run / "project/outputs/a03.png").exists()
try:
    host.fetch_step(run, {"job_id": JOB, "status": "delivered"})
except ValueError as error:
    out["no_project"] = str(error)[:160]
# an edit: the newest revision is saved next to the first delivery
first = host.fetch_video(run, {"job_id": JOB, "status": "delivered", "video": {"download": descriptor("final.mp4", mp4, "video/mp4")}})
mp4b = mp4 + b"1"
rev = lambda n, body: {"n": n, "created_at": "2026-11-04T00:00:00Z", "notes": f"Revision {n}: line 2 re-voiced; nothing else changed.",
                       "handle": f"final_r{n}.mp4", "video": {"download": descriptor(f"final_r{n}.mp4", body, "video/mp4")}}
edited = host.fetch_revision(run, project("delivered", step("edit", face={"verdict": "pass", "median": 0.8, "p10": 0.7}),
                                          [rev(1, mp4b), rev(2, mp4b + b"2")], spend=0.4))
out["video"] = [os.path.relpath(first["path"], run), os.path.relpath(edited["path"], run), edited["revision"],
                edited["revision_notes"], edited["last_step"]["face"]]
print(json.dumps(out))
`;

test("fetch-step 存下一步的产物并转述花费、回退模型与人脸结论；fetch-revision 把最新修订版另存", async (t) => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-remake-atoms-fetch-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const res = spawnSync("python3", ["-I", "-c", PY, scripts, temp], { encoding: "utf8" });
  assert.equal(res.status, 0, res.stderr);
  const out = JSON.parse(res.stdout);
  assert.deepEqual(out.step, ["step", "project/outputs/a01.png", "a01.png", "image"]);
  assert.equal(out.step_again, "already_saved");
  assert.deepEqual(out.face, ["degraded", "alibaba/wan-3.0/reference-to-video", 4.1]);
  assert.match(out.running, /still running/);
  assert.equal(out.failed.saved, null);
  assert.equal(out.failed.error, "provider_refused");
  assert.equal(out.failed.step_status, "failed");
  assert.match(out.no_project, /"project": true/);
  assert.match(out.wrong_type, /declared image type/);
  assert.equal(out.wrong_left_nothing, true);
  assert.deepEqual(out.video, ["output/remake-11111111.mp4", "output/remake-11111111-r2.mp4", 2,
    "Revision 2: line 2 re-voiced; nothing else changed.", "pass"]);
});

test("G8：description 只在要成片或改成片时触发，写稿、拆解、账号诊断不触发，且不超过 500 字符", async () => {
  const text = await readFile(path.join(root, "skills/remake-viral-video/SKILL.md"), "utf8");
  const description = /^description: "(.*)"$/m.exec(text)[1];
  assert.ok(description.length <= 500, String(description.length));
  assert.match(description, /only when the user wants the video itself made or changed/);
  assert.match(description, /not for writing or adapting a script, breaking down a video, or reviewing an account/);
});
