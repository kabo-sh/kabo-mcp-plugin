// The npm installer (installer/, published as `kabo-sh`) hard-codes values that this repository owns: the repository
// and marketplace names, the MCP address, the OAuth scopes and each host's install commands. These tests run the
// installer in dry-run mode and compare what it would do with INSTALL.md, host-auth.json, the MCP configs and the
// marketplace manifests, so a change on either side fails here until the other side follows.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { isPackageFile } from "./package-layout.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const installerDir = path.join(root, "installer");
const read = (file) => readFileSync(path.join(root, file), "utf8");
const json = (file) => JSON.parse(read(file));
const installerPackage = json("installer/package.json");
const installDoc = read("INSTALL.md");

async function temp(t) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-installer-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

// HOME points at an empty directory so the skills-only path always prints a fresh clone, and PATH is kept only so
// node itself resolves; --host skips detection, so no host binary is ever probed or run.
function dryRun(host, home) {
  return execFileSync(process.execPath, [path.join(installerDir, "bin/kabo.js"), "install", "--host", host, "--dry-run"], {
    env: { PATH: process.env.PATH, HOME: home, USERPROFILE: home },
    encoding: "utf8",
  });
}
const commands = (output) => output.split("\n").filter((line) => line.startsWith("$ ")).map((line) => line.slice(2));

// The shell lines of every ```sh block in one INSTALL.md section.
function docCommands(heading) {
  const start = installDoc.indexOf(`\n## ${heading}\n`);
  assert.ok(start >= 0, `INSTALL.md has no "## ${heading}" section`);
  const end = installDoc.indexOf("\n## ", start + 1);
  const section = installDoc.slice(start, end < 0 ? undefined : end);
  return [...section.matchAll(/```sh\n([\s\S]*?)```/g)]
    .flatMap((match) => match[1].split("\n"))
    .map((line) => line.trim())
    .filter(Boolean);
}

// The repository INSTALL.md tells assistants to install from; every other value is checked against it.
const repoUrl = installDoc.match(/Install only from `(https:\/\/github\.com\/[^`]+)`/)?.[1];
const repo = repoUrl?.replace("https://github.com/", "");

test("INSTALL.md names the official repository", () => {
  assert.match(repo ?? "", /^[\w.-]+\/[\w.-]+$/);
});

test("the npm package points at this repository and stays out of the plugin package", () => {
  assert.equal(installerPackage.name, "kabo-sh");
  assert.equal(installerPackage.repository.url, `git+${repoUrl}.git`);
  assert.equal(installerPackage.repository.directory, "installer");
  assert.equal(installerPackage.bin["kabo-sh"], "bin/kabo.js");
  assert.deepEqual(installerPackage.dependencies ?? {}, {}, "the installer has no runtime dependencies");
  assert.equal(isPackageFile("installer/bin/kabo.js"), false);
  assert.equal(isPackageFile("installer/package.json"), false);
});

test("Claude Code: the installer runs exactly INSTALL.md's commands, against this repository's marketplace", async (t) => {
  const run = commands(dryRun("claude-code", await temp(t)));
  assert.deepEqual(run, docCommands("Claude Code"));
  const marketplace = json(".claude-plugin/marketplace.json");
  const plugin = json(".claude-plugin/plugin.json").name;
  assert.ok(marketplace.plugins.some((entry) => entry.name === plugin));
  assert.deepEqual(run, [
    `claude plugin marketplace add ${repo}`,
    `claude plugin install ${plugin}@${marketplace.name}`,
  ]);
});

test("Codex: the installer runs INSTALL.md's commands and prints its sign-in command with host-auth.json's scopes", async (t) => {
  const output = dryRun("codex", await temp(t));
  const doc = docCommands("Codex and ChatGPT");
  const [install, login] = [doc.slice(0, 2), doc[2]];
  const marketplace = json(".agents/plugins/marketplace.json");
  const plugin = json("plugin.json").name;
  assert.ok(marketplace.plugins.some((entry) => entry.name === plugin));
  assert.deepEqual(commands(output), install);
  assert.deepEqual(install, [
    `codex plugin marketplace add ${repo}`,
    `codex plugin add ${plugin}@${marketplace.name}`,
  ]);
  const auth = json("host-auth.json");
  const scopes = [...auth.baseScopes, ...auth.defaultScopes].join(",");
  assert.equal(login, `codex mcp login ${plugin} --scopes ${scopes}`);
  assert.ok(output.includes(login), "the installer prints INSTALL.md's Codex sign-in command");
});

test("skills only: the installer clones INSTALL.md's branch and prints the MCP address every config uses", async (t) => {
  const home = await temp(t);
  const output = dryRun("skills-only", home);
  const clone = docCommands("Grok Bot").find((line) => line.startsWith("git clone "));
  assert.ok(clone, "INSTALL.md shows the clone command under Grok Bot");
  assert.deepEqual(commands(output), [clone.replace(/ ~\//, ` ${home}/`)]);

  const mcpUrl = json("host-auth.json").resource;
  assert.equal(json("mcp.json").mcpServers.kabo.url, mcpUrl);
  assert.equal(json(".mcp.json").mcpServers.kabo.url, mcpUrl);
  assert.ok(installDoc.includes(`\`${mcpUrl}\``), "INSTALL.md names the same MCP address");
  assert.ok(output.includes(`remote MCP server at ${mcpUrl} `), "the installer prints the MCP address");
});

test("every host points to INSTALL.md on the stable branch, and that file exists", async (t) => {
  const home = await temp(t);
  const link = `${repoUrl}/blob/stable/INSTALL.md`;
  assert.ok(existsSync(path.join(root, "INSTALL.md")));
  assert.ok(dryRun("skills-only", home).includes(link));
  assert.ok(read("installer/bin/kabo.js").includes("/blob/stable/INSTALL.md"));
});
