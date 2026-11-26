// analyze-content-video observation sources: server frames, whole-video viewing and local frames each become
// ContentEvidence through the one evidence builder, and the one brief script turns any of them into the same
// analysis instructions. Nothing touches the network: the tool results are written in the shapes the backend
// returns (the whole-video result is a synthetic, schema-valid fixture built from the MCP output schema).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readdir, readFile, realpath, rm, writeFile } from "node:fs/promises";
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
function mediaEnvelope(operation, jobId, { failed = false, duration = 30, emptyTranscript = false, frameTimes = [0, 0.5, 1, 12, 25], measuredDuration, cues, signals } = {}) {
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
  if (operation === "fetch_transcript" && cues)
    return { ...base, data: { cues, origin: "speech_recognition", cue_count: cues.length, artifacts: [] } };
  if (operation === "fetch_transcript")
    return { ...base, data: { cues: [{ text: "I ruined it again.", start_ms: 0, end_ms: 2400 }, { text: "Here is why your pan keeps burning.", start_ms: 2400, end_ms: 9000 }],
      origin: "speech_recognition", cue_count: 2, artifacts: [] } };
  if (operation === "measure_media_signals")
    return { ...base, data: { shots: { count: 2, cuts_at_s: [12.5], shots: [{ start_s: 0, end_s: 12.5 }, { start_s: 12.5, end_s: 30 }] }, artifacts: [],
      ...(measuredDuration ? { duration_s: measuredDuration } : {}), ...signals } };
  const frames = frameTimes.map((t, i) => ({ bytes: 100, sha256: "c".repeat(64), frame_id: `frame-${String(i + 1).padStart(4, "0")}`, t_seconds: t,
    object_ref: `creator-media/${jobId}/epoch-1/frame-${String(i + 1).padStart(4, "0")}.jpg` }));
  return { ...base, data: { frames, artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
    selection: "duration_scaled_v1", duration_s: 30, frame_count: frames.length } };
}
// Every signal the measurement returns for a typical 30-second video of six shots: the momentary loudness every 0.1 s,
// brightness per shot, a silence span, framing, and what was and was not measured.
const FULL_SIGNALS = {
  shots: { count: 6, cuts_at_s: [2.4, 6.3, 11, 17.5, 24], shots: [0, 2.4, 6.3, 11, 17.5, 24].map((start, index, all) =>
    ({ index, start_s: start, end_s: all[index + 1] ?? 30, duration_s: +((all[index + 1] ?? 30) - start).toFixed(3) })) },
  silence: { min_s: 0.5, floor_db: -40, spans: [{ start_s: 28.9, end_s: 30, duration_s: 1.1 }] },
  freeze: { min_s: 1, spans: [] },
  framing: { fps: 30, width: 720, height: 1280, aspect_ratio: 0.5625, vertical_screen_fill: 1,
    bars: { top: 0, left: 0, right: 0, bottom: 0 }, content_rect: { x: 0, y: 0, width: 720, height: 1280 } },
  brightness: { samples: 30, whole_video: { samples: 30, mean_luma: 121.4 },
    per_shot: [134.9, 106.4, 146.7, 115.9, 98.2, 127.5].map((mean_luma, shot_index) => ({ shot_index, samples: 5, mean_luma })) },
  loudness: { interval_s: 0.1, series: Array.from({ length: 300 }, (_, i) => ({ t_seconds: +(i / 10).toFixed(1),
    momentary_lufs: i < 3 ? -120.7 : +(-15 + 3 * Math.sin(i / 7)).toFixed(1) })) },
  measured: ["shots", "brightness", "silence", "loudness", "freeze", "framing"], unavailable: [],
};
function composite(args, { failed = false, duration, emptyTranscript, frameTimes, measuredDuration, cues, signals } = {}) {
  const jobs = [], list = [];
  args.requests.forEach((request) => {
    const group = `${request.content_id}/${request.operation}`;
    const jobId = uuid(JOB_NUMBER[request.operation]);
    // `failed: "all"` loses the post's metadata too, as a deleted video does; `true` keeps it, as a public video whose
    // download the platform refused does.
    const lost = failed === "all" || (failed && request.operation !== "collect_public_metadata");
    jobs.push({ group, content_id: request.content_id, operation: request.operation, attempt: 1, job_id: jobId, status: lost ? "failed" : "completed" });
    list.push({ tool: TOOLS[request.operation], parameters: request.parameters, group, attempts: 1,
      result: mediaEnvelope(request.operation, jobId, { failed: lost, duration, emptyTranscript, frameTimes, measuredDuration, cues, signals }) });
  });
  return { schema_version: "kabo-composite-fetch.v1", tool: "collect_video_media", status: "completed", calls: list,
    summary: { requests: jobs.length, pending: 0, jobs }, coverage: { deadline_reached: false, unfinished: [], provider_calls: 0, pending: 0 }, limitations: [] };
}
const mcp = (value) => JSON.stringify({ content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value });
const YOUTUBE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
// youtube_get_video's envelope for that link, as the connector answers (counts as strings, thumbnails highest first).
const youtubeVideo = ({ duration = 30, status = "completed" } = {}) => ({ schema_version: "1.0", connector_id: "youtube-public",
  operation: "get_video", provider: "fixture", status, summary: status === "completed" ? "Found 1 video" : "not available", limitations: [],
  evidence_ref: "ev-yt", raw_sha256: "d".repeat(64), request_id: "req-yt", retrieved_at: "2026-11-16T00:00:00Z",
  data: status === "completed" ? { rows: [{ id: "dQw4w9WgXcQ", title: "Why your pan burns", description: "Fix it", duration_seconds: duration,
    published_at: "2026-11-01T00:00:00Z", metrics: { views: "1200", likes: "90", comments: "4" }, tags: ["cooking"],
    thumbnails: [{ url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg" }] }] } : null });
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
const OBSERVED = /"status": "(?:observed|timed_out|metadata_only|source_unavailable)"/;
async function observe(t, source, { viewerSteps = [viewerFixture], mediaFailed = false, mode = "diagnosis", duration,
  emptyTranscript, afterRound, frameTimes, args = [], cues, url = TIKTOK, measuredDuration, youtube = youtubeVideo() } = {}) {
  const run = await newRun(t);
  let out = python("observe_video.py", ["--url", url, "--mode", mode, ...(source ? ["--observe-source", source] : []), ...args], run).out;
  const steps = [...viewerSteps];
  const handed = [];
  let mediaCalls = 0;
  for (let round = 0; round < 8 && !OBSERVED.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    assert.ok(calls.length, out);
    for (const [index, call] of calls.entries()) {
      handed.push(call);
      if (call.tool === "collect_video_media") {
        const failed = typeof mediaFailed === "function" ? mediaFailed(mediaCalls) : mediaFailed;
        mediaCalls += 1;
        await writeFile(files[index], mcp(composite(call.arguments, { failed, duration, emptyTranscript, frameTimes, cues, measuredDuration })));
      } else if (call.tool === "youtube_get_video") {
        // The post's metadata rides in the first hand-over; null saves nothing, as a host without the tool does.
        if (youtube !== null) await writeFile(files[index], typeof youtube === "string" ? youtube : mcp(youtube));
      } else await writeFile(files[index], typeof steps[0] === "string" ? steps.shift() : mcp(steps.shift()));
    }
    if (afterRound) await afterRound(run, round);
    const resumed = shell(resumeOf(out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
    assert.equal(resumed.code, 0, resumed.out);
    out = resumed.out;
  }
  assert.match(out, OBSERVED);
  return { run, out, handed };
}
const operationsOf = (call) => call.arguments.requests.map((request) => request.operation);

test("observation-order.json is the agreed table, and the next source follows it", async () => {
  assert.deepEqual(await readJson(path.join(skill, "references/observation-order.json")), {
    schema_version: "observation-order/v2", default: ["server_frames"], fallback: { server_frames: ["whole_video"], whole_video: ["server_frames"] },
    add_when_cards: { sound: ["whole_video"], "audience-response": ["comment_summary"] },
    add_when_asks: { identify_track: ["song"] }, add_when_modes: { diagnosis: ["song"] }, whole_video_max_ms: 600000 });
  const pick = (...args) => { const r = python("observation_order.py", args, root); return { code: r.code, ...JSON.parse(r.out) }; };
  assert.equal(pick("--platform", "tiktok").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--failed", "server_frames").source, "whole_video");
  // No platform list: the viewing is offered for any link (and a kabo-file, which has no platform); the tool answers.
  assert.equal(pick("--platform", "douyin", "--failed", "server_frames").source, "whole_video");
  assert.equal(pick("--platform", "bilibili", "--failed", "server_frames").source, "whole_video");
  assert.equal(pick("--failed", "server_frames").source, "whole_video");
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
  assert.equal(pick("--platform", "douyin", "--cards", "sound").source, "combined");
  assert.equal(pick("--platform", "youtube", "--duration-s", "900", "--cards", "sound").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--cards", "sound", "--mode", "transcript_export").source, "server_frames");
  // The audience-response card and a find-the-song request add a side call, never an observation source.
  const audience = pick("--platform", "tiktok", "--cards", "diagnosis-default,audience-response");
  assert.deepEqual([audience.source, audience.side_calls], ["server_frames", ["comment_summary"]]);
  const song = pick("--platform", "tiktok", "--mode", "content_read", "--ask", "identify_track");
  assert.deepEqual([song.source, song.side_calls], ["server_frames", ["song"]]);
  assert.deepEqual(pick("--platform", "tiktok", "--cards", "sound,audience-response").source, "combined");
  assert.deepEqual(pick("--local-file", "--cards", "audience-response").side_calls, []);
  // A diagnosis of a link also asks for the song (one bounded side call, no viewing); other modes do not.
  const diagnosis = pick("--platform", "tiktok", "--mode", "diagnosis");
  assert.deepEqual([diagnosis.source, diagnosis.side_calls], ["server_frames", ["song"]]);
  assert.deepEqual(pick("--platform", "tiktok", "--mode", "diagnosis", "--cards", "audience-response").side_calls, ["comment_summary", "song"]);
  assert.deepEqual(pick("--platform", "tiktok", "--mode", "craft_teardown").side_calls, []);
  assert.deepEqual(pick("--platform", "tiktok", "--mode", "content_read").side_calls, []);
  assert.deepEqual(pick("--local-file", "--mode", "diagnosis").side_calls, []);
  // A viewing that already failed is never added back, and a forced source stays forced.
  assert.equal(pick("--platform", "tiktok", "--failed", "whole_video", "--cards", "sound").source, "server_frames");
  assert.equal(pick("--platform", "tiktok", "--observe-source", "server_frames", "--cards", "sound").source, "server_frames");
});

test("server_frames: one media call, persisted envelopes, valid evidence with no viewer block, timing recorded", async (t) => {
  const { run, out } = await observe(t, null);
  assert.match(out, /"source": "server_frames"/);
  assert.match(out, /^read: /m);
  await writeRequest(run);
  // The hint alone carries every flag the builder requires besides where to write: --request included.
  assert.match(flagsOf(out), /^--request analysis\/video-analysis-request\.json /);
  const built = shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' ${flagsOf(out)} `
    + "--snapshot-root snapshot --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json");
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

// A viewing that fails or runs out of readings on TikTok had only the metadata-only media call beside it: the
// fallback must hand over a media call for the frames, transcript and measurements, and judge them on that call's
// results. (Running out of time is the observation deadline, which leaves no time for a fallback: tested below.)
const backdate = async (run) => {
  const file = path.join(run, "observe-video.json");
  const state = await readJson(file);
  // Once, as soon as the viewing has started (it waits for the duration the metadata call reports).
  if (!state.viewer?.active || state.backdated) return;
  state.backdated = true;
  state.viewer.polls = 15;
  await writeFile(file, JSON.stringify(state));
};
for (const [name, options, code, failure] of [
  ["an MCP error result", { viewerSteps: [JSON.stringify({ isError: true, content: [{ type: "text", text: "subscription_required: an active Pro subscription is required for a new analysis" }] })] },
    "subscription_required", { code: "subscription_required", retryable: false }],
  ["a bare failure body", { viewerSteps: [JSON.stringify({ code: "quota_exceeded", message: "The analysis quota is used up.", retryable: true })] },
    "quota_exceeded", { code: "quota_exceeded", retryable: true }],
  ["its readings running out", { viewerSteps: [queued], afterRound: backdate }, "still_running", null],
]) {
  test(`fallback: a whole-video viewing ended by ${name} hands over the frames media call`, async (t) => {
    const back = await observe(t, "whole_video", options);
    assert.match(back.out, /"source": "server_frames"/);
    assert.match(back.out, new RegExp(`whole_video failed \\(${code}\\); falling back to server_frames`));
    const media = back.handed.filter((call) => call.tool === "collect_video_media");
    assert.equal(media.length, 2, back.out);
    // With the duration unknown, the viewing's media call also measures: the measurement reports the duration.
    assert.deepEqual(operationsOf(media[0]), ["collect_public_metadata", "measure_media_signals"]);
    // Exactly what the first call did not ask for, under the same run key.
    assert.deepEqual(operationsOf(media[1]), ["fetch_transcript", "extract_keyframes"]);
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
  // Frames and words came back empty but the post's metadata arrived: the run goes on from it, never "observed".
  assert.match(out, /"status": "metadata_only"/);
  assert.match(out, /Only the post's metadata arrived/);
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

test("extract_local_frames prints contact-sheet paths from the run folder; the artifact keeps them from analysis/", { skip: !hasFfmpeg }, async (t) => {
  const run = await newRun(t);
  const video = path.join(run, "analysis", "clip.mp4");
  const made = spawnSync("ffmpeg", ["-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x284:rate=10",
    video], { encoding: "utf8" });
  assert.equal(made.status, 0, made.stderr);
  const result = spawnSync("python3", ["-B", path.join(scripts, "extract_local_frames.py"), "--media", video, "--out-dir", "analysis/frames",
    "--artifact", "analysis/local-media.json", "--hook-window-s", "3"], { cwd: run, encoding: "utf8", env });
  assert.equal(result.status, 0, result.stderr);
  const printed = JSON.parse(result.stdout).contact_sheets;
  const stored = (await readJson(path.join(run, "analysis/local-media.json"))).frames.contact_sheets;
  assert.ok(printed.length > 0 && printed.length === stored.length, result.stdout);
  for (const [index, sheet] of printed.entries()) {
    assert.match(sheet.path, /^analysis\/frames\/sheet-\d+\.jpg$/);
    assert.ok(existsSync(path.join(run, sheet.path)), sheet.path);
    assert.equal(stored[index].path, sheet.path.slice("analysis/".length));
  }
});

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
// A diagnosis with topic cards: sections 5-7 are the shipped default rules plus the cards the brief prints at its end.
const cardsLine = (when) => "Sections 5-7 are references/diagnosis-rules.md plus this run's topic cards, which the brief prints at its end "
  + "(in section 5 they follow the base card, in place of the line \"No topic card was asked for\"): do not read analysis/rules.md; "
  + `read references/diagnosis-rules.md whole ${when} only when it is not already in your context.`;
const CREDIT_LINE = /^Credit check: where the Kabo tool start_skill_run exists, call it now \(skill_id analyze-content-video, run_id \d{8}T\d{6}Z-[0-9a-f]{12}\) and wait for its answer before making any call printed below; if it fails with credits_exhausted, tell the creator and stop\. This command fetched nothing itself\.$/;
// The whole brief: sections 1-4 (analysis/brief.md, from the evidence) and 5-7 (analysis/rules.md, from the request).
const readBrief = async (run) => (await readFile(path.join(run, "analysis/brief.md"), "utf8")) + "\n"
  + (await readFile(path.join(run, "analysis/rules.md"), "utf8"));
async function prepare(run, args, question = "why did this flop?") {
  await writeFile(path.join(run, "analysis/question.txt"), question);
  return python("prepare_analysis.py", ["--run", run, "--question-file", path.join(run, "analysis/question.txt"), ...args], run);
}

// Section 5 is byte-identical here because every source selects the same cards; a requested card one source cannot
// support is skipped, and section 5 then says so (see the method-selection test).
test("one brief from any source: sections 1, 2, 5, 6 and 7 are byte-identical when the same cards are selected; discarded viewer fields never reach it", async (t) => {
  const briefs = {};
  const rules = {};
  for (const source of ["server_frames", "whole_video", "combined"]) {
    const { run, out } = await observe(t, source);
    await writeRequest(run);
    assert.equal(build(run, flagsOf(out)).code, 0);
    const prepared = await prepare(run, ["--mode", "diagnosis", "--focus", "opening"]);
    assert.equal(prepared.code, 0, prepared.out);
    // The brief comes printed; the rules file (written here: no begin step ran) is the default plus the topic card,
    // which the brief prints, so it needs no read.
    assert.match(prepared.out, /## 3\. Evidence index/);
    assert.ok(prepared.out.includes(cardsLine("now")), prepared.out);
    briefs[source] = await readBrief(run);
    rules[source] = await readFile(path.join(run, "analysis/rules.md"), "utf8");
    assert.ok(prepared.out.includes(await readFile(path.join(run, "analysis/brief.md"), "utf8")), "the printed brief is the file");
    assert.doesNotMatch(briefs[source], SENTINEL, source);
    const method = await readJson(path.join(run, "analysis/method.json"));
    assert.deepEqual(method.cards.map((card) => [card.id, card.role]), [["diagnosis-default", "base"], ["opening", "topic"]]);
    assert.equal(method.schema_version, "method-selection/v1");
    const timing = await readJson(path.join(run, "analysis/timing.json"));
    assert.deepEqual(timing.stages.map((stage) => stage.stage), ["observe", "prepare"]);
    assert.ok(existsSync(path.join(run, "analysis/deterministic.json")));
    // Unchanged on a second run: nothing new to read.
    const again = await prepare(run, ["--mode", "diagnosis", "--focus", "opening"]);
    assert.ok(again.out.includes(cardsLine("now")), again.out);
  }
  if (hasFfmpeg) {
    const run = await localRun(t);
    assert.equal(shell(`cd '${run}' && python3 -B '${path.join(scripts, "build_content_evidence.py")}' --request analysis/video-analysis-request.json `
      + "--local-media analysis/local-media.json --output analysis/content_evidence.json --reference-index analysis/content_evidence.references.json").code, 0);
    assert.equal((await prepare(run, ["--mode", "diagnosis", "--focus", "opening"])).code, 0);
    briefs.local_frames = await readBrief(run);
  }
  const headings = briefs.server_frames.split("\n").filter((line) => line.startsWith("## "));
  assert.deepEqual(headings, ["## 1. Creator question", "## 2. Mode", "## 3. Evidence index", "## 4. Deterministic results",
    "## Topic cards for section 5", "## 5. Method", "## 6. Judgment rules", "## 7. Output contract"]);
  // Sections 5-7 depend on the request alone: the rules file is the same whichever source observed the video.
  for (const [source, text] of Object.entries(rules)) assert.equal(text, rules.server_frames, source);
  assert.match(rules.server_frames, /^# Analysis rules\n/);
  // The creator view's reference rides with the diagnosis rules, so the view needs no read of its own.
  assert.match(section(briefs.server_frames, 7), /Creator view reference \(`references\/diagnosis-report\.md`\)/);
  assert.match(section(briefs.server_frames, 7), /#### Result shape/);
  for (const [source, brief] of Object.entries(briefs))
    for (const number of [1, 2, 5, 6, 7]) assert.equal(section(brief, number), section(briefs.server_frames, number), `${source} section ${number}`);
  assert.match(section(briefs.whole_video, 3), /`V01` 0–2\.5s \[hook\]/);
  assert.match(section(briefs.server_frames, 3), /`frame-0001` 0s/);
  assert.match(section(briefs.server_frames, 7), /"title": "Video judgment"/);
});

// A default diagnosis (no topic card, no special ask) always has the same sections 5-7. They ship as
// references/diagnosis-rules.md, which a host may preload (SKILL.md metadata.preload), so the run names that file
// instead of its own byte-identical analysis/rules.md and the model reads nothing it already holds.
const REGENERATE_RULES = "python3 -B -c \"import sys; sys.path.insert(0, 'skills/analyze-content-video/scripts'); "
  + "import prepare_analysis as p; p.DEFAULT_RULES.write_text(p.default_rules(), encoding='utf-8')\"";
test("references/diagnosis-rules.md is exactly the default diagnosis rules, and SKILL.md preloads it with the runtime and the card index", async () => {
  const generated = spawnSync("python3", ["-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import prepare_analysis; "
    + "sys.stdout.buffer.write(prepare_analysis.default_rules().encode('utf-8'))", scripts], { encoding: "utf8", env });
  assert.equal(generated.status, 0, generated.stderr);
  const shipped = await readFile(path.join(skill, "references/diagnosis-rules.md"), "utf8");
  assert.ok(generated.stdout === shipped, `references/diagnosis-rules.md drifted from prepare_analysis.default_rules(); regenerate it from the repository root: ${REGENERATE_RULES}`);
  assert.match(shipped, /^# Analysis rules\n[\s\S]*## 5\. Method[\s\S]*`diagnosis-default`, base card[\s\S]*## 6\. Judgment rules[\s\S]*## 7\. Output contract/);
  const body = await readFile(path.join(skill, "SKILL.md"), "utf8");
  const preload = /^metadata:\n(?:  .*\n)*?  preload: "([^"]*)"$/m.exec(body.split("\n---\n")[0] + "\n");
  assert.ok(preload, "SKILL.md declares metadata.preload");
  assert.deepEqual(preload[1].split(" "), ["references/diagnosis-runtime.md", "references/video-method/index.md", "references/diagnosis-rules.md"]);
  for (const file of preload[1].split(" ")) assert.ok(existsSync(path.join(skill, file)), file);
});

test("prepare_analysis.py names references/diagnosis-rules.md for a default diagnosis, that file plus the printed topic cards for a diagnosis with cards, and analysis/rules.md otherwise", async (t) => {
  const { run, out } = await observe(t, "server_frames");
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(prepared.code, 0, prepared.out);
  assert.equal(await readFile(path.join(run, "analysis/rules.md"), "utf8"), await readFile(path.join(skill, "references/diagnosis-rules.md"), "utf8"));
  assert.equal(JSON.parse(prepared.out.split("\n")[0]).rules, "references/diagnosis-rules.md");
  assert.match(prepared.out, /Sections 5-7 are references\/diagnosis-rules\.md \(this run's analysis\/rules\.md is the same text\): no read when it is already in your context, otherwise read it whole now\. Then write analysis\/video_judgment\.json/);
  assert.match(await readFile(path.join(run, "analysis/brief.md"), "utf8"), /Sections 5-7 \(method, judgment rules, output contract\) are `references\/diagnosis-rules\.md`/);
  // Topic cards change only section 5: the default rules plus the cards, printed at the end of the brief, exactly
  // as analysis/rules.md holds them, so the run's own file needs no read.
  const shipped = await readFile(path.join(skill, "references/diagnosis-rules.md"), "utf8");
  const focused = await prepare(run, ["--mode", "diagnosis", "--focus", "opening,narrative-structure"]);
  assert.equal(focused.code, 0, focused.out);
  assert.equal(JSON.parse(focused.out.split("\n")[0]).rules, "references/diagnosis-rules.md + topic cards");
  assert.equal(focused.out.trimEnd().split("\n").at(-1), "(End of analysis/brief.md; read the file only if the text above is cut off.) "
    + cardsLine("now") + " Then write analysis/video_judgment.json as section 7 says.");
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.ok(focused.out.includes(brief), "the printed brief is the file, cards included");
  assert.match(brief, /are `references\/diagnosis-rules\.md`, with this run's topic cards \(at the end of this brief\) in its section 5\./);
  const cards = brief.slice(brief.indexOf("\n### ", brief.indexOf("## Topic cards for section 5")) + 1).trimEnd();
  assert.match(cards, /^### Opening \(`opening`, topic card[\s\S]*\n### Narrative structure \(`narrative-structure`, topic card/);
  assert.doesNotMatch(cards, /diagnosis-default|^## /m);
  // Exact: the default with its opening line of section 5 left out and the printed cards after the base card is
  // byte for byte the run's own rules file.
  const DEFAULT_ONLY = "No topic card was asked for: the base card alone gives the default analysis.\n\n";
  const rebuilt = shipped.replace(DEFAULT_ONLY, "").replace("\n## 6. Judgment rules\n", `\n${cards}\n\n## 6. Judgment rules\n`);
  assert.ok(rebuilt === await readFile(path.join(run, "analysis/rules.md"), "utf8"), "default rules + printed cards = analysis/rules.md");
  // Any other difference keeps the run's own file: a content read has no shipped default.
  const read = await prepare(run, ["--mode", "content_read", "--focus", "opening"]);
  assert.equal(read.code, 0, read.out);
  assert.equal(JSON.parse(read.out.split("\n")[0]).rules, "analysis/rules.md");
  assert.match(read.out, /Sections 5-7 were just written to analysis\/rules\.md: read it whole now/);
  assert.doesNotMatch(read.out, /references\/diagnosis-rules\.md|## Topic cards for section 5/);
  // A rules file that differs from the default anywhere else is never taken for default plus cards.
  await writeFile(path.join(run, "analysis/rules.md"), rebuilt.replace("## 6. Judgment rules\n", "## 6. Judgment rules\n\nOne more rule.\n"));
  const odd = spawnSync("python3", ["-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import prepare_analysis as p; from pathlib import Path; "
    + "print(p.rules_source(Path(sys.argv[2])), p.topic_cards(Path(sys.argv[2])))", scripts, path.join(run, "analysis")], { encoding: "utf8", env });
  assert.equal(odd.stdout.trim(), "analysis/rules.md None", odd.stderr);
});

test("method selection: no focus is the base card only; unknown or excess focus exits 2; missing evidence skips or refuses", async (t) => {
  // The duration is given, so the viewing needs no measurement and the run has none.
  const { run, out } = await observe(t, "whole_video", { args: ["--duration-s", "30"] });
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const plain = await prepare(run, ["--mode", "diagnosis"], "");
  assert.equal(plain.code, 0, plain.out);
  const method = await readJson(path.join(run, "analysis/method.json"));
  assert.deepEqual(method.cards.map((card) => card.id), ["diagnosis-default"]);
  assert.equal(method.default_only, true);
  const brief = await readBrief(run);
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
  const focusedBrief = await readBrief(run);
  assert.match(section(focusedBrief, 3), /Method card `editing-pacing` was skipped: evidence_missing:measure/);
  assert.match(section(focusedBrief, 3), /The requested topic card `editing-pacing` was skipped for missing evidence: answer that part of the question from the other cards in section 5/);
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
  // The long legal-ref list comes last, so the issues and the review are read first.
  assert.deepEqual(Object.keys(result), ["status", "artifact", "issues", "grounding_review", "view_contract", "legal_source_refs"]);
  // A ready judgment brings the creator view's contract with it, the same one --print-view-contract prints.
  const contract = JSON.parse(python("build_creator_result.py", ["--print-view-contract", "--observations-from", "analysis/video_judgment.json"], run).out);
  assert.deepEqual(result.view_contract, contract);
  assert.deepEqual(result.view_contract.creator_view.cards.evidence_refs.at_least_one_from, ["observations.obs-1"]);
  assert.ok(checked.out.indexOf('"grounding_review"') < checked.out.indexOf('"legal_source_refs"'));
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

test("a YouTube link's first hand-over, metadata call included, is in the form the Web host executes", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", YOUTUBE, "--mode", "diagnosis", "--duration-s", "30"], run);
  const handover = hostHandover(first.out);
  assert.ok(handover, first.out);
  assert.deepEqual(handover.calls.map((call) => call.tool), ["collect_video_media", "youtube_get_video"]);
  // The host maps it to data_connector_run youtube-public/get_video: `parameters` must be an object, `delivery` is dropped.
  const { delivery, ...rest } = handover.calls[1].arguments;
  assert.equal(delivery, "download");
  assert.deepEqual(rest, { parameters: { video_id: "dQw4w9WgXcQ" } });
  // What the host writes is the research tool's output and the connector envelope itself, each unwrapped.
  await writeFile(handover.files[0], JSON.stringify(composite(handover.calls[0].arguments)));
  await writeFile(handover.files[1], JSON.stringify(youtubeVideo()));
  const resumed = spawnSync("python3", [handover.resume.script, ...handover.resume.args], { cwd: handover.resume.cwd, encoding: "utf8", env });
  assert.equal(resumed.status, 0, resumed.stdout + resumed.stderr);
  assert.match(resumed.stdout, /"status": "observed"/);
  assert.match(resumed.stdout, /Side calls: metadata completed\./);
  assert.match(flagsOf(resumed.stdout), /^--request analysis\/video-analysis-request\.json --envelope snapshot\/envelope-02\.json --envelope snapshot\/envelope-03\.json --envelope snapshot\/envelope-04\.json --envelope snapshot\/envelope-01\.json /);
  const persisted = await readJson(path.join(run, "snapshot/envelope-01.json"));
  assert.deepEqual([persisted.connector_id, persisted.operation], ["youtube-public", "get_video"]);
});

// Cards first: select_method.py runs on the request alone, before anything is fetched, and the observation reads
// its choice. The sound card adds the whole-video viewing; prepare_analysis.py re-checks the same cards against
// the evidence that arrived, with no --focus of its own.
async function selectFirst(run, focus, mode = "diagnosis") {
  const chosen = python("select_method.py", ["--mode", mode, ...(focus ? ["--focus", focus] : []), "--out", "analysis/method.json"], run);
  assert.equal(chosen.code, 0, chosen.out);
  return readJson(path.join(run, "analysis/method.json"));
}
async function driveFrom(run, out, { viewerSteps = [viewerFixture], media = {}, youtube = youtubeVideo() } = {}) {
  const steps = [...viewerSteps];
  const handed = [];
  for (let round = 0; round < 8 && !/"status": "observed"/.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    assert.ok(calls.length, out);
    for (const [index, call] of calls.entries()) {
      handed.push(call);
      // A diagnosis also asks for the song: answer it with no match, leaving the viewer steps to the viewing. A YouTube
      // link's metadata call gets `youtube` (a string as it is, null saves nothing).
      if (call.tool === "youtube_get_video" && youtube === null) continue;
      await writeFile(files[index], call.tool === "collect_video_media" ? mcp(composite(call.arguments, media))
        : call.tool === "identify_video_song" ? mcp(SONG.noMatch)
        : call.tool === "youtube_get_video" ? (typeof youtube === "string" ? youtube : mcp(youtube))
        : typeof steps[0] === "string" ? steps.shift() : mcp(steps.shift()));
    }
    const resumed = shell(resumeOf(out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
    assert.equal(resumed.code, 0, resumed.out);
    out = resumed.out;
  }
  assert.match(out, /"status": "observed"/);
  return { out, handed };
}

// begin_analysis.py is the four setup steps in one command: the request, the creator's words, the cards and the first
// observation run. Its output is observe_video.py's own, byte for byte, after at most two leading lines (the run
// directory with --workspace, and where sections 5-7 are), because the Web host reads the hand-over from it; the files
// are those the separate steps write, and the brief's sections 5-7 are ready before the fetch.
test("begin_analysis: one command writes what the separate setup steps write and prints observe_video.py's output unchanged", async (t) => {
  const question = "is the hook strong enough? it's my first try";
  const separate = await newRun(t);
  assert.equal(python("prepare_link_request.py", ["--url", TIKTOK, "--platform", "tiktok", "--subject-state", "unknown", "--mode", "diagnosis",
    "--confirmed-by-user", "--output", "analysis/video-analysis-request.json"], separate).code, 0);
  await writeFile(path.join(separate, "analysis/question.txt"), question);
  await selectFirst(separate, "opening,sound");
  const before = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], separate);
  assert.equal(before.code, 0, before.out);

  const run = await newRun(t);
  // A card problem is refused before anything is written or fetched; the corrected command then goes through.
  const refused = python("begin_analysis.py", ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--focus", "opening,no-such-card", "--confirmed-by-user"], run);
  assert.equal(refused.code, 2, refused.out);
  assert.match(refused.out, /unknown method card id\(s\): no-such-card/);
  assert.deepEqual((await readdir(path.join(run, "analysis"))).sort(), []);
  assert.equal(existsSync(path.join(run, "observe-video.json")), false);
  const begun = python("begin_analysis.py", ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--focus", "opening,sound", "--confirmed-by-user"], run);
  assert.equal(begun.code, 0, begun.out);
  // The same output but for the run's own path and the run key derived from it, after one leading line: with topic
  // cards, sections 5-7 are the shipped default plus those cards, which the brief prints.
  const same = (out, dir) => out.replaceAll(dir, "<run>").replace(/"run_key": "acv:[0-9a-f]+"/g, '"run_key": "<key>"');
  const [rulesLine, ...observed] = begun.out.split("\n");
  assert.equal(rulesLine, cardsLine("while the evidence arrives"));
  assert.equal(same(observed.join("\n"), run), same(before.out, separate));
  assert.ok(begun.out.split("\n").some((line) => line.startsWith("Hand-over: ")));
  assert.equal(path.basename(hostHandover(begun.out)?.resume.script ?? ""), "observe_video.py");

  // With --workspace it reserves the run itself: the run directory comes first, then the credit-check line (where
  // start_skill_run exists, it is called before any printed call: the command fetched nothing), then the same
  // output. A refused command reserves nothing.
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-begin-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const noRun = python("begin_analysis.py", ["--workspace", workspace, "--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--focus", "opening,no-such-card", "--confirmed-by-user"], workspace);
  assert.equal(noRun.code, 2, noRun.out);
  assert.equal(existsSync(path.join(workspace, ".kabo-runs")), false);
  const oneStep = python("begin_analysis.py", ["--workspace", workspace, "--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--focus", "opening,sound", "--confirmed-by-user"], workspace);
  assert.equal(oneStep.code, 0, oneStep.out);
  const [runLine, creditLine, rulesAgain, ...rest] = oneStep.out.split("\n");
  const reserved = /^Run directory: (\/.+)$/.exec(runLine)?.[1];
  assert.ok(reserved, oneStep.out);
  assert.equal(path.dirname(reserved), path.join(await realpath(workspace), ".kabo-runs"));
  assert.ok(existsSync(path.join(reserved, ".static-run.json")));
  assert.deepEqual(await readdir(path.join(workspace, ".kabo-runs")), [path.basename(reserved)]);
  assert.match(creditLine, CREDIT_LINE);
  assert.ok(creditLine.includes(`run_id ${path.basename(reserved)})`), creditLine);
  assert.equal(rulesAgain, rulesLine);
  assert.equal(same(rest.join("\n"), reserved), same(before.out, separate));
  assert.equal(hostHandover(oneStep.out)?.resume.cwd, reserved);
  assert.equal((await readJson(path.join(reserved, "analysis/video-analysis-request.json"))).request_id, path.basename(reserved));
  // Another request in the same run is refused before anything is written.
  const other = python("begin_analysis.py", ["--url", TIKTOK, "--subject-state", "third_party", "--mode", "diagnosis"], run);
  assert.equal(other.code, 1, other.out);
  assert.match(other.out, /already holds another request/);

  const request = await readJson(path.join(run, "analysis/video-analysis-request.json"));
  const expected = await readJson(path.join(separate, "analysis/video-analysis-request.json"));
  assert.equal(request.request_id, path.basename(run));
  assert.deepEqual({ ...request, request_id: null }, { ...expected, request_id: null });
  assert.equal(await readFile(path.join(run, "analysis/question.txt"), "utf8"), question);
  assert.deepEqual(await readJson(path.join(run, "analysis/method.json")), await readJson(path.join(separate, "analysis/method.json")));
  const rules = await readFile(path.join(run, "analysis/rules.md"), "utf8");
  assert.match(rules, /## 5\. Method[\s\S]*\(`opening`, topic card[\s\S]*\(`sound`, topic card[\s\S]*## 6\. Judgment rules[\s\S]*## 7\. Output contract/);

  // The observation goes on from observe_video.py's resume command, which builds the evidence and prints the brief
  // itself once the observation ends; the brief finds the rules unchanged.
  const { out } = await driveFrom(run, begun.out);
  assert.doesNotMatch(out, /^Pass these to build_content_evidence\.py/m);
  assert.match(out, /^Evidence \(step 4\) built here, with: --request analysis\/video-analysis-request\.json --envelope snapshot\/envelope-01\.json/m);
  assert.ok(out.includes(cardsLine("now")), out);
  assert.match(out, /## Topic cards for section 5\n[\s\S]*\(`opening`, topic card[\s\S]*\(`sound`, topic card/);
  assert.equal(await readFile(path.join(run, "analysis/rules.md"), "utf8"), rules);
  assert.match(out, /## 1\. Creator question\n\nis the hook strong enough\? it's my first try/);
  assert.ok(out.includes(await readFile(path.join(run, "analysis/brief.md"), "utf8")), "the printed brief is the file");

  // Run again by mistake: the observation is complete, so nothing starts again.
  const again = python("begin_analysis.py", ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--focus", "opening,sound", "--confirmed-by-user"], run);
  assert.equal(again.code, 1, again.out);
  assert.match(again.out, /already complete: never observe twice/);
  assert.doesNotMatch(again.out, /^Hand-over: /m);
});

// Where the host has no start_skill_run, one command opens the run, and the observation's last command builds the
// evidence and prints the brief: a default diagnosis goes from the link to the frames and the judgment in two
// commands. Sections 5-7 are the shipped references/diagnosis-rules.md, which a host may already have preloaded.
async function beginInWorkspace(t, args) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-begin-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const begun = python("begin_analysis.py", ["--workspace", workspace, ...args], workspace);
  assert.equal(begun.code, 0, begun.out);
  const run = /^Run directory: (\/.+)$/m.exec(begun.out)[1];
  return { run, begun };
}
test("begin --workspace, default diagnosis: the observation ends with the evidence built and the brief printed, well under the 64 KiB output cap", async (t) => {
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis", "--question", "", "--confirmed-by-user"]);
  assert.match(begun.out.split("\n")[1], CREDIT_LINE);
  assert.equal(begun.out.split("\n")[2], "Sections 5-7 are references/diagnosis-rules.md (this run's analysis/rules.md is the same text): "
    + "no read when it is already in your context, otherwise read it whole while the evidence arrives.");
  // A typical short video: 30 seconds, 60 frames (every half second), 20 spoken lines, every signal measured.
  const frameTimes = Array.from({ length: 60 }, (_, i) => i / 2);
  const cues = Array.from({ length: 20 }, (_, i) => ({ text: `Line ${i + 1}: here is one more reason your pan keeps burning on a high flame.`,
    start_ms: i * 1500, end_ms: i * 1500 + 1400 }));
  const { out } = await driveFrom(run, begun.out, { media: { frameTimes, cues, signals: FULL_SIGNALS } });
  const bytes = Buffer.byteLength(out);
  t.diagnostic(`final observation output: ${bytes} bytes (brief ${Buffer.byteLength(await readFile(path.join(run, "analysis/brief.md")))} bytes)`);
  assert.ok(bytes < 56 * 1024, `${bytes} bytes`);
  assert.match(out, /^Envelopes included: snapshot\/envelope-01\.json, snapshot\/envelope-02\.json, snapshot\/envelope-03\.json, snapshot\/envelope-04\.json$/m);
  assert.match(out, /^\{"status": "ok", "output": "analysis\/content_evidence\.json"/m);
  // The frame reads come before the brief, the brief is the file, and the last line says to read the frames first.
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  assert.ok(out.indexOf("read: {") < out.indexOf(brief) && out.includes(brief), out);
  assert.match(brief, /are `references\/diagnosis-rules\.md`/);
  assert.match(out, /"rules": "references\/diagnosis-rules\.md"/);
  assert.match(out, /Sections 5-7 are references\/diagnosis-rules\.md \(this run's analysis\/rules\.md is the same text\): no read when it is already in your context, otherwise read it whole now\. Then write analysis\/video_judgment\.json/);
  assert.equal(out.trimEnd().split("\n").at(-1), "Make the frame reads above before writing anything.");
  assertValidEvidence(await readJson(path.join(run, "analysis/content_evidence.json")));
  // Section 3 holds every measured value and every citable reference, so the model reads neither evidence file:
  // each measured group by name with its numbers, each acquisition step, and only references the check accepts.
  const section3 = brief.slice(brief.indexOf("## 3. Evidence index"), brief.indexOf("## 4. "));
  assert.match(section3, /This index lists every citable reference with its value: cite each exactly as written here/);
  assert.match(section3, /they need no read\./);
  assert.doesNotMatch(section3, /read from the evidence file|The complete list of legal references/);
  assert.match(section3, /^- `media\.probed\.loudness` \(momentary loudness summary; `\.<field>`\): interval_s 0\.1, samples 300, mean_lufs -1[0-9.]+, min_lufs -120\.7, .*lead_in_silence_s 0\.2, first_audible_s 0\.3/m);
  assert.match(section3, /^- `media\.probed\.brightness` \(mean luma, 0-255\): 30 samples; whole video mean luma 121\.4 \(`\.whole_video`\); per shot \(`\.per_shot\[i\]` = shot index: mean luma\) \[0\] shot 0: 134\.9, .*\[5\] shot 5: 127\.5$/m);
  assert.match(section3, /^- `media\.probed\.mean_volume_db` = -1[0-9.]+ \(the loudness mean\)$/m);
  assert.match(section3, /^- `media\.probed\.measured`: shots, brightness, silence, loudness, freeze, framing$/m);
  assert.match(section3, /^- `acquisition\[0\]` collect_public_metadata completed; `acquisition\[1\]` /m);
  const refs = new Set((await readJson(path.join(run, "analysis/content_evidence.references.json"))).evidence_refs);
  const cited = [...section3.matchAll(/`((?:media\.probed|media\.discrepancies|acquisition|owner_metrics)[A-Za-z0-9_.\[\]]*)`/g)].map((match) => match[1]);
  assert.ok(cited.length >= 10, cited.join(" "));
  assert.deepEqual(cited.filter((ref) => !refs.has(ref)), []);
  // A second resume by mistake neither observes nor builds again.
  const again = shell(resumeOf(begun.out));
  assert.match(again.out, /already complete; its evidence and brief were built/);
  // Past the output budget (hosts keep 64 KiB of a command's output) the brief stays in its file and the output says so.
  const long = spawnSync("python3", ["-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import observe_video as o; "
    + "o.PRINTED[0] = o.PRINT_LIMIT; sys.exit(o.next_step({'mode': 'diagnosis'}, True))", scripts], { cwd: run, encoding: "utf8", env });
  assert.equal(long.status, 0, long.stderr);
  const [status, note, last] = long.stdout.trimEnd().split("\n");
  assert.equal(JSON.parse(status).status, "ready");
  assert.match(note, /^The brief is too long to print with the observation: read analysis\/brief\.md whole now\. Sections 5-7 are references\/diagnosis-rules\.md/);
  assert.equal(last, "Make the frame reads above before writing anything.");
  assert.doesNotMatch(long.stdout, /# Analysis brief/);

  // A per-run flag that comes in later: the printed rebuild command, with it added, builds over the run's own pair,
  // and the printed step 5 prints the brief again.
  const line = out.split("\n").find((item) => item.startsWith("If another envelope is persisted after this"));
  const [rebuild, again5] = line.slice(line.indexOf("cd '")).split(" then ");
  const rebuilt = shell(`${rebuild} --limitation 'The creator says the audio was replaced after posting.'`);
  assert.equal(rebuilt.code, 0, rebuilt.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assert.ok(JSON.stringify(evidence).includes("the audio was replaced after posting"));
  const index = await readJson(path.join(run, "analysis/content_evidence.references.json"));
  assert.equal(index.evidence_sha256, createHash("sha256").update(await readFile(path.join(run, "analysis/content_evidence.json"))).digest("hex"));
  const reprepared = shell(again5);
  assert.equal(reprepared.code, 0, reprepared.out);
  assert.match(reprepared.out, /## 3\. Evidence index/);
  // --replace builds only over the builder's own pair: an evidence file edited by hand is refused, and kept.
  await writeFile(path.join(run, "analysis/content_evidence.json"), "{}\n");
  const refused = shell(rebuild);
  assert.equal(refused.code, 1, refused.out);
  assert.match(refused.out, /--replace builds again only over this builder's own evidence and reference index/);
  assert.equal(await readFile(path.join(run, "analysis/content_evidence.json"), "utf8"), "{}\n");
});

test("begin --workspace, diagnosis with the two largest topic cards: the brief ends with the cards, no rules file to read, still under the output cap", async (t) => {
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", "how are my hook and my music?", "--focus", "opening,sound", "--confirmed-by-user"]);
  assert.equal(begun.out.split("\n")[2], cardsLine("while the evidence arrives"));
  const frameTimes = Array.from({ length: 60 }, (_, i) => i / 2);
  const cues = Array.from({ length: 20 }, (_, i) => ({ text: `Line ${i + 1}: here is one more reason your pan keeps burning on a high flame.`,
    start_ms: i * 1500, end_ms: i * 1500 + 1400 }));
  const { out } = await driveFrom(run, begun.out, { media: { frameTimes, cues } });
  const bytes = Buffer.byteLength(out);
  const brief = await readFile(path.join(run, "analysis/brief.md"), "utf8");
  const cards = brief.slice(brief.indexOf("## Topic cards for section 5"));
  t.diagnostic(`final observation output: ${bytes} bytes (brief ${Buffer.byteLength(brief)} bytes, of which topic cards ${Buffer.byteLength(cards)})`);
  assert.ok(bytes < 56 * 1024, `${bytes} bytes`);
  assert.ok(out.includes(brief), "the brief, cards included, is printed whole");
  assert.match(out, /"rules": "references\/diagnosis-rules\.md \+ topic cards"/);
  assert.ok(out.includes(cardsLine("now") + " Then write analysis/video_judgment.json as section 7 says."), out);
  assert.doesNotMatch(out, /analysis\/rules\.md: read it whole|(?<!not )read analysis\/rules\.md/);
  assert.equal(out.trimEnd().split("\n").at(-1), "Make the frame reads above before writing anything.");
  // Past the output budget the brief stays in its file, which holds the cards too.
  const long = spawnSync("python3", ["-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import observe_video as o; "
    + "o.PRINTED[0] = o.PRINT_LIMIT; sys.exit(o.next_step({'mode': 'diagnosis'}, True))", scripts], { cwd: run, encoding: "utf8", env });
  assert.equal(long.status, 0, long.stderr);
  const note = long.stdout.trimEnd().split("\n")[1];
  assert.ok(note.startsWith("The brief is too long to print with the observation: read analysis/brief.md whole now. " + cardsLine("now")), note);
});

// The opening on every host: where start_skill_run exists, the model calls it after begin_analysis.py printed the run
// directory and before any printed call, which is safe only because the command itself fetches nothing.
test("begin_analysis.py --workspace fetches nothing itself: with every socket blocked it reserves the run and prints the hand-over calls", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-begin-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const blocked = "import runpy, socket, sys\n"
    + "def refuse(*args, **kwargs):\n    raise SystemExit('network attempt: ' + repr(args))\n"
    + "socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = refuse\n"
    + "sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')\n";
  const done = spawnSync("python3", ["-B", "-c", blocked, path.join(scripts, "begin_analysis.py"), "--workspace", workspace, "--url", TIKTOK,
    "--subject-state", "unknown", "--mode", "diagnosis", "--question", "", "--confirmed-by-user"], { cwd: workspace, encoding: "utf8", env });
  assert.equal(done.status, 0, done.stdout + done.stderr);
  assert.doesNotMatch(done.stdout + done.stderr, /network attempt/);
  assert.match(done.stdout.split("\n")[1], CREDIT_LINE);
  assert.ok(done.stdout.split("\n").some((line) => line.startsWith("Hand-over: ")), done.stdout);
  assert.deepEqual(callLines(done.stdout).map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
});

test("begin_analysis: argument mistakes are refused with one JSON line that says what to correct, and nothing is reserved", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-begin-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const base = ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis", "--question", "hook, pacing, visuals, ending?", "--confirmed-by-user"];
  const refused = (args, cwd = workspace) => {
    const done = python("begin_analysis.py", args, cwd);
    const line = JSON.parse(done.out.trim().split("\n").at(-1));
    assert.equal(existsSync(path.join(workspace, ".kabo-runs")), false, done.out);
    return { code: done.code, ...line };
  };
  // The creator's words where card ids belong: the message names the cards those words point to.
  const words = refused(["--workspace", workspace, ...base, "--focus", "hook,pacing"]);
  assert.equal(words.code, 2);
  assert.match(words.error, /unknown method card id\(s\): hook, pacing\. Topic cards are: .*--focus takes card ids, not the creator's words: hook -> opening; pacing -> editing-pacing$/);
  // More than two cards: the message says to keep the two the question leans on most.
  const many = refused(["--workspace", workspace, ...base, "--focus", "opening,editing-pacing,visual-color,narrative-structure"]);
  assert.equal(many.code, 2);
  assert.match(many.error, /^at most 2 topic cards; got 4 \(opening, editing-pacing, visual-color, narrative-structure\): pass the 2/);
  // A flag argparse refuses (unknown, conflicting or missing) is the same JSON line, exit 2.
  for (const args of [[...base, "--workspace", workspace, "--run", workspace], [...base, "--workspace", workspace, "--question-file", "q.txt"],
    ["--workspace", workspace, "--url", TIKTOK, "--mode", "diagnosis"]]) {
    const flag = refused(args);
    assert.equal(flag.code, 2);
    assert.equal(flag.status, "refused");
    assert.match(flag.error, /Nothing was reserved, written or fetched: correct the arguments \(SKILL\.md, analysis step 2\) and run the same command again$/);
  }
  // A workspace that is not a directory, and no --workspace outside a reserved run.
  const nowhere = refused(["--workspace", path.join(workspace, "no-such-dir"), ...base]);
  assert.equal(nowhere.code, 1);
  assert.match(nowhere.error, /^--workspace takes an existing directory/);
  const unreserved = refused(base);
  assert.equal(unreserved.code, 1);
  assert.match(unreserved.error, /^no run is reserved here: begin with --workspace '<user-workspace>' and the same arguments/);
});

test("a YouTube observation makes youtube_get_video in its first hand-over, persists its answer and builds with it", async (t) => {
  const args = ["--url", YOUTUBE, "--subject-state", "unknown", "--mode", "diagnosis", "--question", "", "--confirmed-by-user", "--duration-s", "30"];
  const first = await beginInWorkspace(t, args);
  const calls = callLines(first.begun.out);
  // Last in the first hand-over, with the arguments the runtime reference prescribes; saved whole like the side calls.
  assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media", "identify_video_song", "youtube_get_video"]);
  assert.deepEqual(calls[2].arguments, { parameters: { video_id: "dQw4w9WgXcQ" }, delivery: "download" });
  assert.match(slotFiles(first.begun.out)[2], /\/host-results\/03-youtube_get_video\.json$/);
  assert.match(first.begun.out, /Save each [^.]*youtube_get_video result whole/);
  const { out } = await driveFrom(first.run, first.begun.out);
  assert.match(out, /^Side calls: song no_match, metadata completed\./m);
  // Read on the first resume, before the media envelopes: envelope-01, persisted as persist_envelope.py would.
  assert.match(out, /^Envelopes included: snapshot\/envelope-02\.json, snapshot\/envelope-03\.json, snapshot\/envelope-04\.json, snapshot\/envelope-01\.json$/m);
  assert.match(out, /# Analysis brief/);
  const persisted = await readJson(path.join(first.run, "snapshot/envelope-01.json"));
  assert.deepEqual([persisted.connector_id, persisted.operation, persisted.status], ["youtube-public", "get_video", "completed"]);
  const evidence = await readJson(path.join(first.run, "analysis/content_evidence.json"));
  assert.equal(evidence.content_metadata.status, "available");
  assert.equal(evidence.content_metadata.title, "Why your pan burns");
  assert.doesNotMatch(out, /metadata call \(youtube_get_video\) brought nothing/);

  // The Web host writes the connector envelope itself (no MCP wrapper, no download): staged and persisted the same way.
  const web = await beginInWorkspace(t, args);
  const onWeb = await driveFrom(web.run, web.begun.out, { youtube: JSON.stringify(youtubeVideo()) });
  assert.match(onWeb.out, /metadata completed/);
  assert.equal((await readJson(path.join(web.run, "analysis/content_evidence.json"))).content_metadata.status, "available");

  // A host that staged the result itself and saved no file: the staged copy is persisted.
  const staged = await beginInWorkspace(t, args);
  await writeFile(path.join(staged.run, "host-results/yt-staged.json"), mcp(youtubeVideo()));
  assert.equal(python("static_host.py", ["stage", "--tool", "youtube_get_video", "--input", "host-results/yt-staged.json"], staged.run).code, 0);
  const fromStage = await driveFrom(staged.run, staged.begun.out, { youtube: null });
  assert.match(fromStage.out, /metadata completed/);

  // An answer that the video is unavailable is persisted as the evidence it is: the build records the metadata as unavailable.
  const failed = await beginInWorkspace(t, args);
  const refused = await driveFrom(failed.run, failed.begun.out, { youtube: youtubeVideo({ status: "failed" }) });
  assert.match(refused.out, /metadata failed/);
  assert.equal((await readJson(path.join(failed.run, "analysis/content_evidence.json"))).content_metadata.status, "unavailable");

  // Nothing saved, an MCP error with no connector evidence, or the Web host's bare failure: one limitation line, and the
  // observation builds and prints the brief all the same.
  for (const [youtube, status, why] of [
    [null, "not_returned", "no result was saved for this call"],
    [JSON.stringify({ isError: true, content: [{ type: "text", text: "rate limited, retry later" }] }), "failed", "MCP error contains no terminal connector evidence: rate limited, retry later"],
    [JSON.stringify({ connector_id: "youtube-public", operation: "get_video", status: "failed", error_code: "upstream_failed" }), "failed", "upstream_failed"],
  ]) {
    const gap = await beginInWorkspace(t, args);
    const done = await driveFrom(gap.run, gap.begun.out, { youtube });
    assert.match(done.out, new RegExp(`metadata ${status}\\.`));
    assert.match(done.out, /# Analysis brief/);
    assert.doesNotMatch(done.out, /^Pass these/m);
    const line = `The post's metadata call (youtube_get_video) brought nothing usable (${why}), so its title, description, tags, cover, publish date and public counts are missing from this analysis.`;
    const evidence = await readJson(path.join(gap.run, "analysis/content_evidence.json"));
    assert.ok(JSON.stringify(evidence).includes(JSON.stringify(line).slice(1, -1)), JSON.stringify(evidence.limitations ?? evidence));
    assert.equal(evidence.content_metadata.status, "not_attempted");
  }
});

test("a YouTube run that already holds its metadata envelope makes no metadata call and builds with it", async (t) => {
  const args = ["--url", YOUTUBE, "--subject-state", "unknown", "--mode", "diagnosis", "--question", "", "--confirmed-by-user", "--duration-s", "30"];
  const run = await newRun(t);
  await writeFile(path.join(run, "snapshot/envelope-01.json"), JSON.stringify(youtubeVideo()));
  const begun = python("begin_analysis.py", args, run);
  assert.equal(begun.code, 0, begun.out);
  assert.deepEqual(callLines(begun.out).map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
  const { out } = await driveFrom(run, begun.out);
  assert.doesNotMatch(out, /metadata (?:completed|failed|not_returned)/);
  assert.match(out, /^Envelopes included: snapshot\/envelope-02\.json, snapshot\/envelope-03\.json, snapshot\/envelope-04\.json, snapshot\/envelope-01\.json$/m);
  assert.match(out, /# Analysis brief/);
});

test("a transcript export builds the evidence at the end of the observation and goes straight to the export", async (t) => {
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "transcript_export", "--confirmed-by-user"]);
  // No brief, so no rules line: the run directory and the credit check are the only lines before observe_video.py's.
  assert.match(begun.out.split("\n")[1], CREDIT_LINE);
  assert.match(begun.out.split("\n")[2], /^Observation source: /);
  const { out } = await driveFrom(run, begun.out);
  assert.match(out, /^Envelopes included: snapshot\/envelope-01\.json$/m);
  assert.match(out, /A transcript export has no brief: now run export_transcript\.py as the Skill says\./);
  assert.match(out, /then export_transcript\.py as the Skill says/);
  const exported = shell(`cd '${run}' && python3 -B '${path.join(scripts, "export_transcript.py")}' analysis/content_evidence.json report/`);
  assert.equal(exported.code, 0, exported.out);
  assert.match(await readFile(path.join(run, "report/transcript.txt"), "utf8"), /Here is why your pan keeps burning/);
});

test("begin_analysis: an attached file and a transcript export need no card, and an unknown link must name its platform", async (t) => {
  const id = uuid(7);
  const run = await newRun(t);
  const begun = python("begin_analysis.py", ["--file-ref", `kabo-file:${id}`, "--platform", "tiktok", "--subject-state", "own_unpublished",
    "--mode", "transcript_export", "--confirmed-by-user"], run);
  assert.equal(begun.code, 0, begun.out);
  assert.deepEqual(callLines(begun.out).map((call) => call.tool), ["collect_video_media"]);
  assert.equal((await readJson(path.join(run, "analysis/video-analysis-request.json"))).source.url, `kabo-file:${id}`);
  assert.deepEqual((await readJson(path.join(run, "analysis/method.json"))).cards, []);
  // A transcript export has no brief, so no rules either.
  assert.equal(existsSync(path.join(run, "analysis/rules.md")), false);
  const unknown = await newRun(t);
  const refused = python("begin_analysis.py", ["--url", "https://example.com/v/1", "--subject-state", "unknown", "--mode", "diagnosis"], unknown);
  assert.equal(refused.code, 1, refused.out);
  assert.match(refused.out, /--platform names the platform of the link/);
});

test("cards first: the pre-fetch selection skips nothing, and the sound card makes the observation combined", async (t) => {
  const run = await newRun(t);
  const method = await selectFirst(run, "sound");
  assert.deepEqual(method.cards.map((card) => [card.id, card.role]), [["diagnosis-default", "base"], ["sound", "topic"]]);
  assert.deepEqual(method.skipped, []);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  assert.equal(first.code, 0, first.out);
  assert.match(first.out, /Observation source: combined \(default order; the sound card adds whole_video; side calls: song\)/);
  // The duration is not known yet: the media call goes first (with the diagnosis's song recognition beside it), and
  // the paid viewing starts once it reports 30 s.
  assert.deepEqual(callLines(first.out).map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
  const { out, handed } = await driveFrom(run, first.out);
  assert.deepEqual(handed.map((call) => call.tool), ["collect_video_media", "identify_video_song", "analyze_content_video", "get_analysis_run"].slice(0, handed.length));
  assert.match(out, /"source": "combined"/);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "diagnosis"], "does the music fit?");
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(section(brief, 2), /Focus: `sound`/);
  assert.match(section(brief, 5), /\(`sound`, topic card/);
  assert.deepEqual((await readJson(path.join(run, "analysis/method.json"))).cards.map((card) => card.id), ["diagnosis-default", "sound"]);

  // Without the sound card the same link observes server frames only.
  const plain = await newRun(t);
  await selectFirst(plain, "opening");
  const framesOnly = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], plain);
  assert.match(framesOnly.out, /Observation source: server_frames \(default order; side calls: song\)/);
  assert.deepEqual(callLines(framesOnly.out).map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
});

test("cards first: a chosen card the evidence cannot support is skipped by prepare_analysis.py, and the brief says so", async (t) => {
  const run = await newRun(t);
  await selectFirst(run, "editing-pacing");
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  const { out } = await driveFrom(run, first.out);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "diagnosis"], "is the pacing too slow?");
  assert.equal(prepared.code, 0, prepared.out);
  const method = await readJson(path.join(run, "analysis/method.json"));
  assert.deepEqual(method.skipped, [{ id: "editing-pacing", reason: "evidence_missing:measure" }]);
  const brief = await readBrief(run);
  assert.match(section(brief, 2), /Focus: `editing-pacing`/);
  assert.match(section(brief, 3), /The requested topic card `editing-pacing` was skipped for missing evidence/);
  // Section 5 is what was asked for before the fetch: the skipped card's text stays, and section 3 says it does not apply.
  assert.match(section(brief, 5), /\(`editing-pacing`, topic card/);
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

test("a video attached in Kabo (kabo-file:<id>) goes to the media tool as its url; the sound card adds a whole-video viewing as for any link", async (t) => {
  const run = await newRun(t);
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  await selectFirst(run, "sound");
  const first = python("observe_video.py", ["--url", `KABO-FILE:${id.toUpperCase()}`, "--mode", "diagnosis"], run);
  assert.equal(first.code, 0, first.out);
  assert.match(first.out, /Observation source: combined/);
  const calls = callLines(first.out);
  // The duration is not known yet: the media call measures the stored file first (no YouTube-style metadata round).
  assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media"]);
  assert.deepEqual(operationsOf(calls[0]), ["fetch_transcript", "extract_keyframes", "measure_media_signals"]);
  for (const request of calls[0].arguments.requests) assert.equal(request.parameters.url, `kabo-file:${id}`);
  await writeFile(slotFiles(first.out)[0], mcp(composite(calls[0].arguments)));
  const started = shell(resumeOf(first.out));
  assert.deepEqual(callLines(started.out).map((call) => call.tool), ["analyze_content_video"], started.out);
  assert.equal(callLines(started.out)[0].arguments.source_url, `kabo-file:${id}`);
  const { out: doneOut } = await driveFrom(run, started.out);
  const done = { out: doneOut };
  assert.match(done.out, /"source": "combined"/);
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

test("SKILL.md: cards are chosen before the observation, the credit check comes before the fetch, and an unsupported link stops the run", async () => {
  const text = await readFile(path.join(skill, "SKILL.md"), "utf8");
  // One setup command, on every host, reserves the run, takes the cards and prints the observation's calls; where
  // start_skill_run exists, its answer (the credit check) comes before the first printed call.
  assert.match(text, /python3 <skill directory>\/scripts\/begin_analysis\.py --workspace '<user-workspace>' --url '<link exactly as given>' --subject-state <chosen-state> --mode <diagnosis\|content_read\|craft_teardown\|transcript_export> --question '<their words, verbatim>' \[--focus <id>\[,<id>\]\] \[--ask identify_track\]/);
  assert.match(text, /On every host the first command, `begin_analysis\.py --workspace` \(analysis step 2\), reserves it; a\s+local file reserves it with:/);
  assert.match(text, /call the Kabo tool `start_skill_run` once right after the run directory is printed/);
  assert.match(text, /`begin_analysis\.py` fetches nothing itself and only prints the observation's calls, so wait for its answer before making any of them, never in the same turn/);
  assert.doesNotMatch(text, /right after `init`|three with it|wait for its answer before `begin_analysis\.py`/);
  assert.ok(text.indexOf("scripts/begin_analysis.py --workspace") < text.indexOf("prepare_analysis.py --run"));
  assert.match(text, /read the rules file it named whole \(sections 5-7 of the brief/);
  assert.match(text, /Setup is one command, `begin_analysis\.py --workspace`, on\s+every host \(then `start_skill_run`, where available, before its printed calls\)\./);
  assert.match(text, /Run it from any directory: it reserves the run and prints its directory first; never pass\s+`--workspace` again for this request\./);
  assert.match(text, /Exit 2 names an argument problem \(a card\s+id, a flag\): correct it once and run the same command again/);
  // The observation's last command builds and prepares; an envelope or per-run flag that comes later means one rebuild.
  assert.match(text, /the\s+same command also runs steps 4 and 5/);
  assert.match(text, /If you persist an envelope after that \(a post row, a baseline\) or a\s+per-run flag applies, run steps 4 and 5 once more/);
  // YouTube's metadata comes from the observation's own hand-over: never a call the model makes beside it.
  assert.doesNotMatch(text, /YouTube metadata, post|on every platform but YouTube|`youtube-public` \/ `get_video`/);
  assert.ok(text.match(/^allowed-tools: (.*)$/m)[1].split(" ").includes("youtube_get_video"));
  assert.match(text, /A file this\s+Skill's `metadata\.preload` lists \(those two and `references\/diagnosis-rules\.md`\) that the host already\s+put in your context needs no read/);
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
  assert.deepEqual(operationsOf(callLines(out)[0]), ["collect_public_metadata", "measure_media_signals"]);
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
  // The diagnosis's song recognition rides along beside the media call.
  assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
  await writeFile(slotFiles(first.out)[0], mcp(noDuration(calls[0].arguments)));
  const done = shell(resumeOf(first.out));
  assert.equal(done.code, 0, done.out);
  assert.match(done.out, /"source": "server_frames"/);
  assert.equal(callLines(done.out).length, 0);
  assert.match(done.out, /Fallback: combined narrowed to server_frames \(duration_unknown\)/);
  assert.match(flagsOf(done.out), /--limitation 'Whole-video viewing not started because the video duration could not be read/);
});

test("duration gate: YouTube reads the duration from its own metadata envelope or from the measurement, and without either no viewing starts", async (t) => {
  const YT = YOUTUBE;
  // The first round measures the file, beside the youtube_get_video call in the same hand-over: no round is added.
  const begin = async () => {
    const run = await newRun(t);
    const first = python("observe_video.py", ["--url", YT, "--mode", "diagnosis", "--observe-source", "whole_video"], run);
    assert.equal(first.code, 0, first.out);
    const calls = callLines(first.out);
    assert.deepEqual(calls.map((call) => call.tool), ["collect_video_media", "youtube_get_video"]);
    assert.deepEqual(operationsOf(calls[0]), ["measure_media_signals"]);
    return { run, first, call: calls[0], file: slotFiles(first.out)[0], metadata: slotFiles(first.out)[1] };
  };

  // The metadata call's answer is persisted on the resume, before the gate reads the duration from it.
  const persisted = await begin();
  await writeFile(persisted.metadata, mcp(youtubeVideo({ duration: 45 })));
  await writeFile(persisted.file, mcp(composite(persisted.call.arguments)));
  const resumed = shell(resumeOf(persisted.first.out));
  assert.deepEqual(callLines(resumed.out).map((call) => call.tool), ["analyze_content_video"], resumed.out);
  assert.equal(callLines(resumed.out)[0].arguments.source_url, YT);

  // youtube_get_video answered unsupported (the provider's quota): the measurement's duration starts the viewing.
  const measured = await begin();
  await writeFile(measured.metadata, mcp(youtubeVideo({ status: "unsupported" })));
  await writeFile(measured.file, mcp(composite(measured.call.arguments, { measuredDuration: 41.5 })));
  const started = shell(resumeOf(measured.first.out));
  assert.deepEqual(callLines(started.out).map((call) => call.tool), ["analyze_content_video"], started.out);
  assert.match(started.out, /runs 41\.5s, within the whole-video limit/);
  await writeFile(slotFiles(started.out)[0], mcp(viewerFixture));
  const done = shell(resumeOf(started.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.match(done.out, /"status": "observed"/, done.out);
  assert.match(flagsOf(done.out), /--duration-s 41\.5/);
  const made = python("prepare_link_request.py", ["--url", YT, "--platform", "youtube", "--subject-state", "unknown", "--mode", "diagnosis",
    "--confirmed-by-user"], measured.run);
  assert.equal(made.code, 0, made.out);
  // A relative --output still names the run: the request id is the run directory's name, so no id ends in "-unknown".
  assert.equal((await readJson(path.join(measured.run, "analysis/video-analysis-request.json"))).request_id, path.basename(measured.run));
  const built = build(measured.run, flagsOf(done.out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(measured.run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.deepEqual([evidence.media.duration_s, evidence.media.duration_source], [41.5, "connector_measure"]);
  assert.equal(evidence.transcript.source_connector, "kabo-video-analysis");
  // With the duration known, a whole-video run gets a hook window by the video's length, and the promise is anchored.
  assert.equal((await prepare(measured.run, ["--mode", "diagnosis"])).code, 0);
  const promise = await readJson(path.join(measured.run, "analysis/promise_payoff.json"));
  assert.deepEqual([promise.hook_window_s, promise.hook_window_basis, promise.promise.status], [3, "video_length", "located"]);

  // Neither: the viewing is refused at once and server frames take over. No round is handed over just to wait for
  // the metadata (KS9).
  const bare = await begin();
  await writeFile(bare.file, mcp(composite(bare.call.arguments)));
  const fell = shell(resumeOf(bare.first.out));
  assert.doesNotMatch(fell.out, /starts only once the video's duration is known/);
  assert.match(fell.out, /whole_video returned no usable evidence \(duration_unknown\)/);
  assert.match(fell.out, /trying server_frames/);
  assert.deepEqual(callLines(fell.out).map((call) => call.tool), ["collect_video_media"]);
  // The measurement was already asked for under this run key: only the rest is asked now.
  assert.deepEqual(operationsOf(callLines(fell.out)[0]), ["fetch_transcript", "extract_keyframes"]);
});

test("duration gate: Instagram metadata carries no duration, so the forced viewing's media call measures and the viewing starts", async (t) => {
  const IG = "https://www.instagram.com/reel/DAbCdEfGhIj/";
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", IG, "--mode", "diagnosis", "--observe-source", "whole_video"], run);
  const [call] = callLines(first.out);
  assert.deepEqual(operationsOf(call), ["collect_public_metadata", "measure_media_signals"]);
  // The metadata answers with duration_seconds null, as Instagram's does; the measurement reports 23.3s.
  await writeFile(slotFiles(first.out)[0], mcp(composite(call.arguments, { duration: null, measuredDuration: 23.3 })));
  const started = shell(resumeOf(first.out));
  assert.deepEqual(callLines(started.out).map((item) => item.tool), ["analyze_content_video"], started.out);
});

test("a duration given with --duration-s reaches media.duration_s on a whole-video-only run", async (t) => {
  const YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
  const { run, out, handed } = await observe(t, "whole_video", { url: YT, args: ["--duration-s", "45"], youtube: null });
  // Known up front: no measurement is needed, and nothing but the viewing and the post's metadata is called.
  assert.deepEqual(handed.map((call) => call.tool), ["analyze_content_video", "youtube_get_video"]);
  assert.match(flagsOf(out), /--duration-s 45/);
  assert.equal(python("prepare_link_request.py", ["--url", YT, "--platform", "youtube", "--subject-state", "unknown", "--mode", "diagnosis",
    "--confirmed-by-user"], run).code, 0);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.deepEqual([evidence.media.duration_s, evidence.media.duration_source], [45, "host_supplied"]);
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
  const brief = await readBrief(run);
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

// End-to-end findings: what real runs of this Skill tripped over, pinned so they stay fixed.
// The builder never overwrites its outputs; a rebuild in the same run clears them first.
async function rebuild(run, flags) {
  for (const name of ["content_evidence.json", "content_evidence.references.json"]) await rm(path.join(run, "analysis", name), { force: true });
  return build(run, flags);
}
async function envelopeFlags(run, out, keep = () => true) {
  const files = flagsOf(out).split(" ").filter((word) => word.startsWith("snapshot/envelope-"));
  const kept = [];
  for (const file of files) if (keep(await readJson(path.join(run, file)))) kept.push(`--envelope ${file}`);
  return kept.join(" ");
}

test("frame reads come in chunks of at most 15 object refs, so a host shows every image", async (t) => {
  const frameTimes = Array.from({ length: 32 }, (_, i) => i * 0.9);
  const { out } = await observe(t, null, { frameTimes });
  const reads = out.split("\n").filter((line) => line.startsWith("read: ")).map((line) => JSON.parse(line.slice(6)));
  assert.equal(reads.length, 3, out);
  for (const read of reads) {
    assert.equal(read.tool, "read_research_data_artifacts");
    assert.ok(read.arguments.object_refs.length <= 15);
    // Read inline: no delivery, so the host shows the images instead of a link it cannot save.
    assert.equal(read.arguments.delivery, undefined);
  }
  assert.equal(new Set(reads.flatMap((read) => read.arguments.object_refs)).size, 32);
  assert.match(out, /make these 3 reads now/);
});

test("prepare_link_request --url: mode defaults, an unresolved short link keeps a null id, a wrong platform is refused", async (t) => {
  const run = await newRun(t);
  const make = (args, name) => python("prepare_link_request.py", [...args, "--output", path.join(run, "analysis", name)], run);
  const made = make(["--url", TIKTOK, "--platform", "tiktok", "--subject-state", "unknown", "--mode", "content_read", "--confirmed-by-user"], "a.json");
  assert.equal(made.code, 0, made.out);
  const request = await readJson(path.join(run, "analysis/a.json"));
  assert.deepEqual([request.source.acquisition, request.source.url, request.source.content_id, request.budget.max_connector_calls,
    request.acquire.owner_metrics, request.baseline ?? null], ["public_url", TIKTOK, "7300000000000000001", 8, "skip", null]);
  const own = make(["--url", TIKTOK, "--platform", "tiktok", "--subject-state", "own_published", "--mode", "diagnosis"], "b.json");
  assert.equal(own.code, 0, own.out);
  assert.equal((await readJson(path.join(run, "analysis/b.json"))).budget.max_connector_calls, 15);
  const short = make(["--url", "https://www.tiktok.com/t/ZTfCHqHy2/", "--platform", "tiktok", "--subject-state", "unknown", "--mode", "diagnosis"], "c.json");
  assert.equal(short.code, 0, short.out);
  assert.equal((await readJson(path.join(run, "analysis/c.json"))).source.content_id, null);
  assert.match(make(["--url", TIKTOK, "--platform", "instagram", "--subject-state", "unknown", "--mode", "diagnosis"], "d.json").out, /is a tiktok link/);
  assert.notEqual(make(["--url", TIKTOK, "--platform", "tiktok", "--subject-state", "unknown"], "e.json").code, 0);
  assert.equal(make(["--url", TIKTOK, "--platform", "tiktok", "--subject-state", "unknown", "--max-connector-calls", "4"], "f.json").code, 0);
});

test("evidence: compact upload dates become ISO; an unresolved short link builds with a null id; tiktok_search_get_video is metadata", async (t) => {
  const { run, out } = await observe(t, null);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const dated = await readJson(path.join(run, "analysis/content_evidence.json"));
  assert.equal(dated.content_ref.published_at, "2026-11-01");

  // A short link nobody resolved, and no metadata result: the id stays null instead of failing the build.
  const SHORT = "https://www.tiktok.com/t/ZTfCHqHy2/";
  await rm(path.join(run, "analysis/video-analysis-request.json"));
  assert.equal(python("prepare_link_request.py", ["--url", SHORT, "--platform", "tiktok", "--subject-state", "unknown", "--mode", "diagnosis",
    "--confirmed-by-user", "--output", path.join(run, "analysis/video-analysis-request.json")], run).code, 0);
  const media = await envelopeFlags(run, out, (envelope) => envelope.operation !== "collect_public_metadata");
  const bare = await rebuild(run, media);
  assert.equal(bare.code, 0, bare.out);
  const unresolved = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(unresolved);
  assert.equal(unresolved.content_ref.content_id, null);
  assert.match(unresolved.evidence_id, /^ev-tt-unresolved-[0-9a-f]{12}$/);
  assert.equal(unresolved.audio_attribution, undefined);
  const refs = await readJson(path.join(run, "analysis/content_evidence.references.json"));
  assert.doesNotMatch(JSON.stringify(refs), /audio_attribution/);

  // The TikTok search row names the video, its counts, caption, hashtags and declared sound.
  await writeFile(path.join(run, "snapshot/envelope-09.json"), JSON.stringify({
    schema_version: "1.0", connector_id: "tiktok-search", operation: "get_video", provider: "fixture", status: "completed",
    summary: "ok", limitations: [], credential_values_recorded: false, request_id: "req-tt", retrieved_at: "2026-11-16T00:00:00Z",
    raw_sha256: "d".repeat(64), observation_refs: [], evidence_ref: "ev-tt",
    data: { video: { aweme_id: "7183729178263473414", desc: "Best detergent #dishwasher #CleanTok", create_time: 1672592291,
      statistics: { play_count: 477554, digg_count: 32322, comment_count: 1791 }, author: { unique_id: "laundry" },
      video: { duration: 30000 }, text_extra: [{ type: 1, hashtag_name: "dishwasher" }, { type: 1, hashtag_name: "cleantok" }],
      music: { id_str: "7183729185767066374", is_original_sound: true, author: "Laundry", title: "original sound - laundry" } } } }));
  const full = await rebuild(run, `${media} --envelope snapshot/envelope-09.json`);
  assert.equal(full.code, 0, full.out);
  const tiktok = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(tiktok);
  assert.equal(tiktok.content_ref.content_id, "7183729178263473414");
  assert.equal(tiktok.content_ref.published_at, "2023-01-01T16:58:11Z");
  assert.equal(tiktok.content_metadata.status, "available");
  assert.equal(tiktok.content_metadata.caption, "Best detergent #dishwasher #CleanTok");
  assert.deepEqual(tiktok.content_metadata.tags, ["dishwasher", "cleantok"]);
  assert.deepEqual(tiktok.public_metrics.map((metric) => [metric.native_name, metric.value]),
    [["view_count", 477554], ["like_count", 32322], ["comment_count", 1791]]);
  assert.equal(tiktok.audio_attribution.uses_original_audio, true);
  assert.match(JSON.stringify(await readJson(path.join(run, "analysis/content_evidence.references.json"))), /audio_attribution\.uses_original_audio/);
});

test("the brief's Sound lines: attribution unavailable, sound markers in the cues, and whether music and mix were analysed", async (t) => {
  const { run, out } = await observe(t, null);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const file = path.join(run, "analysis/content_evidence.json");
  const evidence = await readJson(file);
  evidence.transcript.cues[1].text = "[Music] here is why ♪";
  await writeFile(file, JSON.stringify(evidence));
  assert.equal((await prepare(run, ["--mode", "content_read"], "what does it say?")).code, 0);
  const brief = await readBrief(run);
  const sound = brief.slice(brief.indexOf("### Sound"), brief.indexOf("### Frames"));
  assert.match(sound, /`audio_attribution` unavailable/);
  assert.match(sound, /`transcript\.cue\[1\]` \[Music\] ♪/);
  assert.match(sound, /Music and mix: neither measured nor heard/);
  assert.match(section(brief, 7), /When `audio_attribution` is unavailable, decide from what the run has: sound markers/);
  assert.match(section(brief, 6), /Say no more than the cited evidence shows/);
  assert.match(section(brief, 6), /English when there are none/);
  assert.match(section(brief, 5), /a transcript says nothing about them/);
});

test("content read and craft teardown close the judge stage and record the answer's length", async (t) => {
  const { run, out } = await observe(t, null, { mode: "content_read" });
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  assert.equal((await prepare(run, ["--mode", "content_read"], "what is he doing?")).code, 0);
  assert.notEqual(python("acv_timing.py", ["answer", "--run", run, "--answer", "analysis/answer.md"], run).code, 0);
  await writeFile(path.join(run, "analysis/answer.md"), "He burns the pan at 0:00, then explains why.\n");
  const recorded = python("acv_timing.py", ["answer", "--run", run, "--answer", "analysis/answer.md"], run);
  assert.equal(recorded.code, 0, recorded.out);
  const timing = await readJson(path.join(run, "analysis/timing.json"));
  assert.deepEqual(timing.stages.map((stage) => stage.stage), ["observe", "prepare", "judge"]);
  assert.equal(timing.reply.chars, "He burns the pan at 0:00, then explains why.".length);
  assert.ok(timing.reply.total_ms >= 0);
  assert.notEqual(python("acv_timing.py", ["answer", "--run", run, "--answer", "../outside.md"], run).code, 0);
});

const JUDGMENT = { observations: [{ observation_id: "obs-1", dimension: "first_frame_promise", t_start_s: 0, t_end_s: 0,
  statement: "The burnt pan is in the first frame.", basis: "frame", evidence_refs: ["frame-0001"], confidence: "medium" }],
  evidence_completeness: { account_baseline: "unavailable" } };
function creatorView({ long = false, decision = "borrow" } = {}) {
  const card = (title) => ({ title, why_for_you: "First line\nSecond line\nThird line", action: "Keep the result first.",
    evidence_refs: ["observations.obs-1"] });
  const second = card("What you would inherit");
  if (long) second.why_for_you = `${"x".repeat(479)}\nSecond line\nThird line`;
  const third = { ...card("What to do in yours"), hooks: [{ purpose: "Open on the result", visual_direction: "The burnt pan, close up",
    on_screen_text: "Why does this keep happening?" }] };
  return { decision, creator_view: { language: "en", headline: "The result comes first", summary: "The pan opens the video.",
    cards: [card("What works"), second, third], next_actions: ["Film your own result shot."] } };
}

test("finish_diagnosis --check lists every view violation and writes nothing; a failed finish leaves no report", async (t) => {
  const { run, out } = await observe(t, null);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  assert.equal((await prepare(run, ["--mode", "diagnosis"], "")).code, 0);
  await writeFile(path.join(run, "analysis/video_judgment.json"), JSON.stringify(JUDGMENT));
  const contract = JSON.parse(python("build_creator_result.py", ["--print-view-contract", "--observations-from", "analysis/video_judgment.json"], run).out);
  assert.deepEqual(Object.keys(contract.document.decision.allowed), ["borrow", "skip"]);
  assert.equal(contract.display_column_limits["cards[].why_for_you"], 480);
  assert.equal(contract.creator_view.cards.why_for_you.max_display_columns, 480);
  assert.match(contract.creator_view.cards.hooks.fields.time_range, /"4\.03–6\.13s"/);
  assert.match(contract.creator_view.language, /English|en when there are none/);

  await writeFile(path.join(run, "analysis/creator_view.json"), JSON.stringify(creatorView({ long: true, decision: "recut" })));
  const checked = python("finish_diagnosis.py", ["--run-dir", run, "--check"], run);
  // needs_correction exits 3, so `--check && finish` never finishes an uncorrected view.
  assert.equal(checked.code, 3, checked.out);
  const verdict = JSON.parse(checked.out.slice(0, checked.out.lastIndexOf("}") + 1));
  assert.equal(verdict.status, "needs_correction");
  assert.ok(verdict.violations.some((line) => /why_for_you runs \d+ columns against a 480 limit/.test(line)), checked.out);
  assert.ok(verdict.violations.some((line) => /details\.decision is 'recut'; for this video it is one of borrow, skip/.test(line)), checked.out);
  assert.equal(existsSync(path.join(run, "report/VIDEO_DIAGNOSIS.md")), false);
  assert.equal(existsSync(path.join(run, "analysis/creator-task-result.json")), false);
  assert.ok(!(await readJson(path.join(run, "analysis/timing.json"))).stages.some((stage) => stage.stage === "validate"));

  // --finish-if-ready finishes nothing while the view still needs its correction.
  const notYet = python("finish_diagnosis.py", ["--run-dir", run, "--check", "--finish-if-ready"], run);
  assert.equal(notYet.code, 3, notYet.out);
  assert.match(notYet.out, /"status": "needs_correction"/);
  assert.equal(existsSync(path.join(run, "report/VIDEO_DIAGNOSIS.md")), false);

  const failed = python("finish_diagnosis.py", ["--run-dir", run], run);
  assert.notEqual(failed.code, 0);
  assert.match(failed.out, /no report was written/);
  assert.equal(existsSync(path.join(run, "report/VIDEO_DIAGNOSIS.md")), false);
  assert.deepEqual((await readdir(path.join(run, "report"))).filter((name) => !name.startsWith("transcript")), []);

  await writeFile(path.join(run, "analysis/creator_view.json"), JSON.stringify(creatorView()));
  const ready = python("finish_diagnosis.py", ["--run-dir", run, "--check"], run);
  assert.equal(ready.code, 0, ready.out);
  assert.match(ready.out, /"status": "ready"/);
  assert.match(python("finish_diagnosis.py", ["--help"], run).out, /3 is\s+needs_correction/);
  // Ready: the same call finishes and prints exactly what the final step prints, nothing of the check's own.
  const finished = python("finish_diagnosis.py", ["--run-dir", run, "--check", "--finish-if-ready"], run);
  assert.equal(finished.code, 0, finished.out);
  assert.doesNotMatch(finished.out, /"status": "ready"|Run the final step now/);
  const report = await readFile(path.join(run, "report/VIDEO_DIAGNOSIS.md"), "utf8");
  assert.ok(finished.out.includes(report + `creator_report: ${path.join(run, "report/VIDEO_DIAGNOSIS.md")}\n`), finished.out);
  assert.match(report, /- \*\*On screen\*\*: Why does this keep happening\?/);
  assert.match(report, /- \*\*Shot\*\*: The burnt pan, close up/);
  assert.match(report, /\*\*How to avoid it\*\*: Keep the result first\./);
  assert.match(finished.out, /leave them, and every file path, out of the reply/);
  // The host reads the line after creator_report: an English view renders whole, so the report goes as it is.
  assert.match(finished.out, /\ncreator_report: [^\n]+VIDEO_DIAGNOSIS\.md\nreport_delivery: as_is\nYour reply is this report/);
  const timing = await readJson(path.join(run, "analysis/timing.json"));
  assert.equal(timing.reply.file, "report/VIDEO_DIAGNOSIS.md");
  assert.equal(timing.reply.chars, report.trim().length);
});

test("the report keeps a non-zero tenth of a second: a measured 0.4s is not printed as 0:00", () => {
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
from render_video_report import timecode, format_time_range, prose_timecodes
print(json.dumps([timecode(0.4), timecode(4.017), timecode(15.207), timecode(4.9999), timecode(61.0),
                  format_time_range("0.000–4.017s"), prose_timecodes("sound from 0.4s", {0.4})]))
`;
  const result = spawnSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" });
  // Rounded to the tenth shown: 4.9999s is 0:05, not a truncated 0:04.9.
  assert.deepEqual(JSON.parse(result.stdout), ["0:00.4", "0:04", "0:15.2", "0:05", "1:01", "[0:00–0:04]", "sound from [0:00.4]"]);
});

// Findings of the observation bake-off: what each source returned, honestly read.
const viewerWith = ({ dimensions, transcript = viewerFixture.transcript }) =>
  ({ ...viewerFixture, result: { ...viewerFixture.result, dimensions }, transcript });
async function evidenceFrom(t, { envelopes, viewer, request = {} }) {
  const run = await newRun(t);
  await writeRequest(run, request);
  const flags = [];
  for (const [index, envelope] of envelopes.entries()) {
    const file = path.join(run, `snapshot/envelope-${String(index + 1).padStart(2, "0")}.json`);
    await writeFile(file, JSON.stringify(envelope));
    flags.push(`--envelope ${file}`);
  }
  if (viewer) {
    await writeFile(path.join(run, "host-results/viewer.json"), mcp(viewer));
    flags.push(`--viewer ${path.join(run, "host-results/viewer.json")}`);
  }
  const built = build(run, flags.join(" "));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  return { run, evidence };
}
const measureEnvelope = (duration, cuts = [5.03]) => ({ ...mediaEnvelope("measure_media_signals", uuid(4)),
  data: { shots: { count: cuts.length + 1, cuts_at_s: cuts }, artifacts: [], duration_s: duration } });
const transcriptEnvelope = (cues, extra = {}) => ({ ...mediaEnvelope("fetch_transcript", uuid(2), { cues }), ...extra });

test("a gone video: every source empty prints source_unavailable and no build arguments, and a brief from no evidence is refused with the stop rule", async (t) => {
  const { out } = await observe(t, null, {
    mediaFailed: "all", viewerSteps: [JSON.stringify({ code: "not_found", message: "The video could not be fetched.", retryable: false })] });
  assert.match(out, /"status": "source_unavailable"/);
  assert.doesNotMatch(out, /"status": "observed"/);
  assert.doesNotMatch(out, /Pass these to build_content_evidence\.py/);
  assert.match(out, /Follow \*Stops and gaps\* in the Skill/);
  // Built anyway (a host that went on): the brief is refused, pointing to the stop rule.
  const empty = transcriptEnvelope([], { status: "completed_partial", data: { cues: [], artifacts: [], cue_count: 0 } });
  const { run } = await evidenceFrom(t, { envelopes: [empty, { ...mediaEnvelope("extract_keyframes", uuid(3)), status: "completed_partial",
    data: { frames: [], artifacts: [], selection: "none", frame_count: 0 } }] });
  const refused = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(refused.code, 2, refused.out);
  assert.match(refused.out, /"status": "refused"/);
  assert.match(refused.out, /Stops and gaps/);
  assert.equal(existsSync(path.join(run, "analysis/brief.md")), false);
});

test("a refused download: frames and words empty but the post's metadata in, the run answers from the metadata and never calls the video deleted or private", async (t) => {
  const { run, out } = await observe(t, null, {
    mediaFailed: true, viewerSteps: [JSON.stringify({ code: "not_found", message: "The video could not be fetched.", retryable: false })] });
  assert.match(out, /"status": "metadata_only"/);
  assert.doesNotMatch(out, /Follow \*Stops and gaps\*/);
  assert.doesNotMatch(out, /deleted, made private/);
  assert.match(out, /never say the video is deleted, private or unavailable/);
  const flags = allFlags(out);
  assert.match(flags, /--limitation 'media_not_fetched: the platform did not let Kabo download/);
  await writeRequest(run);
  const built = build(run, flags);
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.content_metadata.status, "available");
  const prepared = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(brief, /### Picture and sound not fetched\n\n- media_not_fetched:/);
  assert.match(brief, /The video is not deleted or private/);
});

test("a refused download as the backend reports it: frames completed_partial and empty, the transcript failed, the metadata complete", async (t) => {
  const blocked = (args) => {
    const value = composite(args);
    for (const call of value.calls) {
      const op = call.result.operation;
      if (op === "extract_keyframes") {
        call.result.status = "completed_partial";
        call.result.data = { frame_count: 0, selection: "none", duration_s: null, sampling_plan: null, frames: [], artifacts: [] };
      } else if (op === "fetch_transcript") {
        call.result = { ...call.result, status: "failed", data: undefined, limitations: ["The audio could not be retrieved."] };
      }
    }
    return value;
  };
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", "https://www.bilibili.com/video/BV1V9W96uEVa", "--mode", "craft_teardown"], run);
  assert.equal(first.code, 0, first.out);
  const { out } = await driveWith(run, first.out, { media: blocked,
    viewerSteps: [JSON.stringify({ code: "unsupported_source", message: "This source is not supported.", retryable: false })] });
  assert.match(out, /"status": "metadata_only"/);
});

test("a limitation recorded twice in one observation is passed to the builder once", async (t) => {
  const { out } = await observe(t, null, { afterRound: async (dir) => {
    const file = path.join(dir, "observe-video.json");
    const state = await readJson(file);
    state.limitations = ["The source could not be fetched.", "The source could not be fetched."];
    await writeFile(file, JSON.stringify(state));
  } });
  assert.equal(flagsOf(out).split("--limitation 'The source could not be fetched.'").length, 2, flagsOf(out));
});

test("whole-video notes past the end are dropped and named, with the minutes-read-as-seconds pattern; the brief flags notes beside measured cuts", async (t) => {
  const { run, evidence } = await evidenceFrom(t, {
    envelopes: [measureEnvelope(417.5, [5.03, 126.8])],
    viewer: viewerWith({ dimensions: [
      { key: "hook", score: 1, summary: "x", evidence: [{ startMs: 4000, endMs: 9000, note: "The sketch becomes the finished drawing." }] },
      { key: "Audio Integration", score: 1, summary: "x", evidence: [{ startMs: 0, endMs: 30000, note: "A soft piano track runs under the voice." }] },
      { key: "payoff", score: 1, summary: "x", evidence: [{ startMs: 209000, endMs: 215000, note: "The planet appears." },
        { startMs: 637000, endMs: 640000, note: "The final image." }, { startMs: 658000, endMs: 660000, note: "End card." }] },
    ] }) });
  const ids = evidence.viewer_observations.items.map((item) => item.start_ms);
  assert.deepEqual(ids, [0, 4000, 209000]);
  const line = evidence.limitations.find((text) => /start after the end of this 417\.5s video and were dropped/.test(text));
  assert.ok(line, evidence.limitations.join("\n"));
  assert.match(line, /minutes:seconds read as seconds \(637s as 6:37, 658s as 6:58\)/);
  assert.match(line, /No time was converted/);
  assert.equal((await prepare(run, ["--mode", "diagnosis"])).code, 0);
  const brief = await readBrief(run);
  assert.match(brief, /The sketch becomes the finished drawing\. \(measured cut at 5\.03s, 1\.03s after the note's start\)/);
  // An "Audio Integration" note is heard sound.
  assert.match(brief, /Music and mix evidence: whole-video sound note `V01`/);
  assert.doesNotMatch(brief, /neither measured nor heard/);
});

test("transcript sources: a lone invented line over music is flagged against the viewer's silence and never anchors the promise", async (t) => {
  const { run, evidence } = await evidenceFrom(t, {
    envelopes: [measureEnvelope(20), transcriptEnvelope([{ text: "Thanks for watching!", start_ms: 1000, end_ms: 2000 }])],
    viewer: viewerWith({ dimensions: viewerFixture.result.dimensions, transcript: [] }) });
  assert.equal(evidence.transcript.source_connector, "public-video-media");
  assert.deepEqual(evidence.transcript.suspect_cues, [{ index: 0, reason: "generic_line" }]);
  assert.deepEqual(evidence.transcript.sources.map((item) => [item.source, item.used]), [["fetched", true], ["whole_video_viewer", false]]);
  assert.ok(evidence.transcript.conflicts.some((text) => /while the whole-video viewer heard no words/.test(text)), evidence.transcript.conflicts);
  assert.equal((await prepare(run, ["--mode", "diagnosis"])).code, 0);
  const promise = await readJson(path.join(run, "analysis/promise_payoff.json"));
  assert.equal(promise.promise.status, "unavailable");
  assert.match(promise.promise.reason, /cue 0 there is a sound marker or a line speech recognition invents/);
  const brief = await readBrief(run);
  assert.match(brief, /- Fetched transcript \(kept\): available, 1 cues/);
  assert.match(brief, /- Whole-video viewer's transcript \(not kept\): no_speech_heard, 0 cues/);
  assert.match(brief, /On-screen text in the frames: yours to read/);
  assert.match(brief, /- Conflict: The fetched transcript holds 1 cue\(s\)/);
  assert.match(brief, /`transcript\.cue\[0\]` 1s: Thanks for watching! \[no evidence of speech: generic line/);
});

test("transcript sources: a marker-only fetched transcript gives way to the viewer's words, and its stale no-transcript line is gone", async (t) => {
  const empty = transcriptEnvelope([{ text: "[Music]", start_ms: 0, end_ms: 9000 }], {
    status: "completed_partial", limitations: ["This video exposes no subtitle track; no transcript was retrieved this run. Do not substitute prior knowledge."] });
  const { evidence } = await evidenceFrom(t, { envelopes: [measureEnvelope(30), empty], viewer: viewerFixture });
  assert.equal(evidence.transcript.source_connector, "kabo-video-analysis");
  assert.match(evidence.transcript.status_basis, /held only sound markers or generic lines/);
  assert.equal(evidence.transcript.cues[0].text, "I ruined it again.");
  assert.ok(!evidence.limitations.some((text) => /no transcript was retrieved/.test(text)), evidence.limitations.join("\n"));
  assert.ok(evidence.limitations.some((text) => /the transcript here is the one the whole-video viewer heard/.test(text)));
});

test("transcript sources: disagreeing words, another language and cues past the end are each named", async (t) => {
  const dutch = [{ text: "Dit is het verhaal van een man die niet wist wat hij moest doen, maar ook dat was voor niets", start_ms: 0, end_ms: 4000 },
    { text: "En dat is het einde van dit verhaal voor nu", start_ms: 40000, end_ms: 42000 }];
  const { evidence } = await evidenceFrom(t, { envelopes: [measureEnvelope(30), transcriptEnvelope(dutch, { data: { cues: dutch, origin: "platform_captions", language: "nl", cue_count: 2, artifacts: [] } })],
    viewer: viewerFixture });
  const conflicts = evidence.transcript.conflicts.join("\n");
  assert.match(conflicts, /disagree \(about \d+% shared words\)/);
  assert.match(conflicts, /reads as nl while the whole-video viewer heard en/);
  assert.match(conflicts, /cue\[1\] is after the end of the video \(30s\)/);
  assert.deepEqual(evidence.transcript.suspect_cues, [{ index: 1, reason: "past_end" }]);
  assert.equal(evidence.transcript.sources[0].detected_language, "nl");
});

test("a whole-video failure a host saved as plain text is read as that failure; an input refusal repeats the start without the new inputs", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  const calls = callLines(first.out), files = slotFiles(first.out);
  await writeFile(files[0], "MCP error -32602: Input validation error: Invalid arguments for tool analyze_content_video: unrecognized key wait_s");
  await writeFile(files[1], mcp(composite(calls[1].arguments)));
  const retried = shell(resumeOf(first.out));
  assert.equal(retried.code, 0, retried.out);
  assert.deepEqual(callLines(retried.out), [{ tool: "analyze_content_video", arguments: { source_url: TIKTOK, idempotency_key: calls[0].arguments.idempotency_key } }]);
  const probe = `
import json, sys
sys.path.insert(0, sys.argv[1])
import viewer_response
print(json.dumps(viewer_response.read(b"MCP error -32603: subscription_required: an active Pro subscription is required")["error"]))
`;
  const read = JSON.parse(spawnSync("python3", ["-I", "-B", "-c", probe, scripts], { encoding: "utf8" }).stdout);
  assert.equal(read.code, "subscription_required");
});

// Frame sampling, one rule on both ends: the keyframes request asks for the contract's 120 frames, a frame just
// after each cut, the dense windows the selected method cards name (analysis/method.json `frames`), and the default
// window, the first 50 seconds every 0.5s.
const DEFAULT_WINDOW = { start_s: 0, end_s: 50, interval_s: 0.5 };
const keyframesOf = (call) => call.arguments.requests.find((request) => request.operation === "extract_keyframes").parameters;
const pinnedKeyframes = JSON.parse(readFileSync(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools
  .find((tool) => tool.name === "public_video_extract_keyframes");

test("keyframes request: the contract's max_frames, shot starts and the default window by default, and the opening card's dense window", async (t) => {
  assert.equal(pinnedKeyframes.inputSchema.properties.parameters.properties.max_frames.maximum, 120);
  const plain = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], plain);
  assert.deepEqual(keyframesOf(callLines(first.out)[0]),
    { url: TIKTOK, sampling: "duration_scaled", max_frames: 120, include_shot_starts: true, dense_windows: [DEFAULT_WINDOW],
      overview: true, quick_above_s: 180 });

  const run = await newRun(t);
  const method = await selectFirst(run, "opening,editing-pacing");
  assert.deepEqual(method.frames, { include_shot_starts: true, dense_windows: [{ start_s: 0, end_s: 5, interval_s: 0.25 }] });
  const out = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run).out;
  const call = callLines(out)[0];
  // The card's window first, then the default one.
  assert.deepEqual(keyframesOf(call), { url: TIKTOK, sampling: "duration_scaled", max_frames: 120, include_shot_starts: true,
    dense_windows: [{ start_s: 0, end_s: 5, interval_s: 0.25 }, DEFAULT_WINDOW], overview: true, quick_above_s: 180 });
  // The options are fixed at the first hand-over, so a repeated call while jobs run sends the same arguments.
  assert.deepEqual((await readJson(path.join(run, "collect-media.json"))).frame_options,
    { include_shot_starts: true, dense_windows: [{ start_s: 0, end_s: 5, interval_s: 0.25 }, DEFAULT_WINDOW], overview: true });

  // Merged with the cards' windows, the request never carries more than three: a card window the default already
  // covers is left out, a repeat is dropped, and past the limit the later card windows go, never the default.
  const merge = (windows) => JSON.parse(spawnSync("python3", ["-I", "-B", "-c", `
import json, sys
sys.path.insert(0, sys.argv[1])
import select_method
print(json.dumps(select_method.with_default_window(json.loads(sys.argv[2]))))
`, path.join(skill, "scripts"), JSON.stringify(windows)], { encoding: "utf8" }).stdout);
  const late = { start_s: 60, end_s: 70, interval_s: 0.5 }, later = { start_s: 80, end_s: 90, interval_s: 0.25 };
  const opening = { start_s: 0, end_s: 5, interval_s: 0.25 }, covered = { start_s: 10, end_s: 20, interval_s: 1 };
  assert.deepEqual(merge([]), [DEFAULT_WINDOW]);
  assert.deepEqual(merge([covered]), [DEFAULT_WINDOW]);
  assert.deepEqual(merge([opening, opening]), [opening, DEFAULT_WINDOW]);
  assert.deepEqual(merge([opening, covered, late, later]), [opening, late, DEFAULT_WINDOW]);
  assert.deepEqual(merge([{ start_s: 40, end_s: 60, interval_s: 0.5 }]), [{ start_s: 40, end_s: 60, interval_s: 0.5 }, DEFAULT_WINDOW]);

  // A transcript export takes no frames, and a card hint outside the request's limits is refused by the library.
  const exportRun = await newRun(t);
  assert.deepEqual((await selectFirst(exportRun, null, "transcript_export")).frames, { include_shot_starts: false, dense_windows: [] });
  const library = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-library-"));
  t.after(() => rm(library, { recursive: true, force: true }));
  const index = JSON.parse(readFileSync(path.join(skill, "references/video-method/index.json"), "utf8"));
  for (const card of index.cards) await writeFile(path.join(library, card.file), readFileSync(path.join(skill, "references/video-method", card.file)));
  index.cards.find((card) => card.id === "opening").frames = { dense_windows: [{ start_s: 0, end_s: 5, interval_s: 0.1 }] };
  await writeFile(path.join(library, "index.json"), JSON.stringify(index));
  const refused = python("select_method.py", ["--mode", "diagnosis", "--focus", "opening", "--out", "m.json", "--library", library], exportRun);
  assert.equal(refused.code, 1);
  assert.match(refused.out, /frame hint/);
});

const FRAME_OPTIONS_REJECTED = JSON.stringify({ isError: true, content: [{ type: "text",
  text: "MCP error -32602: Input validation error: Invalid arguments for tool collect_video_media: Unrecognized key: \"include_shot_starts\"" }] });

test("a server refusing the frame options (keyframes item validation_error, or -32602): the media call is repeated without overview, then without the rest, and the run says so", async (t) => {
  const run = await newRun(t);
  await selectFirst(run, "opening");
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  const [call] = callLines(first.out);
  assert.equal(keyframesOf(call).include_shot_starts, true);
  assert.equal(keyframesOf(call).overview, true);
  await writeFile(slotFiles(first.out)[0], FRAME_OPTIONS_REJECTED);
  const retried = shell(resumeOf(first.out));
  assert.equal(retried.code, 0, retried.out);
  // The newest option goes alone first: a server that knows shot starts and windows keeps them.
  const { overview: _overview, ...withoutOverview } = keyframesOf(call);
  assert.deepEqual(keyframesOf(callLines(retried.out)[0]), withoutOverview);
  assert.equal((await readJson(path.join(run, "collect-media.json"))).frame_options_refused, undefined);
  await writeFile(slotFiles(retried.out)[0], FRAME_OPTIONS_REJECTED);
  const retriedAgain = shell(resumeOf(retried.out));
  assert.equal(retriedAgain.code, 0, retriedAgain.out);
  const [again] = callLines(retriedAgain.out);
  assert.equal(again.tool, "collect_video_media");
  assert.deepEqual(keyframesOf(again), { url: TIKTOK, sampling: "duration_scaled", max_frames: 120, quick_above_s: 180 });
  assert.equal(again.arguments.run_key, call.arguments.run_key);
  assert.equal((await readJson(path.join(run, "collect-media.json"))).frame_options_refused, true);
  const { out } = await driveFrom(run, retriedAgain.out);
  assert.match(out, /Fallback: collect_video_media did not accept overview on this server; repeated without it/);
  assert.match(out, /Fallback: collect_video_media did not accept include_shot_starts \/ dense_windows on this server; repeated without them/);
  assert.match(out, /Frames: This server refused the shot-start and dense-window frame options/);
  assert.match(out, /The overview was not applied/);

  // collect_media.py on its own retries the same way.
  const alone = await newRun(t);
  const handed = python("collect_media.py", ["--url", TIKTOK, "--operations", "keyframes"], alone);
  await writeFile(slotFiles(handed.out)[0], FRAME_OPTIONS_REJECTED);
  const repeatedOnce = shell(resumeOf(handed.out));
  assert.equal(repeatedOnce.code, 0, repeatedOnce.out);
  assert.match(repeatedOnce.out, /did not accept overview/);
  await writeFile(slotFiles(repeatedOnce.out)[0], FRAME_OPTIONS_REJECTED);
  const repeated = shell(resumeOf(repeatedOnce.out));
  assert.equal(repeated.code, 0, repeated.out);
  assert.match(repeated.out, /did not accept include_shot_starts \/ dense_windows/);
  assert.deepEqual(keyframesOf(callLines(repeated.out)[0]), { url: TIKTOK, sampling: "duration_scaled", max_frames: 120, quick_above_s: 180 });
  // Inside collect_video_media a bad option fails only the keyframes item (validation_error) while the other items
  // run: that too repeats the call once without the options, and the newer keyframes result is the one used.
  const itemRun = await newRun(t);
  const opened = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], itemRun);
  const firstCall = callLines(opened.out)[0];
  const itemFailed = composite(firstCall.arguments);
  for (const entry of itemFailed.calls) if (entry.result.operation === "extract_keyframes")
    Object.assign(entry.result, { status: "failed", error_code: "validation_error", data: undefined });
  await writeFile(slotFiles(opened.out)[0], mcp(itemFailed));
  const repeatedItem = shell(resumeOf(opened.out));
  assert.equal(repeatedItem.code, 0, repeatedItem.out);
  const { overview: _dropped, ...itemWithoutOverview } = keyframesOf(firstCall);
  assert.deepEqual(keyframesOf(callLines(repeatedItem.out)[0]), itemWithoutOverview);
  const { out: itemOut } = await driveFrom(itemRun, repeatedItem.out);
  assert.match(itemOut, /Fallback: collect_video_media did not accept overview/);
  assert.match(itemOut, /^read: /m);
  const aloneItem = await newRun(t);
  const handedItem = python("collect_media.py", ["--url", TIKTOK, "--operations", "transcript,keyframes"], aloneItem);
  const aloneFailed = composite(callLines(handedItem.out)[0].arguments);
  for (const entry of aloneFailed.calls) if (entry.result.operation === "extract_keyframes")
    Object.assign(entry.result, { status: "failed", error_code: "validation_error", data: undefined });
  await writeFile(slotFiles(handedItem.out)[0], mcp(aloneFailed));
  const aloneAgain = shell(resumeOf(handedItem.out));
  assert.equal(aloneAgain.code, 0, aloneAgain.out);
  assert.match(aloneAgain.out, /refused overview for the frames/);
  const { overview: _alsoDropped, ...aloneWithoutOverview } = keyframesOf(callLines(handedItem.out)[0]);
  assert.deepEqual(keyframesOf(callLines(aloneAgain.out)[0]), aloneWithoutOverview);
  // Any other failure is never taken for a refusal of the options.
  const failedRun = await newRun(t);
  const other = python("collect_media.py", ["--url", TIKTOK, "--operations", "keyframes"], failedRun);
  await writeFile(slotFiles(other.out)[0], JSON.stringify({ isError: true, content: [{ type: "text", text: "quota_exceeded: used up" }] }));
  const failed = shell(resumeOf(other.out));
  assert.doesNotMatch(failed.out, /did not accept include_shot_starts/);
});

// The frames a newer server returns carry `source` and the plan names its options; an older one ignores them.
function withShotStarts(value) {
  for (const call of value.calls) {
    if (call.result.operation !== "extract_keyframes") continue;
    call.result.data.frames = call.result.data.frames.map((frame, index) => ({ ...frame, source: index === 3 ? "shot_start" : "hook" }));
    call.result.data.sampling_plan = { base_interval_s: 1, hook_window_s: 3, hook_frames: 3, frames: 5, budget: 120, body_degraded: false,
      include_shot_starts: true, shot_detection: { status: "detected", cuts: 1, threshold: 0.15 }, shot_start_frames: 1, dense_window_frames: 0,
      dense_windows: [], dropped_for_budget: { shot_start: 0, dense_window: 0 }, dropped_as_duplicate: { shot_start: 0, dense_window: 0, body: 0 },
      dedupe_s: 0.25, budget_priority: ["hook", "closing", "shot_start", "dense_window", "body"], frame_sources: [] };
  }
  return value;
}

test("frame options: applied ones reach the evidence (frame source, plan); a server that ignored them is named, not hidden", async (t) => {
  const { run, out } = await observe(t, null);
  assert.match(out, /Frames: This server took its standard frame plan/);
  await writeRequest(run);
  assert.equal(build(run, flagsOf(out)).code, 0);
  const plainEvidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assert.equal(plainEvidence.frames.items.some((item) => "source" in item), false);

  const applied = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], applied);
  await writeFile(slotFiles(first.out)[0], mcp(withShotStarts(composite(callLines(first.out)[0].arguments))));
  const done = shell(resumeOf(first.out));
  assert.match(done.out, /"status": "observed"/);
  assert.doesNotMatch(done.out, /standard frame plan/);
  await writeRequest(applied);
  const built = build(applied, flagsOf(done.out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(applied, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.frames.items[3].source, "shot_start");
  assert.equal(evidence.frames.sampling_plan.include_shot_starts, true);
  assert.equal(evidence.frames.sampling_plan.shot_detection.status, "detected");
  assert.equal("frame_sources" in evidence.frames.sampling_plan, false);
});

// The overview plan (acv_timing.py): a server that made it returns low-resolution sheets of every second besides the
// frames; the read brings the sheets first with a legend, and the evidence and the brief carry them with their seconds.
function withOverview(value, { overview = true } = {}) {
  for (const call of value.calls) {
    if (call.result.operation !== "extract_keyframes") continue;
    const data = call.result.data;
    data.duration_s = 120;
    data.frames = data.frames.map((frame, index) => ({ ...frame, source: index === 3 ? "change" : "hook",
      ...(index === 3 ? { reason: "text_change", change_units: 180 } : {}) }));
    data.sampling_plan = { base_interval_s: 1, hook_window_s: 3, hook_frames: 3, frames: 5, budget: 120, body_degraded: false,
      body_interval_s: null, body_frames: 0, include_shot_starts: true, shot_detection: { status: "detected", cuts: 0, threshold: 0.15 },
      shot_start_frames: 0, dense_window_frames: 0, dense_windows: [], dropped_for_budget: { shot_start: 0, dense_window: 0 },
      dropped_as_duplicate: { shot_start: 0, dense_window: 0, body: 0, change: 0 }, dedupe_s: 0.25,
      budget_priority: ["hook", "closing", "shot_start", "dense_window", "change", "anchor"], frame_sources: [],
      ...(overview ? { overview: true, overview_stride_s: 1, change_candidates: 4, change_frames: 1, anchor_frames: 0,
        change_threshold_units: 100, anchor_gap_s: 10 } : {}) };
    if (overview) {
      const sheets = [0, 1, 2, 3].map((index) => ({ sheet_id: `overview-0${index + 1}`, object_ref: `creator-media/job/overview-0${index + 1}.jpg`,
        sha256: "d".repeat(64), bytes: 200, from_s: index * 30, to_s: index * 30 + 29, tiles: 30 }));
      data.overview = { status: "available", selection: "overview_v1", columns: 6, rows: 5, tile_long_edge_px: 256, stride_s: 1,
        padding_px: 2, seconds: 120, sheets, change: { grid_px: 64, threshold_units: 100, picture_units: [], text_units: [] } };
      data.artifacts.push(...sheets.map((sheet) => ({ kind: "keyframes", bytes: 200, sha256: sheet.sha256, object_ref: sheet.object_ref })));
    }
  }
  return value;
}

test("overview: the sheets are read first with their seconds, reach the evidence and the brief; a server without it is named", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  await writeFile(slotFiles(first.out)[0], mcp(withOverview(composite(callLines(first.out)[0].arguments))));
  const done = shell(resumeOf(first.out));
  assert.match(done.out, /"status": "observed"/);
  assert.match(done.out, /Overview: the first 4 image\(s\) read are low-resolution sheets of every 1s/);
  assert.match(done.out, /overview-02 30-59s/);
  const read = JSON.parse(done.out.split("\n").find((line) => line.startsWith("read: ")).slice(6));
  assert.deepEqual(read.arguments.object_refs.slice(0, 4), [1, 2, 3, 4].map((n) => `creator-media/job/overview-0${n}.jpg`));
  assert.equal(read.arguments.object_refs.length, 4 + 5);
  assert.doesNotMatch(done.out, /overview was not applied/);
  await writeRequest(run);
  const built = build(run, flagsOf(done.out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.deepEqual(evidence.frames.overview.sheets.map((sheet) => [sheet.sheet_id, sheet.from_s, sheet.to_s, sheet.path]),
    [0, 1, 2, 3].map((index) => [`overview-0${index + 1}`, index * 30, index * 30 + 29, `creator-media/job/overview-0${index + 1}.jpg`]));
  assert.equal(evidence.frames.items[3].reason, "text_change");
  assert.equal(evidence.frames.sampling_plan.change_frames, 1);
  const prepared = await prepare(run, ["--mode", "diagnosis", "--focus", "opening"]);
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(brief, /Overview: every 1s of the whole video at low resolution, 6 tiles a row and 5 rows a sheet/);
  assert.match(brief, /- overview `overview-03` 60s–89s `creator-media\/job\/overview-03\.jpg`/);
  assert.match(brief, /`frame-0004` 12s change \(text_change\)/);
  assert.match(brief, /no body grid: the overview shows every 1s, with 1 change and 0 anchor frame\(s\)/);

  // A server that took the options but made no overview on a long video: said plainly, the frames still read.
  const older = await newRun(t);
  const opened = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], older);
  await writeFile(slotFiles(opened.out)[0], mcp(withOverview(composite(callLines(opened.out)[0].arguments), { overview: false })));
  const plain = shell(resumeOf(opened.out));
  assert.match(plain.out, /This server does not make the overview yet\. The overview was not applied/);
  assert.doesNotMatch(plain.out, /^Overview: /m);
});

// Whole-video fallback for every source: the platform list is gone; the tool's own answer decides.
const DOUYIN = "https://www.douyin.com/video/7300000000000000002";
const BILIBILI = "https://www.bilibili.com/video/BV1xx411c7mD";

test("whole-video fallback: a Douyin or Bilibili link whose server frames brought nothing gets the viewing", async (t) => {
  for (const url of [DOUYIN, BILIBILI]) {
    const { out, handed } = await observe(t, null, { mediaFailed: true, url });
    assert.match(out, /"source": "whole_video"/, url);
    assert.match(out, /Fallback: server_frames failed \(media_unavailable\); falling back to whole_video/);
    const viewing = handed.filter((call) => call.tool === "analyze_content_video");
    assert.equal(viewing.length, 1, url);
    assert.equal(viewing[0].arguments.source_url, url);
  }
});

test("whole-video fallback: a kabo-file whose frames and words came back empty is viewed once its measured duration is known", async (t) => {
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  const { out, handed } = await observe(t, null, { url: `kabo-file:${id}`, frameTimes: [], emptyTranscript: true,
    measuredDuration: 20 });
  assert.match(out, /falling back to whole_video/);
  const viewing = handed.filter((call) => call.tool === "analyze_content_video");
  assert.equal(viewing.length, 1);
  assert.equal(viewing[0].arguments.source_url, `kabo-file:${id}`);
});

test("whole-video viewing the tool cannot read (unsupported) is a gap: the run carries on with frames and says so", async (t) => {
  const answers = [
    JSON.stringify({ isError: true, content: [{ type: "text",
      text: "MCP error -32602: Input validation error: Invalid arguments for tool analyze_content_video: [{\"path\":[\"source_url\"],\"message\":\"Unsupported URL\"}]" }] }),
    mcp({ ...viewerFixture, status: "failed", result: null, transcript: null, failure: { code: "unsupported_platform", message: "This platform is not supported." } }),
  ];
  for (const answer of answers) {
    const run = await newRun(t);
    await selectFirst(run, "sound");
    const first = python("observe_video.py", ["--url", DOUYIN, "--mode", "diagnosis"], run);
    assert.match(first.out, /Observation source: combined/);
    const { out, handed } = await driveFrom(run, first.out, { viewerSteps: [answer] });
    // One viewing call: an unsupported source is never taken for an older server and repeated.
    assert.equal(handed.filter((call) => call.tool === "analyze_content_video").length, 1);
    assert.match(out, /"status": "observed"/);
    assert.match(flagsOf(out), /--limitation 'The whole-video viewing cannot read this source/);
    assert.match(out, /^read: /m);
  }
});

// One observation deadline (330 s from the first hand-over, the same on every host): Kabo Web ends a turn at 500 s,
// and on the pre-release service a throttled Bilibili download held the fetch step for 477 s until the turn died
// with no reply. The clock is injected by moving the run's recorded start back, so nothing here waits.
const DEADLINE_S = 330;
// The whole flags line: flagsOf stops at the first ": ", and a limitation line has one of its own.
const allFlags = (out) => { const line = out.split("\n").find((item) => item.startsWith("Pass these to build_content_evidence.py")); return line.slice(line.indexOf(": ") + 2); };
function withPending(args, operations, change = (value) => value) {
  const value = composite(args);
  const late = new Set(operations);
  value.calls = value.calls.filter((call) => !late.has(call.group.split("/")[1]));
  value.summary.jobs = value.summary.jobs.map((job) => late.has(job.operation) ? { ...job, status: "running" } : job);
  value.summary.pending = value.coverage.pending = late.size;
  value.coverage.unfinished = value.summary.jobs.filter((job) => late.has(job.operation)).map((job) => job.group);
  return change(value);
}
async function startedAgo(run, seconds) {
  const file = path.join(run, "observe-video.json");
  const state = await readJson(file);
  state.started_at = new Date(Date.now() - seconds * 1000).toISOString();
  await writeFile(file, JSON.stringify(state));
}
// Drive an observation already started in `run` to its end: `media(args, n)` answers the n-th media call.
// The two side calls: `side[tool]` is what the host saved for that call (an object is saved as an MCP result, a string
// as it is); a tool left out of `side` gets no file at all, as on a host that does not have it.
const SIDE_TOOLS = new Set(["identify_video_song", "summarize_video_comments"]);
async function driveWith(run, out, { media = (args) => composite(args), viewerSteps = [viewerFixture], afterRound, side = {} } = {}) {
  const steps = [...viewerSteps];
  const handed = [];
  let mediaCalls = 0;
  for (let round = 0; round < 10 && !OBSERVED.test(out); round += 1) {
    const calls = callLines(out), files = slotFiles(out);
    assert.ok(calls.length, out);
    for (const [index, call] of calls.entries()) {
      handed.push(call);
      if (call.tool === "collect_video_media") await writeFile(files[index], mcp(media(call.arguments, mediaCalls++)));
      else if (SIDE_TOOLS.has(call.tool)) {
        if (side[call.tool] !== undefined) await writeFile(files[index], typeof side[call.tool] === "string" ? side[call.tool] : mcp(side[call.tool]));
      } else await writeFile(files[index], typeof steps[0] === "string" ? steps.shift() : mcp(steps.shift()));
    }
    if (afterRound) await afterRound(run, round);
    const resumed = shell(resumeOf(out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
    assert.equal(resumed.code, 0, resumed.out);
    out = resumed.out;
  }
  assert.match(out, OBSERVED);
  return { out, handed };
}

test("observation deadline: frames and transcript still running at 330 s stop the wait, no fallback viewing starts, and the run goes on from the metadata saying they did not arrive in time", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  const late = ["fetch_transcript", "extract_keyframes"];
  // Round one is well inside the deadline: the same call is handed over again.
  const { out, handed } = await driveWith(run, first.out, {
    media: (args) => withPending(args, late),
    afterRound: async (dir, round) => { if (round === 1) await startedAgo(dir, DEADLINE_S + 60); } });
  assert.equal(handed.filter((call) => call.tool === "collect_video_media").length, 2, out);
  assert.equal(handed.filter((call) => call.tool === "analyze_content_video").length, 0, "no viewing can finish in time");
  assert.match(out, /"status": "timed_out"/);
  assert.match(out, /"timed_out": \["the transcript", "the frames"\]/);
  assert.match(out, /stopped at its 330-second deadline: the transcript and the frames did not arrive in time/);
  assert.match(out, /must say plainly that/);
  const flags = allFlags(out);
  assert.match(flags, /--deferred-incomplete fetch_transcript=/);
  assert.match(flags, /--deferred-incomplete extract_keyframes=/);
  assert.match(flags, /--limitation 'Observation deadline reached \(330s\): the transcript and the frames did not arrive in time/);
  assert.match(flags, /--limitation 'No fallback whole-video viewing was started: too little of the 330s observation deadline was left to finish\.'/);
  await writeRequest(run);
  const built = build(run, flags);
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  assert.equal(evidence.content_metadata.status, "available");
  // The metadata arrived: the analysis goes on from it, and the brief says first what did not arrive.
  const prepared = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(brief, /### Did not arrive in time\n\n- Observation deadline reached \(330s\)/);
  assert.match(brief, /Say this plainly in the first lines of what the creator reads/);
});

test("observation deadline: a video known to run past ten minutes stops waiting at 270 s, leaving the analysis more of the turn", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  const late = ["fetch_transcript", "extract_keyframes"];
  // The metadata reports an 18-minute video; frames and words are still running 280 s in.
  const { out } = await driveWith(run, first.out, {
    media: (args) => withPending(args, late, (value) => {
      for (const call of value.calls) if (call.result.data?.video) call.result.data.video.duration_seconds = 1106;
      return value;
    }),
    afterRound: async (dir, round) => { if (round === 0) await startedAgo(dir, 280); } });
  assert.match(out, /"status": "timed_out"/);
  assert.match(out, /stopped at its 270-second deadline/);
  assert.doesNotMatch(out, /330-second deadline/);
});

test("observation deadline: a measurement that finished while the frames still run sets the long-video deadline", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  // The metadata reports no duration; the measurement, done while frames and words run, reports 18 minutes.
  const { out } = await driveWith(run, first.out, {
    media: (args) => withPending(args, ["fetch_transcript", "extract_keyframes"], (value) => {
      for (const call of value.calls) {
        if (call.result.data?.video) call.result.data.video.duration_seconds = null;
        if (call.result.operation === "measure_media_signals") call.result.data.duration_s = 1106;
      }
      return value;
    }),
    afterRound: async (dir, round) => { if (round === 0) await startedAgo(dir, 280); } });
  assert.match(out, /"status": "timed_out"/);
  assert.match(out, /stopped at its 270-second deadline/);
});

test("observation deadline: with nothing and no metadata in time, the brief is refused with a did-not-arrive statement, not the gone-video one", async (t) => {
  const run = await newRun(t);
  await writeRequest(run);
  const late = "Observation deadline reached (330s): the transcript and the frames did not arrive in time, so the analysis uses only what had arrived.";
  const built = build(run, `--deferred-incomplete fetch_transcript=${uuid(2)} --deferred-incomplete extract_keyframes=${uuid(3)} --limitation '${late}'`);
  assert.equal(built.code, 0, built.out);
  const refused = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(refused.code, 2, refused.out);
  assert.match(refused.out, /did not arrive in time/);
  assert.doesNotMatch(refused.out, /deleted/);
});

test("observation deadline: a viewing still running at 330 s is recorded as not arrived in time and no fallback starts", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  const { out, handed } = await driveWith(run, first.out, { viewerSteps: [queued, queued, queued],
    afterRound: async (dir, round) => { if (round === 1) await startedAgo(dir, DEADLINE_S + 5); } });
  assert.equal(handed.filter((call) => call.tool === "analyze_content_video").length, 1);
  // The viewing's media call carried the metadata only; no frames call follows it past the deadline.
  assert.equal(handed.filter((call) => call.tool === "collect_video_media").length, 1, out);
  assert.match(out, /"timed_out": \["the whole-video viewing"\]/);
  assert.match(out, /whole_video failed \(timed_out\)/);
  assert.match(allFlags(out), /--limitation 'Observation deadline reached \(330s\): the whole-video viewing did not arrive in time/);
});

test("observation deadline: the same 330 s bound holds in collect_media.py and observe_video.py, from one constant", () => {
  const probe = spawnSync("python3", ["-I", "-B", "-c", "import sys, json\nsys.path.insert(0, sys.argv[1])\n"
    + "import collect_media, observation_order, observe_video\n"
    + "print(json.dumps([observation_order.OBSERVE_DEADLINE_S, collect_media.WAIT_BUDGET_S, hasattr(observe_video, 'VIEWER_BUDGET_S')]))",
  scripts], { encoding: "utf8", env });
  assert.equal(probe.status, 0, probe.stderr);
  assert.deepEqual(JSON.parse(probe.stdout), [DEADLINE_S, DEADLINE_S, false]);
});

// The deadline bounds when the last hand-over ends, not only when it starts: each call waits inside its tool (45 s),
// so a new one starts only while what is left covers its wait plus a 15 s margin; a wait_s is shortened to fit. On
// pre, a 45 s poll started just before 330 s held a 1 h 50 min video's fetch step for 385 s and the turn died at 500 s.
test("observation deadline: round_waits gives each call of a round the wait the deadline still covers, one constant for every host", () => {
  const probe = spawnSync("python3", ["-I", "-B", "-c", "import sys, json\nsys.path.insert(0, sys.argv[1])\n"
    + "import observation_order as o\n"
    + "print(json.dumps([o.CALL_WAIT_S, o.MIN_CALL_WAIT_S, o.HAND_OVER_MARGIN_S]\n"
    + "  + [o.round_waits(left, 1) for left in (330, 60, 59, 40, 25, 24, 0)]\n"
    + "  + [o.round_waits(left, 2) for left in (330, 80, 30, 24)]))",
  scripts], { encoding: "utf8", env });
  assert.equal(probe.status, 0, probe.stderr);
  assert.deepEqual(JSON.parse(probe.stdout), [45, 10, 15, [45], [45], [44], [25], [10], [], [], [45, 45], [32, 32], [15], []]);
});

test("observation deadline: a media poll that would run past the deadline is not started, and the outcome text is the deadline's", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], run);
  const late = ["fetch_transcript", "extract_keyframes"];
  // 310 s in, still before 330 s: 20 s left cannot cover a poll's wait plus the margin, so none starts.
  const { out, handed } = await driveWith(run, first.out, {
    media: (args) => withPending(args, late),
    afterRound: async (dir, round) => { if (round === 1) await startedAgo(dir, 310); } });
  assert.equal(handed.filter((call) => call.tool === "collect_video_media").length, 2, out);
  assert.equal(handed.filter((call) => call.arguments.wait_s !== undefined).length, 0, "both polls were full length");
  assert.match(out, /"status": "timed_out"/);
  assert.match(out, /"timed_out": \["the transcript", "the frames"\]/);
  assert.match(out, /stopped at its 330-second deadline: the transcript and the frames did not arrive in time/);
  const flags = allFlags(out);
  assert.match(flags, /--deferred-incomplete fetch_transcript=/);
  assert.match(flags, /--limitation 'Observation deadline reached \(330s\): the transcript and the frames did not arrive in time, so the analysis uses only what had arrived\.'/);
});

test("observation deadline: a viewing's wait_s is shortened to what is left, and a reading that cannot fit is not started", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "whole_video"], run);
  // 290 s in: 40 s left, less the 15 s margin, leaves a 25 s reading; 312 s in: 18 s left fits none.
  const { out, handed } = await driveWith(run, first.out, { viewerSteps: [queued, queued, queued, queued],
    afterRound: async (dir, round) => { if (round === 1) await startedAgo(dir, 290); if (round === 2) await startedAgo(dir, 312); } });
  const readings = handed.filter((call) => call.tool === "get_analysis_run").map((call) => call.arguments.wait_s);
  // 24 once the resume's own start-up has ticked past the whole second.
  assert.equal(readings.length, 2);
  assert.equal(readings[0], 45);
  assert.ok(readings[1] === 25 || readings[1] === 24, `wait_s ${readings[1]}`);
  assert.match(out, /"timed_out": \["the whole-video viewing"\]/);
  assert.match(out, /whole_video failed \(timed_out\)/);
  assert.match(allFlags(out), /--limitation 'Observation deadline reached \(330s\): the whole-video viewing did not arrive in time/);
});

test("observation deadline: a viewing reading and a media poll in one round share what is left, and both wait_s add up inside it", async (t) => {
  const run = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis", "--duration-s", "30", "--observe-source", "combined"], run);
  // 250 s in: 80 s left, less the margin, is 65 s for two calls made one after the other: 32 s each.
  const { out, handed } = await driveWith(run, first.out, { viewerSteps: [queued, queued, queued],
    media: (args) => withPending(args, ["fetch_transcript"]),
    afterRound: async (dir, round) => { if (round === 0) await startedAgo(dir, 250); if (round === 1) await startedAgo(dir, DEADLINE_S + 5); } });
  const second = handed.slice(2, 4);
  assert.deepEqual(second.map((call) => call.tool), ["get_analysis_run", "collect_video_media"]);
  // An equal share each (31 once the resume's own start-up has ticked past 64 s), never more than 65 s in all.
  const [viewing, media] = second.map((call) => call.arguments.wait_s);
  assert.ok((viewing === 32 || viewing === 31) && viewing === media, `wait_s ${viewing} + ${media}`);
  assert.match(out, /"timed_out": \["the whole-video viewing", "the transcript"\]/);
});

// "What song is this?" is its own request: answered from metadata, on-screen text and speech, never by ear, so it
// takes no sound card and never starts the paid whole-video viewing, not even as a fallback.
test("find the track: select_method records the ask, refuses the sound card, and the observation never starts a viewing", async (t) => {
  const run = await newRun(t);
  const select = (...args) => python("select_method.py", [...args, "--out", "analysis/method.json"], run);
  assert.equal(select("--mode", "content_read", "--ask", "identify_track", "--focus", "sound").code, 2);
  assert.equal(select("--mode", "diagnosis", "--ask", "identify_track").code, 2);
  const chosen = select("--mode", "content_read", "--ask", "identify_track");
  assert.equal(chosen.code, 0, chosen.out);
  const method = await readJson(path.join(run, "analysis/method.json"));
  assert.equal(method.ask, "identify_track");
  assert.deepEqual(method.cards.map((card) => card.id), ["diagnosis-default"]);
  const pick = python("observation_order.py", ["--platform", "tiktok", "--failed", "server_frames", "--ask", "identify_track", "--mode", "content_read"], root);
  assert.equal(JSON.parse(pick.out).source, null);
  assert.match(JSON.parse(pick.out).reason, /find-the-song request never starts a whole-video viewing/);
  // Frames and words fail: the run ends without a viewing. The one song recognition call rides in the first round.
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "content_read"], run);
  const ops = callLines(first.out)[0].arguments.requests.map((request) => request.operation);
  assert.deepEqual(ops, ["collect_public_metadata", "fetch_transcript", "extract_keyframes"]);
  const { handed } = await driveWith(run, first.out, { media: (args) => composite(args, { failed: true }) });
  assert.deepEqual(handed.map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
});

test("find the track: the brief answers from metadata, on-screen text and speech and says plainly when the track can't be identified", async (t) => {
  const run = await newRun(t);
  assert.equal(python("select_method.py", ["--mode", "content_read", "--ask", "identify_track", "--out", "analysis/method.json"], run).code, 0);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "content_read"], run);
  const { out } = await driveWith(run, first.out);
  await writeRequest(run);
  assert.equal(build(run, allFlags(out)).code, 0);
  const prepared = await prepare(run, ["--mode", "content_read"], "what song is this?");
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(brief, /Find the track: which song or sound the video uses/);
  assert.match(brief, /This is a find-the-song request/);
  assert.match(brief, /Never name a song, artist or remix from your own impression of the sound/);
  assert.match(brief, /the track can't be identified from this\s+video's data/);
  assert.equal((await readJson(path.join(run, "analysis/method.json"))).ask, "identify_track");
});

// A deleted or private video ended differently from run to run. Whatever said so (a result's
// data.source_unavailable, or every source empty), there is one evidence marker and one statement for the creator.
test("source unavailable: one marker and one statement, from the observation, the evidence and the brief alike", async (t) => {
  const statement = "This video can't be opened: it may have been deleted, made private or limited to some regions. Send another public link or the video file and I'll analyse that instead.";
  const marker = "source_unavailable: the video itself could not be fetched (it may be deleted, private or limited to some regions), so nothing in it was seen or heard.";
  const gone = (args) => {
    const value = composite(args);
    for (const call of value.calls) {
      call.result.status = "completed_partial";
      call.result.data = { ...call.result.data, source_unavailable: true, cues: [], frames: [], artifacts: [] };
    }
    return value;
  };
  const flagged = await newRun(t);
  const flaggedOut = await driveWith(flagged, python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], flagged).out, { media: gone });
  const empty = await observe(t, null, { mediaFailed: "all", viewerSteps: [JSON.stringify({ code: "not_found", message: "gone", retryable: false })] });
  for (const out of [flaggedOut.out, empty.out]) {
    assert.match(out, /"status": "source_unavailable"/);
    assert.ok(out.includes(`Evidence: ${marker}`), out);
    assert.ok(out.includes(statement), out);
    assert.doesNotMatch(out, /Pass these to build_content_evidence\.py/);
  }
  // No paid viewing after the backend said the video itself is gone.
  assert.equal(flaggedOut.handed.filter((call) => call.tool === "analyze_content_video").length, 0);
  // Built anyway: the evidence carries the marker once, and the brief is refused with the same statement.
  const envelope = (operation, number, data) => ({ ...mediaEnvelope(operation, uuid(number)), status: "completed_partial",
    data: { ...data, source_unavailable: true, artifacts: [] } });
  const { run, evidence } = await evidenceFrom(t, { envelopes: [
    envelope("fetch_transcript", 2, { cues: [], cue_count: 0 }),
    envelope("extract_keyframes", 3, { frames: [], frame_count: 0, selection: "none" })] });
  assert.equal(evidence.limitations.filter((text) => text === marker).length, 1, evidence.limitations.join("\n"));
  const refused = await prepare(run, ["--mode", "diagnosis"]);
  assert.equal(refused.code, 2, refused.out);
  assert.ok(JSON.parse(refused.out.split("\n")[0]).error.includes(statement), refused.out);
});

// Side calls: a find-the-song request adds one identify_video_song call and the audience-response card one
// summarize_video_comments call. Each rides in the observation's first hand-over (no round of its own, KS9), is
// read once, and whatever it brings, nothing included, becomes evidence the same way on every host.
const pinnedTools = new Map(JSON.parse(readFileSync(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map((tool) => [tool.name, tool]));
const pinnedInput = (name) => new Ajv({ strict: false, logger: false, validateFormats: false }).compile(pinnedTools.get(name).inputSchema);
const pinnedOutput = (name) => new Ajv({ strict: false, logger: false, validateFormats: false }).compile(pinnedTools.get(name).outputSchema);
const SONG = {
  matched: { status: "matched", source: "recognition", reason: null, platform: "tiktok", sample_start_s: 0,
    song: { title: "Golden Hour", artist: "Example Artist", album: "Example Album", url: "https://music.example.com/track/1" },
    platform_audio: { title: "original sound", credit: "cook", original: true, url: null } },
  noMatch: { status: "no_match", source: null, reason: null, platform: "tiktok", sample_start_s: 0, song: null,
    platform_audio: { title: "Golden Hour (sped up)", credit: "Example Artist", original: false, url: "https://www.tiktok.com/music/x-1" } },
  unsupported: { status: "unsupported_platform", source: null, reason: null, platform: null, sample_start_s: null, song: null, platform_audio: null },
};
const COMMENTS = {
  ok: { status: "ok", platform: "tiktok", total_comments: null, sample_size: 48, language: "en",
    sentiment: { positive: 70, neutral: 20, negative: 10 }, summary: "Viewers relate to the burnt pan and want the fix spelled out.",
    themes: [{ label: "Which pan", description: "Many ask which pan is used in the close-up.", share: 40 },
      { label: "Relatable mistake", description: "Viewers say they burn food the same way.", share: 35 }],
    questions: ["Which pan is this?"], requests: ["Show the same fix for stainless steel."],
    controversy: { flagged: false, note: null }, retrieved_at: "2026-11-21" },
  tooFew: { status: "too_few_comments", platform: "tiktok", total_comments: null, sample_size: 3, language: null, sentiment: null,
    summary: null, themes: [], questions: [], requests: [], controversy: null, retrieved_at: "2026-11-21" },
};

async function sideRun(t, { focus, ask, url = TIKTOK, side = {}, mode } = {}) {
  const run = await newRun(t);
  const runMode = mode ?? (ask ? "content_read" : "diagnosis");
  const chosen = python("select_method.py", ["--mode", runMode, ...(focus ? ["--focus", focus] : []), ...(ask ? ["--ask", ask] : []),
    "--out", "analysis/method.json"], run);
  assert.equal(chosen.code, 0, chosen.out);
  const first = python("observe_video.py", ["--url", url, "--mode", runMode], run);
  assert.equal(first.code, 0, first.out);
  const { out, handed } = await driveWith(run, first.out, { side });
  if (url.startsWith("kabo-file:")) {
    const made = python("prepare_link_request.py", ["--file-ref", url, "--platform", "tiktok", "--subject-state", "own_unpublished",
      "--max-connector-calls", "10", "--confirmed-by-user", "--output", path.join(run, "analysis/video-analysis-request.json")], run);
    assert.equal(made.code, 0, made.out);
  } else await writeRequest(run);
  const built = build(run, allFlags(out));
  assert.equal(built.code, 0, built.out);
  const evidence = await readJson(path.join(run, "analysis/content_evidence.json"));
  assertValidEvidence(evidence);
  return { run, first: first.out, out, handed, evidence };
}

test("side-call fixtures match the pinned output schemas of identify_video_song and summarize_video_comments", () => {
  for (const value of Object.values(SONG)) assert.ok(pinnedOutput("identify_video_song")(value), JSON.stringify(value));
  for (const value of Object.values(COMMENTS)) assert.ok(pinnedOutput("summarize_video_comments")(value), JSON.stringify(value));
});

test("find the track, matched: one identify_video_song call beside the media call; the brief names the song and its listen link", async (t) => {
  const { run, first, handed, evidence, out } = await sideRun(t, { ask: "identify_track", side: { identify_video_song: SONG.matched } });
  // One hand-over: the media call and the song call together, in the form the Web host executes.
  const handover = hostHandover(first);
  assert.deepEqual(handover.calls.map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
  assert.deepEqual(handover.calls[1].arguments, { video_url: TIKTOK });
  assert.ok(pinnedInput("identify_video_song")(handover.calls[1].arguments));
  assert.equal(handed.filter((call) => call.tool === "identify_video_song").length, 1);
  assert.equal(handed.some((call) => call.tool === "analyze_content_video"), false);
  assert.match(out, /--song snapshot\/song\.json/);
  assert.match(out, /Side calls: song matched/);
  assert.deepEqual(evidence.song_identification.song, SONG.matched.song);
  assert.equal(evidence.song_identification.source, "recognition");
  assert.ok(evidence.acquisition.some((entry) => entry.operation === "identify_video_song" && entry.status === "completed"));
  const refs = (await readJson(path.join(run, "analysis/content_evidence.references.json"))).evidence_refs;
  assert.ok(refs.includes("song_identification.song") && refs.includes("song_identification.platform_audio"));
  const prepared = await prepare(run, ["--mode", "content_read"], "what song is this?");
  assert.equal(prepared.code, 0, prepared.out);
  const brief = await readBrief(run);
  assert.match(section(brief, 3), /recognised from the video's audio .*"Golden Hour" by Example Artist.*listen link https:\/\/music\.example\.com\/track\/1/);
  assert.match(section(brief, 3), /marked as the creator's original sound/);
  assert.match(section(brief, 7), /A song recognition match .* comes first: give the title and artist, and its listen link/s);
});

test("find the track, no match: the platform's sound label is the fallback, and the brief says the recognition found nothing", async (t) => {
  const { run, evidence } = await sideRun(t, { ask: "identify_track", side: { identify_video_song: SONG.noMatch } });
  assert.equal(evidence.song_identification.status, "no_match");
  assert.equal(evidence.song_identification.song, null);
  assert.equal(evidence.song_identification.platform_audio.title, "Golden Hour (sped up)");
  assert.ok(evidence.limitations.includes("The song recognition found no match in the video's audio."), evidence.limitations.join(" | "));
  assert.equal((await prepare(run, ["--mode", "content_read"], "what song is this?")).code, 0);
  const brief = await readBrief(run);
  assert.match(section(brief, 3), /Song recognition: no_match \(the recognition found no match in the video's audio\)/);
  assert.match(section(brief, 3), /the platform's sound label\): "Golden Hour \(sped up\)", credited to Example Artist/);
  assert.match(section(brief, 7), /the track can't be identified from this\s+video's data/);
});

test("find the track, unsupported or missing: the tool's unsupported answer, an error and no saved result are each a gap, never a failure", async (t) => {
  const douyin = await newRun(t);
  assert.equal(python("select_method.py", ["--mode", "content_read", "--ask", "identify_track", "--out", "analysis/method.json"], douyin).code, 0);
  // Any public link gets the call: which links it reads is the tool's own answer.
  assert.deepEqual(callLines(python("observe_video.py", ["--url", DOUYIN, "--mode", "content_read"], douyin).out)[1],
    { tool: "identify_video_song", arguments: { video_url: DOUYIN } });
  for (const [answer, status, code] of [[SONG.unsupported, "unsupported_platform", null],
    ["MCP error -32601: Tool not found: identify_video_song", "failed", "tool_error"], [undefined, "failed", "not_returned"]]) {
    const { run, out, evidence } = await sideRun(t, { ask: "identify_track", side: answer === undefined ? {} : { identify_video_song: answer } });
    assert.match(out, /"status": "observed"/);
    assert.equal(evidence.song_identification.status, status);
    assert.equal(evidence.song_identification.failure?.code ?? null, code);
    assert.equal((await prepare(run, ["--mode", "content_read"], "what song is this?")).code, 0);
    assert.match(section(await readBrief(run), 3), new RegExp(`Song recognition: ${status}`));
  }
});

test("find the track, uploaded file: no recognition call; the evidence says it was not attempted", async (t) => {
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  const { run, handed, evidence, out } = await sideRun(t, { ask: "identify_track", url: `kabo-file:${id}` });
  assert.deepEqual(handed.map((call) => call.tool), ["collect_video_media"]);
  assert.match(out, /Side calls: song uploaded_file/);
  assert.deepEqual([evidence.song_identification.status, evidence.song_identification.reason], ["not_attempted", "uploaded_file"]);
  assert.equal(evidence.acquisition.some((entry) => entry.operation === "identify_video_song"), false);
  assert.equal((await prepare(run, ["--mode", "content_read"], "what song is this?")).code, 0);
  assert.match(section(await readBrief(run), 3), /an uploaded file is not sent to the recognition/);
});

test("audience-response: choosing the card adds one summarize_video_comments call; the summary becomes citable evidence and a brief section", async (t) => {
  const { run, first, handed, evidence, out } = await sideRun(t, { focus: "audience-response", side: { summarize_video_comments: COMMENTS.ok } });
  const handover = hostHandover(first);
  assert.deepEqual(handover.calls.map((call) => call.tool), ["collect_video_media", "summarize_video_comments", "identify_video_song"]);
  assert.ok(pinnedInput("summarize_video_comments")(handover.calls[1].arguments));
  assert.equal(handed.filter((call) => call.tool === "summarize_video_comments").length, 1);
  assert.match(out, /--comment-summary snapshot\/comment-summary\.json/);
  const block = evidence.audience_response;
  assert.equal(block.status, "available");
  assert.equal(block.sample_size, 48);
  assert.deepEqual(block.themes.map((theme) => theme.label), ["Which pan", "Relatable mistake"]);
  const refs = (await readJson(path.join(run, "analysis/content_evidence.references.json"))).evidence_refs;
  for (const ref of ["audience_response.summary", "audience_response.sentiment", "audience_response.controversy",
    "audience_response.themes[1]", "audience_response.questions[0]", "audience_response.requests[0]"]) assert.ok(refs.includes(ref), ref);
  assert.equal((await prepare(run, ["--mode", "diagnosis"], "why did this do so well?")).code, 0);
  const brief = await readBrief(run);
  assert.match(section(brief, 3), /### Audience response \(comment summary\)/);
  assert.match(section(brief, 3), /A paraphrased summary of 48 top comments, mostly in en.*No comment text: never quote or invent a comment/);
  assert.match(section(brief, 3), /`audience_response\.themes\[0\]` Which pan \(40% of the sample\)/);
  assert.match(section(brief, 3), /`audience_response\.questions\[0\]` question: Which pan is this\?/);
  assert.match(section(brief, 5), /\(`audience-response`, topic card, version 1\.0\.0\)/);
  // Without the card, no comment call is made.
  const plain = await newRun(t);
  await selectFirst(plain, "opening");
  assert.deepEqual(callLines(python("observe_video.py", ["--url", TIKTOK, "--mode", "diagnosis"], plain).out).map((call) => call.tool), ["collect_video_media", "identify_video_song"]);
});

test("audience-response without a summary (tool missing on this host, an error, too few comments, an uploaded file): the comments were not read", async (t) => {
  const cases = [
    [{}, "failed", /the comment summary is not available here/],
    [{ summarize_video_comments: JSON.stringify({ code: "service_unavailable", message: "down", retryable: true }) }, "failed", /the comment summary is not available here/],
    [{ summarize_video_comments: COMMENTS.tooFew }, "too_few_comments", /the post has too few comments to summarise/],
  ];
  for (const [side, status, why] of cases) {
    const { run, out, evidence } = await sideRun(t, { focus: "audience-response", side });
    assert.match(out, /"status": "observed"/);
    assert.equal(evidence.audience_response.status, status);
    assert.deepEqual(evidence.audience_response.themes, []);
    assert.ok(evidence.limitations.some((line) => line.startsWith("The comments were not read")), evidence.limitations.join(" | "));
    assert.equal((await prepare(run, ["--mode", "diagnosis"], "what are people saying about this?")).code, 0);
    const brief = await readBrief(run);
    assert.match(section(brief, 3), new RegExp(`The comments were not read: ${why.source}\\. Work from the public comment count \\(\`public_metrics\\.comment_count\` = 4\\)`));
    const refs = (await readJson(path.join(run, "analysis/content_evidence.references.json"))).evidence_refs;
    assert.equal(refs.some((ref) => ref.startsWith("audience_response.")), false);
  }
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  const uploadedRun = await sideRun(t, { focus: "audience-response", url: `kabo-file:${id}` });
  assert.equal(uploadedRun.handed.some((call) => call.tool === "summarize_video_comments"), false);
  assert.equal(uploadedRun.evidence.audience_response.status, "not_attempted");
});

// Long videos in two steps. By default the keyframes, measurement and transcript requests carry quick_above_s, so a
// video past 180 s comes back as a quick, explicitly partial sample; `--depth deep` (only after the creator accepted
// the offer) is the full pass, keyed by the link and the UTC date so a deep run begun again replays the same jobs.
const QUICK_OPERATIONS = ["fetch_transcript", "extract_keyframes", "measure_media_signals"];
const quickOf = (call) => Object.fromEntries(call.arguments.requests.map((request) => [request.operation, request.parameters.quick_above_s]));
const deepKey = (url) => "acv-deep:" + createHash("sha256").update(`${url}|${new Date().toISOString().slice(0, 10)}`).digest("hex").slice(0, 32);

test("quick by default: every sampled operation of a link carries quick_above_s 180, never the metadata; a transcript export and an uploaded file carry none", async (t) => {
  for (const mode of ["diagnosis", "content_read", "craft_teardown"]) {
    const run = await newRun(t);
    const [call] = callLines(python("observe_video.py", ["--url", TIKTOK, "--mode", mode], run).out);
    assert.deepEqual(quickOf(call), { collect_public_metadata: undefined, fetch_transcript: 180, extract_keyframes: 180,
      ...(mode === "content_read" ? {} : { measure_media_signals: 180 }) }, mode);
    assert.match(call.arguments.run_key, /^acv:[0-9a-f]{32}$/);
    const media = await readJson(path.join(run, "collect-media.json"));
    assert.deepEqual([media.depth, media.quick_above_s], ["quick", 180]);
  }
  const exported = await newRun(t);
  const [exportCall] = callLines(python("observe_video.py", ["--url", TIKTOK, "--mode", "transcript_export"], exported).out);
  assert.deepEqual(exportCall.arguments.requests.map((request) => "quick_above_s" in request.parameters), [false]);
  const uploaded = await newRun(t);
  const [uploadCall] = callLines(python("observe_video.py", ["--url", `kabo-file:${uuid(9)}`, "--mode", "diagnosis"], uploaded).out);
  assert.equal(uploadCall.arguments.requests.some((request) => "quick_above_s" in request.parameters), false);
  // The threshold is the one constant, and the contract takes it on the three operations.
  const tools = new Map(JSON.parse(readFileSync(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map((tool) => [tool.name, tool]));
  for (const name of ["public_video_extract_keyframes", "public_video_fetch_transcript", "public_video_measure_media_signals"]) {
    const quick = tools.get(name).inputSchema.properties.parameters.properties.quick_above_s;
    assert.deepEqual([quick.type, quick.minimum, quick.maximum], ["integer", 30, 3600], name);
    assert.ok(quick.minimum <= 180 && 180 <= quick.maximum);
  }
});

test("deep: no quick threshold, the run key is the link and the UTC date, fixed at the first hand-over and the same in a second run", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-deep-"));
  if (!process.env.KEEP) t.after(() => rm(workspace, { recursive: true, force: true }));
  const runs = [];
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const begun = python("begin_analysis.py", ["--workspace", workspace, "--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
      "--question", "", "--confirmed-by-user", "--depth", "deep"], workspace);
    assert.equal(begun.code, 0, begun.out);
    const [call] = callLines(begun.out);
    assert.equal(call.arguments.run_key, deepKey(TIKTOK));
    assert.equal(call.arguments.requests.some((request) => "quick_above_s" in request.parameters), false);
    runs.push(/^Run directory: (\/.+)$/m.exec(begun.out)[1]);
  }
  const [first, second] = await Promise.all(runs.map((run) => readJson(path.join(run, "collect-media.json"))));
  assert.equal(first.depth, "deep");
  assert.equal((await readJson(path.join(runs[0], "observe-video.json"))).depth, "deep");
  // The second run counts the wait from when the first asked for the same jobs.
  assert.equal(second.deep_started_at, first.deep_started_at);
});

// The frames of a 111-minute video still running after the first wait: the full pass (0.06 x 6660 + 40 = 440 s) cannot
// arrive inside the 270-second deadline, so a deep run stops waiting instead of cutting the frames short.
test("deep_pending: a deep run whose frames cannot arrive in time names the running jobs for the host, writes nothing, and the same command continues the same jobs", async (t) => {
  const question = "why does the middle drag?";
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--confirmed-by-user", "--duration-s", "6660", "--depth", "deep"]);
  const [call] = callLines(begun.out);
  const files = slotFiles(begun.out);
  await writeFile(files[0], mcp(withPending(call.arguments, ["fetch_transcript", "extract_keyframes"])));
  await writeFile(files[1], mcp(SONG.noMatch));
  const stopped = shell(resumeOf(begun.out));
  assert.equal(stopped.code, 0, stopped.out);
  const lines = stopped.out.trimEnd().split("\n");
  const status = JSON.parse(lines[0]);
  assert.equal(status.status, "deep_pending");
  assert.deepEqual(status.pending, [`fetch_transcript=${uuid(2)}`, `extract_keyframes=${uuid(3)}`]);
  assert.equal(status.minutes_left, 8);
  assert.equal(lines[1], `deep_analysis_pending: ${JSON.stringify({ jobs: [uuid(2), uuid(3)], url: TIKTOK, question })}`);
  assert.match(lines[2], /^The full analysis is still running on Kabo's side: about 8 more minutes for this 111-minute video\. .*Write no report and no answer about the video in this turn\. Tell the creator, in their language/);
  assert.doesNotMatch(stopped.out, /^(?:Hand-over|call): /m);
  assert.equal(existsSync(path.join(run, "analysis/content_evidence.json")), false);
  assert.equal((await readJson(path.join(run, "observe-video.json"))).deep_pending.jobs.length, 2);

  // The same command (the one printed, or begin_analysis.py again in this run) hands the same media call over again.
  const again = lines[2].slice(lines[2].indexOf("cd '"));
  assert.match(again, /'--depth' 'deep'$/);
  const continued = shell(again);
  assert.equal(continued.code, 0, continued.out);
  const [repeat] = callLines(continued.out);
  assert.deepEqual(repeat.arguments, call.arguments);
  assert.equal(callLines(continued.out).length, 1, "the song is not asked for twice");
  const { out } = await driveWith(run, continued.out, { media: (args) => composite(args, { duration: 6660 }) });
  assert.match(out, /"status": "observed"/);
  assert.match(out, /^Envelopes included: /m);
  // A rerun of the whole begin command in this run continues the same way.
  const fresh = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "diagnosis",
    "--question", question, "--confirmed-by-user", "--duration-s", "6660", "--depth", "deep"]);
  await writeFile(slotFiles(fresh.begun.out)[0], mcp(withPending(callLines(fresh.begun.out)[0].arguments, ["extract_keyframes"])));
  assert.match(shell(resumeOf(fresh.begun.out)).out, /"status": "deep_pending"/);
  const rebegun = shell(`cd '${fresh.run}' && python3 -B '${path.join(scripts, "begin_analysis.py")}' --url '${TIKTOK}' --subject-state unknown `
    + `--mode diagnosis --question '${question}' --confirmed-by-user --duration-s 6660 --depth deep`);
  assert.equal(rebegun.code, 0, rebegun.out);
  assert.equal(callLines(rebegun.out)[0].arguments.run_key, deepKey(TIKTOK));
});

test("deep run: frames that fit keep the normal wait, and frames still running when no wait fits end deep_pending, never timed_out", async (t) => {
  // A 200-second video: the full pass (52 s) fits, so the same call is handed over again.
  const short = await newRun(t);
  const first = python("observe_video.py", ["--url", TIKTOK, "--mode", "content_read", "--duration-s", "200", "--depth", "deep"], short);
  await writeFile(slotFiles(first.out)[0], mcp(withPending(callLines(first.out)[0].arguments, ["extract_keyframes"])));
  const waiting = shell(resumeOf(first.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.match(waiting.out, /^Still running: 1 media job\(s\) are still running\. Keep waiting\.$/m);
  // Past the deadline with the frames still running: deep_pending, not a report without frames.
  await writeFile(slotFiles(waiting.out)[0], mcp(withPending(callLines(waiting.out)[0].arguments, ["extract_keyframes"])));
  await startedAgo(short, DEADLINE_S + 10);
  const late = shell(resumeOf(waiting.out).replace("'--placed'", "'--placed' --poll-sleep-s 0"));
  assert.match(late.out, /^\{"status": "deep_pending"/);
  assert.doesNotMatch(late.out, /timed_out|did not arrive in time/);
  // A quick run in the same situation still ends timed_out, as before.
  const quick = await newRun(t);
  const begun = python("observe_video.py", ["--url", TIKTOK, "--mode", "content_read", "--duration-s", "200"], quick);
  await writeFile(slotFiles(begun.out)[0], mcp(withPending(callLines(begun.out)[0].arguments, ["extract_keyframes"])));
  await startedAgo(quick, DEADLINE_S + 10);
  assert.match(shell(resumeOf(begun.out).replace("'--placed'", "'--placed' --poll-sleep-s 0")).out, /"status": "observed"/);
});

// The quick sample in the backend's shape (kabo-sh/kabo#2474): 24 frames at fixed moments of an 18-minute video, no
// overview, the first 60 s measured (also carried as the frames' signals) and, without platform captions, the first
// 180 s heard.
const QUICK_TIMES = [0, 1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 540, 660, 780, 900, 960, 1020, 1075];
const COVERED = (to) => ({ mode: "partial", covered_s: [0, to], duration_s: 1080.2 });
function quickComposite(args, { captions = false } = {}) {
  const value = composite(args, { duration: 1080 });
  for (const call of value.calls) {
    const result = call.result;
    if (result.operation === "extract_keyframes") {
      const frames = QUICK_TIMES.map((t, i) => ({ frame_id: `frame-quick-${String(i).padStart(3, "0")}`, t_seconds: t, bytes: 100,
        sha256: "c".repeat(64), object_ref: `creator-media/${result.job_id}/epoch-1/frame-quick-${String(i).padStart(3, "0")}.jpg` }));
      result.data = { frame_count: 24, selection: "quick_sample_v1", duration_s: 1080.2, sampling_plan: null,
        sampling: { mode: "quick", above_s: 180, frames: 24, duration_s: 1080.2, times_s: QUICK_TIMES }, frames,
        artifacts: frames.map((f) => ({ kind: "keyframes", bytes: 100, sha256: f.sha256, object_ref: f.object_ref })),
        signals: { shots: { count: 2, cuts_at_s: [12.5], shots: [{ start_s: 0, end_s: 12.5 }, { start_s: 12.5, end_s: 60 }] }, coverage: COVERED(60) } };
      result.limitations = ["Quick sample: 24 frames at fixed moments across the video; the full pass was not run."];
    } else if (result.operation === "measure_media_signals") {
      result.data.coverage = COVERED(60);
    } else if (result.operation === "fetch_transcript") {
      if (captions) result.data.origin = "platform_captions";
      else result.data.coverage = COVERED(180);
    }
  }
  return value;
}
async function quickRun(t, mode, options) {
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", mode, "--question", "",
    "--confirmed-by-user"]);
  const { out } = await driveWith(run, begun.out, { media: (args) => quickComposite(args, options), side: { identify_video_song: SONG.noMatch } });
  return { run, out, evidence: await readJson(path.join(run, "analysis/content_evidence.json")), brief: await readBrief(run) };
}

test("quick first read: the sample, the speech heard and the measured opening reach the evidence, and the brief states them with the rule and, for a diagnosis, leaves the offer to the report", async (t) => {
  const { run, out, evidence, brief } = await quickRun(t, "diagnosis");
  assertValidEvidence(evidence);
  assert.equal(evidence.frames.selection, "quick_sample_v1");
  assert.deepEqual(evidence.frames.sampling, { mode: "quick", above_s: 180, frames: 24, duration_s: 1080.2, times_s: QUICK_TIMES });
  assert.deepEqual(evidence.transcript.coverage, COVERED(180));
  assert.deepEqual(evidence.media.probed.coverage, COVERED(60));
  assert.equal(evidence.frames.items.length, 24);
  assert.ok(out.includes("### Quick first read of a long video"), "the printed brief carries it");
  const index = section(brief, 3);
  assert.match(index, /### Quick first read of a long video\n\n- Frames: 24 frames at fixed moments across the 18-minute video \(0s, 1s, 2s, .*, 1075s\), not the full pass\. Nothing between those moments was seen\./);
  assert.match(index, /- Speech: heard only for 0s–180s \(`transcript\.coverage`\); nothing said after that was heard\./);
  assert.match(index, /- Measurements \(cuts, silence, freezes, framing, brightness, loudness\): the first 60s only \(`media\.probed\.coverage`\), not the whole 1080\.2s\./);
  assert.match(index, /- Rule: frame any judgment about a stretch that was not sampled as not observed in this quick read\./);
  assert.match(index, /The final step closes the report with one paragraph saying this was a quick first read/);
  assert.doesNotMatch(index, /with this paragraph/);
  // The report's closing paragraph comes from the same facts.
  const quick = JSON.parse(spawnSync("python3", ["-I", "-B", "-c", "import json, sys; sys.path.insert(0, sys.argv[1]); "
    + "import report_locale as r; print(json.dumps(r.quick_read(json.load(open(sys.argv[2])))))", scripts,
  path.join(run, "analysis/content_evidence.json")], { encoding: "utf8" }).stdout);
  assert.deepEqual(quick, { duration_s: 1080.2, minutes: 18, frames: 24, speech: "partial", heard_minutes: 3, eta_minutes: 3 });
});

test("quick first read, content read and craft teardown: the brief hands over the closing offer word for word in every report language; platform captions are named as whole", async (t) => {
  for (const mode of ["content_read", "craft_teardown"]) {
    const { evidence, brief } = await quickRun(t, mode, { captions: true });
    assertValidEvidence(evidence);
    assert.equal("coverage" in evidence.transcript, false);
    const index = section(brief, 3);
    assert.match(index, /- Speech: the platform's captions, for the whole video\./);
    assert.match(index, mode === "craft_teardown"
      ? /- End the report with this paragraph, after its line on what it rests on, unchanged, in the creator's language/
      : /- End your answer with this paragraph, after any other offer, unchanged, in the creator's language/);
    assert.ok(index.includes("  - zh: 这是对这条 18 分钟视频的快速初看：全片抽看了 24 张画面，台词用的是平台字幕。完整分析大约需要 3 分钟，会再用一次视频额度；回复“深度分析”即可开始。"), mode);
    assert.ok(index.includes("  - en: This is a quick first read of this 18-minute video: 24 frames sampled across it, the speech from the platform's captions. A full analysis takes about 3 minutes and uses one more video credit; reply \"full analysis\" to start it."), mode);
    assert.equal(index.match(/^  - [a-z]{2}: /gm).length, 12);
    assert.doesNotMatch(index, /The final step closes the report/);
  }
});

test("a full pass (no sampling block, no coverage) adds no quick lines and no offer", async (t) => {
  const { run, begun } = await beginInWorkspace(t, ["--url", TIKTOK, "--subject-state", "unknown", "--mode", "content_read", "--question", "",
    "--confirmed-by-user"]);
  await driveWith(run, begun.out);
  const brief = await readBrief(run);
  assert.doesNotMatch(brief, /Quick first read|full analysis/);
});

test("quick first read, diagnosis end to end: the finished report ends with the offer and passes every gate", async (t) => {
  const { run } = await quickRun(t, "diagnosis");
  const judgment = { ...JUDGMENT, observations: [{ ...JUDGMENT.observations[0], evidence_refs: ["frame-quick-000"] }] };
  await writeFile(path.join(run, "analysis/video_judgment.json"), JSON.stringify(judgment));
  await writeFile(path.join(run, "analysis/creator_view.json"), JSON.stringify(creatorView()));
  const finished = python("finish_diagnosis.py", ["--run-dir", run, "--check", "--finish-if-ready"], run);
  assert.equal(finished.code, 0, finished.out);
  const report = await readFile(path.join(run, "report/VIDEO_DIAGNOSIS.md"), "utf8");
  assert.equal(report.trimEnd().split("\n\n").at(-1), "This is a quick first read of this 18-minute video: 24 frames sampled across it, the speech heard "
    + "for the first 3 minutes only. A full analysis takes about 3 minutes and uses one more video credit; reply \"full analysis\" to start it.");
  const result = await readJson(path.join(run, "analysis/creator-task-result.json"));
  assert.deepEqual(result.details.quick_read, { duration_s: 1080.2, minutes: 18, frames: 24, speech: "partial", heard_minutes: 3, eta_minutes: 3 });
  assert.match(result.creator_view.data_note, /^TikTok video; 24 extracted frames; 1 cited frame refs; /);
});
