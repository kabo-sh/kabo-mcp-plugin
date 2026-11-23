// analyze-content-video: the report-side fixes from the observation bake-off, checked on the scripts' own functions.
// Each probe runs the Skill's Python with -I -B and prints JSON; nothing touches the network.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, realpath, rm, writeFile, mkdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
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

// Creators write in many languages. A view in a language listed in references/report-locales.json renders the
// report's own labels and its data_note in that language, by the tag's primary subtag; any other renders in English.
const LOCALIZED = {
  es: { tag: "es-MX", action: "Qué cambiar", next: "Siguientes pasos", source: "Video de YouTube", unknown: "desconocido" },
  pt: { tag: "pt-BR", action: "O que mudar", next: "Próximos passos", source: "Vídeo do YouTube", unknown: "desconhecido" },
  de: { tag: "de", action: "Was du ändern solltest", next: "Nächste Schritte", source: "YouTube-Video", unknown: "unbekannt" },
  fr: { tag: "fr-FR", action: "Ce qu'il faut changer", next: "Prochaines étapes", source: "Vidéo YouTube", unknown: "inconnu" },
  ja: { tag: "ja-JP", action: "変えること", next: "次にやること", source: "YouTubeの動画", unknown: "不明" },
  ko: { tag: "ko", action: "바꿀 점", next: "다음 단계", source: "YouTube 영상", unknown: "알 수 없음" },
  id: { tag: "id-ID", action: "Yang perlu diubah", next: "Langkah berikutnya", source: "Video YouTube", unknown: "tidak diketahui" },
  vi: { tag: "vi-VN", action: "Cần thay đổi gì", next: "Bước tiếp theo", source: "Video YouTube", unknown: "không rõ" },
  ar: { tag: "ar-SA", action: "ما الذي تغيّره", next: "الخطوات التالية", source: "فيديو YouTube", unknown: "غير معروف" },
  hi: { tag: "hi-IN", action: "क्या बदलें", next: "अगले कदम", source: "YouTube वीडियो", unknown: "अज्ञात" },
};
const LOCALE_EVIDENCE = `
evidence = {"content_ref": {"platform": "youtube"}, "owner_metrics": {"status": "unavailable"},
            "transcript": {"status": "available", "origin": "platform_captions",
                           "cues": [{"start_s": i, "text": "line"} for i in range(108)]},
            "frames": {"status": "available", "origin": "extracted_frames", "sampling_plan": {"frames": 14},
                       "items": [{"frame_id": f"f{i}", "t_seconds": i} for i in range(14)]}}
analysis = {"observations": [{"observation_id": "o1", "evidence_refs": ["f0", "f1"]}]}
def view(language):
    card = {"title": "T", "why_for_you": "a\\nb\\nc", "action": "do it", "evidence_refs": ["observations.o1"]}
    hook = {"purpose": "p", "visual_direction": "close-up", "on_screen_text": "words", "spoken_line": "line"}
    return {"language": language, "headline": "H", "summary": "S",
            "cards": [dict(card), dict(card), dict(card, hooks=[hook])], "next_actions": ["go"]}
`;

