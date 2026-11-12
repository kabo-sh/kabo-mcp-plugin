import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// remake-viral-video 的本地文件：upload-call / upload 把本地视频或照片传到 upload_file 给的签名链接，
// 之后 kabo-file:<id> 可以放在任何收链接的位置。上传经进程内的假 HTTPS 处理器，测试不联网。
const root = fileURLToPath(new URL("..", import.meta.url));
const script = path.join(root, "skills/remake-viral-video/scripts/static_host.py");
const scripts = path.dirname(script);
const FILE = "0f8fad5b-d9cb-469f-a165-70867728950e";
const PHOTO = "7c9e6679-7425-40de-944b-e07fc1f90ae7";

function run() {
  const workspace = mkdtempSync(path.join(tmpdir(), "remake-upload-"));
  return execFileSync("python3", [script, "init", "--workspace", workspace], { encoding: "utf8" }).trim();
}

function call(dir, args) {
  return spawnSync("python3", [script, ...args], { encoding: "utf8", env: { ...process.env, KABO_STATIC_RUN_DIR: dir } });
}

test("kabo-file 引用可放在参考、本人视频与照片的位置，规范成小写；同一个文件不能两用", () => {
  const dir = run();
  const ok = call(dir, ["start-call", "--reference-url", `KABO-FILE:${FILE.toUpperCase()}`,
    "--creator-video", "https://www.instagram.com/reel/ABC123/", "--creator-photo", `kabo-file:${PHOTO}`,
    "--creator-name", "rose"]);
  assert.equal(ok.status, 0, ok.stderr);
  const args = JSON.parse(ok.stdout).arguments;
  assert.equal(args.reference_url, `kabo-file:${FILE}`);
  assert.deepEqual(args.creator.photo_urls, [`kabo-file:${PHOTO}`]);
  const same = call(dir, ["start-call", "--reference-url", `kabo-file:${FILE}`, "--creator-video", `kabo-file:${FILE}`,
    "--creator-name", "rose"]);
  assert.notEqual(same.status, 0);
  assert.match(same.stderr, /same video/);
  const project = call(dir, ["project-call", "--reference-video", `kabo-file:${FILE}`, "--reference-image", `kabo-file:${PHOTO}`]);
  assert.equal(project.status, 0, project.stderr);
  const parsed = JSON.parse(project.stdout).arguments;
  assert.deepEqual(parsed.reference_video_urls, [`kabo-file:${FILE}`]);
  assert.deepEqual(parsed.reference_image_urls, [`kabo-file:${PHOTO}`]);
  const bad = call(dir, ["start-call", "--reference-url", "kabo-file:not-a-uuid", "--instagram-handle", "rose"]);
  assert.notEqual(bad.status, 0);
  assert.match(bad.stderr, /kabo-file/);
});

test("upload-call：只收视频与 JPEG/PNG，文件名按内容摘要命名，幂等键绑定内容", () => {
  const dir = run();
  const media = mkdtempSync(path.join(tmpdir(), "remake-media-"));
  const video = path.join(media, "我的 秘密 名字.MOV");
  writeFileSync(video, Buffer.alloc(2048, 7));
  const first = call(dir, ["upload-call", "--file", video]);
  assert.equal(first.status, 0, first.stderr);
  const parsed = JSON.parse(first.stdout);
  assert.equal(parsed.tool, "upload_file");
  assert.match(parsed.arguments.filename, /^video-[0-9a-f]{16}\.mov$/);
  assert.equal(parsed.arguments.size_bytes, 2048);
  assert.equal(JSON.parse(call(dir, ["upload-call", "--file", video]).stdout).arguments.idempotency_key,
    parsed.arguments.idempotency_key);
  writeFileSync(video, Buffer.alloc(2048, 8));
  assert.notEqual(JSON.parse(call(dir, ["upload-call", "--file", video]).stdout).arguments.idempotency_key,
    parsed.arguments.idempotency_key);
  const gif = path.join(media, "a.gif");
  writeFileSync(gif, "GIF89a");
  const refused = call(dir, ["upload-call", "--file", gif]);
  assert.notEqual(refused.status, 0);
  assert.match(refused.stderr, /JPEG \/ PNG/);
});

