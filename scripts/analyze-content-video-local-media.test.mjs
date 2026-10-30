import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

// analyze-content-video 的本地视频与「媒体拿不全」路径：移植自 creator-skills analyze-content-video 0.14.29。
// 证据构建用录好的产物跑真实 CLI 并过 schema；真实抽帧需要 ffmpeg，缺了就跳过。
const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills/analyze-content-video/scripts");
const options = { encoding: "utf8", maxBuffer: 16 * 1024 * 1024, timeout: 600_000 };
// 脚本按自身目录导入同目录模块，不能用 -I（它会去掉脚本目录）。
const python = (args) => execFileSync("python3", ["-B", ...args], options);
const hasFfmpeg = ["ffmpeg", "ffprobe"].every((tool) => spawnSync(tool, ["-version"]).status === 0);
// 宿主把运行目录拷回时只收这种文件名（Kabo agent 沙箱的收集规则）。
const REPLAYABLE = /^\.?[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$/;

async function workspace(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-local-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  await mkdir(path.join(temp, "analysis"));
  return temp;
}

const ajv = new Ajv2020({ allErrors: true, strict: false, logger: false });
const schema = ajv.compile(JSON.parse(await readFile(
  path.join(root, "skills/analyze-content-video/references/content-evidence.schema.json"), "utf8")));

const REQUEST = {
  schema_version: "video-analysis-request.v1", request_id: "var-yt-TbLcaf5I0LE",
  source: { acquisition: "public_url", subject_state: "third_party", platform: "youtube",
            url: "https://www.youtube.com/watch?v=TbLcaf5I0LE", content_id: "TbLcaf5I0LE",
            file_ref: null, declared_format: "short", owner_data: null },
  acquire: { transcript_language: "en" },
};
const localRequest = (temp) => ({
  ...REQUEST,
  source: { ...REQUEST.source, acquisition: "local_file", subject_state: "own_unpublished", url: null,
            content_id: null, file_ref: path.join(temp, "cut-v3.mp4") },
});

function envelope(operation, data, n) {
  return {
    schema_version: "1.0", connector_id: "public-video-media", operation, provider: "Kabo",
    status: "completed", summary: "", limitations: [], credential_values_recorded: false, data,
    request_id: `req-${operation}-${n}`, retrieved_at: "2026-09-15T09:59:00.000Z",
    raw_sha256: n.toString(16).padStart(64, "0"),
  };
}
const PLAN = { base_interval_s: 1.0, hook_window_s: 3.0, hook_dense_window_s: 3.0, hook_interval_s: 0.5,
  hook_frames: 7, body_interval_s: 1.017, body_frames: 56, budget: 600, frames: 63,
  body_degraded: false, note: "Opening 3s sampled every 0.5s.", closing_frame_s: 59.867 };
const FRAMES_DATA = { frame_count: 2, selection: "duration_scaled_v1", duration_s: 59.967, sampling_plan: PLAN,
  frames: [
    { frame_id: "frame-0001", t_seconds: 0.0, object_ref: "gs://kabo/keyframes/a/0001.jpg", sha256: "a".repeat(64), bytes: 10 },
    { frame_id: "frame-0002", t_seconds: 0.5, object_ref: "gs://kabo/keyframes/a/0002.jpg", sha256: "b".repeat(64), bytes: 10 },
  ], artifacts: [] };
const CAPTIONS = envelope("fetch_transcript", { cues: [
  { start_ms: 199, end_ms: 2100, text: "behind me is what $8,400 can get you in" },
  { start_ms: 4017, end_ms: 6000, text: "and it is not what you think" },
], cue_count: 2, origin: "platform_captions", artifacts: [] }, 2);

function localMedia(signals) {
  const media = { duration_s: 59.833, width: 1080, height: 1920, has_audio: true,
    encoding: { video_codec: "h264", frame_rate: "30/1", audio_codec: "aac" } };
  if (signals) media.signals = signals;
  return {
    schema_version: "local-media-extraction.v1", media_path: "cut-v3.mp4", content_id: "cut-v3",
    input_sha256: "sha-of-the-master",
    steps: [
      { step: "local_extraction", operation: "probe_media", tool: "ffprobe", tool_version: "ffprobe version 8.1.2",
        invocation_sha256: "inv-probe", started_at: "2026-09-20T04:00:00+00:00", status: "completed" },
      { step: "local_extraction", operation: "extract_keyframes", tool: "ffmpeg", tool_version: "ffmpeg version 8.1.2",
        invocation_sha256: "inv-frames", started_at: "2026-09-20T04:00:05+00:00", status: "completed" },
    ],
    media,
    frames: {
      status: "available", selection: "duration_scaled_v1",
      sampling_plan: { ...PLAN, body_interval_s: 1.015, closing_frame_s: 59.733, note: "Sampled on this machine." },
      items: [
        { frame_id: "cut-v3#frame-001-0.000s.jpg", t_seconds: 0.0, sha256: "a".repeat(64), bytes: 10,
          retained_outside_git: true, path: "frames/frame-1.jpg" },
        { frame_id: "cut-v3#frame-008-4.015s.jpg", t_seconds: 4.015, sha256: "b".repeat(64), bytes: 10,
          retained_outside_git: true, path: "frames/frame-8.jpg" },
      ],
      skipped: [],
    },
    limitations: [],
  };
}
const localTranscript = (origin) => ({
  schema_version: "local-transcript.v1", status: "available", granularity: "timestamped",
  source_file_name: "host-transcript.srt", source_file_sha256: "sha-of-the-srt", language: "en", origin,
  cues: [{ start_s: 0.199, text: "behind me is what $8,400 buys" }, { start_s: 4.017, text: "and it is not what you think" }],
  steps: [{ step: "local_extraction", operation: "read_subtitle_file", tool: "read_subtitle_file",
            tool_version: "local-transcript.v1", invocation_sha256: "inv-subtitle", input_sha256: "sha-of-the-srt",
            started_at: "2026-09-20T04:00:00+00:00", status: "completed" }],
});

async function build(temp, name, request, { envelopes = [], localMediaArtifact, localTranscriptArtifact } = {}) {
  const requestFile = path.join(temp, "analysis", `${name}-request.json`);
  await writeFile(requestFile, JSON.stringify(request));
  const args = [path.join(scripts, "build_content_evidence.py"), "--request", requestFile];
  for (const [i, document] of envelopes.entries()) {
    const file = path.join(temp, `${name}-envelope-${i}.json`);
    await writeFile(file, JSON.stringify(document));
    args.push("--envelope", file);
  }
  for (const [flag, document] of [["--local-media", localMediaArtifact], ["--local-transcript", localTranscriptArtifact]]) {
    if (!document) continue;
    const file = path.join(temp, "analysis", `${name}${flag}.json`);
    await writeFile(file, JSON.stringify(document));
    args.push(flag, file);
  }
  const output = path.join(temp, "analysis", `${name}-evidence.json`);
  python([...args, "--output", output]);
  const evidence = JSON.parse(await readFile(output, "utf8"));
  assert.ok(schema(evidence), `${name}：${JSON.stringify(schema.errors)}`);
  return evidence;
}

test("ACV 证据：关键帧结果带的 signals 进 media.probed，文件结尾未闭合的静音段按时长补齐", async (t) => {
  const temp = await workspace(t);
  const signals = { duration_s: 59.967, measured: ["shots", "silence"], unavailable: [],
    shots: { count: 1, cuts_at_s: [], shots: [] },
    silence: { floor_db: -40, min_s: 0.5, spans: [{ start_s: 58.0, end_s: null, duration_s: null }] } };
  const carried = envelope("extract_keyframes_hosted_stream", { ...FRAMES_DATA, signals }, 3);
  const evidence = await build(temp, "carried", REQUEST, { envelopes: [CAPTIONS, carried] });
  const probed = evidence.media.probed;
  assert.deepEqual(probed.measured, ["shots", "silence"]);
  assert.equal(probed.silence.spans[0].end_s, 59.967);
  assert.equal(probed.silence.spans[0].duration_s, 1.967);

  // 单独的测量结果到了就以它为准：那是专门要的那次调用。
  const measured = envelope("measure_media_signals", { duration_s: 59.967, measured: ["shots"], unavailable: ["silence", "freeze"],
    shots: { count: 2, cuts_at_s: [3.0], shots: [] } }, 4);
  const both = await build(temp, "both", REQUEST, { envelopes: [CAPTIONS, carried, measured] });
  assert.deepEqual(both.media.probed.shots.cuts_at_s, [3.0]);
  assert.deepEqual(both.media.probed.unavailable, ["silence", "freeze"]);
});

test("ACV 证据：YouTube 测量以托管变体名 measure_media_signals_hosted_stream 回来时仍按测量读入", async (t) => {
  const temp = await workspace(t);
  const hosted = envelope("measure_media_signals_hosted_stream", { duration_s: 59.967, measured: ["shots"], unavailable: [],
    shots: { count: 2, cuts_at_s: [4.0], shots: [] } }, 5);
  const evidence = await build(temp, "hosted", REQUEST, { envelopes: [CAPTIONS, hosted] });
  assert.deepEqual(evidence.media.probed.shots.cuts_at_s, [4.0]);
});

test("ACV 证据：本地抽帧时测的 signals 与连接器结果走同一个 probed 过滤", async (t) => {
  const temp = await workspace(t);
  const evidence = await build(temp, "local", localRequest(temp), { localMediaArtifact: localMedia({
    duration_s: 59.833, measured: ["shots", "silence"], unavailable: ["freeze"],
    shots: { count: 2, cuts_at_s: [3.0], shots: [
      { index: 0, start_s: 0.0, end_s: 3.0, duration_s: 3.0 },
      { index: 1, start_s: 3.0, end_s: 59.833, duration_s: 56.833 }] },
    silence: { floor_db: -40, min_s: 0.5, spans: [{ start_s: 57.0, end_s: 59.833, duration_s: 2.833 }] },
  }) });
  assert.deepEqual(evidence.media.probed.shots.cuts_at_s, [3.0]);
  assert.equal(evidence.media.probed.silence.spans[0].start_s, 57.0);
  assert.deepEqual(evidence.media.probed.unavailable, ["freeze"]);

  const plain = await build(temp, "plain", localRequest(temp), { localMediaArtifact: localMedia() });
  assert.equal(plain.media.probed, undefined);
});

test("ACV 证据：宿主机器转写的字幕记为 speech_recognition，不冒充创作者原话", async (t) => {
  const temp = await workspace(t);
  const heard = await build(temp, "heard", localRequest(temp), {
    localMediaArtifact: localMedia(), localTranscriptArtifact: localTranscript("speech_recognition") });
  assert.equal(heard.transcript.origin, "speech_recognition");
  assert.match(heard.transcript.status_basis, /by machine/);
  const supplied = await build(temp, "supplied", localRequest(temp), {
    localMediaArtifact: localMedia(), localTranscriptArtifact: localTranscript("creator_supplied") });
  assert.equal(supplied.transcript.origin, "creator_supplied");
});

test("ACV read_subtitle_file：--origin 写进产物，缺省仍是 creator_supplied", async (t) => {
  const temp = await workspace(t);
  const srt = path.join(temp, "host-transcript.srt");
  await writeFile(srt, "1\n00:00:00,199 --> 00:00:02,100\nbehind me is what it buys\n\n2\n00:00:04,017 --> 00:00:06,000\nand it is not what you think\n");
  const read = (name, extra) => {
    const artifact = path.join(temp, "analysis", name);
    python([path.join(scripts, "read_subtitle_file.py"), "--subtitle", srt, "--artifact", artifact, ...extra]);
    return readFile(artifact, "utf8").then(JSON.parse);
  };
  assert.equal((await read("heard.json", ["--origin", "speech_recognition"])).origin, "speech_recognition");
  assert.equal((await read("default.json", [])).origin, "creator_supplied");
});

test("ACV extract_local_frames：先写开头、再写结尾、正文由粗到细；帧文件名是 id 的哈希", () => {
  const probe = String.raw`
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("extract_local_frames", sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
frame_id = module.frame_identifier("测试 #稿(1)", 3, 1.5)
print(json.dumps({"order": module.extraction_order(20, 7), "id": frame_id,
                  "name": module.frame_file_name(frame_id),
                  "other": module.frame_file_name(module.frame_identifier("other", 3, 1.5))}))
`;
  const out = JSON.parse(python(["-c", probe, path.join(scripts, "extract_local_frames.py")]));
  assert.deepEqual(out.order.slice(0, 7), [0, 1, 2, 3, 4, 5, 6]);
  assert.equal(out.order[7], 19);
  assert.deepEqual([...out.order].sort((a, b) => a - b), [...Array(20).keys()]);
  const bodyFirst = out.order.slice(8, 11);
  assert.ok(Math.max(...bodyFirst) - Math.min(...bodyFirst) > 5, "正文先写的几帧应铺开整段，而不是挤在开头");
  assert.match(out.id, /#frame-003-1\.500s/);
  assert.match(out.name, REPLAYABLE);
  assert.notEqual(out.name, out.other);
});

test("ACV extract_local_frames：真实抽帧缩到 720 长边、文件名可回放、字节预算保住开头", { skip: !hasFfmpeg && "需要 ffmpeg/ffprobe" }, async (t) => {
  const temp = await workspace(t);
  const media = path.join(temp, "测试 #稿(1).mp4");
  execFileSync("ffmpeg", ["-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
    "-i", "testsrc2=duration=4:size=1920x1080:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", media], options);
  const artifact = path.join(temp, "analysis/named.json");
  python([path.join(scripts, "extract_local_frames.py"), "--media", media,
    "--out-dir", path.join(temp, "analysis/named"), "--artifact", artifact]);
  const document = JSON.parse(await readFile(artifact, "utf8"));
  assert.ok(document.frames.items.length > 0);
  for (const item of document.frames.items) {
    assert.ok(item.frame_id.startsWith("测试 #稿(1)#frame-"), item.frame_id);
    assert.match(path.basename(item.path), REPLAYABLE);
  }
  const width = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
    "-of", "csv=p=0", path.join(path.dirname(artifact), document.frames.items[0].path)], options).trim();
  assert.equal(width, "720");

  // 一个字节的预算只放得下第一张写出的帧，也就是开头那张。
  const budget = path.join(temp, "analysis/budget.json");
  python([path.join(scripts, "extract_local_frames.py"), "--media", media, "--base-interval-s", "0.25",
    "--out-dir", path.join(temp, "analysis/budget"), "--artifact", budget, "--max-total-bytes", "1"]);
  const thinned = JSON.parse(await readFile(budget, "utf8"));
  assert.deepEqual(thinned.frames.items.map((item) => item.t_seconds), [0]);
  const note = thinned.limitations.find((text) => /byte budget/.test(text));
  assert.ok(note);
  // 预算在开头就用完了：不能说开头和结尾都看过。
  assert.match(note, /Not all of the opening and closing frames were written/);
  assert.doesNotMatch(note, /are whole/);
});