test("report labels and data_note: es, pt, de, fr, ja, ko, id, vi, ar and hi render in their own language; an unlisted one in English", () => {
  const tags = Object.values(LOCALIZED).map((entry) => entry.tag).concat(["nl", "en"]);
  const out = probe(`
from creator_measurement_basis import canonical_note, note_matches
from render_video_report import render
from build_creator_result import build
from report_locale import LOCALES
${LOCALE_EVIDENCE}
images = {"media_type": "image_carousel", "returned_count": 5, "expected_count": None, "completeness": "unknown",
          "items": [{"status": "available"}] * 4 + [{"status": "unavailable"}]}
english = canonical_note(evidence, analysis, view("en"))
out = {"locales": sorted(LOCALES), "english": english}
for tag in ${JSON.stringify(tags)}:
    v = view(tag)
    note = canonical_note(evidence, analysis, v)
    v["data_note"] = note
    image = build({"creator_view": view(tag)}, analysis, {"images": images, "owner_metrics": {"status": "unavailable"}},
                  {"source": {"acquisition": "public_url"}})["creator_view"]["data_note"]
    out[tag] = {"note": note, "image": image,
                "own": render({"creator_view": v, "details": {"subject_state": "own_published"}}),
                "theirs": render({"creator_view": v, "details": {"subject_state": "third_party"}}),
                "matches": note_matches(note, evidence, analysis, v),
                "older English line": note_matches(english, evidence, analysis, v),
                "pre-1.0.32 English line": note_matches(english[:-1] + "; viewing unverified.", evidence, analysis, v),
                "edited": note_matches(note.replace("14", "15"), evidence, analysis, v),
                "another language": note_matches(canonical_note(evidence, analysis, view("de" if tag != "de" else "fr")), evidence, analysis, v)}
print(json.dumps(out, ensure_ascii=False))`);
  assert.deepEqual(out.locales, ["ar", "de", "es", "fr", "hi", "id", "ja", "ko", "pt", "vi"]);
  const labels = (text) => [...text.matchAll(/\*\*([^*]+)\*\*(?: : |: |：)/g)].map((match) => match[1]);
  const catalog = JSON.parse(readFileSync(path.join(root, "skills/analyze-content-video/references/report-locales.json"), "utf8")).languages;
  for (const [code, expected] of Object.entries(LOCALIZED)) {
    const got = out[expected.tag];
    const words = catalog[code].labels;
    assert.deepEqual(labels(got.own), [words.reuse, words.fix, words.shot, words.on_screen, words.say, words.action], code);
    assert.deepEqual(labels(got.theirs), [words.reuse, words.avoid, words.shot, words.on_screen, words.say, words.yours], code);
    assert.ok(got.own.includes(`**${expected.action}**`), code);
    assert.ok(got.own.includes(`## ${expected.next}`), code);
    assert.doesNotMatch(got.own + got.theirs, /What to change|How to reuse it|How to avoid it|Say this|On screen|## Next/, code);
    // The data_note: same facts and numbers, in the creator's language, accepted by the measurement-basis check.
    assert.ok(got.note.startsWith(expected.source), `${code}: ${got.note}`);
    for (const figure of ["14", "2", "108"]) assert.ok(got.note.includes(figure), `${code}: ${figure} in ${got.note}`);
    assert.notEqual(got.note, out.english, code);
    assert.ok(got.own.includes(`*${got.note}*`), code);
    assert.equal(got.matches, true, code);
    assert.equal(got["older English line"], true, code);
    assert.equal(got["pre-1.0.32 English line"], true, code);
    assert.equal(got.edited, false, code);
    assert.equal(got["another language"], false, code);
    assert.ok(got.image.includes("4") && got.image.includes("5"), `${code}: ${got.image}`);
    assert.ok(got.image.includes(expected.unknown), `${code}: ${got.image}`);
    assert.doesNotMatch(got.image, /Image post|owner metrics/, code);
  }
  // Every listed language carries the same keys as Spanish, the first one added.
  for (const code of Object.keys(LOCALIZED)) {
    for (const part of ["labels", "note", "listen"]) {
      assert.deepEqual(Object.keys(catalog[code][part]).sort(), Object.keys(catalog.es[part]).sort(), `${code}.${part}`);
    }
    for (const part of ["frames", "transcript", "owner_status"]) {
      assert.deepEqual(Object.keys(catalog[code].note[part]).sort(), Object.keys(catalog.es.note[part]).sort(), `${code}.note.${part}`);
    }
    assert.deepEqual(Object.keys(catalog[code].listen.items).sort(), Object.keys(catalog.es.listen.items).sort(), `${code}.listen.items`);
  }
  // A language with no catalog entry, and English itself, keep the English wording.
  assert.equal(out.nl.note, out.english);
  assert.equal(out.en.note, out.english);
  assert.equal(out.nl.own, out.en.own);
  assert.match(out.nl.own, /\*\*What to change\*\*: do it/);
  assert.match(out.nl.image, /^Image post: 4\/5 returned positions available/);
  assert.equal(out.nl["another language"], false);
});

// A video the dense windows cover whole has no body grid: the plan's body interval is null (0.0 in local plans
// written before that), and the data_note still derives. The shape is the 13s local run that failed with "reduced
// sampling interval is unknown or invalid"; the server shape is the connector's plan with extras.
test("data_note: a plan whose frames all come from the opening, closing, shot starts and windows derives without a body interval", () => {
  const out = probe(`
from creator_measurement_basis import canonical_note, note_matches
from extract_local_frames import plan_frames
import select_method
${LOCALE_EVIDENCE}
local_run = {"base_interval_s": 1.0, "hook_window_s": 3.0, "hook_dense_window_s": 3.0, "hook_interval_s": 0.5,
             "hook_frames": 6, "body_interval_s": 0.0, "body_frames": 0, "closing_frame_s": 11.1, "budget": 120,
             "frames": 14, "body_degraded": False, "include_shot_starts": True, "shot_start_frames": 8,
             "dense_window_frames": 10,
             "dense_windows": [{"start_s": 0.0, "end_s": 13.1, "requested_interval_s": 0.5, "interval_s": 0.5,
                                "frames": 10, "clipped": True, "ignored": None}]}
local = dict(evidence, content_ref={}, media={"duration_source": "local_probe"},
             frames=dict(evidence["frames"], sampling_plan=local_run))
server = dict(evidence, frames=dict(evidence["frames"], sampling_plan=dict(
    local_run, body_interval_s=None, closing_frame_s=None, body_degraded=True)))
fresh = plan_frames(13.1, 3.0, 1.0, 2, 120, cuts=[], dense_windows=select_method.with_default_window([]))
def derive(item):
    try:
        note = canonical_note(item, analysis, view("en"))
        return [note, note_matches(note, item, analysis, view("en"))]
    except ValueError as error:
        return [str(error), None]
broken = dict(evidence, frames=dict(evidence["frames"], sampling_plan=dict(local_run, body_frames=3)))
stretched = dict(evidence, frames=dict(evidence["frames"], sampling_plan=dict(local_run, dense_windows=[
    dict(local_run["dense_windows"][0], interval_s=0)])))
print(json.dumps({"local": derive(local), "server": derive(server), "fresh": [fresh["body_interval_s"], fresh["body_frames"]],
                  "zh": canonical_note(local, analysis, view("zh")), "broken": derive(broken),
                  "window": derive(stretched)}, ensure_ascii=False))`);
  assert.deepEqual(out.local, ["Local video file; 14 extracted frames; 2 cited frame refs; platform captions (108 cues); owner metrics unavailable.", true]);
  assert.equal(out.server[1], true, out.server[0]);
  assert.match(out.server[0], /^YouTube video; 14 extracted frames;/);
  assert.match(out.zh, /^本地视频文件；抽取 14 帧/);
  assert.deepEqual(out.fresh, [null, 0], "a fresh local plan with no body grid writes null, as the connector does");
  // A body grid with no interval, or a laid window with none, is still refused.
  assert.deepEqual(out.broken, ["cannot derive data_note: reduced sampling interval is unknown or invalid", null]);
  assert.deepEqual(out.window, ["cannot derive data_note: dense window interval is unknown or invalid", null]);
});

// A local file's sound is measured, never heard: what only an ear can judge is the creator's to listen to. The
// builder derives one line for it from the evidence; the renderer prints it under the data note; the shape gate
// accepts it only as derived.
test("listen line: derived from a local sound measurement nobody heard, localized, rendered under the data note, never authored", () => {
  const out = probe(`
from build_creator_result import build
from render_video_report import render
from validate_creator_shape import check
${LOCALE_EVIDENCE}
audio = {"status": "available", "findings": [], "listen_check": [{"id": "genre_mood_fit", "ask": "What the music is."},
                                                                  {"id": "accents_on_cuts", "ask": "x"}],
         "voice": {"speech_s": 30.0, "reading": "bed under the voice"}, "onsets": {"count": 40}}
def built(tag, sound, viewer=None, authored=None):
    ev = dict(evidence, media={"audio": sound} if sound is not None else {})
    if viewer:
        ev["viewer_observations"] = {"status": viewer}
    v = view(tag)
    if authored:
        v["listen_note"] = authored
    return build({"creator_view": v}, analysis, ev, {"source": {"acquisition": "local_file"}}), ev
out = {}
for tag in ("zh-CN", "en", "es", "ja", "hi", "nl"):
    result, ev = built(tag, audio)
    out[tag] = {"line": result["creator_view"].get("listen_note"), "report": render(result)}
out["viewer heard it"] = "listen_note" in built("en", audio, viewer="available")[0]["creator_view"]
out["viewer failed"] = "listen_note" in built("en", audio, viewer="unavailable")[0]["creator_view"]
out["nothing to listen for"] = "listen_note" in built("en", dict(audio, listen_check=[]))[0]["creator_view"]
out["no measurement"] = "listen_note" in built("en", None)[0]["creator_view"]
out["authored, replaced"] = built("en", audio, authored="Sounds great.")[0]["creator_view"]["listen_note"]
out["authored, dropped"] = "listen_note" in built("en", None, authored="Sounds great.")[0]["creator_view"]
def gate(result, ev):
    return [e for e in check(result, {"subject_state": "own_published", "observations": analysis["observations"]}, ev) if "listen_note" in e]
result, ev = built("en", audio)
out["gate derived"] = gate(result, ev)
tampered = dict(result, creator_view=dict(result["creator_view"], listen_note="The music fits."))
out["gate tampered"] = gate(tampered, ev)
old = dict(result, creator_view={k: v for k, v in result["creator_view"].items() if k != "listen_note"})
out["gate older result"] = gate(old, ev)
print(json.dumps(out, ensure_ascii=False))`);
  assert.equal(out["zh-CN"].line, "声音只做了测量，没有人耳听：曲风和情绪是否贴合、是哪首歌、歌词是唱的还是说的、人声音色、音效好不好，请你自己听一下。");
  assert.match(out.en.line, /^The sound was measured, not listened to:/);
  assert.match(out.es.line, /^El sonido solo se midió/);
  assert.match(out.ja.line, /^音は測定しただけで/);
  assert.match(out.hi.line, /^आवाज़ सिर्फ़ मापी गई/);
  assert.equal(out.nl.line, out.en.line);
  for (const tag of ["zh-CN", "en", "es", "ja", "hi"]) {
    const lines = out[tag].report.split("\n");
    const note = lines.findIndex((line) => line.startsWith("*") && line.endsWith("*") && !line.startsWith("**"));
    assert.ok(note > 0, out[tag].report);
    assert.equal(lines[note + 2], `*${out[tag].line}*`, out[tag].report);
  }
  assert.equal(out["viewer heard it"], false);
  assert.equal(out["viewer failed"], true);
  assert.equal(out["nothing to listen for"], false);
  assert.equal(out["no measurement"], false);
  assert.equal(out["authored, replaced"], out.en.line);
  assert.equal(out["authored, dropped"], false);
  assert.deepEqual(out["gate derived"], []);
  assert.equal(out["gate tampered"].length, 1);
  assert.deepEqual(out["gate older result"], []);
});

// The listen line names only what the measurement found: no voice on a video without speech, no music without
// a bed or lasting other sound, sung or spoken only for words over music, effects only with accents measured on the
// cuts; with nothing, no line.
test("listen line: names only the items the sound measurement supports, in every locale, and is omitted when none apply", () => {
  const out = probe(`
from report_locale import listen_items, listen_note, _CATALOG
from validate_creator_shape import check
check_ask = [{"id": "genre_mood_fit", "ask": "What the music is."}]
cases = {
    "music only, lyrics heard": {"voice": {"speech_s": 25.0, "reading": "words may be sung"},
                                 "segments": [{"start_s": 0, "end_s": 3, "label": "non_speech_signal"}],
                                 "onsets": {"count": 90}, "cut_alignment": {"cuts": 12}},
    "music only, no words": {"voice": {"speech_s": 0.0, "reading": None},
                             "segments": [{"start_s": 0, "end_s": 30, "label": "non_speech_signal"}],
                             "listen_check": [{"id": "wordless_sound", "ask": "x"}], "onsets": {"count": 50}},
    "talking head, silent room": {"voice": {"speech_s": 40.0, "reading": "no bed under the voice"},
                                  "segments": [{"start_s": 0, "end_s": 40, "label": "speech"},
                                               {"start_s": 40, "end_s": 40.1, "label": "non_speech_signal"}]},
    "voice over a bed, accents on cuts": {"voice": {"speech_s": 40.0, "reading": "bed under the voice"},
                                          "cut_alignment": {"cuts": 8}, "listen_check": [{"id": "accents_on_cuts", "ask": "x"}]},
    "talking head, a short sting": {"voice": {"speech_s": 50.0, "reading": "no bed under the voice"}, "duration_s": 60,
                                    "segments": [{"start_s": 55, "end_s": 58, "label": "non_speech_signal"}],
                                    "onsets": {"count": 40}, "cut_alignment": {"cuts": 9}},
    "short speech, no reading": {"voice": {"speech_s": 3.0, "reading": None}},
    "unclear words": {"voice": {"speech_s": 4.0, "reading": None},
                      "listen_check": [{"id": "unclear_words", "ask": "x"}]},
    "nothing": {"voice": {"speech_s": 0.0}, "onsets": {"count": 0}},
}
out = {"items": {}, "lines": {}, "gate": {}}
for name, sound in cases.items():
    audio = dict(sound, status="available", findings=[], listen_check=check_ask + sound.get("listen_check", []))
    out["items"][name] = listen_items(audio)
    ev = {"media": {"audio": audio}}
    out["lines"][name] = {code: listen_note(ev, code) for code in _CATALOG}
full = {"voice": {"speech_s": 40.0, "reading": "bed under the voice"}, "onsets": {"count": 3}}
out["full"] = {code: listen_note({"media": {"audio": dict(full, listen_check=check_ask + [{"id": "accents_on_cuts", "ask": "x"}])}}, code) for code in _CATALOG}
out["phrases"] = {code: entry["listen"] for code, entry in _CATALOG.items()}
print(json.dumps(out, ensure_ascii=False))`);
  assert.deepEqual(out.items["music only, lyrics heard"], ["music_fit", "track_identity", "sung_or_spoken"], "onsets and cuts alone do not ask about effects");
  assert.deepEqual(out.items["music only, no words"], ["music_fit", "track_identity"]);
  assert.deepEqual(out.items["talking head, silent room"], ["voice_timbre"], "a 0.1 s sliver is not a music bed");
  assert.deepEqual(out.items["voice over a bed, accents on cuts"], ["music_fit", "track_identity", "sung_or_spoken", "voice_timbre", "sfx_quality"]);
  assert.deepEqual(out.items["talking head, a short sting"], ["voice_timbre"], "3 s of other sound in 60 s is not a music bed");
  assert.deepEqual(out.items["short speech, no reading"], ["voice_timbre"]);
  assert.deepEqual(out.items["unclear words"], ["sung_or_spoken", "music_fit", "track_identity"].sort((a, b) =>
    ["music_fit", "track_identity", "sung_or_spoken"].indexOf(a) - ["music_fit", "track_identity", "sung_or_spoken"].indexOf(b)));
  assert.deepEqual(out.items.nothing, []);
  const codes = Object.keys(out.phrases);
  assert.deepEqual(codes.sort(), ["ar", "de", "en", "es", "fr", "hi", "id", "ja", "ko", "pt", "vi", "zh"]);
  for (const code of codes) {
    const { items } = out.phrases[code];
    assert.equal(out.lines.nothing[code], null, code);
    const music = out.lines["music only, lyrics heard"][code];
    assert.ok(!music.includes(items.voice_timbre), `${code}: ${music}`);
    assert.ok(music.includes(items.sung_or_spoken) && music.includes(items.music_fit), `${code}: ${music}`);
    const wordless = out.lines["music only, no words"][code];
    assert.ok(!wordless.includes(items.voice_timbre) && !wordless.includes(items.sung_or_spoken), `${code}: ${wordless}`);
    const talk = out.lines["talking head, silent room"][code];
    assert.ok(talk.includes(items.voice_timbre), `${code}: ${talk}`);
    for (const other of ["music_fit", "track_identity", "sung_or_spoken", "sfx_quality"]) {
      assert.ok(!talk.includes(items[other]), `${code}: ${talk}`);
    }
    for (const item of Object.values(items)) assert.ok(out.full[code].includes(item), `${code}: ${out.full[code]}`);
    assert.ok(!out.full[code].includes("{items}"), code);
  }
  assert.equal(out.lines["talking head, silent room"].en,
    "The sound was measured, not listened to: listen for yourself to check how the voice comes across.");
  assert.equal(out.lines["music only, no words"].en,
    "The sound was measured, not listened to: listen for yourself to check whether the music's genre and mood fit and which track it is.");
});

// A view step that fails on something no view edit can fix (the data note cannot be derived from the evidence,
// the measurement basis disagrees) is a failed step, not the run's one view correction.
test("finish_diagnosis --check: a derivation failure is a failed step; a view violation still needs correction", () => {
  const out = probe(`
import contextlib, io, subprocess, tempfile
from pathlib import Path
import finish_diagnosis as fd
def run_with(message):
    def fake(command, **kwargs):
        step = Path(command[2]).name
        if step == "build_creator_result.py":
            return subprocess.CompletedProcess(command, 1, "", message + "\\n")
        return subprocess.CompletedProcess(command, 0, "", "")
    fd.subprocess.run = fake
    buffer = io.StringIO()
    with tempfile.TemporaryDirectory() as run, contextlib.redirect_stdout(buffer):
        code = fd.check(Path(run))
    text = buffer.getvalue()
    return [code, json.loads(text[: text.rindex("}") + 1])]
print(json.dumps({
    "derive": run_with("cannot derive data_note: dense window interval is unknown or invalid"),
    "basis": run_with("creator_view.data_note disagrees with the recorded measurement basis"),
    "unknown observation": run_with("cannot derive data_note: unknown observation obs_9"),
    "view": run_with("ERROR: creator_view.headline runs 90 columns against a 60 limit"),
}))`);
  assert.deepEqual(out.derive, [1, { status: "failed", step: "build_creator_result.py",
    errors: ["cannot derive data_note: dense window interval is unknown or invalid"] }]);
  assert.equal(out.basis[0], 1);
  assert.equal(out.basis[1].status, "failed");
  assert.equal(out["unknown observation"][0], 3, "a card citing a missing observation is the view's to fix");
  assert.equal(out["unknown observation"][1].status, "needs_correction");
  assert.deepEqual(out.view, [3, { status: "needs_correction", step: "build_creator_result.py",
    violations: ["creator_view.headline runs 90 columns against a 60 limit"],
    gates_not_run: ["render_video_report.py", "validate_creator_shape.py", "validate_creator_report.py"] }]);
});

// One correction should usually be enough: a view gate that fails does not hide the gates after it. Every later gate
// whose input exists still runs, and the check lists all their violations together.
test("finish_diagnosis --check: violations from every gate that can run are listed together for the one correction", () => {
  const out = probe(`
import contextlib, io, subprocess, tempfile
from pathlib import Path
import finish_diagnosis as fd
def run_with(failing):
    ran = []
    def fake(command, **kwargs):
        step = Path(command[2]).name
        ran.append(step)
        if step in failing:
            return subprocess.CompletedProcess(command, 1, "", failing[step] + "\\n")
        return subprocess.CompletedProcess(command, 0, "", "")
    fd.subprocess.run = fake
    buffer = io.StringIO()
    with tempfile.TemporaryDirectory() as run, contextlib.redirect_stdout(buffer):
        code = fd.check(Path(run))
    text = buffer.getvalue()
    return [code, json.loads(text[: text.rindex("}") + 1]), ran, text[text.rindex("}") + 1:].strip()]
print(json.dumps({
    "render_and_shape": run_with({"render_video_report.py": "ERROR: creator_view.headline is required to render",
                                  "validate_creator_shape.py": "ERROR: cards[1]: why_for_you runs 600 columns against a 480 limit"}),
    "shape_and_report": run_with({"validate_creator_shape.py": "ERROR: creator_view.summary runs 400 columns against a 360 limit",
                                  "validate_creator_report.py": "ERROR: Creator-facing report contains internal field name"}),
}))`);
  const [code, verdict, ran, advice] = out.render_and_shape;
  assert.equal(code, 3);
  assert.deepEqual(verdict.violations, ["creator_view.headline is required to render",
    "cards[1]: why_for_you runs 600 columns against a 480 limit"]);
  assert.equal(verdict.step, "render_video_report.py");
  assert.deepEqual(Object.keys(verdict.gates), ["render_video_report.py", "validate_creator_shape.py"]);
  // The report check needs the rendered report, so it waits; the shape gate does not.
  assert.deepEqual(verdict.gates_not_run, ["validate_creator_report.py"]);
  assert.ok(!ran.includes("validate_creator_report.py"));
  assert.match(advice, /for every violation above together/);
  assert.match(advice, /full-width character is two/);
  const [code2, verdict2] = out.shape_and_report;
  assert.equal(code2, 3);
  assert.equal(verdict2.violations.length, 2);
  assert.equal(verdict2.gates_not_run, undefined);
});

// The Web host delivers a printed report itself only when nothing in it is left to translate: the line after
// creator_report says so. A diagnosis renders its own words in 12 languages; a view in any other language still
// needs the model, and a craft teardown is written in the creator's language from the start.
test("emit-report: report_delivery follows creator_report, as_is for a rendered language or a teardown, translate otherwise", async () => {
  const run = await realpath(await mkdtemp(path.join(os.tmpdir(), "acv-delivery-")));
  try {
    await mkdir(path.join(run, "report"), { recursive: true });
    await mkdir(path.join(run, "analysis"), { recursive: true });
    const diagnosis = path.join(run, "report", "VIDEO_DIAGNOSIS.md");
    const teardown = path.join(run, "report", "craft-teardown.md");
    await writeFile(diagnosis, "# Report\n\nBody.\n");
    await writeFile(teardown, "# Wie es gemacht wurde\n\nText.\n");
    const emit = (report) => {
      const result = spawnSync("python3", ["-I", "-B", path.join(scripts, "validate_creator_report.py"), report, "--emit-report"],
        { encoding: "utf8", env });
      assert.equal(result.status, 0, result.stderr);
      return result.stdout;
    };
    const delivered = async (language) => {
      await writeFile(path.join(run, "analysis", "creator-task-result.json"), JSON.stringify({ creator_view: { language } }));
      return /\nreport_delivery: (\S+)\n/.exec(emit(diagnosis))[1];
    };
    assert.equal(await delivered("zh-CN"), "as_is");
    assert.equal(await delivered("en"), "as_is");
    assert.equal(await delivered("pt-BR"), "as_is");
    assert.equal(await delivered("hi"), "as_is");
    assert.equal(await delivered("it"), "translate");
    assert.equal(await delivered("ru-RU"), "translate");
    const out = emit(diagnosis);
    // The report bytes, then creator_report, then report_delivery, then the instruction: earlier lines unchanged.
    assert.ok(out.startsWith("# Report\n\nBody.\n" + `creator_report: ${diagnosis}\nreport_delivery: translate\nYour reply is this report`), out);
    await rm(path.join(run, "analysis", "creator-task-result.json"));
    assert.match(emit(diagnosis), /\nreport_delivery: translate\n/, "without the delivered result the model checks it");
    assert.match(emit(teardown), new RegExp(`\ncreator_report: ${teardown.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\nreport_delivery: as_is\n`));
  } finally {
    await rm(run, { recursive: true, force: true });
  }
});

// A pre-release report printed "## 你的下一条怎么做" ("what to do in yours") and, under it, the action labelled
// "**你的下一条怎么做**：" again: the card's heading was the label word for word. The heading stands; the line goes unlabelled.
test("renderer: a card whose heading already is its action label does not repeat it", () => {
  const out = probe(`
from render_video_report import render
def report(subject, titles, language):
    cards = [{"title": title, "why_for_you": "a\\nb\\nc", "action": f"act {i}"} for i, title in enumerate(titles)]
    return render({"creator_view": {"language": language, "headline": "H", "cards": cards}, "details": {"subject_state": subject}})
print(json.dumps({
  "zh": report("third_party", ["它为什么能打动人", "照搬会继承的问题", "你的下一条怎么做"], "zh"),
  "en": report("own_published", ["What works", "What holds it back", "What to change:"], "en"),
  "distinct": report("third_party", ["What works", "What you would inherit", "Your next video"], "en"),
}, ensure_ascii=False))`);
  assert.equal(out.zh.split("你的下一条怎么做").length - 1, 1, out.zh);
  assert.match(out.zh, /## 你的下一条怎么做\n\n- a\n- b\n- c\n\nact 2\n$/);
  assert.equal(out.en.split("What to change").length - 1, 1, out.en);
  assert.match(out.distinct, /\*\*What to do in yours\*\*: act 2\n$/);
});

// Creator-facing text named a Skill id ("create-script-and-packaging") and evidence paths ("media.probed.*") in a
// pre-release run. The view check reports each as a correction, never as a failed step, and leaves ids in
// evidence_refs and the derived lines alone.
test("view check: Skill ids, script names and evidence field paths in creator-facing text need correction", async () => {
  const lock = JSON.parse(await readFile(path.join(root, "skills.lock.json"), "utf8"));
  const out = probe(`
from validate_creator_shape import SKILL_IDS, internal_name_errors
from finish_diagnosis import view_can_fix
view = {"language": "zh", "headline": "H", "summary": "响度见media.probed.loudness，第3句transcript.cue[3]。",
        "data_note": "media.probed is derived", "cards": [
          {"title": "T", "why_for_you": "a\\nb\\nc", "action": "keep the frames. Then cut", "evidence_refs": ["observations.o1", "media.probed.loudness"]},
          {"title": "U", "why_for_you": "a\\nb\\nc", "action": "the platform's sound label says original audio"},
          {"title": "V", "why_for_you": "a\\nb\\nc", "action": "run render_video_report.py", "hooks": [{"visual_direction": "audio_attribution 显示原声"}]}],
        "next_actions": ["用 create-script-and-packaging 写下一条", "ask for a review of the whole account"]}
found = internal_name_errors(view)
print(json.dumps({"ids": sorted(SKILL_IDS), "found": found, "fixable": view_can_fix(found)}, ensure_ascii=False))`);
  assert.deepEqual(out.ids, lock.skills.map((skill) => skill.id).sort(), "SKILL_IDS follows skills.lock.json");
  const names = out.found.map((message) => /names '([^']+)'/.exec(message)[1]);
  assert.deepEqual(names, ["media.probed.loudness", "transcript.cue[3]", "render_video_report.py", "audio_attribution",
    "create-script-and-packaging"]);
  assert.ok(out.found.every((message) => /^creator_view\.(summary|cards\[2\]\.(action|hooks\[0\]\.visual_direction)|next_actions\[0\]) /.test(message)), out.found.join("\n"));
  assert.equal(out.fixable, true);
});

// When the observation deadline stops the wait before the frames arrive, the measurement line says so in every
// report language instead of "frames not sampled", which reads as a choice.
test("data_note: frames still running at the observation deadline did not arrive in time", () => {
  const out = probe(`
from creator_measurement_basis import canonical_note
from report_locale import LOCALES
${LOCALE_EVIDENCE}
late = dict(evidence, frames={"status": "not_attempted", "items": []},
            acquisition=[{"operation": "extract_keyframes", "status": "deferred_incomplete"}])
skipped = dict(late, acquisition=[])
print(json.dumps({"en": canonical_note(late, analysis, view("en")), "zh": canonical_note(late, analysis, view("zh")),
                  "skipped": canonical_note(skipped, analysis, view("en")),
                  "locales": {code: canonical_note(late, analysis, view(code)) for code in LOCALES},
                  "words": {code: LOCALES[code]["note"]["frames"]["timed_out"] for code in LOCALES}}, ensure_ascii=False))`);
  assert.match(out.en, /^YouTube video; frames did not arrive in time; 0 cited frame refs;/);
  assert.match(out.zh, /画面帧未能及时取回/);
  assert.match(out.skipped, /frames not sampled/);
  for (const [code, note] of Object.entries(out.locales)) assert.ok(note.includes(out.words[code]), `${code}: ${note}`);
});

test("a craft teardown ends with the line on what it rests on and is checked before delivery", () => {
  const craft = readFileSync(new URL("../skills/analyze-content-video/references/craft-teardown.md", import.meta.url), "utf8");
  assert.match(craft, /End the report with one line, in the creator's language, saying what it\s+rests on/);
  assert.match(craft, /scripts\/validate_creator_report\.py report\/craft-teardown\.md --emit-report/);
  // The brief is what the model reads at the end; on Kabo Web a teardown delivered without the check was followed by the
  // host's own basis note, which contradicted the report. The brief's craft section must end on the same check.
  const brief = readFileSync(new URL("../skills/analyze-content-video/references/analysis-brief.md", import.meta.url), "utf8");
  const section = brief.split("<!-- section: output-craft-teardown -->")[1].split("<!-- section:")[0];
  assert.match(section, /validate_creator_report\.py report\/craft-teardown\.md --emit-report/);
  assert.match(section, /what it rests on/);
});
