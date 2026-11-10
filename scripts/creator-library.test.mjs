// start-with-kabo、pick-daily-viral-videos、review-new-posts 共用的 creator_library.py：离线测试，不联网。
// 覆盖：三份副本相同；先读 Kabo 画像再提支柱；本地支柱规则；确认后才保存；24 小时复盘的选取与同龄基线；
// 账号回顾；不留文件的宿主重建；每日精选；以及 history-request → 暂存组合结果 → snapshot → ingest 的整条路。
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const owners = ["start-with-kabo", "pick-daily-viral-videos", "review-new-posts"];
const skillDir = path.join(root, "skills/start-with-kabo/scripts");
const cli = path.join(skillDir, "creator_library.py");
const options = { encoding: "utf8", maxBuffer: 4 * 1024 * 1024, timeout: 30_000 };
const run = (...args) => JSON.parse(execFileSync("python3", ["-I", "-B", cli, ...args], options));
const refuse = (...args) => spawnSync("python3", ["-I", "-B", cli, ...args], options);

async function workspace(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-library-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  return temp;
}

// 与 build_public_snapshot.py 输出同形的最小快照：只放复盘与支柱用到的字段。
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

// 十条已稳定的旧作品：播放分布让前六条占大头。
function history(observedAt) {
  const rows = [];
  for (let i = 0; i < 10; i++)
    rows.push(item(`old${i}`, hoursBefore(observedAt, 100 + i * 24), i < 6 ? 1000 + i * 100 : 400));
  return rows;
}

// get_creator_profile（effective: true）的结果形状：只放脚本读取的字段。
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

test("三份 creator_library.py 逐字相同；快照拼装脚本与账号复盘的副本相同", async () => {
  const copies = new Set(await Promise.all(owners.map(id => readFile(path.join(root, "skills", id, "scripts/creator_library.py"), "utf8"))));
  assert.equal(copies.size, 1);
  const reference = await readFile(path.join(root, "skills/review-creator-account/scripts/build_public_snapshot.py"), "utf8");
  for (const id of ["start-with-kabo", "review-new-posts"])
    assert.equal(await readFile(path.join(root, "skills", id, "scripts/build_public_snapshot.py"), "utf8"), reference);
});

