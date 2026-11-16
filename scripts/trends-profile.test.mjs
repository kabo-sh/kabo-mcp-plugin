import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

// The three trends Skills accept the backend account profile (ported from creator-skills #918): how the profile file is read,
// mutual exclusion of start, describe not printing audience numbers, and handing off again after include is rejected. Tests script behavior only, no spec gate is added.
// The fixtures first pass the pinned get_creator_profile outputSchema: if the contract changes after the artifact is re-pinned, this goes red first.

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = (skill) => path.join(root, "skills", skill, "scripts");
const tools = JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools;
const pinned = new Map(tools.map((tool) => [tool.name, tool]));
const fixture = async (platform) => JSON.parse(await readFile(path.join(root, "scripts/fixtures/creator-profile", `${platform}.json`), "utf8"));
// The pinned schema is draft-07; formats such as uuid and date-time are not validated here (they are backstopped by a pattern).
const ajv = () => new Ajv({ allErrors: true, strict: false, logger: false });
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

/** The profile file lives outside both the run directory and the Skill directory, as SKILL.md requires. */
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

test("fixtures match the pinned get_creator_profile outputSchema; the no-pillar and null-profile variants are equally valid", async () => {
  for (const platform of ["tiktok", "instagram", "youtube"]) {
    const value = await fixture(platform);
    assert.ok(profileSchema(value), `${platform}: ${JSON.stringify(profileSchema.errors)}`);
    const none = { ...value, contentProfile: { ...value.contentProfile, signatureContentStatus: "insufficient_sample", signatureContent: [] } };
    assert.ok(profileSchema(none), JSON.stringify(profileSchema.errors));
    assert.ok(profileSchema({ ...value, contentProfile: null }), JSON.stringify(profileSchema.errors));
  }
  // The input for reading the profile is indeed a pinned include value; the handed-out call carries no keys the schema lacks.
  const input = pinned.get("get_creator_profile").inputSchema;
  assert.deepEqual(input.properties.include.items.enum, ["content_profile"]);
  assert.equal(input.additionalProperties, false);
});

test("once the provider fixes the empty tuple, every pinned tool schema passes the draft-07 meta-schema", () => {
  const strictAjv = new Ajv({ allErrors: true, strict: false, logger: false });
  for (const tool of tools) {
    for (const schema of [tool.inputSchema, tool.outputSchema].filter(Boolean)) {
      assert.ok(strictAjv.validateSchema(schema), `${tool.name}: ${JSON.stringify(strictAjv.errors)}`);
    }
  }
});

test("start --profile: both the full tool result and bare structuredContent are readable; pillars are printed, audience counts are not", async (t) => {
  for (const skill of [RTT, RIT, RYT]) {
    const value = await fixture(PLATFORM[skill]);
    for (const [label, shape] of [["complete", toolResult(value)], ["structured", value]]) {
      const temp = await workspace(t);
      const run = await newRun(temp, skill);
      const started = drive(skill, run, "start", "--profile", await profileFile(temp, shape));
      assert.equal(started.exit, 0, `${skill} ${label}: ${started.stderr}${started.stdout}`);
      assert.match(started.stdout, new RegExp(`^creator profile: @${value.account.handle.replace(/^@/, "").replace(".", "\\.")} on ${PLATFORM[skill]}$`, "m"));
      const items = started.stdout.split("\n").filter((line) => line.startsWith("signature content "));
      assert.equal(items.length, value.contentProfile.signatureContent.length, started.stdout);
      // Audience numbers stay only in the file for eligibility filtering and do not enter the model context (except field descriptions in the schema; check from the profile lines onward).
      const printed = started.stdout.slice(started.stdout.indexOf("creator profile: "));
      assert.doesNotMatch(printed, /audience/i, `${skill} ${label}`);
      assert.doesNotMatch(printed, new RegExp(`\\b${value.account.audienceCount}\\b`));
      // The run directory keeps the bytes as is, and the later discover reads from it.
      assert.equal(await readFile(path.join(run, "creator-profile-source.json"), "utf8"), JSON.stringify(shape));
    }
  }
  // The list order of the TikTok fixture is the reverse of the weights: printing numbers them in descending weight.
  const temp = await workspace(t);
  const run = await newRun(temp, RTT);
  const out = drive(RTT, run, "start", "--profile", await profileFile(temp, await fixture("tiktok"))).stdout;
  assert.match(out, /^signature content 1 \(sc1, weight 0\.65\)/m);
  assert.match(out, /^signature content 2 \(sc2, weight 0\.35\)/m);
});

