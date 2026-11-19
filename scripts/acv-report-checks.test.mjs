// analyze-content-video: the report-side fixes from the observation bake-off, checked on the scripts' own functions.
// Each probe runs the Skill's Python with -I -B and prints JSON; nothing touches the network.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "analyze-content-video", "scripts");
const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
delete env.KABO_STATIC_RUN_DIR;

function probe(code) {
  const result = spawnSync("python3", ["-I", "-B", "-c", `import json, sys\nsys.path.insert(0, sys.argv[1])\n${code}`, scripts],
    { encoding: "utf8", env });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("renderer: each card's action label is right and distinct for whose video it is, and a label the text already starts with is not repeated", () => {
  const out = probe(`
from render_video_report import render
def report(subject, actions, language="en"):
    cards = [{"title": f"T{i}", "why_for_you": "a\\nb\\nc", "action": action} for i, action in enumerate(actions)]
    return render({"creator_view": {"language": language, "headline": "H", "cards": cards}, "details": {"subject_state": subject}})
print(json.dumps({
  "own": report("own_published", ["one", "two", "three"]),
  "borrowed": report("third_party", ["one", "How to avoid it: two", "**What to do in yours**: three"]),
  "zh": report("unknown", ["one", "two", "three"], "zh-CN"),
}))`);
  const labels = (text) => [...text.matchAll(/\*\*([^*]+)\*\*(?:: |：)/g)].map((match) => match[1]);
  assert.deepEqual(labels(out.own), ["How to reuse it", "How to fix it", "What to change"]);
  assert.deepEqual(labels(out.borrowed), ["How to reuse it", "How to avoid it", "What to do in yours"]);
  assert.match(out.borrowed, /\*\*How to avoid it\*\*: two\n/);
  assert.match(out.borrowed, /\*\*What to do in yours\*\*: three\n/);
  assert.doesNotMatch(out.borrowed, /How to avoid it\*\*: How to avoid it/);
  assert.equal(new Set(labels(out.zh)).size, 3);
});

test("renderer: durations stay durations, positions become timecodes rounded to the tenth", () => {
  const out = probe(`
from render_video_report import prose_timecodes, timecode
lines = ["cuts every 0.03-1.4s through the middle", "the last 3.07s holds the logo", "a 2.5s pause before the reveal",
         "at 3.07s the logo appears", "at about 9.75s the cut lands", "5.9 seconds of silence at 98.2-104.1s"]
print(json.dumps({"lines": [prose_timecodes(line, set()) for line in lines], "clock": [timecode(9.75), timecode(9.74), timecode(59.97)]}))`);
  assert.deepEqual(out.lines, ["cuts every 0.03–1.4 s through the middle", "the last 3.07 s holds the logo", "a 2.5 s pause before the reveal",
    "at [0:03.1] the logo appears", "at about [0:09.8] the cut lands", "5.9 seconds of silence at [1:38.2–1:44.1]"]);
  assert.deepEqual(out.clock, ["0:09.8", "0:09.7", "1:00"]);
});

test("view check: a figure read off a frame as on-screen text (600 m²) and a dot-thousands count (3.430) are grounded; others are not", () => {
  const out = probe(`
from validate_creator_shape import figure_errors, source_values
evidence = {"observations": [{"statement": "The first frame reads 'Derri\\u00e8re cette fa\\u00e7ade se cachent 600 m\\u00b2 de vitraux'"}], "views": 3430}
ok = figure_errors({"summary": "The opening promises 600 m\\u00b2 of glass and has 3.430 views (3,430)."}, source_values(evidence))
bad = figure_errors({"summary": "3.431 views and 600m plays"}, source_values(evidence))
print(json.dumps({"ok": ok, "bad": len(bad)}))`);
  assert.deepEqual(out.ok, []);
  assert.equal(out.bad, 2);
});

test("unknown or third-party ownership: the composer fills account_baseline unavailable, and the validator says how to fix it", () => {
  const out = probe(`
from compose_video_analysis import completeness
evidence = {"media": {"status": "available"}, "transcript": {"status": "available"}, "frames": {"status": "available"}}
print(json.dumps({s: completeness(evidence, {}, s).get("account_baseline") for s in ("unknown", "third_party", "own_published")}))`);
  assert.deepEqual(out, { unknown: "unavailable", third_party: "unavailable", own_published: null });
  for (const file of ["validate_video_analysis.py", "validate_creator_shape.py"]) {
    const text = spawnSync("grep", ["-c", "unknown ownership has no account baseline", path.join(scripts, file)], { encoding: "utf8" }).stdout.trim();
    assert.equal(text, "1", file);
  }
});

test("a local file is never unknown ownership: the error names the states to choose", () => {
  const out = probe(`
from prepare_link_request import public_only_request_errors
request = {"source": {"acquisition": "local_file", "subject_state": "unknown", "owner_data": None}, "acquire": {"owner_metrics": "skip"}}
print(json.dumps(public_only_request_errors(request)))`);
  assert.match(out[0], /a file on this machine is never `unknown`/);
  assert.match(out[0], /`third_party`/);
  assert.match(out[0], /`own_unpublished`/);
});

test("transcript checks: sound markers, invented lines, language and disagreement", () => {
  const out = probe(`
import transcript_checks as t
print(json.dumps({
  "marker": [t.marker_only("[Music]"), t.marker_only("\\u266a\\u266a"), t.marker_only("[Music] hello")],
  "generic": [t.generic_line("Thanks for watching!"), t.generic_line("Please subscribe to the channel."),
              t.generic_line("Thank you."), t.generic_line("Thank you.", short_transcript=True), t.generic_line("Thanks for the pan tip")],
  "language": [t.language_of("Dit is het verhaal van een man die niet wist wat hij moest doen, maar ook dat was voor niets"),
               t.language_of("This is the story of a man and what you do with your life, the one that you have"),
               t.language_of("short line")],
  "same": [t.same_language("en-US", "en"), t.same_language("nl", "en"), t.same_language("ja", "zh"), t.same_language(None, "en")],
}))`);
  assert.deepEqual(out.marker, [true, true, false]);
  assert.deepEqual(out.generic, [true, true, false, true, false]);
  assert.deepEqual(out.language, ["nl", "en", null]);
  assert.deepEqual(out.same, [true, false, true, null]);
});

test("promise payoff: a named payoff cue is written to analysis/promise_payoff.json, where the view check reads it", async (t) => {
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-payoff-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  await mkdir(path.join(run, "analysis"));
  const evidence = { media: { duration_s: 40 }, frames: { sampling_plan: { hook_window_s: 3 } },
    transcript: { status: "available", origin: "speech_recognition", cues: [
      { start_s: 0, text: "[Music]" }, { start_s: 0.5, text: "Here is why your pan keeps burning." }, { start_s: 12.25, text: "Lower the heat." }] } };
  await writeFile(path.join(run, "analysis/content_evidence.json"), JSON.stringify(evidence));
  const done = spawnSync("python3", ["-B", path.join(scripts, "compute_promise_payoff.py"), "analysis/content_evidence.json", "--payoff-cue", "2"],
    { cwd: run, encoding: "utf8", env });
  assert.equal(done.status, 0, done.stderr);
  const written = JSON.parse(await readFile(path.join(run, "analysis/promise_payoff.json"), "utf8"));
  // The marker-only cue at 0s never anchors the promise.
  assert.equal(written.promise.cue_index, 1);
  assert.equal(written.gap_s, 11.75);
  const grounded = probe(`
from validate_creator_shape import figure_errors, source_values
payoff = json.load(open(${JSON.stringify(path.join(run, "analysis/promise_payoff.json"))}))
print(json.dumps(figure_errors({"summary": "The payoff comes 11.75 seconds after the promise."}, source_values({}, payoff))))`);
  assert.deepEqual(grounded, []);
  assert.match(await readFile(path.join(scripts, "validate_creator_shape.py"), "utf8"), /promise_payoff\.json/);
});

test("brief: no audio track is said plainly; a local file asks for the link before a performance answer", () => {
  const out = probe(`
from prepare_analysis import sound_lines, evidence_index
silent = sound_lines({"media": {"has_audio": False}, "transcript": {"status": "no_audio_track"}})
local = evidence_index({"content_ref": {"platform": "tiktok"}, "media": {}, "frames": {}, "transcript": {}}, "local_frames",
                       {"skipped": []}, {"source": {"acquisition": "local_file"}})
print(json.dumps({"silent": silent, "local": local}))`);
  assert.ok(out.silent.some((line) => /has no audio track: there is no music, voice or mix to analyse/.test(line)), out.silent);
  assert.ok(!out.silent.some((line) => /neither measured nor heard/.test(line)));
  assert.ok(out.local.some((line) => /ask once for the published link/.test(line)));
});

test("local extraction: a thinned body sampled at least once a second is not degraded; local steps open the observe stage", async (t) => {
  const out = probe(`
from extract_local_frames import plan_frames
dense = plan_frames(70.0, 3.0, 0.5, 2, 100)
sparse = plan_frames(170.0, 3.0, 1.0, 2, 100)
print(json.dumps({"dense": [dense["body_degraded"], dense["body_interval_s"]], "sparse": [sparse["body_degraded"], sparse["body_interval_s"]]}))`);
  assert.equal(out.dense[0], false);
  assert.ok(out.dense[1] <= 1, out.dense);
  assert.equal(out.sparse[0], true);
  const run = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-timing-"));
  t.after(() => rm(run, { recursive: true, force: true }));
  await mkdir(path.join(run, "analysis"));
  await writeFile(path.join(run, ".static-run.json"), "{}");
  probe(`
import acv_timing
acv_timing.open_for_artifact(${JSON.stringify(path.join(run, "analysis/local-media.json"))})
acv_timing.open_for_artifact(${JSON.stringify(path.join(os.tmpdir(), "elsewhere", "analysis", "x.json"))})
print("{}")`);
  assert.ok(existsSync(path.join(run, "analysis/.timing-open.json")));
  assert.ok(JSON.parse(await readFile(path.join(run, "analysis/.timing-open.json"), "utf8")).observe);
  for (const file of ["extract_local_frames.py", "transcribe_local.py"])
    assert.match(await readFile(path.join(scripts, file), "utf8"), /acv_timing\.open_for_artifact\(args\.artifact\)/, file);
});

// A sibling import run without -B writes __pycache__/*.pyc into the Skill; the .pyc embeds the absolute source
// path, so a concurrent working-tree package check fails on it. Every script that imports a sibling turns
// bytecode off first.
test("scripts that import a sibling module turn bytecode writing off before the import", async () => {
  const { readdir } = await import("node:fs/promises");
  for (const name of (await readdir(scripts)).filter((file) => file.endsWith(".py"))) {
    const text = await readFile(path.join(scripts, name), "utf8");
    const first = text.search(/sys\.path\.insert\(0|spec_from_file_location\(/);
    if (first < 0) continue;
    const off = text.indexOf("sys.dont_write_bytecode = True");
    assert.ok(off >= 0 && off < first, name);
  }
});
