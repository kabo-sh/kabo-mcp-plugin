// analyze-content-video local sound measurement (measure_audio_local.py): synthetic ffmpeg audio (tone bursts,
// silence, noise; stereo and mono), the numpy-absent path through KABO_ACV_NO_NUMPY, a deadline that stops a pass
// early, merging into the frame command's artifact, and the block's way through the evidence and the brief.
// Cases that need ffmpeg skip without it; the numpy cases skip where python3 has no numpy.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const skill = path.join(root, "skills/analyze-content-video");
const scripts = path.join(skill, "scripts");
const measure = path.join(scripts, "measure_audio_local.py");
const hasFfmpeg = spawnSync("ffmpeg", ["-version"]).status === 0;
const hasNumpy = spawnSync("python3", ["-c", "import numpy"]).status === 0;
const baseEnv = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
delete baseEnv.KABO_STATIC_RUN_DIR;
delete baseEnv.KABO_ACV_NO_NUMPY;

const run = (args, { cwd, env = {} } = {}) => {
  const result = spawnSync("python3", ["-B", ...args], { cwd, encoding: "utf8", env: { ...baseEnv, ...env } });
  return { code: result.status, stdout: result.stdout, stderr: result.stderr };
};
const readJson = async (file) => JSON.parse(await readFile(file, "utf8"));

async function workspace(t) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-audio-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

// Ten seconds: one second of digital silence, then 0.3 s tone bursts every 0.5 s over a quiet noise bed, then
// a loud last three seconds. Stereo by default (the bursts centred, the noise different in each channel).
function synth(dir, { name = "clip.mp4", stereo = true, video = true } = {}) {
  const file = path.join(dir, name);
  const tone = "if(gte(t,1),1,0)*(0.25*sin(2*PI*440*t)*lt(mod(t,0.5),0.3)*if(gte(t,7),3,1))";
  const noise = "if(gte(t,1),1,0)*0.01*(random(0)-0.5)";
  const expr = stereo ? `${tone}+${noise}|${tone}+0.01*if(gte(t,1),1,0)*(random(1)-0.5)` : `${tone}+${noise}`;
  const args = ["-nostdin", "-loglevel", "error", "-y",
    ...(video ? ["-f", "lavfi", "-i", "testsrc=duration=10:size=160x284:rate=10"] : []),
    "-f", "lavfi", "-i", `aevalsrc='${expr}':s=44100:d=10`,
    ...(video ? ["-pix_fmt", "yuv420p", "-shortest"] : []), "-c:a", "aac", file];
  assert.equal(spawnSync("ffmpeg", args).status, 0);
  return file;
}

function sha256(file) {
  const result = spawnSync("shasum", ["-a", "256", file], { encoding: "utf8" });
  return result.stdout.split(/\s+/)[0];
}

async function transcriptFor(dir, file, cues) {
  const artifact = path.join(dir, "analysis", "local-transcript.json");
  spawnSync("mkdir", ["-p", path.dirname(artifact)]);
  await writeFile(artifact, JSON.stringify({
    schema_version: "local-transcript.v1", source_file_name: path.basename(file), source_file_sha256: sha256(file),
    origin: "speech_recognition", status: "available", granularity: "timestamped", complete: true,
    transcribed_until_s: 10, language: "en", cues }));
  return artifact;
}

const frames = (dir, file) => run([path.join(scripts, "extract_local_frames.py"), "--media", file, "--out-dir",
  "analysis/frames", "--artifact", "analysis/local-media.json", "--no-contact-sheets"], { cwd: dir });

