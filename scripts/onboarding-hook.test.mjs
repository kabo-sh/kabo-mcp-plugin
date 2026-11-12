import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { packageFiles } from "./package-check.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const script = path.join(root, "hooks/onboarding-nudge.sh");

async function temp(t) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-onboarding-hook-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

// The hook gets only the environment the host provides; other variables are cleared so that a CLAUDE_PLUGIN_DATA set
// on the development machine cannot leak in.
const run = env => execFileSync("sh", [script], { env: { PATH: process.env.PATH, ...env }, encoding: "utf8" });

test("hooks.json calls the in-repo script only in startup sessions, with the path resolved through CLAUDE_PLUGIN_ROOT", async () => {
  const config = JSON.parse(await readFile(path.join(root, "hooks/hooks.json"), "utf8"));
  assert.deepEqual(Object.keys(config.hooks), ["SessionStart"]);
  const [entry] = config.hooks.SessionStart;
  assert.equal(config.hooks.SessionStart.length, 1);
  assert.equal(entry.matcher, "startup");
  const [hook] = entry.hooks;
  assert.equal(hook.type, "command");
  assert.equal(hook.command, 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/onboarding-nudge.sh"');
  assert.ok(hook.timeout <= 10);
});

test("the first session prints the start-with-kabo offer once, then stays silent", async t => {
  const data = path.join(await temp(t), "plugin-data");
  const first = JSON.parse(run({ CLAUDE_PLUGIN_DATA: data }));
  assert.equal(first.hookSpecificOutput.hookEventName, "SessionStart");
  const note = first.hookSpecificOutput.additionalContext;
  assert.match(note, /kabo:start-with-kabo/);
  // A user who does not take the offer right away must still know how to start later, so the note has to give a
  // command that can be typed directly.
  assert.match(note, /typing \/kabo:start-with-kabo/);
  // The note may only have the model ask for consent, never start for the creator; it must not be started in
  // unattended scheduled tasks.
  assert.match(note, /Never start the setup without the user's agreement/);
  assert.match(note, /scheduled or unattended runs/);
  assert.ok(existsSync(path.join(data, "onboarding-offered")));
  assert.equal(run({ CLAUDE_PLUGIN_DATA: data }), "");
});

test("falls back to ~/.kabo when an older host has no CLAUDE_PLUGIN_DATA", async t => {
  const home = await temp(t);
  assert.match(run({ HOME: home }), /start-with-kabo/);
  assert.ok(existsSync(path.join(home, ".kabo/onboarding-offered")));
  assert.equal(run({ HOME: home }), "");
});

test("exits silently when the marker cannot be written, instead of offering in every session", async t => {
  const blocker = path.join(await temp(t), "not-a-directory");
  await writeFile(blocker, "");
  assert.equal(run({ CLAUDE_PLUGIN_DATA: path.join(blocker, "data") }), "");
});

test("hooks/ stays in the Claude Code repository install and is not in the release ZIP", async () => {
  assert.ok(existsSync(path.join(root, "hooks/hooks.json")));
  assert.equal((await packageFiles()).some(file => file.name.startsWith("hooks/")), false);
});
