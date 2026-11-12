// Two pieces of content shared by the slimmed-down Skills are distributed as copies (KS4.2): the whole of
//   references/data-calls.md, and the handoff-and-resume section of
// connector_driver.py (each call's storage file and one resume command, with resume itself doing fetch / stage
//   on the named files).
// The copies must be identical character for character: changing one means changing all copies in sync,
//   otherwise the same handoff is worded differently in different Skills.
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const skills = readdirSync(path.join(root, "skills"), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);
const copies = (relative) => skills
  .map((skill) => ({ skill, file: path.join(root, "skills", skill, relative) }))
  .filter(({ file }) => existsSync(file))
  .map(({ skill, file }) => ({ skill, text: readFileSync(file, "utf8") }));

test("references/data-calls.md is identical across Skills", () => {
  const found = copies("references/data-calls.md");
  assert.ok(found.length >= 2, "at least two copies of data-calls.md");
  for (const { skill, text } of found) assert.equal(text, found[0].text, `${skill} differs from ${found[0].skill}`);
});

for (const relative of ["scripts/short_window_topic_gate.py", "references/short-window-topic-gate.md",
  "scripts/render_short_window_report.py"]) {
  test(`${relative} is identical across the three platform trend Skills`, () => {
    const found = copies(relative);
    assert.equal(found.length, 3);
    for (const { skill, text } of found) assert.equal(text, found[0].text, skill);
  });
}

test("the handoff block of connector_driver.py (resume_command and hand_over) is identical across Skills", () => {
  const block = (text) => {
    const start = text.indexOf("def resume_command()");
    const end = text.indexOf("def fetch_or_hand_over(");
    return start >= 0 && end > start ? text.slice(start, end) : null;
  };
  const found = copies("scripts/connector_driver.py").map(({ skill, text }) => ({ skill, block: block(text) }));
  const withBlock = found.filter(({ block }) => block !== null);
  assert.ok(withBlock.length >= 2, "at least two copies of connector_driver.py with a handoff block");
  for (const { skill, block } of withBlock) assert.equal(block, withBlock[0].block, `${skill} differs from ${withBlock[0].skill}`);
});