test("merges into the frame command's artifact: frames kept, one audio block, a rerun replaces it", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = synth(dir);
  assert.equal(frames(dir, file).code, 0);
  const before = await readJson(path.join(dir, "analysis/local-media.json"));
  await transcriptFor(dir, file, [{ start_s: 1.0, end_s: 9.9, text: "words here", avg_logprob: -0.2 }]);
  for (let pass = 0; pass < 2; pass += 1) {
    const result = run([measure, "--media", file, "--artifact", "analysis/local-media.json"], { cwd: dir });
    assert.equal(result.code, 0, result.stdout + result.stderr);
  }
  const after = await readJson(path.join(dir, "analysis/local-media.json"));
  assert.deepEqual(after.frames.items, before.frames.items);
  const audio = after.media.audio;
  assert.equal(audio.schema_version, "local-audio.v1");
  assert.equal(audio.status, "completed");
  // One set of steps, not one per run.
  assert.equal(after.steps.filter((step) => step.operation === "measure_audio_levels").length, 1);
  assert.equal(new Set(after.limitations).size, after.limitations.length);
  assert.ok(typeof audio.loudness.integrated_lufs === "number");
  assert.ok(typeof audio.loudness.true_peak_dbtp === "number");
  assert.equal(audio.loudness.series_1s.momentary_mean_lufs.length, 10);
  // The silent first second is silence, the transcript's span is speech, all on one timeline.
  assert.equal(audio.segments[0].label, "silence");
  assert.ok(audio.segments[0].end_s >= 0.9 && audio.segments[0].end_s <= 1.1, JSON.stringify(audio.segments[0]));
  assert.ok(audio.segments.some((segment) => segment.label === "speech"));
  const ids = audio.findings.map((item) => item.id);
  assert.ok(ids.includes("dead_air"), ids.join());
  for (const item of audio.findings) {
    assert.ok(["high", "medium"].includes(item.confidence));
    assert.ok("threshold" in item && "measure" in item, JSON.stringify(item));
  }
  // What no measure settles is a question for the creator, never a finding.
  assert.deepEqual(audio.listen_check.slice(0, 4).map((item) => item.id),
    ["genre_mood_fit", "track_identity", "voice_timbre", "sfx_quality"]);
  assert.ok(!ids.some((id) => /genre|mood|track|timbre|sfx/.test(id)));
  assert.equal(audio.thresholds.silence_floor_db, -40);
  assert.equal(audio.speech_source.mean_avg_logprob, -0.2);
  if (hasNumpy) {
    assert.deepEqual(audio.skipped, []);
    assert.ok(audio.stereo && typeof audio.stereo.side_to_mid_db_overall === "number", JSON.stringify(audio.stereo));
    assert.ok(typeof audio.pulse.strength === "number");
    assert.equal(audio.cut_alignment.cut_source, "frames.sampling_plan.shot_detection.cuts_at_s");
  }
});

test("numpy absent: the ffmpeg-only measures stand and the rest are named as skipped", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = synth(dir, { stereo: false });
  const result = run([measure, "--media", file, "--artifact", "analysis/local-media.json"],
    { cwd: dir, env: { KABO_ACV_NO_NUMPY: "1" } });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const artifact = await readJson(path.join(dir, "analysis/local-media.json"));
  // Measured first, with no frame command before it: a frame-less artifact of the same shape.
  assert.equal(artifact.schema_version, "local-media-extraction.v1");
  assert.equal(artifact.frames.status, "not_attempted");
  const audio = artifact.media.audio;
  assert.deepEqual(audio.skipped.map((item) => item.measure),
    ["onsets", "pulse", "cut_alignment", "stereo", "clarity.hf_share_in_speech", "clarity.hum", "voice.speech_modulation"]);
  assert.ok(audio.skipped.every((item) => /numpy/.test(item.reason)));
  assert.ok(audio.notes.some((note) => /numpy is not installed/.test(note)));
  assert.ok(artifact.limitations.some((note) => /numpy is not installed/.test(note)));
  assert.ok(typeof audio.loudness.integrated_lufs === "number");
  assert.ok(!("pulse" in audio));
  // No transcript: sound the map cannot classify, and a note saying why.
  assert.ok(audio.segments.some((segment) => segment.label === "sound_unclassified"));
  assert.ok(audio.notes.some((note) => /No transcript/.test(note)));
  assert.ok(!audio.findings.some((item) => /bed|wordless|no_words/.test(item.id)));
});

test("mono with numpy: no stereo reading, and nothing claimed about width", { skip: !hasFfmpeg || !hasNumpy }, async (t) => {
  const dir = await workspace(t);
  const file = synth(dir, { stereo: false });
  await transcriptFor(dir, file, [{ start_s: 1.0, end_s: 9.9, text: "words here" }]);
  const result = run([measure, "--media", file, "--artifact", "analysis/local-media.json"], { cwd: dir });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const audio = (await readJson(path.join(dir, "analysis/local-media.json"))).media.audio;
  assert.equal(audio.stereo, null);
  assert.ok(!audio.findings.some((item) => item.id === "wide_under_voice"));
});

