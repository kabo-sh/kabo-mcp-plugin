// research-instagram-trends: when one lane returns 90+ items the Gate table spans three pages, and in
// production (2026-11-05..08) the model ended its turn without writing scores.
// discover first keeps GATE_ITEMS_PER_LANE items per lane by a deterministic rule (alternating top
// search-ranked and hottest by discovery heat, original order),
// writes them into the eligible slot, and the later Gate, ranking and Snapshot read the same copy. This
// calls that step in drive.py directly, without network.
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

// Item n: search rank n+1; heat runs opposite to rank, the hottest is last, and items at both ends should
// be kept.
const item = (n, total) => ({ content_key: `instagram:reel:K${String(n).padStart(3, "0")}`, platform: "instagram", caption: `item ${n}`,
  metrics: n % 7 === 0 ? { like_count: 100 * n } : { play_count: 1000 * n }, sources: [{ query: "q", rank: n + 1 }] });
const set = (count) => ({ schema_version: "trend-candidate-set.v1", candidate_set_id: "set-1", platform: "instagram",
  coverage: { candidate_count: count }, items: Array.from({ length: count }, (_, n) => item(n, count)) });

test("Gate candidate cap: 94 candidates keep 30, top-ranked and hottest are retained, original order is kept, other fields and candidate_set_id unchanged", async (t) => {
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
  assert.deepEqual(kept.gate_shortlist, { input_items: 94, kept_items: 30, rule: "in the request window first, then undated, then outside; within each, best search rank and discovery heat alternating; up to 30", kept_in_window: 0 });
  const keys = kept.items.map((row) => row.content_key);
  assert.deepEqual(keys, [...keys].sort(), "original order");
  for (const n of [0, 1, 2, 14]) assert.ok(keys.includes(full.items[n].content_key), `rank ${n + 1}`);
  const hottest = [...full.items].sort((a, b) => (b.metrics.play_count ?? b.metrics.like_count * 24) - (a.metrics.play_count ?? a.metrics.like_count * 24));
  for (const row of hottest.slice(0, 15)) assert.ok(keys.includes(row.content_key), `heat ${row.content_key}`);
});

test("Gate candidate cap: a subset already filtered by the profile is capped further on top of it; nothing is written when under the cap", async (t) => {
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

// Collection recalls over a wider discovery window, and items outside the Request window are only
// excluded at the Snapshot (measured: 30 of 103 items were within "this week",
// and collecting in no particular order kept only 9): collect in-window items first, then those with no
// publish time, and fill in out-of-window items last.
test("Gate candidate cap: take items inside the Request window first, then those without a publish time, and fill with out-of-window items last", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-ig-shortlist-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  await writeFile(path.join(run, "trend-research-request.json"), JSON.stringify({ window: { since: "2026-11-03T00:00:00Z", until: "2026-11-10T00:00:00Z" } }));
  const full = set(100);
  // The first 70 rank and heat high but are outside the window; of the last 30, 20 are inside the window
  // and 10 have no publish time.
  full.items.forEach((row, n) => {
    if (n < 70) row.published_at = "2026-10-20T00:00:00Z";
    else if (n < 90) row.published_at = "2026-11-05T00:00:00Z";
    row.metrics = { play_count: 1_000_000 - 1000 * n };
  });
  await writeFile(path.join(run, "trend-candidate-set.json"), JSON.stringify(full));
  shortlist(run, "relevance");
  const kept = JSON.parse(await readFile(path.join(run, "trend-candidate-set-eligible.json"), "utf8"));
  assert.equal(kept.items.length, 30);
  assert.equal(kept.gate_shortlist.kept_in_window, 20);
  const dated = kept.items.map((row) => row.published_at ?? null);
  assert.equal(dated.filter((value) => value === "2026-11-05T00:00:00Z").length, 20);
  assert.equal(dated.filter((value) => value === null).length, 10);
});