test("start --profile: isError results, a missing contentProfile key, and files that are not an account read are all rejected and do not occupy the run directory", async (t) => {
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
      assert.notEqual(refused.exit, 0, `${skill}: ${JSON.stringify(shape).slice(0, 80)}`);
      assert.match(refused.stderr + refused.stdout, message);
      // The check comes before the run directory is occupied: the same run without --profile starts as usual.
      const plain = drive(skill, run, "start");
      assert.equal(plain.exit, 0, plain.stderr);
    }
  }
});

test("start: --profile is mutually exclusive with --video / --post", async (t) => {
  for (const skill of [RTT, RIT, RYT]) {
    const temp = await workspace(t);
    const run = await newRun(temp, skill);
    const both = drive(skill, run, "start", ...SOURCE_FLAG[skill], "--profile", await profileFile(temp, await fixture(PLATFORM[skill])));
    assert.notEqual(both.exit, 0);
    assert.match(both.stderr + both.stdout, new RegExp(`--profile and ${SOURCE_FLAG[skill][0]} are two different starts`));
  }
});

test("other platforms and a null profile attach nothing; a zero-category profile still attaches the base fields", async (t) => {
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
    ["no signature content", none, /no signature content \(base_profile_only \(no_qualifying_group\)\)/],
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
    if (label === "no signature content") {
      const searches = callsOf(discovered.stdout).filter((call) => call.tool === "collect_tiktok_video_candidates");
      assert.equal(searches.length, 1);
      for (const call of searches) assert.deepEqual(call.arguments.include, ["content_signals"]);
    } else {
      assert.deepEqual(callsOf(discovered.stdout), baseline, label);
      assert.doesNotMatch(discovered.stdout, /--without-include/, label);
    }
    const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
    assert.equal(request.creator_profile?.signature_content, undefined, label);
    if (label === "no signature content") {
      assert.equal(request.creator_profile.audience_count, value.account.audienceCount);
      assert.deepEqual(request.creator_profile.formats, ["short_video"]);
    }
  }
});

test("RTT discover with a profile: the composite fetch carries include; after rejection, --without-include drops include and resubmits, and later runs omit it too", async (t) => {
  const temp = await workspace(t);
  const run = await newRun(temp, RTT);
  assert.equal(drive(RTT, run, "start", "--profile", await profileFile(temp, toolResult(await fixture("tiktok")))).exit, 0);
  await authored(RTT, run);
  const first = drive(RTT, run, "discover", "--policy", "default_1y");
  assert.equal(first.exit, 0, first.stderr);
  const calls = callsOf(first.stdout);
  // One composite call finishes all searches (both sort orders) and the daily chart; include is at the top level.
  assert.deepEqual(calls.map((call) => call.tool), ["collect_tiktok_video_candidates"]);
  const searches = calls;
  assert.deepEqual(searches[0].arguments.include, ["content_signals"]);
  assert.deepEqual(searches[0].arguments.sorts, [0, 1]);
  assert.equal(searches[0].arguments.top_contents.fallback_days, 1);
  assert.match(first.stdout, /run this same command with --without-include instead of --placed/);
  // Profile fields are copied into the Request by the script; language is only a retrieval label and is not written into locale.
  const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
  assert.equal(request.creator_profile.handle, "Bead.Studio");
  assert.equal(request.creator_profile.content_language, "en");
  assert.equal(request.creator_profile.audience_count, 2000);
  assert.deepEqual(request.locale, { region: "US", language: null });

  const fallback = drive(RTT, run, "discover", "--policy", "default_1y", "--without-include");
  assert.equal(fallback.exit, 0, fallback.stderr);
  assert.match(fallback.stdout, /Kabo refused `include` on collect_tiktok_video_candidates/);
  const again = callsOf(fallback.stdout);
  // A rejected composite call is resubmitted once with include removed, other input unchanged.
  assert.deepEqual(again, searches.map((call) => ({ ...call, arguments: Object.fromEntries(Object.entries(call.arguments).filter(([key]) => key !== "include")) })));
  const state = JSON.parse(await readFile(path.join(run, ".drive.json"), "utf8"));
  assert.deepEqual(state.include_refused, ["collect_tiktok_video_candidates"]);
  // Run again without --placed: the same round is handed out as usual, the rejected operation no longer carries include, and no hint is shown any more.
  const rerun = drive(RTT, run, "discover", "--policy", "default_1y");
  assert.equal(rerun.exit, 0, rerun.stderr);
  for (const call of callsOf(rerun.stdout)) assert.equal(call.arguments.include, undefined);
  assert.doesNotMatch(rerun.stdout, /--without-include/);
});

