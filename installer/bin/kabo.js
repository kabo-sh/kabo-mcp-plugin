#!/usr/bin/env node
"use strict";
// Kabo installer. Zero dependencies. Runs each host's own official commands;
// never edits a host's config files and never touches credentials.
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERSION = require("../package.json").version;
const REPO = "kabo-sh/kabo-mcp-plugin";
const REPO_URL = `https://github.com/${REPO}`;
const MCP_URL = "https://kabo.sh/mcp-pub";
const INSTALL_DOC = `${REPO_URL}/blob/stable/INSTALL.md`;

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const option = (name) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
};
const command = argv.find((a) => !a.startsWith("-")) || "install";
const dryRun = flag("--dry-run");
const forcedHost = option("--host");

const out = (line = "") => process.stdout.write(`${line}\n`);

function has(bin) {
  const probe = spawnSync(bin, ["--version"], { stdio: "ignore", shell: process.platform === "win32" });
  return !probe.error && probe.status === 0;
}

function run(bin, args) {
  out(`$ ${bin} ${args.join(" ")}`);
  if (dryRun) return true;
  const result = spawnSync(bin, args, { stdio: "inherit", shell: process.platform === "win32" });
  if (result.error || result.status !== 0) {
    out(`  That command did not finish (exit ${result.status ?? result.error.code}).`);
    return false;
  }
  return true;
}

function installClaudeCode() {
  out("Claude Code");
  const ok =
    run("claude", ["plugin", "marketplace", "add", REPO]) &&
    run("claude", ["plugin", "install", "kabo@kabo-mcp-plugin"]);
  if (!ok) return { host: "Claude Code", ok: false };
  return {
    host: "Claude Code",
    ok: true,
    left: [
      "In Claude Code, run /reload-plugins (or start a new session).",
      "Run /mcp, choose the Kabo server, and sign in to Kabo in your browser.",
      'Then say: "Get me started with Kabo."',
    ],
  };
}

function installCodex() {
  out("Codex");
  const ok =
    run("codex", ["plugin", "marketplace", "add", REPO]) &&
    run("codex", ["plugin", "add", "kabo@kabo-plugin-openai"]);
  if (!ok) return { host: "Codex", ok: false };
  return {
    host: "Codex",
    ok: true,
    left: [
      "Sign in to Kabo: run  codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write  and approve in your browser.",
      "Open a new task so Codex loads the Kabo tools and Skills.",
      'Then say: "Get me started with Kabo."',
    ],
  };
}

function installSkillsOnly() {
  out("Skills (no Claude Code or Codex command found on this computer)");
  const target = path.join(os.homedir(), "kabo-mcp-plugin");
  let ok;
  if (fs.existsSync(path.join(target, ".git"))) {
    ok = run("git", ["-C", target, "pull", "--ff-only"]);
  } else {
    ok = run("git", ["clone", "--branch", "stable", "--single-branch", `${REPO_URL}.git`, target]);
  }
  if (!ok) return { host: "Skills", ok: false };
  return {
    host: "Skills",
    ok: true,
    left: [
      `Skills are in ${path.join(target, "skills")}. Import each folder as a skill, or read a Skill's SKILL.md from there when the user asks for it.`,
      `Add the connection: a remote MCP server at ${MCP_URL} (Streamable HTTP, OAuth in the browser, no API key).`,
      "  Grok Bot: add it as a custom app from the chat and show the user the Connect card.",
      "  Muse: register it as a custom connector from the chat and show the user the Connect card.",
      "  ChatGPT: open Plugins, find Kabo and add it.",
      "The user signs in to Kabo in the browser. Never ask for a password, token or API key.",
      `Full instructions for AI assistants: ${INSTALL_DOC}`,
    ],
  };
}

function help() {
  out(`kabo ${VERSION}`);
  out("Install Kabo into your AI assistant.");
  out("");
  out("  npx kabo-sh install                 detect Claude Code and Codex and install the Kabo plugin");
  out("  npx kabo-sh install --host <name>   claude-code | codex | skills-only");
  out("  npx kabo-sh install --dry-run       print the commands without running them");
  out("  npx kabo-sh doctor                  show what this computer has");
  out("");
  out(`More: https://kabo.sh/install   ${REPO_URL}`);
}

function doctor() {
  out(`kabo ${VERSION} on node ${process.version} (${process.platform} ${process.arch})`);
  for (const bin of ["claude", "codex", "git", "python3"]) {
    out(`  ${bin}: ${has(bin) ? "found" : "not found"}`);
  }
}

function install() {
  out(`Kabo installer ${VERSION}${dryRun ? " (dry run: nothing is changed)" : ""}`);
  out("");
  const results = [];
  const wantClaude = forcedHost ? forcedHost === "claude-code" : has("claude");
  const wantCodex = forcedHost ? forcedHost === "codex" : has("codex");
  if (wantClaude) results.push(installClaudeCode());
  if (wantCodex) results.push(installCodex());
  if (results.length === 0 || forcedHost === "skills-only") results.push(installSkillsOnly());
  out("");
  let failed = false;
  for (const result of results) {
    if (!result.ok) {
      failed = true;
      out(`${result.host}: not installed. See ${INSTALL_DOC}`);
      continue;
    }
    out(`${result.host}: installed${dryRun ? " (dry run)" : ""}. What is left for you:`);
    let step = 0;
    for (const line of result.left) out(line.startsWith("  ") ? `  ${line}` : `  ${(step += 1)}. ${line}`);
  }
  out("");
  out("Kabo never asks for a password or API key here. Sign-in happens in your browser.");
  process.exitCode = failed ? 1 : 0;
}

if (flag("--version") || flag("-v")) out(VERSION);
else if (flag("--help") || flag("-h") || command === "help") help();
else if (command === "doctor") doctor();
else if (command === "install") install();
else {
  out(`Unknown command: ${command}`);
  help();
  process.exitCode = 1;
}
