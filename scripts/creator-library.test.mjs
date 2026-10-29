import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const owners = ["build-creator-library", "pick-daily-viral-videos", "review-new-posts"];
const cli = path.join(root, "skills/build-creator-library/scripts/creator_library.py");
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
  return { content_id: id, creator_id: extra.creator ?? "c-1", format: "instagram_reel", published_at: publishedAt,
    url: `https://www.instagram.com/reel/${id}/`, title: extra.title ?? `post ${id}`,
    metrics: { views: metric(views), likes: metric(extra.likes ?? 10), comments: metric(extra.comments ?? 1),
      shares: metric(null), saves: metric(null) } };
}
async function snapshot(dir, name, observedAt, items, platform = "instagram", handle = "maker") {
  const file = path.join(dir, name);
  await writeFile(file, JSON.stringify({ schema_version: "public-content-snapshot.v1", snapshot_id: name,
    observed_at: observedAt, platform, creators: [{ creator_id: "c-1", handle }], items }));
  return file;
}
const hoursBefore = (iso, hours) => new Date(Date.parse(iso) - hours * 3_600_000).toISOString().replace(".000Z", "Z");

// 十条已稳定的旧作品：两组主题，播放分布让第一组占大头。
function history(observedAt) {
  const rows = [];
  for (let i = 0; i < 10; i++)
    rows.push(item(`old${i}`, hoursBefore(observedAt, 100 + i * 24), i < 6 ? 1000 + i * 100 : 400));
  return rows;
}

test("三份 creator_library.py 逐字相同；两份快照拼装脚本与账号复盘的副本相同", async () => {
  const copies = new Set(await Promise.all(owners.map(id => readFile(path.join(root, "skills", id, "scripts/creator_library.py"), "utf8"))));
  assert.equal(copies.size, 1);
  const reference = await readFile(path.join(root, "skills/review-creator-account/scripts/build_public_snapshot.py"), "utf8");
  for (const id of ["build-creator-library", "review-new-posts"])
    assert.equal(await readFile(path.join(root, "skills", id, "scripts/build_public_snapshot.py"), "utf8"), reference);
});

test("建库记下绑定时间；之后发布的作品按 1 小时、24 小时、7 天各复盘一次，同龄基线取自别的作品", async t => {
  const temp = await workspace(t);
  const library = run("path", "--workspace", temp, "--platform", "instagram", "--handle", "@Maker").library;
  assert.ok(library.endsWith(path.join("kabo-library", "instagram-maker")));
  const t0 = "2026-10-20T08:00:00Z";
  const first = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  assert.equal(first.created, true);
  assert.deepEqual(first.new_tracked_posts, []);
  assert.deepEqual(first.due, []);
  // 绑定前的作品永远不进复盘；别人的作品不进素材库。
  const t1 = "2026-10-20T09:30:00Z";
  const s1 = await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-20T08:20:00Z", 300),
    item("guest", "2026-10-20T08:25:00Z", 999, { creator: "c-2" })]);
  const second = run("ingest", "--library", library, "--snapshot", s1);
  assert.deepEqual(second.new_tracked_posts, ["new1"]);
  assert.deepEqual(second.due.map(row => [row.content_id, row.checkpoint]), [["new1", "1h"]]);
  assert.equal(run("posts", "--library", library).posts.some(row => row.content_id === "guest"), false);
  // 同一份快照再导入不加观测。
  assert.equal(run("ingest", "--library", library, "--snapshot", s1).observations_added, 0);

  const facts = run("review-facts", "--library", library, "--content-id", "new1", "--checkpoint", "1h");
  assert.equal(facts.age_hours, 1.17);
  assert.equal(facts.same_age_baseline.multiple, null);
  assert.equal(facts.typical_settled.posts, 10);
  assert.match(facts.limits[0], /no same-age comparison/);
  const report = path.join(temp, "r.md");
  await writeFile(report, "review");
  run("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "1h", "--report", report);
  assert.match(refuse("record-review", "--library", library, "--content-id", "new1", "--checkpoint", "1h", "--report", report).stderr, /already recorded/);
  assert.deepEqual(run("due", "--library", library).due, []);

  // 三条更早的新作品在 24 小时被量过，第四条才有同龄基线。
  let rows = [...history(t0)];
  for (const [index, views] of [[1, 1000], [2, 2000], [3, 3000]]) {
    const published = hoursBefore("2026-10-23T08:00:00Z", 26 + index);
    rows.push(item(`peer${index}`, published, views));
  }
  await snapshot(temp, "s2.json", "2026-10-22T07:00:00Z", rows.map(row => ({ ...row, metrics: { ...row.metrics, views: metric(10) } })));
  run("ingest", "--library", library, "--snapshot", path.join(temp, "s2.json"));
  rows.push(item("new1", "2026-10-20T08:20:00Z", 4000));
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s3.json", "2026-10-23T08:00:00Z", rows));
  const due = run("due", "--library", library).due.map(row => [row.content_id, row.checkpoint]);
  assert.ok(due.some(([id, checkpoint]) => id === "peer1" && checkpoint === "24h"));
  const late = run("review-facts", "--library", library, "--content-id", "peer3", "--checkpoint", "24h");
  assert.equal(late.same_age_baseline.posts, 2);
  // new1 已经 71 小时：24 小时时点仍在窗口内，1 小时那次已记录，不再出现。
  assert.ok(due.some(([id, checkpoint]) => id === "new1" && checkpoint === "24h"));
  assert.equal(due.some(([id, checkpoint]) => id === "new1" && checkpoint === "1h"), false);
});

