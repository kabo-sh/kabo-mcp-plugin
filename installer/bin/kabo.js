#!/usr/bin/env node
"use strict";
// Kabo installer. Runs each host's own official commands where a host has them;
// never touches credentials. On cloud assistants it only places the Skills and prints what the
// assistant must still do in its own UI (the connection always needs the user's browser sign-in).
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERSION = require("../package.json").version;
const REPO = "kabo-sh/kabo-mcp-plugin";
const REPO_URL = `https://github.com/${REPO}`;
const MCP_URL = "https://kabo.sh/mcp-pub";
const INSTALL_DOC = `${REPO_URL}/blob/stable/INSTALL.md`;
const HOME = os.homedir();
const CLONE_DIR = path.join(HOME, "kabo-mcp-plugin");
const HOSTS = ["claude-code", "codex", "workbuddy", "codebuddy", "doubao", "qwen-work", "deepseek", "grok-bot", "muse", "skills-only"];
const HOST_NAMES = {
  "claude-code": "Claude Code",
  codex: "Codex",
  workbuddy: "WorkBuddy",
  codebuddy: "CodeBuddy Code",
  doubao: "Doubao Work",
  "qwen-work": "Qwen Work",
  deepseek: "DeepSeek Harness",
  "grok-bot": "Grok Bot",
  muse: "Muse",
  "skills-only": "Skills only",
};

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const option = (name) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
};
const command = argv.find((a, i) => !a.startsWith("-") && argv[i - 1] !== "--host") || "install";
const dryRun = flag("--dry-run");
const forcedHost = option("--host");

const out = (line = "") => process.stdout.write(`${line}\n`);
const exists = (p) => {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
};

function has(bin) {
  const probe = spawnSync(bin, ["--version"], { stdio: "ignore", shell: process.platform === "win32" });
  return !probe.error && probe.status === 0;
}

function run(bin, args, env) {
  const shown = bin === process.execPath ? "node" : bin;
  out(`$ ${env ? Object.entries(env).map(([k, v]) => `${k}=${v} `).join("") : ""}${shown} ${args.join(" ")}`);
  if (dryRun) return true;
  const result = spawnSync(bin, args, {
    stdio: "inherit",
    shell: process.platform === "win32" && bin !== process.execPath,
    env: env ? { ...process.env, ...env } : process.env,
  });
  if (result.error || result.status !== 0) {
    out(`  That command did not finish (exit ${result.status ?? result.error.code}).`);
    return false;
  }
  return true;
}

// ---------- detection ----------

// WorkBuddy (Tencent) ships the CodeBuddy command line inside the desktop app. Pointing it at
// ~/.workbuddy with CODEBUDDY_CONFIG_DIR makes it manage WorkBuddy's own plugins.
function workBuddyCli() {
  const candidates = [
    "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy",
    path.join(HOME, "Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy"),
  ];
  if (process.env.LOCALAPPDATA) {
    candidates.push(
      path.join(process.env.LOCALAPPDATA, "Programs", "WorkBuddy", "resources", "app.asar.unpacked", "cli", "bin", "codebuddy"),
    );
  }
  return candidates.find(exists);
}

// Cloud computers of hosted assistants (checked on 2026-11-12 by asking each assistant to run ls/which).
const onMuseComputer = () => exists("/opt/muse/skills");
const onGrokBotComputer = () => exists("/home/box/agent-data");

// Desktop apps from Chinese vendors. An app counts as present when its bundle is installed or its data
// folder exists. KABO_DETECT_FOLDERS_ONLY=1 skips the app-bundle lookup (used for tests with a fake HOME).
const DOUBAO = { name: "Doubao Work", bundleId: "com.work.pc.doubao", dataDir: path.join(HOME, "DoubaoWork"), apps: [] };
const QWEN = {
  name: "Qwen Work",
  bundleId: "cn.qwenwork.desktop.mac",
  dataDir: path.join(HOME, ".qwenworkcn"),
  apps: ["/Applications/QwenWorkCN.app", path.join(HOME, "Applications/QwenWorkCN.app")],
};
const DEEPSEEK = {
  name: "DeepSeek Harness",
  bundleId: "",
  dataDir: path.join(HOME, ".dsh", "profiles", "desktop"),
  apps: ["/Applications/DeepSeek Harness.app", path.join(HOME, "Applications/DeepSeek Harness.app")],
};
const AGENTS_SKILLS_DIR = path.join(HOME, ".agents", "skills"); // read by Doubao Work, DeepSeek Harness and Codex