test("cuts on clicks: the alignment beats its shifted-cut chance and is reported", { skip: !hasFfmpeg || !hasNumpy }, async (t) => {
  const dir = await workspace(t);
  const file = path.join(dir, "cuts.mp4");
  // Nine one-second colour shots (eight cuts), a click at every cut and nothing else but faint noise.
  const colours = ["red", "blue", "green", "yellow", "white", "purple", "orange", "cyan", "gray"];
  const inputs = colours.flatMap((colour) => ["-f", "lavfi", "-i", `color=${colour}:size=160x284:rate=30:duration=1`]);
  const chain = `${colours.map((_, index) => `[${index}:v]`).join("")}concat=n=${colours.length}:v=1:a=0[v]`;
  const click = "0.002*(random(0)-0.5)+0.8*lt(mod(t,1),0.01)*gte(t,0.5)*sin(2*PI*2000*t)";
  assert.equal(spawnSync("ffmpeg", ["-nostdin", "-loglevel", "error", "-y", ...inputs, "-f", "lavfi", "-i",
    `aevalsrc='${click}':s=44100:d=9`, "-filter_complex", chain, "-map", "[v]", "-map", `${colours.length}:a`,
    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", file]).status, 0);
  assert.equal(frames(dir, file).code, 0);
  const result = run([measure, "--media", file, "--artifact", "analysis/local-media.json"], { cwd: dir });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const audio = (await readJson(path.join(dir, "analysis/local-media.json"))).media.audio;
  const alignment = audio.cut_alignment;
  assert.equal(alignment.status, "measured", JSON.stringify([alignment, audio.segments]));
  assert.ok(alignment.share_on_onset >= 0.75 && alignment.chance_share < 0.4, JSON.stringify(alignment));
  assert.ok(audio.findings.some((item) => item.id === "cuts_on_sound"), JSON.stringify([alignment, audio.findings]));
});

test("the cut list: the full-rate list first, then the 0.1 s measurement grid, then shot-start frames", () => {
  const code = String.raw`
import json, sys
sys.path.insert(0, sys.argv[1])
import measure_audio_local as m
full = {"frames": {"sampling_plan": {"shot_detection": {"cuts": 2, "cuts_at_s": [1.5, 3.25]}}},
        "media": {"signals": {"shots": {"cuts_at_s": [1.5, 3.3]}}}}
grid = {"frames": {"sampling_plan": {"shot_detection": {"cuts": 2}}}, "media": {"signals": {"shots": {"cuts_at_s": [1.5, 3.3]}}}}
starts = {"frames": {"items": [{"t_seconds": 1.55, "source": "shot_start"}, {"t_seconds": 2.0, "source": "body"}]}, "media": {}}
print(json.dumps([m.cut_list(full), m.cut_list(grid), m.cut_list(starts), m.cut_list({"frames": {}, "media": {}})]))
`;
  const result = run(["-c", code, scripts]);
  assert.equal(result.code, 0, result.stderr);
  const [full, grid, starts, none] = JSON.parse(result.stdout);
  assert.deepEqual(full, [[1.5, 3.25], "frames.sampling_plan.shot_detection.cuts_at_s", false]);
  assert.deepEqual(grid[0], [1.5, 3.3]);
  assert.equal(grid[2], true, "cuts on the 0.1 s grid widen the tolerance");
  assert.deepEqual(starts[0].map((value) => Math.round(value * 1000) / 1000), [1.5]);
  assert.deepEqual(none, [null, null, false]);
});

test("deadline: a pass stopped early keeps what it read and names the second it reached", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = synth(dir);
  // The real pass, cut back to what it had printed by 4 s, reported as stopped by the time budget.
  const code = String.raw`
import sys
sys.path.insert(0, sys.argv[1])
import measure_audio_local as m
real = m.local_frames.run_pass
def stopped(args, deadline):
    status, log, reached, note = real(args, deadline)
    kept = []
    for line in log.splitlines(keepends=True):
        if " t: " in line and float(line.split(" t: ")[1].split()[0]) > 4.0:
            break
        kept.append(line)
    return "completed_partial", "".join(kept), 4.0, "stopped early: this command's time budget was used up"
m.local_frames.run_pass = stopped
m.decode_samples = lambda media, channels, deadline: (b"", "failed", "stopped before reading any of the file: this command's time budget was used up")
raise SystemExit(m.main(["--media", sys.argv[2], "--artifact", sys.argv[3]]))
`;
  const result = run(["-c", code, scripts, file, path.join(dir, "analysis/local-media.json")], { cwd: dir });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const artifact = await readJson(path.join(dir, "analysis/local-media.json"));
  const audio = artifact.media.audio;
  assert.equal(audio.status, "completed_partial");
  assert.ok(audio.measured_until_s.levels >= 3.9 && audio.measured_until_s.levels < 5, JSON.stringify(audio.measured_until_s));
  assert.ok(audio.notes.some((note) => /unmeasured, not quiet/.test(note)));
  // No finding reaches past the second the pass read, and a level against the feed target needs the whole file.
  assert.ok(audio.findings.every((item) => (item.at_s ?? 0) <= 4.1), JSON.stringify(audio.findings));
  assert.ok(!audio.findings.some((item) => /too_quiet|too_loud/.test(item.id)));
  assert.ok(audio.segments.at(-1).end_s <= 4.1);
});

test("refusals: no such file, another file's artifact, and a file with no sound", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const missing = run([measure, "--media", path.join(dir, "nope.mp4"), "--artifact", "analysis/local-media.json"], { cwd: dir });
  assert.equal(missing.code, 2);
  const first = synth(dir, { name: "one.mp4" });
  const second = synth(dir, { name: "two.mp4", stereo: false });
  assert.equal(run([measure, "--media", first, "--artifact", "analysis/local-media.json"], { cwd: dir, env: { KABO_ACV_NO_NUMPY: "1" } }).code, 0);
  const other = run([measure, "--media", second, "--artifact", "analysis/local-media.json"], { cwd: dir });
  assert.equal(other.code, 2);
  assert.match(other.stderr, /different file/);
  const silent = path.join(dir, "silent.mp4");
  assert.equal(spawnSync("ffmpeg", ["-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
    "testsrc=duration=4:size=160x284:rate=10", "-pix_fmt", "yuv420p", silent]).status, 0);
  const none = run([measure, "--media", silent, "--artifact", "analysis/silent.json"], { cwd: dir });
  assert.equal(none.code, 0, none.stderr);
  assert.equal((await readJson(path.join(dir, "analysis/silent.json"))).media.audio.status, "no_audio_track");
});

test("evidence and brief: media.audio validates, drops the per-second series, and the brief lists findings apart from listen-checks", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const runDir = run([path.join(scripts, "static_host.py"), "init", "--workspace", dir]).stdout.trim();
  const file = synth(dir);
  assert.equal(frames(runDir, file).code, 0);
  await transcriptFor(runDir, file, [{ start_s: 1.0, end_s: 9.9, text: "words here" }]);
  assert.equal(run([measure, "--media", file, "--artifact", "analysis/local-media.json"], { cwd: runDir }).code, 0);
  await writeFile(path.join(runDir, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-audio",
    source: { acquisition: "local_file", subject_state: "own_unpublished", platform: "tiktok", url: null, content_id: null,
      declared_format: "video", owner_data: null, file_ref: file },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 0, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] } }));
  const built = run([path.join(scripts, "build_content_evidence.py"), "--request", "analysis/video-analysis-request.json",
    "--local-media", "analysis/local-media.json", "--local-transcript", "analysis/local-transcript.json",
    "--output", "analysis/content_evidence.json"], { cwd: runDir });
  assert.equal(built.code, 0, built.stdout + built.stderr);
  const evidence = await readJson(path.join(runDir, "analysis/content_evidence.json"));
  const schema = JSON.parse(await readFile(path.join(skill, "references/content-evidence.schema.json"), "utf8"));
  const ajv = new Ajv2020({ allErrors: true, strict: false, logger: false });
  ajv.addFormat("date-time", true);
  const validate = ajv.compile(schema);
  assert.ok(validate(evidence), JSON.stringify(validate.errors, null, 1));
  const audio = evidence.media.audio;
  assert.equal(audio.schema_version, "local-audio.v1");
  assert.ok(!("series_1s" in audio.loudness));
  assert.ok(!("notes" in audio));
  assert.ok(audio.findings.length > 0);
  const brief = run(["-c", String.raw`
import json, sys
sys.path.insert(0, sys.argv[1])
import prepare_analysis
print("\n".join(prepare_analysis.sound_lines(json.load(open(sys.argv[2])))))
`, scripts, path.join(runDir, "analysis/content_evidence.json")]);
  assert.equal(brief.code, 0, brief.stderr);
  assert.match(brief.stdout, /Local sound measurement \(`media\.audio`, completed\)/);
  assert.match(brief.stdout, /`media\.audio\.findings\[0\]`/);
  assert.match(brief.stdout, /Listen-check, for the creator to hear; never a finding/);
  assert.match(brief.stdout, /`media\.audio`/);
});
