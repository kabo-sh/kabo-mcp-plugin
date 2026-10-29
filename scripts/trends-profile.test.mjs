import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

// 三份 trends Skill 接收后台账号画像（creator-skills #918 移植）：画像文件的读法、
// start 的互斥、describe 不打印受众数、include 被拒后经交接重交。只测脚本行为，不加规范门禁。
// 夹具先过钉住的 get_creator_profile outputSchema：重新钉制品后契约若变了，这里先红。

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = (skill) => path.join(root, "skills", skill, "scripts");
const tools = JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools;
const pinned = new Map(tools.map((tool) => [tool.name, tool]));
const fixture = async (platform) => JSON.parse(await readFile(path.join(root, "scripts/fixtures/creator-profile", `${platform}.json`), "utf8"));
// 钉住的 schema 是 draft-07；uuid、date-time 这类 format 不在这里校验（它们另有 pattern 兜底）。
// kabo#1875 起 effectiveContentProfile.formats 的第一支是 `{"type":"array","items":[]}`（zod 的空元组），
// draft-07 元模式要求数组形 items 至少一项，ajv 默认会拒绝编译整份 schema。这是提供方制品的问题，不在本仓改；
// 这里关掉元模式校验，另由下面那条测试钉住「元模式错误恰好只有这一处」，提供方修好后那条会红，届时删掉这段绕行。
const ajv = () => new Ajv({ allErrors: true, strict: false, logger: false, validateSchema: false });
const profileSchema = ajv().compile(pinned.get("get_creator_profile").outputSchema);

const RTT = "research-tiktok-trends";
const RIT = "research-instagram-trends";
const RYT = "research-youtube-trends";
const PLATFORM = { [RTT]: "tiktok", [RIT]: "instagram", [RYT]: "youtube" };
const SOURCE_FLAG = { [RTT]: ["--video", "https://www.tiktok.com/@creator/video/7412345678901234567"], [RIT]: ["--post", "https://www.instagram.com/reel/DeZrE2phzDx/"], [RYT]: ["--video", "dQw4w9WgXcQ"] };

function attempt(args, { cwd = root, run } = {}) {
  try {
    const stdout = execFileSync("python3", ["-B", ...args], {
      cwd, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(run ? { KABO_STATIC_RUN_DIR: run } : {}) },
    });
    return { exit: 0, stdout, stderr: "" };
  } catch (error) {
    return { exit: error.status, stdout: String(error.stdout), stderr: String(error.stderr) };
  }
}

async function workspace(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-profile-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  return temp;
}

async function newRun(temp, skill) {
  const made = attempt([path.join(scripts(skill), "static_host.py"), "init", "--workspace", temp]);
  assert.equal(made.exit, 0, made.stderr);
  return made.stdout.trim();
}

/** 画像文件放在运行目录与 Skill 目录之外，SKILL.md 就是这么要求的。 */
async function profileFile(temp, value, name = "creator-profile.json") {
  const file = path.join(temp, name);
  await writeFile(file, JSON.stringify(value));
  return file;
}

const drive = (skill, run, ...args) => attempt([path.join(scripts(skill), "drive.py"), ...args], { cwd: run, run });
const callsOf = (stdout) => stdout.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));
const toolResult = (structured) => ({ content: [{ type: "text", text: JSON.stringify(structured) }], structuredContent: structured, isError: false });

const REQUEST = {
  [RTT]: { schema_version: "trend-research-request.v3", request_id: "tt-profile", mode: "current_popular", niche: "fuse bead crafts", platforms: ["tiktok"], locale: { region: "US", language: null }, formats: ["tiktok_video"] },
  [RIT]: { schema_version: "trend-research-request.v3", request_id: "ig-profile", mode: "current_popular", niche: "restaurant food reels", platforms: ["instagram"], locale: { region: null, language: null }, formats: ["instagram_reel"] },
};
const PLAN = {
  [RTT]: ["tiktok-trend-query-plan.json", { schema_version: "tiktok-trend-query-plan.v1", request_id: "tt-profile", intents: [{ intent_id: "tutorials", search_query: "fuse bead craft ideas" }, { intent_id: "fruit", search_query: "perler bead fruit" }] }],
  [RIT]: ["trend-query-plan.json", { schema_version: "trend-query-plan.v1", request_id: "ig-profile", intents: [{ intent_id: "bites", search_query: "restaurant reels first bite" }, { intent_id: "cook", search_query: "cooking reels kitchen" }, { intent_id: "dish", search_query: "food reels plating" }] }],
};