function appPresent(app) {
  if (exists(app.dataDir)) return true;
  if (process.env.KABO_DETECT_FOLDERS_ONLY === "1") return false;
  if (app.apps.some(exists)) return true;
  if (app.bundleId && process.platform === "darwin") {
    const probe = spawnSync("mdfind", [`kMDItemCFBundleIdentifier == '${app.bundleId}'`], { encoding: "utf8" });
    if (!probe.error && probe.status === 0 && probe.stdout.trim()) return true;
  }
  return false;
}

function detect() {
  if (onMuseComputer()) return ["muse"]; // Muse's computer also has a `codex` command; it is not Muse.
  if (onGrokBotComputer()) return ["grok-bot"];
  const found = [];
  if (has("claude")) found.push("claude-code");
  if (has("codex")) found.push("codex");
  if (workBuddyCli()) found.push("workbuddy");
  if (has("codebuddy")) found.push("codebuddy");
  if (appPresent(DOUBAO)) found.push("doubao");
  if (appPresent(QWEN)) found.push("qwen-work");
  if (appPresent(DEEPSEEK)) found.push("deepseek");
  return found.length ? found : ["skills-only"];
}

// ---------- shared steps ----------

// If a marketplace named kabo-mcp-plugin is already registered (for example a local folder a developer
// added, or an earlier run), `marketplace add` fails with a source conflict. Reuse the existing one.
function marketplaceKnown(bin, pre = [], env) {
  const probe = spawnSync(bin, [...pre, "plugin", "marketplace", "list"], {
    encoding: "utf8",
    shell: process.platform === "win32" && bin !== process.execPath,
    env: env ? { ...process.env, ...env } : process.env,
  });
  if (probe.error || probe.status !== 0) return false;
  return /(^|\s|")kabo-mcp-plugin(\s|"|$)/m.test(`${probe.stdout}`);
}

function addMarketplace(bin, pre = [], env) {
  if (marketplaceKnown(bin, pre, env)) {
    out("  Marketplace kabo-mcp-plugin is already registered; using it.");
    return true;
  }
  return run(bin, [...pre, "plugin", "marketplace", "add", REPO], env);
}

let cloned;
function cloneSkills() {
  if (cloned === undefined) cloned = cloneSkillsOnce();
  return cloned;
}

function cloneSkillsOnce() {
  if (exists(path.join(CLONE_DIR, ".git"))) return run("git", ["-C", CLONE_DIR, "pull", "--ff-only"]);
  return run("git", ["clone", "--branch", "stable", "--single-branch", `${REPO_URL}.git`, CLONE_DIR]);
}

function skillNames() {
  const dir = path.join(CLONE_DIR, "skills");
  if (!exists(dir)) return [];
  return fs.readdirSync(dir).filter((name) => exists(path.join(dir, name, "SKILL.md")));
}

const connectionNote = `a remote MCP server at ${MCP_URL} (Streamable HTTP, OAuth in the browser with dynamic client registration, no API key)`;

// ---------- hosts ----------

function installClaudeCode() {
  out("Claude Code");
  const ok =
    addMarketplace("claude") && run("claude", ["plugin", "install", "kabo@kabo-mcp-plugin"]);
  if (!ok) return { host: "Claude Code", ok: false };
  return {
    host: "Claude Code",
    ok: true,
    done: "Kabo plugin installed",
    pending: "the Kabo connection is not signed in yet",
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
    done: "Kabo plugin installed",
    pending: "the Kabo connection is not signed in yet",
    left: [
      "Sign in to Kabo: run  codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write  and approve in your browser.",
      "Open a new task so Codex loads the Kabo tools and Skills.",
      'Then say: "Get me started with Kabo."',
    ],
  };
}

