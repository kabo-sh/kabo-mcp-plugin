// analyze-content-video observation sources: server frames, whole-video viewing and local frames each become
// ContentEvidence through the one evidence builder, and the one brief script turns any of them into the same
// analysis instructions. Nothing touches the network: the tool results are written in the shapes the backend
// returns (the whole-video result is a synthetic, schema-valid fixture built from the MCP output schema).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import Ajv from "ajv";

const root = fileURLToPath(new URL("..", import.meta.url));
const skill = path.join(root, "skills", "analyze-content-video");
const scripts = path.join(skill, "scripts");
const viewerFixture = JSON.parse(readFileSync(path.join(root, "scripts/fixtures/acv-whole-video/synthetic-get-analysis-run.json"), "utf8"));
const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
delete env.KABO_STATIC_RUN_DIR;

const python = (script, args, cwd) => {
  const result = spawnSync("python3", ["-B", path.join(scripts, script), ...args], { cwd, encoding: "utf8", env });
  return { code: result.status, out: result.stdout + result.stderr };
};
const shell = (command) => {
  const result = spawnSync("bash", ["-c", command], { encoding: "utf8", env });
  return { code: result.status, out: result.stdout + result.stderr };
};
const callLines = (out) => out.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)));
const slotFiles = (out) => out.split("\n").filter((line) => /^\s+result \d+\s+\(fallback file/.test(line)).map((line) => line.split(": ").pop().slice(0, -1));
const resumeOf = (out) => { const line = out.split("\n").find((l) => l.startsWith("Then run this one command")); return line.slice(line.indexOf("cd '")).replace(/ --id=<id>$/, ""); };
const flagsOf = (out) => out.split("\n").find((line) => line.startsWith("Pass these to build_content_evidence.py")).split(": ")[1];
const SENTINEL = /SENTINEL-/;

const TIKTOK = "https://www.tiktok.com/@cook/video/7300000000000000001";
const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const TOOLS = { collect_public_metadata: "public_video_collect_public_metadata", fetch_transcript: "public_video_fetch_transcript",
  extract_keyframes: "public_video_extract_keyframes", measure_media_signals: "public_video_measure_media_signals" };

// One fixed job id per operation, so a second media call in the same run (after a fallback) never reuses one.
const JOB_NUMBER = { collect_public_metadata: 1, fetch_transcript: 2, extract_keyframes: 3, measure_media_signals: 4 };
function mediaEnvelope(operation, jobId, { failed = false, duration = 30, emptyTranscript = false } = {}) {
  const base = {
    schema_version: "1.0", connector_id: "public-video-media", operation, provider: "fixture", status: failed ? "failed" : "completed",
    summary: "ok", limitations: failed ? ["the platform refused the download"] : [], credential_values_recorded: false, job_id: jobId,
    evidence_ref: `ev-${jobId}`, raw_sha256: jobId.replace(/-/g, "").padEnd(64, "a"), request_id: `req-${jobId}`,
    retrieved_at: "2026-11-16T00:00:00Z", observation_refs: [],
  };
  if (failed) return base;
  if (operation === "collect_public_metadata")
    return { ...base, data: { artifacts: [], video: { id: "7300000000000000001", title: "Why your pan burns", description: "Fix it #cooking",
      view_count: 1200, like_count: 90, comment_count: 4, duration_seconds: duration, upload_date: "20261101", thumbnail: null, tags: ["cooking"],
      webpage_url: TIKTOK } } };
  if (operation === "fetch_transcript" && emptyTranscript)
    return { ...base, data: { cues: [], origin: "speech_recognition", cue_count: 0, artifacts: [] } };
  if (operation === "fetch_transcript")
    return { ...base, data: { cues: [{ text: "I ruined it again.", start_ms: 0, end_ms: 2400 }, { text: "Here is why your pan keeps burning.", start_ms: 2400, end_ms: 9000 }],
      origin: "speech_recognition", cue_count: 2, artifacts: [] } };
  if (operation === "measure_media_signals")
    return { ...base, data: { shots: { count: 2, cuts_at_s: [12.5], shots: [{ start_s: 0, end_s: 12.5 }, { start_s: 12.5, end_s: 30 }] }, artifacts: [] } };
  const frames = [0, 0.5, 1, 12, 25].map((t, i) => ({ bytes: 100, sha256: "c".repeat(64), frame_id: `frame-${String(i + 1).padStart(4, "0")}`, t_seconds: t,
    object_ref: `creator-media/${jobId}/epoch-1/frame-${String(i + 1).padStart(4, "0")}.jpg` }));
  return { ...base, data: { frames, artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
    selection: "duration_scaled_v1", duration_s: 30, frame_count: frames.length } };
}
function composite(args, { failed = false, duration, emptyTranscript } = {}) {
  const jobs = [], list = [];
  args.requests.forEach((request) => {
    const group = `${request.content_id}/${request.operation}`;
    const jobId = uuid(JOB_NUMBER[request.operation]);
    const lost = failed && request.operation !== "collect_public_metadata";
    jobs.push({ group, content_id: request.content_id, operation: request.operation, attempt: 1, job_id: jobId, status: lost ? "failed" : "completed" });
    list.push({ tool: TOOLS[request.operation], parameters: request.parameters, group, attempts: 1,
      result: mediaEnvelope(request.operation, jobId, { failed: lost, duration, emptyTranscript }) });
  });
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_video_media", status: "completed", calls: list,
    summary: { requests: jobs.length, pending: 0, jobs }, coverage: { deadline_reached: false, unfinished: [], provider_calls: 0, pending: 0 }, limitations: [] };
}
const mcp = (value) => JSON.stringify({ content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value });
const queued = { ...viewerFixture, status: "queued", progress: 5, result: null, transcript: null, completedAt: null };

async function newRun(t) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-observe-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const init = python("static_host.py", ["init", "--workspace", workspace]);
  assert.equal(init.code, 0, init.out);
  return init.out.trim();
}
async function writeRequest(run, { acquisition = "public_url", url = TIKTOK } = {}) {
  await writeFile(path.join(run, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-observe",
    source: { acquisition, subject_state: acquisition === "local_file" ? "own_unpublished" : "unknown", platform: "tiktok", url: acquisition === "local_file" ? null : url,
      content_id: "7300000000000000001", declared_format: "video", owner_data: null,
      ...(acquisition === "local_file" ? { file_ref: path.join(run, "analysis", "clip.mp4") } : {}) },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 10, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] },
  }));
}
function build(run, flags) {
  return shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
    + `${flags} --snapshot-root snapshot --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json`);
}
const evidenceSchema = JSON.parse(readFileSync(path.join(skill, "references/content-evidence.schema.json"), "utf8"));
function assertValidEvidence(evidence) {
  const ajv = new Ajv2020({ allErrors: true, strict: false, logger: false });
  ajv.addFormat("date-time", true);
  const validate = ajv.compile(evidenceSchema);
  assert.ok(validate(evidence), JSON.stringify(validate.errors, null, 1));
}
const readJson = async (file) => JSON.parse(await readFile(file, "utf8"));

