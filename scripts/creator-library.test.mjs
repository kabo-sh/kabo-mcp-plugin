// start-with-kabo、pick-daily-viral-videos、review-new-posts 共用的 creator_library.py：离线测试，不联网。
// 覆盖：三份副本相同；画像与每日推荐只读后台工具的结果（prepare_creator_profile、get_creator_profile、
// get_for_you_videos），本地不推导；每日推荐的展示限制与各 status 分支；24 小时复盘的选取与同龄基线；
// 账号回顾；复盘第一次运行（或不留文件的宿主）自建库，没有支柱也照常复盘；
// 以及 history-request → 暂存组合结果 → snapshot → ingest 的整条路。
// 后台的两个新工具尚未上线：这里的结果形状按约定契约构造，真实宿主联调要等后台上线后另做。
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const owners = ["start-with-kabo", "pick-daily-viral-videos", "review-new-posts"];
// 三份副本逐字相同（第一条测试守着）；用复盘那份，因为只有它带取数用的 static_host 白名单与快照拼装脚本。
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

test("三份 creator_library.py 逐字相同；复盘的快照拼装脚本与账号复盘的相同；引导与推荐不再带取数脚本", async () => {
  const copies = new Set(await Promise.all(owners.map(id => readFile(path.join(root, "skills", id, "scripts/creator_library.py"), "utf8"))));
  assert.equal(copies.size, 1);
  const reference = await readFile(path.join(root, "skills/review-creator-account/scripts/build_public_snapshot.py"), "utf8");
  assert.equal(await readFile(path.join(root, "skills/review-new-posts/scripts/build_public_snapshot.py"), "utf8"), reference);
  // 引导与每日推荐不读作品历史：不带快照拼装脚本，static_host 也不收任何取数结果，只建运行目录。
  for (const id of ["start-with-kabo", "pick-daily-viral-videos"]) {
    await assert.rejects(access(path.join(root, "skills", id, "scripts/build_public_snapshot.py")));
    const probe = "import json, runpy, sys\nm = runpy.run_path(sys.argv[1])\nprint(json.dumps([sorted(m['CONNECTOR_TOOLS']), sorted(m['AGGREGATE_TOOLS']), sorted(m['HANDED_COMPOSITES'])]))";
    const tables = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, path.join(root, "skills", id, "scripts/static_host.py")], options));
    assert.deepEqual(tables, [[], [], []], id);
  }
});

// 被删掉的本地推导与本地检索：三个 Skill 的说明里不得再引用这些命令、文件与工具。
const REMOVED = ["propose-pillars", "save-pillars", "media-request", "transcripts", "pick-request", "candidates --", "clusters.json",
  "confirmed.json", "schedule.json", "set-profile", "collect_video_media", "collect_instagram_trend_candidates",
  "collect_youtube_trend_candidates", "enrich_instagram_shortlist", "enrich_youtube_shortlist", "evidence_strength", "0.8 times",
  "creator_library.py' posts", "creator_library.py' pick "];