test("建库记下绑定时间；之后发布的作品满 24 小时才复盘一次，同龄基线取自别的作品", async t => {
  const temp = await workspace(t);
  const library = run("path", "--workspace", temp, "--platform", "instagram", "--handle", "@Maker").library;
  assert.ok(library.endsWith(path.join("kabo-library", "instagram-maker")));
  const t0 = "2026-10-20T08:00:00Z";
  const first = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0), { followers: 1000 }), "--handle", "maker");
  assert.equal(first.created, true);
  assert.deepEqual(first.new_tracked_posts, []);
  assert.deepEqual(first.due, []);
  assert.equal(first.followers_now, 1000);
  // 绑定前的作品永远不进复盘；别人的作品和图文不进素材库；不满 24 小时不到期。
  const t1 = "2026-10-20T20:00:00Z";
  const young = await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-20T08:20:00Z", 300),
    item("guest", "2026-10-20T08:25:00Z", 999, { creator: "c-2" }), item("photo", "2026-10-20T08:26:00Z", null, { format: "instagram_feed" })]);
  const second = run("ingest", "--library", library, "--snapshot", young);
  assert.deepEqual(second.new_tracked_posts, ["new1"]);
  assert.deepEqual(second.due, []);
  assert.deepEqual(run("posts", "--library", library).posts.map(row => row.content_id).filter(id => ["guest", "photo"].includes(id)), []);
  assert.equal(run("ingest", "--library", library, "--snapshot", young).observations_added, 0);
  // 可选时点：满 1 小时还没到 24 小时的作品，只有带 --with-optional 才出现。
  assert.deepEqual(run("due", "--library", library, "--with-optional").due.map(row => [row.content_id, row.checkpoint]), [["new1", "1h"]]);

  const t2 = "2026-10-21T10:00:00Z";
  const third = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s2.json", t2, [...history(t0), item("new1", "2026-10-20T08:20:00Z", 900)]));
  assert.deepEqual(third.due.map(row => [row.content_id, row.checkpoint, row.late]), [["new1", "24h", false]]);
  const facts = run("review-facts", "--library", library, "--content-id", "new1", "--checkpoint", "24h");
  assert.equal(facts.age_hours, 25.67);
  assert.equal(facts.same_age_baseline.multiple, null);
  assert.equal(facts.typical_settled.posts, 10);
  assert.match(facts.limits[0], /no same-age comparison/);
  const report = path.join(temp, "r.md");
  await writeFile(report, "review");
  run("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "24h", "--report", report);
  assert.match(refuse("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "24h", "--report", report).stderr, /already recorded/);
  assert.deepEqual(run("due", "--library", library).due, []);

  // 三条更早的作品在 24–48 小时区间被量过，第四条才有同龄基线。
  const peers = [1, 2, 3].map(index => item(`peer${index}`, `2026-10-21T0${index}:00:00Z`, index * 1000));
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s3.json", "2026-10-22T08:00:00Z", [...history(t0), ...peers]));
  const rows = [...history(t0), ...peers, item("new2", "2026-10-21T19:00:00Z", 4000)];
  const fourth = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s4.json", "2026-10-22T20:00:00Z", rows));
  assert.ok(fourth.due.some(row => row.content_id === "new2" && row.checkpoint === "24h"));
  const compared = run("review-facts", "--library", library, "--content-id", "new2", "--checkpoint", "24h");
  // 同龄基线是别的作品在 24–48 小时区间的读数：三条同伴加上更早复盘过的 new1。
  assert.equal(compared.same_age_baseline.posts, 4);
  assert.equal(compared.same_age_baseline.median_views, 1500);
  assert.equal(compared.same_age_baseline.multiple, 2.67);
  assert.deepEqual(compared.limits, []);
});

test("迟到的复盘标明迟到；1 小时与 7 天只在要求时出现，7 天复盘接在 24 小时之后", async t => {
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

test("TikTok 只给日期时：编号里的时间同一天才采用，定时发布改按第一次看到的时间计龄", async t => {
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

test("先读 Kabo 画像：可见的画像项按占比成为候选支柱，带证据、编辑上下文与被创作者隐藏的项", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "profile.json");
  await writeFile(file, JSON.stringify(profileResult([signature("sc2", "Charisma tips", 0.3), signature("sc1", "Viral breakdowns", 0.55), signature("sc3", "Vlogs", 0.1)])));
  const proposal = run("profile-pillars", "--profile", file);
  assert.equal(proposal.status, "ok");
  assert.equal(proposal.niche, "Short breakdowns of viral videos for small creators");
  assert.equal(proposal.profile_edited, true);
  assert.deepEqual(proposal.candidates.map(row => row.id), ["viral-breakdowns", "charisma-tips", "vlogs"]);
  assert.deepEqual(proposal.candidates[0].search_queries, ["Viral breakdowns query", "Viral breakdowns second"]);
  assert.equal(proposal.candidates[0].source, "kabo_profile");
  assert.equal(proposal.candidates[0].profile_item_id, "sc1");
  assert.equal(proposal.candidates[0].evidence.share_of_posts, 0.55);
  assert.equal(proposal.candidates[0].evidence.examples[0].url, "https://www.instagram.com/reel/sc1ex/");
  assert.deepEqual(proposal.hidden_by_creator, ["Giveaways"]);
  assert.deepEqual(proposal.update_context, { account_id: "acc-1", expected_version: 3, basis: "2026-10-01T00:00:00Z" });
  assert.equal(proposal.candidates[0].search_queries_are_tags, false);
  assert.deepEqual(proposal.advice, []);
  // 画像只给一项、检索词又是标签时：提示换成观众会搜的短语，并提示再从帖子里找候选。
  const tagged = path.join(temp, "tagged.json");
  await writeFile(tagged, JSON.stringify(profileResult([{ ...signature("sc9", "Tagged pillar", 0.4), seedTerms: ["views", "viralhooks", "reelstips"] }])));
  const single = run("profile-pillars", "--profile", tagged);
  assert.equal(single.candidates[0].search_queries_are_tags, true);
  assert.equal(single.advice.length, 2);
  assert.match(single.advice[0], /phrases a viewer would type/);
  assert.match(single.advice[1], /step 4b/);
  // 没有画像项时不编造，退回本地计算。
  const empty = path.join(temp, "empty.json");
  await writeFile(empty, JSON.stringify(profileResult([])));
  const none = run("profile-pillars", "--profile", empty);
  assert.equal(none.status, "no_signature_content");
  assert.deepEqual(none.candidates, []);
});

test("本地提议：中位播放不低于常规水平 0.8 倍才推荐，第二个支柱要占 20%；样本不足时不推荐；确认前不写库", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const clusters = path.join(temp, "clusters.json");
  const cluster = (id, ids) => ({ id, name: id, definition: `about ${id}`, search_queries: [`${id} query`], content_ids: ids });
  await writeFile(clusters, JSON.stringify({ clusters: [cluster("breakdowns", ["old0", "old1", "old2"]), cluster("charisma", ["old6", "old7", "old8"])] }));
  const proposal = run("propose-pillars", "--library", library, "--clusters", clusters);
  assert.equal(proposal.status, "ok");
  assert.equal(proposal.typical_settled_views, 1050);
  assert.deepEqual(proposal.candidates.map(row => [row.id, row.recommended]), [["breakdowns", true], ["charisma", false]]);
  assert.match(proposal.candidates[1].why, /under 0\.8 times/);
  assert.equal(proposal.candidates[0].example_posts[0].url, "https://www.instagram.com/reel/old2/");
  assert.deepEqual(JSON.parse(await readFile(path.join(library, "library.json"), "utf8")).pillars, []);
  // 常规水平之下的聚类全都不合格时，退回占比最高的一个并标明偏弱。
  await writeFile(clusters, JSON.stringify({ clusters: [cluster("weak", ["old6", "old7", "old8"])] }));
  const weak = run("propose-pillars", "--library", library, "--clusters", clusters);
  assert.equal(weak.below_typical, true);
  assert.equal(weak.candidates[0].recommended, true);
  // 稳定作品太少时不推荐，交给创作者选。
  const thin = path.join(temp, "thin");
  run("ingest", "--library", thin, "--snapshot", await snapshot(temp, "thin.json", t0, history(t0).slice(0, 4)), "--handle", "maker");
  await writeFile(clusters, JSON.stringify({ clusters: [cluster("solo", ["old0", "old1", "old2", "old3"])] }));
  const insufficient = run("propose-pillars", "--library", thin, "--clusters", clusters);
  assert.equal(insufficient.status, "insufficient_history");
  assert.deepEqual(insufficient.candidates.map(row => row.recommended), [false]);
  assert.match(insufficient.note, /without a recommendation/);
});

test("支柱只在创作者确认后保存；保存时给作品归支柱，新作品用 set-pillar 归类", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const pillar = (id, ids, source = "local_posts") => ({ id, name: id, definition: `about ${id}`, search_queries: [`${id} query`], source, content_ids: ids });
  const file = path.join(temp, "confirmed.json");
  const body = { niche: "Viral video breakdowns", niche_source: "posts", pillars: [pillar("breakdowns", ["old0", "old1"]), pillar("charisma", ["old6"])] };
  await writeFile(file, JSON.stringify(body));
  assert.match(refuse("save-pillars", "--library", library, "--file", file).stderr, /not confirmed/);
  await writeFile(file, JSON.stringify({ ...body, confirmed: true, pillars: [{ ...pillar("breakdowns", ["old0"]), source: "guess" }] }));
  assert.match(refuse("save-pillars", "--library", library, "--file", file).stderr, /needs a source/);
  await writeFile(file, JSON.stringify({ ...body, confirmed: true, pillars: Array.from({ length: 5 }, (_, i) => pillar(`p${i}`, ["old0"])) }));
  assert.match(refuse("save-pillars", "--library", library, "--file", file).stderr, /1 to 4/);
  await writeFile(file, JSON.stringify({ ...body, confirmed: true }));
  const saved = run("save-pillars", "--library", library, "--file", file);
  assert.deepEqual(saved.pillars, ["breakdowns", "charisma"]);
  assert.equal(saved.posts_assigned, 3);
  const shown = run("show", "--library", library);
  assert.equal(shown.niche.text, "Viral video breakdowns");
  assert.equal(shown.pillars_confirmed_by, "creator");
  assert.equal(run("posts", "--library", library).posts.find(row => row.content_id === "old1").pillar_id, "breakdowns");
  assert.equal(run("set-pillar", "--library", library, "--content-id", "old3", "--pillar-id", "other").pillar_id, "other");
  assert.match(refuse("set-pillar", "--library", library, "--content-id", "old3", "--pillar-id", "nope").stderr, /one of the library's pillars/);
});

test("每日回顾：粉丝变化、近 7 天对比常规水平、每个支柱的读数；没有两次读数时如实说明", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0), { followers: 1000 }), "--handle", "maker");
  const file = path.join(temp, "confirmed.json");
  await writeFile(file, JSON.stringify({ confirmed: true, niche: "n", niche_source: "creator", pillars: [
    { id: "breakdowns", name: "Breakdowns", definition: "d", search_queries: ["bd query"], source: "creator", content_ids: ["old0", "old1", "old2", "old3"] }] }));
  run("save-pillars", "--library", library, "--file", file);
  const first = run("recap", "--library", library, "--date", "2026-10-20");
  assert.equal(first.followers.available, false);
  assert.equal(first.followers.now, 1000);
  assert.ok(first.limits.some(line => /no follower change/.test(line)));
  const t1 = "2026-10-21T10:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-21T06:00:00Z", 700)], { followers: 1040 }));
  const recap = run("recap", "--library", library, "--date", "2026-10-21");
  assert.deepEqual([recap.followers.available, recap.followers.change, recap.followers.previous, recap.followers.since_hours], [true, 40, 1000, 26]);
  assert.equal(recap.typical_settled_views, 1050);
  // 近 7 天（168 小时）内的作品：old0、old1 与 new1；new1 还不满 72 小时。
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

