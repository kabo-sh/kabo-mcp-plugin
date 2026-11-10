// research-instagram-trends：一条车道回来 90 多条时 Gate 表翻三页，线上（2026-11-05..08）模型没写分就结束回合。
// discover 先按确定规则给每条车道留 GATE_ITEMS_PER_LANE 条（搜索排名靠前与发现热度最高的交替入选，原顺序），
// 写进 eligible 那个位置，后面的 Gate、排序、Snapshot 读同一份。这里直接调 drive.py 里的那一步，不联网。
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "research-instagram-trends", "scripts");

const HARNESS = String.raw`
import json, os, sys
sys.path.insert(0, sys.argv[1])
os.chdir(sys.argv[2])
import drive
drive.shortlist_for_gate(sys.argv[3])
print(json.dumps({"cap": drive.GATE_ITEMS_PER_LANE}))
`;
const shortlist = (run, lane) => JSON.parse(execFileSync("python3", ["-B", "-c", HARNESS, scripts, run, lane],
  { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", KABO_STATIC_RUN_DIR: run } }).trim().split("\n").at(-1));

// 第 n 条：搜索排名 n+1；热度与排名反着来，最热的排在最后，两头的条目都该留下。
const item = (n, total) => ({ content_key: `instagram:reel:K${String(n).padStart(3, "0")}`, platform: "instagram", caption: `item ${n}`,
  metrics: n % 7 === 0 ? { like_count: 100 * n } : { play_count: 1000 * n }, sources: [{ query: "q", rank: n + 1 }] });
const set = (count) => ({ schema_version: "trend-candidate-set.v1", candidate_set_id: "set-1", platform: "instagram",
  coverage: { candidate_count: count }, items: Array.from({ length: count }, (_, n) => item(n, count)) });

test("Gate 候选上限：94 条留 30 条，排名前列与最热的都在，保持原顺序，其余字段与 candidate_set_id 不变", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-ig-shortlist-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  const full = set(94);
  await writeFile(path.join(run, "trend-candidate-set.json"), JSON.stringify(full));
  const { cap } = shortlist(run, "relevance");
  assert.equal(cap, 30);
  const kept = JSON.parse(await readFile(path.join(run, "trend-candidate-set-eligible.json"), "utf8"));
  assert.equal(kept.items.length, 30);
  assert.equal(kept.candidate_set_id, "set-1");
  assert.deepEqual(kept.coverage, full.coverage);
  assert.deepEqual(kept.gate_shortlist, { input_items: 94, kept_items: 30, rule: "best search rank and discovery heat, alternating, up to 30" });
  const keys = kept.items.map((row) => row.content_key);
  assert.deepEqual(keys, [...keys].sort(), "原顺序");
  for (const n of [0, 1, 2, 14]) assert.ok(keys.includes(full.items[n].content_key), `排名第 ${n + 1}`);
  const hottest = [...full.items].sort((a, b) => (b.metrics.play_count ?? b.metrics.like_count * 24) - (a.metrics.play_count ?? a.metrics.like_count * 24));
  for (const row of hottest.slice(0, 15)) assert.ok(keys.includes(row.content_key), `热度 ${row.content_key}`);
});

test("Gate 候选上限：已有画像过滤的子集在它上面再收；不超过上限时什么都不写", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-ig-shortlist-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  await writeFile(path.join(run, "trend-candidate-set-reach.json"), JSON.stringify(set(90)));
  await writeFile(path.join(run, "trend-candidate-set-reach-eligible.json"), JSON.stringify({ ...set(40), eligibility: { kept_items: 40 } }));
  shortlist(run, "reach");
  const kept = JSON.parse(await readFile(path.join(run, "trend-candidate-set-reach-eligible.json"), "utf8"));
  assert.equal(kept.items.length, 30);
  assert.equal(kept.gate_shortlist.input_items, 40);
  assert.deepEqual(kept.eligibility, { kept_items: 40 });

  await writeFile(path.join(run, "trend-candidate-set.json"), JSON.stringify(set(25)));
  shortlist(run, "relevance");
  await assert.rejects(readFile(path.join(run, "trend-candidate-set-eligible.json"), "utf8"));
});