test("三个 Skill 的说明不再引用已删除的命令、文件与本地推导工具；推荐只用 get_for_you_videos，画像只经 prepare_creator_profile 与 get_creator_profile", async () => {
  const texts = {};
  for (const id of owners) {
    const files = [path.join(root, "skills", id, "SKILL.md")];
    for (const name of ["pillars.md", "profile-edits.md", "host-schedules.md", "review-format.md"]) {
      const file = path.join(root, "skills", id, "references", name);
      try { await access(file); files.push(file); } catch { /* 该 Skill 没有这份说明 */ }
    }
    texts[id] = (await Promise.all(files.map(file => readFile(file, "utf8")))).join("\n");
    for (const word of REMOVED) assert.equal(texts[id].includes(word), false, `${id} 仍引用 ${word}`);
  }
  const allowed = (id) => texts[id].match(/^allowed-tools: (.*)$/m)[1].split(" ");
  assert.deepEqual(allowed("pick-daily-viral-videos").sort(), ["get_for_you_videos", "list_connected_accounts"]);
  for (const name of ["prepare_creator_profile", "get_creator_profile", "update_content_preferences", "get_for_you_videos", "connect_public_account"])
    assert.ok(allowed("start-with-kabo").includes(name), name);
  assert.equal(allowed("start-with-kabo").includes("collect_account_history"), false);
  // 复盘保持原样：自己读历史与评论，支柱从画像读。
  for (const name of ["collect_account_history", "get_creator_profile", "list_connected_accounts"]) assert.ok(allowed("review-new-posts").includes(name), name);
  // 开场：脚本两句，说明里也写两句加一个问题；不再承诺「一分钟内」看到账号事实。
  assert.equal(run("opening").tell_creator_now.length, 2);
  assert.match(texts["start-with-kabo"], /two short messages and one question/);
  assert.doesNotMatch(texts["start-with-kabo"], /within about a minute|three short messages/);
  // 后台推断不出赛道时只问创作者一次，原话带 niche 重试，模型不替创作者编。
  assert.match(texts["start-with-kabo"], /"niche": "<the creator's answer, in their\s+own words>"/);
  assert.match(texts["start-with-kabo"], /Never write the niche\s+yourself/);
  assert.match(texts["start-with-kabo"], /--niche-sent/);
  // 两处等待上限写在说明里，与脚本一致。
  assert.match(texts["start-with-kabo"], /at most 8 more\s+calls and at most 8 minutes/);
  assert.match(texts["pick-daily-viral-videos"], /at most 3\s+more calls and at most 10 minutes/);
  // 绑定前明确问一次。
  assert.match(texts["start-with-kabo"], /Ask before linking/);
  assert.doesNotMatch(texts["start-with-kabo"], /unless the creator objected/);
  // 推荐的证据口径：不说倍数、不说匹配支柱。
  assert.doesNotMatch(texts["pick-daily-viral-videos"], /times what @author usually gets|author_typical_views|pillar it matches/);
});

