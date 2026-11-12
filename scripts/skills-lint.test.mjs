import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cp, mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { lintSkill, lintSkills } from "./skills-lint.mjs";

const context = { toolNames: new Set(["youtube_get_video", "get_research_data_job"]), skillIds: new Set(["demo-skill", "other-skill"]) };
const skill = (front, body = "Run the steps.\n", extra = {}) =>
  new Map(Object.entries({ "SKILL.md": `---\n${front}\n---\n${body}`, ...extra }).map(([name, text]) => [name, Buffer.from(text)]));
const rules = (findings, level = "error") => findings.filter(finding => finding.level === level).map(finding => finding.rule).sort();

test("a spec-compliant skill has no errors; allowed-tools covers the /mcp-pub tools used in the body", () => {
  const files = skill(
    "name: demo-skill\ndescription: Analyze one public video.\ncompatibility: Requires Python 3 and file access.\nlicense: MIT\nmetadata:\n  version: \"1.0.0\"\nallowed-tools: youtube_get_video get_research_data_job",
    "Call `youtube_get_video`, then wait with `get_research_data_job`.\nWhen done, suggest other-skill as a next step.\n",
    { "scripts/run.py": "print('ok')\n" },
  );
  assert.deepEqual(rules(lintSkill("demo-skill", files, context)), []);
});

test("errors when frontmatter does not match the open spec", () => {
  assert.deepEqual(rules(lintSkill("demo-skill", skill("name: demo-skill\ndescription: uses search then get: never collect"), context)), ["KS1.1"]);
  assert.deepEqual(rules(lintSkill("demo-skill", skill("name: Demo-Skill\ndescription: x\nexecution: subagent"), context)), ["KS1.1", "KS1.3"]);
  const long = lintSkill("demo-skill", skill(`name: demo-skill\ndescription: ${"a".repeat(600)}`), context);
  assert.deepEqual(rules(long), []);
  assert.deepEqual(rules(long, "warn"), ["KS1.2"]);
});

test("reports only KS1.1 without throwing when frontmatter is not a mapping", () => {
  assert.deepEqual(rules(lintSkill("demo-skill", skill("hello"), context)), ["KS1.1"]);
  assert.deepEqual(rules(lintSkill("demo-skill", skill("- a\n- b"), context)), ["KS1.1"]);
});

test("non-md text in references, plain JSON length, multiple SPDX, unrecognized license, and JS fetch", () => {
  const findings = lintSkill(
    "demo-skill",
    skill("name: demo-skill\ndescription: x\ncompatibility: Python 3", "Run.\n", {
      "references/guide.txt": "Call mcp__plugin_kabo__run.\n",
      "references/data.json": JSON.stringify({ x: "y".repeat(20_001) }),
      "references/big.schema.json": JSON.stringify({ x: "y".repeat(20_001) }),
      "scripts/mixed.py": "# SPDX-License-Identifier: MIT\n# SPDX-License-Identifier: MPL-2.0\n",
      "assets/NOTICE": "Licensed under MPL-2.0.\n",
      "assets/LICENSE": "MIT License\nPermission is hereby granted, free of charge\n",
      "scripts/get.mjs": "await fetch('https://example.com');\n",
      "references/guide.rst": "Set PLUGIN_ROOT and call youtube_get_video.\n",
      "scripts/compound.py": "# SPDX-License-Identifier: MIT OR GPL-3.0-only\n",
      "scripts/exception.py": "# SPDX-License-Identifier: (Apache-2.0 WITH LLVM-exception)\n",
    }),
    context,
  );
  assert.deepEqual(rules(findings), ["KS2.1", "KS2.1", "KS2.2", "KS3.2", "KS5.2", "KS5.2"]);
  assert.deepEqual(rules(findings, "audit"), ["KS5.2", "KS7.3"]);
  assert.deepEqual(findings.filter(f => f.rule === "KS5.2" && f.level === "error").map(f => f.file).sort(), ["scripts/compound.py", "scripts/mixed.py"]);
});

test("dependencies: host-private runtime, undeclared tools, and tools outside the list (including registered tools already removed from the server) all error", () => {
  const findings = lintSkill(
    "demo-skill",
    skill("name: demo-skill\ndescription: x\nallowed-tools: get_research_skill not_a_tool", "Use kabo-run-pipeline and mcp__plugin_kabo__run, then `youtube_get_video`.\n"),
    context,
  );
  assert.deepEqual(rules(findings), ["KS2.1", "KS2.1", "KS2.2", "KS2.2", "KS2.2"]);
});

