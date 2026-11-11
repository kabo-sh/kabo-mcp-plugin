// 视频分析的媒体证据是一次后台组合调用 collect_video_media（KS9）：collect_media.py 只交出一行 call:；还有 job
// 在跑时续跑再交同一个调用；全部终态后逐项 persist 成 snapshot/envelope-NN.json，打印证据构建的 --envelope 参数和
// 一次读帧。这里不联网：组合结果按后台对这组入参会给出的形状手写，走「没有下载链接」的退路落盘。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "analyze-content-video", "scripts");

function python(script, args, { cwd, run } = {}) {
  const result = spawnSync("python3", [path.join(scripts, script), ...args], {
    cwd, encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(run ? { KABO_STATIC_RUN_DIR: run } : {}) },
  });
  return { code: result.status, out: result.stdout + result.stderr };
}
function shell(command) {
  const result = spawnSync("bash", ["-c", command], { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return { code: result.status, out: result.stdout + result.stderr };
}
const calls = (out) => out.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));
const reads = (out) => out.split("\n").filter((line) => line.startsWith("read: ")).map((line) => JSON.parse(line.slice(6)));
const saveOf = (out) => out.split("\n").find((line) => line.startsWith("  result ")).split("has no download url: ")[1].slice(0, -1);
const resumeOf = (out) => { const line = out.split("\n").find((l) => l.startsWith("Then run this one command")); return line.slice(line.indexOf("cd '")).replace(/ --id=<id>$/, ""); };

const URL_ = "https://www.youtube.com/watch?v=fixture0001";
const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
function mediaEnvelope(request, jobId) {
  const base = {
    schema_version: "1.0", connector_id: "public-video-media", provider: "fixture", status: "completed", summary: "ok",
    limitations: [], credential_values_recorded: false, job_id: jobId, evidence_ref: `ev-${jobId}`, raw_sha256: jobId.replace(/-/g, "").padEnd(64, "a"),
    request_id: `req-${jobId}`, retrieved_at: "2026-11-06T00:00:00Z", observation_refs: [],
  };
  if (request.operation === "fetch_transcript")
    return { ...base, operation: "fetch_transcript", data: { cues: [{ text: "Here is the one thing you need.", start_ms: 0, end_ms: null }], origin: "speech_recognition", cue_count: 1,
      artifacts: [{ kind: "transcript", bytes: 10, sha256: "b".repeat(64), object_ref: `creator-media/${jobId}/epoch-1/transcript.json` }] } };
  if (request.operation === "measure_media_signals")
    return { ...base, operation: "measure_media_signals_hosted_stream", data: { shots: [], artifacts: [] } };
  const frames = [0, 0.5, 1].map((t, i) => ({ bytes: 100, sha256: "c".repeat(64), frame_id: `frame-${String(i + 1).padStart(4, "0")}`, t_seconds: t,
    object_ref: `creator-media/${jobId}/epoch-1/frame-${String(i + 1).padStart(4, "0")}.jpg` }));
  return { ...base, operation: "extract_keyframes_hosted_media", data: { frames, artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
    selection: "duration_scaled_v1", duration_s: 30, frame_count: frames.length } };
}
const TOOLS = { fetch_transcript: "public_video_fetch_transcript", extract_keyframes: "public_video_extract_keyframes_hosted_media",
  measure_media_signals: "public_video_measure_media_signals" };
function composite(args, pendingGroups = new Set()) {
  const jobs = [], list = [], unfinished = [];
  args.requests.forEach((request, index) => {
    const group = `${request.content_id}/${request.operation}`;
    const jobId = uuid(index + 1);
    const pending = pendingGroups.has(group);
    jobs.push({ group, content_id: request.content_id, operation: request.operation, attempt: 1, job_id: jobId, status: pending ? "running" : "completed" });
    if (pending) { unfinished.push(group); return; }
    list.push({ tool: TOOLS[request.operation], parameters: request.parameters, group, attempts: 1, result: mediaEnvelope(request, jobId) });
  });
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_video_media", status: unfinished.length ? "partial" : "completed", calls: list,
    summary: { requests: jobs.length, pending: unfinished.length, jobs },
    coverage: { deadline_reached: unfinished.length > 0, unfinished, provider_calls: 0, pending: unfinished.length }, limitations: [] };
}
const save = (file, result) => writeFile(file, JSON.stringify({ content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result }));

