// creator_library.py shared by start-with-kabo, pick-daily-viral-videos, and review-new-posts: offline
// tests, no network.
// Covers: the three copies are identical; the profile and daily picks only read backend tool results
// (prepare_creator_profile, get_creator_profile,
// get_for_you_videos) and derive nothing locally; the display limits and every status branch of the daily
// picks; selection for the 24-hour review and the equal-age baseline;
// the account recap; the first review run (or a host that keeps no files) builds the library itself, and
// reviews still run with no pillars;
// and the whole path history-request -> stage combined result -> snapshot -> ingest.
// The two new backend tools are not live yet: the result shapes here are built from the agreed contract;
// real-host integration has to wait until the backend ships.
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const owners = ["start-with-kabo", "pick-daily-viral-videos", "review-new-posts"];
// The three copies are byte-identical (guarded by the first test); use the review copy, because only it
// carries the static_host allowlist for data fetching and the snapshot assembly script.
const skillDir = path.join(root, "skills/review-new-posts/scripts");
const cli = path.join(skillDir, "creator_library.py");
const options = { encoding: "utf8", maxBuffer: 4 * 1024 * 1024, timeout: 30_000 };
const run = (...args) => JSON.parse(execFileSync("python3", ["-I", "-B", cli, ...args], options));
const refuse = (...args) => spawnSync("python3", ["-I", "-B", cli, ...args], options);

async function workspace(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-library-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  return temp;
}

// A minimal snapshot with the same shape as the build_public_snapshot.py output: only the fields used by
// the review and pillars.
const metric = (value) => value === null ? { status: "unavailable", value: null } : { status: value ? "available" : "zero", value };
function item(id, publishedAt, views, extra = {}) {
  return { content_id: id, creator_id: extra.creator ?? "c-1", format: extra.format ?? "instagram_reel", published_at: publishedAt,
    url: `https://www.instagram.com/reel/${id}/`, title: extra.title ?? `post ${id}`, duration_seconds: extra.duration,
    metrics: { views: metric(views), likes: metric(extra.likes ?? 10), comments: metric(extra.comments ?? 1),
      shares: metric(null), saves: metric(null) } };
}
async function snapshot(dir, name, observedAt, items, { platform = "instagram", handle = "maker", followers } = {}) {
  const file = path.join(dir, name);
  await writeFile(file, JSON.stringify({ schema_version: "public-content-snapshot.v1", snapshot_id: name,
    observed_at: observedAt, platform, creators: [{ creator_id: "c-1", handle, ...(followers === undefined ? {} : { followers }) }], items }));
  return file;
}
const hoursBefore = (iso, hours) => new Date(Date.parse(iso) - hours * 3_600_000).toISOString().replace(".000Z", "Z");
const hoursAfter = (iso, hours) => hoursBefore(iso, -hours);

// Ten older posts that have stabilized: the views distribution lets the top six account for most of it.
function history(observedAt) {
  const rows = [];
  for (let i = 0; i < 10; i++)
    rows.push(item(`old${i}`, hoursBefore(observedAt, 100 + i * 24), i < 6 ? 1000 + i * 100 : 400));
  return rows;
}

// Result shape of get_creator_profile (effective: true): only the fields the script reads.
const signature = (id, name, share, extra = {}) => ({ id, name, topic: `topic of ${name}`, approach: "talking head", share,
  medianMultiplier: 1.8, contentCount: 9, format: "short_video", weight: share,
  seedTerms: extra.terms ?? [`${name} query`, `${name} second`], seedHashtags: [], seedSounds: [],
  representativeContent: [{ contentId: `${id}-ex`, sourceUrl: `https://www.instagram.com/reel/${id}ex/`, title: `example of ${name}`, views: 9000, multiplier: 2.1 }] });
const profileResult = (items, { niche = "Short breakdowns of viral videos for small creators", version = 3 } = {}) => ({
  structuredContent: {
    account: { id: "acc-1", platform: "instagram", handle: "maker", displayName: "Maker", dataState: "available" },
    diagnosis: { insight: { niche, headline: "h" } },
    effectiveContentProfile: { base: { generatedAt: "2026-10-01T00:00:00Z", ruleVersion: "r" }, edited: true,
      preferences: { status: "applied", updatedAt: null, version }, hiddenSignatureContent: [{ id: "sc9", name: "Giveaways" }],
      language: { primary: "en", accepted: [], confidence: "high", source: "profile" }, signatureContent: items },
  },
});

test("the three creator_library.py copies are identical verbatim; the snapshot assembly script of onboarding and review matches that of the account review; daily picks carry no data-fetch script", async () => {
  const copies = new Set(await Promise.all(owners.map(id => readFile(path.join(root, "skills", id, "scripts/creator_library.py"), "utf8"))));
  assert.equal(copies.size, 1);
  const reference = await readFile(path.join(root, "skills/review-creator-account/scripts/build_public_snapshot.py"), "utf8");
  // Onboarding reads posts locally again (1.0.40: pillars proposed locally); like the review, it carries the
  // snapshot assembly script and the fetch allowlist.
  for (const id of ["review-new-posts", "start-with-kabo"])
    assert.equal(await readFile(path.join(root, "skills", id, "scripts/build_public_snapshot.py"), "utf8"), reference, id);
  const probe = "import json, runpy, sys\nm = runpy.run_path(sys.argv[1])\nprint(json.dumps([sorted(m['CONNECTOR_TOOLS'].values()), sorted(m['HANDED_COMPOSITES'])]))";
  const startTables = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, path.join(root, "skills/start-with-kabo/scripts/static_host.py")], options));
  assert.deepEqual(startTables[1], ["collect_account_history", "collect_video_media"]);
  assert.ok(startTables[0].includes("public_video_fetch_transcript"));
  // The daily picks do not read post history: no snapshot assembly script, and static_host accepts no fetch
  // results either; it only creates the run directory.
  for (const id of ["pick-daily-viral-videos"]) {
    await assert.rejects(access(path.join(root, "skills", id, "scripts/build_public_snapshot.py")));
    const probe = "import json, runpy, sys\nm = runpy.run_path(sys.argv[1])\nprint(json.dumps([sorted(m['CONNECTOR_TOOLS']), sorted(m['AGGREGATE_TOOLS']), sorted(m['HANDED_COMPOSITES'])]))";
    const tables = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, path.join(root, "skills", id, "scripts/static_host.py")], options));
    assert.deepEqual(tables, [[], [], []], id);
  }
});

// Deleted local search and old commands: the instructions of the three Skills must no longer reference
// them. Since 1.0.40 onboarding proposes pillars locally again,
// so pillar-related commands may appear only in start-with-kabo.
const REMOVED = ["pick-request", "candidates --", "schedule.json", "set-profile", "collect_instagram_trend_candidates",
  "collect_youtube_trend_candidates", "enrich_instagram_shortlist", "enrich_youtube_shortlist", "evidence_strength",
  "creator_library.py' pick "];
const LOCAL_PROPOSAL = ["propose-pillars", "save-pillars", "media-request", "transcripts", "clusters.json", "confirmed.json",
  "collect_video_media", "creator_library.py' posts"];