// Drive one public-link observation to the end with the given tool answers; returns the run, its final output and
// every call handed over, in order. `mediaFailed` fails the media call's observing jobs (true, or a function of the
// media call's number in this run); `afterRound` runs after each round's results are saved, before the resume.
async function observe(t, source, { viewerSteps = [viewerFixture], mediaFailed = false, mode = "diagnosis", duration,
  emptyTranscript, afterRound } = {}) {
  const run = await newRun(t);
  let out = python("observe_video.py", ["--url", TIKTOK, "--mode", mode, ...(source ? ["--observe-source", source] : [])], run).out;
  const steps = [...viewerSteps];
  const handed = [];
  let mediaCalls = 0;
  for (let round = 0; round < 8 && !/"status": "observed"/.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    assert.ok(calls.length, out);
    for (const [index, call] of calls.entries()) {
      handed.push(call);
      if (call.tool === "collect_video_media") {
        const failed = typeof mediaFailed === "function" ? mediaFailed(mediaCalls) : mediaFailed;
        mediaCalls += 1;
        await writeFile(files[index], mcp(composite(call.arguments, { failed, duration, emptyTranscript })));
      } else await writeFile(files[index], typeof steps[0] === "string" ? steps.shift() : mcp(steps.shift()));
    }
    if (afterRound) await afterRound(run, round);
    const resumed = shell(resumeOf(out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
    assert.equal(resumed.code, 0, resumed.out);
    out = resumed.out;
  }
  assert.match(out, /"status": "observed"/);
  return { run, out, handed };
}
const operationsOf = (call) => call.arguments.requests.map((request) => request.operation);

test("observation-order.json is the agreed table, and the next source follows it", async () => {
  assert.deepEqual(await readJson(path.join(skill, "references/observation-order.json")), {
    schema_version: "observation-order/v2", default: ["server_frames"], fallback: { server_frames: ["whole_video"], whole_video: ["server_frames"] },
    add_when_cards: { sound: ["whole_video"] }, whole_video_max_ms: 600000, whole_video_platforms: ["youtube", "instagram", "tiktok"] });
  const pick = (...args) => { const r = python("observation_order.py", args, root); return { code: r.code, ...JSON.parse(r.out) }; };
  assert.equal(pick("--platform", "tiktok").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--failed", "server_frames").source, "whole_video");
  assert.equal(pick("--platform", "douyin", "--failed", "server_frames").source, null);
  assert.equal(pick("--platform", "youtube", "--duration-s", "900", "--failed", "server_frames").source, null);
  assert.equal(pick("--platform", "tiktok", "--failed", "server_frames", "--failure-code", "source_unavailable").source, null);
  assert.equal(pick("--platform", "tiktok", "--failed", "whole_video").source, "server_frames");
  assert.equal(pick("--platform", "douyin", "--observe-source", "combined").source, "combined");
  assert.equal(pick("--local-file").source, "local_frames");
  // A transcript export never starts a paid viewing, not even as a fallback or when forced.
  assert.equal(pick("--platform", "tiktok", "--failed", "server_frames", "--mode", "transcript_export").source, null);
  assert.equal(pick("--platform", "tiktok", "--observe-source", "whole_video", "--mode", "transcript_export").source, "server_frames");
  // A craft teardown needs frames: a viewing alone becomes combined; after server frames failed, nothing is left.
  assert.equal(pick("--platform", "tiktok", "--observe-source", "whole_video", "--mode", "craft_teardown").source, "combined");
  assert.equal(pick("--platform", "tiktok", "--failed", "server_frames", "--mode", "craft_teardown").source, null);
  assert.equal(pick("--observe-source", "everything").code, 2);
  // The sound card adds the whole-video viewing (it hears the audio) wherever a viewing is possible, and only there.
  const sound = pick("--platform", "tiktok", "--cards", "diagnosis-default,sound");
  assert.equal(sound.source, "combined");
  assert.match(sound.reason, /the sound card adds whole_video/);
  assert.equal(pick("--platform", "tiktok", "--cards", "diagnosis-default,opening").source, "server_frames");
  const douyin = pick("--platform", "douyin", "--cards", "sound");
  assert.equal(douyin.source, "server_frames");
  assert.match(douyin.reason, /the sound card would add whole_video, but whole-video viewing does not cover douyin/);
  assert.equal(pick("--platform", "youtube", "--duration-s", "900", "--cards", "sound").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--cards", "sound", "--mode", "transcript_export").source, "server_frames");
  // A viewing that already failed is never added back, and a forced source stays forced.
  assert.equal(pick("--platform", "tiktok", "--failed", "whole_video", "--cards", "sound").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--observe-source", "server_frames", "--cards", "sound").source, "server_frames");
});

test("server_frames: one media call, persisted envelopes, valid evidence with no viewer block, timing recorded", async (t) => {
  const { run, out } = await observe(t, null);
  assert.match(out, /"source": "server_frames"/);
  assert.match(out, /^read: /m);
  await writeRequest(run);
  const built = build(run, flagsOf(out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.frames.status, "available");
  assert.equal("viewer_observations" in evidence, false);
  const timing = await readJson(path.join(run, "analysis/timing.json"));
  assert.equal(timing.schema_version, "acv-timing/v1");
  assert.equal(timing.observation_source, "server_frames");
  assert.deepEqual(timing.stages.map((stage) => stage.stage), ["observe"]);
});

test("whole_video: start, poll after a script-side wait, keep notes and transcript, drop every score and piece of advice", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  assert.equal(first.code, 0, first.out);
  const calls = callLines(first.out);
  // The viewer call goes first; the metadata-only media call rides along for TikTok's post metadata.
  assert.deepEqual(calls.map((call) => call.tool), ["analyze_content_video", "collect_video_media"]);
  assert.equal(calls[0].arguments.source_url, TIKTOK);
  assert.match(calls[0].arguments.idempotency_key, /^acv-wv:[0-9a-f]{32}:a1$/);
  // The tool waits for a final status itself and offers the finished result as a download.
  assert.equal(calls[0].arguments.wait_s, undefined);
  assert.equal(calls[0].arguments.delivery, "download");
  assert.deepEqual(calls[1].arguments.requests.map((r) => r.operation), ["collect_public_metadata"]);
  const files = slotFiles(first.out);
  await writeFile(files[0], mcp(queued));
  await writeFile(files[1], mcp(composite(calls[1].arguments)));
  const second = shell(resumeOf(first.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.equal(second.code, 0, second.out);
  const poll = callLines(second.out);
  assert.deepEqual(poll, [{ tool: "get_analysis_run", arguments: { analysis_id: viewerFixture.id, wait_s: 45, delivery: "download" } }]);
  // The same start again (a lost answer) would replay the same analysis: the key never changes within a run.
  await writeFile(slotFiles(second.out)[0], JSON.stringify(viewerFixture));
  const third = shell(resumeOf(second.out));
  assert.equal(third.code, 0, third.out);
  assert.match(third.out, /"status": "observed"/);
  assert.match(flagsOf(third.out), /--viewer snapshot\/whole-video\.json/);
  assert.doesNotMatch(await readFile(path.join(run, "snapshot/whole-video.json"), "utf8"), SENTINEL);

  await writeRequest(run);
  const built = build(run, flagsOf(third.out));
  assert.equal(built.code, 0, built.out);
  const text = await readFile(path.join(run, "analysis/content_evidence.json"), "utf8");
  assert.doesNotMatch(text, SENTINEL);
  const evidence = JSON.parse(text);
  assertValidEvidence(evidence);
  const viewer = evidence.viewer_observations;
  assert.equal(viewer.status, "available");
  assert.equal(viewer.analysis_id, viewerFixture.id);
  assert.deepEqual(viewer.items.map((item) => item.id), ["V01", "V02", "V03", "V04"]);
  assert.deepEqual(viewer.items[0], { id: "V01", start_ms: 0, end_ms: 2500, aspect: "hook", note: viewerFixture.result.dimensions[0].evidence[0].note });
  for (const field of ["overallScore", "dimensions[].score", "dimensions[].summary", "strengths", "improvements", "hooks", "titleIdeas", "viralPotential", "summary", "verdict"])
    assert.ok(viewer.discarded_fields.includes(field), field);
  // No fetched transcript: the viewer's fills the block, machine-heard, seconds not milliseconds.
  assert.equal(evidence.transcript.status, "available");
  assert.equal(evidence.transcript.source_connector, "kabo-video-analysis");
  assert.equal(evidence.transcript.origin, "speech_recognition");
  assert.deepEqual(evidence.transcript.cues[2], { start_s: 21, text: "Lower heat, and look at that." });
  const entry = evidence.acquisition.find((item) => item.operation === "analyze_content_video");
  assert.equal(entry.status, "completed");
  assert.equal(entry.connector_request_id, viewerFixture.id);
  assert.match(entry.note, /after 1 get_analysis_run poll/);
  const refs = await readJson(path.join(run, "analysis/content_evidence.references.json"));
  assert.ok(refs.evidence_refs.includes("V01"));
  const timing = await readJson(path.join(run, "analysis/timing.json"));
  assert.equal(timing.observation_source, "whole_video");
});

test("combined: the viewer starts before the media call, and both readings merge into one evidence object", async (t) => {
  const { run, out } = await observe(t, "combined");
  assert.match(out, /"source": "combined"/);
  await writeRequest(run);
  const built = build(run, flagsOf(out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.frames.status, "available");
  assert.equal(evidence.viewer_observations.status, "available");
  // A fetched transcript wins over the viewer's, and the run says so.
  assert.equal(evidence.transcript.source_connector, "public-video-media");
  assert.ok(evidence.limitations.some((line) => /viewer also returned a transcript/.test(line)), evidence.limitations.join(" | "));
  assert.equal((await readJson(path.join(run, "analysis/timing.json"))).observation_source, "combined");
});

test("combined hand-over: analyze_content_video is the first call of the first round", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "combined"], run);
  assert.deepEqual(callLines(first.out).map((call) => call.tool), ["analyze_content_video", "collect_video_media"]);
  const ops = callLines(first.out)[1].arguments.requests.map((r) => r.operation);
  assert.deepEqual(ops, ["collect_public_metadata", "fetch_transcript", "extract_keyframes", "measure_media_signals"]);
  assert.match(first.out, /^Hand-over: /m);
});

test("fallback: server frames with nothing usable start one whole-video viewing, labelled whole_video", async (t) => {
  const { run, out, handed } = await observe(t, null, { mediaFailed: true });
  assert.match(out, /"source": "whole_video"/);
  assert.match(out, /Fallback: server_frames failed \(media_unavailable\); falling back to whole_video/);
  assert.match(flagsOf(out), /--viewer snapshot\/whole-video\.json/);
  // Every media operation was already asked for: the viewing starts with no second media call.
  assert.deepEqual(handed.map((call) => call.tool), ["collect_video_media", "analyze_content_video"]);
  await writeRequest(run);
  const built = build(run, flagsOf(out));
  assert.equal(built.code, 0, built.out);
  assertValidEvidence(await readJson(path.join(run, "analysis/content_evidence.json")));
  // The failed media jobs observed nothing: the run is a whole-video one, not combined.
  assert.equal((await readJson(path.join(run, "analysis/timing.json"))).observation_source, "whole_video");
});

// A viewing that fails or runs out of time on TikTok had only the metadata-only media call beside it: the fallback
// must hand over a media call for the frames, transcript and measurements, and judge them on that call's results.
const backdate = async (run) => {
  const file = path.join(run, "observe-video.json");
  const state = await readJson(file);
  // Once, as soon as the viewing has started (it waits for the duration the metadata call reports).
  if (!state.viewer?.active || state.backdated) return;
  state.backdated = true;
  state.viewer.started_at = new Date(Date.now() - 9 * 60 * 1000).toISOString();
  await writeFile(file, JSON.stringify(state));
};
for (const [name, options, code, failure] of [
  ["an MCP error result", { viewerSteps: [JSON.stringify({ isError: true, content: [{ type: "text", text: "subscription_required: an active Pro subscription is required for a new analysis" }] })] },
    "subscription_required", { code: "subscription_required", retryable: false }],
  ["a bare failure body", { viewerSteps: [JSON.stringify({ code: "quota_exceeded", message: "The analysis quota is used up.", retryable: true })] },
    "quota_exceeded", { code: "quota_exceeded", retryable: true }],
  ["the viewing budget running out", { viewerSteps: [queued], afterRound: backdate }, "still_running", null],
]) {
  test(`fallback: a whole-video viewing ended by ${name} hands over the frames media call`, async (t) => {
    const back = await observe(t, "whole_video", options);
    assert.match(back.out, /"source": "server_frames"/);
    assert.match(back.out, new RegExp(`whole_video failed \\(${code}\\); falling back to server_frames`));
    const media = back.handed.filter((call) => call.tool === "collect_video_media");
    assert.equal(media.length, 2, back.out);
    assert.deepEqual(operationsOf(media[0]), ["collect_public_metadata"]);
    // Exactly what the first call did not ask for, under the same run key.
    assert.deepEqual(operationsOf(media[1]), ["fetch_transcript", "extract_keyframes", "measure_media_signals"]);
    assert.equal(media[1].arguments.run_key, media[0].arguments.run_key);
    // Never a second paid viewing in the same run.
    assert.equal(back.handed.filter((call) => call.tool === "analyze_content_video").length, 1);
    assert.match(back.out, /^read: .*"read_research_data_artifacts"/m);
    await writeRequest(back.run);
    const rebuilt = build(back.run, flagsOf(back.out));
    assert.equal(rebuilt.code, 0, rebuilt.out);
    const evidence = await readJson(path.join(back.run, "analysis/content_evidence.json"));
    assertValidEvidence(evidence);
    assert.equal(evidence.frames.status, "available");
    assert.equal(evidence.transcript.source_connector, "public-video-media");
    assert.equal(evidence.content_metadata.status, "available");
    if (failure) {
      assert.equal(evidence.viewer_observations.status, "unavailable");
      assert.deepEqual(evidence.viewer_observations.failure, failure);
    } else assert.equal(evidence.viewer_observations.status, "pending");
    assert.equal((await readJson(path.join(back.run, "analysis/timing.json"))).observation_source, "server_frames");
  });
}

test("a duration the media call returned keeps an over-long video from starting a viewing", async (t) => {
  const { out, handed } = await observe(t, null, { mediaFailed: true, duration: 900 });
  assert.equal(handed.filter((call) => call.tool === "analyze_content_video").length, 0, out);
  assert.match(out, /Fallback: server_frames failed \(media_unavailable\); the video runs 900s, past the whole-video limit of 600s/);
});

test("transcript export: never a whole-video viewing, and a finished transcript with no words is its answer", async (t) => {
  const failed = await observe(t, null, { mode: "transcript_export", mediaFailed: true });
  assert.deepEqual(failed.handed.map((call) => call.tool), ["collect_video_media"]);
  assert.deepEqual(operationsOf(failed.handed[0]), ["fetch_transcript"]);
  assert.doesNotMatch(failed.out, /analyze_content_video/);
  assert.match(failed.out, /"tried": \["server_frames"\]/);
  const forced = await observe(t, "whole_video", { mode: "transcript_export" });
  assert.deepEqual(forced.handed.map((call) => call.tool), ["collect_video_media"]);
  const music = await observe(t, null, { mode: "transcript_export", emptyTranscript: true });
  assert.deepEqual(music.handed.map((call) => call.tool), ["collect_video_media"]);
  assert.match(music.out, /"tried": \[\]/);
  assert.doesNotMatch(music.out, /^Fallback: /m);
  assert.match(music.out, /no speech to export/);
});

test("craft teardown: a forced whole-video observation still takes server frames", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "craft_teardown", "--duration-s", "30", "--observe-source", "whole_video"], run);
  assert.equal(first.code, 0, first.out);
  assert.match(first.out, /Observation source: combined/);
  const calls = callLines(first.out);
  assert.deepEqual(calls.map((call) => call.tool), ["analyze_content_video", "collect_video_media"]);
  assert.ok(operationsOf(calls[1]).includes("extract_keyframes"));
});

test("the synthetic whole-video fixture is valid against the MCP output schema", async () => {
  const tools = JSON.parse(readFileSync(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8"));
  const list = Array.isArray(tools) ? tools : tools.tools;
  for (const name of ["get_analysis_run", "analyze_content_video"]) {
    const ajv = new Ajv({ allErrors: true, strict: false, logger: false });
    ajv.addFormat("date-time", true); ajv.addFormat("uuid", true);
    const validate = ajv.compile(list.find((tool) => tool.name === name).outputSchema);
    assert.ok(validate(viewerFixture), JSON.stringify(validate.errors));
    assert.ok(validate(queued), JSON.stringify(validate.errors));
  }
});

async function localRun(t) {
  const run = await newRun(t);
  const video = path.join(run, "analysis", "clip.mp4");
  const made = spawnSync("ffmpeg", ["-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x284:rate=10",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest", "-pix_fmt", "yuv420p", video], { encoding: "utf8" });
  assert.equal(made.status, 0, made.stderr);
  const extracted = python("extract_local_frames.py", ["--media", video, "--out-dir", "analysis/frames", "--artifact", "analysis/local-media.json", "--hook-window-s", "3"], run);
  assert.equal(extracted.code, 0, extracted.out);
  await writeRequest(run, { acquisition: "local_file" });
  return run;
}
const hasFfmpeg = spawnSync("ffmpeg", ["-version"]).status === 0;

test("local_frames: the creator's file becomes valid evidence; a whole-video result is refused beside it", { skip: !hasFfmpeg }, async (t) => {
  const run = await localRun(t);
  await writeFile(path.join(run, "host-results/viewer.json"), JSON.stringify(viewerFixture));
  const mixed = shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
    + "--local-media analysis/local-media.json --viewer host-results/viewer.json --output analysis/content_evidence.json");
  assert.equal(mixed.code, 1, mixed.out);
  assert.match(mixed.out, /viewer watched the published copy/);
  const built = shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
    + "--local-media analysis/local-media.json --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json");
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.frames.status, "available");
  assert.equal((await readJson(path.join(run, "analysis/timing.json"))).observation_source, "local_frames");
});

const section = (brief, number) => {
  const start = brief.indexOf(`\n## ${number}. `);
  assert.notEqual(start, -1, `section ${number}`);
  const end = brief.indexOf("\n## ", start + 4);
  return brief.slice(start, end === -1 ? undefined : end);
};
async function prepare(run, args, question = "why did this flop?") {
  await writeFile(path.join(run, "analysis/question.txt"), question);
  return python("prepare_analysis.py", ["--run", run, "--question-file", path.join(run, "analysis/question.txt"), ...args], run);
}

// Section 5 is byte-identical here because every source selects the same cards; a requested card one source cannot
// support is skipped, and section 5 then says so (see the method-selection test).
test("one brief from any source: sections 1, 2, 5, 6 and 7 are byte-identical when the same cards are selected; discarded viewer fields never reach it", async (t) => {
  const briefs = {};
  for (const source of ["server_frames", "whole_video", "combined"]) {
    const { run, out } = await observe(t, source);
    await writeRequest(run);
    assert.equal(build(run, flagsOf(out)).code, 0);
    const prepared = await prepare(run, ["--mode", "diagnosis", "--focus", "opening"]);
    assert.equal(prepared.code, 0, prepared.out);
    assert.match(prepared.out, /Read analysis\/brief\.md whole now/);
    briefs[source] = await readFile(path.join(run, "analysis/brief.md"), "utf8");
    assert.doesNotMatch(briefs[source], SENTINEL, source);
    const method = await readJson(path.join(run, "analysis/method.json"));
    assert.deepEqual(method.cards.map((card) => [card.id, card.role]), [["diagnosis-default", "base"], ["opening", "topic"]]);
    assert.equal(method.schema_version, "method-selection/v1");
    const timing = await readJson(path.join(run, "analysis/timing.json"));
    assert.deepEqual(timing.stages.map((stage) => stage.stage), ["observe", "prepare"]);
    assert.ok(existsSync(path.join(run, "analysis/deterministic.json")));
  }
  if (hasFfmpeg) {
    const run = await localRun(t);
    assert.equal(shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
      + "--local-media analysis/local-media.json --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json").code, 0);
    assert.equal((await prepare(run, ["--mode", "diagnosis", "--focus", "opening"])).code, 0);
    briefs.local_frames = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  }
  const headings = briefs.server_frames.split("\n").filter((line) => line.startsWith("## "));
  assert.deepEqual(headings, ["## 1. Creator question", "## 2. Mode", "## 3. Evidence index", "## 4. Deterministic results",
    "## 5. Method", "## 6. Judgment rules", "## 7. Output contract"]);
  for (const [source, brief] of Object.entries(briefs))
    for (const number of [1, 2, 5, 6, 7]) assert.equal(section(brief, number), section(briefs.server_frames, number), `${source} section ${number}`);
  assert.match(section(briefs.whole_video, 3), /`V01` 0–2\.5s \[hook\]/);
  assert.match(section(briefs.server_frames, 3), /`frame-0001` 0s/);
  assert.match(section(briefs.server_frames, 7), /"title": "Video judgment"/);
});

test("method selection: no focus is the base card only; unknown or excess focus exits 2; missing evidence skips or refuses", async (t) => {
  const { run, out } = await observe(t, "whole_video");
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const plain = await prepare(run, ["--mode", "diagnosis"], "");
  assert.equal(plain.code, 0, plain.out);
  const method = await readJson(path.join(run, "analysis/method.json"));
  assert.deepEqual(method.cards.map((card) => card.id), ["diagnosis-default"]);
  assert.equal(method.default_only, true);
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.match(section(brief, 1), /no words beyond the link/);
  assert.match(section(brief, 2), /Focus: none \(default analysis\)/);

  const select = (...args) => python("select_method.py", ["--evidence", path.join(run, "analysis/content_evidence.json"), "--out", path.join(run, "analysis/m.json"), ...args], run);
  assert.equal(select("--mode", "diagnosis", "--focus", "no-such-card").code, 2);
  assert.equal(select("--mode", "diagnosis", "--focus", "opening,sound,emotion").code, 2);
  assert.equal(select("--mode", "diagnosis", "--focus", "diagnosis-default").code, 2);
  assert.equal((await prepare(run, ["--mode", "diagnosis", "--focus", "no-such-card"])).code, 2);
  // A whole-video-only run has no measurements or frames: the pacing card is skipped and recorded...
  const skipped = select("--mode", "diagnosis", "--focus", "editing-pacing");
  assert.equal(skipped.code, 0, skipped.out);
  assert.deepEqual((await readJson(path.join(run, "analysis/m.json"))).skipped, [{ id: "editing-pacing", reason: "evidence_missing:measure" }]);
  // A requested card that was skipped is still a focused request: the brief says it was skipped, not that none was asked.
  assert.equal((await readJson(path.join(run, "analysis/m.json"))).default_only, false);
  const focused = await prepare(run, ["--mode", "diagnosis", "--focus", "editing-pacing"], "is the pacing too slow?");
  assert.equal(focused.code, 0, focused.out);
  const focusedBrief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.match(section(focusedBrief, 3), /Method card `editing-pacing` was skipped: evidence_missing:measure/);
  assert.match(section(focusedBrief, 5), /The requested topic card `editing-pacing` was skipped for missing evidence \(see the skip notice in section 3\)/);
  assert.doesNotMatch(section(focusedBrief, 5), /No topic card was asked for/);
  // ...and a craft teardown, whose base card needs frames, is refused rather than run without them.
  const craft = select("--mode", "craft_teardown");
  assert.equal(craft.code, 2, craft.out);
  assert.match(craft.out, /needs frames evidence/);
  const exportMode = select("--mode", "transcript_export");
  assert.equal(exportMode.code, 0);
  assert.deepEqual((await readJson(path.join(run, "analysis/m.json"))).cards, []);
});

test("a retried finish keeps one judge and one validate timing entry", async (t) => {
  const run = await newRun(t);
  await writeFile(path.join(run, "analysis/timing.json"), JSON.stringify({ schema_version: "acv-timing/v1", observation_source: "server_frames",
    stages: [{ stage: "prepare", started_at: "2026-11-16T00:00:00.000Z", ended_at: "2026-11-16T00:00:01.000Z", duration_ms: 1000 }] }));
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const finished = python("finish_diagnosis.py", ["--run-dir", run], run);
    assert.notEqual(finished.code, 0, finished.out);
  }
  const timing = await readJson(path.join(run, "analysis/timing.json"));
  assert.deepEqual(timing.stages.map((stage) => stage.stage), ["prepare", "judge", "validate"]);
});

test("a judgment may cite a whole-video note id, and the validator resolves it", async (t) => {
  const { run, out } = await observe(t, "whole_video");
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  await writeFile(path.join(run, "analysis/video_judgment.json"), JSON.stringify({ observations: [{
    observation_id: "obs-1", dimension: "first_frame_promise", statement: "The burnt pan is on screen from the first second.",
    basis: "viewer_observation", evidence_refs: ["V01"], confidence: "medium" }] }));
  const checked = python("compose_video_analysis.py", ["--check-judgment-refs", "--judgment", "analysis/video_judgment.json",
    "--evidence", "analysis/content_evidence.json", "--reference-index", "analysis/content_evidence.references.json"], run);
  assert.equal(checked.code, 0, checked.out);
  const result = JSON.parse(checked.out);
  assert.equal(result.status, "ready", checked.out);
  assert.deepEqual(result.grounding_review.referenced_sources.map((row) => row.kind), ["viewer_observation"]);
});

test("SKILL.md declares the whole-video tools and their permission, and makes a bare link a diagnosis", async () => {
  const text = await readFile(path.join(skill, "SKILL.md"), "utf8");
  const allowed = text.match(/^allowed-tools: (.*)$/m)[1].split(" ");
  for (const tool of ["analyze_content_video", "get_analysis_run", "collect_video_media"]) assert.ok(allowed.includes(tool), tool);
  assert.match(text.match(/^compatibility: "(.*)"$/m)[1], /Kabo permissions?: data[^.]*video/);
  assert.doesNotMatch(text, /a different product flow, not this Skill/);
  assert.match(text, /observe_video\.py/);
  assert.match(text, /prepare_analysis\.py/);
  assert.match(text, /analysis\/brief\.md/);
});

// The rule the Web host uses to read a hand-over (parsePluginHandover in kabo-agent-service), copied from
// acv-video-media.test.mjs: when it parses, the host makes every call itself, writes each result to its file and
// runs the resume command, so the round costs the model nothing on Web.
function hostHandover(stdout) {
  const lines = stdout.split("\n");
  const start = lines.findIndex((line) => line.startsWith("Hand-over: "));
  if (start < 0) return null;
  const words = (text) => {
    const out = []; let i = 0;
    while (i < text.length) {
      if (text[i] === " ") { i += 1; continue; }
      if (text[i] === "'") { const end = text.indexOf("'", i + 1); if (end < 0) return null; out.push(text.slice(i + 1, end)); i = end + 1; if (i < text.length && text[i] !== " ") return null; continue; }
      let end = text.indexOf(" ", i); if (end < 0) end = text.length;
      const word = text.slice(i, end); if (/["`\\]/.test(word)) return null; out.push(word); i = end;
    }
    return out;
  };
  const calls = [], files = []; let resume = null;
  for (const line of lines.slice(start + 1)) {
    const call = /^call: (\{.*\})\s*$/.exec(line);
    if (call) { calls.push(JSON.parse(call[1])); continue; }
    const slot = /^\s+result (\d+)\s+\(fallback file[^:]*: (\/\S+)\)\s*$/.exec(line);
    if (slot) { if (files.length !== calls.length - 1) return null; files.push(slot[2]); continue; }
    const tail = /^Then run this one command right away[^:]*\(ids expire[^)]*\): (.+)$/.exec(line);
    if (tail) {
      const w = words(tail[1].trim());
      if (!w || w[0] !== "cd" || w[2] !== "&&" || w[3] !== "python3") return null;
      const args = []; const rest = w.slice(5);
      for (let k = 0; k < rest.length; k += 1) { if (rest[k] === "--id") { k += 1; continue; } if (rest[k].startsWith("--id=")) continue; args.push(rest[k]); }
      resume = { cwd: w[1], script: w[4], args }; break;
    }
  }
  return resume && calls.length && files.length === calls.length ? { calls, files, resume } : null;
}

test("the observe_video.py hand-over, two calls included, is in the form the Web host executes", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "combined"], run);
  const handover = hostHandover(first.out);
  assert.ok(handover, first.out);
  assert.deepEqual(handover.calls.map((call) => call.tool), ["analyze_content_video", "collect_video_media"]);
  assert.equal(path.basename(handover.resume.script), "observe_video.py");
  await writeFile(handover.files[0], JSON.stringify(viewerFixture));
  await writeFile(handover.files[1], JSON.stringify(composite(handover.calls[1].arguments)));
  const resumed = spawnSync("python3", [handover.resume.script, ...handover.resume.args], { cwd: handover.resume.cwd, encoding: "utf8", env });
  assert.equal(resumed.status, 0, resumed.stdout + resumed.stderr);
  assert.match(resumed.stdout, /"status": "observed"/);
  assert.match(resumed.stdout, /--viewer snapshot\/whole-video\.json/);
});