test("视频分析媒体一次组合调用：交接一个 call，续跑等到终态，逐项落成 envelope-NN 并打印读帧", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-media-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const init = python("static_host.py", ["init", "--workspace", workspace]);
  assert.equal(init.code, 0, init.out);
  const run = init.out.trim();
  if (process.env.KEEP) console.log("RUN=" + run);

  const first = python("collect_media.py", ["--url", URL_, "--operations", "transcript,keyframes,measure"], { cwd: run, run });
  assert.equal(first.code, 0, first.out);
  const handed = calls(first.out);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].tool, "collect_video_media");
  const args = handed[0].arguments;
  assert.equal(args.delivery, "download");
  assert.match(args.run_key, /^acv:[0-9a-f]{32}$/);
  assert.deepEqual(args.requests.map((r) => r.operation), ["fetch_transcript", "extract_keyframes", "measure_media_signals"]);
  const keyframes = args.requests.find((r) => r.operation === "extract_keyframes");
  assert.deepEqual(keyframes.parameters, { url: URL_, sampling: "duration_scaled", max_frames: 60 });

  // 还有 job 在跑：续跑再交同一个调用。
  await save(saveOf(first.out), composite(args, new Set(["video/extract_keyframes"])));
  const second = shell(resumeOf(first.out));
  assert.equal(second.code, 0, second.out);
  assert.match(second.out, /1 media job\(s\) are still running/);
  assert.deepEqual(calls(second.out)[0].arguments, args);

  const final = composite(args);
  await save(saveOf(second.out), final);
  const third = shell(resumeOf(second.out));
  assert.equal(third.code, 0, third.out);
  assert.match(third.out, /"status": "collected"/);
  for (const [index, call] of final.calls.entries()) {
    const placed = JSON.parse(await readFile(path.join(run, `snapshot/envelope-${String(index + 1).padStart(2, "0")}.json`), "utf8"));
    assert.equal(placed.job_id, call.result.job_id);
    assert.equal(placed.operation, call.result.operation);
  }
  assert.match(third.out, /--envelope snapshot\/envelope-01\.json --envelope snapshot\/envelope-02\.json --envelope snapshot\/envelope-03\.json/);
  const frameReads = reads(third.out);
  assert.equal(frameReads.length, 1);
  assert.equal(frameReads[0].arguments.job_id, uuid(2));
  assert.equal(frameReads[0].arguments.object_refs.length, 3);
  // 读帧把图片直接给了模型就算看过：不要求逐帧暂存（Web 上 59 帧就是 59 步，超出每轮步数）。
  assert.match(third.out, /If its result shows you the images, they are viewed: do not save or stage them/);
  assert.match(first.out, / --id=<id>$/m);

  // 没有暂存任何帧字节：builder 照样按 keyframes 信封列出全部帧，测量依据行照常生成。
  const request = path.join(run, "analysis/video-analysis-request.json");
  await writeFile(request, JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-frames",
    source: { acquisition: "public_url", subject_state: "unknown", platform: "youtube", url: URL_, content_id: "fixture0001", declared_format: "video", owner_data: null },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 10, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] },
  }));
  const built = shell(`cd '${run}' && python3 '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
    + "--envelope snapshot/envelope-01.json --envelope snapshot/envelope-02.json --envelope snapshot/envelope-03.json "
    + "--snapshot-root snapshot --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json");
  assert.equal(built.code, 0, built.out);
  const evidence = JSON.parse(await readFile(path.join(run, "analysis/content_evidence.json"), "utf8"));
  assert.equal(evidence.frames.status, "available");
  assert.equal(evidence.frames.origin, "extracted_frames");
  assert.equal(evidence.frames.items.length, 3);
  const basis = spawnSync("python3", ["-c", "import json,sys; sys.path.insert(0, sys.argv[1]); import creator_measurement_basis as m; "
    + "print(json.dumps(m.measurement_basis(json.load(open(sys.argv[2])), {}, {})))", scripts, path.join(run, "analysis/content_evidence.json")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  assert.equal(basis.status, 0, basis.stderr);
  assert.equal(JSON.parse(basis.stdout).frame_kind, "extracted");
});

test("collect_media.py：未知操作与超出上限的帧数直接拒绝，不交出调用", () => {
  const bad = python("collect_media.py", ["--url", URL_, "--operations", "frames"], { cwd: os.tmpdir() });
  assert.equal(bad.code, 1);
  assert.match(bad.out, /--operations takes/);
  assert.equal(calls(bad.out).length, 0);
});

test("collect_media.py：续跑时既没有结果编号、也没有暂存记录，报错说出先 stage 再续跑", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-media-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const run = python("static_host.py", ["init", "--workspace", workspace]).out.trim();
  const first = python("collect_media.py", ["--url", URL_, "--operations", "transcript,keyframes,measure"], { cwd: run, run });
  assert.equal(first.code, 0, first.out);
  const resumed = shell(resumeOf(first.out));
  assert.equal(resumed.code, 1, resumed.out);
  assert.match(resumed.out, /no result for this hand-over/);
  assert.match(resumed.out, /static_host\.py stage --tool collect_video_media/);
});

// Web 宿主读交接的规则（kabo-agent-service src/tools/plugin-handover.ts 的 parsePluginHandover），照抄到这里：
// 读得懂，宿主就自己调用、把原样结果写进槽位文件、按续跑命令接着跑，模型不用经手暂存。
function hostHandover(stdout) {
  const lines = stdout.split("\n");
  const start = lines.findIndex((line) => line.startsWith("Hand-over: "));
  if (start < 0) return null;
  const words = (text) => {
    const out = []; let i = 0;
    while (i < text.length) {
      if (text[i] === " ") { i += 1; continue; }
      if (text[i] === "'") { const end = text.indexOf("'", i + 1); if (end < 0) return null; out.push(text.slice(i + 1, end)); i = end + 1; if (i < text.length && text[i] !== " ") return null; continue; }
      let end = text.indexOf(" ", i); if (end < 0) end = text.length;
      const word = text.slice(i, end); if (/["`\\]/.test(word)) return null; out.push(word); i = end;
    }
    return out;
  };
  const calls = [], files = []; let resume = null;
  for (const line of lines.slice(start + 1)) {
    const call = /^call: (\{.*\})\s*$/.exec(line);
    if (call) { calls.push(JSON.parse(call[1])); continue; }
    const slot = /^\s+result (\d+)\s+\(fallback file[^:]*: (\/\S+)\)\s*$/.exec(line);
    if (slot) { if (files.length !== calls.length - 1) return null; files.push(slot[2]); continue; }
    const tail = /^Then run this one command right away[^:]*\(ids expire[^)]*\): (.+)$/.exec(line);
    if (tail) {
      const w = words(tail[1].trim());
      if (!w || w[0] !== "cd" || w[2] !== "&&" || w[3] !== "python3") return null;
      const args = []; const rest = w.slice(5);
      for (let k = 0; k < rest.length; k += 1) { if (rest[k] === "--id") { k += 1; continue; } if (rest[k].startsWith("--id=")) continue; args.push(rest[k]); }
      resume = { cwd: w[1], script: w[4], args }; break;
    }
  }
  return resume && calls.length && files.length === calls.length ? { calls, files, resume } : null;
}

