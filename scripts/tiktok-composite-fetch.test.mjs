// The two TikTok Skills now fetch data through backend composite tools (docs/skills-spec.md KS9):
// the discover of research-tiktok-trends used to take two handoff rounds (per-intent sort 0 + the D-1 daily chart, then sort 1 + D-2 when the chart was empty),
// and rank used up to 12 list_account_posts; analyze-tiktok-competitors used four searches in discover and five histories in content.
// Now each stage hands off one composite call. Here a small neutral fixture builds the backend result in the shape of kabo-composite-fetch.v1; after stage,
// the driver is resumed, checking that: the input handed out fits the pinned inputSchema, results are put back into their original slots and request provenance by group, downstream scripts run to completion as usual;
// when a popular account's history is missing it continues as usual (only absolute views remain), and when a competitor account is missing it stops as before.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = (skill) => path.join(root, "skills", skill, "scripts");
const pinned = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map((tool) => [tool.name, tool]));
const validate = (name) => new Ajv({ allErrors: true, strict: false, logger: false, validateFormats: false }).compile(pinned.get(name).inputSchema);
const RTT = "research-tiktok-trends";
const TTC = "analyze-tiktok-competitors";
const DAY = 86_400_000;

function attempt(args, { cwd = root, run, input } = {}) {
  try {
    const stdout = execFileSync("python3", ["-B", "-W", "ignore", ...args], {
      cwd, encoding: "utf8", input: input ?? "", stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(run ? { KABO_STATIC_RUN_DIR: run } : {}) },
    });
    return { exit: 0, stdout, stderr: "" };
  } catch (error) {
    return { exit: error.status, stdout: String(error.stdout), stderr: String(error.stderr) };
  }
}

async function newRun(t, skill) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-composite-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const made = attempt([path.join(scripts(skill), "static_host.py"), "init", "--workspace", temp]);
  assert.equal(made.exit, 0, made.stderr);
  return made.stdout.trim();
}

const drive = (skill, run, args, input) => attempt([path.join(scripts(skill), "drive.py"), ...args], { cwd: run, run, input });
const callsOf = (stdout) => stdout.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));

/** Write the backend result to disk by stage (fallback path when download delivery is unavailable; the split logic is the same as fetch). */
async function stage(skill, run, tool, value) {
  const file = path.join(run, "host-results", `${tool}-${Math.random().toString(16).slice(2)}.json`);
  await writeFile(file, JSON.stringify({ structuredContent: value }));
  const staged = attempt([path.join(scripts(skill), "static_host.py"), "stage", "--tool", tool, "--input", file], { cwd: run, run });
  assert.equal(staged.exit, 0, staged.stderr);
  return JSON.parse(staged.stdout);
}

let sequence = 0;
function envelope(connector, operation, data, { status = "completed", at = new Date() } = {}) {
  sequence += 1;
  const rows = data.items ?? data.rows ?? [];
  return {
    schema_version: "1.0", connector_id: connector, operation, provider: "provider-a", status,
    summary: `Found ${rows.length} public results.`, limitations: [], credential_values_recorded: false,
    request_id: `req-${sequence}`, retrieved_at: at.toISOString(), raw_sha256: `${sequence}`.padStart(64, "0"),
    observation_refs: [], evidence_ref: `ev-${sequence}`, data,
  };
}

const AUTHORS = ["neutral.maker.a", "neutral.maker.b", "neutral.maker.c"];
/** Two recent videos per author; every search returns the same batch (six candidates after dedup). */
function searchItems(keyword) {
  return AUTHORS.flatMap((handle, a) => [0, 1].map((n) => {
    const id = `74000000000000${a}${n}`;
    return {
      content_id: id, url: `https://www.tiktok.com/@${handle}/video/${id}`, creator_id: `90${a}`, creator_handle: handle,
      creator_name: handle, creator_url: `https://www.tiktok.com/@${handle}`, creator_followers: 1000 * (a + 1),
      title: `${keyword} idea ${a}-${n} #craft`, published_at: new Date(Date.now() - (3 + a + n) * DAY).toISOString(),
      views: 50_000 * (a + 1) + n, likes: 900, comments: 20, shares: 5, period_views: null, native_category_ids: [], sound: null,
    };
  }));
}

