// Clock times in the publish-time report: when a recommendation is given, the title or summary must state the
//   recommended window as HH:MM and not state any clock time outside the window; when a single hour is given,
// the winning segment of the chunked vote must not appear in the body as a time range (in one migration run
//   the report title recommended 18:00 while "how it was compared" said 06:00-09:00
// did best). When the creator's time zone was not obtained, the model must write creator_view.clock_note in
//   the creator's language, and the renderer places it below the answer.
// The rules look only at structure (HH:MM, adjacent hours, whether a field is present) and recognize no
//   literal in any language. This only checks the errors of these rules.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "recommend-publish-timing", "scripts");

function recommendation({ source = "creator_confirmed", start = "18:00", end = "19:00", resolution = "hour", winner = "06-09", outcome = "recommended" } = {}) {
  return {
    outcome,
    recommendation: { windows: outcome === "recommended" ? [{ weekday: "all", start_local: start, end_local: end, zone: "America/New_York", resolution, supporting_n: 5 }] : [],
      confidence_penalties: [] },
    evidence_base: {
      timezone: { analysis_zone: source === "creator_confirmed" ? "America/New_York" : "UTC", source, note: null },
      ranking: { granularity_hours: 3, winner, windows: [] },
      signals: [], hour_curve: { hours: {} }, cohort: {}, practical_stakes: {},
    },
  };
}

function result({ headline = "Post the next one at 18:00", summary = "Across your last 40 posts the 18:00 hour has the highest median views.",
  lines = [], next = [], clockNote, language = "en" } = {}) {
  return {
    schema_version: "creator-task-result.v2-final", result_id: "r1", task: "recommend_publish_timing", status: "complete",
    details: {}, evidence_index: [], interaction: {},
    creator_view: {
      language, headline, summary, data_note: "", ...(clockNote ? { clock_note: clockNote } : {}),
      cards: [{ title: "How it was compared", why_for_you: lines.join("\n"), action: "Schedule the next post for 18:00.", evidence_refs: ["hour_curve"] }],
      next_actions: next,
    },
  };
}