// Cards first: select_method.py runs on the request alone, before anything is fetched, and the observation reads
// its choice. The sound card adds the whole-video viewing; prepare_analysis.py re-checks the same cards against
// the evidence that arrived, with no --focus of its own.
async function selectFirst(run, focus, mode = "diagnosis") {
  const chosen = python("select_method.py", ["--mode", mode, ...(focus ? ["--focus", focus] : []), "--out", "analysis/method.json"], run);
  assert.equal(chosen.code, 0, chosen.out);
  return readJson(path.join(run, "analysis/method.json"));
}
async function driveFrom(run, out, { viewerSteps = [viewerFixture] } = {}) {
  const steps = [...viewerSteps];
  const handed = [];
  for (let round = 0; round < 8 && !/"status": "observed"/.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    assert.ok(calls.length, out);
    for (const [index, call] of calls.entries()) {
      handed.push(call);
      await writeFile(files[index], call.tool === "collect_video_media" ? mcp(composite(call.arguments)) : mcp(steps.shift()));
    }
    const resumed = shell(resumeOf(out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
    assert.equal(resumed.code, 0, resumed.out);
    out = resumed.out;
  }
  assert.match(out, /"status": "observed"/);
  return { out, handed };
}

test("cards first: the pre-fetch selection skips nothing, and the sound card makes the observation combined", async (t) => {
  const run = await newRun(t);
  const method = await selectFirst(run, "sound");
  assert.deepEqual(method.cards.map((card) => [card.id, card.role]), [["diagnosis-default", "base"], ["sound", "topic"]]);
  assert.deepEqual(method.skipped, []);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  assert.equal(first.code, 0, first.out);
  assert.match(first.out, /Observation source: combined \(default order; the sound card adds whole_video\)/);
  // The duration is not known yet: the media call goes first, and the paid viewing starts once it reports 30 s.
  assert.deepEqual(callLines(first.out).map((call) => call.tool), ["collect_video_media"]);
  const { out, handed } = await driveFrom(run, first.out);
  assert.deepEqual(handed.map((call) => call.tool), ["collect_video_media", "analyze_content_video", "get_analysis_run"].slice(0, handed.length));
  assert.match(out, /"source": "combined"/);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "diagnosis"], "does the music fit?");
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.match(section(brief, 2), /Focus: `sound`/);
  assert.match(section(brief, 5), /\(`sound`, topic card/);
  assert.deepEqual((await readJson(path.join(run, "analysis/method.json"))).cards.map((card) => card.id), ["diagnosis-default", "sound"]);

  // Without the sound card the same link observes server frames only.
  const plain = await newRun(t);
  await selectFirst(plain, "opening");
  const framesOnly = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], plain);
  assert.match(framesOnly.out, /Observation source: server_frames \(default order\)/);
  assert.deepEqual(callLines(framesOnly.out).map((call) => call.tool), ["collect_video_media"]);
});