test("the three Skills' instructions no longer reference removed commands, files, or local derivation tools; picks use only get_for_you_videos, and the profile goes only through prepare_creator_profile and get_creator_profile", async () => {
  const texts = {};
  for (const id of owners) {
    const files = [path.join(root, "skills", id, "SKILL.md")];
    for (const name of ["pillars.md", "profile-edits.md", "host-schedules.md", "review-format.md"]) {
      const file = path.join(root, "skills", id, "references", name);
      try { await access(file); files.push(file); } catch { /* this Skill has no such instruction file */ }
    }
    texts[id] = (await Promise.all(files.map(file => readFile(file, "utf8")))).join("\n");
    for (const word of REMOVED) assert.equal(texts[id].includes(word), false, `${id} still references ${word}`);
    if (id !== "start-with-kabo") for (const word of LOCAL_PROPOSAL) assert.equal(texts[id].includes(word), false, `${id} references ${word}`);
  }
  const allowed = (id) => texts[id].match(/^allowed-tools: (.*)$/m)[1].split(" ");
  assert.deepEqual(allowed("pick-daily-viral-videos").sort(), ["get_for_you_videos", "list_connected_accounts"]);
  for (const name of ["prepare_creator_profile", "get_creator_profile", "update_content_preferences", "get_for_you_videos", "connect_public_account"])
    assert.ok(allowed("start-with-kabo").includes(name), name);
  for (const name of ["collect_account_history", "collect_video_media", "get_research_data_download"]) assert.ok(allowed("start-with-kabo").includes(name), name);
  // After kabo#2185 pinned it: the declare_pillars and get_creator_profile pillars input and the
  // declaredPillars output are in the contract, with shapes matching the script.
  {
    const tools = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map(tool => [tool.name, tool]));
    const write = tools.get("update_content_preferences").inputSchema;
    assert.ok(write.properties.action.enum.includes("declare_pillars"));
    assert.deepEqual(write.properties.pillars.items.required.sort(), ["definition", "name", "searchPhrases"]);
    assert.equal(tools.get("get_creator_profile").inputSchema.properties.pillars.type, "boolean");
    const item = tools.get("get_creator_profile").outputSchema.properties.declaredPillars.items;
    assert.deepEqual([item.properties.name.maxLength, item.properties.definition.maxLength, item.properties.searchPhrases.maxItems,
      item.properties.searchPhrases.items.maxLength], [60, 200, 3, 60]);
  }
  // Propose locally, sync once, replace the whole set, report failures honestly; local numbers are not Kabo's
  // statistical conclusions.
  assert.match(texts["start-with-kabo"], /## 5\. Save the pillars to Kabo, once/);
  assert.match(texts["start-with-kabo"], /replaces the whole set Kabo holds/);
  assert.match(texts["start-with-kabo"], /saved on this computer only, not in Kabo/);
  assert.match(texts["start-with-kabo"], /\*\*not Kabo's statistics\*\*/);
  assert.match(texts["start-with-kabo"], /it does not recommend or reject anything/);
  assert.match(texts["start-with-kabo"], /"pillars": true/);
  assert.match(texts["start-with-kabo"], /do not wait for the profile/);
  assert.match(texts["review-new-posts"], /A scheduled run never\s+writes to Kabo/);
  assert.ok(allowed("review-new-posts").includes("update_content_preferences"));
  // The review stays as it was: it reads history and comments itself, and reads pillars from the profile.
  for (const name of ["collect_account_history", "get_creator_profile", "list_connected_accounts"]) assert.ok(allowed("review-new-posts").includes(name), name);
  // Opening: the script gives two sentences, and the instructions also say two sentences plus one question;
  // no longer promise to show account facts "within a minute".
  assert.equal(run("opening").tell_creator_now.length, 2);
  assert.match(texts["start-with-kabo"], /two short messages and one question/);
  assert.doesNotMatch(texts["start-with-kabo"], /within about a minute|three short messages/);
  // When the backend cannot infer the niche, ask the creator only once and retry with their own words as
  // niche; the model does not make one up for the creator.
  assert.match(texts["start-with-kabo"], /set to the creator's own words/);
  assert.match(texts["start-with-kabo"], /Never write the niche\s+yourself/);
  // The wait limit for picks is written in the instructions and matches the script (onboarding no longer
  // waits for the profile).
  assert.match(texts["pick-daily-viral-videos"], /at most 3\s+more calls and at most 10 minutes/);
  // Handling of missing write permission is written in the instructions; scheduled tasks run only the two
  // read-only or data-fetching Skills and call no write tools.
  assert.match(texts["start-with-kabo"], /`ask_write_access`/);
  assert.match(texts["start-with-kabo"], /The scheduled jobs run only `pick-daily-viral-videos` and `review-new-posts`/);
  for (const id of ["pick-daily-viral-videos", "review-new-posts"]) assert.equal(allowed(id).includes("prepare_creator_profile"), false, id);
  // The two new tools are in the pinned tools/list, with scopes matching the Skill's compatibility; all input
  // keys are in inputSchema.
  const pinned = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map(tool => [tool.name, tool]));
  const scopes = (name) => pinned.get(name).securitySchemes.flatMap(scheme => scheme.scopes);
  assert.deepEqual(scopes("get_for_you_videos"), ["workspace:read"]);
  assert.deepEqual(scopes("prepare_creator_profile"), ["workspace:write"]);
  assert.deepEqual(Object.keys(pinned.get("prepare_creator_profile").inputSchema.properties).sort(), ["account_id", "niche"]);
  assert.deepEqual(pinned.get("prepare_creator_profile").inputSchema.required, ["account_id"]);
  assert.deepEqual(pinned.get("prepare_creator_profile").outputSchema.properties.status.enum, ["ready", "generating", "insufficient_posts", "niche_required", "failed"]);
  assert.deepEqual(pinned.get("get_for_you_videos").outputSchema.properties.status.enum, ["ready", "generating", "not_eligible", "failed"]);
  assert.deepEqual(pinned.get("get_for_you_videos").outputSchema.properties.reason.anyOf[0].enum,
    ["no_linked_account", "no_public_videos", "profile_insufficient", "language_unknown", "unavailable"]);
  for (const id of owners) for (const name of allowed(id)) assert.ok(pinned.has(name), `${id}: ${name} is not in the pinned tools/list`);
  // Every review run refreshes pillars from the profile, and keeps the old values if it cannot read them.
  assert.match(texts["review-new-posts"], /refresh-pillars --library '<library directory>' --profile profile\.json/);
  assert.match(texts["review-new-posts"], /--unavailable/);
  // How to write unknown authors and long videos is spelled out in the instructions, not left to the model to
  // improvise.
  assert.match(texts["pick-daily-viral-videos"], /author not supplied/);
  assert.match(texts["pick-daily-viral-videos"], /`format` is `long`/);
  assert.match(texts["pick-daily-viral-videos"], /same_video_in_another_window/);
  assert.match(texts["pick-daily-viral-videos"], /below_views_floor/);
  // kabo#2181: fetch author_id with include; only when include is rejected as an invalid input, drop it and
  // retry once.
  assert.match(texts["pick-daily-viral-videos"], /`\{"account_id": "<id>", "include": \["author_id"\]\}`/);
  assert.match(texts["pick-daily-viral-videos"], /refused as invalid input because of `include`[\s\S]*call once more with `\{"account_id": "<id>"\}` only[\s\S]*Drop `include` for no other error, and only once/);
  assert.match(texts["start-with-kabo"], /"include": \["author_id"\]/);
  assert.match(texts["pick-daily-viral-videos"], /exactly as the `author` field gives it/);
  {
    const forYouTool = JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.find(tool => tool.name === "get_for_you_videos");
    assert.deepEqual(forYouTool.inputSchema.properties.include.items.enum, ["author_id"]);
    assert.deepEqual(Object.keys(forYouTool.inputSchema.properties).sort(), ["account_id", "include"]);
    const item = forYouTool.outputSchema.properties.windows.anyOf[0].properties["7d"].items;
    assert.ok(item.properties.author_id, "author_id is in the pinned output");
    assert.equal(item.required.includes("author_id"), false, "author_id is a gated output, not a required field");
  }
  assert.match(texts["pick-daily-viral-videos"], /10% of the views of that list's top video/);
  assert.match(texts["pick-daily-viral-videos"], /last-30-days list/);
  // Ask explicitly once before binding.
  assert.match(texts["start-with-kabo"], /Ask before linking/);
  assert.doesNotMatch(texts["start-with-kabo"], /unless the creator objected/);
  // Basis of the picks' evidence: do not state a multiple and do not state a matched pillar.
  assert.doesNotMatch(texts["pick-daily-viral-videos"], /times what @author usually gets|author_typical_views|pillar it matches/);
});

test("building the library records the bind time; a post published afterwards is reviewed once after 24 hours, and the equal-age baseline comes from other posts", async t => {
  const temp = await workspace(t);
  const located = run("path", "--workspace", temp, "--platform", "instagram", "--handle", "@Maker");
  const library = located.library;
  assert.ok(library.endsWith(path.join("kabo-library", "instagram-maker")));
  // path gives only a directory: the two Skills run unattended, so it cannot carry anything to be said to the
  // creator.
  assert.deepEqual(Object.keys(located).sort(), ["exists", "library"]);
  assert.equal(located.exists, false);
  const t0 = "2026-10-20T08:00:00Z";
  const first = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0), { followers: 1000 }), "--handle", "maker");
  assert.equal(first.created, true);
  assert.deepEqual(first.new_tracked_posts, []);
  assert.deepEqual(first.due, []);
  assert.equal(first.followers_now, 1000);
  // Posts from before binding never enter the review; other people's posts and image posts do not enter the
  // library; nothing is due before 24 hours.
  const t1 = "2026-10-20T20:00:00Z";
  const young = await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-20T08:20:00Z", 300),
    item("guest", "2026-10-20T08:25:00Z", 999, { creator: "c-2" }), item("photo", "2026-10-20T08:26:00Z", null, { format: "instagram_feed" })]);
  const second = run("ingest", "--library", library, "--snapshot", young);
  assert.deepEqual(second.new_tracked_posts, ["new1"]);
  assert.deepEqual(second.due, []);
  const stored = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  assert.deepEqual(Object.keys(stored).filter(id => ["guest", "photo"].includes(id)), []);
  assert.equal(run("ingest", "--library", library, "--snapshot", young).observations_added, 0);
  // Optional time points: posts at least 1 hour old but under 24 hours appear only with --with-optional.
  assert.deepEqual(run("due", "--library", library, "--with-optional").due.map(row => [row.content_id, row.checkpoint]), [["new1", "1h"]]);

  const t2 = "2026-10-21T10:00:00Z";
  const third = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s2.json", t2, [...history(t0), item("new1", "2026-10-20T08:20:00Z", 900)]));
  assert.deepEqual(third.due.map(row => [row.content_id, row.checkpoint, row.late]), [["new1", "24h", false]]);
  const facts = run("review-facts", "--library", library, "--content-id", "new1", "--checkpoint", "24h");
  assert.equal(facts.age_hours, 25.67);
  assert.equal(facts.same_age_baseline.multiple, null);
  assert.equal(facts.typical_settled.posts, 10);
  assert.match(facts.limits[0], /not with posts at the same age/);
  const report = path.join(temp, "r.md");
  await writeFile(report, "review");
  run("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "24h", "--report", report);
  assert.match(refuse("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "24h", "--report", report).stderr, /already recorded/);
  assert.deepEqual(run("due", "--library", library).due, []);

  // Three earlier posts were measured in the 24-48 hour band, so the fourth one has an equal-age baseline.
  const peers = [1, 2, 3].map(index => item(`peer${index}`, `2026-10-21T0${index}:00:00Z`, index * 1000));
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s3.json", "2026-10-22T08:00:00Z", [...history(t0), ...peers]));
  const rows = [...history(t0), ...peers, item("new2", "2026-10-21T19:00:00Z", 4000)];
  const fourth = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s4.json", "2026-10-22T20:00:00Z", rows));
  assert.ok(fourth.due.some(row => row.content_id === "new2" && row.checkpoint === "24h"));
  const compared = run("review-facts", "--library", library, "--content-id", "new2", "--checkpoint", "24h");
  // The equal-age baseline is the readings of other posts in the 24-48 hour band: the three peers plus new1,
  // which was reviewed earlier.
  assert.equal(compared.same_age_baseline.posts, 4);
  assert.equal(compared.same_age_baseline.median_views, 1500);
  assert.equal(compared.same_age_baseline.multiple, 2.67);
  assert.deepEqual(compared.limits, []);
});

test("a late review is marked late; 1-hour and 7-day reviews appear only when requested, and the 7-day review follows the 24-hour one", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const rows = [...history(t0), item("slow", "2026-10-20T09:00:00Z", 500)];
  const t1 = "2026-10-23T08:00:00Z";
  const late = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s1.json", t1, rows));
  assert.deepEqual(late.due.map(row => [row.content_id, row.late]), [["slow", true]]);
  const facts = run("review-facts", "--library", library, "--content-id", "slow", "--checkpoint", "24h");
  assert.ok(facts.limits.some(line => /late/.test(line)));
  assert.equal(facts.same_age_baseline.multiple, null);
  const report = path.join(temp, "r.md");
  await writeFile(report, "review");
  run("record-review", "--library", library, "--content-id", "slow", "--checkpoint", "24h", "--report", report);
  assert.deepEqual(run("due", "--library", library, "--with-optional").due, []);
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s2.json", "2026-10-28T08:00:00Z", rows));
  assert.deepEqual(run("due", "--library", library).due, []);
  assert.deepEqual(run("due", "--library", library, "--with-optional").due.map(row => [row.content_id, row.checkpoint]), [["slow", "7d"]]);
});

test("when TikTok gives only a date: the time in the id is used only if it falls on the same day, and scheduled posts are aged from the first time they were seen", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const observed = "2026-10-29T10:00:00Z";
  const made = (unix) => (BigInt(unix) << 32n).toString();
  const sameDay = made(Date.parse("2026-10-29T03:05:57Z") / 1000);
  const scheduled = made(Date.parse("2026-10-25T12:16:32Z") / 1000);
  const tiktok = (id) => ({ ...item(id, "2026-10-29T00:00:00Z", 50), format: "tiktok_video" });
  await snapshot(temp, "t0.json", "2026-10-28T10:00:00Z", [{ ...item(made(1792900000), "2026-10-27T05:00:00Z", 80), format: "tiktok_video" }], { platform: "tiktok" });
  run("ingest", "--library", library, "--snapshot", path.join(temp, "t0.json"), "--handle", "maker");
  const result = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "t1.json", observed, [tiktok(sameDay), tiktok(scheduled)], { platform: "tiktok" }));
  assert.deepEqual(result.new_tracked_posts.sort(), [sameDay, scheduled].sort());
  const posts = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  assert.equal(posts[sameDay].published_at, "2026-10-29T03:05:57Z");
  assert.equal(posts[sameDay].published_at_source, "video_id");
  assert.equal(posts[scheduled].published_at_source, "date_only");
  assert.equal(posts[scheduled].observations[0].age_hours, 0);
  assert.equal(posts[scheduled].observations[0].age_from, "first_seen");
});

test("the profile only organizes backend results: visible main content becomes pillars by share, with evidence, edit context, and items the creator hid; if there are none, say so", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "profile.json");
  await writeFile(file, JSON.stringify(profileResult([signature("sc2", "Charisma tips", 0.3), signature("sc1", "Viral breakdowns", 0.55), signature("sc3", "Vlogs", 0.1)])));
  const proposal = run("profile-pillars", "--profile", file);
  assert.equal(proposal.status, "ok");
  assert.equal(proposal.niche, "Short breakdowns of viral videos for small creators");
  assert.equal(proposal.profile_edited, true);
  assert.deepEqual(proposal.candidates.map(row => row.id), ["viral-breakdowns", "charisma-tips", "vlogs"]);
  assert.equal(proposal.candidates[0].source, "kabo_profile");
  assert.equal(proposal.candidates[0].profile_item_id, "sc1");
  assert.equal(proposal.candidates[0].evidence.share_of_posts, 0.55);
  assert.equal(proposal.candidates[0].evidence.examples[0].url, "https://www.instagram.com/reel/sc1ex/");
  // Pillars no longer carry search terms: the daily picks no longer search by pillar.
  assert.equal("search_queries" in proposal.candidates[0], false);
  assert.deepEqual(proposal.hidden_by_creator, ["Giveaways"]);
  assert.deepEqual(proposal.update_context, { account_id: "acc-1", expected_version: 3, basis: "2026-10-01T00:00:00Z" });
  assert.deepEqual(proposal.advice, []);
  assert.equal("tell_creator_now" in proposal, false);
  // Only one entry and the backend marks it no_qualifying_group: still a valid pillar; do not tell the model
  // to look for another in the posts.
  const single = path.join(temp, "single.json");
  const one = profileResult([signature("sc9", "Only pillar", 0.4)]);
  one.structuredContent.effectiveContentProfile.signatureContentStatus = "no_qualifying_group";
  await writeFile(single, JSON.stringify(one));
  const lone = run("profile-pillars", "--profile", single);
  assert.equal(lone.advice.length, 1);
  assert.match(lone.advice[0], /present it as a valid pillar/);
  // A result with only content[0].text is also accepted.
  await writeFile(single, JSON.stringify({ content: [{ type: "text", text: JSON.stringify(one.structuredContent) }] }));
  assert.equal(run("profile-pillars", "--profile", single).candidates.length, 1);
  // With no signature content, do not fabricate any and do not tell the model to cluster by itself.
  const empty = path.join(temp, "empty.json");
  await writeFile(empty, JSON.stringify(profileResult([])));
  const none = run("profile-pillars", "--profile", empty);
  assert.equal(none.status, "no_signature_content");
  assert.deepEqual(none.candidates, []);
  assert.match(none.note, /never group the posts yourself/);
  // A result the host marked isError is not read as a profile.
  await writeFile(empty, JSON.stringify({ isError: true, content: [{ type: "text", text: "not_found" }] }));
  assert.match(refuse("profile-pillars", "--profile", empty).stderr, /refused/);
});

// Final output of prepare_creator_profile (kabo#2176): all fields are always present, null when not
// applicable.
const prepared = (status, extra = {}) => ({ structuredContent: { status, account_id: "00000000-0000-4000-8000-000000000001",
  job_id: null, failure_code: null, retryable: null, retry_after_seconds: null, ...extra } });

