import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// 插件跟上服务端 2026-10-22 上线的目录面改动：lookup_tiktok_video、
// 延迟媒体调用的 idempotency_key、get_research_data_download 重签与聚合工具的
// delivery。只测脚本行为，不加规范门禁。

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = (id) => path.join(root, "skills", id, "scripts");
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const pinned = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map((tool) => [tool.name, tool]));

function python(args, { cwd = root, run } = {}) {
  return execFileSync("python3", ["-B", ...args], {
    cwd, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(run ? { KABO_STATIC_RUN_DIR: run } : {}) },
  });
}

function attempt(args, options) {
  try {
    return { exit: 0, stdout: python(args, options), stderr: "" };
  } catch (error) {
    return { exit: error.status, stdout: String(error.stdout), stderr: String(error.stderr) };
  }
}

async function newRun(t, skill) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-sync-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  return python([path.join(scripts(skill), "static_host.py"), "init", "--workspace", temp]).trim();
}

async function stage(skill, run, tool, value, command = "stage") {
  // 输入放在运行目录之外：放置脚本会把运行目录里已有的同一份回答当成「已放置」。
  const file = path.join(path.dirname(path.dirname(run)), `input-${Math.random().toString(16).slice(2)}.json`);
  await writeFile(file, JSON.stringify(value));
  return attempt([path.join(scripts(skill), "static_host.py"), command, "--tool", tool, "--input", file], { run });
}

async function metas(run) {
  const directory = path.join(run, "snapshot/.host-evidence");
  const names = (await readdir(directory)).filter((name) => name.endsWith(".meta")).sort();
  return Promise.all(names.map(async (name) => JSON.parse(await readFile(path.join(directory, name), "utf8"))));
}

const result = (envelope) => ({ structuredContent: { result: envelope } });
const RTT = "research-tiktok-trends";
const VIDEO_URL = "https://www.tiktok.com/@creator/video/7412345678901234567?is_from_webapp=1&sender_device=pc";
const CANONICAL_VIDEO = "https://www.tiktok.com/@creator/video/7412345678901234567";

/** lookup_tiktok_video 的投影信封（kabo.tiktok_video.v1）；路线决定 connector_id / operation。 */
function tiktokEnvelope({ route = "share_url", video = {}, unavailable = [] } = {}) {
  const [connector, operation, kind] = {
    id: ["tiktok-discovery", "get_video", "primary"],
    share_url: ["tiktok-discovery", "get_video_by_share_url", "primary"],
    fallback: ["tiktok-search", "get_video", "fallback"],
  }[route];
  const fallback = kind === "fallback";
  return {
    schema_version: "1.0", connector_id: connector, operation, provider: fallback ? "scrapecreators" : "tikhub",
    status: fallback ? "completed_partial" : "completed", summary: "Found 1 video",
    limitations: fallback ? ["TikTok discovery refused this video (forbidden), so Kabo answered through the search route."] : [],
    credential_values_recorded: false, evidence_ref: `ev-${route}`, raw_sha256: sha256(route),
    data: {
      projection: "kabo.tiktok_video.v1",
      video: video === null ? null : {
        id: "7412345678901234567", url: CANONICAL_VIDEO, caption: "Rainy day #fyp", published_at: "2026-10-01T00:00:00Z",
        author: { id: "1", sec_uid: "MS4", handle: "creator", nickname: "C", followers: 1200 },
        metrics: { views: 10000, likes: 900, comments: 12, shares: null },
        duration_s: 15, thumbnail_url: "https://p16-sign.tiktokcdn.com/x.jpg?x-expires=1",
        sound: { id: "5", title: "original sound", author: "creator", is_original: true },
        ...video,
      },
      source: { route: kind, connector_id: connector, operation, provider: fallback ? "scrapecreators" : "tikhub", retrieved_at: "2026-10-22T08:00:00Z", fallback_reason: fallback ? "forbidden" : null },
      unavailable_fields: unavailable,
    },
  };
}