function historyRows(handle, count) {
  return Array.from({ length: count }, (_, i) => ({
    content_id: `75${AUTHORS.indexOf(handle)}${String(i).padStart(4, "0")}`, creator_id: `90${AUTHORS.indexOf(handle)}`, username: handle,
    title: `${handle} post ${i}`, published_at: new Date(Date.now() - (2 + i) * DAY).toISOString(),
    url: `https://www.tiktok.com/@${handle}/video/75${AUTHORS.indexOf(handle)}${String(i).padStart(4, "0")}`,
    format: "tiktok_video", metrics: { views: 1000 + 37 * i, likes: 40, comments: 2 },
  }));
}

/** Build a composite result for the handed-off calls from the backend collectTiktokVideoCandidates grouping and inputs; the daily chart is empty for D-1 and has data for D-2. */
function candidatesResult(args) {
  const calls = [];
  const searches = [];
  args.intents.forEach((intent, i) => args.sorts.forEach((sort) => {
    const parameters = { keyword: intent.keyword, sort_type: sort, count: args.count,
      ...(args.region ? { region: args.region } : {}), ...(intent.publish_time !== undefined ? { publish_time: intent.publish_time } : {}),
      ...(args.include ? { include: args.include } : {}) };
    const result = envelope("tiktok-discovery", "search_videos", { count: args.count, items: searchItems(intent.keyword), query: intent.keyword, offset: 0, has_more: false });
    calls.push({ tool: "tiktok_discovery_search_videos", parameters, group: `intent-${i}-sort-${sort}`, attempts: 1, result });
    searches.push({ group: `intent-${i}-sort-${sort}`, keyword: intent.keyword, sort_type: sort, status: "completed", rows: result.data.items.length });
  }));
  const board = [];
  if (args.top_contents) {
    let date = args.top_contents.date;
    for (let day = 0; day <= args.top_contents.fallback_days; day += 1) {
      const stamp = Math.floor(Date.parse(`${date}T00:00:00Z`) / 1000);
      const items = day === 0 ? [] : searchItems("board").slice(0, 1);
      const result = envelope("tiktok-discovery", "list_top_contents", { period_end_timestamp: stamp, ...(args.region ? { country_code: args.region } : {}), items },
        { at: new Date(Date.now() + day * 1000) });
      calls.push({ tool: "tiktok_discovery_list_top_contents", group: `top-${date}`, attempts: 1, result,
        parameters: { period_end_timestamp: stamp, period_dimension: 3, ...(args.region ? { country_code: args.region } : {}), limit: 100 } });
      board.push({ group: `top-${date}`, date, status: "completed", items: items.length });
      if (items.length) break;
      date = new Date(Date.parse(`${date}T00:00:00Z`) - DAY).toISOString().slice(0, 10);
    }
  }
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_tiktok_video_candidates", status: "completed", calls,
    summary: { searches, ...(args.top_contents ? { top_contents: board } : {}) },
    coverage: { deadline_reached: false, unfinished: [], provider_calls: calls.length }, limitations: [] };
}