test("建库记下绑定时间；之后发布的作品满 24 小时才复盘一次，同龄基线取自别的作品", async t => {
  const temp = await workspace(t);
  const located = run("path", "--workspace", temp, "--platform", "instagram", "--handle", "@Maker");
  const library = located.library;
  assert.ok(library.endsWith(path.join("kabo-library", "instagram-maker")));
  // path 只给目录：两个 Skill 无人值守，它不能带要对创作者说的话。
  assert.deepEqual(Object.keys(located).sort(), ["exists", "library"]);
  assert.equal(located.exists, false);
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
  const stored = JSON.parse(await readFile(path.join(library, "posts.json"), "utf8")).posts;
  assert.deepEqual(Object.keys(stored).filter(id => ["guest", "photo"].includes(id)), []);
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

test("画像只整理后台结果：可见的主打内容按占比成为支柱，带证据、编辑上下文与被创作者隐藏的项；没有就说没有", async t => {
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
  // 支柱不再带检索词：每日推荐不再按支柱检索。
  assert.equal("search_queries" in proposal.candidates[0], false);
  assert.deepEqual(proposal.hidden_by_creator, ["Giveaways"]);
  assert.deepEqual(proposal.update_context, { account_id: "acc-1", expected_version: 3, basis: "2026-10-01T00:00:00Z" });
  assert.deepEqual(proposal.advice, []);
  assert.equal("tell_creator_now" in proposal, false);
  // 只有一项且后台标 no_qualifying_group：照样是合格支柱，不叫模型去作品里另找。
  const single = path.join(temp, "single.json");
  const one = profileResult([signature("sc9", "Only pillar", 0.4)]);
  one.structuredContent.effectiveContentProfile.signatureContentStatus = "no_qualifying_group";
  await writeFile(single, JSON.stringify(one));
  const lone = run("profile-pillars", "--profile", single);
  assert.equal(lone.advice.length, 1);
  assert.match(lone.advice[0], /present it as a valid pillar/);
  // 只有 content[0].text 的结果也认。
  await writeFile(single, JSON.stringify({ content: [{ type: "text", text: JSON.stringify(one.structuredContent) }] }));
  assert.equal(run("profile-pillars", "--profile", single).candidates.length, 1);
  // 没有主打内容时不编造，也不叫模型自己聚类。
  const empty = path.join(temp, "empty.json");
  await writeFile(empty, JSON.stringify(profileResult([])));
  const none = run("profile-pillars", "--profile", empty);
  assert.equal(none.status, "no_signature_content");
  assert.deepEqual(none.candidates, []);
  assert.match(none.note, /never group the posts yourself/);
  // 宿主标了 isError 的结果不当画像读。
  await writeFile(empty, JSON.stringify({ isError: true, content: [{ type: "text", text: "not_found" }] }));
  assert.match(refuse("profile-pillars", "--profile", empty).stderr, /refused/);
});

// prepare_creator_profile 的定稿出参（kabo#2176）：字段固定全出现，不适用时为 null。
const prepared = (status, extra = {}) => ({ structuredContent: { status, account_id: "00000000-0000-4000-8000-000000000001",
  job_id: null, failure_code: null, retryable: null, retry_after_seconds: null, ...extra } });

test("prepare_creator_profile：ready 去读画像；generating 严格按 retry_after 等，首次后最多再查 8 次、总等待不超过 480 秒；niche_required 问一次领域后带 niche 重试；其余照常往下走", async t => {
  const temp = await workspace(t);
  const file = path.join(temp, "prepare.json");
  const status = async (value, ...flags) => { await writeFile(file, JSON.stringify(value)); return run("profile-status", "--result", file, ...flags); };
  assert.equal((await status(prepared("ready"))).action, "read_profile");
  const first = await status(prepared("generating", { job_id: "job-1", retry_after_seconds: 60 }));
  assert.deepEqual([first.action, first.wait_seconds, first.next_flags], ["wait", 60, { "--attempt": 2, "--waited": 60 }]);
  assert.match(first.tell_creator_now, /few minutes/);
  // 后台一档 60 秒：8 次再查正好 480 秒，第 8 次之后停。
  let flags = { attempt: 1, waited: 0 }, waits = 0;
  for (;;) {
    const step = await status(prepared("generating", { retry_after_seconds: 60 }), "--attempt", String(flags.attempt), "--waited", String(flags.waited));
    if (step.action !== "wait") { assert.equal(step.action, "continue_without_profile"); assert.match(step.tell_creator_now, /not ready yet/); break; }
    waits += 1;
    flags = { attempt: step.next_flags["--attempt"], waited: step.next_flags["--waited"] };
  }
  assert.deepEqual([waits, flags.waited], [8, 480]);
  // 不缩短后台给的等待：剩余额度装不下下一次等待就停，不提前去查。
  assert.equal((await status(prepared("generating", { retry_after_seconds: 120 }), "--attempt", "3", "--waited", "400")).action, "continue_without_profile");
  // 没给 retry_after 时按 60 秒。
  assert.equal((await status(prepared("generating"), "--attempt", "2", "--waited", "60")).wait_seconds, 60);

  // niche_required：问一个问题；带了 niche 之后再遇到就不再问，往下走。
  const ask = await status(prepared("niche_required"));
  assert.equal(ask.action, "ask_niche");
  assert.match(ask.tell_creator_now, /can't tell your niche/);
  assert.match(ask.question, /one sentence/);
  assert.match(ask.then, /niche set to the creator's own words.*--niche-sent/);
  const again = await status(prepared("niche_required"), "--niche-sent");
  assert.equal(again.action, "continue_without_profile");
  assert.match(again.tell_creator_now, /no content pillars for now/);
  // 带 niche 重试后又进入 generating：从头计数，照常轮询。
  assert.equal((await status(prepared("generating", { retry_after_seconds: 60 }), "--attempt", "1", "--waited", "0", "--niche-sent")).action, "wait");

  const thin = await status(prepared("insufficient_posts", { retry_after_seconds: 86000 }));
  assert.equal(thin.action, "continue_without_profile");
  assert.match(thin.tell_creator_now, /enough videos/);
  assert.equal(thin.retry_after_seconds, 86000);
  const failed = await status(prepared("failed", { failure_code: "profile_build_failed", retryable: true, retry_after_seconds: 300 }));
  assert.equal(failed.action, "continue_without_profile");
  assert.equal(failed.failure_code, "profile_build_failed");
  assert.match(failed.tell_creator_now, /tried again later/);
  assert.equal(failed.reported.failure_code, "profile_build_failed");
  // 契约之外的 status 与工具错误都按失败处理，原样带回。
  const odd = await status({ status: "queued_somewhere" });
  assert.deepEqual([odd.status, odd.action, odd.reported.status], ["queued_somewhere", "continue_without_profile", "queued_somewhere"]);
  const notFound = await status({ isError: true, content: [{ type: "text", text: "not_found: account is not yours" }] });
  assert.deepEqual([notFound.status, notFound.failure_code], ["failed", "not_found: account is not yours"]);
});

// ---- 每日推荐：只读 get_for_you_videos 的结果，按 SKILL.md 写明的限制选 3 条。

const video = (id, author, rank, extra = {}) => ({ content_id: id, url: `https://www.instagram.com/reel/${id}/`, platform: "instagram",
  format: "reel", title: `title ${id}`, caption: null, author_handle: author, published_at: "2026-11-05T10:00:00Z", views: 100000 - rank * 1000, rank,
  reason: `Popular in your niche (${id})`, ...extra });
// get_for_you_videos 的定稿出参（kabo#2176）：字段固定全出现，不适用时为 null；windows 三个键都在。
const forYouResult = (status, extra = {}) => ({ structuredContent: { status, account_id: "00000000-0000-4000-8000-000000000001",
  platform: "instagram", reason: null, failure_code: null, retryable: null, retry_after_seconds: null, generated_at: null,
  expires_at: null, next_refresh_at: null, windows: null, ...extra } });
const ready = (windows, extra = {}) => forYouResult("ready", { windows: { "7d": [], "30d": [], "24h": [], ...windows },
  generated_at: "2026-11-11T00:00:00Z", expires_at: "2026-11-12T00:00:00Z", next_refresh_at: "2026-11-12T00:00:00Z", ...extra });

test("每日推荐：7 天窗按排名优先，再用 30 天、24 小时补；跳过本人、同一作者、以前展示过的与跨窗重复；不凑数；零条的日子也记下", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "kabo-library", "instagram-maker");
  const result = path.join(temp, "for-you.json");
  const forYou = async (value, date, ...flags) => {
    await writeFile(result, JSON.stringify(value));
    return run("for-you", "--library", library, "--result", result, "--handle", "@Maker", "--date", date, "--write", ...flags);
  };
  // 7 天窗里：rank 乱序给出；本人（大小写与 @ 不同）一条、同一作者两条、没有链接一条。
  const day1 = await forYou(ready({
    "7d": [video("b", "beta", 2), video("a", "Alpha", 1), video("own", "@MAKER", 3), video("a2", "@alpha", 4), video("nolink", "nl", 5, { url: null })],
    "30d": [video("a", "Alpha", 1), video("c", "gamma", 2)],
    "24h": [video("d", "delta", 1)],
  }), "2026-11-11");
  assert.equal(day1.status, "ready");
  assert.deepEqual(day1.picks.map(pick => [pick.content_id, pick.window, pick.rank]), [["a", "7d", 1], ["b", "7d", 2], ["c", "30d", 2]]);
  assert.deepEqual(day1.skipped, { shown_on_earlier_day: 0, own_post: 1, same_author: 1, duplicate: 1, no_link: 1 });
  assert.equal(day1.picks[0].reason, "Popular in your niche (a)");
  assert.equal(day1.picks[0].views, 99000);
  // 没有时长：复刻只说「会先检查」，不臆测。
  assert.match(day1.picks[0].remake, /checks whether this video qualifies/);
  assert.equal(day1.recorded, true);
  assert.equal(day1.generated_at, "2026-11-11T00:00:00Z");
  // 证据只有后台给的口径：没有倍数、没有支柱。
  for (const key of ["multiple", "author_typical_views", "pillar_id"]) assert.equal(key in day1.picks[0], false);

  // 同一天再跑：不重选、不覆盖，即便后台这次给了别的结果。
  const again = await forYou(ready({ "7d": [video("z", "zeta", 1)] }), "2026-11-11");
  assert.equal(again.already_recorded, true);
  assert.deepEqual(again.picks.map(pick => pick.content_id), ["a", "b", "c"]);
  assert.deepEqual(run("picks", "--library", library, "--date", "2026-11-11").picks.map(pick => pick.content_id), ["a", "b", "c"]);

  // 第二天：昨天展示过的按编号或链接（去掉 query、www 与结尾斜杠）都认出来；只剩两条就给两条。
  const day2 = await forYou(ready({
    "7d": [video("a", "Alpha", 1), { ...video("b-again", "beta", 2), content_id: "b-again", url: "https://instagram.com/reel/b?igsh=xyz" }],
    "30d": [video("e", "epsilon", 1)],
    "24h": [video("d", "delta", 1)],
  }), "2026-11-12");
  assert.deepEqual(day2.picks.map(pick => [pick.content_id, pick.window]), [["e", "30d"], ["d", "24h"]]);
  assert.equal(day2.skipped.shown_on_earlier_day, 2);
  assert.match(day2.note, /never pad/);

  // 第三天：全部展示过（或没有编号也没有链接、无法识别）——零条，也记下「今天查过」。
  const day3 = await forYou(ready({ "7d": [video("a", "Alpha", 1)], "30d": [], "24h": [video("d", "delta", 1)] }), "2026-11-13");
  assert.deepEqual(day3.picks, []);
  assert.equal(day3.recorded, true);
  const checked = run("picks", "--library", library, "--date", "2026-11-13");
  assert.deepEqual([checked.checked, checked.picks], [true, []]);
  assert.deepEqual(run("picks", "--library", library, "--date", "2026-11-14"), { date: "2026-11-14", checked: false, picks: null, recorded_days: ["2026-11-11", "2026-11-12", "2026-11-13"] });

  // 去重集合不混入空值：编号与链接都缺的旧记录不会让别的视频被当成「展示过」。
  const stored = JSON.parse(await readFile(path.join(library, "picks.json"), "utf8"));
  stored.days["2026-11-10"] = [{ content_id: null, url: "", keys: ["", null] }];
  await writeFile(path.join(library, "picks.json"), JSON.stringify(stored));
  const day4 = await forYou(ready({ "7d": [video("f", "phi", 1, { content_id: "" })] }), "2026-11-14");
  assert.deepEqual(day4.picks.map(pick => pick.url), ["https://www.instagram.com/reel/f/"]);
  assert.deepEqual(day4.picks[0].keys, ["url:instagram.com/reel/f"]);
  // 契约没有时长：复刻一律「会先检查」；缺 platform 时从链接认；没有 title 时用 caption。
  const day5 = await forYou(ready({ "7d": [video("g", "g1", 1, { platform: null, title: null, caption: "caption g" })] }), "2026-11-15");
  assert.equal(day5.picks[0].platform, "instagram");
  assert.equal(day5.picks[0].title, "caption g");
  assert.match(day5.picks[0].remake, /checks whether this video qualifies/);
});

test("每日推荐的各 status：generating 严格按 retry_after 有上限地等，not_eligible（含 unavailable）与 failed（转述 failure_code）一句话结束；工具错误与未知 status 按失败；都不记当天", async t => {
  const temp = await workspace(t);
  const library = path.join(temp, "lib");
  const result = path.join(temp, "for-you.json");
  const forYou = async (value, ...flags) => {
    await writeFile(result, JSON.stringify(value));
    return run("for-you", "--library", library, "--result", result, "--handle", "maker", "--date", "2026-11-11", "--write", ...flags);
  };
  // 推荐：通常 120 秒，补画像时 300 秒；首次后最多再查 3 次、总等待不超过 600 秒。
  const waiting = await forYou(forYouResult("generating", { retry_after_seconds: 120 }));
  assert.deepEqual([waiting.action, waiting.wait_seconds, waiting.next_flags], ["wait", 120, { "--attempt": 2, "--waited": 120 }]);
  assert.match(waiting.progress_line, /still preparing/);
  // 两次 300 秒的补画像等待装得下，第三次装不下就停。
  assert.equal((await forYou(forYouResult("generating", { retry_after_seconds: 300 }), "--attempt", "2", "--waited", "300")).wait_seconds, 300);
  const overBudget = await forYou(forYouResult("generating", { retry_after_seconds: 300 }), "--attempt", "3", "--waited", "600");
  assert.equal(overBudget.action, "stop");
  const gaveUp = await forYou(forYouResult("generating", { retry_after_seconds: 120 }), "--attempt", "4", "--waited", "360");
  assert.equal(gaveUp.action, "stop");
  assert.match(gaveUp.message, /next run will bring them/);

  const expected = {
    no_linked_account: /No account is linked/, no_public_videos: /no public videos/, profile_insufficient: /more of your posts/,
    language_unknown: /which language/, unavailable: /not available for this account/, brand_new_reason: /reason: brand_new_reason/,
  };
  for (const [reason, pattern] of Object.entries(expected)) {
    const answer = await forYou(forYouResult("not_eligible", { reason, retry_after_seconds: reason === "no_linked_account" ? null : 3600 }));
    assert.deepEqual([answer.action, answer.reason], ["stop", reason]);
    assert.match(answer.message, pattern);
    assert.equal(answer.retry_after_seconds, reason === "no_linked_account" ? null : 3600);
  }
  const retryable = await forYou(forYouResult("failed", { failure_code: "upstream_timeout", retryable: true, retry_after_seconds: 600 }));
  assert.equal(retryable.failure_code, "upstream_timeout");
  assert.match(retryable.message, /upstream_timeout.*tried again later/);
  const final = await forYou({ structuredContent: { status: "failed", retryable: false, message: "provider quota" } });
  assert.match(final.message, /provider quota/);
  assert.doesNotMatch(final.message, /tried again/);
  // 多账号未指定是工具错误 validation_error，不是某个 status。
  const ambiguous = await forYou({ isError: true, content: [{ type: "text", text: "validation_error: account_id is required (acc-1, acc-2)" }] });
  assert.deepEqual([ambiguous.status, ambiguous.action], ["failed", "stop"]);
  assert.match(ambiguous.message, /validation_error/);
  const odd = await forYou({ structuredContent: { status: "paused", detail: 1 } });
  assert.deepEqual([odd.status, odd.action], ["paused", "stop"]);
  assert.match(odd.message, /status: paused/);
  assert.deepEqual(odd.reported, { status: "paused" });
  const blank = await forYou({});
  assert.equal(blank.status, "failed");
  // 以上都不是 ready：今天没有记录，下次运行会再问后台。
  assert.equal(run("picks", "--library", library, "--date", "2026-11-11").checked, false);
  await assert.rejects(access(path.join(library, "picks.json")));
  // ready 但 windows 为 null：零条，照样记下今天。
  const empty = await forYou(forYouResult("ready"));
  assert.deepEqual([empty.found, empty.recorded, empty.window_sizes], [0, true, { "7d": 0, "30d": 0, "24h": 0 }]);
});

test("每日回顾：粉丝变化、近 7 天对比常规水平、每个支柱的读数；没有两次读数时如实说明", async t => {
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
  assert.ok(first.limits.some(line => /only this run's reading/.test(line)));
  const t1 = "2026-10-21T10:00:00Z";
  run("ingest", "--library", library, "--snapshot", await snapshot(temp, "s1.json", t1, [...history(t0), item("new1", "2026-10-21T06:00:00Z", 700)], { followers: 1040 }));
  const recap = run("recap", "--library", library, "--date", "2026-10-21");
  // 第二次在同一个库上读到历史：宿主留住了文件，不再说「只有这一次读数」。
  assert.equal(recap.limits.some(line => /only this run's reading/.test(line)), false);
  assert.equal(run("show", "--library", library).fresh, false);
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

test("复盘第一次运行：没有本地库时从 Kabo 画像建库，回看 48 小时；没有画像或画像没有支柱也照常建库、复盘并出日报", async t => {
  const temp = await workspace(t);
  const profile = path.join(temp, "profile.json");
  await writeFile(profile, JSON.stringify(profileResult([signature("sc1", "Viral breakdowns", 0.6), signature("sc2", "Charisma tips", 0.3)])));
  const library = path.join(temp, "lib");
  // 每日推荐可能先在同一目录里写了 picks.json：不影响建库。
  run("for-you", "--library", library, "--result", await (async () => { const f = path.join(temp, "fy.json"); await writeFile(f, JSON.stringify(ready({ "7d": [video("a", "alpha", 1)] }))); return f; })(), "--date", "2026-10-21", "--write");
  const boot = run("bootstrap", "--library", library, "--platform", "instagram", "--handle", "@Maker", "--profile", profile);
  assert.equal(boot.fresh, true);
  assert.deepEqual(boot.pillars, ["viral-breakdowns", "charisma-tips"]);
  assert.match(refuse("bootstrap", "--library", library, "--platform", "instagram", "--handle", "maker", "--profile", profile).stderr, /already exists/);
  const shown = run("show", "--library", library);
  assert.equal(shown.pillars_source, "kabo_profile");
  assert.deepEqual(shown.pick_days, ["2026-10-21"]);

  // 没有画像（账号没在 Kabo 绑定）与画像没有支柱，两种都建得起来。
  for (const [name, extra] of [["no-profile", []], ["no-pillars", ["--profile", path.join(temp, "empty.json")]]]) {
    await writeFile(path.join(temp, "empty.json"), JSON.stringify(profileResult([])));
    const bare = path.join(temp, name);
    const built = run("bootstrap", "--library", bare, "--platform", "instagram", "--handle", "maker", ...extra);
    assert.deepEqual(built.pillars, [], name);
    assert.match(built.note, /no pillar section/);
    // 第一次读历史：48 小时内发布的作品进入复盘，更早的不进；账号编号由账号名认领。
    const observed = "2026-10-21T10:00:00Z";
    const rows = [item("fresh", "2026-10-20T08:00:00Z", 800), item("stale", "2026-10-17T08:00:00Z", 900), ...history("2026-10-21T10:00:00Z")];
    const ingested = run("ingest", "--library", bare, "--snapshot", await snapshot(temp, `${name}.json`, observed, rows, { followers: 500 }));
    assert.deepEqual(ingested.new_tracked_posts, ["fresh"]);
    assert.deepEqual(ingested.due.map(row => [row.content_id, row.checkpoint]), [["fresh", "24h"]]);
    // 没有支柱时只能归到 other。
    assert.match(refuse("set-pillar", "--library", bare, "--content-id", "fresh", "--pillar-id", "viral-breakdowns").stderr, /one of the library's pillars/);
    const facts = run("review-facts", "--library", bare, "--content-id", "fresh", "--checkpoint", "24h");
    assert.equal(facts.pillar_id, null);
    assert.ok(facts.limits.some(line => /only this run's reading/.test(line)));
    const review = path.join(temp, `${name}-review.md`);
    await writeFile(review, "review");
    run("record-review", "--library", bare, "--content-id", "fresh", "--checkpoint", "24h", "--report", review);
    assert.deepEqual(run("due", "--library", bare).due, []);
    const recap = run("recap", "--library", bare, "--date", "2026-10-21");
    assert.deepEqual(recap.pillars, []);
    assert.ok(recap.limits.some(line => /no confirmed pillars|no per-pillar reading/.test(line)));
    assert.equal(recap.followers.now, 500);
    // 常规水平取满 72 小时的作品：十条旧作品加上 stale，fresh 还在攒播放。
    assert.equal(recap.typical_settled_views, 1000);
    const daily = path.join(temp, `${name}-recap.md`);
    await writeFile(daily, "recap");
    assert.match(run("record-recap", "--library", bare, "--report", daily, "--date", "2026-10-21").report, /recaps\/2026-10-21\.md$/);
  }
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
  assert.equal(run("path", "--workspace", temp, "--platform", "instagram", "--handle", "neutral.creator").library, library);
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