test("RTT static_host：lookup_tiktok_video 三条作答路线都可 stage；别的操作、缺投影与旧工具名被拒", async (t) => {
  const run = await newRun(t, RTT);
  for (const route of ["id", "share_url", "fallback"]) {
    const staged = await stage(RTT, run, "lookup_tiktok_video", result(tiktokEnvelope({ route })));
    assert.equal(staged.exit, 0, `${route}：${staged.stderr}`);
  }
  // 失败信封不带 data、标 isError：照样是那条路线的证据。
  const { data: _data, ...failed } = { ...tiktokEnvelope(), status: "failed", error_code: "not_found", limitations: ["No public video."] };
  assert.equal((await stage(RTT, run, "lookup_tiktok_video", { isError: true, ...result(failed) })).exit, 0);
  assert.deepEqual((await metas(run)).map((meta) => `${meta.connector_id}/${meta.operation}`).sort(), [
    "tiktok-discovery/get_video", "tiktok-discovery/get_video_by_share_url", "tiktok-discovery/get_video_by_share_url", "tiktok-search/get_video",
  ]);
  const wrong = await stage(RTT, run, "lookup_tiktok_video", result({ ...tiktokEnvelope(), connector_id: "tiktok-discovery", operation: "list_comments" }));
  assert.match(wrong.stderr, /does not match its declared operation/);
  const raw = { ...tiktokEnvelope(), data: { item: { title: "raw" } } };
  assert.match((await stage(RTT, run, "lookup_tiktok_video", result(raw))).stderr, /declared projection/);
  // 旧单操作工具已从服务端删除；冒充证据的旧结果仍须拒收。
  assert.equal(pinned.has("tiktok_discovery_get_video_by_share_url"), false);
  assert.match((await stage(RTT, run, "tiktok_discovery_get_video_by_share_url", result(raw))).stderr, /Not a declared evidence tool/);
  const allowed = (await readFile(path.join(root, "skills", RTT, "SKILL.md"), "utf8")).match(/^allowed-tools: (.*)$/m)[1].split(" ");
  assert.ok(allowed.includes("lookup_tiktok_video") && allowed.includes("get_research_data_download"));
  assert.equal(allowed.includes("tiktok_discovery_get_video_by_share_url"), false);
  for (const name of allowed) assert.ok(pinned.has(name), `${name} 不在钉住的 tools/list 里`);
});

test("RTT 驱动：源视频交成顶层 video + delivery 的 lookup_tiktok_video；回退路线也能放置，start --placed 按投影打印", async (t) => {
  const run = await newRun(t, RTT);
  const drive = path.join(scripts(RTT), "drive.py");
  const first = python([drive, "start", "--video", VIDEO_URL], { cwd: run, run });
  const calls = first.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));
  // 跟踪参数在交出前去掉；入参字段都是钉住的 inputSchema 声明过的。
  assert.deepEqual(calls, [{ tool: "lookup_tiktok_video", arguments: { video: CANONICAL_VIDEO, delivery: "download" } }]);
  for (const field of Object.keys(calls[0].arguments)) assert.ok(pinned.get("lookup_tiktok_video").inputSchema.properties[field]);
  assert.match(first, /run this same start command again with --placed/);

  const staged = await stage(RTT, run, "lookup_tiktok_video", result(tiktokEnvelope({ route: "fallback", unavailable: ["video.metrics.shares"] })));
  assert.equal(staged.exit, 0, staged.stderr);
  const placed = python([drive, "start", "--video", VIDEO_URL, "--placed"], { cwd: run, run });
  const line = placed.split("\n").find((text) => text.startsWith("source video (the Creator is its author"));
  assert.ok(line, placed);
  assert.match(line, /author\.handle/);
  assert.deepEqual(JSON.parse(line.slice(line.indexOf("{"))), {
    id: "7412345678901234567", url: CANONICAL_VIDEO, caption: "Rainy day #fyp", published_at: "2026-10-01T00:00:00Z",
    author: { handle: "creator", nickname: "C", followers: 1200 },
    metrics: { views: 10000, likes: 900, comments: 12 },
    duration_s: 15, sound: { title: "original sound", author: "creator", is_original: true },
    route: "fallback", unavailable: ["video.metrics.shares"],
  });
  const source = JSON.parse(await readFile(path.join(run, "source-video.json"), "utf8"));
  assert.equal(source.connector_id, "tiktok-search");
});