/** collectAccountHistory (TikTok): one list_account_posts per account; accounts in `skip` simulate not being issued in time (no call). */
function historyResult(args, skip = []) {
  const calls = [];
  const accounts = [];
  const limitations = [];
  args.accounts.forEach((ref, i) => {
    const group = `acct-${i}`;
    if (skip.includes(ref.handle)) {
      accounts.push({ group, input: ref, resolved: { handle: ref.handle, id: null }, status: "partial", items_total: 0, pages: 0 });
      limitations.push(`${group}: not started before the time budget ran out.`);
      return;
    }
    const rows = historyRows(ref.handle, 12);
    const result = envelope("tiktok-public", "list_account_posts", { handle: ref.handle, follower_count: 1000, rows, more_available: true });
    calls.push({ tool: "tiktok_list_account_posts", parameters: { handle: `@${ref.handle}`, limit: Math.max(5, args.history.max_items) }, group, attempts: 1, result });
    accounts.push({ group, input: ref, resolved: { handle: ref.handle, id: null }, status: "completed", items_total: rows.length, pages: 1 });
  });
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_account_history", status: skip.length ? "partial" : "completed", calls,
    summary: { accounts }, coverage: { deadline_reached: skip.length > 0, unfinished: [], provider_calls: calls.length }, limitations };
}

test("research-tiktok-trends: discover and rank each hand off one composite call, results go back to their original slots by group, and accounts missing history continue as usual", async (t) => {
  const run = await newRun(t, RTT);
  assert.equal(drive(RTT, run, ["start"]).exit, 0);
  await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ mode: "current_popular", niche: "bead craft ideas", platforms: ["tiktok"], locale: { region: "US", language: null, named_in_ask: "in the US" }, formats: ["tiktok_video"] }));
  await writeFile(path.join(run, "tiktok-trend-query-plan.json"), JSON.stringify({ intents: [{ search_query: "bead craft ideas" }, { search_query: "perler bead patterns" }] }));
  const discover = ["discover", "--policy", "recent_90d", "--question-file", "-"];
  const handed = drive(RTT, run, discover, "What bead craft videos are trending in the US?");
  assert.equal(handed.exit, 0, handed.stdout + handed.stderr);
  const [call, ...rest] = callsOf(handed.stdout);
  assert.equal(rest.length, 0, "discover hands over exactly one call");
  assert.equal(call.tool, "collect_tiktok_video_candidates");
  assert.ok(validate(call.tool)(call.arguments), JSON.stringify(validate(call.tool).errors));
  const d1 = new Date(Date.now() - DAY).toISOString().slice(0, 10);
  assert.deepEqual(call.arguments, {
    intents: [{ keyword: "bead craft ideas", publish_time: 90 }, { keyword: "perler bead patterns", publish_time: 90 }],
    sorts: [0, 1], count: 30, region: "US", top_contents: { date: d1, fallback_days: 1 }, delivery: "download",
  });
  await stage(RTT, run, call.tool, candidatesResult(call.arguments));

  const placed = drive(RTT, run, [...discover, "--placed"]);
  assert.equal(placed.exit, 0, placed.stdout + placed.stderr);
  assert.match(placed.stdout, /the D-1 board came back empty; the D-2 board was asked once/);
  const envelopes = JSON.parse(await readFile(path.join(run, "discovery-envelopes.json"), "utf8")).runs;
  assert.deepEqual(Object.keys(envelopes), ["intent-1-relevance", "intent-1-most-liked", "intent-2-relevance", "intent-2-most-liked", "ranked-board-d1", "ranked-board-d2"]);
  const provenance = JSON.parse(await readFile(path.join(run, "discovery-requests.json"), "utf8")).runs;
  assert.deepEqual(provenance["intent-2-most-liked"].params, { keyword: "perler bead patterns", sort_type: 1, count: 30, region: "US", publish_time: 90 });
  assert.equal(provenance["intent-2-most-liked"].request_id, envelopes["intent-2-most-liked"].request_id);
  assert.deepEqual(provenance["ranked-board-d1"].params, { period_end_timestamp: Date.parse(`${d1}T00:00:00Z`) / 1000, period_dimension: 3, country_code: "US", limit: 100 });
  assert.match(placed.stdout, /"gate_scoring"/);
  const items = JSON.parse(await readFile(path.join(run, "trend-relevance-gate-input.json"), "utf8")).items.length;
  assert.equal(items, 6);

  await writeFile(path.join(run, "trend-relevance-gate.tsv"), Array.from({ length: items }, (_, i) => `${i + 1} 90 90`).join("\n") + "\n");
  const ranked = drive(RTT, run, ["rank"]);
  assert.equal(ranked.exit, 0, ranked.stdout + ranked.stderr);
  const [history, ...more] = callsOf(ranked.stdout);
  assert.equal(more.length, 0, "rank hands over exactly one call");
  assert.equal(history.tool, "collect_account_history");
  assert.ok(validate(history.tool)(history.arguments), JSON.stringify(validate(history.tool).errors));
  assert.deepEqual(history.arguments.history, { max_items: 30 });
  assert.equal(history.arguments.platform, "tiktok");
  assert.equal(history.arguments.on_identity_miss, "gap");
  const handles = history.arguments.accounts.map((ref) => ref.handle);
  assert.deepEqual([...handles].sort(), [...AUTHORS].sort());
  // The second-ranked account did not post by the deadline: rank continues as usual, and that account is left with only absolute views.
  await stage(RTT, run, history.tool, historyResult(history.arguments, [handles[1]]));
  const enriched = drive(RTT, run, ["rank", "--placed"]);
  assert.equal(enriched.exit, 0, enriched.stdout + enriched.stderr);
  assert.match(enriched.stdout, new RegExp(`no account history came back for: ${handles[1].replace(/\./g, "\\.")}`));
  const histories = JSON.parse(await readFile(path.join(run, "account-history-envelopes.json"), "utf8")).runs;
  assert.deepEqual(Object.keys(histories), [handles[0], handles[2]]);
  assert.equal(histories[handles[0]].data.handle, handles[0]);
  assert.ok(JSON.parse(await readFile(path.join(run, "public-content-analysis.json"), "utf8")));
  assert.match(enriched.stdout, /trend-research-synthesis/);
});

