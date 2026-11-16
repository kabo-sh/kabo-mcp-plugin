import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const han = /\p{Script=Han}/u;
const script = (skill, name) => path.join(root, "skills", skill, "scripts", name);
const options = { encoding: "utf8", maxBuffer: 4 * 1024 * 1024, timeout: 30_000 };
const run = (...args) => execFileSync("python3", ["-I", "-B", ...args], options);
async function workspace(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-language-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  return temp;
}
async function jsonFile(temp, name, data) {
  const file = path.join(temp, name);
  await writeFile(file, JSON.stringify(data));
  return file;
}

// Run the real CLI: omitting the language must create an English draft, an explicit Chinese still works;
// a wrong language must not be silently swapped.
test("deep seeds default to English; explicit Chinese and invalid languages are handled separately", async t => {
  const temp = await workspace(t);
  const source = await jsonFile(temp, "input.json", {
    schema_version: "deep-synthesis-input.v1", analysis_id: "language-fixture", watched: [], unwatched: [],
  });
  const stability = await jsonFile(temp, "stability.json", {
    schema_version: "catalog-stability.v1", analysis_id: "language-fixture", rise_fade: [],
  });
  const cli = script("review-creator-account-deep", "read_deep_synthesis_packet.py");
  const englishSeed = path.join(temp, "english.json");
  const packet = JSON.parse(run(cli, source, "--seed", englishSeed));
  assert.equal(packet.analysis_id, "language-fixture");
  assert.equal(JSON.parse(await readFile(englishSeed, "utf8")).output_language, "en");
  const chineseSeed = path.join(temp, "chinese.json");
  run(cli, source, "--seed", chineseSeed, "--output-language", "zh-CN", "--stability", stability);
  assert.equal(JSON.parse(await readFile(chineseSeed, "utf8")).output_language, "zh-CN");
  const rejected = spawnSync("python3", ["-I", "-B", cli, source, "--output-language", "invalid"], options);
  assert.notEqual(rejected.status, 0);
  assert.match(rejected.stderr, /invalid choice/);
  assert.doesNotMatch(rejected.stderr, han);
});

// Generate the full catalog digest and check that original titles are not translated; the final report
// still keeps the explicit Chinese branch.
test("deep catalog summaries and baseline notes use English, keep original titles, and pluralize correctly", () => {
  const output = JSON.parse(run("-c", String.raw`
import json, sys
sys.path.insert(0, sys.argv[1])
from build_catalog_stability import build_catalog_stability
from compose_catalog_plus import compose_catalog_plus
from compose_deep_review import _baseline_lines
analysis = {"analysis_id": "language-fixture", "platform": "instagram", "scope": {"account": "example", "followers": 100},
            "rankings": [{"content_id": "post-1", "title": "保留原始标题", "format": "reel", "url": "https://www.instagram.com/another/reel/fixture/",
                          "metrics": {"views": 75, "likes": -1}, "view_multiple_vs_format_median": 1}]}
cases = []
for followers in (None, 50, 1000, 150):
    analysis["scope"]["followers"] = followers
    stability = build_catalog_stability(analysis)
    cases.append({"memo": compose_catalog_plus(analysis, stability), "median": stability["median_views"], "readings": stability["readings"]})
stability["rise_fade"] = [{"format": "reel", "status": "rise", "earlier_view_share": 0.2, "later_view_share": 0.8},
                          {"format": "video", "status": "fade", "earlier_view_share": 0.8, "later_view_share": 0.2}]
cases.append({"memo": compose_catalog_plus(analysis, stability), "median": stability["median_views"], "readings": stability["readings"]})
english = {}
for count in (1, 2):
    stability["hidden_likes_n"] = count
    stability["other_handle_n"] = count
    english[str(count)] = _baseline_lines(stability, "en")
chinese = _baseline_lines({"hidden_likes_n": 1}, "zh-CN")
print(json.dumps({"cases": cases, "english": english, "chinese": chinese}))
`, path.dirname(script("review-creator-account-deep", "compose_catalog_plus.py"))));
  for (const item of output.cases) {
    assert.equal(item.median, 75);
    assert.match(item.memo, /保留原始标题/);
    assert.doesNotMatch(item.memo.replaceAll("保留原始标题", ""), han);
    assert.doesNotMatch(item.readings.join("\n"), han);
    assert.match(item.memo, /No videos have been watched/);
  }
  assert.match(output.cases.at(-1).memo, /formats gaining view share \(reel\)/);
  assert.match(output.cases.at(-1).memo, /formats losing view share \(video\)/);
  assert.match(output.english["1"].join("\n"), /1 post has its likes hidden/);
  assert.match(output.english["1"].join("\n"), /1 post has its views counted/);
  assert.match(output.english["2"].join("\n"), /2 posts have their likes hidden/);
  assert.doesNotMatch(Object.values(output.english).flat().join("\n"), han);
  assert.match(output.chinese.join("\n"), han);
});