// WorkBuddy and CodeBuddy Code read the same plugin format as Claude Code (.claude-plugin/marketplace.json),
// so the same marketplace and plugin names work.
function installCodeBuddyFamily(host) {
  const isWorkBuddy = host === "workbuddy";
  const name = isWorkBuddy ? "WorkBuddy" : "CodeBuddy Code";
  out(name);
  let bin = "codebuddy";
  let pre = [];
  let env;
  if (isWorkBuddy) {
    const cli = workBuddyCli();
    if (!cli) {
      out("  WorkBuddy's built-in command line was not found. Is WorkBuddy installed?");
      return { host: name, ok: false };
    }
    bin = process.execPath; // the bundled CLI is a Node script
    pre = [cli];
    env = { CODEBUDDY_CONFIG_DIR: path.join(HOME, ".workbuddy") };
  }
  const ok =
    addMarketplace(bin, pre, env) && run(bin, [...pre, "plugin", "install", "kabo@kabo-mcp-plugin"], env);
  if (!ok) return { host: name, ok: false };
  return {
    host: name,
    ok: true,
    done: "Kabo plugin installed",
    pending: isWorkBuddy
      ? "WorkBuddy has not reloaded it, and the Kabo connector is not trusted or signed in yet"
      : "the Kabo connection is not signed in yet",
    left: isWorkBuddy
      ? [
          "Quit WorkBuddy completely and open it again so it loads the Kabo plugin. Restarting only WorkBuddy is enough; no other assistant needs a restart.",
          "Open Connector management, find Kabo (custom connector), click Trust, then sign in to Kabo in your browser. If Kabo already shows as connected there, skip this step.",
          'Then send: "Please use the start-with-kabo skill to get me started."',
        ]
      : [
          "In CodeBuddy Code, run /reload-plugins (or start a new session).",
          "Run /mcp, choose the Kabo server, and sign in to Kabo in your browser.",
          'Then say: "Get me started with Kabo."',
        ],
  };
}