test("cards first: a chosen card the evidence cannot support is skipped by prepare_analysis.py, and the brief says so", async (t) => {
  const run = await newRun(t);
  await selectFirst(run, "editing-pacing");
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--observe-source", "whole_video"], run);
  const { out } = await driveFrom(run, first.out);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "diagnosis"], "is the pacing too slow?");
  assert.equal(prepared.code, 0, prepared.out);
  const method = await readJson(path.join(run, "analysis/method.json"));
  assert.deepEqual(method.skipped, [{ id: "editing-pacing", reason: "evidence_missing:measure" }]);
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.match(section(brief, 2), /Focus: `editing-pacing`/);
  assert.match(section(brief, 5), /The requested topic card `editing-pacing` was skipped for missing evidence/);
  // Run again (a corrected attempt): the skipped card is still the request, not forgotten.
  assert.equal((await prepare(run, ["--mode", "diagnosis"], "is the pacing too slow?")).code, 0);
  assert.deepEqual((await readJson(path.join(run, "analysis/method.json"))).skipped, [{ id: "editing-pacing", reason: "evidence_missing:measure" }]);
});

// A finished whole-video result asked for with delivery "download" carries a signed link instead of its result. The
// script downloads it through static_host.py's verified downloader; the HTTPS answer is faked in-process (the same
// approach as static-host-fetch.test.mjs), so nothing touches the network.
const DOWNLOAD_HARNESS = String.raw`
import base64, http.client, io, json, os, runpy, sys, urllib.request, urllib.response
responses = json.loads(os.environ["FAKE_RESPONSES"])
class FakeHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        code, body, headers = responses[req.full_url]
        message = http.client.parse_headers(io.BytesIO(("".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n").encode()))
        response = urllib.response.addinfourl(io.BytesIO(base64.b64decode(body)), message, req.full_url, code)
        response.msg = "fake"
        return response
original = urllib.request.build_opener
urllib.request.build_opener = lambda *handlers: original(*handlers, FakeHTTPS())
script = sys.argv[1]
sys.argv = [script, *sys.argv[2:]]
runpy.run_path(script, run_name="__main__")
`;
const LINK = "https://storage.googleapis.com/kabo-research/analysis-run/result.json?X-Goog-Signature=abc";
function offered(body, { sha = null, expires = new Date(Date.now() + 600000).toISOString() } = {}) {
  // The server's real shape: result and transcript stay in the answer as null (they are required in its schema), and
  // the download reuses the envelope export (kind "envelope").
  const { result, transcript, ...head } = viewerFixture;
  return { ...head, result: null, transcript: null, download: { status: "ready", kind: "envelope", url: LINK, expires_at: expires.replace(/\.\d+Z$/, "Z"),
    sha256: sha ?? createHash("sha256").update(body).digest("hex"), bytes: Buffer.byteLength(body), content_type: "application/json" } };
}
async function resumeWithFake(t, run, responses) {
  const harness = path.join(await mkdtemp(path.join(os.tmpdir(), "kabo-acv-harness-")), "harness.py");
  t.after(() => rm(path.dirname(harness), { recursive: true, force: true }));
  await writeFile(harness, DOWNLOAD_HARNESS);
  const result = spawnSync("python3", ["-B", harness, path.join(scripts, "observe_video.py"), "--url", TIKTOK, "--mode", "diagnosis",
    "--placed", "--poll-sleep-s", "0"], { cwd: run, encoding: "utf8", env: { ...env, FAKE_RESPONSES: JSON.stringify(responses) } });
  return { code: result.status, out: result.stdout + result.stderr };
}
async function startWholeVideo(t) {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  const calls = callLines(first.out), files = slotFiles(first.out);
  await writeFile(files[1], mcp(composite(calls[1].arguments)));
  return { run, files };
}

