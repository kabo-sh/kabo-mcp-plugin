// diagnose-reach-drop 的近期掉量对比：一次公开快照里早发的帖子总是更“老”，累计值天然偏向前期。
// 近期更年轻却不低于前期，就直接说没有下降；近期更低时不设固定成熟天数，只给出发布时长差，
// 由书面分析结合用户问题推测。夹具是中性的合成账号数据。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const workflow = path.join(root, "skills", "diagnose-reach-drop", "scripts", "run_traffic_workflow.py");
const OBSERVED = "2026-11-01T00:00:00Z";
const daysAgo = (days) => new Date(Date.parse(OBSERVED) - days * 86400000).toISOString().replace(".000", "");

function group(label, rows) {
  return {
    label, values: rows.map(([, value]) => value), content_ids: rows.map(([days]) => `${label}-${days}`),
    published_at: rows.map(([days]) => daysAgo(days)), observed_at: rows.map(() => OBSERVED),
  };
}

function brief(format, earlier, recent, extra = {}) {
  return {
    schema_version: "traffic-workflow-brief.v1", platform: "youtube", account: "user-supplied-account",
    source: { kind: "user_supplied", locator: "numbers in the user's message" }, coverage: [],
    user_request: "Did views on my recent videos drop compared with earlier ones?",
    questions: [{ id: "drop", kind: "recent_drop", intent: "diagnose", metric: "views", format,
      ask: "Compare recent and earlier videos.", selection_reason: "The user supplied per-video views.",
      groups: [group("earlier", earlier), group("recent", recent)], ...extra }],
  };
}

async function run(payload) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "reach-age-"));
  try {
    const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
    delete env.KABO_STATIC_RUN_DIR;
    const result = spawnSync("python3", ["-B", workflow, "prepare", "-", "--output-dir", dir, "--language", "en"],
      { input: JSON.stringify(payload), env, encoding: "utf8" });
    const out = result.stdout + result.stderr;
    const assessment = JSON.parse(await readFile(path.join(dir, "reach_drop_assessment.json"), "utf8"));
    const evidence = await readFile(path.join(dir, "TRAFFIC_EVIDENCE.md"), "utf8");
    const verdicts = spawnSync("python3", ["-B", "-c",
      "import json,sys; sys.path.insert(0, sys.argv[1]); from compose_traffic import verdict; "
      + "a = json.load(open(sys.argv[2])); print('\\n'.join(verdict(q, z) for q in a['questions'] for z in (True, False)))",
      path.dirname(workflow), path.join(dir, "reach_drop_assessment.json")], { env, encoding: "utf8" });
    const fact = assessment.questions[0].facts.find((item) => item.type === "performance");
    return { out, fact, evidence, verdict: verdicts.stdout + verdicts.stderr };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

const EARLIER = [[40, 9000], [36, 10000], [32, 11000]];

test("younger recent posts that are not lower mean no decline", async () => {
  const { out, fact, verdict } = await run(brief("short_video", EARLIER, [[10, 12000], [6, 13000], [2, 9500]]));
  assert.equal(fact?.age_reading?.basis, "recent_younger_not_lower", out);
  assert.match(verdict, /^The recent posts are younger, yet their current cumulative median is not lower, so there is no sign of a decline/m);
  assert.match(verdict, /^近期内容发布时间更短，当前累计中位数却不低于前期，所以没有下降迹象/m);
});

test("a lower recent median reports the age gap, with no fixed maturity age", async () => {
  const { out, fact, evidence, verdict } = await run(brief("youtube_long", EARLIER, [[12, 4000], [9, 5000], [3, 800]]));
  assert.equal(fact?.age_reading?.basis, "recent_lower_younger", out);
  assert.equal(fact.age_reading.median_age_gap_hours, 27 * 24);
  assert.match(evidence, /Median age gap \(earlier − recent\): 648 hours\./);
  assert.match(verdict, /^The recent median is lower, but the recent posts are about 27 days younger at the median; this snapshot cannot separate/m);
  assert.match(verdict, /^近期中位数低于前期，但近期内容的发布时长中位数比前期少约 27 天；这份快照分不开/m);
  assert.doesNotMatch(evidence + verdict, /at least \d+ days old|满 \d+ 天/);
});

test("same-age, explicit-age and non-cumulative comparisons keep their existing verdicts", async () => {
  const sameAge = brief("short_video", EARLIER, [[12, 4000], [9, 5000]], { post_age_hours: 168 });
  for (const item of sameAge.questions[0].groups) { delete item.published_at; delete item.observed_at; }
  const same = await run(sameAge);
  assert.equal(same.fact?.age_reading, undefined, same.out);
  const policy = await run(brief("short_video", EARLIER, [[12, 4000], [9, 5000], [3, 800]],
    { minimum_age_hours: 72, age_policy_reason: "The user only counts posts older than three days." }));
  assert.equal(policy.fact?.age_reading, undefined, policy.out);
  const rate = brief("short_video", EARLIER, [[12, 4000], [9, 5000], [3, 800]]);
  rate.questions[0].metric = "average_view_duration_seconds";
  const average = await run(rate);
  assert.equal(average.fact?.age_reading, undefined, average.out);
});