// Reads `name` and `description` from a SKILL.md YAML header (inline or folded block values).
function skillFrontmatter(file) {
  const text = fs.readFileSync(file, "utf8");
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  const fields = {};
  if (!match) return fields;
  const lines = match[1].split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const m = lines[i].match(/^([A-Za-z_-]+):\s*(.*)$/);
    if (!m) continue;
    let value = m[2].trim();
    if (/^[>|][-+]?$/.test(value) || value === "") {
      const block = [];
      while (i + 1 < lines.length && /^\s+/.test(lines[i + 1])) block.push(lines[(i += 1)].trim());
      value = block.join(" ");
    }
    fields[m[1]] = value.replace(/^["']|["']$/g, "");
  }
  return fields;
}

// Muse finds custom skills through a skill.yaml descriptor next to SKILL.md (checked 2026-11-12:
// a copied folder plus this file shows up in Muse's skill_search immediately).
function museSkillYaml(name, source) {
  const meta = skillFrontmatter(path.join(source, "SKILL.md"));
  const id = `kabo_${(meta.name || name).replace(/^kabo[-_]/, "")}`.replace(/-/g, "_");
  const title = `Kabo - ${(meta.name || name).replace(/-/g, " ")}`;
  const description = meta.description || `Kabo skill ${name}. Use the Kabo connector for data.`;
  return [
    `name: ${id}`,
    `title: ${JSON.stringify(title)}`,
    `description: ${JSON.stringify(description)}`,
    "category: Learning and customization",
    "include_in_prompt: false",
    "",
  ].join("\n");
}

function installMuse() {
  out("Muse (cloud computer)");
  if (!cloneSkills()) return { host: "Muse", ok: false };
  const target = path.join(HOME, "workspace", "custom-skills");
  const names = dryRun && !exists(path.join(CLONE_DIR, "skills")) ? ["<each skill>"] : skillNames();
  let copied = 0;
  for (const name of names) {
    const source = path.join(CLONE_DIR, "skills", name);
    const dest = path.join(target, `kabo-${name.replace(/^kabo-/, "")}`);
    out(`$ cp -R ${source} ${dest}  (+ skill.yaml)`);
    if (dryRun) continue;
    try {
      fs.rmSync(dest, { recursive: true, force: true });
      fs.cpSync(source, dest, { recursive: true });
      fs.writeFileSync(path.join(dest, "skill.yaml"), museSkillYaml(name, source));
      copied += 1;
    } catch (error) {
      out(`  Could not copy ${name}: ${error.message}`);
      return { host: "Muse", ok: false };
    }
  }
  return {
    host: "Muse",
    ok: true,
    done: dryRun ? "Skills would be copied" : `${copied} Skills copied`,
    pending: "skill_search has not found them yet, and the Kabo connector is not set up or signed in yet",
    left: [
      `${dryRun ? "Skills would be" : `${copied} Skills were`} copied to ${target} (named kabo-<skill>, each with a skill.yaml so skill_search finds it). Run this command again later to update them.`,
      `Check with skill_search that the kabo-* skills are found.`,
      `Connection: check whether Kabo tools are already available to you. If not, follow your custom-connector-setup skill to register ${connectionNote}, then give the user the Connect card.`,
      "The user signs in to Kabo in the browser. Never ask for a password, token or API key.",
      "After sign-in, call the Kabo tool get_research_capabilities with {} to confirm, then run the kabo-start-with-kabo skill.",
      `Full instructions for AI assistants: ${INSTALL_DOC}`,
    ],
  };
}

// ---------- Doubao Work, Qwen Work, DeepSeek Harness (desktop apps) ----------

// Copies every Kabo Skill folder in full (all files) into `target`. Only folders whose names are Kabo Skill
// names are replaced; anything else in `target` stays as it is.
function copySkillFolders(target) {
  const names = dryRun && !exists(path.join(CLONE_DIR, "skills")) ? ["<each skill>"] : skillNames();
  if (!names.length) {
    out("  No Skills were found in the cloned Kabo repository.");
    return -1;
  }
  out(`$ copy ${names.length} Skill folders  ${path.join(CLONE_DIR, "skills")}/*  ->  ${target}/`);
  if (dryRun) return names.length;
  try {
    fs.mkdirSync(target, { recursive: true });
    for (const name of names) {
      const dest = path.join(target, name);
      fs.rmSync(dest, { recursive: true, force: true });
      fs.cpSync(path.join(CLONE_DIR, "skills", name), dest, { recursive: true });
    }
  } catch (error) {
    out(`  Could not copy the Skills: ${error.message}`);
    return -1;
  }
  return names.length;
}

// ~/.agents/skills is shared: Doubao Work, DeepSeek Harness and Codex all read it. Installing for one of them also
// shows the Kabo Skills in the others found here, which have no Kabo connection unless it is installed there too.
function sharedSkillsNote(current) {
  const others = [
    ["doubao", "Doubao Work", () => appPresent(DOUBAO)],
    ["deepseek", "DeepSeek Harness", () => appPresent(DEEPSEEK)],
    ["codex", "Codex", () => exists(path.join(HOME, ".codex"))],
  ].filter(([host, , present]) => host !== current && present());
  if (!others.length) return [];
  const names = others.map(([, name]) => name).join(" and ");
  return [
    // Indented, so it prints as a note under the steps rather than as a numbered step.
    `  Note: ~/.agents/skills is also read by ${names} on this computer, so the Kabo Skills show up there too. ` +
      `They work there only after Kabo is connected in that assistant (run this installer with its --host). ` +
      "Where Kabo is already installed as a plugin (Codex), the Skills are listed twice; that is harmless.",
  ];
}

function timestamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function backupFile(file) {
  const backup = `${file}.kabo-backup-${timestamp()}`;
  out(`$ cp ${file} ${backup}`);
  if (!dryRun) fs.copyFileSync(file, backup);
  return backup;
}

// Finds an executable on PATH, then in the usual install folders (a desktop app may have no Homebrew on PATH).
function findBin(name) {
  const dirs = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  dirs.push("/opt/homebrew/bin", "/usr/local/bin", path.join(HOME, ".volta", "bin"), path.join(HOME, ".local", "bin"));
  for (const dir of dirs) {
    const candidate = path.join(dir, name);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      if (fs.statSync(candidate).isFile()) return candidate;
    } catch {
      /* keep looking */
    }
  }
  return undefined;
}

