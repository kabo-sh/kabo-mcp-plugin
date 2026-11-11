// diagnose-reach-drop 的多来源：用户口述的数字可以和导入的公开数据放进同一份计划，
// 各自挂自己的来源、在报告里标出；比较只在同一来源内做，单组数字作为观察交出。
// 夹具是中性的合成账号数据。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const workflow = path.join(root, "skills", "diagnose-reach-drop", "scripts", "run_traffic_workflow.py");
const OBSERVED = "2026-11-01T00:00:00Z";
const daysAgo = (days) => new Date(Date.parse(OBSERVED) - days * 86400000).toISOString().replace(".000", "");

// 只含 from_analysis 读取的字段：账号、观察时间与每条内容的公开指标。
const analysis = {
  schema_version: "account-analysis.v3", analysis_id: "fixture", platform: "instagram",
  scope: { account: "@sample.account", observed_at: OBSERVED },
  rankings: [40, 36, 32, 12, 9, 3].map((days, index) => ({
    content_id: `post-${days}`, format: "reel", published_at: daysAgo(days),
    metrics: { views: [9000, 10000, 11000, 4000, 5000, 800][index] },
  })),
};

const publicDrop = {
  id: "drop", kind: "recent_drop", intent: "diagnose", metric: "views", format: "reel",
  ask: "Compare recent and earlier reels.", selection_reason: "Public history of the account.",
  groups: [{ label: "earlier", record_ids: ["post-40", "post-36", "post-32"] },
    { label: "recent", record_ids: ["post-12", "post-9", "post-3"] }],
};
const userSkip = {
  id: "brief", kind: "recent_drop", intent: "diagnose", metric: "three_second_skip_rate_percent", format: "reel",
  ask: "How did the named reel hold viewers?", selection_reason: "The user gave this reel's insights.",
  source: { kind: "user_supplied", locator: "creator message" },
  groups: [{ label: "named reel", values: [80], content_ids: ["named-reel"] }],
};

function plan(questions) {
  return {
    schema_version: "traffic-workflow-brief.v1", platform: "instagram", account: "@sample.account",
    source: { kind: "account_analysis", locator: "account_analysis.json" }, coverage: [],
    user_request: "Why did my latest reel get so little reach?", questions,
  };
}

async function prepare(payload) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "reach-sources-"));
  try {
    const file = path.join(dir, "account_analysis.json");
    await writeFile(file, JSON.stringify(analysis));
    const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
    delete env.KABO_STATIC_RUN_DIR;
    const result = spawnSync("python3", ["-B", workflow, "prepare", "-", "--output-dir", dir, "--language", "en",
      "--analysis", file], { input: JSON.stringify(payload), env, encoding: "utf8" });
    const out = result.stdout + result.stderr;
    let assessment = null;
    let evidence = "";
    try {
      assessment = JSON.parse(await readFile(path.join(dir, "reach_drop_assessment.json"), "utf8"));
      evidence = await readFile(path.join(dir, "TRAFFIC_EVIDENCE.md"), "utf8");
    } catch { /* needs_correction 时不产出 */ }
    return { out, assessment, evidence };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("user-supplied numbers join imported public data under their own labelled source", async () => {
  const { out, assessment, evidence } = await prepare(plan([publicDrop, userSkip]));
  assert.ok(assessment, out);
  const kinds = Object.fromEntries(assessment.sources.map((source) => [source.id, source.kind]));
  const [drop, skip] = assessment.questions;
  assert.equal(kinds[drop.facts[0].source_ref], "public");
  assert.ok(drop.facts[0].change, "the public comparison still runs");
  assert.equal(kinds[skip.facts[0].source_ref], "user_supplied");
  // 单组：数值作为观察交出，没有变化比，也写明缺对照。
  assert.equal(skip.facts[0].change, null);
  assert.equal(skip.facts[0].groups[0].median, 80);
  assert.ok(skip.facts[0].limits.includes("no_comparison_group"));
  assert.ok(skip.missing.includes("earlier_and_recent_performance_records"));
  assert.match(evidence, /Source: user-supplied, not verified\./);
  assert.match(evidence, /One group only: these values are observations, not a comparison\./);
  // 交给创作者的最终报告由 compose_traffic.compose 组装，同样要带出来源标注。
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
  const final = spawnSync("python3", ["-B", "-c",
    "import json,sys; sys.path.insert(0, sys.argv[1]); from compose_traffic import compose; "
    + "print(compose(json.loads(sys.stdin.read()), {}, 'en'))",
    path.dirname(workflow)], { input: JSON.stringify(assessment), env, encoding: "utf8" });
  assert.match(final.stdout + final.stderr, /Source: user-supplied, not verified\./);
});

test("values left on the plan's public source are sent back for their own source", async () => {
  const { source: _, ...unlabelled } = userSkip;
  const { out, assessment } = await prepare(plan([publicDrop, unlabelled]));
  assert.equal(assessment, null);
  assert.match(out, /needs_correction/);
  assert.match(out, /give each question that carries values its own source/);
});

test("one comparison never mixes sources", () => {
  // 计划层面跨问题引用就会被拦；这里直接喂给比较函数，确认它自己也不跨来源比。
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
  const code = [
    "import sys; sys.path.insert(0, sys.argv[1]); from analyze_traffic import performance",
    "row = lambda i, src: {'id': i, 'content_id': i, 'format': 'reel', 'metrics': {'views': 1}, 'source_ref': src}",
    "q = {'kind': 'recent_drop', 'metric': 'views'}",
    "try:\n performance(q, [('a', [row('1', 'public')]), ('b', [row('2', 'user')])])\nexcept ValueError as e:\n print(e)",
  ].join("\n");
  const result = spawnSync("python3", ["-B", "-c", code, path.dirname(workflow)], { env, encoding: "utf8" });
  assert.match(result.stdout + result.stderr, /a comparison uses one source/);
});
