// review-creator-account-deep has only one run per request (exposed by the 1.0.14 production regression):
// the model first ran static_host.py init,
// recorded one start_skill_run against that run, then ran fetch_catalog.py --workspace, which reserved
// another run, so the same request recorded usage twice.
// Now --workspace first claims a run of this Skill that was just reserved in this workspace and is still
// empty; a run that has already started is not claimed.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "review-creator-account-deep", "scripts");
const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
delete env.KABO_STATIC_RUN_DIR;

const python = (script, args, cwd) => {
  const result = spawnSync("python3", [path.join(scripts, script), ...args], { cwd, encoding: "utf8", env });
  return { code: result.status, out: result.stdout + result.stderr };
};
const catalog = (workspace) =>
  python("fetch_catalog.py", ["--workspace", workspace, "--platform", "youtube", "--account", "@neutral", "--output-language", "en"], workspace);

async function workspace(t) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-deep-run-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

test("after init, running --workspace claims the just-reserved empty run instead of creating another", async (t) => {
  const dir = await workspace(t);
  const init = python("static_host.py", ["init", "--workspace", dir], dir);
  assert.equal(init.code, 0, init.out);
  const reserved = init.out.trim();
  const { code, out } = catalog(dir);
  assert.equal(code, 0, out);
  assert.equal(JSON.parse(out.slice(out.indexOf("{"))).run_directory, reserved);
  assert.equal((await readdir(path.join(dir, ".kabo-runs"))).length, 1);
});

test("a run that has already started is not claimed: create another", async (t) => {
  const dir = await workspace(t);
  const init = python("static_host.py", ["init", "--workspace", dir], dir);
  const started = init.out.trim();
  await writeFile(path.join(started, "account_analysis.json"), "{}");
  const { code, out } = catalog(dir);
  assert.equal(code, 0, out);
  assert.notEqual(JSON.parse(out.slice(out.indexOf("{"))).run_directory, started);
  const runs = await readdir(path.join(dir, ".kabo-runs"));
  assert.equal(runs.length, 2);
});