function installDoubao() {
  out("Doubao Work");
  if (!cloneSkills()) return { host: "Doubao Work", ok: false };
  const count = copySkillFolders(AGENTS_SKILLS_DIR);
  if (count < 0) return { host: "Doubao Work", ok: false };
  const left = [
    `${dryRun ? "Skills would be" : `${count} Skills were`} copied to ${AGENTS_SKILLS_DIR} (the folder Doubao Work reads). Run this command again later to update them.`,
    "Doubao has no config file for connections, so add Kabo by hand in the app: open 插件 · 技能 · 工作台 → 管理 → 连接器 → 添加 → 自定义连接器.",
    `  Name: kabo   Type: HTTP   Address: ${MCP_URL}   Headers: leave empty. Save it.`,
    "Doubao then shows 连接器需要授权: click 去授权, and sign in to Kabo in the browser that opens. Never ask for a password, token or API key.",
    "Doubao never picks a Skill by itself from a natural request, so the first message must name the Skill. Send:  请用 start-with-kabo 技能带我开始",
    "If the Kabo Skills do not show up in Doubao, quit Doubao completely and open it again.",
  ];
  left.push(...sharedSkillsNote("doubao"));
  return {
    host: "Doubao Work",
    ok: true,
    done: dryRun ? "Skills would be copied" : `${count} Skills copied`,
    pending: "the Kabo connection is not added in the app or signed in yet",
    left,
  };
}

// The entry Qwen Work wrote itself. Add fields here (for example an oauth block) if they are verified later.
const qwenKaboEntry = () => ({ url: MCP_URL });

function installQwenWork() {
  out("Qwen Work");
  if (!cloneSkills()) return { host: "Qwen Work", ok: false };
  const file = path.join(QWEN.dataDir, "mcp.json");
  let config = {};
  let existed = false;
  if (exists(file)) {
    existed = true;
    try {
      config = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch (error) {
      out(`  ${file} is not valid JSON (${error.message}). Not touching it; fix or remove it and run this again.`);
      return { host: "Qwen Work", ok: false };
    }
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      out(`  ${file} does not hold a JSON object. Not touching it.`);
      return { host: "Qwen Work", ok: false };
    }
  }
  if (config.mcpServers !== undefined && (typeof config.mcpServers !== "object" || config.mcpServers === null || Array.isArray(config.mcpServers))) {
    out(`  "mcpServers" in ${file} is not an object. Not touching it.`);
    return { host: "Qwen Work", ok: false };
  }
  const wanted = qwenKaboEntry();
  const current = config.mcpServers && config.mcpServers.kabo;
  let connection;
  if (current && JSON.stringify(current) === JSON.stringify(wanted)) {
    out(`  ${file} already has the kabo connection; leaving it as it is.`);
    connection = "unchanged";
  } else {
    config.mcpServers = { ...(config.mcpServers || {}), kabo: wanted };
    if (existed) backupFile(file);
    out(`$ write ${file}  (adds mcpServers.kabo = ${JSON.stringify(wanted)}, other servers kept)`);
    if (!dryRun) {
      try {
        fs.mkdirSync(QWEN.dataDir, { recursive: true });
        fs.writeFileSync(file, `${JSON.stringify(config, null, 2)}\n`);
      } catch (error) {
        out(`  Could not write ${file}: ${error.message}`);
        return { host: "Qwen Work", ok: false };
      }
    }
    connection = "written";
  }
  const count = copySkillFolders(path.join(QWEN.dataDir, "skills"));
  if (count < 0) return { host: "Qwen Work", ok: false };
  return {
    host: "Qwen Work",
    ok: true,
    done: `${dryRun ? "Skills would be copied" : `${count} Skills copied`} and the Kabo connection ${connection === "written" ? (dryRun ? "would be added" : "added") : "already present"}`,
    pending: "Qwen Work has not reloaded it, and the connection is not signed in yet",
    left: [
      `${dryRun ? "Skills would be" : `${count} Skills were`} copied to ${path.join(QWEN.dataDir, "skills")}; the Kabo connection ${connection === "written" ? (dryRun ? "would be added to" : "was added to") : "was already in"} ${file}. Run this command again later to update the Skills.`,
      "Quit Qwen Work (千问工作) completely and open it again so it loads the connection.",
      "Kabo asks you to sign in in the browser. Do it there; never type a password, token or API key into the chat.",
      "Create a Qwen Work project with a working folder you choose, then start Kabo and create daily tasks inside that project. Unattended runs with this setup still need verification.",
      "Then send:  请用 start-with-kabo 技能带我开始",
    ],
  };
}