test("TikTok 只给日期时：编号里的时间同一天才采用，定时发布改按第一次看到的时间计龄", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const observed = "2026-10-29T10:00:00Z";
  const made = (unix) => (BigInt(unix) << 32n).toString();
  const sameDay = made(Date.parse("2026-10-29T03:05:57Z") / 1000);
  const scheduled = made(Date.parse("2026-10-25T12:16:32Z") / 1000);
  const tiktok = (id) => ({ ...item(id, "2026-10-29T00:00:00Z", 50), format: "tiktok_video" });
  await snapshot(temp, "t0.json", "2026-10-28T10:00:00Z", [{ ...item(made(1792900000), "2026-10-27T05:00:00Z", 80), format: "tiktok_video" }], "tiktok");
  run("ingest", "--library", library, "--snapshot", path.join(temp, "t0.json"), "--handle", "maker");
  const result = run("ingest", "--library", library, "--snapshot", await snapshot(temp, "t1.json", observed, [tiktok(sameDay), tiktok(scheduled)], "tiktok"));
  assert.deepEqual(result.new_tracked_posts.sort(), [sameDay, scheduled].sort());
  const posts = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  assert.equal(posts[sameDay].published_at, "2026-10-29T03:05:57Z");
  assert.equal(posts[sameDay].published_at_source, "video_id");
  assert.equal(posts[scheduled].published_at_source, "date_only");
  assert.equal(posts[scheduled].observations[0].age_hours, 0);
  assert.equal(posts[scheduled].observations[0].age_from, "first_seen");
});

test("内容支柱先过「中位数不低于常规水平 0.8 倍」再按播放占比排序，第二支柱还要占 20%；样本不足时等创作者自己选", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const clusters = async (groups) => {
    const file = path.join(temp, `clusters-${Object.keys(groups).join("-")}.json`);
    await writeFile(file, JSON.stringify({ clusters: Object.entries(groups).map(([id, ids]) => ({
      id, name: id, definition: `posts about ${id}`, search_queries: [`${id} ideas`], content_ids: ids })) }));
    return file;
  };
  const twoGroups = await clusters({ breakdowns: ["old0", "old1", "old2", "old3", "old4", "old5"], charisma: ["old6", "old7", "old8", "old9"] });
  const ruled = run("pillars", "--library", library, "--clusters", twoGroups);
  // charisma 占 16%，低于 20%，不能当第二支柱。
  assert.deepEqual(ruled.pillars, ["breakdowns"]);
  assert.equal(ruled.chosen_by, "rule");
  const chosen = run("pillars", "--library", library, "--clusters", twoGroups, "--choose", "charisma,breakdowns", "--write");
  assert.equal(chosen.chosen_by, "creator");
  const saved = JSON.parse(await readFile(path.join(library, "library.json"), "utf8"));
  assert.deepEqual(saved.pillars.map(pillar => pillar.id), ["charisma", "breakdowns"]);
  // 发得多但单条偏弱的聚类不当支柱：volume 占播放大头（54%），中位数却只有常规水平的 0.38 倍。
  const frequentButWeak = await clusters({ volume: ["old0", "old1", "old2", "old6", "old7", "old8", "old9"], strong: ["old3", "old4", "old5"] });
  const effective = run("pillars", "--library", library, "--clusters", frequentButWeak);
  assert.deepEqual(effective.clusters.map(row => [row.id, row.view_share, row.median_multiple]), [["volume", 0.538, 0.38], ["strong", 0.462, 1.33]]);
  assert.deepEqual(effective.pillars, ["strong"]);
  assert.equal(effective.below_typical, false);
  assert.match(refuse("pillars", "--library", library, "--clusters", await clusters({ a: ["old0"], b: ["old0"] })).stderr, /more than one cluster/);
  assert.match(refuse("pillars", "--library", library, "--clusters", await clusters({ a: ["nope"] })).stderr, /Unknown content_id/);

  const thin = path.join(temp, "thin");
  const fewPosts = history(t0).slice(0, 4);
  run("ingest", "--library", thin, "--snapshot", await snapshot(temp, "thin.json", t0, fewPosts), "--handle", "maker");
  const insufficient = run("pillars", "--library", thin, "--clusters", await clusters({ solo: ["old0", "old1", "old2", "old3"] }), "--write");
  assert.equal(insufficient.status, "insufficient_history");
  assert.deepEqual(insufficient.pillars, []);
  assert.equal(insufficient.written, undefined);
});

