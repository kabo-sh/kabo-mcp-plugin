// analyze-content-video local speech recognition (transcribe_local.py): an optional tier the creator installs. The
// tests are offline and never load a real model: a stand-in `faster_whisper` package (and a stand-in `numpy`, so
// the test does not depend on it) is put first on PYTHONPATH, and the missing-dependency path runs Python without
// site-packages. ffmpeg decodes the audio, as in a real run.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills/analyze-content-video/scripts");
const hasFfmpeg = spawnSync("ffmpeg", ["-version"]).status === 0;
const baseEnv = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
delete baseEnv.KABO_STATIC_RUN_DIR;

const STUB_WHISPER = String.raw`
class Word:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word

class Segment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words

class Info:
    language = "en"

class WhisperModel:
    def __init__(self, name, device=None, compute_type=None, local_files_only=None):
        # The Skill's settings: the small model, int8 on the CPU, and never a download.
        assert (name, device, compute_type, local_files_only) == ("small", "cpu", "int8", True)

    def transcribe(self, audio, language=None, vad_filter=None, word_timestamps=None):
        assert vad_filter is True and word_timestamps is True
        segments = [Segment(0.0, 1.25, " Hello there.", [Word(0.0, 0.5, " Hello"), Word(0.5, 1.25, " there.")]),
                    Segment(1.5, 1.9, "   ", []),
                    Segment(2.0, 2.75, "Second line", [])]
        return iter(segments), Info()
`;
const STUB_NUMPY = String.raw`
int16, float32 = "int16", "float32"

class _Samples:
    def astype(self, kind):
        return self

    def __truediv__(self, other):
        return self

def frombuffer(raw, dtype=None):
    return _Samples()
`;

