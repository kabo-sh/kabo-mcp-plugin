import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, writeFile, readFile, rm, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { packageFiles, checkPackage } from "./package-check.mjs";
import { deterministicZip, validatePackage } from "./openai-plugin-package.mjs";

const ids = ["analyze-content-video", "review-creator-account", "review-creator-account-deep", "create-script-and-packaging", "develop-content-ideas", "research-instagram-trends", "research-tiktok-trends", "research-youtube-trends", "analyze-creator-competitors", "analyze-tiktok-competitors", "remake-viral-video", "diagnose-reach-drop", "recommend-publish-timing", "plan-platform-monetization", "verify-platform-rule", "optimize-creator-brand", "plan-content-calendar", "price-creator-brand-deals", "start-with-kabo", "pick-daily-viral-videos", "review-new-posts"];

async function installed(t) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-static-installed-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const files = await packageFiles();
  validatePackage(files);
  const archive = path.join(temp, "kabo.zip");
  await writeFile(archive, deterministicZip(files));
  const root = path.join(temp, "installed");
  execFileSync("unzip", ["-q", archive, "-d", root]);
  return { temp, root, files };
}

test("the twenty-one pinned Skills unpack completely; root directory, host identity and the single MCP are consistent", async t => {
  const { root, files } = await installed(t);
  const result = await checkPackage(root);
  assert.equal(result.version, JSON.parse(await readFile(new URL("../plugin.json", import.meta.url))).version);
  assert.equal(result.submissionReady, false);
  const runtime = JSON.parse(await readFile(path.join(root, "runtime-contract.json")));
  assert.deepEqual(runtime.skills, ids);
  // The tool surface has converged to the tools the plugin actually uses: the required and optional groups exactly cover the tools/list pinned in this repo (the contract is not in the package), no more and no fewer.
  const pinnedNames = JSON.parse(await readFile(new URL("../contracts/directory-mcp/tools-list.json", import.meta.url))).tools.map(tool => tool.name).sort();
  assert.equal(pinnedNames.length, 80);
  assert.deepEqual([...runtime.requiredTools, ...runtime.optionalTools].sort(), pinnedNames);
  assert.ok(runtime.optionalTools.includes("public_video_measure_media_signals"));
  assert.equal(files.some(file => /^(plugin|bin|hooks)\//.test(file.name)), false);
  for (const id of ids) assert.ok((await readFile(path.join(root, "skills", id, "SKILL.md"))).length);
  assert.deepEqual(deterministicZip(files), deterministicZip([...files].reverse()));
  // hooks/ is a component read only when Claude Code installs from the repository: it may sit at the root without
  // an error, but it does not go into the package.
  await mkdir(path.join(root, "hooks"));
  await writeFile(path.join(root, "hooks/hooks.json"), "{}");
  assert.equal((await packageFiles(root)).some(file => file.name.startsWith("hooks/")), false);
  await mkdir(path.join(root, "commands"));
  await writeFile(path.join(root, "commands/start.md"), "start");
  await assert.rejects(checkPackage(root), /filter/);
});

// The two hosts each read their own marketplace manifest, and each lists only this single kabo at the repo root; the Codex marketplace name is referenced by installs on users' machines, so renaming it would leave installed entries unable to find their source.
test("the Claude Code and Codex marketplace manifests both point to the same kabo at the repository root and stay out of the install package", async () => {
  const json = async name => JSON.parse(await readFile(new URL(`../${name}`, import.meta.url)));
  const manifest = await json("plugin.json");
  const claude = await json(".claude-plugin/marketplace.json");
  const codex = await json(".agents/plugins/marketplace.json");
  assert.equal(claude.name, "kabo-mcp-plugin");
  assert.equal(codex.name, "kabo-plugin-openai");
  assert.deepEqual(claude.plugins.map(entry => [entry.name, entry.source]), [[manifest.name, "./"]]);
  assert.deepEqual(codex.plugins.map(entry => [entry.name, entry.source]), [[manifest.name, { source: "local", path: "./" }]]);
  // The version is taken only from plugin.json; writing it again in the entry would drift (Claude Code goes by plugin.json and warns).
  assert.equal("version" in claude.plugins[0], false);
  assert.equal((await packageFiles()).some(file => file.name.endsWith("marketplace.json")), false);
});

// The current brand has only the K Fold icon; the old triangle mark is retired, and both hosts' manifests point to the same file.
test("the plugin icon is only composer-icon.png and both manifests point to it", async () => {
  const json = async name => JSON.parse(await readFile(new URL(`../${name}`, import.meta.url)));
  const ui = (await json("plugin.json")).extensions["com.openai"].interface;
  assert.equal(ui.logo, "./assets/composer-icon.png");
  assert.equal(ui.composerIcon, "./assets/composer-icon.png");
  assert.equal((await json(".claude-plugin/plugin.json")).icon, "./assets/composer-icon.png");
  assert.deepEqual((await packageFiles()).filter(file => file.name.startsWith("assets/")).map(file => file.name), ["assets/composer-icon.png"]);
  const original = await packageFiles();
  const broken = original.map(file => file.name === ".claude-plugin/plugin.json"
    ? { ...file, bytes: Buffer.from(JSON.stringify({ ...JSON.parse(file.bytes), icon: "./assets/logo.png" })) } : file);
  assert.throws(() => validatePackage(broken), /icon/);
});

test("the MIT license ships with the package and both manifests declare it consistently", async () => {
  const original = await packageFiles();
  assert.ok(original.some(file => file.name === "LICENSE"));
  const mismatched = original.map(file => file.name === ".claude-plugin/plugin.json"
    ? { ...file, bytes: Buffer.from(JSON.stringify({ ...JSON.parse(file.bytes), license: "Apache-2.0" })) } : file);
  assert.throws(() => validatePackage(mismatched), /same plugin identity/);
});

test("each Skill carries a license consistent with the plugin manifest, for standalone skills CLI installs", async () => {
  const original = await packageFiles();
  const filename = "skills/develop-content-ideas/SKILL.md";
  for (const to of ["license: Apache-2.0\n", ""]) {
    const changed = original.map(file => file.name === filename ? { ...file, bytes: Buffer.from(String(file.bytes).replace("license: MIT\n", to)) } : file);
    assert.throws(() => validatePackage(changed), /license/);
  }
});

test("pinned Skills can be edited directly in this repository; missing body, unrecorded directories and wrong tool bindings are still rejected", async () => {
  const original = await packageFiles();
  const filename = "skills/review-creator-account/scripts/drive.py";
  const changed = original.map(file => file.name === filename ? { ...file, bytes: Buffer.from("print('changed')") } : file);
  validatePackage(changed);
  validatePackage(original.filter(file => file.name !== "skills/review-creator-account/manifest.json"));
  assert.throws(() => validatePackage(original.filter(file => file.name !== "skills/review-creator-account/SKILL.md")), /entry is missing|body/);
  assert.throws(() => validatePackage([...original, { name: "skills/extra-skill/SKILL.md", bytes: Buffer.from("---\nname: extra-skill\ndescription: x\n---\nbody\n"), mode: 0o100644 }]), /not recorded/);
  // The Skill has dropped the bindings table per the spec; a bindings table in the package that disagrees with the public contract must still be rejected.
  const bindings = "skills/review-creator-account/references/mcp-bindings.json";
  assert.throws(() => validatePackage([...original.filter(file => file.name !== bindings), { name: bindings, bytes: Buffer.from("{}"), mode: 0o100644 }]), /public tool contract/);
  for (const edit of [
    data => { data.execution = "agent-service"; },
    data => { data.requiredTools.push("not_a_pinned_tool"); },
    data => { data.connectorTools["youtube-public/get_channel"] = "youtube_get_video"; },
    data => { data.skills.pop(); },
  ]) {
    const changed = original.map(file => {
      if (file.name !== "runtime-contract.json") return file;
      const value = JSON.parse(file.bytes); edit(value);
      return { ...file, bytes: Buffer.from(JSON.stringify(value)) };
    });
    assert.throws(() => validatePackage(changed));
  }
});

test("drivers in the real ZIP download no program and hand off to public tools explicitly; deep no longer looks up other Skills", async t => {
  const { root, temp } = await installed(t);
  const scripts = path.join(root, "skills/review-creator-account/scripts");
  const run = execFileSync("python3", [path.join(scripts, "static_host.py"), "init", "--workspace", temp], { encoding: "utf8" }).trim();
  const output = execFileSync("python3", [path.join(scripts, "drive.py"), "fetch", "--platform", "youtube", "--handle", "@fixture", "--question-file", "-"], {
    encoding: "utf8", cwd: run, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", KABO_STATIC_RUN_DIR: run }, input: "Review public YouTube account @fixture.",
  });
  const calls = output.split("\n").filter(line => line.startsWith("call: ")).map(line => JSON.parse(line.slice(6)));
  assert.ok(calls.length > 0);
  // Fetching is one backend composite call (KS9) with delivery:"download": the full data is downloaded, split and validated by static_host.py fetch.
  assert.deepEqual(calls.map(call => call.tool), ["collect_account_history"]);
  assert.equal(calls[0].arguments.platform, "youtube");
  assert.equal(calls[0].arguments.delivery, "download");
  // deep used to look for the video skill in the host skill cache (KS4.2 / KS7.1); that script has been removed.
  await assert.rejects(readFile(path.join(root, "skills/review-creator-account-deep/scripts/resolve_video_skill.py")));
});

// The planned frame count is the requested amount: if the provider returns one frame fewer (120 requested, 119 records), state it as is in data_note; reject only if it returns more than planned.
test("ACV data_note accepts fewer frame records than planned and states the requested amount; more than planned is still rejected", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from creator_measurement_basis import canonical_note
def evidence(count):
    return {"content_ref": {"platform": "youtube"}, "transcript": {"status": "not_attempted"},
            "owner_metrics": {"status": "unavailable"},
            "frames": {"status": "available", "origin": "extracted_frames", "sampling_plan": {"frames": 120},
                       "items": [{"frame_id": f"f{i}", "t_seconds": i} for i in range(count)]}}
out = {}
for count in (119, 120, 121):
    try:
        out[count] = canonical_note(evidence(count), {}, {})
    except ValueError as error:
        out[count] = "ERROR " + str(error)
print(json.dumps(out))
`;
  const scripts = path.join(import.meta.dirname, "..", "skills", "analyze-content-video", "scripts");
  const out = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }));
  assert.match(out[119], /^YouTube video; 119 extracted frames of 120 requested;/);
  assert.match(out[120], /^YouTube video; 120 extracted frames;/);
  assert.match(out[121], /^ERROR cannot derive data_note: sampling-plan frame count disagrees/);
});

// Reports are relayed verbatim: a Chinese-view report carries its own Chinese labels (the equivalents of "What to change", "Say this" and "Next step") and its data_note is in Chinese;
// the English view, and any view with no language set, stays word for word as the original English. In the 2026-11-04 regression a Chinese report contained "What to change", "Say this" and an English data_note.
test("the ACV Chinese view renders Chinese labels and the Chinese data_note; the English view is unchanged verbatim", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from creator_measurement_basis import canonical_note, note_matches
from render_video_report import render
from build_creator_result import build
evidence = {"content_ref": {"platform": "youtube"}, "owner_metrics": {"status": "unavailable"},
            "transcript": {"status": "available", "origin": "platform_captions",
                           "cues": [{"start_s": i, "text": "line"} for i in range(108)]},
            "frames": {"status": "available", "origin": "extracted_frames", "sampling_plan": {"frames": 14},
                       "items": [{"frame_id": f"f{i}", "t_seconds": i} for i in range(14)]}}
analysis = {"observations": [{"observation_id": "o1", "evidence_refs": ["f0", "f1"]}]}
def view(language):
    card = {"title": "T", "why_for_you": "a\\nb\\nc", "action": "do it", "evidence_refs": ["observations.o1"]}
    hook = {"purpose": "p", "visual_direction": "close-up", "spoken_line": "line"}
    return {"language": language, "headline": "H", "summary": "S",
            "cards": [dict(card), dict(card), dict(card, hooks=[hook])], "next_actions": ["go"]}
out = {}
for language in ("zh-CN", "en", None):
    v = view(language)
    v["data_note"] = canonical_note(evidence, analysis, v)
    out[str(language)] = {"note": v["data_note"], "report": render({"creator_view": v})}
images = {"media_type": "image_carousel", "returned_count": 5, "expected_count": None, "completeness": "unknown",
          "items": [{"status": "available"}] * 4 + [{"status": "unavailable"}]}
request = {"source": {"acquisition": "public_url"}}
for language in ("zh-CN", "en"):
    built = build({"creator_view": view(language)}, analysis, {"images": images, "owner_metrics": {"status": "unavailable"}}, request)
    out["image " + language] = built["creator_view"]["data_note"]
zh, en = view("zh-CN"), view("en")
english_line = canonical_note(evidence, analysis, en)
out["replay"] = {"zh view, older English line": note_matches(english_line, evidence, analysis, zh),
                 "zh view, Chinese line": note_matches(canonical_note(evidence, analysis, zh), evidence, analysis, zh),
                 "en view, Chinese line": note_matches(canonical_note(evidence, analysis, zh), evidence, analysis, en),
                 "zh view, edited line": note_matches(english_line.replace("14", "15"), evidence, analysis, zh),
                 "zh view, pre-1.0.32 Chinese line": note_matches(canonical_note(evidence, analysis, zh)[:-1] + "；画面查看未核实。", evidence, analysis, zh),
                 "en view, pre-1.0.32 English line": note_matches(english_line[:-1] + "; viewing unverified.", evidence, analysis, en)}
print(json.dumps(out, ensure_ascii=False))
`;
  const scripts = path.join(import.meta.dirname, "..", "skills", "analyze-content-video", "scripts");
  const out = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }));
  // Stop writing "viewing unverified / 画面查看未核实" (Chinese for "visual review unverified"): the frames reached the model and the report cites them one by one, yet creators read it as "the visuals were never viewed".
  const english = "YouTube video; 14 extracted frames; 2 cited frame refs; platform captions (108 cues); owner metrics unavailable.";
  assert.equal(out.en.note, english);
  assert.equal(out.None.note, english);
  assert.equal(out["zh-CN"].note, "YouTube 视频；抽取 14 帧；报告引用 2 帧；平台字幕（108 条）；后台数据不可用。");
  for (const label of ["**怎么复用**：", "**要改什么**：", "- **镜头**：close-up", "- **这样说**：line", "## 下一步"]) {
    assert.ok(out["zh-CN"].report.includes(label), label);
  }
  assert.doesNotMatch(out["zh-CN"].report, /What to change|How to reuse it|Say this|Shot|## Next/);
  for (const report of [out.en.report, out.None.report]) {
    for (const label of ["**How to reuse it**: ", "**What to change**: ", "- **Shot**: close-up", "- **Say this**: line", "## Next"]) {
      assert.ok(report.includes(label), label);
    }
  }
  assert.equal(out.None.report, out.en.report);
  assert.equal(out["image zh-CN"], "图文帖：返回 5 个位置，4 个可用；总数未知；完整度未知；后台数据不可用。");
  assert.equal(out["image en"], "Image post: 4/5 returned positions available; total count unknown; completeness unknown; owner metrics unavailable.");
  // An earlier version wrote an English data_note for the zh view; replay must still accept it, and a line with altered numbers is still blocked.
  // Lines before 1.0.32 end with an extra "viewing unverified / 画面查看未核实" (Chinese for "visual review unverified"); replay of old results accepts that as well.
  assert.deepEqual(out.replay, {"zh view, older English line": true, "zh view, Chinese line": true,
                                "en view, Chinese line": false, "zh view, edited line": false,
                                "zh view, pre-1.0.32 Chinese line": true, "en view, pre-1.0.32 English line": true});
});

