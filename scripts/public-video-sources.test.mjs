// Which platforms single-video analysis accepts comes only from the support list public-video-sources.v1: kabo's
// docs/contracts/public-video-sources.v1.json is copied byte for byte to contracts/, with a byte-identical copy under
// analyze-content-video's references/ (a standalone Skill install and the Web bundle both carry it). The scripts read
// platforms, id prefixes, link ids and public counts from it, and the schema's platform enum matches it. Nothing here
// goes online: the envelopes are hand-written in the shapes kabo's public-video-media.ts gives for Douyin and Facebook
// (the same style as the TikTok/YouTube envelopes in acv-video-media.test.mjs). Douyin's metadata and measurements
// come back with the keyframes round (data.video / data.signals) and the standalone metadata and measure calls answer
// unsupported; every result's data carries video_identity; the Facebook view count is the page's rounded display
// (view_count_basis) and is null when it cannot be read.
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
const KEYS = new Set(["id", "label", "content_id_prefix", "page_hosts", "short_link_hosts", "short_link_path_patterns", "url_patterns", "query_id_params",
  "canonical_url", "metadata_route", "public_metrics", "notes"]);
const METRICS = ["views", "likes", "comments", "shares", "saves"];

function python(args, { cwd = root } = {}) {
  const result = spawnSync("python3", ["-B", ...args], { cwd, encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return { code: result.status, stdout: result.stdout, out: result.stdout + result.stderr };
}

test("support list: contracts/ and the Skill copy are byte-identical and match the public-video-sources.v1 shape", async () => {
  const pinned = await readFile(path.join(root, "contracts/public-video-sources.v1.json"), "utf8");
  const copy = await readFile(path.join(skill, "references/public-video-sources.v1.json"), "utf8");
  assert.equal(copy, pinned, "references/public-video-sources.v1.json must be byte-identical to the pinned copy under contracts/");
  const list = JSON.parse(pinned);
  assert.equal(list.schema_version, "public-video-sources.v1");
  assert.deepEqual(list.sources.map((source) => source.id).sort(), [...IDS].sort());
  const hosts = new Set(), prefixes = new Set();
  for (const source of list.sources) {
    for (const key of Object.keys(source)) assert.ok(KEYS.has(key), `${source.id}: unknown field ${key}`);
    assert.ok(typeof source.label === "string" && source.label.trim(), source.id);
    assert.match(source.content_id_prefix, /^[a-z]+$/);
    assert.ok(!prefixes.has(source.content_id_prefix), `${source.id}: duplicate prefix`);
    prefixes.add(source.content_id_prefix);
    for (const host of [...source.page_hosts, ...source.short_link_hosts]) {
      assert.equal(host, host.toLowerCase(), `${source.id}: ${host} must be lowercase`);
      assert.ok(!hosts.has(host), `${host} appears under two platforms`);
      hosts.add(host);
    }
    assert.ok(source.page_hosts.length && source.url_patterns.length, source.id);
    for (const pattern of [...source.url_patterns, ...(source.short_link_path_patterns ?? [])]) {
      // Both JS and Python must compile it; it is anchored at the start of the path.
      assert.ok(pattern.startsWith("^/"), `${source.id}: ${pattern} must be anchored at the start of the path`);
      new RegExp(pattern);
    }
    // The first capture group is the video id; a pattern without one takes the id from query_id_params, so the
    // platform must declare its query parameters.
    for (const pattern of source.url_patterns)
      if (new RegExp(`${pattern}|`).exec("").length < 2)
        assert.ok(source.query_id_params?.length, `${source.id}: ${pattern} has no capture group and no query_id_params`);
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
  const compiled = python(["-c", "import json,re,sys; [re.compile(p) for s in json.load(open(sys.argv[1]))['sources'] for p in s['url_patterns'] + s.get('short_link_path_patterns', [])]",
    path.join(root, "contracts/public-video-sources.v1.json")]);
  assert.equal(compiled.code, 0, compiled.out);
});

test("support list: the schema platform enum and the evidence-reading notes match it, SKILL.md names no platform list, and no script keeps its own platform table", async () => {
  const ids = (await readJson(path.join(root, "contracts/public-video-sources.v1.json"))).sources.map((source) => source.id).sort();
  const request = await readJson(path.join(skill, "references/video-analysis-request.schema.json"));
  assert.deepEqual([...request.properties.source.properties.platform.enum].sort(), [...ids, "unknown"].sort());
  const craft = await readJson(path.join(skill, "references/craft-request.schema.json"));
  assert.deepEqual([...craft.properties.subject.properties.platform.enum].sort(), [...ids, "other"].sort());
  const evidence = await readJson(path.join(skill, "references/content-evidence.schema.json"));
  assert.deepEqual([...evidence.properties.content_ref.properties.platform.enum].sort(), ids);

  const list = await readJson(path.join(root, "contracts/public-video-sources.v1.json"));
  const body = await readFile(path.join(skill, "SKILL.md"), "utf8");
  // Which platforms can be read is the backend's answer, not the Skill's: the evidence table is not a list of
  // supported platforms, and an unsupported link stops the run with one sentence to the creator.
  const header = body.split("\n").find((line) => line.startsWith("| Evidence |"));
  for (const source of list.sources) assert.ok(!header.includes(source.label), `the evidence table lists ${source.label} as a column`);
  assert.match(body, /when a tool says the platform or link is not\s+supported, tell the creator which link could not be read and stop/);
  const reading = await readFile(path.join(skill, "references/evidence-reading.md"), "utf8");
  for (const source of list.sources.filter((item) => !item.public_metrics.views))
    assert.match(reading, new RegExp(`${source.label}[^.]*publish\\s+no\\s+public\\s+view\\s+count`), `evidence-reading.md does not say ${source.label} publishes no view count`);

  // The platform table lives only in the list: a line naming all three original platforms as literals is another copy of it.
  for (const name of await readdir(scripts)) {
    if (!name.endsWith(".py")) continue;
    const text = await readFile(path.join(scripts, name), "utf8");
    for (const line of text.split("\n"))
      assert.ok(!["\"youtube\"", "\"instagram\"", "\"tiktok\""].every((word) => line.includes(word)), `${name} still hard-codes a platform table: ${line.trim()}`);
  }
});

// Expected values follow kabo matchPublicVideoSource: [platform, kind, id]; null means not a video page on the list.
const SAMPLES = {
  "https://www.douyin.com/video/7703997413695219810": ["douyin", "video", "7703997413695219810"],
  "https://www.iesdouyin.com/share/video/7703997413695219810/?region=CN": ["douyin", "video", "7703997413695219810"],
  "https://v.douyin.com/iRNBho6u/": ["douyin", "short_link", null],
  "https://www.xiaohongshu.com/explore/696f1c34000000002203bef3?xsec_token=ABC": ["xiaohongshu", "video", "696f1c34000000002203bef3"],
  "https://www.rednote.com/discovery/item/696f1c34000000002203bef3": ["xiaohongshu", "video", "696f1c34000000002203bef3"],
  "https://xhslink.com/a/AbCdEf": ["xiaohongshu", "short_link", null],
  "https://www.kuaishou.com/short-video/3xvk7pzwq5ypcwu": ["kuaishou", "video", "3xvk7pzwq5ypcwu"],
  "https://www.kuaishou.com/f/X8aBcDeF": ["kuaishou", "short_link", null],
  "https://www.facebook.com/reel/1586859269911090": ["facebook", "video", "1586859269911090"],
  "https://www.facebook.com/watch/?v=1586859269911090": ["facebook", "video", "1586859269911090"],
  "https://m.facebook.com/somepage/videos/1586859269911090/": ["facebook", "video", "1586859269911090"],
  "https://www.facebook.com/somepage/videos/a-title/1586859269911090/": ["facebook", "video", "1586859269911090"],
  "https://www.facebook.com/share/r/1AbCdEf/": ["facebook", "short_link", null],
  "https://fb.watch/abcd1234/": ["facebook", "short_link", null],
  "https://www.facebook.com/somepage": null,
  "https://www.bilibili.com/video/BV1DJWy66EXr/?spm_id_from=333": ["bilibili", "video", "BV1DJWy66EXr"],
  "https://b23.tv/abc123": ["bilibili", "short_link", null],
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3": ["youtube", "video", "dQw4w9WgXcQ"],
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ&v=aaaaaaaaaaa": null,
  "https://youtu.be/dQw4w9WgXcQ": ["youtube", "video", "dQw4w9WgXcQ"],
  "https://www.instagram.com/reel/DeZrE2phzDx/?igsh=abc": ["instagram", "video", "DeZrE2phzDx"],
  "https://www.instagram.com/creator.name/reel/DeZrE2phzDx/?igsh=abc": ["instagram", "video", "DeZrE2phzDx"],
  "https://www.tiktok.com/@someone/photo/7301234567890123456": ["tiktok", "video", "7301234567890123456"],
  "https://www.youtube.com/v/dQw4w9WgXcQ": ["youtube", "video", "dQw4w9WgXcQ"],
  "https://www.tiktok.com/@someone/video/7301234567890123456?lang=en": ["tiktok", "video", "7301234567890123456"],
  "https://vm.tiktok.com/ZMabc/": ["tiktok", "short_link", null],
  // www.tiktok.com/t/<code>/ is a share link on a page host: short_link_path_patterns, not a video page.
  "https://www.tiktok.com/t/ZTfCHqHy2/": ["tiktok", "short_link", null],
  "https://www.tiktok.com/t/ZTfCHqHy2": ["tiktok", "short_link", null],
  "https://www.tiktok.com/t/ZTfCHqHy2/extra": null,
  "https://www.tiktok.com/@someone": null,
  // Hosts are compared exactly, never by suffix; https only.
  "https://www.douyin.com.example.net/video/7703997413695219810": null,
  "http://www.douyin.com/video/7703997413695219810": null,
};

test("support list: links resolve to platform and id by kabo's rules (exact hosts, query id when no capture group, share paths are short links, no guessed short-link ids)", () => {
  const probe = "import json,sys; sys.path.insert(0, sys.argv[1]); import public_video_sources as s; "
    + "out = {}\nfor u in json.loads(sys.argv[2]):\n  m = s.match_url(u)\n  out[u] = [m['platform'], m['kind'], m['id']] if m else None\n"
    + "  assert s.content_id_from_url(m['platform'] if m else 'douyin', u) == (m['id'] if m else None)\nprint(json.dumps(out))";
  const result = python(["-c", probe, scripts, JSON.stringify(Object.keys(SAMPLES))]);
  assert.equal(result.code, 0, result.out);
  assert.deepEqual(JSON.parse(result.stdout), SAMPLES);
});

test("support list: a www.tiktok.com/t/<code>/ share link is a TikTok short link with no guessed id", () => {
  const url = "https://www.tiktok.com/t/ZTfCHqHy2/";
  const probe = "import json,sys; sys.path.insert(0, sys.argv[1]); import public_video_sources as s; "
    + "print(json.dumps([s.match_url(sys.argv[2]), s.content_id_from_url('tiktok', sys.argv[2])]))";
  const result = python(["-c", probe, scripts, url]);
  assert.equal(result.code, 0, result.out);
  assert.deepEqual(JSON.parse(result.stdout), [{ platform: "tiktok", kind: "short_link", id: null }, null]);
});

const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
function mediaEnvelope(operation, jobId, data, { status = "completed", limitations = [] } = {}) {
  return {
    schema_version: "1.0", connector_id: "public-video-media", operation, provider: "fixture", status, summary: "ok",
    limitations, credential_values_recorded: false, job_id: jobId, evidence_ref: `ev-${jobId}`, raw_sha256: jobId.replace(/-/g, "").padEnd(64, "a"),
    request_id: `req-${jobId}`, retrieved_at: "2026-11-12T00:00:00Z", observation_refs: [], ...(data === undefined ? {} : { data }),
  };
}
// kabo notFetchedForPlatform: on the paid-resolver platforms the standalone metadata and measure calls answer
// unsupported, with no data.
const unsupported = (operation, jobId, pointer) => mediaEnvelope(operation, jobId, undefined, {
  status: "unsupported",
  limitations: [{ code: "operation_not_implemented", message: `This operation did not retrieve anything for this Douyin link, and ${pointer}. Do not substitute prior knowledge or treat anything missing here as zero.` }],
});
const transcriptData = (identity) => ({ cues: [{ text: "Here is the one thing you need.", start_ms: 0, end_ms: 1800 }],
  origin: "speech_recognition", cue_count: 1, artifacts: [{ kind: "transcript", bytes: 10, sha256: "b".repeat(64), object_ref: `creator-media/${uuid(2)}/epoch-1/transcript.json` }],
  ...(identity ? { video_identity: identity } : {}) });
function keyframesData(extra = {}) {
  const frames = [0, 0.5, 1].map((t, i) => ({ bytes: 100, sha256: "c".repeat(64), frame_id: `frame-${String(i + 1).padStart(4, "0")}`, t_seconds: t,
    object_ref: `creator-media/${uuid(3)}/epoch-1/frame-${String(i + 1).padStart(4, "0")}.jpg` }));
  return { frames, artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
    selection: "duration_scaled_v1", duration_s: 30, frame_count: frames.length, ...extra };
}
const SIGNALS = { duration_s: 30, measured: ["shots"], unavailable: ["silence", "freeze", "framing", "brightness", "loudness"],
  shots: { count: 2, cuts_at_s: [12.4], shots: [{ start_s: 0, end_s: 12.4 }, { start_s: 12.4, end_s: 30 }] }, limitations: [] };

const DOUYIN_ID = "7703997413695219810";
const DOUYIN_IDENTITY = { platform: "douyin", platform_video_id: DOUYIN_ID, canonical_url: `https://www.douyin.com/video/${DOUYIN_ID}`, resolved_from_short_link: false };
const FACEBOOK_ID = "1586859269911090";
const FACEBOOK_IDENTITY = { platform: "facebook", platform_video_id: FACEBOOK_ID, canonical_url: `https://www.facebook.com/watch/?v=${FACEBOOK_ID}`, resolved_from_short_link: false };
const CASES = [
  {
    platform: "douyin", label: "Douyin", zh: "抖音视频", prefix: "dy", url: `https://www.douyin.com/video/${DOUYIN_ID}`, id: DOUYIN_ID,
    // A paid-resolver platform: metadata and measurements both arrive in the keyframes round; Douyin publishes no
    // view count, so view_count is null and the evidence must not show one.
    envelopes: () => [
      unsupported("collect_public_metadata", uuid(1), "the keyframes result for this video carries its public metadata as data.video"),
      mediaEnvelope("fetch_transcript", uuid(2), transcriptData(DOUYIN_IDENTITY)),
      mediaEnvelope("extract_keyframes_hosted_media", uuid(3), keyframesData({
        signals: SIGNALS, video_identity: DOUYIN_IDENTITY,
        video: { id: DOUYIN_ID, title: "One thing", description: "One thing #tips", webpage_url: `https://www.douyin.com/video/${DOUYIN_ID}`,
          channel: "creator", channel_id: "MS4w", duration_seconds: 30, upload_date: "20261101", view_count: null, like_count: 1520,
          comment_count: 48, share_count: 12, save_count: 30, thumbnail: "https://p3.douyinpic.com/cover.jpeg", tags: ["tips"] } })),
      unsupported("measure_media_signals", uuid(4), "the keyframes result for this video carries these measurements as data.signals"),
    ],
    linkedSource: 2,
    metrics: { like_count: 1520, comment_count: 48, share_count: 12, save_count: 30 },
    limitations: ["Douyin does not publish a public view count, so views are unavailable, not zero."],
    probed: true,
  },
  {
    platform: "facebook", label: "Facebook", zh: "Facebook 视频", prefix: "fb", url: `https://www.facebook.com/reel/${FACEBOOK_ID}`, id: FACEBOOK_ID,
    // Facebook uses the general downloader: metadata is its own round; the view count is the page's rounded
    // display, with a precision note.
    envelopes: () => [
      mediaEnvelope("collect_public_metadata", uuid(1), { video_identity: FACEBOOK_IDENTITY, artifacts: [],
        video: { id: FACEBOOK_ID, title: "161K views · 2.3K reactions | Reel", description: "Reel caption", channel: "Page", channel_id: "100",
          view_count: 161000, view_count_basis: "page_display_rounded", like_count: 2300, comment_count: 51, duration_seconds: 6,
          upload_date: "20261105", thumbnail: "https://scontent.xx.fbcdn.net/cover.jpg", tags: [], webpage_url: `https://www.facebook.com/reel/${FACEBOOK_ID}` } },
      { limitations: [{ code: "partial_provider_response", message: "The view count is the page's own rounded display (161K views), not an exact figure: compare it only at that precision." }] }),
      mediaEnvelope("fetch_transcript", uuid(2), transcriptData(FACEBOOK_IDENTITY)),
      mediaEnvelope("extract_keyframes_hosted_media", uuid(3), keyframesData({ video_identity: FACEBOOK_IDENTITY })),
    ],
    linkedSource: 0,
    metrics: { view_count: 161000, like_count: 2300, comment_count: 51 },
    limitations: ["The view count is the page's own rounded display (161K views), not an exact figure: compare it only at that precision."],
    viewNote: /the page's own rounded display, not an exact figure/,
    probed: false,
  },
];

for (const item of CASES) {
  test(`${item.label} link goes through prepare_link_request -> prepare_video_hook -> evidence, with the same method as the original platforms`, async (t) => {
    const run = await mkdtemp(path.join(os.tmpdir(), `kabo-acv-${item.platform}-`));
    t.after(() => rm(run, { recursive: true, force: true }));
    await mkdir(path.join(run, "snapshot"));
    await mkdir(path.join(run, "analysis"));
    const media = item.envelopes();
    const files = [];
    for (const [index, envelope] of media.entries()) {
      const file = path.join(run, `snapshot/envelope-${String(index + 1).padStart(2, "0")}.json`);
      await writeFile(file, JSON.stringify(envelope));
      files.push(file);
    }
    // The linked-media bundle from reading the link (the shape Web gives when it reads a link) points back to the
    // envelope that carries metadata.
    const source = media[item.linkedSource];
    const linked = path.join(run, "snapshot/linked-media.json");
    await writeFile(linked, JSON.stringify({
      schema_version: "linked-media-evidence.v1", identity: { platform: item.platform }, original_url: item.url, post_id: item.id,
      media_type: "video", returned_count: 0, images: [],
      source: { request_id: source.request_id, connector_id: source.connector_id, operation: source.operation, raw_sha256: source.raw_sha256 },
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

    // Opening method: exactly the fifteen short-video patterns TikTok gets; knowledge.json is unchanged.
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
    assert.equal(evidence.content_ref.published_at, item.platform === "douyin" ? "2026-11-01" : "2026-11-05");
    assert.equal(evidence.content_metadata.status, "available");
    assert.equal(evidence.content_metadata.title, item.platform === "douyin" ? "One thing" : "161K views · 2.3K reactions | Reel");
    assert.equal(evidence.transcript.status, "available");
    assert.equal(evidence.frames.items.length, 3);
    // Every envelope is recorded in acquisition, unsupported ones too; but when the data it points to arrived, it
    // is not a gap.
    assert.deepEqual(evidence.acquisition.map((entry) => entry.status), media.map((envelope) => envelope.status));
    assert.equal(evidence.limitations.some((line) => /returned unsupported|did not retrieve anything/.test(line)), false, JSON.stringify(evidence.limitations));
    assert.equal(Boolean(evidence.media.probed?.shots), item.probed);
    assert.deepEqual(Object.fromEntries((evidence.public_metrics ?? []).map((metric) => [metric.native_name, metric.value])), item.metrics);
    if (item.viewNote) assert.match(evidence.public_metrics.find((metric) => metric.native_name === "view_count").note, item.viewNote);
    for (const line of item.limitations) assert.ok(evidence.limitations.includes(line), `${line} is not in ${JSON.stringify(evidence.limitations)}`);
    assert.equal(evidence.limitations.filter((line) => /does not publish a public/.test(line)).length,
      item.limitations.filter((line) => /does not publish a public/.test(line)).length);

    const basis = python(["-c", "import json,sys; sys.path.insert(0, sys.argv[1]); import creator_measurement_basis as m; e = json.load(open(sys.argv[2])); "
      + "f = m.measurement_basis(e, {}, {}); print(json.dumps([f['source'], m.measurement_note(f, 'zh')], ensure_ascii=False))",
    scripts, path.join(run, "analysis/content_evidence.json")]);
    assert.equal(basis.code, 0, basis.out);
    const [label, zh] = JSON.parse(basis.stdout);
    assert.equal(label, `${item.label} video`);
    assert.ok(zh.startsWith(`${item.zh}；`), zh);
  });
}

async function buildOnly(t, name, source, envelopes) {
  const run = await mkdtemp(path.join(os.tmpdir(), `kabo-acv-${name}-`));
  t.after(() => rm(run, { recursive: true, force: true }));
  await mkdir(path.join(run, "snapshot"));
  await mkdir(path.join(run, "analysis"));
  await writeFile(path.join(run, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: `req-${name}`,
    source: { acquisition: "public_url", subject_state: "unknown", owner_data: null, declared_format: "video", ...source },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 4, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] },
  }));
  const args = [];
  for (const [index, envelope] of envelopes.entries()) {
    const file = `snapshot/envelope-${String(index + 1).padStart(2, "0")}.json`;
    await writeFile(path.join(run, file), JSON.stringify(envelope));
    args.push("--envelope", file);
  }
  const built = python([path.join(scripts, "build_content_evidence.py"), "--request", "analysis/video-analysis-request.json", ...args,
    "--snapshot-root", "snapshot", "--output", "analysis/content_evidence.json"], { cwd: run });
  return { run, built, evidence: built.code === 0 ? await readJson(path.join(run, "analysis/content_evidence.json")) : null };
}

test("short link, transcript only: the link has no readable id, so the backend's video_identity is used and the evidence and TXT export proceed", async (t) => {
  const identity = { ...DOUYIN_IDENTITY, resolved_from_short_link: true };
  const { run, built, evidence } = await buildOnly(t, "douyin-short", { platform: "douyin", url: "https://v.douyin.com/iRNBho6u/", content_id: null },
    [mediaEnvelope("fetch_transcript", uuid(2), transcriptData(identity))]);
  assert.equal(built.code, 0, built.out);
  assert.equal(evidence.content_ref.content_id, DOUYIN_ID);
  assert.equal(evidence.evidence_id, `ev-dy-${DOUYIN_ID}`);
  assert.equal(evidence.content_ref.permalink, "https://v.douyin.com/iRNBho6u/");
  const exported = python([path.join(scripts, "export_transcript.py"), "analysis/content_evidence.json", "report/"], { cwd: run });
  assert.equal(exported.code, 0, exported.out);
  assert.match(await readFile(path.join(run, "report/transcript.txt"), "utf8"), /Here is the one thing you need/);

  // A short link without video_identity keeps its id null instead of failing the run; nothing is guessed.
  const none = await buildOnly(t, "douyin-short-none", { platform: "douyin", url: "https://v.douyin.com/iRNBho6u/", content_id: null },
    [mediaEnvelope("fetch_transcript", uuid(2), transcriptData(null))]);
  assert.equal(none.built.code, 0, none.built.out);
  assert.equal(none.evidence.content_ref.content_id, null);
  assert.match(none.evidence.evidence_id, /^ev-dy-unresolved-/);

  // The result says the video belongs to another platform: the requested platform was wrong; say so rather than mix them.
  const other = await buildOnly(t, "douyin-mismatch", { platform: "tiktok", url: "https://v.douyin.com/iRNBho6u/", content_id: null },
    [mediaEnvelope("fetch_transcript", uuid(2), transcriptData(identity))]);
  assert.equal(other.built.code, 1);
  assert.match(other.built.out, /identify a douyin video, but the request names 'tiktok'/);
});

test("transcript only, one cue: the platform-declared duration from the transcript result closes it and the SRT exports; without a duration it is still refused", async (t) => {
  // Dev-box round 4: speech recognition on a 5.5-second Kuaishou video returned one cue, standalone metadata is
  // not fetched on these three platforms, so the evidence had no duration and the SRT was refused
  // (final_cue_end_unavailable).
  const oneCue = (extra) => ({ cues: [{ text: "Only line.", start_ms: 400, end_ms: null }], cue_count: 1,
    origin: "speech_recognition", video_identity: DOUYIN_IDENTITY, artifacts: [], ...extra });
  const withDuration = await buildOnly(t, "douyin-one-cue", { platform: "douyin", url: `https://www.douyin.com/video/${DOUYIN_ID}`, content_id: DOUYIN_ID },
    [mediaEnvelope("fetch_transcript", uuid(2), oneCue({ duration_seconds: 5.5, duration_source: "platform_declared" }))]);
  assert.equal(withDuration.built.code, 0, withDuration.built.out);
  assert.equal(withDuration.evidence.media.duration_s, 5.5);
  assert.equal(withDuration.evidence.media.duration_source, "connector_transcript");
  const exported = python([path.join(scripts, "export_transcript.py"), "analysis/content_evidence.json", "report/", "--formats", "srt"], { cwd: withDuration.run });
  assert.equal(exported.code, 0, exported.out);
  assert.match(await readFile(path.join(withDuration.run, "report/transcript.srt"), "utf8"),
    /00:00:00,400 --> 00:00:05,500\r?\nOnly line\./);

  const without = await buildOnly(t, "douyin-one-cue-none", { platform: "douyin", url: `https://www.douyin.com/video/${DOUYIN_ID}`, content_id: DOUYIN_ID },
    [mediaEnvelope("fetch_transcript", uuid(2), oneCue({}))]);
  assert.equal(without.built.code, 0, without.built.out);
  assert.equal(without.evidence.media.duration_source, "unavailable");
  const refused = python([path.join(scripts, "export_transcript.py"), "analysis/content_evidence.json", "report/", "--formats", "srt"], { cwd: without.run });
  assert.match(refused.out, /final_cue_end_unavailable/);
});

test("the source video itself cannot be fetched (Bilibili deleted or region-locked): the transcript is not called \"no subtitle track\", the reason goes into limitations, and SKILL.md tells the model to stop", async (t) => {
  // Dev-box round 5: the four results for a region-locked video each said something different, the transcript
  // said "this video exposes no subtitle track", and the model wrote speech observations from that.
  const BV = "BV1GJ411x7h7";
  const reason = "The source video itself could not be fetched: the platform reports it deleted or available only in some regions, which this service cannot reach.";
  const gone = (operation, jobId, data) => mediaEnvelope(operation, jobId, { ...data, source_unavailable: true, artifacts: [] },
    { status: "completed_partial", limitations: [{ code: "no_data_retrieved", message: reason }] });
  const { built, evidence } = await buildOnly(t, "bilibili-source-unavailable", { platform: "bilibili", url: `https://www.bilibili.com/video/${BV}`, content_id: BV }, [
    gone("fetch_transcript", uuid(2), { cues: [], cue_count: 0 }),
    gone("extract_keyframes", uuid(3), { frame_count: 0, selection: "none", duration_s: null, sampling_plan: null, frames: [] }),
  ]);
  assert.equal(built.code, 0, built.out);
  assert.equal(evidence.transcript.status, "provider_error");
  assert.match(evidence.transcript.status_basis, /source video itself could not be fetched/);
  assert.doesNotMatch(JSON.stringify(evidence.transcript), /subtitle track/);
  assert.equal(evidence.frames.status, "unavailable");
  assert.ok(evidence.limitations.includes(reason), evidence.limitations.join(" | "));
  const skill = await readFile(path.join(root, "skills/analyze-content-video/SKILL.md"), "utf8");
  assert.match(skill, /`data\.source_unavailable: true`/);
});

test("Facebook views withheld are null: not kept as a public count, not treated as 0, and the note is passed on", async (t) => {
  const withheld = "The view count was withheld: the only figure this path could read does not match what the page shows, so treat views as unknown rather than zero.";
  const { built, evidence } = await buildOnly(t, "facebook-withheld", { platform: "facebook", url: `https://www.facebook.com/reel/${FACEBOOK_ID}`, content_id: FACEBOOK_ID }, [
    mediaEnvelope("collect_public_metadata", uuid(1), { video_identity: FACEBOOK_IDENTITY, artifacts: [],
      video: { id: FACEBOOK_ID, title: "Reel", description: null, view_count: null, view_count_basis: "withheld", like_count: 2300, comment_count: null,
        duration_seconds: 6, upload_date: "20261105", thumbnail: null, tags: [], webpage_url: `https://www.facebook.com/reel/${FACEBOOK_ID}` } },
    { limitations: [{ code: "partial_provider_response", message: withheld }] }),
  ]);
  assert.equal(built.code, 0, built.out);
  assert.deepEqual(evidence.public_metrics, [{ native_name: "like_count", value: 2300, equals_owner_metric: null,
    note: "Public like_count from public-video-media.collect_public_metadata; not reach or an owner metric." }]);
  assert.ok(evidence.limitations.includes(withheld));
  assert.equal(evidence.limitations.some((line) => /does not publish a public/.test(line)), false);
});

test("prepare_link_request / prepare_video_hook: platforms not on the list are still refused", async (t) => {
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

// collect_media.py still asks for metadata and measurements: on the paid-resolver platforms they answer unsupported,
// fetch nothing and cost nothing, and the one paid resolution rides on keyframes. The unsupported envelopes in the
// combined result must still be saved and handed to the evidence builder.
test("Douyin combined call: metadata and measure answering unsupported are still saved, and the evidence reads metadata and measurements from the keyframes round", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-douyin-media-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
  const run = spawnSync("python3", [path.join(scripts, "static_host.py"), "init", "--workspace", workspace], { encoding: "utf8", env }).stdout.trim();
  const url = `https://www.douyin.com/video/${DOUYIN_ID}`;
  const collect = (args) => spawnSync("python3", [path.join(scripts, "collect_media.py"), ...args], { cwd: run, encoding: "utf8", env: { ...env, KABO_STATIC_RUN_DIR: run } });
  const first = collect(["--url", url, "--operations", "metadata,transcript,keyframes,measure"]);
  assert.equal(first.status, 0, first.stdout + first.stderr);
  const call = JSON.parse(first.stdout.split("\n").find((line) => line.startsWith("call: ")).slice(6));
  const byOperation = Object.fromEntries(CASES[0].envelopes().map((envelope) => [envelope.operation, envelope]));
  const results = { collect_public_metadata: byOperation.collect_public_metadata, fetch_transcript: byOperation.fetch_transcript,
    extract_keyframes: byOperation.extract_keyframes_hosted_media, measure_media_signals: byOperation.measure_media_signals };
  const tools = { collect_public_metadata: "public_video_collect_public_metadata", fetch_transcript: "public_video_fetch_transcript",
    extract_keyframes: "public_video_extract_keyframes_hosted_media", measure_media_signals: "public_video_measure_media_signals" };
  const jobs = call.arguments.requests.map((request, index) => ({ group: `video/${request.operation}`, content_id: "video", operation: request.operation,
    attempt: 1, job_id: uuid(index + 1), status: results[request.operation].status === "unsupported" ? "unsupported" : "completed" }));
  const composite = { schema_version: "kabo-composite-fetch.v1", tool: "collect_video_media", status: "completed",
    calls: call.arguments.requests.map((request) => ({ tool: tools[request.operation], parameters: request.parameters, group: `video/${request.operation}`, attempts: 1, result: results[request.operation] })),
    summary: { requests: jobs.length, pending: 0, jobs }, coverage: { deadline_reached: false, unfinished: [], provider_calls: 1, pending: 0 }, limitations: [] };
  const slot = first.stdout.split("\n").find((line) => line.startsWith("  result ")).split("has no download url: ")[1].slice(0, -1);
  await writeFile(slot, JSON.stringify({ content: [{ type: "text", text: JSON.stringify(composite) }], structuredContent: composite }));
  const resumed = collect(["--url", url, "--operations", "metadata,transcript,keyframes,measure", "--placed"]);
  assert.equal(resumed.status, 0, resumed.stdout + resumed.stderr);
  assert.match(resumed.stdout, /"status": "collected"/);
  const flags = resumed.stdout.split("\n").find((line) => line.startsWith("Pass these to build_content_evidence.py")).split(": ")[1];
  await writeFile(path.join(run, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-douyin",
    source: { acquisition: "public_url", subject_state: "unknown", platform: "douyin", url, content_id: null, declared_format: "video", owner_data: null },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 4, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] },
  }));
  const built = spawnSync("bash", ["-c", `cd '${run}' && python3 '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json ${flags} --snapshot-root snapshot --output analysis/content_evidence.json`],
    { encoding: "utf8", env });
  assert.equal(built.status, 0, built.stdout + built.stderr);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assert.equal(evidence.content_ref.content_id, DOUYIN_ID);
  assert.equal(evidence.content_metadata.status, "available");
  assert.equal(evidence.media.probed.shots.count, 2);
  assert.equal(evidence.acquisition.filter((entry) => entry.status === "unsupported").length, 2);
  assert.equal(evidence.limitations.some((line) => /returned unsupported|did not retrieve anything/.test(line)), false);
});