test("collect_media.py 的交接是 Web 宿主读得懂的写法：宿主写入原样结果、不带编号续跑，就能拿到媒体", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-media-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const run = python("static_host.py", ["init", "--workspace", workspace]).out.trim();
  const first = python("collect_media.py", ["--url", URL_, "--operations", "transcript,keyframes,measure"], { cwd: run, run });
  assert.equal(first.code, 0, first.out);
  const handover = hostHandover(first.out);
  assert.ok(handover, first.out);
  assert.equal(handover.calls.length, 1);
  assert.equal(handover.resume.cwd, run);
  assert.equal(path.basename(handover.resume.script), "collect_media.py");
  assert.ok(!handover.resume.args.includes("<id>"));
  // 宿主写的是研究工具的原样出参（没有 MCP 包装）。续跑命令不带环境变量；shell 里残留着另一个 run 的
  // KABO_STATIC_RUN_DIR 时，结果仍要落在 cd 进去的那个 run。
  const stray = python("static_host.py", ["init", "--workspace", workspace]).out.trim();
  assert.notEqual(stray, run);
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1", KABO_STATIC_RUN_DIR: stray };
  const resume = (current) => spawnSync("python3", [current.resume.script, ...current.resume.args], { cwd: current.resume.cwd, encoding: "utf8", env });
  const args = handover.calls[0].arguments;
  // 第一轮还有 job 在跑：再交的一轮同样要让宿主认得（说明单独一行，槽位编号换成 02）。
  await writeFile(handover.files[0], JSON.stringify(composite(args, new Set(["video/extract_keyframes"]))));
  const second = resume(handover);
  assert.equal(second.status, 0, second.stdout + second.stderr);
  assert.match(second.stdout, /1 media job\(s\) are still running/);
  const again = hostHandover(second.stdout);
  assert.ok(again, second.stdout);
  assert.deepEqual(again.calls[0].arguments, args);
  assert.match(path.basename(again.files[0]), /^02-/);
  await writeFile(again.files[0], JSON.stringify(composite(args)));
  const resumed = resume(again);
  assert.equal(resumed.status, 0, resumed.stdout + resumed.stderr);
  assert.match(resumed.stdout, /"status": "collected"/);
  assert.equal(reads(resumed.stdout).length, 1);
  await readFile(path.join(run, "snapshot/envelope-01.json"), "utf8");
  await assert.rejects(readFile(path.join(stray, "snapshot/envelope-01.json"), "utf8"));
});