// When the evidence text itself carries a magnitude word (transcript "27 B" / "27 billion", caption "27B"), the report may write it as is and must not be judged fabricated;
// when the evidence has only an unrelated bare number 27, "5 billionaires", or an ID fragment ("-5b2e" in a UUID), a report number with a magnitude must still be blocked. Observed as a false positive in the 2026-10-28 Claude Code supplementary P2 test.
test("ACV figure checking accepts numbers whose evidence carries a magnitude word; a bare number still cannot support a magnitude phrasing", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from validate_creator_shape import figure_errors, source_values
evidence = {"transcript": {"cues": [{"start_s": 0.0, "text": "Qwen 3.8 27 B is a 27 billion parameter variant"}]},
            "caption": "Models like Qwen 3.8 27B run on consumer computers", "views": 1600000}
view = {"cards": [{"why_for_you": "The 27B label and the spoken 27 billion both land in the first second; 1.6M views."}]}
print(json.dumps({
    "grounded": figure_errors(view, source_values(evidence)),
    "bare": figure_errors({"cards": [{"why_for_you": "a 27B model"}]}, source_values({"steps": "27 steps"})),
    "other": figure_errors({"cards": [{"why_for_you": "a 28B model"}]}, source_values(evidence)),
    "line_break": figure_errors({"cards": [{"why_for_you": "a 27 billion model"}]}, source_values({"t": "a 27\\nbillion model"})),
    "word_tail": figure_errors({"cards": [{"why_for_you": "5B people"}]}, source_values({"t": "5 billionaires agree"})),
    "leading_dot": figure_errors({"cards": [{"why_for_you": "0.5B users"}]}, source_values({"t": "about .5 billion users"})),
    "metres": figure_errors({"cards": [{"why_for_you": "5M views"}]}, source_values({"t": "he is 5 m tall"})),
    "wan_yi": figure_errors({"cards": [{"why_for_you": "5万"}]}, source_values({"t": "市值5万亿"})),
    "wan_yi_full": figure_errors({"cards": [{"why_for_you": "5万亿"}]}, source_values({"t": "市值5万亿"})),
    "report_dot": figure_errors({"cards": [{"why_for_you": ".5B users"}]}, source_values({"t": "5 billion users"})),
    "dotted_ref": figure_errors({"cards": [{"why_for_you": "see obs.14, v1.5 and version..5"}]}, source_values({"observation_index": 14, "version": 1.5, "patch": 5})),
    "bare_dot": figure_errors({"cards": [{"why_for_you": "a .5 share"}]}, source_values({"t": "a .5 share"})),
    "identifier": figure_errors({"cards": [{"why_for_you": "5B people"}]}, source_values({"id": "7a9b2edb-d958-495d-5b2e-281111e5db11", "sha": "c5b3ff"})),
}))
`;
  const scripts = path.join(import.meta.dirname, "..", "skills", "analyze-content-video", "scripts");
  const out = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }));
  assert.deepEqual(out.grounded, []);
  assert.equal(out.bare.length, 1);
  assert.match(out.bare[0], /states 27B, which appears nowhere/);
  assert.equal(out.other.length, 1);
  assert.match(out.other[0], /states 28B, which appears nowhere/);
  assert.deepEqual(out.line_break, []);
  assert.equal(out.word_tail.length, 1);
  assert.equal(out.identifier.length, 1);
  assert.deepEqual(out.leading_dot, []);
  assert.equal(out.metres.length, 1);
  assert.equal(out.wan_yi.length, 1);
  assert.deepEqual(out.wan_yi_full, []);
  assert.equal(out.report_dot.length, 1);
  assert.deepEqual(out.bare_dot, []);
  assert.deepEqual(out.dotted_ref, []);
});

// A timestamp with fractional seconds (0:07.866, 0:08.366-0:09.366) is a position, not a number; previously only 0:07 was stripped as a time, and the remaining .866 was judged fabricated.
// The Instagram Reel diagnoses in the 2026-11-06 Web pre and plugin retests both stopped at this step.
test("ACV figure checking treats a timestamp with fractional seconds as one time value and does not split out the decimal", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from validate_creator_shape import figure_errors, source_values
values = source_values({"frames": [{"t_seconds": 7.866}]})
print(json.dumps({
    "fraction": figure_errors({"cards": [{"why_for_you": "0:07.866: a back pose; 0:08.366–0:09.366: the approach; 00:00:07,866 in subtitles; 0:07.8667 from a frame"}]}, values),
    "figure_after": figure_errors({"cards": [{"why_for_you": "0:07.8667: 3.5x more likes"}]}, values),
}))
`;
  const scripts = path.join(import.meta.dirname, "..", "skills", "analyze-content-video", "scripts");
  const out = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }));
  assert.deepEqual(out.fraction, []);
  assert.equal(out.figure_after.length, 1);
  assert.match(out.figure_after[0], /states 3\.5/);
});