// Limitation notes are generated by the plugin and must be English; server limitations and verbatim
// audience quotes are kept as they come from the source.
test("comment-evidence pagination, partial-completion, and duplicate notes are English; source text stays unchanged", async t => {
  const temp = await workspace(t);
  const cli = script("develop-content-ideas", "project_comments.py");
  const base = {
    schema_version: "1.0", connector_id: "youtube-public", operation: "list_comments",
    status: "completed_partial", evidence_ref: "fixture-comments", retrieved_at: "2026-10-23T00:00:00Z", limitations: [],
    data: { rows: [{ id: "comment-1", text: "原始评论", source_url: "https://www.youtube.com/watch?v=abcdefghijk" }], page: { next_page_token: "page-2" } },
  };
  const first = await jsonFile(temp, "first.json", base);
  const second = await jsonFile(temp, "second.json", {
    ...base, evidence_ref: "fixture-comments-2", limitations: ["来源限制原文"],
    data: { ...base.data, rows: [{ ...base.data.rows[0], text: "changed comment" }] },
  });
  const output = path.join(temp, "youtube.json");
  run(cli, output, first, second);
  const projected = JSON.parse(await readFile(output, "utf8"));
  assert.equal(projected.comments.length, 1);
  assert.equal(projected.comments[0].text, "原始评论");
  assert.ok(projected.limitations.includes("来源限制原文"));
  const owned = projected.limitations.filter(line => line !== "来源限制原文").join("\n");
  assert.doesNotMatch(owned, han);
  assert.match(owned, /more pages/);
  assert.match(owned, /partially complete/);
  assert.match(owned, /duplicate comment changed/);
  const tiktok = await jsonFile(temp, "tiktok.json", {
    ...base, connector_id: "tiktok-discovery", status: "completed",
    data: { aweme_id: "1234567890", rows: [{ id: "1234", text: "Original comment", source_url: "https://www.tiktok.com/@example/video/1234567890" }], page: { has_more: true } },
  });
  const tiktokOutput = path.join(temp, "tiktok-context.json");
  run(cli, tiktokOutput, tiktok);
  const limits = JSON.parse(await readFile(tiktokOutput, "utf8")).limitations.join("\n");
  assert.doesNotMatch(limits, han);
  assert.match(limits, /inline replies are previews only/);
  const help = run(cli, "--help");
  assert.doesNotMatch(help, han);
});

// Render a report with actually missing inputs: the English region label must not fall back to a Chinese
// prompt.
test("the creative report uses English prompts under en, en-US, and en-GB", async t => {
  const temp = await workspace(t);
  const cli = script("develop-content-ideas", "render_idea_report.py");
  for (const language of ["en", "en-US", "en-GB"]) {
    const source = await jsonFile(temp, `${language}.json`, {
      schema_version: "idea-set.v3-candidate1", report_language: language,
      status: "needs_selection_context", task_intent: "open_shortlist", source_mode: "brief_only",
      overview: { headline: "Choose a topic", missing_context_effect: "A topic is needed to suggest relevant ideas.", recommended_candidate_ids: [] },
      ideas: [], gates: { blocked_reasons: [], selection_missing: ["explicit_content_topic_or_upstream_evidence"], production_missing: [] },
      interaction: { next_actions: ["answer_selection_question"] }, evidence_summary: { data_gaps: [] },
      evidence_gap_translations: [
        { source_text: "needs_selection_context", report_text: "needs topic or context" },
        { source_text: "open_shortlist", report_text: "idea shortlist" },
        { source_text: "brief_only", report_text: "brief only" },
      ],
    });
    const concise = path.join(temp, `${language}-concise.md`);
    const full = path.join(temp, `${language}-full.md`);
    run(cli, source, "--concise", concise, "--full", full);
    const rendered = await readFile(concise, "utf8");
    assert.match(rendered, /What topic or niche should the video cover\?/);
    assert.match(rendered, /Provide missing selection details/);
    assert.doesNotMatch(rendered, han);
    assert.doesNotMatch(await readFile(full, "utf8"), han);
  }
});