test("RTT 驱动：lookup 由另一条路线作答（链接带 id 时是 tiktok-discovery/get_video）时，不带 --placed 再跑照样放置，不再交一次", async (t) => {
  // 交接时请求的是 get_video_by_share_url，信封记的是实际作答路线；轮次登记只认请求那条时，
  // 再跑 start 会判定「没有回答」，把已收费的 lookup 再交一次（review 复现）。
  for (const route of ["id", "fallback"]) {
    const run = await newRun(t, RTT);
    const drive = path.join(scripts(RTT), "drive.py");
    python([drive, "start", "--video", VIDEO_URL], { cwd: run, run });
    const staged = await stage(RTT, run, "lookup_tiktok_video", result(tiktokEnvelope({ route })));
    assert.equal(staged.exit, 0, staged.stderr);
    const again = python([drive, "start", "--video", VIDEO_URL], { cwd: run, run });
    assert.match(again, /placing their responses/, `${route}：${again}`);
    assert.doesNotMatch(again, /^call: /m, route);
    assert.match(again, /^source video \(the Creator is its author/m, route);
  }
});

test("RTT 驱动：另一条路线回的暂时故障在 --placed 时照样整轮重交一次", async (t) => {
  const run = await newRun(t, RTT);
  const drive = path.join(scripts(RTT), "drive.py");
  python([drive, "start", "--video", VIDEO_URL], { cwd: run, run });
  const { data: _data, ...route } = tiktokEnvelope({ route: "id" });
  const limited = { ...route, status: "failed", error_code: "rate_limited", retry_after_seconds: 0.1, limitations: ["Rate limited."] };
  assert.equal((await stage(RTT, run, "lookup_tiktok_video", { isError: true, ...result(limited) })).exit, 0);
  const placed = python([drive, "start", "--video", VIDEO_URL, "--placed"], { cwd: run, run });
  // 没有重交时，这次限流会被当成回答放下（打印「source video: not resolved」）。
  assert.doesNotMatch(placed, /^source video/m, placed);
  const calls = placed.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));
  assert.deepEqual(calls, [{ tool: "lookup_tiktok_video", arguments: { video: CANONICAL_VIDEO, delivery: "download" } }]);
  // 重交后的回答照常放置，打印源视频。
  assert.equal((await stage(RTT, run, "lookup_tiktok_video", result(tiktokEnvelope({ route: "id" })))).exit, 0);
  const done = python([drive, "start", "--video", VIDEO_URL, "--placed"], { cwd: run, run });
  assert.match(done, /^source video \(the Creator is its author/m, done);
  assert.equal(JSON.parse(await readFile(path.join(run, "source-video.json"), "utf8")).status, "completed");
});

test("RTT 读源视频：video 为 null 打印为未解析并带服务端说明；旧 data.item 形状照读", async (t) => {
  const probe = String.raw`
import json, os, sys
sys.path.insert(0, sys.argv[1])
import drive
for case in json.loads(sys.argv[2]):
    with open(drive.SOURCE_VIDEO, "w") as stream:
        json.dump(case, stream)
    drive.print_source_video()
`;
  const run = await newRun(t, RTT);
  const removed = { ...tiktokEnvelope({ route: "id", video: null }), limitations: ["The video is private, removed or a photo post."] };
  const legacy = { connector_id: "tiktok-discovery", operation: "get_video_by_share_url", status: "completed", summary: "ok", limitations: [],
    data: { item: { title: "Old title", creator_handle: "olduser", play_count: 5, thumbnail_url: "https://x" } } };
  const output = python(["-c", probe, scripts(RTT), JSON.stringify([removed, legacy])], { cwd: run, run }).trim().split("\n");
  assert.match(output[0], /^source video: not resolved \(status=completed; The video is private, removed or a photo post\.\)/);
  assert.match(output[1], /comes from creator_handle here/);
  assert.deepEqual(JSON.parse(output[1].slice(output[1].indexOf("{"))), { title: "Old title", creator_handle: "olduser", play_count: 5 });
});