test("ACV extract_local_frames --measure-signals：剪辑点与停顿按连接器形状落在 media.signals，并进入证据", { skip: !hasFfmpeg && "需要 ffmpeg/ffprobe" }, async (t) => {
  const temp = await workspace(t);
  const media = path.join(temp, "cut-v3.mp4");
  execFileSync("ffmpeg", ["-nostdin", "-hide_banner", "-loglevel", "error", "-y",
    "-f", "lavfi", "-i", "color=c=red:size=160x120:duration=3:rate=10",
    "-f", "lavfi", "-i", "testsrc=size=160x120:duration=3:rate=10",
    "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
    "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a][4:a]concat=n=3:v=0:a=1[a]",
    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", media], options);
  const artifact = path.join(temp, "analysis/local-media.json");
  const summary = JSON.parse(python([path.join(scripts, "extract_local_frames.py"), "--media", media, "--measure-signals",
    "--out-dir", path.join(temp, "analysis/frames"), "--artifact", artifact]));
  const document = JSON.parse(await readFile(artifact, "utf8"));
  const signals = document.media.signals;
  assert.deepEqual(signals.measured, ["shots", "silence", "freeze"]);
  assert.equal(signals.shots.count, 2);
  assert.ok(Math.abs(signals.shots.cuts_at_s[0] - 3.0) <= 0.2);
  assert.ok(Math.abs(signals.silence.spans[0].start_s - 2.0) <= 0.2);
  for (const span of [...signals.silence.spans, ...signals.freeze.spans])
    assert.equal(typeof span.end_s, "number");
  assert.equal(summary.signals.shots, 2);

  const evidence = await build(temp, "measured", localRequest(temp), { localMediaArtifact: document });
  assert.equal(evidence.media.probed.shots.count, 2);
});