test("research-tiktok-trends: rank --placed continues as usual when the whole history call is rejected (no result to write)", async (t) => {
  const run = await newRun(t, RTT);
  drive(RTT, run, ["start"]);
  await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ mode: "current_popular", niche: "bead craft ideas", platforms: ["tiktok"], locale: { region: null, language: null }, formats: ["tiktok_video"] }));
  await writeFile(path.join(run, "tiktok-trend-query-plan.json"), JSON.stringify({ intents: [{ search_query: "bead craft ideas" }] }));
  const [call] = callsOf(drive(RTT, run, ["discover", "--policy", "recent_90d"]).stdout);
  assert.equal(call.arguments.region, undefined, "no region is sent when none is known");
  await stage(RTT, run, call.tool, candidatesResult(call.arguments));
  const placed = drive(RTT, run, ["discover", "--policy", "recent_90d", "--placed"]);
  assert.equal(placed.exit, 0, placed.stdout + placed.stderr);
  const items = JSON.parse(await readFile(path.join(run, "trend-relevance-gate-input.json"), "utf8")).items.length;
  await writeFile(path.join(run, "trend-relevance-gate.tsv"), Array.from({ length: items }, (_, i) => `${i + 1} 80 80`).join("\n") + "\n");
  assert.equal(callsOf(drive(RTT, run, ["rank"]).stdout).length, 1);
  const thin = drive(RTT, run, ["rank", "--placed"]);
  assert.equal(thin.exit, 0, thin.stdout + thin.stderr);
  assert.match(thin.stdout, /no account history came back for: .*those accounts keep absolute plays only/);
  assert.deepEqual(JSON.parse(await readFile(path.join(run, "account-history-envelopes.json"), "utf8")), { runs: {} });
});