test("不留文件的宿主：从 Kabo 画像重建最小库，回看 48 小时，不编造历史", async t => {
  const temp = await workspace(t);
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(profileResult([signature("sc1", "Viral breakdowns", 0.6), signature("sc2", "Charisma tips", 0.3)])));
  const library = path.join(temp, "lib");
  const boot = run("bootstrap", "--library", library, "--platform", "instagram", "--handle", "@Maker", "--profile", profile);
  assert.equal(boot.stateless, true);
  assert.deepEqual(boot.pillars, ["viral-breakdowns", "charisma-tips"]);
  assert.match(refuse("bootstrap", "--library", library, "--platform", "instagram", "--handle", "maker", "--profile", profile).stderr, /already exists/);
  const shown = run("show", "--library", library);
  assert.equal(shown.stateless, true);
  assert.equal(shown.pillars_confirmed_by, "saved_profile");
  // 新读一遍历史：48 小时内发布的作品进入复盘，更早的不进；账号编号由账号名认领。
  const observed = "2026-10-21T10:00:00Z";
  const rows = [item("fresh", "2026-10-20T08:00:00Z", 800), item("stale", "2026-10-17T08:00:00Z", 900)];
  const ingested = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", observed, rows, { followers: 500 }));
  assert.deepEqual(ingested.new_tracked_posts, ["fresh"]);
  assert.deepEqual(ingested.due.map(row => [row.content_id, row.checkpoint]), [["fresh", "24h"]]);
  const facts = run("review-facts", "--library", library, "--content-id", "fresh", "--checkpoint", "24h");
  assert.ok(facts.limits.some(line => /keeps no files/.test(line)));
  const recap = run("recap", "--library", library, "--date", "2026-10-21");
  assert.equal(recap.followers.available, false);
  assert.ok(recap.limits.some(line => /keeps no files/.test(line)));
  // 图文与其他账号的作品不进库；Kabo 没有画像项时没有可重建的东西。
  const empty = path.join(temp, "empty.json");
  await writeFile(empty, JSON.stringify(profileResult([])));
  assert.match(refuse("bootstrap", "--library", path.join(temp, "other"), "--platform", "instagram", "--handle", "maker", "--profile", empty).stderr, /nothing to rebuild from/);
});

