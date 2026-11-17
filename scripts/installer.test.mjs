// The npm installer (installer/, published as `kabo-sh`) hard-codes values that this repository owns: the repository
// and marketplace names, the MCP address, the OAuth scopes and each host's install commands. These tests run the
// installer in dry-run mode and compare what it would do with INSTALL.md, host-auth.json, the MCP configs and the
// marketplace manifests, so a change on either side fails here until the other side follows.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
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
  // One pinned dependency, the YAML parser that edits DeepSeek Harness's patch file; nothing else.
  assert.deepEqual(Object.keys(installerPackage.dependencies ?? {}), ["yaml"]);
  assert.match(installerPackage.dependencies.yaml, /^\d+\.\d+\.\d+$/, "the yaml dependency is pinned to an exact version");
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

// The hosts the installer accepts, read from its help text.
function installerHosts() {
  const help = execFileSync(process.execPath, [path.join(installerDir, "bin/kabo.js"), "--help"], { encoding: "utf8" });
  const line = help.split("\n").find((entry) => entry.includes("--host <name>"));
  return line.split("--host <name>")[1].trim().split(" | ");
}

// A HOME with the data folders of Qwen Work and DeepSeek Harness, and a PATH with only node on it, so detection finds
// exactly those two desktop apps and no command-line host.
async function twoDesktopApps(t) {
  const home = await temp(t);
  await mkdir(path.join(home, ".qwenworkcn"), { recursive: true });
  await mkdir(path.join(home, ".dsh", "profiles", "desktop"), { recursive: true });
  const bin = path.join(home, "bin");
  await mkdir(bin);
  await symlink(process.execPath, path.join(bin, "node"));
  return { home, env: { PATH: bin, HOME: home, USERPROFILE: home, KABO_DETECT_FOLDERS_ONLY: "1" } };
}

function runInstaller(args, env) {
  try {
    return { status: 0, output: execFileSync(process.execPath, [path.join(installerDir, "bin/kabo.js"), ...args], { env, encoding: "utf8" }) };
  } catch (error) {
    return { status: error.status, output: `${error.stdout}` };
  }
}

test("several assistants found and none named: the installer installs nothing and asks for --host", async (t) => {
  const { home, env } = await twoDesktopApps(t);
  // Not a dry run: the point is that no other assistant's settings are touched.
  const { status, output } = runInstaller(["install"], env);
  assert.equal(status, 2);
  assert.match(output, /Found more than one assistant on this computer: Qwen Work, DeepSeek Harness\./);
  assert.match(output, /Nothing was installed\./);
  assert.match(output, /npx -y kabo-sh install --host qwen-work /);
  assert.match(output, /npx -y kabo-sh install --host deepseek /);
  assert.match(output, /npx -y kabo-sh install --host all/);
  for (const written of [".agents", "kabo-mcp-plugin", ".qwenworkcn/mcp.json", ".dsh/profiles/desktop/cordis.patch.yml"]) {
    assert.equal(existsSync(path.join(home, written)), false, `${written} must not be created`);
  }
});

test("--host all installs into every assistant found and labels each block", async (t) => {
  const { env } = await twoDesktopApps(t);
  const { output } = runInstaller(["install", "--host", "all", "--dry-run"], env);
  assert.match(output, /Results for 2 assistants\. Each block applies only to the assistant it names\./);
  assert.match(output, /^Qwen Work: /m);
  assert.match(output, /^DeepSeek Harness: /m);
});

test("each host's result says what was done and what is not done yet, never just 'installed'", async (t) => {
  for (const host of ["claude-code", "codex", "doubao", "qwen-work", "grok-bot", "muse", "skills-only"]) {
    const output = dryRun(host, await temp(t));
    const name = host === "skills-only" ? "Skills" : null;
    assert.match(output, new RegExp(`^${name ?? "[^\\n]+"}: [^\\n]+\\(dry run\\)\\. Not done yet: [^\\n]+\\.$`, "m"), host);
    assert.doesNotMatch(output, /installed\. What is left/, host);
    assert.match(output, /Kabo is ready only after the sign-in and one check/, host);
  }
});