test("job-call：同一运行、同一工具、同一组入参、同一尝试序号得到同一把键；键合钉住的 schema，只给延迟媒体工具", async (t) => {
  for (const skill of ["analyze-content-video", "review-creator-account-deep"]) {
    const run = await newRun(t, skill);
    const host = path.join(scripts(skill), "static_host.py");
    const call = (tool, parameters, extra = []) => JSON.parse(python([host, "job-call", "--tool", tool, "--parameters", parameters, ...extra], { cwd: run, run }));
    const first = call("public_video_fetch_transcript", '{"url": "https://www.youtube.com/watch?v=abc", "language": "en"}');
    // 入参键序不影响键：没拿到响应而原样重发时，键必须相同。
    const again = call("public_video_fetch_transcript", '{"language":"en","url":"https://www.youtube.com/watch?v=abc"}');
    assert.deepEqual(again, first);
    assert.deepEqual(Object.keys(first.arguments).sort(), ["delivery", "idempotency_key", "parameters"]);
    assert.equal(first.arguments.delivery, "download");
    const schema = pinned.get("public_video_fetch_transcript").inputSchema.properties.idempotency_key;
    const key = first.arguments.idempotency_key;
    assert.ok(key.length >= schema.minLength && key.length <= schema.maxLength, key);
    assert.match(key, new RegExp(schema.pattern));
    assert.ok(key.startsWith(`${skill}:${path.basename(run)}:public_video_fetch_transcript:`));
    // 拿到错误后再试（下一个尝试序号）、换了入参、换了工具：都是新键。
    const keys = new Set([
      key,
      call("public_video_fetch_transcript", '{"url": "https://www.youtube.com/watch?v=abc", "language": "en"}', ["--attempt", "2"]).arguments.idempotency_key,
      call("public_video_fetch_transcript", '{"url": "https://www.youtube.com/watch?v=xyz", "language": "en"}').arguments.idempotency_key,
      call("public_video_extract_keyframes", '{"url": "https://www.youtube.com/watch?v=abc", "language": "en"}').arguments.idempotency_key,
    ]);
    assert.equal(keys.size, 4);
    // 另一个运行目录：同样的调用也是新请求。
    const other = await newRun(t, skill);
    assert.notEqual(JSON.parse(python([host, "job-call", "--tool", "public_video_fetch_transcript", "--parameters", '{"url": "https://www.youtube.com/watch?v=abc", "language": "en"}'], { cwd: other, run: other })).arguments.idempotency_key, key);
    for (const [tool, parameters, extra, message] of [
      ["youtube_get_video", "{}", [], /Not a deferred media tool/],
      ["public_video_fetch_transcript", "[]", [], /must be a JSON object/],
      ["public_video_fetch_transcript", "{}", ["--attempt", "0"], /positive integer/],
    ]) {
      const refused = attempt([host, "job-call", "--tool", tool, "--parameters", parameters, ...extra], { cwd: run, run });
      assert.equal(refused.exit, 1);
      assert.match(refused.stderr, message);
    }
  }
});

test("job-call：ACV 与 deep 的抽帧请求补上 max_frames 60，显式更小值保留，超过 60 拒绝", async (t) => {
  const url = "https://www.youtube.com/watch?v=abc";
  for (const skill of ["analyze-content-video", "review-creator-account-deep"]) {
    const run = await newRun(t, skill);
    const host = path.join(scripts(skill), "static_host.py");
    const call = (tool, parameters) => attempt([host, "job-call", "--tool", tool, "--parameters", parameters], { cwd: run, run });
    for (const tool of ["public_video_extract_keyframes", "public_video_extract_keyframes_hosted_media", "public_video_extract_keyframes_hosted_stream"]) {
      const capped = call(tool, JSON.stringify({ url }));
      assert.equal(capped.exit, 0, capped.stderr);
      assert.deepEqual(JSON.parse(capped.stdout).arguments.parameters, { url, max_frames: 60 });
    }
    assert.equal(JSON.parse(call("public_video_extract_keyframes", JSON.stringify({ url, max_frames: 30 })).stdout).arguments.parameters.max_frames, 30);
    // 帧数上限只属于抽帧，其他媒体调用的入参不变。
    assert.deepEqual(JSON.parse(call("public_video_fetch_transcript", JSON.stringify({ url })).stdout).arguments.parameters, { url });
    for (const frames of [120, 0, "60", true]) {
      const refused = call("public_video_extract_keyframes", JSON.stringify({ url, max_frames: frames }));
      assert.equal(refused.exit, 1);
      assert.match(refused.stderr, /max_frames must be an integer from 1 to 60/);
    }
  }
  // deep 的计划入参必须过得了 job-call：计划值超过上限会让每次抽帧都被拒。
  const planned = JSON.parse(python(["-c", "import json, sys; sys.path.insert(0, sys.argv[1]); import plan_media_jobs; print(json.dumps(plan_media_jobs.KEYFRAME_PARAMS))",
    scripts("review-creator-account-deep")]));
  assert.equal(planned.max_frames, 60);
});

test("重签结果按原操作放置：get_research_data_download 的信封经 stage 后 persist_envelope 照常落位", async (t) => {
  const skill = "analyze-creator-competitors";
  const run = await newRun(t, skill);
  const channel = { schema_version: "1.0", connector_id: "youtube-public", operation: "get_channel", provider: "youtube", status: "completed",
    summary: "Found 1 channel", limitations: [], credential_values_recorded: false, evidence_ref: "ev-9", raw_sha256: sha256("c"),
    data: { rows: [{ id: "UC1", title: "Channel" }] } };
  const staged = await stage(skill, run, "get_research_data_download", { structuredContent: { download: { status: "unavailable", reason: "too_large" }, result: channel } });
  assert.equal(staged.exit, 0, staged.stderr);
  python([path.join(scripts(skill), "persist_envelope.py"), "--connector", "youtube-public", "--operation", "get_channel", "--any-status", "--dest", "channel.json"], { cwd: run, run });
  assert.deepEqual(JSON.parse(await readFile(path.join(run, "channel.json"), "utf8")).data, channel.data);
});