test("--without-include errors when there is no handoff to answer, and leaves state unchanged", async (t) => {
  for (const profiled of [true, false]) {
    const temp = await workspace(t);
    const run = await newRun(temp, RTT);
    if (profiled) {
      // With a profile, but no round has been handed off yet.
      assert.equal(drive(RTT, run, "start", "--profile", await profileFile(temp, await fixture("tiktok"))).exit, 0);
      await authored(RTT, run);
    } else {
      // One round has been handed off, but the calls in this round carry no include.
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

test("RIT discover with a profile: both lanes' collect carry include media_signals; --without-include removes it from both", async (t) => {
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

test("RYT discover with a profile: the collect call carries no include, and the Request copies the profile fields", async (t) => {
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

// ---------------------------------------------------------------------------------------------
// Effective profile (ported from creator-skills #920; the read port get_creator_profile takes effective:true).
// *-effective*.json fixtures: the three TikTok ones are vectors from the kabo effective-content-profile-v1 golden
// (the input backend profile goes into contentProfile, the expected synthesis result into effectiveContentProfile),
// and the Instagram / YouTube ones are hand-written mirrors of the first batch of fixtures, with the creator's own excluded topics and market added. All pass the pinned outputSchema first.

const EFFECTIVE = ["tiktok-effective", "tiktok-effective-main", "tiktok-effective-no-base", "instagram-effective", "youtube-effective"];
const RTT_EFFECTIVE_PLAN = { schema_version: "tiktok-trend-query-plan.v1", request_id: "tt-profile", intents: [{ intent_id: "legs", search_query: "leg day routine" }, { intent_id: "prep", search_query: "meal prep ideas" }] };

async function startedWith(t, skill, value) {
  const temp = await workspace(t);
  const run = await newRun(temp, skill);
  const started = drive(skill, run, "start", "--profile", await profileFile(temp, value));
  assert.equal(started.exit, 0, `${skill}: ${started.stderr}${started.stdout}`);
  return { temp, run, started };
}

test("effective-profile fixtures match the pinned schema; reading the profile has an effective switch, and effectiveContentProfile may be absent or null", async () => {
  const input = pinned.get("get_creator_profile").inputSchema;
  assert.deepEqual(input.properties.effective, { description: input.properties.effective.description, type: "boolean" });
  assert.ok(!input.required.includes("effective"));
  for (const name of EFFECTIVE) {
    const value = await fixture(name);
    assert.ok(profileSchema(value), `${name}: ${JSON.stringify(profileSchema.errors)}`);
    assert.ok("contentProfile" in value, name);
    assert.equal(value.effectiveContentProfile.ruleVersion, "effective-content-profile.v1");
    assert.ok(profileSchema({ ...value, effectiveContentProfile: null }), name);
    const { effectiveContentProfile: _gone, ...withoutKey } = value;
    assert.ok(profileSchema(withoutKey), name);
  }
});

test("start --profile effective profile: prints the owner's edits, pillar marks, excluded topics, and market, but not audience counts; both file shapes read the same", async (t) => {
  const tiktok = await fixture("tiktok-effective");
  for (const shape of [toolResult(tiktok), tiktok]) {
    const { started } = await startedWith(t, RTT, shape);
    assert.match(started.stdout, /^creator profile: carries the Creator's own edits; use it as it is$/m);
    assert.match(started.stdout, /^content language: es \(set by the Creator\)$/m);
    assert.match(started.stdout, /^accepted languages: es, en$/m);
    assert.match(started.stdout, /^excluded topics \(never search for them\): \["Supplement reviews", "CROSSFIT"\]$/m);
    assert.match(started.stdout, /^market: MX \(set by the Creator; the default search region when the ask names none; never locale\.region\)$/m);
    const printed = started.stdout.slice(started.stdout.indexOf("creator profile: "));
    assert.doesNotMatch(printed, /audience/i);
    assert.doesNotMatch(printed, new RegExp(`\\b${tiktok.account.audienceCount}\\b`));
  }
  // The main item ranks first and is marked main; at equal weight it is also first.
  const { started: main } = await startedWith(t, RTT, await fixture("tiktok-effective-main"));
  assert.match(main.stdout, /^signature content 1 \(sc4, main, weight 0\.31\): Form checks/m);
  assert.match(main.stdout, /^signature content 2 \(sc1, weight 0\.31\)/m);
  // No backend profile, only the creator's own settings: still used, stating that there is no main content, and listing the edits that do not match.
  const { started: noBase } = await startedWith(t, RTT, await fixture("tiktok-effective-no-base"));
  assert.match(noBase.stdout, /no signature content \(settings_only \(no_profile\)\); plan as without signature content, keeping the Creator's settings below/);
  assert.match(noBase.stdout, /^excluded topics \(never search for them\): \["Pranks"\]$/m);
  assert.match(noBase.stdout, /1 of the Creator's edits no longer match the current profile and are not applied: \["Leg workouts"\]/);
  assert.doesNotMatch(noBase.stdout, /it is not used in this run|plan as without a profile/);
  // Instagram has no region parameter: the market is still printed, but with a note that it is not used.
  const { started: instagram } = await startedWith(t, RIT, toolResult(await fixture("instagram-effective")));
  assert.match(instagram.stdout, /^market: BR \(set by the Creator; Instagram search takes no region, so it is not used here\)$/m);
});

test("falls back to contentProfile when the effective-profile literal is unrecognized; when both are unrecognized, treated as unused", async (t) => {
  const value = await fixture("tiktok-effective-main");
  const unknown = { ...value, effectiveContentProfile: { ...value.effectiveContentProfile, version: 2 } };
  const { started } = await startedWith(t, RTT, unknown);
  assert.doesNotMatch(started.stdout.slice(started.stdout.indexOf("creator profile: ")), /own edits|, main,/);
  assert.match(started.stdout, /^signature content 1 \(sc1, weight 0\.40\)/m);
  const neither = { ...unknown, contentProfile: { ...value.contentProfile, ruleVersion: "content-profile.v9" } };
  const { started: none } = await startedWith(t, RTT, neither);
  assert.match(none.stdout, /no signature content to attach \(content_profile_version_not_recognized/);
});

test("RTT discover effective profile: the Request copies excluded topics, market, and the owner's posts; the market serves as the search region only when neither the Request nor --region gives one", async (t) => {
  const value = await fixture("tiktok-effective");
  const discover = async (locale, ...extra) => {
    const { run } = await startedWith(t, RTT, toolResult(value));
    await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ ...REQUEST[RTT], locale }));
    await writeFile(path.join(run, PLAN[RTT][0]), JSON.stringify(RTT_EFFECTIVE_PLAN));
    const discovered = drive(RTT, run, "discover", "--policy", "default_1y", ...extra);
    assert.equal(discovered.exit, 0, discovered.stderr + discovered.stdout);
    const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
    const searches = callsOf(discovered.stdout).filter((call) => call.tool === "collect_tiktok_video_candidates");
    return { request, regions: [...new Set(searches.map((call) => call.arguments.region))] };
  };
  const { request, regions } = await discover({ region: null, language: null });
  assert.deepEqual(regions, ["MX"]);
  const creator = request.creator_profile;
  assert.deepEqual(creator.excluded_topics, ["Supplement reviews", "CROSSFIT"]);
  assert.equal(creator.market_region, "MX");
  assert.equal(creator.profile_basis, "profile_with_edits");
  assert.deepEqual(creator.own_content_ids, value.effectiveContentProfile.ownContentIds);
  assert.equal(creator.content_language, "es");
  // Neither language nor market goes into locale.
  assert.deepEqual(request.locale, { region: null, language: null });
  assert.deepEqual((await discover({ region: "US", language: null })).regions, ["US"]);
  assert.deepEqual((await discover({ region: null, language: null }, "--region", "CA")).regions, ["CA"]);
});

test("a plan carrying excluded topics is always rejected: same for a profile with pillars and one with settings only", async (t) => {
  for (const [name, query] of [["tiktok-effective", "crossfit leg day"], ["tiktok-effective-no-base", "pranks gone wrong"]]) {
    const { run } = await startedWith(t, RTT, await fixture(name));
    await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify(REQUEST[RTT]));
    const plan = { ...RTT_EFFECTIVE_PLAN, intents: [{ intent_id: "legs", search_query: query }, RTT_EFFECTIVE_PLAN.intents[1]] };
    await writeFile(path.join(run, PLAN[RTT][0]), JSON.stringify(plan));
    const refused = drive(RTT, run, "discover", "--policy", "default_1y");
    assert.notEqual(refused.exit, 0, name);
    assert.match(refused.stderr + refused.stdout, /a topic the Creator\s+excluded/, name);
  }
});

test("swapping the profile file mid-run is rejected; rerunning start with the same file works as usual", async (t) => {
  for (const skill of [RTT, RIT, RYT]) {
    // Rerun the same command (same path): if the bytes are unchanged it proceeds as usual; if the user edited the profile on the web and the host re-read it and overwrote the same file: reject.
    const { temp, run } = await startedWith(t, skill, await fixture(PLATFORM[skill]));
    const same = drive(skill, run, "start", "--profile", await profileFile(temp, await fixture(PLATFORM[skill])));
    assert.equal(same.exit, 0, `${skill}: ${same.stderr}`);
    const changed = drive(skill, run, "start", "--profile", await profileFile(temp, await fixture(`${PLATFORM[skill]}-effective`)));
    assert.notEqual(changed.exit, 0, skill);
    assert.match(changed.stderr + changed.stdout, /the profile changed during the run\. Start a new run with the new file/, skill);
  }
});

test("RYT effective profile: collect carries the market only when locale.region is empty, language is not taken from the profile; RIT collect carries no region", async (t) => {
  const collect = async (locale) => {
    const { run } = await startedWith(t, RYT, await fixture("youtube-effective"));
    await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ schema_version: "trend-research-request.v3", request_id: "yt-profile", mode: "current_popular", niche: "fuse bead tutorials", platforms: ["youtube"], locale, formats: ["youtube_short"] }));
    await writeFile(path.join(run, "trend-query-plan.json"), JSON.stringify({ schema_version: "trend-query-plan.v1", request_id: "yt-profile", intents: [{ intent_id: "a", search_query: "fuse beads tutorial" }, { intent_id: "b", search_query: "拼豆教程 新手" }] }));
    const discovered = drive(RYT, run, "discover", "--policy", "default_1y");
    assert.equal(discovered.exit, 0, discovered.stderr + discovered.stdout);
    return callsOf(discovered.stdout)[0].arguments;
  };
  const defaulted = await collect({ region: null, language: null });
  assert.equal(defaulted.region, "GB");
  assert.equal(defaulted.language, undefined);
  assert.equal((await collect({ region: "US", language: null })).region, "US");

  const { run } = await startedWith(t, RIT, await fixture("instagram-effective"));
  await authored(RIT, run);
  const discovered = drive(RIT, run, "discover", "--policy", "default_1y");
  assert.equal(discovered.exit, 0, discovered.stderr + discovered.stdout);
  for (const call of callsOf(discovered.stdout)) assert.equal(JSON.stringify(call.arguments).includes("BR"), false);
  const request = JSON.parse(await readFile(path.join(run, "trend-research-request.json"), "utf8"));
  assert.deepEqual(request.creator_profile.excluded_topics, ["Dessert reviews"]);
  assert.deepEqual(request.locale, { region: null, language: null });
});
