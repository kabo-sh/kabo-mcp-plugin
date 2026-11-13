#!/usr/bin/env node
// Fails a pull request whose title, description or commit messages contain Chinese, Japanese or Korean
// prose. AGENTS.md requires English for all three; the CodeRabbit checks for this are advisory only, so
// this is the gate that blocks the merge.
//
// Ignored, because they are not author prose: fenced and inline code, block quotes (quoted user queries
// that are test inputs), HTML comments and the sections bots append (CodeRabbit summaries).
//
// Usage in CI: node scripts/pr-language-check.mjs  (reads GITHUB_EVENT_PATH, GITHUB_TOKEN, GITHUB_REPOSITORY)
// Local check:  node scripts/pr-language-check.mjs --text "<title>" "<body>" ...

import { readFileSync } from "node:fs";

const CJK = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff\uff01-\uff60]/u;

export function authorProse(text) {
  return (text ?? "")
    .replace(/<!-- This is an auto-generated comment[\s\S]*$/, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/~~~[\s\S]*?~~~/g, "")
    .replace(/`[^`\n]*`/g, "")
    .split("\n")
    .filter((line) => !/^\s*>/.test(line))
    .join("\n");
}

export function offendingLines(text) {
  return authorProse(text)
    .split("\n")
    .filter((line) => CJK.test(line))
    .map((line) => line.trim().slice(0, 120));
}

async function main() {
  const args = process.argv.slice(2);
  const findings = [];
  if (args[0] === "--text") {
    args.slice(1).forEach((t, i) => offendingLines(t).forEach((l) => findings.push(`text ${i + 1}: ${l}`)));
  } else {
    const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
    const pr = event.pull_request;
    if (!pr) {
      console.log("Not a pull request event; nothing to check.");
      return;
    }
    offendingLines(pr.title).forEach((l) => findings.push(`PR title: ${l}`));
    offendingLines(pr.body).forEach((l) => findings.push(`PR description: ${l}`));
    const headers = { authorization: `Bearer ${process.env.GITHUB_TOKEN}`, accept: "application/vnd.github+json" };
    for (let page = 1; ; page += 1) {
      const url = `https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/pulls/${pr.number}/commits?per_page=100&page=${page}`;
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`listing commits failed: HTTP ${res.status}`);
      const commits = await res.json();
      for (const c of commits) {
        if ((c.parents ?? []).length > 1) continue; // merge commits carry the base branch's history
        offendingLines(c.commit.message).forEach((l) => findings.push(`commit ${c.sha.slice(0, 9)}: ${l}`));
      }
      if (commits.length < 100) break;
    }
  }
  if (findings.length) {
    console.error("Non-English prose found (AGENTS.md: commit messages, PR titles and descriptions are English):");
    for (const f of findings) console.error(`  - ${f}`);
    console.error("Rewrite them in English (edit the PR, reword the commits) and re-run this check.");
    process.exit(1);
  }
  console.log("PR title, description and commit messages are English.");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    console.error(e.message);
    process.exit(1);
  });
}