async function workspace(t) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-asr-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  await mkdir(path.join(dir, "stubs/faster_whisper"), { recursive: true });
  await mkdir(path.join(dir, "stubs/numpy"), { recursive: true });
  await writeFile(path.join(dir, "stubs/faster_whisper/__init__.py"), STUB_WHISPER);
  await writeFile(path.join(dir, "stubs/numpy/__init__.py"), STUB_NUMPY);
  return dir;
}
const run = (args, { cwd, stubs, noSite = false, extraEnv = {} } = {}) => {
  const env = { ...baseEnv, ...extraEnv, ...(stubs ? { PYTHONPATH: stubs } : {}) };
  const result = spawnSync("python3", [...(noSite ? ["-S"] : []), "-B", ...args], { cwd, encoding: "utf8", env });
  return { code: result.status, stdout: result.stdout, stderr: result.stderr };
};
const media = async (dir, { audio = true } = {}) => {
  const file = path.join(dir, audio ? "clip.mp4" : "silent.mp4");
  const args = ["-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x284:rate=10",
    ...(audio ? ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest"] : []), "-pix_fmt", "yuv420p", file];
  assert.equal(spawnSync("ffmpeg", args).status, 0);
  return file;
};

test("missing faster-whisper: exit 3, nothing written, and the one install line for the creator", async (t) => {
  const dir = await workspace(t);
  await writeFile(path.join(dir, "clip.mp4"), "not really a video");
  const artifact = path.join(dir, "local-transcript.json");
  const result = run([path.join(scripts, "transcribe_local.py"), "--media", path.join(dir, "clip.mp4"), "--artifact", artifact],
    { cwd: dir, noSite: true });
  assert.equal(result.code, 3, result.stdout + result.stderr);
  assert.match(result.stderr, /^MISSING: faster_whisper/m);
  assert.match(result.stderr, /python3 -m pip install faster-whisper && python3 -c "from faster_whisper import WhisperModel; WhisperModel\('small', device='cpu', compute_type='int8'\)"/);
  assert.equal(JSON.parse(result.stdout).status, "missing");
  await assert.rejects(readFile(artifact));
  // The probe reports the same state and the same line; it never installs anything.
  const probe = JSON.parse(run([path.join(scripts, "probe_media_tools.py")], { cwd: dir, noSite: true }).stdout);
  const row = probe.tools.find((item) => item.key === "faster_whisper");
  assert.equal(row.state, "absent");
  assert.match(row.install_hint, /pip install faster-whisper/);
  assert.equal(probe.can_transcribe_locally, false);
});

test("probe: the package without its model is model_missing; with the model in the cache it is available", async (t) => {
  const dir = await workspace(t);
  const cache = path.join(dir, "hub");
  const probe = () => JSON.parse(run([path.join(scripts, "probe_media_tools.py")], { cwd: dir, stubs: path.join(dir, "stubs"),
    extraEnv: { HF_HUB_CACHE: cache } }).stdout);
  assert.equal(probe().tools.find((item) => item.key === "faster_whisper").state, "model_missing");
  await mkdir(path.join(cache, "models--Systran--faster-whisper-small/snapshots/abc"), { recursive: true });
  await writeFile(path.join(cache, "models--Systran--faster-whisper-small/snapshots/abc/model.bin"), "x");
  const ready = probe();
  assert.equal(ready.tools.find((item) => item.key === "faster_whisper").state, "available");
  assert.equal(ready.can_transcribe_locally, true);
});

test("timestamps: a segment becomes a cue in seconds from the file's start, words kept, offset added", () => {
  const code = String.raw`
import json, sys, types
sys.path.insert(0, sys.argv[1])
import transcribe_local as t
word = types.SimpleNamespace
segment = types.SimpleNamespace(start=1.2344, end=2.5, text="  Hi you ", words=[word(start=1.2344, end=1.6, word=" Hi"), word(start=1.7, end=2.5, word=" you"), word(start=2.5, end=2.5, word=" ")])
sure = types.SimpleNamespace(start=0, end=1, text="Sure", words=[], avg_logprob=-0.23456, no_speech_prob=0.0412)
print(json.dumps([t.cue_from_segment(segment, 0.0), t.cue_from_segment(segment, 12.5), t.cue_from_segment(types.SimpleNamespace(start=0, end=1, text=" ", words=[]), 0.0), t.cue_from_segment(sure, 0.0)]))
`;
  const result = run(["-c", code, scripts]);
  assert.equal(result.code, 0, result.stderr);
  const [plain, shifted, empty, sure] = JSON.parse(result.stdout);
  assert.deepEqual(plain, { start_s: 1.234, end_s: 2.5, text: "Hi you",
    words: [{ start_s: 1.234, end_s: 1.6, text: "Hi" }, { start_s: 1.7, end_s: 2.5, text: "you" }] });
  assert.equal(shifted.start_s, 13.734);
  assert.equal(shifted.words[1].end_s, 15);
  assert.equal(empty, null);
  // The recogniser's confidence is kept per cue when the segment carries it, for the audio measurement.
  assert.deepEqual(sure, { start_s: 0, end_s: 1, text: "Sure", avg_logprob: -0.235, no_speech_prob: 0.041 });
});

test("transcript artifact: the subtitle reader's shape with origin speech_recognition, and the builder reads it", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = await media(dir);
  const artifact = path.join(dir, "local-transcript.json");
  const result = run([path.join(scripts, "transcribe_local.py"), "--media", file, "--artifact", artifact], { cwd: dir, stubs: path.join(dir, "stubs") });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const written = JSON.parse(await readFile(artifact, "utf8"));
  assert.equal(written.schema_version, "local-transcript.v1");
  assert.equal(written.origin, "speech_recognition");
  assert.equal(written.status, "available");
  assert.equal(written.granularity, "timestamped");
  assert.equal(written.language, "en");
  assert.equal(written.complete, true);
  assert.ok(Math.abs(written.transcribed_until_s - 3) < 0.1, String(written.transcribed_until_s));
  assert.deepEqual(written.cues.map((cue) => [cue.start_s, cue.end_s, cue.text]), [[0, 1.25, "Hello there."], [2, 2.75, "Second line"]]);
  assert.equal(written.cues[0].words.length, 2);
  assert.deepEqual(written.steps.map((step) => [step.step, step.operation, step.status]), [["local_extraction", "transcribe_local", "completed"]]);
  assert.match(written.steps[0].input_sha256, /^[0-9a-f]{64}$/);
  // The file name, never the creator's path, goes into the artifact.
  assert.doesNotMatch(JSON.stringify(written), new RegExp(dir.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  // The evidence builder carries it as machine-heard words.
  const runDir = run([path.join(scripts, "static_host.py"), "init", "--workspace", dir]).stdout.trim();
  const frames = run([path.join(scripts, "extract_local_frames.py"), "--media", file, "--out-dir", "analysis/frames", "--artifact", "analysis/local-media.json",
    "--hook-window-s", "3"], { cwd: runDir });
  assert.equal(frames.code, 0, frames.stdout + frames.stderr);
  await writeFile(path.join(runDir, "analysis/video-analysis-request.json"), JSON.stringify({
    schema_version: "video-analysis-request.v1", request_id: "req-asr",
    source: { acquisition: "local_file", subject_state: "own_unpublished", platform: "tiktok", url: null, content_id: null,
      declared_format: "video", owner_data: null, file_ref: file },
    acquire: { media: "best_effort", transcript: "best_effort", frames: "best_effort", owner_metrics: "skip" },
    budget: { max_connector_calls: 0, max_provider_credits: null, confirmed_by_user: true, per_call: { timeout_seconds: 60, max_response_bytes: 50000000 } },
    failure_policy: { on_missing_capability: "return_partial", fatal_capabilities: [] } }));
  const built = run([path.join(scripts, "build_content_evidence.py"), "--request", "analysis/video-analysis-request.json", "--local-media",
    "analysis/local-media.json", "--local-transcript", artifact, "--output", "analysis/content_evidence.json"], { cwd: runDir });
  assert.equal(built.code, 0, built.stdout + built.stderr);
  const evidence = JSON.parse(await readFile(path.join(runDir, "analysis/content_evidence.json"), "utf8"));
  assert.equal(evidence.transcript.status, "available");
  assert.equal(evidence.transcript.origin, "speech_recognition");
  assert.deepEqual(evidence.transcript.cues, [{ start_s: 0, text: "Hello there." }, { start_s: 2, text: "Second line" }]);
});

test("time limit: it stops before the host does, says so, and the same command continues to the end", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = await media(dir);
  const artifact = path.join(dir, "local-transcript.json");
  const args = [path.join(scripts, "transcribe_local.py"), "--media", file, "--artifact", artifact];
  const first = run([...args, "--deadline-s", "1"], { cwd: dir, stubs: path.join(dir, "stubs") });
  assert.equal(first.code, 0, first.stdout + first.stderr);
  assert.match(first.stdout, /run the same command again to continue from 0s/);
  const partial = JSON.parse(await readFile(artifact, "utf8"));
  assert.equal(partial.complete, false);
  assert.equal(partial.status, "partial");
  const second = run(args, { cwd: dir, stubs: path.join(dir, "stubs") });
  assert.equal(second.code, 0, second.stdout + second.stderr);
  const done = JSON.parse(await readFile(artifact, "utf8"));
  assert.equal(done.complete, true);
  assert.equal(done.status, "available");
  assert.equal(done.steps.length, 2);
});

test("a file with no audio track is an answer (no_audio_track), not a failure", { skip: !hasFfmpeg }, async (t) => {
  const dir = await workspace(t);
  const file = await media(dir, { audio: false });
  const artifact = path.join(dir, "local-transcript.json");
  const result = run([path.join(scripts, "transcribe_local.py"), "--media", file, "--artifact", artifact], { cwd: dir, stubs: path.join(dir, "stubs") });
  assert.equal(result.code, 0, result.stdout + result.stderr);
  const written = JSON.parse(await readFile(artifact, "utf8"));
  assert.equal(written.status, "no_audio_track");
  assert.equal(written.cues, null);
});