// View counts rounded to significant digits ("1800万" = 18 million, "1.8千万" = 18 million) or truncated ("2.6M+") are normal writing and must not be judged fabricated;
// small numbers, integers with a single significant digit, and wrongly rounded values must still be blocked. This is what was rejected at final validation in production Web video analysis on 2026-11-06.
test("ACV figure checking accepts large counts rounded or truncated to significant digits; small numbers still follow the original rule", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from validate_creator_shape import figure_errors, source_values
values = source_values({"views": 18067177, "likes": 501301, "other_views": 2689000, "duration_s": 3.9})
def errs(text):
    return len(figure_errors({"summary": text}, values))
print(json.dumps({t: errs(t) for t in [
    "1800 万播放", "1,800 万+", "1.8千万", "约 1807 万", "18M", "2.6M+", "2.7M", "50 万点赞",
    "2000 万", "1900 万", "1.9千万", "18.2M", "3 倍", "100 次"]}, ensure_ascii=False))
print(json.dumps(len(figure_errors({"summary": "跑了 5千米"}, source_values({"distance_km": 5})))))
`;
  const scripts = path.join(import.meta.dirname, "..", "skills", "analyze-content-video", "scripts");
  const [line, unitLine] = execFileSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }).trim().split("\n");
  const out = JSON.parse(line);
  assert.equal(JSON.parse(unitLine), 0, "千米 is a unit, not a scale");
  for (const ok of ["1800 万播放", "1,800 万+", "1.8千万", "约 1807 万", "18M", "2.6M+", "2.7M", "50 万点赞"]) {
    assert.equal(out[ok], 0, ok);
  }
  for (const bad of ["2000 万", "1900 万", "1.9千万", "18.2M", "3 倍", "100 次"]) {
    assert.equal(out[bad], 1, bad);
  }
});