test("length, nesting, license, and non-standard files", () => {
  const findings = lintSkill(
    "demo-skill",
    skill("name: demo-skill\ndescription: x", "line\n".repeat(501), {
      "references/long.md": "x".repeat(20_001),
      "assets/corpus/SKILL.md": "---\nname: nested\n---\n",
      "references/next.md": "See [it](../other-skill/SKILL.md).\n",
      "assets/LICENSE": "GNU AFFERO GENERAL PUBLIC LICENSE Version 3\n",
      "manifest.json": "{}",
      "references/mcp-bindings.json": "{}",
      "agents/openai.yaml": "policy:\n  allow_implicit_invocation: true\n",
    }),
    context,
  );
  assert.deepEqual(rules(findings), ["KS3.1", "KS3.2", "KS4.1", "KS4.2", "KS5.2", "KS6.1", "KS6.2", "KS6.3"]);
});

test("SKILL.md body limit is 21,000 characters; references stay at 20,000", () => {
  const front = "name: demo-skill\ndescription: x";
  assert.deepEqual(rules(lintSkill("demo-skill", skill(front, "x".repeat(21_000)), context)), []);
  assert.deepEqual(rules(lintSkill("demo-skill", skill(front, "x".repeat(21_001)), context)), ["KS3.1"]);
  assert.deepEqual(rules(lintSkill("demo-skill", skill(front, "Run.\n", { "references/a.md": "x".repeat(20_001) }), context)), ["KS3.2"]);
});

test("KS2.3: compatibility must state the Kabo permissions allowed-tools needs and the download host", () => {
  const scoped = { ...context, toolScopes: new Map([["youtube_get_video", ["data"]], ["get_research_data_job", ["data"]]]) };
  const files = compatibility => skill(`name: demo-skill\ndescription: x\ncompatibility: "${compatibility}"\nallowed-tools: youtube_get_video`, "Call `youtube_get_video`.\n", {
    "scripts/fetch.py": "import urllib.request\n",
  });
  const warnings = compatibility => lintSkill("demo-skill", files(compatibility), scoped).filter(f => f.rule === "KS2.3").map(f => f.message);
  assert.equal(warnings("Requires public data and storage.googleapis.com.").length, 1);
  assert.equal(warnings("Requires Python 3. Kabo permission: data.").length, 1);
  assert.deepEqual(warnings("Requires storage.googleapis.com links. Kabo permission: data."), []);
});

test("scripts: reading session records errors; network, install, and other skills' names are audit-only", () => {
  const findings = lintSkill(
    "demo-skill",
    skill("name: demo-skill\ndescription: x\ncompatibility: Python 3", "Run.\n", {
      "scripts/persist.py": "import os\nroot = os.environ.get('CODEX_HOME')\n",
      "scripts/fetch.py": "import urllib.request\nprint('pip install x')\nname = 'other-skill'\n",
      "assets/tool.py": "pass\n",
    }),
    context,
  );
  assert.deepEqual(rules(findings), ["KS7.1"]);
  assert.deepEqual(rules(findings, "audit"), ["KS4.2", "KS7.2", "KS7.3", "KS7.4"]);
});

test("the gate blocks only enabled skills; --strict blocks all", async t => {
  const repo = await mkdtemp(path.join(os.tmpdir(), "kabo-skills-lint-"));
  t.after(() => rm(repo, { recursive: true, force: true }));
  const source = fileURLToPath(new URL("..", import.meta.url));
  for (const name of ["contracts", "scripts"]) await cp(path.join(source, name), path.join(repo, name), { recursive: true });
  await symlink(path.join(source, "node_modules"), path.join(repo, "node_modules"));
  for (const [id, front] of [["good-skill", "name: good-skill\ndescription: Fine."], ["bad-skill", "name: bad-skill\ndescription: x\nexecution: inline"]]) {
    await mkdir(path.join(repo, "skills", id), { recursive: true });
    await writeFile(path.join(repo, "skills", id, "SKILL.md"), `---\n${front}\n---\nRun.\n`);
  }
  await writeFile(path.join(repo, "skills-spec.json"), JSON.stringify({ enforced: ["good-skill"] }));
  assert.deepEqual(lintSkills({ directory: repo }).map(result => [result.id, result.enforced, rules(result.findings)]), [["bad-skill", false, ["KS1.3"]], ["good-skill", true, []]]);
  const run = args => execFileSync(process.execPath, ["scripts/skills-lint.mjs", ...args], { cwd: repo, encoding: "utf8", stdio: "pipe" });
  assert.match(run(["--summary"]), /bad-skill \(gate not enabled\): errors 1/);
  assert.throws(() => run(["--strict"]), /gate failed: bad-skill/);
  await writeFile(path.join(repo, "skills-spec.json"), JSON.stringify({ enforced: ["bad-skill"] }));
  assert.throws(() => run([]), /gate failed: bad-skill/);
  await writeFile(path.join(repo, "skills-spec.json"), JSON.stringify({ enforced: ["missing-skill"] }));
  assert.throws(() => run([]), /nonexistent Skill/);
});