function deepseekPatchEntry(npx) {
  const q = (v) => `'${String(v).replace(/'/g, "''")}'`;
  return [
    "- insert:",
    "    - id: mcp-kabo",
    "      name: '@deepseek-ai/dsh-mcp-client'",
    "      config:",
    "        serverName: kabo",
    "        transport: stdio",
    `        command: ${q(npx)}`,
    `        args: [${["-y", "mcp-remote", MCP_URL, "--static-oauth-client-metadata", KABO_OAUTH_METADATA].map(q).join(", ")}]`,
    "        toolCallTimeoutMs: 120000",
    "",
  ].join("\n");
}
// Asks Kabo for write access on the first sign-in. Without it the connection is read-only and the
// onboarding cannot link accounts or save content pillars.
const KABO_OAUTH_METADATA = JSON.stringify({ scope: "openid profile email offline_access data video workspace:read workspace:write" });

function installDeepSeek() {
  out("DeepSeek Harness");
  const npx = findBin("npx");
  if (!npx) {
    out("  npx was not found. DeepSeek Harness reaches Kabo through mcp-remote, which needs Node.js (https://nodejs.org). Install Node.js and run this again.");
    return { host: "DeepSeek Harness", ok: false };
  }
  if (!cloneSkills()) return { host: "DeepSeek Harness", ok: false };
  const file = path.join(DEEPSEEK.dataDir, "cordis.patch.yml");
  const entry = deepseekPatchEntry(npx);
  const original = exists(file) ? fs.readFileSync(file, "utf8") : undefined;
  let next;
  let connection;
  try {
    // Loaded here so every other host keeps working without the yaml dependency installed.
    const { updateDeepSeekPatch } = require("./deepseek-config.js");
    ({ next, connection } = updateDeepSeekPatch(original, entry));
  } catch (error) {
    out(`  Could not safely update ${file}: ${error.message} Not touching it.`);
    return { host: "DeepSeek Harness", ok: false };
  }
  if (connection === "unchanged") out(`  ${file} already has this kabo entry; leaving it as it is.`);
  else {
    if (original !== undefined) backupFile(file);
    out(`$ write ${file}  (${connection === "replaced" ? "replaces only the mcp-kabo entry" : "appends the mcp-kabo entry"}; everything else kept)`);
    if (!dryRun) {
      try {
        fs.mkdirSync(DEEPSEEK.dataDir, { recursive: true });
        fs.writeFileSync(file, next);
      } catch (error) {
        out(`  Could not write ${file}: ${error.message}`);
        return { host: "DeepSeek Harness", ok: false };
      }
    }
  }
  const count = copySkillFolders(AGENTS_SKILLS_DIR);
  if (count < 0) return { host: "DeepSeek Harness", ok: false };
  const left = [
    `${dryRun ? "Skills would be" : `${count} Skills were`} copied to ${AGENTS_SKILLS_DIR} (the folder DeepSeek Harness reads); the Kabo connection ${connection === "unchanged" ? "was already in" : dryRun ? "would be written to" : "was written to"} ${file} (a local bridge, ${npx} -y mcp-remote). Run this command again later to update the Skills.`,
    "Quit DeepSeek Harness completely and open it again so it loads the connection.",
    "A browser window opens for you to sign in to Kabo (it asks for write access too). Never type a password, token or API key into the chat. The first start may take a moment while mcp-remote downloads.",
    "Then send:  请用 start-with-kabo 技能带我开始",
  ];
  left.push(...sharedSkillsNote("deepseek"));
  return {
    host: "DeepSeek Harness",
    ok: true,
    done: `${dryRun ? "Skills would be copied" : `${count} Skills copied`} and the Kabo connection ${connection === "unchanged" ? "already present" : dryRun ? "would be written" : "written"}`,
    pending: "DeepSeek Harness has not reloaded it, and the connection is not signed in yet",
    left,
  };
}