async function authored(skill, run) {
  await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify(REQUEST[skill]));
  const [name, plan] = PLAN[skill];
  await writeFile(path.join(run, name), JSON.stringify(plan));
}

test("夹具与钉住的 get_creator_profile outputSchema 一致；无主打内容与 null 画像两种变体同样合法", async () => {
  for (const platform of ["tiktok", "instagram", "youtube"]) {
    const value = await fixture(platform);
    assert.ok(profileSchema(value), `${platform}：${JSON.stringify(profileSchema.errors)}`);
    const none = { ...value, contentProfile: { ...value.contentProfile, signatureContentStatus: "insufficient_sample", signatureContent: [] } };
    assert.ok(profileSchema(none), JSON.stringify(profileSchema.errors));
    assert.ok(profileSchema({ ...value, contentProfile: null }), JSON.stringify(profileSchema.errors));
  }
  // 读画像的入参确实是钉住的 include 取值；交出的调用里不会多出 schema 没有的键。
  const input = pinned.get("get_creator_profile").inputSchema;
  assert.deepEqual(input.properties.include.items.enum, ["content_profile"]);
  assert.equal(input.additionalProperties, false);
});

test("钉住的 schema 过不了 draft-07 元模式的只有 effectiveContentProfile.formats 的空元组", () => {
  const strictAjv = new Ajv({ allErrors: true, strict: false, logger: false });
  const known = /effectiveContentProfile\/(?:anyOf\/0\/)?properties\/formats\/anyOf\/0\/items/;
  const failing = [];
  for (const tool of tools) {
    for (const schema of [tool.inputSchema, tool.outputSchema].filter(Boolean)) {
      if (strictAjv.validateSchema(schema)) continue;
      const errors = strictAjv.errors.map((error) => error.instancePath);
      assert.ok(errors.every((where) => known.test(where)), `${tool.name}: ${errors.join(", ")}`);
      failing.push(tool.name);
    }
  }
  // 提供方修好后这里先红：删掉上面的 validateSchema:false 绕行与本条测试。
  assert.deepEqual(failing.sort(), ["get_creator_profile", "update_content_preferences"]);
});

test("start --profile：完整工具结果与裸 structuredContent 都能读，打印主打内容，不打印受众数", async (t) => {
  for (const skill of [RTT, RIT, RYT]) {
    const value = await fixture(PLATFORM[skill]);
    for (const [label, shape] of [["complete", toolResult(value)], ["structured", value]]) {
      const temp = await workspace(t);
      const run = await newRun(temp, skill);
      const started = drive(skill, run, "start", "--profile", await profileFile(temp, shape));
      assert.equal(started.exit, 0, `${skill} ${label}：${started.stderr}${started.stdout}`);
      assert.match(started.stdout, new RegExp(`^creator profile: @${value.account.handle.replace(/^@/, "").replace(".", "\\.")} on ${PLATFORM[skill]}$`, "m"));
      const items = started.stdout.split("\n").filter((line) => line.startsWith("signature content "));
      assert.equal(items.length, value.contentProfile.signatureContent.length, started.stdout);
      // 受众数只留在文件里给资格过滤用，不进模型上下文（schema 里的字段说明除外，从画像那几行起查）。
      const printed = started.stdout.slice(started.stdout.indexOf("creator profile: "));
      assert.doesNotMatch(printed, /audience/i, `${skill} ${label}`);
      assert.doesNotMatch(printed, new RegExp(`\\b${value.account.audienceCount}\\b`));
      // 运行目录里留的是原样字节，后面的 discover 从它读。
      assert.equal(await readFile(path.join(run, "creator-profile-source.json"), "utf8"), JSON.stringify(shape));
    }
  }
  // TikTok 夹具的列表顺序与权重相反：打印按 weight 降序编号。
  const temp = await workspace(t);
  const run = await newRun(temp, RTT);
  const out = drive(RTT, run, "start", "--profile", await profileFile(temp, await fixture("tiktok"))).stdout;
  assert.match(out, /^signature content 1 \(sc1, weight 0\.65\)/m);
  assert.match(out, /^signature content 2 \(sc2, weight 0\.35\)/m);
});