test("niche is read first from the top-level niche of get_creator_profile, then falls back to the two places in the diagnosis; if none has it, it is null; building the library and refreshing pillars use the same reading", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "profile.json");
  const items = [signature("sc1", "Physics explained", 0.6)];
  const shaped = (top, diagnosis) => {
    const value = profileResult(items);
    value.structuredContent.niche = top;
    value.structuredContent.nicheId = top ? "science_education" : null;
    value.structuredContent.diagnosis = diagnosis;
    return value;
  };
  // Codex measured (@veritasium): the top level has the niche, diagnosis is empty.
  await writeFile(file, JSON.stringify(shaped("Science education", {})));
  assert.equal(run("profile-pillars", "--profile", file).niche, "Science education");
  // Top level takes precedence over diagnosis.
  await writeFile(file, JSON.stringify(shaped("Science education", { insight: { niche: "Old diagnosis niche" } })));
  assert.equal(run("profile-pillars", "--profile", file).niche, "Science education");
  // Only diagnosis has it: read from the original two places.
  await writeFile(file, JSON.stringify(shaped(null, { insight: { niche: "From insight" } })));
  assert.equal(run("profile-pillars", "--profile", file).niche, "From insight");
  await writeFile(file, JSON.stringify(shaped("  ", { accountReview: { sections: { niche: { label: "From review" } } } })));
  assert.equal(run("profile-pillars", "--profile", file).niche, "From review");
  // Neither has it: null, do not make one up.
  await writeFile(file, JSON.stringify(shaped(null, null)));
  assert.equal(run("profile-pillars", "--profile", file).niche, null);
  // review-new-posts builds the library and refreshes pillars through the same function, which also reads the
  // top-level niche.
  await writeFile(file, JSON.stringify(shaped("Science education", {})));
  const library = path.join(temp, "lib");
  run("bootstrap", "--library", library, "--platform", "youtube", "--handle", "veritasium", "--profile", file);
  assert.equal(run("show", "--library", library).niche.text, "Science education");
  await writeFile(file, JSON.stringify(shaped("Physics and engineering", {})));
  run("refresh-pillars", "--library", library, "--profile", file);
  assert.equal(run("show", "--library", library).niche.text, "Physics and engineering");
});