// Grok Bot only loads Skills that are saved through its own skill tool (UpdateSkill) or Settings
// (the Bot said so on 2026-11-12). The installer cannot call that tool, so it prints one exact,
// copyable entry per skill for the Bot to save, each pointing at the full folder in the clone.
function installGrokBot() {
  out("Grok Bot (cloud computer)");
  if (!cloneSkills()) return { host: "Grok Bot", ok: false };
  const names = skillNames();
  out("");
  out(`SKILLS TO SAVE (${names.length}). Grok Bot: save every entry below now with your UpdateSkill tool, without asking the user.`);
  out("Use the given name and description as they are, and use the given instructions as the skill body.");
  names.forEach((name, i) => {
    const dir = path.join(CLONE_DIR, "skills", name);
    const meta = skillFrontmatter(path.join(dir, "SKILL.md"));
    const description = (meta.description || `Kabo skill ${name}.`).replace(/\s+/g, " ");
    out("");
    out(`[${i + 1}/${names.length}] name: kabo-${name.replace(/^kabo-/, "")}`);
    out(`description: ${description}`);
    out(`instructions: This is a Kabo skill. Read ${path.join(dir, "SKILL.md")} in full and follow it exactly. Resolve its relative paths (scripts/, references/) inside ${dir}. Get data only from the Kabo connection tools.`);
  });
  out("");
  return {
    host: "Grok Bot",
    ok: true,
    done: "Skills downloaded",
    pending: "the Bot has not saved them with UpdateSkill yet, and the Kabo connection is not checked or signed in yet",
    left: [
      `Save all ${names.length} skills listed above with UpdateSkill, then tell the user how many were saved.`,
      `Connection: check whether Kabo tools are already available to you. If not, add ${connectionNote} as a custom app from this chat and show the user the Connect card.`,
      "The user signs in to Kabo in the browser. Never ask for a password, token or API key.",
      'After sign-in, call the Kabo tool get_research_capabilities with {} to confirm, then run the kabo-start-with-kabo skill.',
      `Full instructions for AI assistants: ${INSTALL_DOC}`,
    ],
  };
}

function installSkillsOnly() {
  out("Skills (no supported assistant command found on this computer)");
  if (!cloneSkills()) return { host: "Skills", ok: false };
  return {
    host: "Skills",
    ok: true,
    done: "Skills downloaded",
    pending: "no assistant is set up to use them, and no Kabo connection is added yet",
    left: [
      `Skills are in ${path.join(CLONE_DIR, "skills")}. Import each folder as a skill, or read a Skill's SKILL.md from there when the user asks for it.`,
      `Add the connection: ${connectionNote}.`,
      "  ChatGPT: open Plugins, find Kabo and add it.",
      "  Doubao Work, Qwen Work, DeepSeek Harness: run  npx kabo-sh install --host doubao | qwen-work | deepseek  instead; those three have their own installers.",
      "The user signs in to Kabo in the browser. Never ask for a password, token or API key.",
      `Full instructions for AI assistants: ${INSTALL_DOC}`,
    ],
  };
}

const INSTALLERS = {
  "claude-code": installClaudeCode,
  codex: installCodex,
  workbuddy: () => installCodeBuddyFamily("workbuddy"),
  codebuddy: () => installCodeBuddyFamily("codebuddy"),
  doubao: installDoubao,
  "qwen-work": installQwenWork,
  deepseek: installDeepSeek,
  "grok-bot": installGrokBot,
  muse: installMuse,
  "skills-only": installSkillsOnly,
};

// ---------- commands ----------