test("每日精选：只收样本够且至少 2 倍的爆款，按支柱各保一条、作者不重复、跨天不重复，不凑数；可无人值守重放", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const confirmed = path.join(temp, "confirmed.json");
  const pillar = (id, queries) => ({ id, name: id, definition: "d", search_queries: queries, source: "creator" });
  await writeFile(confirmed, JSON.stringify({ confirmed: true, niche: "n", niche_source: "creator",
    pillars: [pillar("breakdowns", ["viral breakdown", "why it worked", "hook teardown"]), pillar("charisma", ["charisma tips", "camera confidence", "speak better"])] }));
  run("save-pillars", "--library", library, "--file", confirmed);
  // 检索请求：每个支柱的第一条检索词优先，一共最多 6 条意图；YouTube 最多 2 条。
  const request = run("pick-request", "--library", library, "--language", "en");
  assert.equal(request.platform, "instagram");
  assert.equal(request.window, "last-week");
  assert.equal(request.language, "en");
  assert.deepEqual(request.intents.map(row => row.intent_id), ["breakdowns.1", "charisma.1", "breakdowns.2", "charisma.2", "breakdowns.3", "charisma.3"]);
  assert.equal(request.delivery, "download");
  const youtube = run("pick-request", "--library", library, "--platform", "youtube");
  assert.deepEqual(youtube.intents, [{ intent_id: "breakdowns.1", query: "viral breakdown" }, { intent_id: "charisma.1", query: "charisma tips" }]);
  assert.ok(Date.parse(youtube.published_before) - Date.parse(youtube.published_after) === 7 * 86_400_000);

  const reel = (key, pillarId, multiple, score, extra = {}) => ({ content_key: `instagram:${key}`, url: `https://www.instagram.com/reel/${key}/`,
    platform: "instagram", final_score: score, author: { handle: extra.author ?? key }, metrics: { play_count: 50000 },
    outlier: { multiple, cohort_median: 5000, cohort_size: 12, evidence_strength: extra.strength ?? "strong" },
    sources: [{ intent_id: `${pillarId}.1` }], semantic_scores: { topic_relevance: 90, locale_fit: 90, creator_transferability: 70 },
    caption: key, duration_seconds: extra.duration });
  const enrichment = path.join(temp, "enrich.json");
  await writeFile(enrichment, JSON.stringify({ schema_version: "trend-enrichment.v1", items: [
    reel("a1", "breakdowns", 6, 0.99, { duration: 40 }), reel("a2", "breakdowns", 5, 0.98, { author: "a1" }), reel("a3", "breakdowns", 4, 0.97),
    reel("c1", "charisma", 3, 0.5), reel("weak", "charisma", 9, 0.96, { strength: "directional" }),
    reel("low", "breakdowns", 1.6, 0.95), reel("mine", "breakdowns", 8, 0.94, { author: "maker" }),
    reel("long", "breakdowns", 3, 0.4, { duration: 720 })] }));
  const day1 = run("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-21", "--write");
  assert.deepEqual(day1.picks.map(pick => pick.content_key), ["instagram:a1", "instagram:c1", "instagram:a3"]);
  assert.deepEqual(day1.rejected, { already_shown: 0, own_post: 1, below_multiple: 1, no_pillar: 0, weak_or_missing_baseline: 1 });
  assert.match(day1.picks[0].remake, /talking-head or voice-over video \(40 seconds long\)/);
  assert.match(day1.picks[1].remake, /unknown length: possible only if/);
  assert.match(refuse("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-21", "--write").stderr, /already recorded/);
  // 同一天再跑（定时任务重试）：直接取回已记录的精选，不再检索。
  assert.deepEqual(run("picks", "--library", library, "--date", "2026-10-21").picks.map(pick => pick.content_key), ["instagram:a1", "instagram:c1", "instagram:a3"]);
  assert.equal(run("picks", "--library", library, "--date", "2026-10-23").picks, null);
  // 第二天：用过的全部排除，只剩作者重复的 a2 与超长的 long；不凑数。
  const day2 = run("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-22", "--write");
  assert.deepEqual(day2.picks.map(pick => pick.content_key), ["instagram:a2", "instagram:long"]);
  assert.match(day2.picks[1].remake, /longer than 10 minutes/);
  assert.match(day2.note, /never pad/);

  // YouTube 结果用 account_breakout / channel / views，归一后同样可选，且 YouTube 不是复刻不支持的平台。
  const yt = path.join(temp, "yt.json");
  await writeFile(yt, JSON.stringify({ schema_version: "youtube-trend-enrichment.v1", items: [{ content_key: "youtube:v1",
    url: "https://www.youtube.com/shorts/v1", platform: "youtube", final_score: 0.9, channel: { id: "UCxxxxxxxxxxxxxxxxxxxxxx", title: "Chan" },
    metrics: { views: 90000 }, account_breakout: { multiple: 4.2, cohort_median: 20000, comparable_count: 15, evidence_strength: "moderate" },
    sources: [{ intent_id: "charisma.1" }], duration_seconds: 45 }] }));
  const mixed = run("pick", "--library", library, "--enrichment", yt, "--date", "2026-10-23");
  assert.deepEqual(mixed.picks.map(pick => [pick.author, pick.views, pick.author_posts_compared]), [["Chan", 90000, 15]]);
  assert.match(refuse("pick", "--library", library, "--enrichment", confirmed).stderr, /not a staged enrich/);
  // 没有确认过的支柱时不选。
  const bare = path.join(temp, "bare");
  run("ingest", "--library", bare, "--snapshot", path.join(temp, "s0.json"), "--handle", "maker");
  assert.match(refuse("pick", "--library", bare, "--enrichment", enrichment).stderr, /no confirmed content pillars/);
});