test("每日精选：只收样本够且至少 2 倍的爆款，按支柱各保一条、作者不重复、跨天不重复", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const t0 = "2026-10-20T08:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s0.json", t0, history(t0)), "--handle", "maker");
  const groups = path.join(temp, "clusters.json");
  await writeFile(groups, JSON.stringify({ clusters: [
    { id: "breakdowns", name: "b", definition: "d", search_queries: ["viral breakdown"], content_ids: ["old0", "old1", "old2"] },
    { id: "charisma", name: "c", definition: "d", search_queries: ["charisma tips"], content_ids: ["old6", "old7", "old8"] }] }));
  run("pillars", "--library", library, "--clusters", groups, "--choose", "breakdowns,charisma", "--write");
  const reel = (key, pillar, multiple, score, extra = {}) => ({ content_key: `instagram:${key}`, url: `https://www.instagram.com/reel/${key}/`,
    platform: "instagram", final_score: score, author: { handle: extra.author ?? key }, metrics: { play_count: 50000 },
    outlier: { multiple, cohort_median: 5000, cohort_size: 12, evidence_strength: extra.strength ?? "strong" },
    sources: [{ intent_id: `${pillar}.1` }], semantic_scores: { topic_relevance: 90, locale_fit: 90, creator_transferability: 70 },
    caption: key, duration_seconds: extra.duration });
  const enrichment = path.join(temp, "enrich.json");
  await writeFile(enrichment, JSON.stringify({ schema_version: "trend-enrichment.v1", items: [
    reel("a1", "breakdowns", 6, 0.99), reel("a2", "breakdowns", 5, 0.98, { author: "a1" }), reel("a3", "breakdowns", 4, 0.97),
    reel("c1", "charisma", 3, 0.5), reel("weak", "charisma", 9, 0.96, { strength: "directional" }),
    reel("low", "breakdowns", 1.6, 0.95), reel("mine", "breakdowns", 8, 0.94, { author: "maker" }),
    reel("long", "breakdowns", 3, 0.4, { duration: 120 })] }));
  const day1 = run("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-21", "--write");
  assert.deepEqual(day1.picks.map(pick => pick.content_key), ["instagram:a1", "instagram:c1", "instagram:a3"]);
  assert.deepEqual(day1.rejected, { already_shown: 0, own_post: 1, below_multiple: 1, no_pillar: 0, weak_or_missing_baseline: 1 });
  assert.match(day1.picks[0].remake, /possible if/);
  assert.match(refuse("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-21", "--write").stderr, /already recorded/);
  // 第二天：用过的全部排除，只剩作者重复的 a2 与超长的 long；不凑数。
  const day2 = run("pick", "--library", library, "--enrichment", enrichment, "--date", "2026-10-22", "--write");
  assert.deepEqual(day2.picks.map(pick => pick.content_key), ["instagram:a2", "instagram:long"]);
  assert.match(day2.picks[1].remake, /longer than 90 seconds/);
  assert.match(day2.note, /never pad/);

  // YouTube 结果用 account_breakout / channel / views，归一后同样可选。
  const youtube = path.join(temp, "yt.json");
  await writeFile(youtube, JSON.stringify({ schema_version: "youtube-trend-enrichment.v1", items: [{ content_key: "youtube:v1",
    url: "https://www.youtube.com/shorts/v1", platform: "youtube", final_score: 0.9, channel: { id: "UCxxxxxxxxxxxxxxxxxxxxxx", title: "Chan" },
    metrics: { views: 90000 }, account_breakout: { multiple: 4.2, cohort_median: 20000, comparable_count: 15, evidence_strength: "moderate" },
    sources: [{ intent_id: "charisma.1" }], duration_seconds: 45 }] }));
  const mixed = run("pick", "--library", library, "--enrichment", youtube, "--date", "2026-10-23");
  assert.deepEqual(mixed.picks.map(pick => [pick.author, pick.views, pick.author_posts_compared]), [["Chan", 90000, 15]]);
  assert.match(refuse("pick", "--library", library, "--enrichment", groups).stderr, /not a staged enrich/);
});