test("whole_video download: the result is downloaded, checked against its sha256 and bytes, and read like an inline one", async (t) => {
  const { run, files } = await startWholeVideo(t);
  const body = JSON.stringify(viewerFixture);
  await writeFile(files[0], mcp(offered(body)));
  const resumed = await resumeWithFake(t, run, { [LINK]: [200, Buffer.from(body).toString("base64"), { "Content-Type": "application/json" }] });
  assert.equal(resumed.code, 0, resumed.out);
  assert.match(resumed.out, /"status": "observed"/);
  assert.doesNotMatch(resumed.out, /X-Goog-Signature/);
  const persisted = await readJson(path.join(run, "snapshot/whole-video.json"));
  assert.equal(persisted.delivery, "download");
  assert.equal(persisted.download.sha256, createHash("sha256").update(body).digest("hex"));
  assert.doesNotMatch(JSON.stringify(persisted), SENTINEL);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(resumed.out)).code, 0);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assert.equal(evidence.viewer_observations.status, "available");
  assert.equal(evidence.viewer_observations.items[0].id, "V01");
});

test("whole_video download: a mismatched body is never used; the finished result is read again, inline", async (t) => {
  const { run, files } = await startWholeVideo(t);
  const body = JSON.stringify(viewerFixture);
  await writeFile(files[0], mcp(offered(body, { sha: "0".repeat(64) })));
  const resumed = await resumeWithFake(t, run, { [LINK]: [200, Buffer.from(body).toString("base64"), { "Content-Type": "application/json" }] });
  assert.equal(resumed.code, 0, resumed.out);
  assert.deepEqual(callLines(resumed.out), [{ tool: "get_analysis_run", arguments: { analysis_id: viewerFixture.id, delivery: "inline" } }]);
  assert.equal(existsSync(path.join(run, "snapshot/whole-video.json")), false);
  await writeFile(slotFiles(resumed.out)[0], mcp(viewerFixture));
  const done = shell(resumeOf(resumed.out));
  assert.equal(done.code, 0, done.out);
  assert.match(done.out, /"status": "observed"/);
  assert.equal((await readJson(path.join(run, "snapshot/whole-video.json"))).delivery, "inline");
});

