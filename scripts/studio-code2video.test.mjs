import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { isPackageFile } from "./package-layout.mjs";
import { buildPluginBundle } from "./web-publish/bundle.mjs";

test("the Studio job can load both template revisions without installing a desktop Skill", () => {
  const bundle = buildPluginBundle({ skillDirectory: "studio/code2video", sourceCommit: "f".repeat(40), version: "0.1.4" });
  assert.equal(bundle.source.repository, "kabo-sh/kabo-mcp-plugin");
  assert.equal(bundle.manifest, null);
  for (const file of bundle.files) assert.equal(isPackageFile("studio/code2video/" + file.path), false);
  const instructions = Buffer.from(bundle.files.find(file => file.path === "SKILL.md").content_base64, "base64").toString();
  assert.match(instructions, /action:"render"/);
  assert.doesNotMatch(instructions, /action:"(?:preview|review)"|beat_review/);
  const templates = JSON.parse(readFileSync(new URL("./fixtures/studio-code2video.json", import.meta.url)));
  assert.equal(new Set(templates.map(template => template.templateId)).size, 2);
  for (const template of templates) {
    assert.ok(instructions.includes("| " + template.templateId + " |"));
    assert.ok(instructions.includes("revision " + template.version));
    assert.equal(new Set(template.episodes.map(episode => episode.script)).size, 2);
  }
});
