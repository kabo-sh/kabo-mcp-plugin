// Every Skill fits the Kabo Web sandbox.
// Origin: the analyze-content-video redesign reached 65 files under scripts/ and references/. Kabo Web delivers
// both trees to its sandbox whole and refuses a Skill over 64 files (skill_files_too_many), so on Web every
// script step failed with "bundle_unavailable" and the model answered without the Skill. Nothing in this
// repository noticed; the limit only showed on the pre environment.
// The numbers mirror the sandbox protocol in kabo-agent-service (services/sandbox/src/protocol.ts:
// SANDBOX_SKILL_FILES_MAX, SANDBOX_SKILL_FILE_BYTES_MAX, SANDBOX_SKILL_FILES_TOTAL_BYTES_MAX and
// SANDBOX_SKILL_FILE_PATH). Web counts the files of scripts/ and references/ only, skipping __pycache__.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const FILES_MAX = 64;
const FILE_BYTES_MAX = 1024 * 1024;
const TOTAL_BYTES_MAX = 4 * 1024 * 1024;
const SEGMENT = "[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}";
const PATH = new RegExp(`^(?:scripts|references)(?:/${SEGMENT}){1,4}$`);

const tracked = execFileSync("git", ["ls-files", "-z", "skills"], { cwd: root, encoding: "utf8" })
  .split("\0")
  .filter(Boolean);
const skills = new Map();
for (const file of tracked) {
  const [, id, ...rest] = file.split("/");
  const relative = rest.join("/");
  if (!/^(?:scripts|references)\//.test(relative) || relative.split("/").includes("__pycache__")) continue;
  if (!skills.has(id)) skills.set(id, []);
  skills.get(id).push({ relative, bytes: statSync(path.join(root, file)).size });
}

test("the Skills that ship scripts or references are found", () => {
  assert.ok(skills.has("analyze-content-video"));
});

for (const [id, files] of skills) {
  test(`${id} fits the Web sandbox's file limits`, () => {
    assert.ok(files.length <= FILES_MAX, `${id} has ${files.length} files under scripts/ and references/; Web delivers at most ${FILES_MAX}`);
    for (const file of files) {
      assert.match(file.relative, PATH, `${id}/${file.relative} is not a path Web can deliver`);
      assert.ok(file.bytes <= FILE_BYTES_MAX, `${id}/${file.relative} is ${file.bytes} bytes; Web delivers at most ${FILE_BYTES_MAX} per file`);
    }
    const total = files.reduce((sum, file) => sum + file.bytes, 0);
    assert.ok(total <= TOTAL_BYTES_MAX, `${id} ships ${total} bytes; Web delivers at most ${TOTAL_BYTES_MAX} per Skill`);
  });
}