test("whole_video download: an expired link asks for a new one, and the re-reading is bounded", async (t) => {
  const { run, files } = await startWholeVideo(t);
  const body = JSON.stringify(viewerFixture);
  const stale = mcp(offered(body, { expires: "2026-01-01T00:00:00.000Z" }));
  await writeFile(files[0], stale);
  let out = (await resumeWithFake(t, run, {})).out;
  assert.deepEqual(callLines(out), [{ tool: "get_analysis_run", arguments: { analysis_id: viewerFixture.id, wait_s: 45, delivery: "download" } }]);
  // Every answer keeps expiring: after two re-readings the viewing ends as unavailable and frames take over.
  for (let round = 0; round < 4 && callLines(out).every((call) => call.tool === "get_analysis_run"); round += 1) {
    await writeFile(slotFiles(out)[0], stale);
    out = (await resumeWithFake(t, run, {})).out;
  }
  assert.match(out, /whole_video returned no usable evidence \(download_failed\); trying server_frames/);
  assert.equal(callLines(out).filter((call) => call.tool === "get_analysis_run").length, 0);
});

test("a video attached in Kabo (kabo-file:<id>) goes to the media tool as its url; it gets no whole-video viewing", async (t) => {
  const run = await newRun(t);
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  await selectFirst(run, "sound");
  const first = python("observe_video.py", ["--url", `KABO-FILE:${id.toUpperCase()}`, "--mode", "diagnosis"], run);
  assert.equal(first.code, 0, first.out);
  assert.match(first.out, /Observation source: server_frames/);
  const calls = callLines(first.out);
  assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media"]);
  assert.deepEqual(operationsOf(calls[0]), ["fetch_transcript", "extract_keyframes", "measure_media_signals"]);
  for (const request of calls[0].arguments.requests) assert.equal(request.parameters.url, `kabo-file:${id}`);
  await writeFile(slotFiles(first.out)[0], mcp(composite(calls[0].arguments)));
  const done = shell(resumeOf(first.out));
  assert.match(done.out, /"status": "observed"/);
  const made = python("prepare_link_request.py", ["--file-ref", `kabo-file:${id}`, "--platform", "tiktok", "--subject-state", "own_unpublished",
    "--max-connector-calls", "10", "--confirmed-by-user", "--output", path.join(run, "analysis/video-analysis-request.json")], run);
  assert.equal(made.code, 0, made.out);
  const request = await readJson(path.join(run, "analysis/video-analysis-request.json"));
  assert.deepEqual([request.source.acquisition, request.source.url, request.source.content_id, request.source.subject_state],
    ["public_url", `kabo-file:${id}`, id, "own_unpublished"]);
  const built = build(run, flagsOf(done.out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.content_ref.permalink, `kabo-file:${id}`);
  // A malformed reference is refused before any call is handed over.
  assert.match(python("collect_media.py", ["--url", "kabo-file:not-a-uuid", "--operations", "transcript"], run).out, /kabo-file:<id>/);
  assert.equal(python("prepare_link_request.py", ["--file-ref", `kabo-file:${id}`, "--subject-state", "unknown",
    "--max-connector-calls", "1", "--output", path.join(run, "analysis/other.json")], run).code, 1);
});

test("SKILL.md: cards are chosen before the observation, and an unsupported link stops the run", async () => {
  const text = await readFile(path.join(skill, "SKILL.md"), "utf8");
  assert.ok(text.indexOf("select_method.py") < text.indexOf("observe_video.py --url"), "select_method.py comes before the observation");
  assert.ok(text.indexOf("observe_video.py --url") < text.indexOf("prepare_analysis.py --run"));
  assert.match(text, /when a tool says the platform or link is not\s+supported, tell the creator which link could not be read and stop/);
  assert.doesNotMatch(text, /Douyin, Xiaohongshu, Kuaishou, Facebook, Bilibili/);
  assert.match(text, /kabo-file:<id>/);
  assert.match(text.match(/^compatibility: "(.*)"$/m)[1], /faster-whisper/);
});

// The paid viewing starts only once the duration is known to be within the limit. The backend cannot look the
// duration up for Instagram or TikTok, so the script reads it from the media results (or YouTube's metadata envelope)
// first, in the rounds the media call already takes.
const noDuration = (args) => {
  const value = composite(args);
  for (const call of value.calls) {
    if (call.result.data?.video) call.result.data.video.duration_seconds = null;
    if (call.result.data) delete call.result.data.duration_s;
  }
  return value;
};

test("duration gate: a forced viewing of a video the metadata says is too long never starts; frames take over", async (t) => {
  const run = await newRun(t);
  let out = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--observe-source", "whole_video"], run).out;
  assert.deepEqual(callLines(out).map((call) => call.tool), ["collect_video_media"]);
  assert.deepEqual(operationsOf(callLines(out)[0]), ["collect_public_metadata"]);
  const handed = [];
  for (let round = 0; round < 4 && !/"status": "observed"/.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    for (const [index, call] of calls.entries()) { handed.push(call.tool); await writeFile(files[index], mcp(composite(call.arguments, { duration: 900 }))); }
    out = shell(resumeOf(out)).out;
  }
  assert.match(out, /"source": "server_frames"/);
  assert.equal(handed.includes("analyze_content_video"), false);
  assert.match(flagsOf(out), /--limitation 'Whole-video viewing not started because the video runs 900s, past the whole-video limit of 600s\.'/);
  await writeRequest(run);
  const built = build(run, flagsOf(out));
  assert.equal(built.code, 0, built.out);
  assert.ok((await readJson(path.join(run, "analysis/content_evidence.json"))).limitations.some((line) => /runs 900s/.test(line)));
});

test("duration gate: when no media result reports a duration, the sound card's viewing is not started and frames carry on", async (t) => {
  const run = await newRun(t);
  await selectFirst(run, "sound");
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  const calls = callLines(first.out);
  assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media"]);
  await writeFile(slotFiles(first.out)[0], mcp(noDuration(calls[0].arguments)));
  const done = shell(resumeOf(first.out));
  assert.equal(done.code, 0, done.out);
  assert.match(done.out, /"source": "server_frames"/);
  assert.equal(callLines(done.out).length, 0);
  assert.match(done.out, /Fallback: combined narrowed to server_frames \(duration_unknown\)/);
  assert.match(flagsOf(done.out), /--limitation 'Whole-video viewing not started because the video duration could not be read/);
});

test("duration gate: YouTube reads the duration from its own metadata envelope, and without it no viewing starts", async (t) => {
  const YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
  const youtubeEnvelope = { schema_version: "1.0", connector_id: "youtube-public", operation: "get_video", status: "completed",
    data: { rows: [{ id: "dQw4w9WgXcQ", duration_seconds: 45 }] } };
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", YT, "--mode", "diagnosis", "--observe-source", "whole_video"], run);
  assert.equal(first.code, 0, first.out);
  assert.equal(callLines(first.out).length, 0);
  assert.match(first.out, /starts only once the video's duration is known/);
  await writeFile(path.join(run, "snapshot/envelope-01.json"), JSON.stringify(youtubeEnvelope));
  const resumed = shell(first.out.split("\n").find((line) => line.includes("then run this one command")).split("then run this one command: ")[1]);
  assert.deepEqual(callLines(resumed.out).map((call) => call.tool), ["analyze_content_video"]);
  assert.equal(callLines(resumed.out)[0].arguments.source_url, YT);

  const bare = await newRun(t);
  const waiting = python("observe_video.py", ["--url", YT, "--mode", "diagnosis", "--observe-source", "whole_video"], bare);
  const fell = shell(waiting.out.split("\n").find((line) => line.includes("then run this one command")).split("then run this one command: ")[1]);
  assert.match(fell.out, /trying server_frames/);
  assert.deepEqual(callLines(fell.out).map((call) => call.tool), ["collect_video_media"]);
});

// A video attached in Kabo, read by the media tool from the stored file. The envelopes follow the backend tests that
// pin the uploaded-file branch (scripts/fixtures/acv-kabo-file/README.md): extra fields (frame_preview, width,
// height, fps, has_audio, origin) are tolerated, null platform fields stay unavailable, and the transcript is
// machine-heard.
const uploaded = JSON.parse(readFileSync(path.join(root, "scripts/fixtures/acv-kabo-file/envelopes.json"), "utf8"));
function uploadedComposite(args, replace = {}) {
  const jobs = [], calls = [];
  for (const request of args.requests) {
    const result = replace[request.operation] ?? uploaded.envelopes[request.operation];
    jobs.push({ group: `video/${request.operation}`, content_id: "video", operation: request.operation, attempt: 1,
      job_id: result.job_id, status: result.status });
    calls.push({ tool: TOOLS[request.operation], parameters: request.parameters, group: `video/${request.operation}`, attempts: 1, result });
  }
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_video_media", status: "completed", calls,
    summary: { requests: jobs.length, pending: 0, jobs }, coverage: { deadline_reached: false, unfinished: [], provider_calls: 0, pending: 0 }, limitations: [] };
}
async function uploadedRun(t, replace) {
  const run = await newRun(t);
  const first = python("collect_media.py", ["--url", uploaded.file_ref.toUpperCase().replace("KABO-FILE", "kabo-file"),
    "--operations", "metadata,transcript,keyframes,measure"], run);
  assert.equal(first.code, 0, first.out);
  const [call] = callLines(first.out);
  for (const request of call.arguments.requests) assert.equal(request.parameters.url, uploaded.file_ref);
  await writeFile(slotFiles(first.out)[0], mcp(uploadedComposite(call.arguments, replace)));
  const done = shell(resumeOf(first.out));
  assert.equal(done.code, 0, done.out);
  assert.match(done.out, /"status": "collected"/);
  const made = python("prepare_link_request.py", ["--file-ref", uploaded.file_ref, "--platform", "instagram", "--subject-state", "own_unpublished",
    "--max-connector-calls", "10", "--confirmed-by-user", "--output", path.join(run, "analysis/video-analysis-request.json")], run);
  assert.equal(made.code, 0, made.out);
  const built = build(run, flagsOf(done.out));
  assert.equal(built.code, 0, built.out);
  return { run, done, evidence: await readJson(path.join(run, "analysis/content_evidence.json")) };
}

test("kabo-file: the uploaded-file envelopes go through collect_media.py, the evidence builder and the brief", async (t) => {
  const { run, done, evidence } = await uploadedRun(t);
  assert.match(done.out, /^read: .*"read_research_data_artifacts"/m);
  assertValidEvidence(evidence);
  const fileId = uploaded.file_ref.split(":")[1];
  assert.equal(evidence.content_ref.content_id, fileId);
  assert.equal(evidence.content_ref.permalink, uploaded.file_ref);
  assert.equal(evidence.content_ref.published_at, "unpublished");
  assert.equal(evidence.frames.status, "available");
  assert.equal(evidence.frames.items.length, 9);
  assert.equal(evidence.transcript.status, "available");
  assert.equal(evidence.transcript.origin, "speech_recognition");
  assert.deepEqual(evidence.transcript.cues, [{ start_s: 0.4, text: "hello" }, { start_s: 2.25, text: "world" }]);
  assert.equal(evidence.media.duration_s, 30.5);
  // Platform counts that do not apply stay unavailable, never zero.
  assert.equal((evidence.public_metrics ?? []).some((metric) => metric.value === 0), false);
  assert.ok(evidence.limitations.some((line) => /uploaded video file, not a platform post/.test(line)), evidence.limitations.join(" | "));
  const prepared = await prepare(run, ["--mode", "diagnosis"], "is this draft ready?");
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.match(section(brief, 3), new RegExp(`content \`${fileId}\``));
  assert.match(section(brief, 3), /`frame-0001` 0s/);

  // A backend that names the file as the video's identity is the same video, whatever the platform field says.
  const named = await uploadedRun(t, { extract_keyframes: { ...uploaded.envelopes.extract_keyframes,
    data: { ...uploaded.envelopes.extract_keyframes.data, video_identity: { platform: null, platform_video_id: fileId } } } });
  assert.equal(named.evidence.content_ref.content_id, fileId);
});

test("kabo-file: no audio or no speech (completed_partial) and no speech recognition (unsupported) are gaps, not failures", async (t) => {
  const transcript = uploaded.envelopes.fetch_transcript;
  const partial = { ...transcript, status: "completed_partial", limitations: ["The uploaded file has no audio track."],
    data: { cues: [], origin: "speech_recognition", cue_count: 0, artifacts: [] } };
  const quiet = await uploadedRun(t, { fetch_transcript: partial });
  assertValidEvidence(quiet.evidence);
  assert.notEqual(quiet.evidence.transcript.status, "available");
  assert.equal(quiet.evidence.frames.status, "available");
  const { data, ...head } = transcript;
  const unsupported = { ...head, status: "unsupported", limitations: ["This deployment has no speech recognition configured for uploaded videos."] };
  const deaf = await uploadedRun(t, { fetch_transcript: unsupported });
  assertValidEvidence(deaf.evidence);
  assert.notEqual(deaf.evidence.transcript.status, "available");
  assert.equal((await prepare(deaf.run, ["--mode", "content_read"], "what does it show?")).code, 0);
});

// A server that does not know wait_s / delivery yet refuses them as invalid arguments (closed input schemas): the
// script repeats that call once with the original arguments and keeps them for the rest of the run. Any other
// failure is the viewing's own answer and is never retried this way.
const REJECTED = (tool) => JSON.stringify({ isError: true, content: [{ type: "text",
  text: `MCP error -32602: Input validation error: Invalid arguments for tool ${tool}: Unrecognized key: "delivery"` }] });

test("an older server refusing wait_s / delivery: the call is repeated once without them, and later readings omit them", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  const calls = callLines(first.out), files = slotFiles(first.out);
  assert.equal(calls[0].arguments.delivery, "download");
  await writeFile(files[0], REJECTED("analyze_content_video"));
  await writeFile(files[1], mcp(composite(calls[1].arguments)));
  const retried = shell(resumeOf(first.out));
  assert.equal(retried.code, 0, retried.out);
  const key = calls[0].arguments.idempotency_key;
  assert.deepEqual(callLines(retried.out), [{ tool: "analyze_content_video", arguments: { source_url: TIKTOK, idempotency_key: key } }]);
  assert.equal((await readJson(path.join(run, "observe-video.json"))).legacy_viewer_args, true);
  await writeFile(slotFiles(retried.out)[0], mcp(queued));
  const polled = shell(resumeOf(retried.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.deepEqual(callLines(polled.out), [{ tool: "get_analysis_run", arguments: { analysis_id: viewerFixture.id } }]);
  await writeFile(slotFiles(polled.out)[0], mcp(viewerFixture));
  const done = shell(resumeOf(polled.out));
  assert.match(done.out, /"status": "observed"/);
  assert.match(done.out, /"whole_video": "completed"/);

  // The same refusal saved as a JSON-RPC error, on a reading: the reading is repeated with the analysis id alone.
  const other = await newRun(t);
  const start = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], other);
  const startCalls = callLines(start.out), startFiles = slotFiles(start.out);
  await writeFile(startFiles[0], mcp(queued));
  await writeFile(startFiles[1], mcp(composite(startCalls[1].arguments)));
  const reading = shell(resumeOf(start.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.deepEqual(callLines(reading.out)[0].arguments, { analysis_id: viewerFixture.id, wait_s: 45, delivery: "download" });
  await writeFile(slotFiles(reading.out)[0], JSON.stringify({ jsonrpc: "2.0", id: 7, error: { code: -32602,
    message: "Input validation error: Invalid arguments for tool get_analysis_run" } }));
  const again = shell(resumeOf(reading.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.deepEqual(callLines(again.out), [{ tool: "get_analysis_run", arguments: { analysis_id: viewerFixture.id } }]);
});

test("a failure that is not an input refusal is never repeated without the new inputs", async (t) => {
  const { out, handed, run } = await observe(t, "whole_video", { viewerSteps: [JSON.stringify({ isError: true,
    content: [{ type: "text", text: "quota_exceeded: The analysis quota is used up." }] })] });
  assert.equal(handed.filter((call) => call.tool === "analyze_content_video").length, 1);
  assert.match(out, /whole_video failed \(quota_exceeded\); falling back to server_frames/);
  assert.equal((await readJson(path.join(run, "observe-video.json"))).legacy_viewer_args, undefined);
});