// ---- 整条取数路径：静态宿主暂存组合结果（与后台同形）→ snapshot → ingest；转写同理。

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

test("history-request 的参数合 collect_account_history 的入参；暂存组合结果后 snapshot 与 ingest 建出库", async t => {
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
  const ingested = inRun(runDir, "ingest", "--library", library, "--snapshot", "snapshot/posts.json", "--handle", "neutral.creator");
  assert.equal(ingested.created, true);
  assert.equal(ingested.posts_in_library, 4);
  assert.equal(ingested.followers_now, 12000);
  assert.deepEqual(ingested.due, []);

  // 读不到任何帖子（账号不存在、私密或读取失败）时说清原因，不建空库。
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

test("media-request 只为有链接的作品要转写；暂存转写后 transcripts 按作品打印文本，没有台词的标明", async t => {
  const temp = await workspace(t);
  const runDir = host(["init", "--workspace", temp]);
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
  host(["stage", "--tool", "collect_video_media", "--input", file], { cwd: runDir, runDir });
  const read = inRun(runDir, "transcripts");
  assert.equal(read.pending, 0);
  assert.deepEqual(read.transcripts.map(row => [row.content_id, row.has_speech]), [["old0", true], ["old1", false]]);
  assert.equal(read.transcripts[0].text, "Hello there today we break down a hook");
});