// 九份 static_host 里重签分支有两种写法（带 ROUTE_ALIASES 与投影拒绝的、只查 CONNECTOR_TOOLS 的），
// 不在逐字节一致的共享段里：逐个 Skill 钉住接受、拒绝，以及落盘后由本 Skill 的 persist_envelope 按原操作放置。
const RESIGN_SKILLS = ["analyze-content-video", "analyze-creator-competitors", "analyze-tiktok-competitors", "develop-content-ideas",
  "research-instagram-trends", "research-tiktok-trends", "research-youtube-trends", "review-creator-account", "review-creator-account-deep", "diagnose-reach-drop", "recommend-publish-timing", "plan-platform-monetization"];

test("重签工具：十二个 Skill 都接受本 Skill 声明的操作并能按原操作放置，拒绝未声明的操作", async (t) => {
  const probe = String.raw`
import json, sys
sys.path.insert(0, sys.argv[1])
import static_host as h
projected = getattr(h, "PROJECTIONS", {})
plain = [key for key, tool in h.CONNECTOR_TOOLS.items() if tool not in projected]
print(json.dumps(sorted(plain, key=lambda key: h.CONNECTOR_TOOLS[key].startswith("public_video_"))[0]))
`;
  for (const skill of RESIGN_SKILLS) {
    const [connector, operation] = JSON.parse(python(["-c", probe, scripts(skill)])).split("/");
    const run = await newRun(t, skill);
    const envelope = { schema_version: "1.0", connector_id: connector, operation, provider: "p", status: "completed", summary: "ok",
      limitations: [], credential_values_recorded: false, evidence_ref: "ev-1", raw_sha256: sha256(skill), data: { rows: [{ id: "1" }] } };
    const signed = (value) => ({ structuredContent: { download: { status: "unavailable", reason: "too_large" }, result: value } });
    const staged = await stage(skill, run, "get_research_data_download", signed(envelope));
    assert.equal(staged.exit, 0, `${skill}：${staged.stderr}`);
    python([path.join(scripts(skill), "persist_envelope.py"), "--connector", connector, "--operation", operation, "--any-status", "--dest", "placed.json"], { cwd: run, run });
    assert.deepEqual(JSON.parse(await readFile(path.join(run, "placed.json"), "utf8")).data, envelope.data, skill);
    const refused = await stage(skill, run, "get_research_data_download", signed({ ...envelope, connector_id: "nowhere", operation: "nothing" }));
    assert.equal(refused.exit, 1, skill);
    assert.match(refused.stderr, /not from one of this Skill's data tools/, skill);
  }
});

test("重签工具：RTT 的 lookup_tiktok_video 各作答路线重签回来是原始信封，被拒并指回再调 lookup", async (t) => {
  const run = await newRun(t, RTT);
  for (const route of ["id", "share_url", "fallback"]) {
    const { data: _data, ...raw } = tiktokEnvelope({ route });
    const refused = await stage(RTT, run, "get_research_data_download", { structuredContent: { download: { status: "unavailable", reason: "too_large" }, result: { ...raw, data: { item: { id: "1" } } } } });
    assert.equal(refused.exit, 1, route);
    assert.match(refused.stderr, /raw envelope, not the projection; call lookup_tiktok_video again/, route);
  }
});

test("RIT 精简补全交接：打印的 enrich_instagram_shortlist 入参带 delivery:\"download\"，与钉住的 inputSchema 一致", async (t) => {
  const run = await newRun(t, "research-instagram-trends");
  const probe = String.raw`
import sys
sys.path.insert(0, sys.argv[1])
import drive
try:
    drive.hand_over_lean({"window": {"since": "a", "until": "b"}, "items": [{"content_key": "k"}]})
except SystemExit:
    pass
`;
  const output = python(["-c", probe, scripts("research-instagram-trends")], { cwd: run, run });
  const call = JSON.parse(output.split("\n")[0]);
  assert.equal(call.delivery, "download");
  for (const field of Object.keys(call)) assert.ok(pinned.get("enrich_instagram_shortlist").inputSchema.properties[field], field);
  assert.equal(JSON.parse(await readFile(path.join(run, "trend-enrichment-call.json"), "utf8")).delivery, "download");
});
