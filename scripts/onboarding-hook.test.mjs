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

// 钩子只拿到宿主给的环境；其余变量清空，避免开发机上的 CLAUDE_PLUGIN_DATA 混进来。
const run = env => execFileSync("sh", [script], { env: { PATH: process.env.PATH, ...env }, encoding: "utf8" });

test("hooks.json 只在 startup 会话调用仓内脚本，路径经 CLAUDE_PLUGIN_ROOT 解析", async () => {
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

test("首个会话输出一次 start-with-kabo 提示，之后静默", async t => {
  const data = path.join(await temp(t), "plugin-data");
  const first = JSON.parse(run({ CLAUDE_PLUGIN_DATA: data }));
  assert.equal(first.hookSpecificOutput.hookEventName, "SessionStart");
  const note = first.hookSpecificOutput.additionalContext;
  assert.match(note, /kabo:start-with-kabo/);
  // 提示只能让模型征求同意，不能替创作者开跑；无人值守的定时任务里不能发起。
  assert.match(note, /Never start the setup without the user's agreement/);
  assert.match(note, /scheduled or unattended runs/);
  assert.ok(existsSync(path.join(data, "onboarding-offered")));
  assert.equal(run({ CLAUDE_PLUGIN_DATA: data }), "");
});

test("旧版宿主没有 CLAUDE_PLUGIN_DATA 时退回 ~/.kabo", async t => {
  const home = await temp(t);
  assert.match(run({ HOME: home }), /start-with-kabo/);
  assert.ok(existsSync(path.join(home, ".kabo/onboarding-offered")));
  assert.equal(run({ HOME: home }), "");
});

test("标记写不进去时静默退出，不在每个会话反复提示", async t => {
  const blocker = path.join(await temp(t), "not-a-directory");
  await writeFile(blocker, "");
  assert.equal(run({ CLAUDE_PLUGIN_DATA: path.join(blocker, "data") }), "");
});

test("hooks/ 留在 Claude Code 的仓库安装里，不进发布 ZIP", async () => {
  assert.ok(existsSync(path.join(root, "hooks/hooks.json")));
  assert.equal((await packageFiles()).some(file => file.name.startsWith("hooks/")), false);
});