test("start --profile：isError 结果、缺 contentProfile 键、不是账号读的文件一律拒收，且不占运行目录", async (t) => {
  const value = await fixture("tiktok");
  const { contentProfile: _dropped, ...withoutKey } = value;
  const cases = [
    [{ isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:read" }] }, /isError/],
    [{ isError: true, structuredContent: value }, /isError/],
    [{ content: [{ type: "text", text: "not json" }] }, /without a structured account read/],
    [withoutKey, /no `contentProfile` field/],
    [value.contentProfile, /no `account` object/],
  ];
  for (const skill of [RTT, RIT, RYT]) {
    for (const [shape, message] of cases) {
      const temp = await workspace(t);
      const run = await newRun(temp, skill);
      const refused = drive(skill, run, "start", "--profile", await profileFile(temp, shape));
      assert.notEqual(refused.exit, 0, `${skill}：${JSON.stringify(shape).slice(0, 80)}`);
      assert.match(refused.stderr + refused.stdout, message);
      // 检查在占用运行目录之前：同一运行不带 --profile 照常开始。
      const plain = drive(skill, run, "start");
      assert.equal(plain.exit, 0, plain.stderr);
    }
  }
});

test("start：--profile 与 --video / --post 互斥", async (t) => {
  for (const skill of [RTT, RIT, RYT]) {
    const temp = await workspace(t);
    const run = await newRun(temp, skill);
    const both = drive(skill, run, "start", ...SOURCE_FLAG[skill], "--profile", await profileFile(temp, await fixture(PLATFORM[skill])));
    assert.notEqual(both.exit, 0);
    assert.match(both.stderr + both.stdout, new RegExp(`--profile and ${SOURCE_FLAG[skill][0]} are two different starts`));
  }
});

test("他平台画像与无主打内容的画像：打印为未使用，discover 交出的调用与不带画像时相同", async (t) => {
  const instagram = await fixture("instagram");
  const tiktok = await fixture("tiktok");
  const none = { ...tiktok, contentProfile: { ...tiktok.contentProfile, signatureContentStatus: "no_qualifying_group", signatureContent: [] } };
  const plainCalls = async () => {
    const temp = await workspace(t);
    const run = await newRun(temp, RTT);
    drive(RTT, run, "start");
    await authored(RTT, run);
    return callsOf(drive(RTT, run, "discover", "--policy", "default_1y").stdout);
  };
  const baseline = await plainCalls();
  for (const [label, value, printed] of [
    ["other platform", instagram, /creator profile: for instagram, not tiktok; it is not used in this run/],
    ["no signature content", none, /no signature content to attach \(no_signature_content \(no_qualifying_group\)\); plan as without a profile/],
    ["null profile", { ...tiktok, contentProfile: null }, /no signature content to attach \(no_content_profile\)/],
  ]) {
    const temp = await workspace(t);
    const run = await newRun(temp, RTT);
    const started = drive(RTT, run, "start", "--profile", await profileFile(temp, toolResult(value)));
    assert.equal(started.exit, 0, started.stderr);
    assert.match(started.stdout, printed, label);
    await authored(RTT, run);
    const discovered = drive(RTT, run, "discover", "--policy", "default_1y");
    assert.equal(discovered.exit, 0, discovered.stderr);
    assert.deepEqual(callsOf(discovered.stdout), baseline, label);
    assert.doesNotMatch(discovered.stdout, /--without-include/, label);
    const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
    assert.equal(request.creator_profile?.signature_content, undefined, label);
  }
});

test("RTT discover 带画像：搜索带 include；被拒后 --without-include 只重交带 include 的调用，后面的轮次自动不带", async (t) => {
  const temp = await workspace(t);
  const run = await newRun(temp, RTT);
  assert.equal(drive(RTT, run, "start", "--profile", await profileFile(temp, toolResult(await fixture("tiktok")))).exit, 0);
  await authored(RTT, run);
  const first = drive(RTT, run, "discover", "--policy", "default_1y");
  assert.equal(first.exit, 0, first.stderr);
  const calls = callsOf(first.stdout);
  const searches = calls.filter((call) => call.tool === "tiktok_discovery_search_videos");
  assert.equal(searches.length, 2);
  for (const call of searches) assert.deepEqual(call.arguments.parameters.include, ["content_signals"]);
  assert.equal(calls.filter((call) => call.tool === "tiktok_discovery_list_top_contents").length, 1);
  assert.match(first.stdout, /run this same command with --without-include instead of --placed/);
  // 画像字段由脚本抄进 Request；语言只是检索标签，不写进 locale。
  const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
  assert.equal(request.creator_profile.handle, "Bead.Studio");
  assert.equal(request.creator_profile.content_language, "en");
  assert.equal(request.creator_profile.audience_count, 2000);
  assert.deepEqual(request.locale, { region: "US", language: null });

  const fallback = drive(RTT, run, "discover", "--policy", "default_1y", "--without-include");
  assert.equal(fallback.exit, 0, fallback.stderr);
  assert.match(fallback.stdout, /Kabo refused `include` on search_videos/);
  const again = callsOf(fallback.stdout);
  // 只重交被拒的两条搜索，不带 include；已作答的榜单不再交一次。
  assert.deepEqual(again, searches.map((call) => ({ ...call, arguments: { ...call.arguments, parameters: Object.fromEntries(Object.entries(call.arguments.parameters).filter(([key]) => key !== "include")) } })));
  const state = JSON.parse(await readFile(path.join(run, ".drive.json"), "utf8"));
  assert.deepEqual(state.include_refused, ["search_videos"]);
  // 再不带 --placed 跑：同一轮照常交出，被拒的操作不再带 include，也不再提示。
  const rerun = drive(RTT, run, "discover", "--policy", "default_1y");
  assert.equal(rerun.exit, 0, rerun.stderr);
  for (const call of callsOf(rerun.stdout)) assert.equal(call.arguments.parameters.include, undefined);
  assert.doesNotMatch(rerun.stdout, /--without-include/);
});

test("--without-include 没有可回应的交接时报错，不改状态", async (t) => {
  for (const profiled of [true, false]) {
    const temp = await workspace(t);
    const run = await newRun(temp, RTT);
    if (profiled) {
      // 带画像但还没有交接过任何一轮。
      assert.equal(drive(RTT, run, "start", "--profile", await profileFile(temp, await fixture("tiktok"))).exit, 0);
      await authored(RTT, run);
    } else {
      // 交接过一轮，但这一轮的调用都不带 include。
      drive(RTT, run, "start");
      await authored(RTT, run);
      drive(RTT, run, "discover", "--policy", "default_1y");
    }
    const refused = drive(RTT, run, "discover", "--policy", "default_1y", "--without-include");
    assert.notEqual(refused.exit, 0, String(profiled));
    assert.match(refused.stderr + refused.stdout, /--without-include answers a hand-over/);
    const state = JSON.parse(await readFile(path.join(run, ".drive.json"), "utf8"));
    assert.equal(state.include_refused, undefined);
  }
});

test("RIT discover 带画像：两条车道的 collect 都带 include media_signals；--without-include 两条都去掉", async (t) => {
  const temp = await workspace(t);
  const run = await newRun(temp, RIT);
  assert.equal(drive(RIT, run, "start", "--profile", await profileFile(temp, await fixture("instagram"))).exit, 0);
  await authored(RIT, run);
  const first = drive(RIT, run, "discover", "--policy", "default_1y");
  assert.equal(first.exit, 0, first.stderr);
  const calls = callsOf(first.stdout);
  assert.equal(calls.length, 2);
  for (const call of calls) {
    assert.equal(call.tool, "collect_instagram_trend_candidates");
    assert.deepEqual(call.arguments.include, ["media_signals"]);
  }
  assert.match(first.stdout, /--without-include instead of --placed/);
  const fallback = drive(RIT, run, "discover", "--policy", "default_1y", "--without-include");
  assert.equal(fallback.exit, 0, fallback.stderr);
  const again = callsOf(fallback.stdout);
  assert.deepEqual(again, calls.map(({ tool, arguments: { include: _include, ...rest } }) => ({ tool, arguments: rest })));
});

test("RYT discover 带画像：collect 调用不带 include，Request 抄入画像字段", async (t) => {
  const temp = await workspace(t);
  const run = await newRun(temp, RYT);
  assert.equal(drive(RYT, run, "start", "--profile", await profileFile(temp, toolResult(await fixture("youtube")))).exit, 0);
  await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ schema_version: "trend-research-request.v3", request_id: "yt-profile", mode: "current_popular", niche: "fuse bead tutorials", platforms: ["youtube"], locale: { region: null, language: null }, formats: ["youtube_short"] }));
  await writeFile(path.join(run, "trend-query-plan.json"), JSON.stringify({ schema_version: "trend-query-plan.v1", request_id: "yt-profile", intents: [{ intent_id: "a", search_query: "fuse beads tutorial" }, { intent_id: "b", search_query: "拼豆教程 新手" }] }));
  const discovered = drive(RYT, run, "discover", "--policy", "default_1y");
  assert.equal(discovered.exit, 0, discovered.stderr);
  const calls = callsOf(discovered.stdout);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].arguments.include, undefined);
  assert.doesNotMatch(discovered.stdout, /--without-include/);
  const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
  assert.deepEqual(request.creator_profile.signature_content.map((item) => item.id), ["sc1", "sc2"]);
  assert.equal(request.locale.language, null);
});
