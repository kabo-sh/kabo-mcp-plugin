// The analyze-content-video method library (references/video-method/): index.json matches the card files, cards stay
//   within KS3.2, and no vendor or model names, numeric scoring language or restrictive licence text (KS5) appear.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const dir = path.join(root, "skills/analyze-content-video/references/video-method");
const index = JSON.parse(readFileSync(path.join(dir, "index.json"), "utf8"));
const indexMd = readFileSync(path.join(dir, "index.md"), "utf8");
const cardIds = ["diagnosis-default", "craft-shot-description", "opening", "narrative-structure", "editing-pacing",
  "sound", "captions-type", "visual-color", "packaging", "emotion"];
const evidenceKinds = new Set(["frames", "transcript", "measure", "viewer_observations", "metadata"]);
const semver = /^\d+\.\d+\.\d+$/;
const libraryFiles = () => readdirSync(dir).filter((name) => /\.(md|json)$/.test(name));

test("index.json lists exactly the fixed cards, each with a file that exists", () => {
  assert.equal(index.schema_version, "video-method-index/v1");
  assert.match(index.library_version, semver);
  const ids = index.cards.map((card) => card.id);
  assert.deepEqual([...ids].sort(), [...cardIds].sort());
  assert.equal(new Set(ids).size, ids.length, "duplicate card id");
  for (const card of index.cards) {
    assert.equal(card.file, `${card.id}.md`, card.id);
    assert.ok(existsSync(path.join(dir, card.file)), `${card.file} missing`);
    assert.match(card.version, semver, card.id);
    assert.equal(typeof card.title, "string");
    assert.ok(card.title.length > 0, card.id);
    assert.equal(typeof card.use_when, "string");
    assert.ok(card.use_when.length > 0, card.id);
    assert.ok(Array.isArray(card.focus_terms.en) && Array.isArray(card.focus_terms.zh), card.id);
    assert.ok(Array.isArray(card.needs_evidence), card.id);
    for (const kind of card.needs_evidence) assert.ok(evidenceKinds.has(kind), `${card.id}: ${kind}`);
    assert.equal(typeof card.topic, "boolean");
    if (card.topic) {
      assert.deepEqual(card.base_for, [], `${card.id}: a topic card is base for nothing`);
      assert.ok(card.focus_terms.en.length > 0 && card.focus_terms.zh.length > 0, `${card.id}: focus terms`);
    } else assert.ok(card.base_for.length > 0, `${card.id}: a base card names its modes`);
  }
  const mdCards = libraryFiles().filter((name) => name.endsWith(".md") && name !== "index.md").sort();
  assert.deepEqual(mdCards, index.cards.map((card) => card.file).sort(), "every card file is indexed");
});

test("each analysis mode has exactly one base card, as the contract fixes", () => {
  const baseFor = (mode) => index.cards.filter((card) => card.base_for.includes(mode)).map((card) => card.id);
  assert.deepEqual(baseFor("diagnosis"), ["diagnosis-default"]);
  assert.deepEqual(baseFor("content_read"), ["diagnosis-default"]);
  assert.deepEqual(baseFor("craft_teardown"), ["craft-shot-description"]);
  assert.deepEqual(baseFor("transcript_export"), []);
});

test("cards stay within KS3.2 and index.md stays short and names every card", () => {
  for (const card of index.cards) {
    const text = readFileSync(path.join(dir, card.file), "utf8");
    assert.ok(text.split("\n").length <= 500, `${card.file}: lines`);
    assert.ok(text.length <= 20_000, `${card.file}: ${text.length} characters`);
    assert.ok(!/^---\n/.test(text), `${card.file}: metadata lives in index.json, not a header block`);
    assert.ok(!/[\u3400-\u9fff]/.test(text), `${card.file}: cards are English`);
  }
  assert.ok(indexMd.length <= 4_000, `index.md: ${indexMd.length} characters`);
  for (const id of cardIds) assert.ok(indexMd.includes(`\`${id}\``), `index.md does not mention ${id}`);
});

test("no vendor, model or provider names, scoring language or restrictive licence text", () => {
  // Names are split so this file does not trip the repository-wide vendor-name scan.
  const vendor = new RegExp(["gem" + "ini", "vertex", "openai", "\\bgpt", "claude", "anthropic",
    "open" + "montage", "vid" + "iq", "opus ?clip"].join("|"), "i");
  const scoring = /\b0\s*[-–—~]\s*100\b|overall\s*score|\/\s*100\b|overallScore|viralPotential/i;
  const restrictive = /\b(?:A|L)?GPL(?:-?v?\d)?\b|GNU (?:Affero |Lesser )?General Public License|SPDX-License-Identifier/i;
  for (const name of libraryFiles()) {
    const text = readFileSync(path.join(dir, name), "utf8");
    assert.doesNotMatch(text, vendor, `${name}: vendor name`);
    assert.doesNotMatch(text, scoring, `${name}: scoring language`);
    assert.doesNotMatch(text, restrictive, `${name}: licence text`);
  }
});

test("the opening card points at the hook-core data by path and does not copy it", () => {
  const opening = readFileSync(path.join(dir, "opening.md"), "utf8");
  assert.ok(opening.includes("references/hook-core/"));
  const hookCore = JSON.parse(readFileSync(
    path.join(root, "skills/analyze-content-video/references/hook-core/knowledge.json"), "utf8"));
  for (const pattern of hookCore.patterns) {
    for (const field of ["visual", "sound", "joint_expression"])
      assert.ok(!opening.includes(pattern[field]), `opening.md copies ${pattern.id}.${field}`);
    assert.ok(!new RegExp(`\\b${pattern.id}\\b`).test(opening), `opening.md names pattern ${pattern.id}`);
  }
});

test("the default card files all seventeen judgment dimensions", () => {
  const schema = JSON.parse(readFileSync(
    path.join(root, "skills/analyze-content-video/references/video-analysis.schema.json"), "utf8"));
  const dimensions = schema.properties.observations.items.properties.dimension.enum;
  const card = readFileSync(path.join(dir, "diagnosis-default.md"), "utf8");
  for (const dimension of dimensions) assert.ok(card.includes(`\`${dimension}\``), dimension);
});

// The selection runs first on the creator's request alone (no evidence yet), and again inside prepare_analysis.py
// against the evidence that arrived. The first one skips nothing: whether a card can be served is not known yet.
test("select_method.py before the fetch: no --evidence, nothing skipped, the same refusals", (t) => {
  const out = mkdtempSync(path.join(os.tmpdir(), "kabo-acv-select-"));
  t.after(() => rmSync(out, { recursive: true, force: true }));
  const select = (...args) => {
    const result = spawnSync("python3", ["-B", path.join(root, "skills/analyze-content-video/scripts/select_method.py"),
      "--out", path.join(out, "method.json"), ...args], { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
    return { code: result.status, out: result.stdout + result.stderr };
  };
  const chosen = select("--mode", "craft_teardown", "--focus", "captions-type,editing-pacing");
  assert.equal(chosen.code, 0, chosen.out);
  const method = JSON.parse(readFileSync(path.join(out, "method.json"), "utf8"));
  assert.equal(method.schema_version, "method-selection/v1");
  assert.deepEqual(method.cards.map((card) => [card.id, card.role]),
    [["craft-shot-description", "base"], ["captions-type", "topic"], ["editing-pacing", "topic"]]);
  assert.deepEqual(method.skipped, []);
  assert.equal(method.default_only, false);
  assert.equal(select("--mode", "diagnosis", "--focus", "no-such-card").code, 2);
  assert.equal(select("--mode", "transcript_export", "--focus", "sound").code, 2);
});