// 只导出逐字稿（雨恬 11-10，生产 1.0.29）：只取转写、不取元数据，模型写的请求不带 content_id；
// 以前 build_content_evidence.py 报「content_ref needs a content_id」退出，转写拿到了也导不出来。
test("只导出逐字稿：请求不带 content_id 时从原始链接取，证据照常生成并导出 TXT/SRT", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-transcript-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const run = python("static_host.py", ["init", "--workspace", workspace]).out.trim();
  const REEL = "https://www.instagram.com/reel/DeZrE2phzDx/?igsh=share";
  const first = python("collect_media.py", ["--url", REEL, "--operations", "transcript"], { cwd: run, run });
  assert.equal(first.code, 0, first.out);
  const args = calls(first.out)[0].arguments;
  await save(saveOf(first.out), composite(args));
  const collected = shell(resumeOf(first.out));
  assert.equal(collected.code, 0, collected.out);
  assert.match(collected.out, /"status": "collected"/);
  await writeFile(path.join(run, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-transcript",
    source: { acquisition: "public_url", subject_state: "unknown", platform: "instagram", url: REEL, content_id: null, declared_format: "video", owner_data: null },
    acquire: { media: "skip", transcript: "required", frames: "skip", owner_metrics: "skip" },
    budget: { max_connector_calls: 4, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] },
  }));
  const built = shell(`cd '${run}' && python3 '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
    + "--envelope snapshot/envelope-01.json --snapshot-root snapshot --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json");
  assert.equal(built.code, 0, built.out);
  const evidence = JSON.parse(await readFile(path.join(run, "analysis/content_evidence.json"), "utf8"));
  assert.equal(evidence.content_ref.content_id, "DeZrE2phzDx");
  assert.equal(evidence.transcript.status, "available");
  const exported = shell(`cd '${run}' && python3 '${path.join(scripts, "export_transcript.py")}' analysis/content_evidence.json report/`);
  assert.equal(exported.code, 0, exported.out);
  assert.match(await readFile(path.join(run, "report/transcript.txt"), "utf8"), /Here is the one thing you need/);
});