test("INSTALL.md gives assistants the installer command with an existing --host", () => {
  const hosts = installerHosts();
  const uses = [...installDoc.matchAll(/kabo-sh install[^\n`]*/g)].map((match) => match[0]);
  assert.ok(uses.length > 0, "INSTALL.md shows the installer command");
  for (const use of uses) {
    const host = use.match(/--host ([\w-]+)/)?.[1];
    assert.ok(host, `"${use}" must name the host: without --host the installer stops when it finds several assistants`);
    assert.ok(hosts.includes(host), `"${use}" names a host the installer does not know`);
  }
});

// A HOME with fake WorkBuddy apps under ~/Applications (the installer also looks there on macOS). The bundled
// command line is an empty script: a dry run only asks it for the marketplace list and runs nothing else.
async function workBuddyApps(t, apps) {
  const { home, env } = await twoDesktopApps(t);
  await rm(path.join(home, ".qwenworkcn"), { recursive: true });
  await rm(path.join(home, ".dsh"), { recursive: true });
  for (const app of apps) {
    const bin = path.join(home, "Applications", app, "Contents", "Resources", "app.asar.unpacked", "cli", "bin");
    await mkdir(bin, { recursive: true });
    await writeFile(path.join(bin, "codebuddy"), "");
  }
  return { home, env };
}

test("WorkBuddy and WorkBuddy AI: --host workbuddy installs into each build found, into its own settings folder", async (t) => {
  const { home, env } = await workBuddyApps(t, ["WorkBuddy.app", "WorkBuddy AI.app"]);
  const { output } = runInstaller(["install", "--host", "workbuddy", "--dry-run"], env);
  assert.ok(output.includes(`CODEBUDDY_CONFIG_DIR=${path.join(home, ".workbuddy")} `));
  assert.ok(output.includes(`CODEBUDDY_CONFIG_DIR=${path.join(home, ".workbuddy-ai")} `));
  assert.match(output, /^WorkBuddy: Kabo plugin installed/m);
  assert.match(output, /^WorkBuddy AI: Kabo plugin installed/m);
  assert.match(output, /Quit WorkBuddy completely and open it again/);
  assert.match(output, /Quit WorkBuddy AI completely and open it again/);

  const only = runInstaller(["install", "--host", "workbuddy-ai", "--dry-run"], env).output;
  assert.doesNotMatch(only, /^WorkBuddy: /m);
  assert.match(only, /^WorkBuddy AI: Kabo plugin installed/m);

  const asked = runInstaller(["install"], env);
  assert.equal(asked.status, 2);
  assert.match(asked.output, /--host workbuddy +WorkBuddy\n/);
  assert.match(asked.output, /--host workbuddy-ai +WorkBuddy AI\n/);
});

test("WorkBuddy AI alone: --host workbuddy finds it; nothing found reports that instead of installing elsewhere", async (t) => {
  const { home, env } = await workBuddyApps(t, ["WorkBuddy AI.app"]);
  const { output } = runInstaller(["install", "--host", "workbuddy", "--dry-run"], env);
  assert.ok(output.includes(`CODEBUDDY_CONFIG_DIR=${path.join(home, ".workbuddy-ai")} `));
  assert.match(output, /^WorkBuddy AI: Kabo plugin installed/m);
  assert.doesNotMatch(output, /^WorkBuddy: /m);

  const none = await workBuddyApps(t, []);
  const missing = runInstaller(["install", "--host", "workbuddy", "--dry-run"], none.env);
  assert.equal(missing.status, 1);
  assert.match(missing.output, /WorkBuddy's built-in command line was not found/);
  assert.match(missing.output, /^WorkBuddy: not installed/m);
});

test("WorkBuddy: INSTALL.md says to restart WorkBuddy before trusting the connector, as the installer does", () => {
  const start = installDoc.indexOf("\n### WorkBuddy\n");
  assert.ok(start >= 0, 'INSTALL.md has no "### WorkBuddy" section');
  const section = installDoc.slice(start, installDoc.indexOf("\n## ", start));
  assert.match(section, /Quit WorkBuddy completely and open it again/);
  assert.match(section, /Trust/);
  assert.match(section, /--host workbuddy-ai/);
});