function help() {
  out(`kabo ${VERSION}`);
  out("Install Kabo into your AI assistant.");
  out("");
  out("  npx kabo-sh install                 detect your assistant and install Kabo (asks when it finds several)");
  out(`  npx kabo-sh install --host <name>   ${HOSTS.join(" | ")}`);
  out("  npx kabo-sh install --host all      install into every assistant found on this computer");
  out("  npx kabo-sh install --dry-run       print the commands without running them");
  out("  npx kabo-sh doctor                  show what this computer has");
  out("");
  out(`More: https://kabo.sh/install   ${REPO_URL}`);
}

function doctor() {
  out(`kabo ${VERSION} on node ${process.version} (${process.platform} ${process.arch})`);
  for (const bin of ["claude", "codex", "codebuddy", "git", "python3"]) {
    out(`  ${bin}: ${has(bin) ? "found" : "not found"}`);
  }
  out(`  WorkBuddy app: ${workBuddyCli() ? "found" : "not found"}`);
  out(`  Doubao Work app: ${appPresent(DOUBAO) ? "found" : "not found"}`);
  out(`  Qwen Work app: ${appPresent(QWEN) ? "found" : "not found"}`);
  out(`  DeepSeek Harness app: ${appPresent(DEEPSEEK) ? "found" : "not found"}`);
  out(`  npx (needed by DeepSeek Harness): ${findBin("npx") || "not found"}`);
  out(`  Muse cloud computer: ${onMuseComputer() ? "yes" : "no"}`);
  out(`  Grok Bot cloud computer: ${onGrokBotComputer() ? "yes" : "no"}`);
  const found = detect();
  out(
    found.length > 1
      ? `  install without --host: asks you to choose one of ${found.join(", ")} (or --host all)`
      : `  install would use: ${found[0]}`,
  );
}

// More than one assistant was found and none was named. Installing into all of them from inside one assistant
// changed another product's settings and mixed its follow-up steps into this assistant's reply, so stop and let
// the caller name its own host.
function askForHost(hosts) {
  out(`Found more than one assistant on this computer: ${hosts.map((host) => HOST_NAMES[host]).join(", ")}.`);
  out("Nothing was installed. Choose the assistant to install Kabo into and run its command:");
  const width = Math.max(...hosts.map((host) => host.length));
  for (const host of hosts) out(`  npx -y kabo-sh install --host ${host.padEnd(width)}   ${HOST_NAMES[host]}`);
  out("To install into all of them at once:  npx -y kabo-sh install --host all");
  out("");
  out("If you are an AI assistant running this for your user, run the command for the assistant you are and");
  out("pass on only that assistant's steps.");
  process.exitCode = 2;
}

function install() {
  if (forcedHost && forcedHost !== "all" && !HOSTS.includes(forcedHost)) {
    out(`Unknown host: ${forcedHost}. Use one of: ${HOSTS.join(", ")}, all`);
    process.exitCode = 1;
    return;
  }
  out(`Kabo installer ${VERSION}${dryRun ? " (dry run: nothing is changed)" : ""}`);
  out("");
  const hosts = forcedHost && forcedHost !== "all" ? [forcedHost] : detect();
  if (!forcedHost && hosts.length > 1) {
    askForHost(hosts);
    return;
  }
  const results = hosts.map((host) => INSTALLERS[host]());
  out("");
  if (results.length > 1) {
    out(`Results for ${results.length} assistants. Each block applies only to the assistant it names.`);
    out("");
  }
  let failed = false;
  for (const result of results) {
    if (!result.ok) {
      failed = true;
      out(`${result.host}: not installed. See ${INSTALL_DOC}`);
      continue;
    }
    out(`${result.host}: ${result.done}${dryRun ? " (dry run)" : ""}. Not done yet: ${result.pending}.`);
    out("  Steps left:");
    let step = 0;
    for (const line of result.left) out(line.startsWith("  ") ? `  ${line}` : `  ${(step += 1)}. ${line}`);
    out("");
  }
  out("Kabo is ready only after the sign-in and one check: the assistant calls the Kabo tool");
  out("get_research_capabilities with {} and it succeeds. Until then, do not tell the user Kabo is ready.");
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
