#!/usr/bin/env node
// Kabo Skills spec validation, with rule numbers matching docs/skills-spec.md one to one.
// Reads only this repo's working tree: the spec governs only the plugin's skills/, and does not read
//   creator-skills or the registry.
import { readFileSync, readdirSync, lstatSync, realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { parseDocument } from "yaml";

const root = fileURLToPath(new URL("..", import.meta.url));
const decoder = new TextDecoder("utf-8", { fatal: true });

// Consistent with skills-ref 0.1.1 (agentskills validate); no Python dependency, CI needs only Node.
const allowedFields = new Set(["name", "description", "license", "compatibility", "metadata", "allowed-tools"]);
// An allowlist rather than a denylist: "no commercial use" would not catch AGPL (which allows commercial use
//   but has network copyleft terms).
export const licenseAllowlist = new Set(["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "CC0-1.0", "CC-BY-4.0"]);
// Characters rather than tokens: tokenizers differ by model, so measuring in tokens would itself bind to a
//   model (principle 1).
const maxLines = 500;
const maxBodyChars = 21_000;
const maxChars = 20_000;
const descriptionWarnChars = 500;
const hostPrivate = [
  [/kabo-run-pipeline/, "kabo-run-pipeline"],
  [/\bCLAUDE_PLUGIN_ROOT\b|\bPLUGIN_ROOT\b/, "PLUGIN_ROOT"],
  [/\bmcp__[A-Za-z0-9_-]+/, "host-namespaced tool name mcp__*"],
];
// Host session records and internal state: the host deliberately hides CODEX_HOME from the command surface,
//   and scripts must not bypass that.
const hostState = /\bCODEX_HOME\b|\.codex\/(?:sessions|state)|rollout-[^"'\s]*\.jsonl|\.claude\/projects|@kabo\/desktop|skill-cache/;
const networkUse = /^\s*(?:import|from)\s+(?:urllib\.request|requests|httpx|aiohttp|http\.client|socket)\b|\burlopen\(|\b(?:curl|wget)\b/m;
const installUse = /\b(?:pip3?|npm|pnpm|apt-get|apt|brew)\s+install\b/;
// A license file passes only if it can be recognized as an allowlisted license; unrecognized ones go to a
//   human and are not allowed by default.
const allowedLicenseText = /\bMIT License\b|Permission is hereby granted, free of charge|Apache License,? Version 2\.0|Redistribution and use in source and binary forms|ISC License|CC0 1\.0|Creative Commons Attribution 4\.0/i;
const restrictiveLicense = /\b(?:A|L)?GPL(?:-?v?\d)?\b|GNU (?:Affero |Lesser )?General Public License|NonCommercial|\bCC[ -]BY(?:-SA)?-NC\b/i;
// Decide text by content, not by extension: description files such as .rst are read by the model too.
const textFile = bytes => !bytes.includes(0) && decode(bytes) !== null;
// Tool names inside structured data (contracts, samples) do not count as dependencies; tool dependencies are counted only from descriptive text.
const dataFile = name => /\.(?:json|jsonl|ya?ml|csv|toml)$/i.test(name);
const spdxIds = expression => {
  const ids = [];
  const tokens = expression.split(/[\s()]+/).filter(Boolean);
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i] === "AND" || tokens[i] === "OR") continue;
    if (tokens[i] === "WITH") { i++; continue; }
    ids.push(tokens[i].replace(/\+$/, ""));
  }
  return ids;
};

function walk(dir, prefix = "") {
  const out = new Map();
  for (const entry of readdirSync(dir).sort()) {
    const full = path.join(dir, entry);
    const name = prefix ? `${prefix}/${entry}` : entry;
    const info = lstatSync(full);
    if (info.isDirectory()) for (const [k, v] of walk(full, name)) out.set(k, v);
    else if (info.isFile()) out.set(name, readFileSync(full));
  }
  return out;
}

function decode(bytes) {
  try { return decoder.decode(bytes); } catch { return null; }
}

/** Validate one skill directory. Keys of files are posix paths relative to the skill root. */
export function lintSkill(id, files, { toolNames, skillIds, toolScopes = new Map() }) {
  const findings = [];
  const add = (rule, level, file, message) => findings.push({ rule, level, file, message });
  const entry = files.get("SKILL.md");
  if (!entry) {
    add("KS1.1", "error", "SKILL.md", "Missing SKILL.md.");
    return findings;
  }
  const text = decode(entry) ?? "";
  const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
  let meta = {};
  let parsed = false;
  if (!front) add("KS1.1", "error", "SKILL.md", "Missing YAML frontmatter.");
  else {
    const doc = parseDocument(front[1], { uniqueKeys: true });
    if (doc.errors.length) add("KS1.1", "error", "SKILL.md", `frontmatter is not valid YAML: ${doc.errors[0].message.split("\n")[0]}`);
    else {
      const value = doc.toJS();
      if (value === null || typeof value !== "object" || Array.isArray(value)) add("KS1.1", "error", "SKILL.md", "frontmatter must be a YAML mapping.");
      else {
        meta = value;
        parsed = true;
      }
    }
  }
  const body = front ? text.slice(front[0].length) : text;

  // KS1: matches the open spec. When frontmatter parsing fails, report only that one error to avoid a cascade of missing-field errors.
  if (parsed) {
    const extra = Object.keys(meta).filter(key => !allowedFields.has(key));
    if (extra.length) add("KS1.3", "error", "SKILL.md", `frontmatter has fields outside the spec: ${extra.join(", ")}.`);
    const name = typeof meta.name === "string" ? meta.name.normalize("NFKC").trim() : "";
    if (!name || name.length > 64 || name !== name.toLowerCase() || /^-|-$|--/.test(name) || !/^[\p{L}\p{N}-]+$/u.test(name) || name !== id)
      add("KS1.1", "error", "SKILL.md", `name must be at most 64 characters of lowercase letters, digits, and hyphens, and match the directory name ${id}.`);
    const description = typeof meta.description === "string" ? meta.description : "";
    if (!description.trim()) add("KS1.2", "error", "SKILL.md", "description must not be empty.");
    else if (description.length > 1024) add("KS1.2", "error", "SKILL.md", `description is ${description.length} characters, over 1024.`);
    else if (description.length > descriptionWarnChars) add("KS1.2", "warn", "SKILL.md", `description is ${description.length} characters, over ${descriptionWarnChars}; it is shortened first when the Codex list budget runs short.`);
    if ("compatibility" in meta && (typeof meta.compatibility !== "string" || meta.compatibility.length > 500))
      add("KS1.4", "error", "SKILL.md", "compatibility must be a string of at most 500 characters.");
    if ("metadata" in meta && (meta.metadata === null || typeof meta.metadata !== "object" || Array.isArray(meta.metadata) || Object.values(meta.metadata).some(v => typeof v !== "string")))
      add("KS1.4", "error", "SKILL.md", "metadata must be a string-to-string mapping.");
  }

  // KS2: the only runtime dependencies are /mcp-pub tools
  const readable = [...files].filter(([file, bytes]) => file === "SKILL.md" || (file.startsWith("references/") && textFile(bytes))).map(([file, bytes]) => [file, decode(bytes) ?? ""]);
  // A contract such as mcp-bindings.json lists every tool, so it cannot count as a dependency.
  const instructions = readable.filter(([file]) => !dataFile(file));
  for (const [file, content] of readable)
    for (const [pattern, label] of hostPrivate)
      if (pattern.test(content)) add("KS2.1", "error", file, `Host-private runtime found: ${label}.`);
  let declared = new Set();
  if ("allowed-tools" in meta) {
    if (typeof meta["allowed-tools"] !== "string") add("KS2.2", "error", "SKILL.md", "allowed-tools must be a space-separated string.");
    else declared = new Set(meta["allowed-tools"].split(/\s+/).filter(Boolean));
    for (const tool of declared) {
      if (!toolNames.has(tool)) add("KS2.2", "error", "SKILL.md", `${tool} in allowed-tools is not in the /mcp-pub tool list.`);
    }
  }
  const used = new Set();
  for (const [, content] of instructions)
    for (const tool of toolNames) if (new RegExp(`\\b${tool}\\b`).test(content)) used.add(tool);
  const undeclared = [...used].filter(tool => !declared.has(tool)).sort();
  if (undeclared.length) add("KS2.2", "error", "SKILL.md", `Tools used in the body but not declared in allowed-tools: ${undeclared.join(", ")}.`);
  const hasScripts = [...files.keys()].some(file => file.startsWith("scripts/"));
  if (hasScripts && !meta.compatibility) add("KS2.3", "warn", "SKILL.md", "Has scripts/ but compatibility does not declare the runtime prerequisites (e.g. Python 3 and file read/write).");
  // Kabo permissions are inferred from the tools in allowed-tools: the host grants a connection, not a skill, so this is the only place a user can see which permission each skill needs.
  const compatibility = typeof meta.compatibility === "string" ? meta.compatibility : "";
  const permissionText = [...compatibility.matchAll(/Kabo permissions?\b[^.]*\./g)].map(match => match[0]).join(" ");
  const scopes = [...new Set([...declared].flatMap(tool => toolScopes.get(tool) ?? []))].sort();
  const unlisted = scopes.filter(scope => !new RegExp(`(?:^|[\\s,;:])${scope}(?=[\\s,;.]|$)`).test(permissionText));
  if (unlisted.length) add("KS2.3", "warn", "SKILL.md", `compatibility does not state the permissions required by allowed-tools using "Kabo permission: ...": ${unlisted.join(", ")}.`);
  const fetches = [...files].some(([file, bytes]) => file.startsWith("scripts/") && textFile(bytes) && networkUse.test(decode(bytes) ?? ""));
  if (fetches && !compatibility.includes("storage.googleapis.com"))
    add("KS2.3", "warn", "SKILL.md", "scripts/ download over the network, but compatibility does not state that access to storage.googleapis.com is required.");
  if (/[\u3400-\u9fff]/.test(body)) add("KS2.5", "warn", "SKILL.md", "Body contains Chinese characters; skill content must be English.");

  // KS3: length
  const measure = (file, content) => {
    const lines = content.split("\n").length;
    const limit = file === "SKILL.md" ? maxBodyChars : maxChars;
    if (lines > maxLines || content.length > limit)
      add(file === "SKILL.md" ? "KS3.1" : "KS3.2", "error", file, `${lines} lines, ${content.length} characters; limit is ${maxLines} lines, ${limit} characters; ${file === "SKILL.md" ? "move the excess to references/" : "split into small files that can be read on demand"}.`);
  };
  measure("SKILL.md", body);
  for (const [file, bytes] of files)
    if (file.startsWith("references/") && textFile(bytes) && !file.endsWith(".schema.json")) measure(file, decode(bytes) ?? "");

  // KS4: no nesting
  for (const file of files.keys())
    if (file !== "SKILL.md" && path.posix.basename(file) === "SKILL.md") add("KS4.1", "error", file, "Skill contains a nested SKILL.md.");
  const others = [...skillIds].filter(other => other !== id);
  for (const [file, bytes] of files) {
    if (!textFile(bytes)) continue;
    const content = decode(bytes) ?? "";
    for (const other of others) {
      const pathRef = new RegExp(`(?:skills/|\\.\\./)${other}/|\\b${other}/(?:scripts|references|assets|SKILL\\.md)`);
      if (pathRef.test(content)) add("KS4.2", "error", file, `Reads or calls another skill: ${other}.`);
      // Shared scripts branch on the skill name (e.g. to pick a per-platform value), so the literal alone does not imply nesting; leave it to manual judgment.
      else if (file.startsWith("scripts/") && new RegExp(`["']${other}["']`).test(content))
        add("KS4.2", "audit", file, `Script mentions another skill's name ${other}; confirm it does not read or call it.`);
    }
  }

  // KS5: license
  if ("license" in meta && !licenseAllowlist.has(meta.license)) add("KS5.1", "error", "SKILL.md", `license ${meta.license} is not in the allowlist.`);
  for (const [file, bytes] of files) {
    if (!textFile(bytes)) continue;
    const content = decode(bytes) ?? "";
    const base = path.posix.basename(file).toUpperCase();
    const licenseFile = /^(?:LICENSE|LICENCE|COPYING|NOTICE)/.test(base);
    const spdx = [...content.matchAll(/SPDX-License-Identifier:[ \t]*([^\r\n*]+)/g)].flatMap(match => spdxIds(match[1].replace(/-->\s*$/, "")));
    if ((licenseFile && restrictiveLicense.test(content)) || spdx.some(id => !licenseAllowlist.has(id)))
      add("KS5.2", "error", file, "Contains license content outside the allowlist (GPL/AGPL/LGPL/NC, etc.).");
    else if (licenseFile && !allowedLicenseText.test(content))
      add("KS5.2", "audit", file, "Not recognized as an allowlisted license; manually confirm the source and license.");
  }

  // KS6: non-standard files
  if (files.has("manifest.json")) add("KS6.1", "error", "manifest.json", "manifest.json is not part of the open spec; move its content to frontmatter per the spec, then delete it.");
  if (files.has("references/mcp-bindings.json")) add("KS6.2", "error", "references/mcp-bindings.json", "The logical connector mapping is replaced by allowed-tools and direct calls to /mcp-pub tool names.");
  for (const file of files.keys())
    if (file.startsWith("agents/")) add("KS6.3", "error", file, "agents/ directory is not allowed; implicit invocation is on by default and MCP is declared by the plugin's mcp.json.");

  // KS7: scripts
  for (const [file, bytes] of files) {
    if (!/\.(?:py|sh|js|mjs)$/.test(file)) continue;
    const content = decode(bytes) ?? "";
    if (hostState.test(content)) add("KS7.1", "error", file, "Reads host session records or internal state.");
    if (!file.startsWith("scripts/")) add("KS7.4", "audit", file, "Executable script is not under scripts/.");
    if (networkUse.test(content) || (/\.m?js$/.test(file) && /\bfetch\(/.test(content))) add("KS7.3", "audit", file, "Has network access; confirm it only reaches Kabo domains or the storage.googleapis.com signed download links given by Kabo tool results (GET only, exact host match, no redirects followed).");
    if (installUse.test(content)) add("KS7.2", "audit", file, "Contains an install command; confirm it is only prompt text and nothing is installed at runtime.");
  }
  return findings;
}

export function lintSkills({ directory = root, only } = {}) {
  const tools = JSON.parse(readFileSync(path.join(directory, "contracts/directory-mcp/tools-list.json"), "utf8")).tools;
  const toolNames = new Set(tools.map(tool => tool.name));
  const toolScopes = new Map(tools.map(tool => [tool.name, (tool.securitySchemes ?? []).flatMap(scheme => scheme.scopes ?? [])]));
  const enforced = new Set(JSON.parse(readFileSync(path.join(directory, "skills-spec.json"), "utf8")).enforced);
  const skillIds = new Set(readdirSync(path.join(directory, "skills")).filter(name => lstatSync(path.join(directory, "skills", name)).isDirectory()));
  for (const id of enforced) if (!skillIds.has(id)) throw new Error(`skills-spec.json enables a nonexistent Skill: ${id}`);
  const results = [];
  for (const id of [...skillIds].sort()) {
    if (only && id !== only) continue;
    const findings = lintSkill(id, walk(path.join(directory, "skills", id)), { toolNames, skillIds, toolScopes });
    results.push({ id, enforced: enforced.has(id), findings });
  }
  return results;
}

function count(findings, level) {
  return findings.filter(finding => finding.level === level).length;
}

if (process.argv[1] && realpathSync(fileURLToPath(import.meta.url)) === realpathSync(process.argv[1])) {
  const { values } = parseArgs({ options: { skill: { type: "string" }, strict: { type: "boolean" }, json: { type: "boolean" }, summary: { type: "boolean" } } });
  const results = lintSkills({ only: values.skill });
  if (values.skill && !results.length) throw new Error(`No such Skill: ${values.skill}`);
  // The gate is enabled per skill: skills not yet enabled are only reported, so existing ones do not block verify.
  const blocking = results.filter(result => (values.strict || result.enforced) && count(result.findings, "error"));
  if (values.json) console.log(JSON.stringify(results, null, 2));
  else
    for (const { id, enforced, findings } of results) {
      const mode = enforced ? "gated" : "gate not enabled";
      console.log(`${id} (${mode}): errors ${count(findings, "error")}, warnings ${count(findings, "warn")}, audits ${count(findings, "audit")}`);
      if (values.summary && !enforced) continue;
      for (const finding of findings) console.log(`  ${finding.level} ${finding.rule} ${finding.file}: ${finding.message}`);
    }
  if (blocking.length) {
    console.error(`Skills spec gate failed: ${blocking.map(result => result.id).join(", ")}`);
    process.exitCode = 1;
  }
}
