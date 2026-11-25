// analyze-content-video "content read" regression.
// Origin: a Reel with only background music and no voice-over was asked "what does this video say"; only the
// transcript was fetched, the machine transcribed the lyrics as if they were spoken, and the answer summarised
// the lyrics as the video's content. The mode table used to have only diagnosis / craft teardown / transcript
// export, and "what does it say" was the easiest to file under transcript export.
// Pinned here: a question about content is a content read (transcript + frames + metadata), a transcript export
// only when a file is wanted, and machine-heard words are first treated as possible lyrics when an existing track
// plays or nobody on screen is speaking. The content-read rules now reach the model through the analysis brief
// (the output-content-read section of references/analysis-brief.md), so they are checked there.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const skillDir = path.join(root, "skills/analyze-content-video");
const skill = readFileSync(path.join(skillDir, "SKILL.md"), "utf8");
const briefTexts = readFileSync(path.join(skillDir, "references/analysis-brief.md"), "utf8");
const contentRead = briefTexts.split(/^<!-- section: output-content-read -->\n/m)[1].split(/^<!-- section: /m)[0];
const description = skill.match(/^description: "(.*)"$/m)[1];
const section = (heading) => {
  const start = skill.indexOf(`\n## ${heading}\n`);
  assert.notEqual(start, -1, `missing ## ${heading}`);
  const end = skill.indexOf("\n## ", start + 4);
  return skill.slice(start, end === -1 ? undefined : end);
};

test("the description says 'what a video is about or says', so the catalogue can select it", () => {
  assert.match(description, /what a video is about or says/);
  // KS1.2: over 500 characters warns and eats into the host's skill-list budget.
  assert.ok(description.length <= 500, `description is ${description.length} characters`);
});

test("mode table: a question about content is a content read; transcript export only takes requests for a file", () => {
  const table = section("Which question is this");
  assert.match(table, /\| What it is about or says .*\| \*\*Content read\*\* \|/);
  assert.match(table, /\| The words themselves as a file .*\| \*\*Transcript export\*\* \(below\) \|/);
  assert.match(table, /"what does it say" are a content\s+read, not a transcript export/);
  assert.match(table, /machine-heard words can\s+be a song's lyrics/);
});

test("a content read observes transcript and frames (plus metadata off YouTube)", async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), "kabo-acv-read-"));
  t.after(() => rm(workspace, { recursive: true, force: true }));
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
  delete env.KABO_STATIC_RUN_DIR;
  const py = (args, cwd) => spawnSync("python3", ["-B", ...args], { cwd, encoding: "utf8", env });
  for (const [url, expected] of [
    ["https://www.instagram.com/reel/DeZrE2phzDx/", ["collect_public_metadata", "fetch_transcript", "extract_keyframes"]],
    ["https://www.youtube.com/watch?v=fixture0001", ["fetch_transcript", "extract_keyframes"]],
  ]) {
    const run = py([path.join(skillDir, "scripts/static_host.py"), "init", "--workspace", workspace], workspace).stdout.trim();
    const out = py([path.join(skillDir, "scripts/observe_video.py"), "--url", url, "--mode", "content_read"], run).stdout;
    const call = out.split("\n").filter((line) => line.startsWith("call: ")).map((line) => JSON.parse(line.slice(6)))
      .find((item) => item.tool === "collect_video_media");
    assert.ok(call, out);
    assert.deepEqual(call.arguments.requests.map((request) => request.operation), expected, url);
  }
});

test("a content read writes no report, and heard words are first checked for lyrics", () => {
  const analysis = section("Analysis");
  assert.match(analysis, /A content read sets `acquire\.owner_metrics` to `skip`/);
  assert.match(analysis, /A content read writes no report and is never called a diagnosis/);
  assert.match(contentRead, /seen in a frame, read from on-screen text or the caption, heard/);
  assert.match(contentRead, /`audio_attribution` names an existing track/);
  assert.match(contentRead, /may\s+be that track's lyrics/);
  assert.match(contentRead, /never summarize its words as the video's\s+message/);
  assert.match(contentRead, /writes no report/);
  // Without a declared track, the rule names what to decide from instead of leaving the trigger unknowable.
  assert.match(contentRead, /When `audio_attribution` is unavailable, decide from what the run has/);
  assert.match(contentRead, /acv_timing\.py answer --run '<run directory>' --answer analysis\/answer\.md/);
  // The delivery note at the top only constrains the diagnosis report; a content read answers from the evidence
  // and must not be blocked by that sentence.
  assert.match(skill, /A content read has no report: it answers from the evidence/);
});

test("mode table: find the track is its own row, with one song recognition call, no sound card and no whole-video viewing", () => {
  const table = section("Which question is this");
  assert.match(table, /\| Which song or track it uses .*\| \*\*Find the track\*\*: a content read with `--ask identify_track` in step 2: one song recognition call for a link; no `sound` card, no whole-video viewing \|/);
  assert.match(table, /answered from the song recognition's match, else metadata,\non-screen text and speech, never by ear/);
  assert.match(skill, /select_method\.py --mode <diagnosis\|content_read\|craft_teardown> \[--focus <id>\[,<id>\]\] \[--ask identify_track\]/);
  const index = readFileSync(path.join(skillDir, "references/video-method/index.md"), "utf8");
  assert.match(index, /"What song is this\?" is a find-the-song request, not the `sound` card/);
});

test("reply hygiene: nothing but the prescribed text reaches the creator, and never an internal name", () => {
  assert.match(skill, /\*\*Nothing else reaches the creator\.\*\* Before the final answer, write no text to the creator but what\s+this Skill prescribes/);
  assert.match(skill, /never names a Skill id, script, file or evidence\s+field/);
  // The next-step line names what would help in plain words, not another Skill's id.
  assert.doesNotMatch(skill, /`(?:review-creator-account|develop-content-ideas|create-script-and-packaging)`/);
  assert.match(briefTexts, /\*\*Plain words for the creator\.\*\*/);
});

// Long videos in two steps: a quick first read whose answer offers the full analysis, which runs only on consent.
test("long videos: the full analysis runs only when the creator accepted the offer or a host says it is ready, never at or under 3 minutes", () => {
  const analysis = section("Analysis");
  assert.match(analysis, /\[--depth deep\]/);
  const long = analysis.slice(analysis.indexOf("**Long videos.**")).replace(/\s+/g, " ");
  assert.match(long, /over 3 minutes is read quickly first, and its answer ends with an offer of the full analysis \(one more video credit\)/);
  assert.match(long, /a new run from step 1 with `--duration-s` from the first result/);
  assert.match(long, /only when the creator accepted that offer \(any wording, any language\) or a host message says the deep analysis is ready, never for 3 minutes or less/);
  const runtime = readFileSync(path.join(skillDir, "references/diagnosis-runtime.md"), "utf8");
  const part = runtime.slice(runtime.indexOf("## Long videos in two steps"), runtime.indexOf("## When part of the media is out of reach")).replace(/\s+/g, " ");
  assert.match(part, /`deep_pending`/);
  assert.match(part, /Write no report or answer about the video in that turn\. When they say continue, run the one command it printed/);
  assert.match(part, /its credit note is the one mention of credits a reply makes/);
});