test("prepare_creator_profile: ready reads the profile; generating waits strictly per retry_after, at most 8 more checks after the first and no more than 480 seconds in total; niche_required asks once for the field and retries with niche; everything else proceeds as usual", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "prepare.json");
  const status = async (value, ...flags) => { await writeFile(file, JSON.stringify(value)); return run("profile-status", "--result", file, ...flags); };
  assert.equal((await status(prepared("ready"))).action, "read_profile");
  const first = await status(prepared("generating", { job_id: "job-1", retry_after_seconds: 60 }));
  assert.deepEqual([first.action, first.wait_seconds, first.next_flags], ["wait", 60, { "--attempt": 2, "--waited": 60 }]);
  assert.match(first.tell_creator_now, /few minutes/);
  // The backend uses a 60-second tier: 8 re-queries is exactly 480 seconds; stop after the 8th.
  let flags = { attempt: 1, waited: 0 }, waits = 0;
  for (;;) {
    const step = await status(prepared("generating", { retry_after_seconds: 60 }), "--attempt", String(flags.attempt), "--waited", String(flags.waited));
    if (step.action !== "wait") { assert.equal(step.action, "continue_without_profile"); assert.match(step.tell_creator_now, /not ready yet/); break; }
    waits += 1;
    flags = { attempt: step.next_flags["--attempt"], waited: step.next_flags["--waited"] };
  }
  assert.deepEqual([waits, flags.waited], [8, 480]);
  // Do not shorten the wait the backend gives: if the remaining budget cannot fit the next wait, stop and do
  // not query early.
  assert.equal((await status(prepared("generating", { retry_after_seconds: 120 }), "--attempt", "3", "--waited", "400")).action, "continue_without_profile");
  // When retry_after is not given, use 60 seconds.
  assert.equal((await status(prepared("generating"), "--attempt", "2", "--waited", "60")).wait_seconds, 60);

  // niche_required: ask one question; once niche has been supplied, do not ask again if it recurs, move on.
  const ask = await status(prepared("niche_required"));
  assert.equal(ask.action, "ask_niche");
  assert.match(ask.tell_creator_now, /can't tell your niche/);
  assert.match(ask.question, /one sentence/);
  assert.match(ask.then, /niche set to the creator's own words.*--niche-sent/);
  const again = await status(prepared("niche_required"), "--niche-sent");
  assert.equal(again.action, "continue_without_profile");
  assert.match(again.tell_creator_now, /no content pillars for now/);
  // After retrying with niche it enters generating again: count from the start and poll as usual.
  assert.equal((await status(prepared("generating", { retry_after_seconds: 60 }), "--attempt", "1", "--waited", "0", "--niche-sent")).action, "wait");

  const thin = await status(prepared("insufficient_posts", { retry_after_seconds: 86000 }));
  assert.equal(thin.action, "continue_without_profile");
  assert.match(thin.tell_creator_now, /enough videos/);
  assert.equal(thin.retry_after_seconds, 86000);
  // kabo#2180: an occasional execution failure (retryable=true) is not "not enough posts": call again after
  // retry_after, the backend reruns automatically and returns generating,
  // sharing the polling limit with generating.
  const flaky = await status(prepared("failed", { failure_code: "classification_unavailable", retryable: true, retry_after_seconds: 42 }));
  assert.deepEqual([flaky.action, flaky.wait_seconds, flaky.next_flags], ["wait", 42, { "--attempt": 2, "--waited": 42 }]);
  assert.match(flaky.tell_creator_now, /couldn't sort them into content pillars this time; it is trying again/);
  assert.doesNotMatch(flaky.tell_creator_now, /enough videos/);
  const otherCode = await status(prepared("failed", { failure_code: "model_invalid_output", retryable: true, retry_after_seconds: 10 }), "--attempt", "2", "--waited", "42");
  assert.equal(otherCode.action, "wait");
  assert.match(otherCode.tell_creator_now, /is trying again\.$/);
  assert.equal(otherCode.failure_code, "model_invalid_output");
  // Automatic rerun: returns generating (when For you is in flight, job_id is null; poll as usual), then ready.
  const rerun = await status(prepared("generating", { job_id: null, retry_after_seconds: 60 }), "--attempt", "3", "--waited", "52");
  assert.deepEqual([rerun.action, rerun.wait_seconds], ["wait", 60]);
  assert.equal((await status(prepared("ready"), "--attempt", "4", "--waited", "112")).action, "read_profile");
  // A retryable failure is bound by the same limit: after 8 queries or when the wait budget is insufficient,
  // stop retrying and move on.
  const exhausted = await status(prepared("failed", { failure_code: "classification_unavailable", retryable: true, retry_after_seconds: 30 }), "--attempt", "9", "--waited", "300");
  assert.equal(exhausted.action, "continue_without_profile");
  assert.match(exhausted.tell_creator_now, /not ready yet/);
  // Rerun reaches its limit or is not retryable: retryable=false; say there are no pillars for now and
  // roughly how long until a retry is possible; do not call again.
  const failed = await status(prepared("failed", { failure_code: "profile_build_failed", retryable: false, retry_after_seconds: 82800 }));
  assert.equal(failed.action, "continue_without_profile");
  assert.equal(failed.failure_code, "profile_build_failed");
  assert.equal(failed.retry_in, "about 23 hours");
  assert.match(failed.tell_creator_now, /can't show your content pillars now.*again in about 23 hours/);
  assert.equal(failed.reported.failure_code, "profile_build_failed");
  // When it fails at enqueue, retry_after is null: do not invent a time.
  const queued = await status(prepared("failed", { failure_code: "queue_unavailable", retryable: false }));
  assert.equal(queued.retry_in, null);
  assert.doesNotMatch(queued.tell_creator_now, /again in/);
  // An old backend reports a classification failure as insufficient_posts: say it as "not enough posts", do
  // not crash.
  assert.equal((await status(prepared("insufficient_posts", { retry_after_seconds: 86400 }))).action, "continue_without_profile");
  // A status outside the contract and tool errors are both handled as failures, returned as is.
  const odd = await status({ status: "queued_somewhere" });
  assert.deepEqual([odd.status, odd.action, odd.reported.status], ["queued_somewhere", "continue_without_profile", "queued_somewhere"]);
  // The host authorization has no workspace:write: tool error Insufficient scope. First ask the creator to
  // re-authorize, then try once more; if it still fails, continue without the profile.
  const noScope = { isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write is required" }] };
  const askWrite = await status(noScope);
  assert.deepEqual([askWrite.status, askWrite.action, askWrite.reason], ["failed", "ask_write_access", "insufficient_scope"]);
  assert.match(askWrite.tell_creator_now, /Reconnect Kabo in this app and approve it/);
  assert.match(askWrite.no_write_access_line, /can't save your content pillars to Kabo for now.*today's picks don't need it/);
  assert.match(askWrite.then, /--write-retried/);
  const stillNoScope = await status(noScope, "--write-retried");
  assert.equal(stillNoScope.action, "continue_without_profile");
  assert.match(stillNoScope.tell_creator_now, /today's picks don't need it/);
  // The failure_code carried by niche_required (e.g. profile_private) is only passed along as explanation;
  // still ask about the field once.
  const privateProfile = await status(prepared("niche_required", { failure_code: "profile_private", retry_after_seconds: 86400 }));
  assert.deepEqual([privateProfile.action, privateProfile.failure_code], ["ask_niche", "profile_private"]);
  // When another request is inferring the niche, the backend gives 30 seconds: wait 30 seconds as told.
  assert.equal((await status(prepared("generating", { retry_after_seconds: 30 }))).wait_seconds, 30);
  const notFound = await status({ isError: true, content: [{ type: "text", text: "not_found: account is not yours" }] });
  assert.deepEqual([notFound.status, notFound.failure_code], ["failed", "not_found: account is not yours"]);
});

// ---- Only everyday language is used when speaking to the creator (1.0.40): the fixed copy in scripts that
// gets relayed, the actual output of every branch,
// and the quoted example sentences in SKILL.md that prescribe "say it this way to the creator" must not
// contain technical terms, tool names, field names, status codes, or Skill ids.
const PINNED_TOOL_NAMES = JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map(tool => tool.name);
const JARGON = new RegExp(String.raw`\b(backend|server|sync\w*|api|mcp|database|scopes?|tools?|status|library|json|run directory|workspace:\w+|` +
  [...PINNED_TOOL_NAMES, "classification_unavailable", "context_changed", "insufficient_posts", "not_eligible", "niche_required",
   "model_invalid_output", "validation_error", "not_found", "failure_code", "retry_after_seconds", "declaredPillars", "declared_pillars",
   "signatureContent", "signature content", "generating", ...owners, "analyze-content-video", "create-script-and-packaging",
   "remake-viral-video"].map(word => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + String.raw`)\b`, "i");
// Wording and number formats seen in real runs: do not say sample / baseline / reference groups; round
// views to integers with thousands separators, never 1726.0 or an integer of 8+ digits without separators.
const ODD_WORDING = /\b(samples?|baselines?|reference groups?)\b|\d+\.0 views|\d{8,}/i;
const plain = (label, text) => {
  assert.doesNotMatch(String(text), JARGON, `${label}: ${text}`);
  assert.doesNotMatch(String(text), ODD_WORDING, `${label}: ${text}`);
};

test("what is said to the creator contains no technical words: fixed script copy, actual output of each branch, quoted example sentences in SKILL.md", async t => {
  // 1. Fixed copy constants.
  const probe = "import json, runpy, sys\nm = runpy.run_path(sys.argv[1])\nprint(json.dumps({k: m[k] for k in ['OPENING', 'PROFILE_STATUS_LINES', 'SYNC_LINES', 'FOR_YOU_NOT_ELIGIBLE', 'FIRST_READING_LINE']}))";
  const constants = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, cli], options));
  const walk = (label, value) => typeof value === "string" ? plain(label, value)
    : Object.entries(value).forEach(([key, inner]) => walk(`${label}.${key}`, inner));
  walk("constants", constants);

  // 2. The fields in each branch's actual output that are relayed to the creator.
  const temp = await workspace(t);
  const said = [];
  const collect = (output) => { for (const key of ["tell_creator_now", "message", "progress_line", "no_write_access_line", "question", "note_for_creator"])
    if (output[key]) said.push(...[output[key]].flat()); for (const line of output.limits ?? []) said.push(line); return output; };
  const file = path.join(temp, "x.json");
  const as = async (value) => { await writeFile(file, JSON.stringify(value)); return file; };
  for (const value of [prepared("generating", { retry_after_seconds: 60 }), prepared("niche_required", { failure_code: "profile_private" }),
    prepared("insufficient_posts", { retry_after_seconds: 86400 }), prepared("failed", { failure_code: "model_invalid_output", retryable: true, retry_after_seconds: 30 }),
    prepared("failed", { failure_code: "classification_unavailable", retryable: true, retry_after_seconds: 30 }),
    prepared("failed", { failure_code: "profile_build_failed", retryable: false, retry_after_seconds: 7200 }), { status: "weird_status" },
    { isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write" }] }])
    collect(run("profile-status", "--result", await as(value)));
  collect(run("profile-status", "--result", await as(prepared("niche_required")), "--niche-sent"));
  const lib = path.join(temp, "lib");
  for (const value of [forYouResult("generating", { retry_after_seconds: 120 }), forYouResult("not_eligible", { reason: "brand_new_reason" }),
    forYouResult("not_eligible", { reason: "unavailable" }), forYouResult("failed", { failure_code: "collection_failed", retry_after_seconds: 3600 }),
    forYouResult("weird_status"), { isError: true, content: [{ type: "text", text: "validation_error: account_id" }] }])
    collect(run("for-you", "--library", lib, "--result", await as(value), "--date", "2026-11-12"));
  collect(run("for-you", "--library", lib, "--result", await as(forYouResult("generating", { retry_after_seconds: 300 })), "--date", "2026-11-12", "--attempt", "4", "--waited", "500"));
  // The limits of pillar sync and review.
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", lib, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  collect(run("posts", "--library", lib, "--tell"));
  // The binding result, the reference block, and each line of the proposal are covered as well.
  for (const value of [{ isError: true, content: [{ type: "text", text: "conflict: This idempotency key was already used for another request." }] },
    { isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write" }] },
    { structuredContent: { account: { id: "acc-9", bindingVersion: "b" } } }])
    collect(run("connect-result", "--result", await as(value), "--handle", "@MrBeast"));
  const reference = run("profile-pillars", "--profile", await as(profileResult([signature("sc1", "Hooks", 0.32)])));
  for (const row of reference.candidates) said.push(row.say_line);
  await writeFile(path.join(temp, "confirmed.json"), JSON.stringify({ confirmed: true, pillars: [{ name: "Breakdowns", definition: "Why one video worked", search_phrases: ["viral breakdown"], content_ids: ["old0"] }] }));
  run("save-pillars", "--library", lib, "--file", path.join(temp, "confirmed.json"));
  for (const value of [{ isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write" }] }, { isError: true, content: [{ type: "text", text: "invalid_input: action" }] },
    { structuredContent: { effectiveContentProfile: {} } }])
    collect(run("record-sync", "--library", lib, "--result", await as(value), "--retried"));
  run("refresh-pillars", "--library", lib, "--unavailable", "get_creator_profile failed: not_found");
  collect(run("recap", "--library", lib, "--date", "2026-10-21"));
  collect(run("review-facts", "--library", lib, "--content-id", "old0", "--checkpoint", "24h"));
  const bare = path.join(temp, "bare");
  run("bootstrap", "--library", bare, "--platform", "instagram", "--handle", "maker");
  collect(run("recap", "--library", bare, "--date", "2026-10-21"));
  assert.ok(said.length > 25, String(said.length));
  for (const line of said) plain("output", line);

  // 3. The quoted example sentences in SKILL.md and references that prescribe what to say to the creator
  // (double-quoted sentences containing spaces).
  for (const id of owners) {
    const dir = path.join(root, "skills", id);
    const files = ["SKILL.md", ...["pillars.md", "profile-edits.md", "host-schedules.md", "review-format.md"].map(name => `references/${name}`)];
    for (const name of files) {
      let text;
      try { text = await readFile(path.join(dir, name), "utf8"); } catch { continue; }
      for (const [, quote] of text.replace(/^---\n[\s\S]*?\n---\n/, "").replace(/`[^`]*`/g, "``").matchAll(/"([^"\n]{12,})"/g))
        // The only exception: the verbatim tool error text quoted in the instructions is for the assistant to
        // recognize failures and is not said to the creator.
        if (/\s/.test(quote) && !quote.startsWith("MCP error contains")) plain(`${id}/${name}`, quote);
    }
  }
});

// ---- Daily picks: read only the get_for_you_videos result and pick 3 according to the limits written in
// SKILL.md.

const video = (id, author, rank, extra = {}) => ({ content_id: id, url: `https://www.instagram.com/reel/${id}/`, platform: "instagram",
  format: "reel", title: `title ${id}`, caption: null, author_handle: author, published_at: "2026-11-05T10:00:00Z", views: 100000 - rank * 1000, rank,
  reason: `Popular in your niche (${id})`, ...extra });
// Final output of get_for_you_videos (kabo#2176): all fields are always present, null when not applicable;
// all three windows keys are there.
const forYouResult = (status, extra = {}) => ({ structuredContent: { status, account_id: "00000000-0000-4000-8000-000000000001",
  platform: "instagram", reason: null, failure_code: null, retryable: null, retry_after_seconds: null, generated_at: null,
  expires_at: null, next_refresh_at: null, windows: null, ...extra } });
const ready = (windows, extra = {}) => forYouResult("ready", { windows: { "7d": [], "30d": [], "24h": [], ...windows },
  generated_at: "2026-11-11T00:00:00Z", expires_at: "2026-11-12T00:00:00Z", next_refresh_at: "2026-11-12T00:00:00Z", ...extra });

test("daily picks: the 7-day window takes priority by rank, then 30-day and 24-hour windows fill in; skip the creator themself, the same author, previously shown items, and cross-window duplicates; never pad; days with zero picks are recorded too", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "kabo-library", "instagram-maker");
  const result = path.join(temp, "for-you.json");
  const forYou = async (value, date, ...flags) => {
    await writeFile(result, JSON.stringify(value));
    return run("for-you", "--library", library, "--result", result, "--handle", "@Maker", "--date", date, "--write", ...flags);
  };
  // Within the 7-day window: rank given out of order; the creator themself (different case and @) one entry,
  // the same author two entries, no link one entry.
  const day1 = await forYou(ready({
    "7d": [video("b", "beta", 2), video("a", "Alpha", 1), video("own", "@MAKER", 3), video("a2", "@alpha", 4), video("nolink", "nl", 5, { url: null })],
    "30d": [video("a", "Alpha", 1), video("c", "gamma", 2)],
    "24h": [video("d", "delta", 1)],
  }), "2026-11-11");
  assert.equal(day1.status, "ready");
  assert.deepEqual(day1.picks.map(pick => [pick.content_id, pick.window, pick.rank]), [["a", "7d", 1], ["b", "7d", 2], ["c", "30d", 2]]);
  assert.deepEqual(day1.skipped, { shown_on_earlier_day: 0, own_post: 1, same_author: 1, same_video_in_another_window: 1, no_link: 1, below_views_floor: 0 });
  assert.equal(day1.picks[0].reason, "Popular in your niche (a)");
  assert.equal(day1.picks[0].views, 99000);
  // No duration: remake only says "will check first" and does not guess.
  assert.match(day1.picks[0].remake, /checks whether this video qualifies/);
  assert.equal(day1.recorded, true);
  assert.equal(day1.generated_at, "2026-11-11T00:00:00Z");
  // Evidence is only the basis the backend gives: no multiple, no pillar.
  for (const key of ["multiple", "author_typical_views", "pillar_id"]) assert.equal(key in day1.picks[0], false);

  // Running again the same day: do not reselect or overwrite, even if the backend gives a different result
  // this time.
  const again = await forYou(ready({ "7d": [video("z", "zeta", 1)] }), "2026-11-11");
  assert.equal(again.already_recorded, true);
  assert.deepEqual(again.picks.map(pick => pick.content_id), ["a", "b", "c"]);
  assert.deepEqual(run("picks", "--library", library, "--date", "2026-11-11").picks.map(pick => pick.content_id), ["a", "b", "c"]);

  // Second day: those shown yesterday are recognized by id or link (query, www, and trailing slash removed);
  // with only two left, give two.
  const day2 = await forYou(ready({
    "7d": [video("a", "Alpha", 1), { ...video("b-again", "beta", 2), content_id: "b-again", url: "https://instagram.com/reel/b?igsh=xyz" }],
    "30d": [video("e", "epsilon", 1)],
    "24h": [video("d", "delta", 1)],
  }), "2026-11-12");
  assert.deepEqual(day2.picks.map(pick => [pick.content_id, pick.window]), [["e", "30d"], ["d", "24h"]]);
  assert.equal(day2.skipped.shown_on_earlier_day, 2);
  assert.match(day2.note, /never pad/);

  // Third day: all already shown (or no id and no link, so unrecognizable) - zero picks, and "checked today"
  // is still recorded.
  const day3 = await forYou(ready({ "7d": [video("a", "Alpha", 1)], "30d": [], "24h": [video("d", "delta", 1)] }), "2026-11-13");
  assert.deepEqual(day3.picks, []);
  assert.equal(day3.recorded, true);
  const checked = run("picks", "--library", library, "--date", "2026-11-13");
  assert.deepEqual([checked.checked, checked.picks], [true, []]);
  assert.deepEqual(run("picks", "--library", library, "--date", "2026-11-14"), { date: "2026-11-14", checked: false, picks: null, recorded_days: ["2026-11-11", "2026-11-12", "2026-11-13"] });

  // The dedupe set does not take in empty values: an old record missing both id and link will not cause other
  // videos to be treated as "already shown".
  const stored = JSON.parse(await readFile(path.join(library, "picks.json"), "utf8"));
  stored.days["2026-11-10"] = [{ content_id: null, url: "", keys: ["", null] }];
  await writeFile(path.join(library, "picks.json"), JSON.stringify(stored));
  const day4 = await forYou(ready({ "7d": [video("f", "phi", 1, { content_id: "" })] }), "2026-11-14");
  assert.deepEqual(day4.picks.map(pick => pick.url), ["https://www.instagram.com/reel/f/"]);
  assert.deepEqual(day4.picks[0].keys, ["url:instagram.com/reel/f"]);
  // The contract has no duration: remake is always "will check first"; when platform is missing, infer it
  // from the link; when there is no title, use caption.
  const day5 = await forYou(ready({ "7d": [video("g", "g1", 1, { platform: null, title: null, caption: "caption g" })] }), "2026-11-15");
  assert.equal(day5.picks[0].platform, "instagram");
  assert.equal(day5.picks[0].title, "caption g");
  assert.match(day5.picks[0].remake, /checks whether this video qualifies/);
});

// Codex measured (YouTube account): author_handle is null for all 30 picks, and the links are watch?v=....
// Only 1 was ever selected,
// because link normalization dropped ?v=, so all watch links were treated as the same video; an empty
// author must not be treated as the same author either.
const ytVideo = (id, rank, extra = {}) => ({ content_id: id, url: `https://www.youtube.com/watch?v=${id}&si=share${rank}`,
  platform: "youtube", format: "long", title: `title ${id}`, caption: null, author_handle: null,
  published_at: "2026-11-10T10:00:00Z", views: 900000 - rank * 1000, rank, reason: `Popular (${id})`, ...extra });

test("daily picks: YouTube results whose authors are all empty can still fill 3 picks; authors partly empty; deduplicate by author_id when present; cross-window dedup looks only at the video id", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const result = path.join(temp, "for-you.json");
  const forYou = async (value, date) => {
    await writeFile(result, JSON.stringify(value));
    return run("for-you", "--library", library, "--result", result, "--handle", "mrbeast", "--date", date, "--write");
  };
  const range = (prefix, count) => Array.from({ length: count }, (_, i) => ytVideo(`${prefix}${i + 1}`, i + 1));
  // All authors empty, 11 in 7d, 12 in 30d, 7 in 24h; the first in 30d and the second in 7d are the same
  // video (different link query).
  const windows = { "7d": range("w", 11), "30d": [{ ...ytVideo("w2", 1), url: "https://youtube.com/watch?v=w2" }, ...range("m", 11)], "24h": range("d", 7) };
  const day1 = await forYou(ready(windows, { platform: "youtube" }), "2026-11-11");
  assert.deepEqual(day1.picks.map(pick => [pick.window, pick.rank, pick.content_id]), [["7d", 1, "w1"], ["7d", 2, "w2"], ["7d", 3, "w3"]]);
  assert.deepEqual(day1.skipped, { shown_on_earlier_day: 0, own_post: 0, same_author: 0, same_video_in_another_window: 0, no_link: 0, below_views_floor: 0 });
  assert.deepEqual(day1.picks[0].keys, ["id:w1", "url:youtube.com/watch?v=w1"]);
  assert.equal(day1.picks[0].author_handle, null);
  assert.equal(day1.picks[0].format, "long");
  // Second day: 7d has only w4 onward; yesterday's w2 reappears in 30d with a different link form and is
  // recognized by ?v=.
  const day2 = await forYou(ready({ "7d": [ytVideo("w1", 1), ytVideo("w2", 2)], "30d": [{ ...ytVideo("w3", 1), content_id: "" }, ytVideo("m1", 2)], "24h": [ytVideo("d1", 1), ytVideo("d2", 2)] }, { platform: "youtube" }), "2026-11-12");
  assert.deepEqual(day2.picks.map(pick => pick.content_id), ["m1", "d1", "d2"]);
  assert.equal(day2.skipped.shown_on_earlier_day, 3);
  // Only a cross-window duplicate within 7d: when the same video reappears in 30d it counts as
  // same_video_in_another_window, not as author.
  const day3 = await forYou(ready({ "7d": [ytVideo("x1", 1)], "30d": [ytVideo("x1", 1), ytVideo("x2", 2)], "24h": [] }, { platform: "youtube" }), "2026-11-13");
  assert.deepEqual(day3.picks.map(pick => pick.content_id), ["x1", "x2"]);
  assert.deepEqual(day3.skipped, { shown_on_earlier_day: 0, own_post: 0, same_author: 0, same_video_in_another_window: 1, no_link: 0, below_views_floor: 0 });

  // Some authors empty and some named: named ones are deduped as usual, empty ones do not participate. The
  // creator themself is excluded only when a name is given.
  const mixed = await forYou(ready({ "7d": [ytVideo("p1", 1, { author_handle: "@Alpha" }), ytVideo("p2", 2, { author_handle: "alpha" }),
    ytVideo("p3", 3), ytVideo("p4", 4, { author_handle: "MrBeast" }), ytVideo("p5", 5)] }), "2026-11-14");
  assert.deepEqual(mixed.picks.map(pick => pick.content_id), ["p1", "p3", "p5"]);
  assert.deepEqual([mixed.skipped.same_author, mixed.skipped.own_post], [1, 1]);
  // author_id takes priority: different names with the same id count as the same author; the same name with
  // different ids does not.
  const byId = await forYou(ready({ "7d": [ytVideo("q1", 1, { author_id: "UC1", author_handle: "one" }), ytVideo("q2", 2, { author_id: "UC1", author_handle: "renamed" }),
    ytVideo("q3", 3, { author_id: "UC2", author_handle: "one" }), ytVideo("q4", 4, { author_id: "UC3" })] }), "2026-11-15");
  assert.deepEqual(byId.picks.map(pick => [pick.content_id, pick.author_id]), [["q1", "UC1"], ["q3", "UC2"], ["q4", "UC3"]]);
  assert.equal(byId.skipped.same_author, 1);
});

test("daily pick author display: YouTube shows the channel name without @, Instagram and TikTok add @, and a missing author is written as author not supplied; author_id takes priority for dedup", async t => {
  const temp = await workspace(t);
  const result = path.join(temp, "for-you.json");
  await writeFile(result, JSON.stringify(ready({ "7d": [
    ytVideo("y1", 1, { author_handle: "MrBeast", author_id: "UCX6OQ3DkcsbYNE6H8uQQuVA" }),
    ytVideo("y2", 2, { author_handle: "MrBeast", author_id: "UCother" }),
    ytVideo("y3", 3, { author_handle: "Some Channel", author_id: "UCX6OQ3DkcsbYNE6H8uQQuVA" }),
    { ...video("ig1", "@creator.one", 4), author_id: "178414" },
    { ...video("tt1", "dancer", 5, { platform: "tiktok", url: "https://www.tiktok.com/@dancer/video/1" }), author_id: null },
    ytVideo("y4", 6),
  ] }, { platform: "youtube" })));
  const picked = run("for-you", "--library", path.join(temp, "lib"), "--result", result, "--date", "2026-11-12", "--count", "5");
  assert.deepEqual(picked.picks.map(pick => [pick.content_id, pick.author]),
    [["y1", "MrBeast"], ["y2", "MrBeast"], ["ig1", "@creator.one"], ["tt1", "@dancer"], ["y4", "author not supplied"]]);
  // The same channel id with different names counts as the same author; the same name with different ids does
  // not.
  assert.equal(picked.skipped.same_author, 1);
  for (const pick of picked.picks) assert.doesNotMatch(pick.author, /^@(None|null)?$/);
});

// Per-window relative views threshold (10% of the top entry): checked against two sets of numbers seen on a
// real host.
test("daily picks: anything below 10% of the window's top views is not picked, each window uses its own top; fewer than 3 that pass the threshold are not padded and this is explained; the threshold value is carried in the output", async t => {
  const temp = await workspace(t);
  const result = path.join(temp, "for-you.json");
  let n = 0;
  const forYou = async (value) => {
    await writeFile(result, JSON.stringify(value));
    n += 1;
    return run("for-you", "--library", path.join(temp, `lib${n}`), "--result", result, "--handle", "maker", "--date", "2026-11-11", "--write");
  };
  const list = (prefix, views, extra = {}) => views.map((count, i) => ({ ...ytVideo(`${prefix}${i + 1}`, i + 1), views: count, ...extra }));

  // YouTube (@mrbeast measured): in 7d only the top entry broke out; the 30d threshold is 380,531; 24h also
  // uses its own top entry.
  const youtube = await forYou(ready({
    "7d": list("w", [63831, 1266, 1240, 1158, 1040, 990]),
    "30d": list("m", [3805307, 2100000, 350000, 120000]),
    "24h": list("d", [9000, 800]),
  }, { platform: "youtube" }));
  assert.deepEqual(youtube.picks.map(pick => [pick.window, pick.rank, pick.views]), [["7d", 1, 63831], ["30d", 1, 3805307], ["30d", 2, 2100000]]);
  assert.deepEqual(youtube.views_floor["7d"], { top_views: 63831, min_views: 6384 });
  assert.deepEqual(youtube.views_floor["30d"], { top_views: 3805307, min_views: 380531 });
  assert.equal(youtube.skipped.below_views_floor, 5);
  // 30d one fewer: 1 from 7d + 1 from 30d + the 24h top entry 1; the second 24h entry is below 900 and is not
  // selected.
  const youtube2 = await forYou(ready({
    "7d": list("w", [63831, 1266, 1240, 1158, 1040]),
    "30d": list("m", [3805307, 350000]),
    "24h": list("d", [9000, 800]),
  }, { platform: "youtube" }));
  assert.deepEqual(youtube2.picks.map(pick => [pick.window, pick.views]), [["7d", 63831], ["30d", 3805307], ["24h", 9000]]);
  // None in 24h either: give only 2, do not pad, and say the rest are clearly below the top entry.
  const youtube3 = await forYou(ready({ "7d": list("w", [63831, 1266, 1240]), "30d": list("m", [3805307, 350000]), "24h": [] }, { platform: "youtube" }));
  assert.deepEqual(youtube3.picks.map(pick => pick.views), [63831, 3805307]);
  assert.match(youtube3.note, /never pad.*far fewer views than the top video of their list \(under 10%/);

  // Instagram (measured): the 7d threshold is 22,084 and takes the first 2; the 3rd is filled from 30d;
  // 220,832 and 68,241 are the same video as in 7d.
  const ig = (id, views) => ({ ...video(id, `author_${id}`, 0), views });
  const seven = [["i1", 220832], ["i2", 68241], ["i3", 8715], ["i4", 6710], ["i5", 3466], ["i6", 2178], ["i7", 558]].map(([id, v], i) => ({ ...ig(id, v), rank: i + 1 }));
  const thirty = [["j1", 604600], ["j2", 232789], ["i1", 220832], ["j4", 79719], ["j5", 79647], ["i2", 68241], ["j7", 36109], ["j8", 30116]].map(([id, v], i) => ({ ...ig(id, v), rank: i + 1 }));
  const instagram = await forYou(ready({ "7d": seven, "30d": thirty, "24h": [] }));
  assert.deepEqual(instagram.picks.map(pick => [pick.window, pick.content_id, pick.views]), [["7d", "i1", 220832], ["7d", "i2", 68241], ["30d", "j1", 604600]]);
  assert.deepEqual(instagram.views_floor["7d"], { top_views: 220832, min_views: 22084 });
  assert.equal(instagram.skipped.below_views_floor, 5);

  // Boundaries: if all pass the threshold, take 3 by rank; only 1; views missing or 0 is not selected; empty
  // window.
  const allPass = await forYou(ready({ "7d": list("a", [1000, 900, 800, 700]) }));
  assert.deepEqual([allPass.picks.map(pick => pick.views), allPass.skipped.below_views_floor], [[1000, 900, 800], 0]);
  const single = await forYou(ready({ "7d": list("s", [5000]) }));
  assert.deepEqual([single.found, single.skipped.below_views_floor], [1, 0]);
  const missing = await forYou(ready({ "7d": [...list("v", [5000]), { ...ytVideo("v2", 2), views: null }, { ...ytVideo("v3", 3), views: 0 }] }));
  assert.deepEqual([missing.found, missing.skipped.below_views_floor], [1, 2]);
  const noViews = await forYou(ready({ "7d": [{ ...ytVideo("z1", 1), views: null }] }));
  assert.deepEqual([noViews.found, noViews.views_floor["7d"]], [0, { top_views: null, min_views: null }]);
  const empty = await forYou(ready({}));
  assert.deepEqual([empty.found, empty.views_floor["24h"]], [0, { top_views: null, min_views: null }]);
});

test("daily pick statuses: generating waits strictly per retry_after with a cap, not_eligible (including unavailable) and failed (relaying failure_code) end in one sentence; tool errors and unknown statuses count as failures; none is recorded for the day", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const result = path.join(temp, "for-you.json");
  const forYou = async (value, ...flags) => {
    await writeFile(result, JSON.stringify(value));
    return run("for-you", "--library", library, "--result", result, "--handle", "maker", "--date", "2026-11-11", "--write", ...flags);
  };
  // Picks: normally 120 seconds, 300 seconds when filling in the profile; at most 3 more queries after the
  // first, total wait no more than 600 seconds.
  const waiting = await forYou(forYouResult("generating", { retry_after_seconds: 120 }));
  assert.deepEqual([waiting.action, waiting.wait_seconds, waiting.next_flags], ["wait", 120, { "--attempt": 2, "--waited": 120 }]);
  assert.match(waiting.progress_line, /preparing today's picks for you. This can take a few minutes/);
  // Two 300-second profile-fill waits fit; the third does not fit, so stop.
  assert.equal((await forYou(forYouResult("generating", { retry_after_seconds: 300 }), "--attempt", "2", "--waited", "300")).wait_seconds, 300);
  const overBudget = await forYou(forYouResult("generating", { retry_after_seconds: 300 }), "--attempt", "3", "--waited", "600");
  assert.equal(overBudget.action, "stop");
  const gaveUp = await forYou(forYouResult("generating", { retry_after_seconds: 120 }), "--attempt", "4", "--waited", "360");
  assert.equal(gaveUp.action, "stop");
  assert.match(gaveUp.message, /you'll get them next time/);

  const expected = {
    no_linked_account: /No account is linked/, no_public_videos: /no public videos/, profile_insufficient: /more of your posts/,
    language_unknown: /which language/, unavailable: /not available for this account/, brand_new_reason: /can't make picks for this account right now\.$/,
  };
  for (const [reason, pattern] of Object.entries(expected)) {
    const answer = await forYou(forYouResult("not_eligible", { reason, retry_after_seconds: reason === "no_linked_account" ? null : 3600 }));
    assert.deepEqual([answer.action, answer.reason], ["stop", reason]);
    assert.match(answer.message, pattern);
    assert.equal(answer.retry_after_seconds, reason === "no_linked_account" ? null : 3600);
  }
  // kabo#2180: never poll on failed; say roughly how long until it can come back, per retry_after_seconds.
  const failedNow = await forYou(forYouResult("failed", { failure_code: "collection_failed", retryable: false, retry_after_seconds: 7200 }));
  assert.deepEqual([failedNow.action, failedNow.failure_code, failedNow.retry_in], ["stop", "collection_failed", "about 2 hours"]);
  assert.match(failedNow.message, /New picks can be made in about 2 hours/);
  assert.doesNotMatch(failedNow.message, /collection_failed/);
  assert.equal("wait_seconds" in failedNow, false);
  // Old backend: context_changed returns failed + retryable=true + about 24 hours - likewise do not poll,
  // state the time honestly.
  const oldStyle = await forYou(forYouResult("failed", { failure_code: "context_changed", retryable: true, retry_after_seconds: 86000 }));
  assert.deepEqual([oldStyle.action, oldStyle.retry_in], ["stop", "about 24 hours"]);
  assert.equal("wait_seconds" in oldStyle, false);
  assert.match((await forYou(forYouResult("failed", { failure_code: "model_budget", retry_after_seconds: 1800 }))).message, /about 30 minutes/);
  const final = await forYou({ structuredContent: { status: "failed", retryable: false, message: "provider quota" } });
  assert.match(final.message, /I'll try again next time/);
  assert.equal(final.failure_code, "provider quota");
  // Multiple accounts without specifying one is the tool error validation_error, not a status.
  const ambiguous = await forYou({ isError: true, content: [{ type: "text", text: "validation_error: account_id is required (acc-1, acc-2)" }] });
  assert.deepEqual([ambiguous.status, ambiguous.action], ["failed", "stop"]);
  assert.match(ambiguous.failure_code, /validation_error/);
  assert.doesNotMatch(ambiguous.message, /validation_error/);
  const odd = await forYou({ structuredContent: { status: "paused", detail: 1 } });
  assert.deepEqual([odd.status, odd.action], ["paused", "stop"]);
  assert.doesNotMatch(odd.message, /paused|status/);
  assert.deepEqual(odd.reported, { status: "paused" });
  const blank = await forYou({});
  assert.equal(blank.status, "failed");
  // None of the above is ready: no record for today, and the next run will ask the backend again.
  assert.equal(run("picks", "--library", library, "--date", "2026-11-11").checked, false);
  await assert.rejects(access(path.join(library, "picks.json")));
  // ready but windows is null: zero picks, and today is still recorded.
  const empty = await forYou(forYouResult("ready"));
  assert.deepEqual([empty.found, empty.recorded, empty.window_sizes], [0, true, { "7d": 0, "30d": 0, "24h": 0 }]);
});

test("daily recap: follower change, last 7 days against the usual level, the reading for each pillar; when there are not two readings, say so honestly", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(profileResult([signature("sc1", "Breakdowns", 0.6)])));
  run("bootstrap", "--library", library, "--platform", "instagram", "--handle", "maker", "--profile", profile);
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0), { followers: 1000 }));
  for (const id of ["old0", "old1", "old2", "old3"]) run("set-pillar", "--library", library, "--content-id", id, "--pillar-id", "breakdowns");
  assert.match(refuse("set-pillar", "--library", library, "--content-id", "old3", "--pillar-id", "nope").stderr, /one of the library's pillars/);
  const first = run("recap", "--library", library, "--date", "2026-10-20");
  assert.equal(first.followers.available, false);
  assert.equal(first.followers.now, 1000);
  assert.ok(first.limits.some(line => /no follower change/.test(line)));
  assert.ok(first.limits.some(line => /first time I've read your account/.test(line)));
  const t1 = "2026-10-21T10:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-21T06:00:00Z", 700)], { followers: 1040 }));
  const recap = run("recap", "--library", library, "--date", "2026-10-21");
  // The second time, history is read on the same library: the host kept the file, so no longer say "this is
  // the only reading".
  assert.equal(recap.limits.some(line => /first time I've read your account/.test(line)), false);
  assert.equal(run("show", "--library", library).fresh, false);
  assert.deepEqual([recap.followers.available, recap.followers.change, recap.followers.previous, recap.followers.since_hours], [true, 40, 1000, 26]);
  assert.equal(recap.typical_settled_views, 1050);
  // Posts within the last 7 days (168 hours): old0, old1, and new1; new1 is not yet 72 hours old.
  assert.deepEqual(recap.last_7_days.posts.map(row => row.content_id).sort(), ["new1", "old0", "old1"]);
  assert.equal(recap.last_7_days.still_gathering_views, 1);
  assert.equal(recap.last_7_days.settled_median_views, 1050);
  assert.equal(recap.last_7_days.settled_median_multiple, 1);
  const pillar = recap.pillars[0];
  assert.deepEqual([pillar.id, pillar.settled_posts, pillar.median_views, pillar.median_multiple], ["breakdowns", 4, 1150, 1.1]);
  assert.equal(pillar.view_share, 0.505);
  assert.equal(recap.recent_posts_without_pillar, 1);
  const report = path.join(temp, "recap.md");
  await writeFile(report, "recap");
  assert.match(run("record-recap", "--library", library, "--report", report, "--date", "2026-10-21").report, /recaps\/2026-10-21\.md$/);
});

test("review first run: with no local library, build it from the Kabo profile and look back 48 hours; with no profile or a profile without pillars, still build the library, review, and produce the daily report", async t => {
  const temp = await workspace(t);
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(profileResult([signature("sc1", "Viral breakdowns", 0.6), signature("sc2", "Charisma tips", 0.3)])));
  const library = path.join(temp, "lib");
  // The daily picks may have written picks.json in the same directory first: it does not affect building the
  // library.
  run("for-you", "--library", library, "--result", await (async () => { const f = path.join(temp, "fy.json"); await writeFile(f, JSON.stringify(ready({ "7d": [video("a", "alpha", 1)] }))); return f; })(), "--date", "2026-10-21", "--write");
  const boot = run("bootstrap", "--library", library, "--platform", "instagram", "--handle", "@Maker", "--profile", profile);
  assert.equal(boot.fresh, true);
  assert.deepEqual(boot.pillars, ["viral-breakdowns", "charisma-tips"]);
  assert.match(refuse("bootstrap", "--library", library, "--platform", "instagram", "--handle", "maker", "--profile", profile).stderr, /already exists/);
  const shown = run("show", "--library", library);
  assert.equal(shown.pillars_source, "kabo_profile");
  assert.deepEqual(shown.pick_days, ["2026-10-21"]);

  // With no profile (account not bound in Kabo) and a profile with no pillars, the library can be built in
  // both cases.
  for (const [name, extra] of [["no-profile", []], ["no-pillars", ["--profile", path.join(temp, "empty.json")]]]) {
    await writeFile(path.join(temp, "empty.json"), JSON.stringify(profileResult([])));
    const bare = path.join(temp, name);
    const built = run("bootstrap", "--library", bare, "--platform", "instagram", "--handle", "maker", ...extra);
    assert.deepEqual(built.pillars, [], name);
    assert.match(built.note, /no pillar section/);
    // First history read: posts published within 48 hours enter the review, older ones do not; the account id
    // is claimed by account name.
    const observed = "2026-10-21T10:00:00Z";
    const rows = [item("fresh", "2026-10-20T08:00:00Z", 800), item("stale", "2026-10-17T08:00:00Z", 900), ...history("2026-10-21T10:00:00Z")];
    const ingested = run("ingest", "--library", bare, "--snapshot", await snapshot(temp, `${name}.json`, observed, rows, { followers: 500 }));
    assert.deepEqual(ingested.new_tracked_posts, ["fresh"]);
    assert.deepEqual(ingested.due.map(row => [row.content_id, row.checkpoint]), [["fresh", "24h"]]);
    // With no pillars, posts can only be assigned to other.
    assert.match(refuse("set-pillar", "--library", bare, "--content-id", "fresh", "--pillar-id", "viral-breakdowns").stderr, /one of the library's pillars/);
    const facts = run("review-facts", "--library", bare, "--content-id", "fresh", "--checkpoint", "24h");
    assert.equal(facts.pillar_id, null);
    assert.ok(facts.limits.some(line => /first time I've read your account/.test(line)));
    const review = path.join(temp, `${name}-review.md`);
    await writeFile(review, "review");
    run("record-review", "--library", bare, "--content-id", "fresh", "--checkpoint", "24h", "--report", review);
    assert.deepEqual(run("due", "--library", bare).due, []);
    const recap = run("recap", "--library", bare, "--date", "2026-10-21");
    assert.deepEqual(recap.pillars, []);
    assert.ok(recap.limits.some(line => /no content pillars saved yet/.test(line)));
    assert.equal(recap.followers.now, 500);
    // The typical level takes posts at a full 72 hours: the ten old posts plus stale; fresh is still
    // accumulating views.
    assert.equal(recap.typical_settled_views, 1000);
    const daily = path.join(temp, `${name}-recap.md`);
    await writeFile(daily, "recap");
    assert.match(run("record-recap", "--library", bare, "--report", daily, "--date", "2026-10-21").report, /recaps\/2026-10-21\.md$/);
  }
});

test("each review run refreshes pillars from the Kabo profile: a rename keeps ownership, a merge reassigns to the merged item, a deletion becomes unassigned; when the profile cannot be read, keep the old values and record it in limits; when the profile has no pillars, clear them", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const profile = path.join(temp, "profile.json");
  const write = (items) => writeFile(profile, JSON.stringify(profileResult(items)));
  await write([signature("sc1", "Viral breakdowns", 0.5), signature("sc2", "Charisma tips", 0.3), signature("sc3", "Vlogs", 0.2)]);
  run("bootstrap", "--library", library, "--platform", "instagram", "--handle", "maker", "--profile", profile);
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)));
  const assign = { old0: "viral-breakdowns", old1: "viral-breakdowns", old2: "charisma-tips", old3: "vlogs", old4: "other" };
  for (const [id, pillar] of Object.entries(assign)) run("set-pillar", "--library", library, "--content-id", id, "--pillar-id", pillar);
  const review = path.join(temp, "r.md");
  await writeFile(review, "review");
  const before = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  const owner = (id) => JSON.parse(execFileSync("python3", ["-I", "-B", "-c", "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))['posts'][sys.argv[2]]['pillar_id']))", path.join(library, "posts.json"), id], options));

  // 1. sc1 is renamed, sc2 and sc3 are merged into m_1 (origin.baseIds lists the members).
  await write([{ ...signature("sc1", "Why videos go viral", 0.5) },
    { ...signature("m_1", "Talking and daily life", 0.5), origin: { baseIds: ["sc2", "sc3"], baseName: null, renamed: true, weightSource: "profile" } }]);
  const merged = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.equal(merged.refreshed, true);
  assert.deepEqual(merged.pillars, ["viral-breakdowns", "talking-and-daily-life"]);
  assert.deepEqual(merged.pillar_moves, { "charisma-tips": "talking-and-daily-life", vlogs: "talking-and-daily-life" });
  assert.deepEqual(merged.posts, { kept: 2, moved: 2, unassigned: 0 });
  assert.deepEqual(["old0", "old1", "old2", "old3", "old4"].map(owner), ["viral-breakdowns", "viral-breakdowns", "talking-and-daily-life", "talking-and-daily-life", "other"]);
  const shown = run("show", "--library", library);
  assert.equal(shown.pillars[0].name, "Why videos go viral");
  assert.deepEqual(shown.pillars[1].profile_base_ids, ["sc2", "sc3"]);
  assert.equal(shown.pillars_refresh.ok, true);

  // 2. Profile unreadable: keep the previous one, explain in the limits of the review and recap; the whole
  // run does not fail.
  const failed = run("refresh-pillars", "--library", library, "--unavailable", "get_creator_profile failed: not_found");
  assert.deepEqual([failed.refreshed, failed.pillars], [false, ["viral-breakdowns", "talking-and-daily-life"]]);
  assert.ok(run("recap", "--library", library, "--date", "2026-10-21").limits.some(line => /couldn't get your latest content pillars from Kabo today, so this uses the ones from \d{4}-\d\d-\d\d/.test(line)));
  assert.ok(run("review-facts", "--library", library, "--content-id", "old0", "--checkpoint", "24h").limits.some(line => /couldn't get your latest content pillars/.test(line)));
  await writeFile(path.join(temp, "refused.json"), JSON.stringify({ isError: true, content: [{ type: "text", text: "Internal error" }] }));
  assert.equal(run("refresh-pillars", "--library", library, "--profile", path.join(temp, "refused.json")).refreshed, false);
  assert.deepEqual(["old0", "old2"].map(owner), ["viral-breakdowns", "talking-and-daily-life"]);

  // 3. A merged item is deleted: its posts become unassigned; readings are not lost.
  await write([signature("sc1", "Why videos go viral", 0.9)]);
  const removed = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.deepEqual(removed.pillars, ["viral-breakdowns"]);
  assert.deepEqual(removed.posts, { kept: 2, moved: 0, unassigned: 2 });
  assert.deepEqual(["old0", "old2", "old3", "old4"].map(owner), ["viral-breakdowns", null, null, "other"]);
  assert.equal(run("recap", "--library", library, "--date", "2026-10-22").limits.some(line => /couldn't get your latest content pillars/.test(line)), false);
  const after = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  assert.deepEqual(after.old2.observations, before.old2.observations);

  // 4. The profile has no pillars: local ones are cleared too, and the recap has no pillar section.
  await write([]);
  const none = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.deepEqual([none.pillars, none.posts.unassigned], [[], 2]);
  const recap = run("recap", "--library", library, "--date", "2026-10-23");
  assert.deepEqual(recap.pillars, []);
  assert.ok(recap.limits.some(line => /no content pillars saved yet/.test(line)));
  assert.equal(run("show", "--library", library).niche.text, "Short breakdowns of viral videos for small creators");
});

// ---- The whole fetch path: static host stages the combined result (same shape as the backend) -> snapshot
// -> ingest; transcripts work the same way.

const NOW = Math.floor(Date.now() / 1000);
const DAY = 86400;
const envelope = (connector_id, operation, data, extra = {}) => ({
  schema_version: "1.0", connector_id, operation, provider: "fixture-provider", status: "completed", summary: "ok", limitations: [],
  credential_values_recorded: false, request_id: `req-${operation}`, evidence_ref: `ev-${operation}`, raw_sha256: "a".repeat(64),
  retrieved_at: new Date(NOW * 1000).toISOString(), data, ...extra,
});
const reelRow = (code, index) => ({ code, pk: `${code}-pk`, taken_at: NOW - (index + 1) * 3 * DAY, like_count: 100 + index, comment_count: 5,
  play_count: 20000 + 900 * index, media_type: 2, product_type: "clips", user: { username: "neutral.creator", pk: "u1" }, caption: { text: `caption ${code}` } });
const composite = (tool, calls, summary = {}) => ({ schema_version: "kabo-composite-fetch.v1", tool, status: "completed",
  calls: calls.map(([name, parameters, result, group]) => ({ tool: name, parameters, group: group ?? "acct-0", attempts: 1, result })),
  summary, coverage: { deadline_reached: false, unfinished: [], provider_calls: calls.length, accounts: [] }, limitations: [] });

function host(args, { cwd, runDir, input } = {}) {
  const result = spawnSync("python3", ["-I", "-B", path.join(skillDir, "static_host.py"), ...args], {
    ...options, cwd, input, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(runDir ? { KABO_STATIC_RUN_DIR: runDir } : {}) } });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}
function inRun(runDir, ...args) {
  return JSON.parse(execFileSync("python3", ["-I", "-B", cli, ...args], { ...options, cwd: runDir, env: { ...process.env, KABO_STATIC_RUN_DIR: runDir } }));
}

test("history-request arguments match the input of collect_account_history; after staging the composite result, snapshot and ingest build the library", async t => {
  const temp = await workspace(t);
  const runDir = host(["init", "--workspace", temp]);
  const full = run("history-request", "--platform", "instagram", "--handle", "@Neutral.Creator", "--depth", "full");
  assert.deepEqual(full, { platform: "instagram", accounts: [{ handle: "neutral.creator" }], profile: true,
    history: { max_items: 100, max_pages: 40, instagram_formats: { posts: false, reels: true, balance: "fewer_rows_first" } },
    on_identity_miss: "gap", delivery: "download" });
  assert.deepEqual(run("history-request", "--platform", "youtube", "--channel-id", "UCaaaaaaaaaaaaaaaaaaaaaa").accounts, [{ channel_id: "UCaaaaaaaaaaaaaaaaaaaaaa" }]);
  assert.deepEqual(run("history-request", "--platform", "tiktok", "--handle", "maker").history, { max_items: 30 });
  assert.match(refuse("history-request", "--platform", "tiktok", "--channel-id", "UCaaaaaaaaaaaaaaaaaaaaaa").stderr, /only for YouTube/);

  const profile = envelope("instagram-discovery", "resolve_profile", { profile: { id: "u1", pk: "u1", username: "neutral.creator", full_name: "Neutral Creator", follower_count: 12000, media_count: 9 } });
  const reels = envelope("instagram-discovery", "list_reels", { rows: [0, 1, 2, 3].map(index => reelRow(`RL${index}`, index)), count: 4, more_available: false });
  const staged = path.join(temp, "history.json");
  await writeFile(staged, JSON.stringify(composite("collect_account_history", [
    ["instagram_resolve_profile", { handle: "neutral.creator" }, profile],
    ["instagram_list_reels", { handle: "neutral.creator", user_id: "u1" }, reels]],
  { accounts: [{ group: "acct-0", status: "completed", items_total: 4, pages: 1 }] })));
  host(["stage", "--tool", "collect_account_history", "--input", staged], { cwd: runDir, runDir });
  const built = inRun(runDir, "snapshot", "--platform", "instagram", "--output", "snapshot/posts.json");
  assert.equal(built.status, "ok");
  assert.equal(built.item_count, 4);
  assert.equal(built.profile_read, true);
  const library = path.join(temp, "kabo-library", "instagram-neutral.creator");
  assert.equal(run("path", "--workspace", temp, "--platform", "instagram", "--handle", "neutral.creator").library, library);
  const ingested = inRun(runDir, "ingest", "--library", library, "--snapshot", "snapshot/posts.json", "--handle", "neutral.creator");
  assert.equal(ingested.created, true);
  assert.equal(ingested.posts_in_library, 4);
  assert.equal(ingested.followers_now, 12000);
  assert.deepEqual(ingested.due, []);

  // When no posts can be read (account does not exist, is private, or the read failed), state the reason and
  // do not build an empty library.
  const second = await workspace(t);
  const secondRun = host(["init", "--workspace", second]);
  const missing = { ...envelope("instagram-discovery", "resolve_profile", undefined), status: "failed", error_code: "not_found", summary: "failed" };
  await writeFile(path.join(second, "history.json"), JSON.stringify(composite("collect_account_history", [["instagram_resolve_profile", { handle: "nobody" }, missing]])));
  host(["stage", "--tool", "collect_account_history", "--input", path.join(second, "history.json")], { cwd: secondRun, runDir: secondRun });
  const failure = spawnSync("python3", ["-I", "-B", cli, "snapshot", "--platform", "instagram", "--output", "snapshot/posts.json"],
    { ...options, cwd: secondRun, env: { ...process.env, KABO_STATIC_RUN_DIR: secondRun } });
  assert.notEqual(failure.status, 0);
  assert.match(failure.stderr, /no public posts/);
});

// Only onboarding reads transcripts: use the static_host from start-with-kabo
// (public_video_fetch_transcript is on its allowlist).
function startHost(args, { cwd, runDir, input } = {}) {
  const result = spawnSync("python3", ["-I", "-B", path.join(root, "skills/start-with-kabo/scripts/static_host.py"), ...args], {
    ...options, cwd, input, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...(runDir ? { KABO_STATIC_RUN_DIR: runDir } : {}) } });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}

test("media-request asks for transcripts only for posts that have links; after staging transcripts, transcripts prints text per post and marks those without speech", async t => {
  const temp = await workspace(t);
  const runDir = startHost(["init", "--workspace", temp]);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const request = inRun(runDir, "media-request", "--library", library, "--limit", "3");
  assert.equal(request.requests.length, 3);
  assert.ok(request.requests.every(row => row.operation === "fetch_transcript" && row.parameters.url.startsWith("https://www.instagram.com/reel/")));
  assert.equal(request.wait_s, 100);
  assert.equal(request.delivery, "download");
  assert.match(request.run_key, /^lib:[0-9a-f]{24}$/);
  assert.deepEqual(inRun(runDir, "media-request", "--library", library).requests.length, 8);
  assert.deepEqual(Object.keys(request).sort(), ["delivery", "requests", "run_key", "wait_s"]);

  const transcript = (cues, plain) => envelope("public-video-media", "fetch_transcript", { origin: "captions", language: "en", cues, plain_text: plain });
  const media = composite("collect_video_media", [
    ["public_video_fetch_transcript", { url: "https://www.instagram.com/reel/old0/" }, transcript([{ start_ms: 0, text: "Hello there" }, { start_ms: 900, text: "today we break down a hook" }]), "old0/fetch_transcript"],
    ["public_video_fetch_transcript", { url: "https://www.instagram.com/reel/old1/" }, transcript([], ""), "old1/fetch_transcript"]],
  { jobs: [] });
  media.coverage = { pending: 0 };
  const file = path.join(temp, "media.json");
  await writeFile(file, JSON.stringify(media));
  startHost(["stage", "--tool", "collect_video_media", "--input", file], { cwd: runDir, runDir });
  const read = inRun(runDir, "transcripts");
  assert.equal(read.pending, 0);
  assert.deepEqual(read.transcripts.map(row => [row.content_id, row.has_speech]), [["old0", true], ["old1", false]]);
  assert.equal(read.transcripts[0].text, "Hello there today we break down a hook");
});

// ---- 1.0.40: onboarding proposes pillars locally, and after the creator confirms, syncs the whole set to
// Kabo once (declare_pillars, kabo#2185).

const cluster = (name, ids, extra = {}) => ({ name, definition: `About ${name}`, search_phrases: [`${name} tips`], content_ids: ids, ...extra });
const declared = (pillars, { version = 3, signature = [] } = {}) => {
  const value = profileResult(signature, { version });
  value.structuredContent.declaredPillars = pillars.map(([name, definition, phrases]) => ({ name, definition, searchPhrases: phrases }));
  return value;
};

test("propose-pillars gives reference numbers only and does not decide; it pre-checks length, duplicate names, and duplicate grouping by backend rules; save-pillars saves only after confirmation and marks as unsynced", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const posts = run("posts", "--library", library, "--tell");
  assert.match(posts.tell_creator_now, /I read 10 of your videos\. A typical one gets about 1,050 views/);
  // The same sentence is said only once, after the posts have been read: later post listings do not carry it.
  assert.equal("tell_creator_now" in run("posts", "--library", library), false);
  const file = path.join(temp, "clusters.json");
  await writeFile(file, JSON.stringify({ clusters: [cluster("Breakdowns", ["old0", "old1", "old2"]), cluster("Charisma", ["old6", "old7", "old8"])] }));
  const proposal = run("propose-pillars", "--library", library, "--clusters", file);
  assert.equal(proposal.typical_settled_views, 1050);
  assert.deepEqual(proposal.groups.map(row => [row.name, row.posts, row.median_views, row.median_multiple_of_typical]), [["Breakdowns", 3, 1100, 1.05], ["Charisma", 3, 400, 0.38]]);
  for (const row of proposal.groups) assert.equal("recommended" in row, false);
  assert.match(proposal.note, /not Kabo's statistics and not a verdict/);
  assert.equal(JSON.parse(await readFile(path.join(library, "library.json"), "utf8")).pillars.length, 0);
  // Pre-check: a name over 60 characters, a definition over 200 characters, 4 search phrases, a duplicate
  // name (case-insensitive), or one post in two groups are all reported before display.
  const bad = [[cluster("x".repeat(61), ["old0"])], [cluster("A", ["old0"], { definition: "d".repeat(201) })],
    [cluster("A", ["old0"], { search_phrases: ["a", "b", "c", "d"] })], [cluster("Same", ["old0"]), cluster("same ", ["old1"])]];
  for (const clusters of bad) {
    await writeFile(file, JSON.stringify({ clusters }));
    assert.match(refuse("propose-pillars", "--library", library, "--clusters", file).stderr, /Fix these before showing or saving/);
  }
  await writeFile(file, JSON.stringify({ clusters: [cluster("A", ["old0"]), cluster("B", ["old0"])] }));
  assert.match(refuse("propose-pillars", "--library", library, "--clusters", file).stderr, /more than one group/);

  const confirmed = path.join(temp, "confirmed.json");
  await writeFile(confirmed, JSON.stringify({ pillars: [cluster("Breakdowns", ["old0", "old1"])] }));
  assert.match(refuse("save-pillars", "--library", library, "--file", confirmed).stderr, /not confirmed/);
  await writeFile(confirmed, JSON.stringify({ confirmed: true, pillars: [cluster("Breakdowns", ["old0", "old1"]), cluster("Charisma tips", ["old6"])] }));
  const saved = run("save-pillars", "--library", library, "--file", confirmed);
  assert.deepEqual([saved.pillars, saved.sync], [["breakdowns", "charisma-tips"], "pending"]);
  const shown = run("show", "--library", library);
  assert.equal(shown.pillars_source, "local_unsynced");
  assert.equal(shown.pillars_sync.state, "pending");
  assert.deepEqual(shown.pillars[0].search_phrases, ["Breakdowns tips"]);
});

test("sync: declare-request submits the whole payload with the version from the profile; success marks synced; on conflict, re-read and retry only once; failure is honestly marked unsynced and synced later", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(declared([], { version: 3 })));
  assert.match(refuse("declare-request", "--library", library, "--profile", profile).stderr, /no pillars the creator declared/);
  const confirmed = path.join(temp, "confirmed.json");
  await writeFile(confirmed, JSON.stringify({ confirmed: true, pillars: [cluster("Breakdowns", ["old0"]), cluster("Charisma", [])] }));
  run("save-pillars", "--library", library, "--file", confirmed);
  const request = run("declare-request", "--library", library, "--profile", profile);
  assert.deepEqual(request, { account_id: "acc-1", expected_version: 3, action: "declare_pillars", pillars: [
    { name: "Breakdowns", definition: "About Breakdowns", searchPhrases: ["Breakdowns tips"] },
    { name: "Charisma", definition: "About Charisma", searchPhrases: ["Charisma tips"] }] });
  // When preferences were never written, preferences is null: take the version as 0.
  const fresh = declared([]);
  fresh.structuredContent.effectiveContentProfile.preferences = null;
  await writeFile(profile, JSON.stringify(fresh));
  assert.equal(run("declare-request", "--library", library, "--profile", profile).expected_version, 0);

  const result = path.join(temp, "declare.json");
  const record = async (value, ...flags) => { await writeFile(result, JSON.stringify(value)); return run("record-sync", "--library", library, "--result", result, ...flags); };
  const conflict = { isError: true, content: [{ type: "text", text: "conflict: preferences_changed" }] };
  assert.equal((await record(conflict)).action, "reread_and_retry");
  const stillConflict = await record(conflict, "--retried");
  assert.equal(stillConflict.sync, "pending");
  assert.match(stillConflict.tell_creator_now, /saved on this computer for now; I couldn't save them to your Kabo account yet/);
  const noScope = await record({ isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write" }] });
  assert.match(noScope.tell_creator_now, /Kabo needs your permission to save to your account/);
  assert.equal(run("show", "--library", library).pillars_sync.state, "pending");
  // Catch-up sync: succeeds the next time writing is possible, marked as synced, and Kabo becomes the place
  // pillars are stored.
  const ok = await record({ structuredContent: { effectiveContentProfile: { version: 1 } } });
  assert.deepEqual([ok.sync, ok.tell_creator_now], ["synced", "Your content pillars are saved in your Kabo account."]);
  const shown = run("show", "--library", library);
  assert.deepEqual([shown.pillars_source, shown.pillars_sync.state], ["kabo_declared", "synced"]);
});

test("refresh-pillars source priority: declared pillars -> backend statistics -> none; aligned by name (case-insensitive); local unsynced pillars are not cleared by backend results", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const confirmed = path.join(temp, "confirmed.json");
  await writeFile(confirmed, JSON.stringify({ confirmed: true, pillars: [cluster("Breakdowns", ["old0", "old1"]), cluster("Charisma", ["old6"])] }));
  run("save-pillars", "--library", library, "--file", confirmed);
  const owner = async (id) => JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts[id].pillar_id;
  const profile = path.join(temp, "profile.json");
  // Not synced: the backend returning an empty declaration and other statistics does not clear the local
  // pillars either.
  await writeFile(profile, JSON.stringify(declared([], { signature: [signature("sc1", "Something else", 0.5)] })));
  const kept = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.deepEqual([kept.refreshed, kept.sync, kept.pillars], [false, "pending", ["breakdowns", "charisma"]]);
  // After a successful sync the backend is authoritative: declared pillars first; a name differing only in
  // case keeps its assignment, a renamed one becomes unassigned.
  await writeFile(path.join(temp, "ok.json"), JSON.stringify({ structuredContent: { effectiveContentProfile: {} } }));
  run("record-sync", "--library", library, "--result", path.join(temp, "ok.json"));
  await writeFile(profile, JSON.stringify(declared([["BREAKDOWNS ", "Why one video worked", ["viral breakdown"]], ["Camera confidence", "How to look calm on camera", ["camera tips"]]],
    { signature: [signature("sc1", "Something else", 0.5)] })));
  const fromDeclared = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.deepEqual(fromDeclared.pillars, ["breakdowns", "camera-confidence"]);
  assert.deepEqual([await owner("old0"), await owner("old1"), await owner("old6")], ["breakdowns", "breakdowns", null]);
  assert.equal(run("show", "--library", library).pillars_source, "kabo_declared");
  // When the declaration is empty, fall back to the backend statistics (aligned by profile item id; a
  // declared pillar has no id -> posts become unassigned).
  await writeFile(profile, JSON.stringify(declared([], { signature: [signature("sc1", "Viral breakdowns", 0.5)] })));
  const fromSignature = run("refresh-pillars", "--library", library, "--profile", profile);
  assert.deepEqual(fromSignature.pillars, ["viral-breakdowns"]);
  assert.equal(await owner("old0"), null);
  assert.equal(run("show", "--library", library).pillars_source, "kabo_profile");
  // Neither exists: no pillars. Without pillars: true (no declaredPillars key in the result), read the
  // statistics as usual and do not treat it as "declaration empty".
  await writeFile(profile, JSON.stringify(declared([])));
  assert.deepEqual(run("refresh-pillars", "--library", library, "--profile", profile).pillars, []);
  const legacy = profileResult([signature("sc2", "Charisma tips", 0.4)]);
  await writeFile(profile, JSON.stringify(legacy));
  assert.deepEqual(run("refresh-pillars", "--library", library, "--profile", profile).pillars, ["charisma-tips"]);
  // Hosts that keep no files: building the library also takes the declared pillars by the same priority.
  await writeFile(profile, JSON.stringify(declared([["Breakdowns", "Why one video worked", ["viral breakdown"]]], { signature: [signature("sc1", "Other", 0.5)] })));
  const boot = run("bootstrap", "--library", path.join(temp, "boot"), "--platform", "instagram", "--handle", "maker", "--profile", profile);
  assert.deepEqual(boot.pillars, ["breakdowns"]);
  assert.equal(run("show", "--library", path.join(temp, "boot")).pillars_sync.state, "synced");
});

// ---- Fixes after measured runs (Codex, three accounts): the binding idempotency key, the numbers given to
// the creator, and the sentences of the reference block.

test("connect-request generates an idempotency key: first bind and replacement bind differ, retrying the same request yields the same key, different replaced versions yield different keys; handle is always lowercased", async () => {
  const first = run("connect-request", "--platform", "youtube", "--handle", "@MrBeast", "--url", "https://www.youtube.com/@MrBeast");
  assert.deepEqual(first, { platform: "youtube", handle_or_url: "https://www.youtube.com/@MrBeast", idempotency_key: "library:youtube:mrbeast:new" });
  const replace = (version) => run("connect-request", "--platform", "youtube", "--handle", "MRBEAST",
    "--expected-account-id", "4779b7a3-ef7b-479f-9d5f-014f20296077", "--expected-binding-version", version);
  const a = replace("c498edb2-1111-4111-8111-111111111111");
  assert.equal(a.idempotency_key, "library:youtube:mrbeast:c498edb2-1111-4111-8111-111111111111");
  assert.equal(a.handle_or_url, "mrbeast");
  // Retry of the same binding: the key is unchanged (even if the version differs in case); the version is
  // passed to the tool as is.
  const again = replace("C498EDB2-1111-4111-8111-111111111111");
  assert.equal(again.idempotency_key, a.idempotency_key);
  assert.deepEqual(replace("c498edb2-1111-4111-8111-111111111111"), a);
  assert.notEqual(replace("d0000000-2222-4222-8222-222222222222").idempotency_key, a.idempotency_key);
  // Contract: 8-128 characters, A-Za-z0-9._:-.
  const longest = run("connect-request", "--platform", "instagram", "--handle", "a".repeat(64), "--expected-account-id",
    "4779b7a3-ef7b-479f-9d5f-014f20296077", "--expected-binding-version", "c498edb2-1111-4111-8111-111111111111").idempotency_key;
  assert.ok(longest.length <= 128 && /^[A-Za-z0-9._:-]{8,128}$/.test(longest), String(longest.length));
  const contract = JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.find(tool => tool.name === "connect_public_account").inputSchema.properties.idempotency_key;
  assert.deepEqual([contract.minLength, contract.maxLength], [8, 128]);
  assert.match(refuse("connect-request", "--platform", "youtube", "--handle", "x", "--expected-account-id", "4779b7a3-ef7b-479f-9d5f-014f20296077").stderr, /needs both/);
  assert.match(refuse("connect-request", "--platform", "youtube", "--handle", "x", "--expected-account-id", "a", "--expected-binding-version", "nope").stderr, /bindingVersion uuid/);
});

test("connect-result: success gives the account id; failure does not relay the backend's own wording but gives plain language and the next step; a missing write permission says authorization is needed", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "connect.json");
  const result = async (value) => { await writeFile(file, JSON.stringify(value)); return run("connect-result", "--result", file, "--handle", "MrBeast"); };
  const ok = await result({ structuredContent: { account: { id: "acc-9", bindingVersion: "bv-1", handle: "mrbeast" } } });
  assert.deepEqual([ok.linked, ok.account_id, ok.tell_creator_now], [true, "acc-9", "@mrbeast is now linked to your Kabo."]);
  const conflict = await result({ isError: true, content: [{ type: "text", text: "conflict: This idempotency key was already used for another request." }] });
  assert.equal(conflict.linked, false);
  assert.equal(conflict.tell_creator_now, "I couldn't link @mrbeast to your Kabo just now. I'll still read its videos and propose pillars; we can try linking again in a moment.");
  assert.match(conflict.reported.message, /idempotency key/);
  assert.doesNotMatch(conflict.tell_creator_now, /idempotency|request/);
  const scope = await result({ isError: true, content: [{ type: "text", text: "Insufficient scope: workspace:write" }] });
  assert.match(scope.tell_creator_now, /needs your permission to save to your account before I can link @mrbeast/);
});

test("numbers shown to the creator: views are rounded with thousands separators, multiples have at most two decimals; reference blocks and each proposal line are written by the script", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  const big = [0, 1, 2, 3].map(i => item(`b${i}`, hoursBefore(t0, 100 + i * 24), [65897439, 1231293530, 148897372, 1726][i]));
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, big), "--handle", "maker");
  const told = run("posts", "--library", library, "--tell").tell_creator_now;
  assert.match(told, /A typical one gets about 107,397,406 views/);
  assert.match(told, /has 1,231,293,530 views, 11\.46 times that/);
  assert.doesNotMatch(told, /\d+\.0 views|\d{8,}/);
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(profileResult([{ ...signature("sc1", "Hooks", 0.32), contentCount: 15, medianMultiplier: 1.48 },
    { ...signature("sc2", "Vlogs", 0.5), contentCount: 20, medianMultiplier: 2 }, { ...signature("sc3", "Shorts", 0.07), contentCount: 3, medianMultiplier: null }])));
  assert.deepEqual(run("profile-pillars", "--profile", profile).candidates.map(row => row.say_line), [
    "Vlogs: 20 of your recent videos, about half; they get about 2 times your usual views.",
    "Hooks: 15 of your recent videos, about a third; they get about 1.48 times your usual views.",
    "Shorts: 3 of your recent videos, about 7%."]);
  const clusters = path.join(temp, "clusters.json");
  await writeFile(clusters, JSON.stringify({ clusters: [cluster("Big ones", ["b0", "b1"])] }));
  assert.equal(run("propose-pillars", "--library", library, "--clusters", clusters).groups[0].say_line, "2 of your videos, about 6.04 times your usual views.");
});

test("wait messaging is at most two sentences and never repeated: say it once on entering the wait, add one on the 3rd call, and stay silent on the remaining polls (same for picks and profile)", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "wait.json");
  const as = async (value) => { await writeFile(file, JSON.stringify(value)); return file; };
  const said = (output) => output.progress_line ?? output.tell_creator_now ?? null;
  // Picks: at most 3 more queries after the first (120 seconds each); stop at the 4th call.
  const picks = [];
  let flags = { attempt: 1, waited: 0 };
  for (;;) {
    const out = run("for-you", "--library", path.join(temp, "lib"), "--result", await as(forYouResult("generating", { retry_after_seconds: 120 })),
      "--date", "2026-11-12", "--attempt", String(flags.attempt), "--waited", String(flags.waited));
    if (out.action !== "wait") break;
    picks.push(said(out));
    if (!said(out)) assert.equal(out.say_to_creator, false);
    flags = { attempt: out.next_flags["--attempt"], waited: out.next_flags["--waited"] };
  }
  assert.deepEqual(picks, ["Kabo is preparing today's picks for you. This can take a few minutes.", null, "Still working on it."]);
  // Profile: at most 8 more queries after the first (60 seconds each); only two sentences are said during the
  // whole wait.
  const profile = [];
  flags = { attempt: 1, waited: 0 };
  for (;;) {
    const out = run("profile-status", "--result", await as(prepared("generating", { retry_after_seconds: 60 })), "--attempt", String(flags.attempt), "--waited", String(flags.waited));
    if (out.action !== "wait") break;
    profile.push(said(out));
    if (!said(out)) assert.equal(out.say_to_creator, false);
    flags = { attempt: out.next_flags["--attempt"], waited: out.next_flags["--waited"] };
  }
  assert.equal(profile.length, 8);
  const lines = profile.filter(Boolean);
  assert.deepEqual(lines, ["Kabo is building your profile from your public videos. This usually takes a few minutes.", "Still working on it."]);
  // Guard: the same sentence is not repeated in consecutive polling output.
  for (const sequence of [picks.filter(Boolean), lines]) assert.equal(new Set(sequence).size, sequence.length);
});
