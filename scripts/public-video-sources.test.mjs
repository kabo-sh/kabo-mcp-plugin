// 单视频分析接受哪些平台，只看支持清单 public-video-sources.v1（kabo 生成，契约见共享规格）。
// contracts/ 下钉一份，analyze-content-video 的 references/ 下放逐字相同的副本（Skill 单独安装、Web 打包都带着它）；
// 脚本按它读平台、编号前缀、链接 id 与公开计数，schema 的平台枚举与它一致。这里不联网：信封按 collect_video_media
// 对抖音、Facebook 会给出的形状手写（与 acv-video-media.test.mjs 的 TikTok/YouTube 信封同一种写法）。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const skill = path.join(root, "skills", "analyze-content-video");
const scripts = path.join(skill, "scripts");
const readJson = async (file) => JSON.parse(await readFile(file, "utf8"));
const IDS = ["youtube", "instagram", "tiktok", "douyin", "xiaohongshu", "kuaishou", "facebook", "bilibili"];
const KEYS = new Set(["id", "label", "content_id_prefix", "page_hosts", "short_link_hosts", "url_patterns", "query_id_params",
  "canonical_url", "metadata_route", "public_metrics", "notes"]);
const METRICS = ["views", "likes", "comments", "shares", "saves"];

function python(args, { cwd = root } = {}) {
  const result = spawnSync("python3", ["-B", ...args], { cwd, encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return { code: result.status, stdout: result.stdout, out: result.stdout + result.stderr };
}

test("支持清单：contracts/ 与 Skill 副本逐字相同，形状符合 public-video-sources.v1", async () => {
  const pinned = await readFile(path.join(root, "contracts/public-video-sources.v1.json"), "utf8");
  const copy = await readFile(path.join(skill, "references/public-video-sources.v1.json"), "utf8");
  assert.equal(copy, pinned, "references/public-video-sources.v1.json 必须与 contracts/ 下的钉住版本逐字相同");
  const list = JSON.parse(pinned);
  assert.equal(list.schema_version, "public-video-sources.v1");
  assert.deepEqual(list.sources.map((source) => source.id).sort(), [...IDS].sort());
  const hosts = new Set(), prefixes = new Set();
  for (const source of list.sources) {
    for (const key of Object.keys(source)) assert.ok(KEYS.has(key), `${source.id}: 未知字段 ${key}`);
    assert.ok(typeof source.label === "string" && source.label.trim(), source.id);
    assert.match(source.content_id_prefix, /^[a-z]+$/);
    assert.ok(!prefixes.has(source.content_id_prefix), `${source.id}: 前缀重复`);
    prefixes.add(source.content_id_prefix);
    for (const host of [...source.page_hosts, ...source.short_link_hosts]) {
      assert.equal(host, host.toLowerCase(), `${source.id}: ${host} 须小写`);
      assert.ok(!hosts.has(host), `${host} 出现在两个平台`);
      hosts.add(host);
    }
    assert.ok(source.page_hosts.length && source.url_patterns.length, source.id);
    for (const pattern of source.url_patterns) {
      // JS 与 Python 都要能编译，且第一个捕获组是视频 id。
      assert.ok(new RegExp(`${pattern}|`).exec("").length >= 2, `${source.id}: ${pattern} 没有捕获组`);
      assert.ok(pattern.startsWith("^/"), `${source.id}: ${pattern} 须锚定在路径开头`);
    }
    if ("query_id_params" in source) assert.ok(source.query_id_params.every((name) => typeof name === "string" && name), source.id);
    assert.match(source.canonical_url, /^https:\/\/[^/]+\/.*\{id\}/);
    assert.equal(source.metadata_route, source.id === "youtube" ? "youtube_get_video" : "media_call");
    assert.deepEqual(Object.keys(source.public_metrics).sort(), [...METRICS].sort());
    for (const metric of METRICS) assert.equal(typeof source.public_metrics[metric], "boolean");
  }
  const views = Object.fromEntries(list.sources.map((source) => [source.id, source.public_metrics.views]));
  assert.equal(views.douyin, false);
  assert.equal(views.xiaohongshu, false);
  assert.equal(views.kuaishou, true);
  const compiled = python(["-c", "import json,re,sys; [re.compile(p) for s in json.load(open(sys.argv[1]))['sources'] for p in s['url_patterns']]",
    path.join(root, "contracts/public-video-sources.v1.json")]);
  assert.equal(compiled.code, 0, compiled.out);
});

test("支持清单：schema 的平台枚举、SKILL.md 证据表与读证据说明都与清单一致，脚本里没有另写的平台表", async () => {
  const ids = (await readJson(path.join(root, "contracts/public-video-sources.v1.json"))).sources.map((source) => source.id).sort();
  const request = await readJson(path.join(skill, "references/video-analysis-request.schema.json"));
  assert.deepEqual([...request.properties.source.properties.platform.enum].sort(), [...ids, "unknown"].sort());
  const craft = await readJson(path.join(skill, "references/craft-request.schema.json"));
  assert.deepEqual([...craft.properties.subject.properties.platform.enum].sort(), [...ids, "other"].sort());
  const evidence = await readJson(path.join(skill, "references/content-evidence.schema.json"));
  assert.deepEqual([...evidence.properties.content_ref.properties.platform.enum].sort(), ids);

  const list = await readJson(path.join(root, "contracts/public-video-sources.v1.json"));
  const body = await readFile(path.join(skill, "SKILL.md"), "utf8");
  const header = body.split("\n").find((line) => line.startsWith("| Evidence |"));
  for (const source of list.sources) assert.ok(header.includes(source.label), `证据表没有 ${source.label}`);
  const reading = await readFile(path.join(skill, "references/evidence-reading.md"), "utf8");
  for (const source of list.sources.filter((item) => !item.public_metrics.views))
    assert.match(reading, new RegExp(`${source.label}[^.]*publish no\\s+public view count`), `evidence-reading.md 没说 ${source.label} 不公开播放数`);

  // 平台表只在清单里：同一行同时写出三个老平台的字面量，就是又抄了一份表。
  for (const name of await readdir(scripts)) {
    if (!name.endsWith(".py")) continue;
    const text = await readFile(path.join(scripts, name), "utf8");
    for (const line of text.split("\n"))
      assert.ok(!["\"youtube\"", "\"instagram\"", "\"tiktok\""].every((word) => line.includes(word)), `${name} 仍写死平台表：${line.trim()}`);
  }
});

const SAMPLES = {
  "https://www.douyin.com/video/7703997413695219810": ["douyin", "7703997413695219810"],
  "https://www.iesdouyin.com/share/video/7703997413695219810/?region=CN": ["douyin", "7703997413695219810"],
  "https://v.douyin.com/iRNBho6u/": ["douyin", null],
  "https://www.xiaohongshu.com/explore/696f1c34000000002203bef3?xsec_token=ABC": ["xiaohongshu", "696f1c34000000002203bef3"],
  "https://www.rednote.com/discovery/item/696f1c34000000002203bef3": ["xiaohongshu", "696f1c34000000002203bef3"],
  "https://www.kuaishou.com/short-video/3xvk7pzwq5ypcwu": ["kuaishou", "3xvk7pzwq5ypcwu"],
  "https://www.facebook.com/reel/1586859269911090": ["facebook", "1586859269911090"],
  "https://www.facebook.com/watch/?v=1586859269911090": ["facebook", "1586859269911090"],
  "https://m.facebook.com/somepage/videos/1586859269911090/": ["facebook", "1586859269911090"],
  "https://www.facebook.com/share/r/1AbCdEf/": ["facebook", null],
  "https://www.bilibili.com/video/BV1DJWy66EXr/?spm_id_from=333": ["bilibili", "BV1DJWy66EXr"],
  "https://b23.tv/abc123": ["bilibili", null],
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3": ["youtube", "dQw4w9WgXcQ"],
  "https://youtu.be/dQw4w9WgXcQ": ["youtube", "dQw4w9WgXcQ"],
  "https://www.instagram.com/creator/reel/DeZrE2phzDx/?igsh=abc": ["instagram", "DeZrE2phzDx"],
  "https://www.tiktok.com/@someone/video/7301234567890123456?lang=en": ["tiktok", "7301234567890123456"],
  // 主机名精确比较，不做后缀匹配。
  "https://www.douyin.com.example.net/video/7703997413695219810": ["douyin", null],
};

test("支持清单：链接里的视频 id 按 page_hosts 精确匹配与 url_patterns / query_id_params 取出，短链不猜 id", () => {
  const probe = "import json,sys; sys.path.insert(0, sys.argv[1]); import public_video_sources as s; "
    + "print(json.dumps({u: s.content_id_from_url(p, u) for u, p in json.loads(sys.argv[2]).items()}))";
  const result = python(["-c", probe, scripts, JSON.stringify(Object.fromEntries(Object.entries(SAMPLES).map(([url, [platform]]) => [url, platform])))]);
  assert.equal(result.code, 0, result.out);
  assert.deepEqual(JSON.parse(result.stdout), Object.fromEntries(Object.entries(SAMPLES).map(([url, [, id]]) => [url, id])));
});

const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
function mediaEnvelope(operation, jobId, data) {
  return {
    schema_version: "1.0", connector_id: "public-video-media", operation, provider: "fixture", status: "completed", summary: "ok",
    limitations: [], credential_values_recorded: false, job_id: jobId, evidence_ref: `ev-${jobId}`, raw_sha256: jobId.replace(/-/g, "").padEnd(64, "a"),
    request_id: `req-${jobId}`, retrieved_at: "2026-11-12T00:00:00Z", observation_refs: [], data,
  };
}
function envelopes(video) {
  const frames = [0, 0.5, 1].map((t, i) => ({ bytes: 100, sha256: "c".repeat(64), frame_id: `frame-${String(i + 1).padStart(4, "0")}`, t_seconds: t,
    object_ref: `creator-media/${uuid(3)}/epoch-1/frame-${String(i + 1).padStart(4, "0")}.jpg` }));
  return {
    metadata: mediaEnvelope("collect_public_metadata", uuid(1), { video }),
    transcript: mediaEnvelope("fetch_transcript", uuid(2), { cues: [{ text: "Here is the one thing you need.", start_ms: 0, end_ms: 1800 }],
      origin: "speech_recognition", cue_count: 1, artifacts: [{ kind: "transcript", bytes: 10, sha256: "b".repeat(64), object_ref: `creator-media/${uuid(2)}/epoch-1/transcript.json` }] }),
    keyframes: mediaEnvelope("extract_keyframes_hosted_media", uuid(3), { frames, artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
      selection: "duration_scaled_v1", duration_s: 30, frame_count: frames.length }),
  };
}

const CASES = [
  {
    platform: "douyin", label: "Douyin", zh: "抖音视频", prefix: "dy", url: "https://www.douyin.com/video/7703997413695219810", id: "7703997413695219810",
    // 抖音不公开播放数：后台给 0 也不是观测值，证据里不能出现 0 播放。
    video: { id: "7703997413695219810", title: "One thing", description: "One thing #tips", channel: "creator", channel_id: "MS4w", view_count: 0, like_count: 1520,
      comment_count: 48, duration_seconds: 30, upload_date: "20261101", thumbnail: "https://p3.douyinpic.com/cover.jpeg", tags: ["tips"],
      webpage_url: "https://www.douyin.com/video/7703997413695219810" },
    metrics: { like_count: 1520, comment_count: 48 },
    limitation: "Douyin does not publish a public view count, so views are unavailable, not zero.",
  },
  {
    platform: "facebook", label: "Facebook", zh: "Facebook 视频", prefix: "fb", url: "https://www.facebook.com/reel/1586859269911090", id: "1586859269911090",
    video: { id: "1586859269911090", title: "Reel", description: "Reel caption", channel: "Page", channel_id: "100", view_count: 161000, like_count: 2300,
      comment_count: 51, duration_seconds: 6, upload_date: "20261105", thumbnail: "https://scontent.xx.fbcdn.net/cover.jpg", tags: [],
      webpage_url: "https://www.facebook.com/reel/1586859269911090" },
    metrics: { view_count: 161000, like_count: 2300, comment_count: 51 },
    limitation: null,
  },
];

for (const item of CASES) {
  test(`${item.label} 链接走完 prepare_link_request → prepare_video_hook → 证据构建，方法与老平台相同`, async (t) => {
    const run = await mkdtemp(path.join(os.tmpdir(), `kabo-acv-${item.platform}-`));
    t.after(() => rm(run, { recursive: true, force: true }));
    await mkdir(path.join(run, "snapshot"));
    await mkdir(path.join(run, "analysis"));
    const media = envelopes(item.video);
    const files = [];
    for (const [index, envelope] of [media.metadata, media.transcript, media.keyframes].entries()) {
      const file = path.join(run, `snapshot/envelope-${String(index + 1).padStart(2, "0")}.json`);
      await writeFile(file, JSON.stringify(envelope));
      files.push(file);
    }
    // 链接读取得到的 linked-media 包（Web 读链接时给的形状），指回元数据信封。
    const linked = path.join(run, "snapshot/linked-media.json");
    await writeFile(linked, JSON.stringify({
      schema_version: "linked-media-evidence.v1", identity: { platform: item.platform }, original_url: item.url, post_id: item.id,
      media_type: "video", returned_count: 0, images: [],
      source: { request_id: media.metadata.request_id, connector_id: "public-video-media", operation: "collect_public_metadata", raw_sha256: media.metadata.raw_sha256 },
    }));

    const requestFile = path.join(run, "analysis/video-analysis-request.json");
    const prepared = python([path.join(scripts, "prepare_link_request.py"), "--envelope", linked, "--subject-state", "unknown",
      "--max-connector-calls", "6", "--confirmed-by-user", "--output", requestFile]);
    assert.equal(prepared.code, 0, prepared.out);
    const request = await readJson(requestFile);
    assert.equal(request.source.platform, item.platform);
    assert.equal(request.source.content_id, item.id);
    const ajv = new Ajv2020({ allErrors: true, strict: false, logger: false });
    const requestSchema = ajv.compile(await readJson(path.join(skill, "references/video-analysis-request.schema.json")));
    assert.ok(requestSchema(request), JSON.stringify(requestSchema.errors));

    // 开场方法：与 TikTok 拿到的十五个短视频模式逐字相同，knowledge.json 不改。
    const hook = python([path.join(scripts, "prepare_video_hook.py"), "--platform", item.platform, "--output", path.join(run, "analysis/hook-catalog.json")]);
    assert.equal(hook.code, 0, hook.out);
    const tiktok = python([path.join(scripts, "prepare_video_hook.py"), "--platform", "tiktok", "--output", path.join(run, "analysis/hook-catalog-tiktok.json")]);
    assert.equal(tiktok.code, 0, tiktok.out);
    const catalog = JSON.parse(hook.stdout);
    assert.equal(catalog.platform, item.platform);
    assert.equal(catalog.pattern_candidates.length, 15);
    assert.deepEqual(catalog.pattern_candidates, JSON.parse(tiktok.stdout).pattern_candidates);
    const picked = python([path.join(scripts, "prepare_video_hook.py"), "--platform", item.platform, "--pattern-id", "M01", "--output", path.join(run, "analysis/hook-patterns.json")]);
    assert.equal(picked.code, 0, picked.out);
    assert.deepEqual(JSON.parse(picked.stdout).pattern_candidates.map((pattern) => pattern.id), ["M01"]);

    const built = python([path.join(scripts, "build_content_evidence.py"), "--request", "analysis/video-analysis-request.json",
      ...[...files, linked].flatMap((file) => ["--envelope", path.relative(run, file)]),
      "--snapshot-root", "snapshot", "--output", "analysis/content_evidence.json", "--reference-index", "analysis/content_evidence.references.json"], { cwd: run });
    assert.equal(built.code, 0, built.out);
    const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
    const evidenceSchema = ajv.compile(await readJson(path.join(skill, "references/content-evidence.schema.json")));
    assert.ok(evidenceSchema(evidence), JSON.stringify(evidenceSchema.errors));
    assert.equal(evidence.evidence_id, `ev-${item.prefix}-${item.id}`);
    assert.equal(evidence.content_ref.platform, item.platform);
    assert.equal(evidence.content_metadata.status, "available");
    assert.equal(evidence.transcript.status, "available");
    assert.equal(evidence.frames.items.length, 3);
    assert.deepEqual(Object.fromEntries((evidence.public_metrics ?? []).map((metric) => [metric.native_name, metric.value])), item.metrics);
    const unavailable = evidence.limitations.filter((line) => /does not publish a public/.test(line));
    assert.deepEqual(unavailable, item.limitation ? [item.limitation] : []);

    const basis = python(["-c", "import json,sys; sys.path.insert(0, sys.argv[1]); import creator_measurement_basis as m; e = json.load(open(sys.argv[2])); "
      + "f = m.measurement_basis(e, {}, {}); print(json.dumps([f['source'], m.measurement_note(f, 'zh')], ensure_ascii=False))",
    scripts, path.join(run, "analysis/content_evidence.json")]);
    assert.equal(basis.code, 0, basis.out);
    const [source, zh] = JSON.parse(basis.stdout);
    assert.equal(source, `${item.label} video`);
    assert.ok(zh.startsWith(`${item.zh}；`), zh);

    const prefix = python(["-c", "import sys; sys.path.insert(0, sys.argv[1]); import public_video_sources as s; print(s.content_id_prefix(sys.argv[2]))", scripts, item.platform]);
    assert.equal(prefix.stdout.trim(), item.prefix);
  });
}

test("prepare_link_request / prepare_video_hook：清单外的平台照旧拒绝", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-unsupported-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  const linked = path.join(run, "linked.json");
  await writeFile(linked, JSON.stringify({ schema_version: "linked-media-evidence.v1", identity: { platform: "vimeo" },
    original_url: "https://vimeo.com/123", post_id: "123", media_type: "video" }));
  const prepared = python([path.join(scripts, "prepare_link_request.py"), "--envelope", linked, "--subject-state", "unknown",
    "--max-connector-calls", "6", "--output", path.join(run, "analysis/request.json")]);
  assert.equal(prepared.code, 1);
  assert.match(prepared.out, /does not identify a supported post/);
  const hook = python([path.join(scripts, "prepare_video_hook.py"), "--platform", "vimeo", "--output", path.join(run, "hook.json")]);
  assert.equal(hook.code, 2);
  assert.match(hook.out, /invalid choice: 'vimeo'/);
});
