// AGENTS.md：提交信息、PR 标题与 PR 描述一律英文。CI 在 pull_request 事件里读标题、描述与本 PR 的提交信息，
// 出现中日韩文字即失败；机器人追加的内容（CodeRabbit 摘要等）放在 HTML 注释块里，先剔除再检查。
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const CJK = /[぀-ヿ㐀-䶿一-鿿가-힯！-｠]/u;

export function stripBotText(text) {
  return String(text ?? "")
    .replace(/<!-- This is an auto-generated comment[\s\S]*?<!-- end of auto-generated comment[^>]*-->/g, "")
    .replace(/<!--[\s\S]*?-->/g, "");
}

export function findings({ title, body, commits }) {
  const found = [];
  const check = (where, text) => {
    const line = stripBotText(text).split("\n").find((row) => CJK.test(row));
    if (line !== undefined) found.push(`${where}: ${line.trim().slice(0, 120)}`);
  };
  check("PR title", title);
  check("PR description", body);
  for (const { sha, message } of commits) check(`commit ${sha.slice(0, 7)}`, message);
  return found;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
  const pr = event.pull_request;
  if (!pr) {
    console.log("Not a pull_request event; nothing to check.");
    process.exit(0);
  }
  const range = `${pr.base.sha}..${pr.head.sha}`;
  const log = execFileSync("git", ["log", "--no-merges", "--format=%H%x00%B%x01", range], { encoding: "utf8" });
  const commits = log.split("\x01").map((entry) => entry.trim()).filter(Boolean)
    .map((entry) => { const [sha, message] = entry.split("\x00"); return { sha, message }; });
  const problems = findings({ title: pr.title, body: pr.body, commits });
  if (problems.length) {
    console.error("AGENTS.md requires English commit messages, PR titles and PR descriptions. Non-English text found:");
    for (const problem of problems) console.error(`- ${problem}`);
    process.exit(1);
  }
  console.log(`PR title, description and ${commits.length} commit message(s) are in English.`);
}