const PY = String.raw`
import http.client, importlib.util, io, json, os, sys, urllib.request, urllib.response, urllib.error
sys.dont_write_bytecode = True
scripts, workspace, media = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("static_host", os.path.join(scripts, "static_host.py"))
host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
calls, plan = [], {}
class FakeHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        body = req.data.read() if hasattr(req.data, "read") else req.data
        calls.append({"method": req.get_method(), "url": req.full_url, "headers": {k.lower(): v for k, v in req.header_items()},
                      "bytes": len(body or b"")})
        code, headers = plan[(req.get_method(), req.full_url)]
        message = http.client.parse_headers(io.BytesIO("".join(f"{k}: {v}\r\n" for k, v in headers.items()).encode() + b"\r\n"))
        if code >= 400:
            raise urllib.error.HTTPError(req.full_url, code, "fake", message, io.BytesIO(b""))
        response = urllib.response.addinfourl(io.BytesIO(b""), message, req.full_url, code)
        response.msg = "fake"
        return response
host.build_opener = lambda: urllib.request.build_opener(host.NoRedirect(), FakeHTTPS())
run = host.init(workspace)
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
FILE = "${FILE}"
video = os.path.join(media, "clip.mp4")
open(video, "wb").write(b"x" * 5000)
signed = "https://storage.googleapis.com/kabo-user-files/u/f?X-Goog-Signature=abc"
session = "https://storage.googleapis.com/upload/storage/v1/b/kabo/o?upload_id=xyz"
headers = {"content-type": "video/mp4", "x-goog-resumable": "start", "x-goog-if-generation-match": "0"}
def result(status="upload_required", url=signed, extra_headers=None, expires="2999-01-01T00:00:00Z"):
    return json.dumps({"structuredContent": {"file_id": FILE, "status": status,
        "upload": None if status == "ready" else {"method": "POST", "url": url, "headers": {**headers, **(extra_headers or {})},
                                                   "expires_at": expires}}}).encode()
out = {}
plan[("POST", signed)] = (201, {"Location": session})
plan[("PUT", session)] = (200, {})
out["uploaded"] = host.upload(result(), video)
out["calls"] = calls[:]
out["ready"] = host.upload(result("ready"), video)
def refused(raw):
    try:
        host.upload(raw, video)
        return None
    except ValueError as error:
        return str(error)
out["other_host"] = refused(result(url="https://evil.example/upload"))
out["extra_header"] = refused(result(extra_headers={"Authorization": "Bearer x"}))
out["expired"] = refused(result(expires="2000-01-01T00:00:00Z"))
plan[("POST", signed)] = (403, {})
out["forbidden"] = refused(result())
plan[("POST", signed)] = (201, {"Location": "https://evil.example/session"})
out["bad_session"] = refused(result())
print(json.dumps(out))
`;

test("upload：一次 POST 开会话、一次 PUT 传完整字节，只认签名存储链接与签名头", () => {
  const workspace = mkdtempSync(path.join(tmpdir(), "remake-upload-py-"));
  const media = mkdtempSync(path.join(tmpdir(), "remake-upload-media-"));
  const result = spawnSync("python3", ["-c", PY, scripts, workspace, media], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.uploaded.tool, "upload_file");
  assert.deepEqual(out.uploaded.arguments, { file_id: FILE });
  assert.equal(out.calls.length, 2);
  assert.equal(out.calls[0].method, "POST");
  assert.equal(out.calls[0].headers["x-goog-resumable"], "start");
  assert.equal(out.calls[0].bytes, 0);
  assert.equal(out.calls[1].method, "PUT");
  assert.equal(out.calls[1].bytes, 5000);
  assert.equal(out.ready.file_ref, `kabo-file:${FILE}`);
  assert.match(out.other_host, /not a Kabo signed storage link/);
  assert.match(out.extra_header, /headers other than the signed ones/);
  assert.match(out.expired, /expired/);
  assert.match(out.forbidden, /HTTP 403/);
  assert.match(out.bad_session, /Opening the upload failed/);
  for (const message of [out.forbidden, out.bad_session, out.other_host]) {
    assert.doesNotMatch(message, /Signature|evil\.example|upload_id/);
  }
});
