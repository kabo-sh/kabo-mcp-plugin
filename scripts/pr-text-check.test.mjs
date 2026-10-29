import test from "node:test";
import assert from "node:assert/strict";
import { findings, stripBotText } from "./pr-text-check.mjs";

test("PR 文字检查：英文通过；标题、描述、提交信息里的中文各自报出；机器人摘要与 HTML 注释不算", () => {
  const commits = [{ sha: "a".repeat(40), message: "fix(trends): keep the run open" }];
  assert.deepEqual(findings({ title: "fix: English", body: "All English.", commits }), []);
  assert.equal(findings({ title: "修复", body: "", commits }).length, 1);
  assert.match(findings({ title: "fix", body: "## 做什么\nok", commits })[0], /^PR description: ## 做什么/);
  assert.match(findings({ title: "fix", body: "", commits: [{ sha: "b".repeat(40), message: "修复 bug" }] })[0], /^commit bbbbbbb/);
  const bot = "Text\n<!-- This is an auto-generated comment: release notes by coderabbit.ai -->\n摘要\n<!-- end of auto-generated comment: release notes by coderabbit.ai -->";
  assert.equal(stripBotText(bot).includes("摘要"), false);
  assert.deepEqual(findings({ title: "fix", body: bot, commits }), []);
});