async function validate(t, rec, res) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-timing-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  await writeFile(path.join(dir, "rec.json"), JSON.stringify(rec));
  await writeFile(path.join(dir, "result.json"), JSON.stringify(res));
  const out = spawnSync("python3", [path.join(scripts, "validate_creator_shape.py"), path.join(dir, "result.json"), path.join(dir, "rec.json")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return out.stdout + out.stderr;
}

const clockErrors = (out) => out.split("\n").filter((line) => /block vote|outside the recommended|states the recommended time|clock_note/.test(line));

test("when a single hour is answered, a body that reports the chunk-winning window is rejected regardless of connector language, and overlap with the recommended hour is also rejected", async (t) => {
  for (const range of ["06:00–09:00", "06:00 à 09:00", "06:00 至 09:00", "06:00 to 09:00"]) {
    const out = await validate(t, recommendation(), result({ lines: [`${range} performs best overall.`, "The 18:00 hour is carried by five posts."] }));
    const errors = clockErrors(out);
    assert.equal(errors.length, 1, `${range}\n${out}`);
    assert.match(errors[0], /06:00–09:00, the 3-hour block vote/);
    assert.match(errors[0], /18:00–19:00/);
  }
  const overlap = await validate(t, recommendation({ start: "07:00", end: "08:00" }),
    result({ headline: "Post the next one at 07:00", summary: "The 07:00 hour leads your own history.", lines: ["06:00–09:00 performs best overall.", "The 07:00 hour is carried by five posts."] }));
  assert.equal(clockErrors(overlap).length, 1, overlap);
});

test("title or summary reporting the recommended window: error when there is no clock hour; a controlled experiment may appear in the next step", async (t) => {
  const out = await validate(t, recommendation(), result({ lines: ["The 18:00 hour is carried by five posts.", "The three-hour block vote did not pick this block."],
    next: ["Try two posts at 20:00 to test the hour your peers use."] }));
  assert.deepEqual(clockErrors(out), [], out);
});

test("title or summary reporting an hour outside the window is rejected; reporting no recommended time in either place is also rejected", async (t) => {
  const outside = await validate(t, recommendation(), result({ headline: "Post the next one at 06:00", summary: "Around 07:00 does better." }));
  const errors = clockErrors(outside);
  assert.ok(errors.some((line) => /^ERROR: headline states 06:00/.test(line)), outside);
  assert.ok(errors.some((line) => /^ERROR: summary states 07:00/.test(line)), outside);
  assert.ok(errors.some((line) => /neither the headline nor the summary states the recommended time/.test(line)), outside);
  const silent = await validate(t, recommendation(), result({ headline: "Post in the evening", summary: "Your own history favours the evening hour over the rest of the day." }));
  assert.equal(clockErrors(silent).length, 1, silent);
});

test("when chunks are answered, reporting that chunk is not a conflict", async (t) => {
  const out = await validate(t, recommendation({ start: "06:00", end: "09:00", resolution: "3h" }),
    result({ headline: "Post the next one between 06:00 and 09:00", summary: "On three-hour blocks, 06:00–09:00 collects the most votes.", lines: ["06:00–09:00 performs best overall."] }));
  assert.deepEqual(clockErrors(out), [], out);
});

test("fallback clock hours: a result with clock hours must carry clock_note and must not name a time zone; results with a known time zone or without clock hours do not require it", async (t) => {
  const missing = await validate(t, recommendation({ source: "not_supplied" }), result());
  assert.ok(clockErrors(missing).some((line) => /creator_view\.clock_note is missing/.test(line)), missing);
  const unresolved = await validate(t, recommendation({ source: "zone_unresolved", outcome: "no_clear_window" }), result({ headline: "Post now", summary: "No hour in your history stands out from the rest of the day." }));
  assert.ok(clockErrors(unresolved).some((line) => /clock_note is missing/.test(line)), unresolved);
  const written = await validate(t, recommendation({ source: "not_supplied" }), result({ clockNote: "These hours are not confirmed as your local time; tell me your city and I will recompute them." }));
  assert.deepEqual(clockErrors(written), [], written);
  const zoned = await validate(t, recommendation({ source: "not_supplied" }), result({ clockNote: "These hours are UTC, not your local time." }));
  assert.match(zoned, /clock_note names a timezone/);
  const typed = await validate(t, recommendation({ source: "not_supplied" }), { ...result(), creator_view: { ...result().creator_view, clock_note: true } });
  assert.match(typed, /clock_note must be a string, not bool/);
  const known = await validate(t, recommendation(), result());
  assert.deepEqual(clockErrors(known), [], known);
  const abstain = await validate(t, recommendation({ source: "not_supplied", outcome: "abstain_no_history" }), result({ headline: "Not enough history yet", summary: "There are too few mature posts to compare any hour of the day." }));
  assert.deepEqual(clockErrors(abstain), [], abstain);
});

test("the renderer places clock_note verbatim below the answer, and omits it when absent", async (t) => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-timing-render-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const render = async (res) => {
    await writeFile(path.join(dir, "rec.json"), JSON.stringify(recommendation({ source: "not_supplied" })));
    await writeFile(path.join(dir, "result.json"), JSON.stringify(res));
    const code = "import json,sys; sys.path.insert(0, sys.argv[1]); import render_timing_report as r; "
      + "print(r.creator_view(json.load(open(sys.argv[3])), json.load(open(sys.argv[2]))), end='')";
    const out = spawnSync("python3", ["-c", code, scripts, path.join(dir, "rec.json"), path.join(dir, "result.json")],
      { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
    assert.equal(out.status, 0, out.stdout + out.stderr);
    return out.stdout;
  };
  const note = "Ces heures ne sont pas votre heure locale ; donnez-moi votre ville pour les recalculer.";
  const lines = (await render(result({ clockNote: note, language: "fr" }))).split("\n").filter(Boolean);
  assert.equal(lines[2], `> ${note}`);
  assert.doesNotMatch(await render(result()), /^> /m);
});