test("analyze-tiktok-competitors: discover and content each hand off one composite call; still stops when account history is missing", async (t) => {
  const run = await newRun(t, TTC);
  assert.equal(drive(TTC, run, ["start"]).exit, 0);
  await writeFile(path.join(run, "competitor-research-request.json"), JSON.stringify({
    subject: { name: "Bead craft studio", description: "TikTok account teaching bead crafts to beginners" }, platforms: ["tiktok"],
    locale: { region: "US", language: "en" }, formats: ["tiktok_video"], discovery_mode: "auto", competitor_refs: [] }));
  await writeFile(path.join(run, "tiktok-query-plan.json"), JSON.stringify({ intents: [{ search_query: "bead craft ideas" }, { search_query: "perler bead patterns" }] }));
  const handed = drive(TTC, run, ["discover", "--region", "US"]);
  assert.equal(handed.exit, 0, handed.stdout + handed.stderr);
  const [call, ...rest] = callsOf(handed.stdout);
  assert.equal(rest.length, 0);
  assert.ok(validate(call.tool)(call.arguments), JSON.stringify(validate(call.tool).errors));
  assert.deepEqual(call.arguments, {
    intents: [{ keyword: "bead craft ideas", publish_time: 30 }, { keyword: "perler bead patterns", publish_time: 30 }],
    sorts: [0, 1], count: 30, region: "US", delivery: "download",
  });
  await stage(TTC, run, call.tool, candidatesResult(call.arguments));
  const placed = drive(TTC, run, ["discover", "--region", "US", "--placed"]);
  assert.equal(placed.exit, 0, placed.stdout + placed.stderr);
  const envelopes = JSON.parse(await readFile(path.join(run, "discovery-envelopes.json"), "utf8")).runs;
  assert.deepEqual(Object.keys(envelopes), ["intent-1-relevance", "intent-1-most-liked", "intent-2-relevance", "intent-2-most-liked"]);
  assert.equal(envelopes["intent-2-relevance"].data.query, "perler bead patterns");
  const accounts = JSON.parse(await readFile(path.join(run, "tiktok-competitor-discovery-input.json"), "utf8")).items.length;
  assert.equal(accounts, AUTHORS.length);

  await writeFile(path.join(run, "tiktok-competitor-discovery-gate.tsv"), Array.from({ length: accounts }, (_, i) => `${i + 1} direct 90 90 90 90`).join("\n") + "\n");
  const content = drive(TTC, run, ["content"]);
  assert.equal(content.exit, 0, content.stdout + content.stderr);
  const [history, ...more] = callsOf(content.stdout);
  assert.equal(more.length, 0);
  assert.equal(history.tool, "collect_account_history");
  assert.ok(validate(history.tool)(history.arguments), JSON.stringify(validate(history.tool).errors));
  assert.deepEqual({ ...history.arguments, accounts: undefined }, { platform: "tiktok", accounts: undefined, history: { max_items: 100 }, profile: false, on_identity_miss: "gap", delivery: "download" });
  assert.deepEqual([...history.arguments.accounts.map((ref) => ref.handle)].sort(), [...AUTHORS].sort());

  // One account did not respond: as with one history missing before, content stops and does not substitute another account.
  await stage(TTC, run, history.tool, historyResult(history.arguments, [history.arguments.accounts[0].handle]));
  const stopped = drive(TTC, run, ["content", "--placed"]);
  assert.equal(stopped.exit, 2, stopped.stdout);
  assert.match(stopped.stdout, /no complete host record of the account histories/);

  // The backend runs once more (complete): after placement, content finishes the snapshot and the evidence projection.
  await stage(TTC, run, history.tool, historyResult(history.arguments));
  const done = drive(TTC, run, ["content", "--placed"]);
  assert.equal(done.exit, 0, done.stdout + done.stderr);
  const histories = JSON.parse(await readFile(path.join(run, "account-history-envelopes.json"), "utf8")).runs;
  assert.deepEqual(Object.keys(histories), history.arguments.accounts.map((ref) => ref.handle));
  assert.match(done.stdout, /competitor-research-synthesis/);
});
