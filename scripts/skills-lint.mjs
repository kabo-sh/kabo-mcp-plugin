#!/usr/bin/env node
// Kabo Skills 规范校验，规则编号与 docs/skills-spec.md 一一对应。
// 只读本仓工作区：规范只管插件 skills/，不读 creator-skills 或 registry。
import { readFileSync, readdirSync, lstatSync, realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { parseDocument } from "yaml";

const root = fileURLToPath(new URL("..", import.meta.url));
const decoder = new TextDecoder("utf-8", { fatal: true });

// 与 skills-ref 0.1.1（agentskills validate）一致；不依赖 Python，CI 只需 Node。
const allowedFields = new Set(["name", "description", "license", "compatibility", "metadata", "allowed-tools"]);
// 白名单而非黑名单：「禁止商业用途」拦不住 AGPL（允许商用但有网络传染条款）。
export const licenseAllowlist = new Set(["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "CC0-1.0", "CC-BY-4.0"]);
// 字符而非 token：分词器因模型而异，用 token 计量本身就绑定了模型（原则 1）。
const maxLines = 500;
const maxChars = 20_000;
const descriptionWarnChars = 500;
const hostPrivate = [
  [/kabo-run-pipeline/, "kabo-run-pipeline"],
  [/\bCLAUDE_PLUGIN_ROOT\b|\bPLUGIN_ROOT\b/, "PLUGIN_ROOT"],
  [/\bmcp__[A-Za-z0-9_-]+/, "宿主命名空间工具名 mcp__*"],
];
// 宿主会话记录与内部状态：宿主刻意对命令面隐藏 CODEX_HOME，脚本不得绕过。
const hostState = /\bCODEX_HOME\b|\.codex\/(?:sessions|state)|rollout-[^"'\s]*\.jsonl|\.claude\/projects|@kabo\/desktop|skill-cache/;
const networkUse = /^\s*(?:import|from)\s+(?:urllib\.request|requests|httpx|aiohttp|http\.client|socket)\b|\burlopen\(|\b(?:curl|wget)\b/m;
const installUse = /\b(?:pip3?|npm|pnpm|apt-get|apt|brew)\s+install\b/;
// 许可证文件能认出是白名单许可证才算通过；认不出的交给人工，不默认放行。
const allowedLicenseText = /\bMIT License\b|Permission is hereby granted, free of charge|Apache License,? Version 2\.0|Redistribution and use in source and binary forms|ISC License|CC0 1\.0|Creative Commons Attribution 4\.0/i;
const restrictiveLicense = /\b(?:A|L)?GPL(?:-?v?\d)?\b|GNU (?:Affero |Lesser )?General Public License|NonCommercial|\bCC[ -]BY(?:-SA)?-NC\b/i;
// 按内容判定文本，不按扩展名：.rst 之类的说明文件同样会被模型读到。
const textFile = bytes => !bytes.includes(0) && decode(bytes) !== null;
// 结构化数据（契约、样本）里的工具名不代表依赖，工具依赖只从说明性文本统计。
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

/** 校验一个 skill 目录。files 的键是相对 skill 根的 posix 路径。 */
export function lintSkill(id, files, { toolNames, skillIds }) {
  const findings = [];
  const add = (rule, level, file, message) => findings.push({ rule, level, file, message });
  const entry = files.get("SKILL.md");
  if (!entry) {
    add("KS1.1", "error", "SKILL.md", "缺少 SKILL.md。");
    return findings;
  }
  const text = decode(entry) ?? "";
  const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
  let meta = {};
  let parsed = false;
  if (!front) add("KS1.1", "error", "SKILL.md", "缺少 YAML frontmatter。");
  else {
    const doc = parseDocument(front[1], { uniqueKeys: true });
    if (doc.errors.length) add("KS1.1", "error", "SKILL.md", `frontmatter 不是合法 YAML：${doc.errors[0].message.split("\n")[0]}`);
    else {
      const value = doc.toJS();
      if (value === null || typeof value !== "object" || Array.isArray(value)) add("KS1.1", "error", "SKILL.md", "frontmatter 必须是 YAML 映射。");
      else {
        meta = value;
        parsed = true;
      }
    }
  }
  const body = front ? text.slice(front[0].length) : text;

  // KS1：与开放规范一致。frontmatter 解析失败时只报那一条，避免连带出一串字段缺失。
  if (parsed) {
    const extra = Object.keys(meta).filter(key => !allowedFields.has(key));
    if (extra.length) add("KS1.3", "error", "SKILL.md", `frontmatter 含规范外字段：${extra.join(", ")}。`);
    const name = typeof meta.name === "string" ? meta.name.normalize("NFKC").trim() : "";
    if (!name || name.length > 64 || name !== name.toLowerCase() || /^-|-$|--/.test(name) || !/^[\p{L}\p{N}-]+$/u.test(name) || name !== id)
      add("KS1.1", "error", "SKILL.md", `name 必须是不超过 64 字符的小写字母、数字、连字符，且与目录名 ${id} 一致。`);
    const description = typeof meta.description === "string" ? meta.description : "";
    if (!description.trim()) add("KS1.2", "error", "SKILL.md", "description 不能为空。");
    else if (description.length > 1024) add("KS1.2", "error", "SKILL.md", `description ${description.length} 字符，超过 1024。`);
    else if (description.length > descriptionWarnChars) add("KS1.2", "warn", "SKILL.md", `description ${description.length} 字符，超过 ${descriptionWarnChars}，Codex 列表预算不足时会先被缩短。`);
    if ("compatibility" in meta && (typeof meta.compatibility !== "string" || meta.compatibility.length > 500))
      add("KS1.4", "error", "SKILL.md", "compatibility 必须是不超过 500 字符的字符串。");
    if ("metadata" in meta && (meta.metadata === null || typeof meta.metadata !== "object" || Array.isArray(meta.metadata) || Object.values(meta.metadata).some(v => typeof v !== "string")))
      add("KS1.4", "error", "SKILL.md", "metadata 必须是字符串到字符串的映射。");
  }

  // KS2：运行依赖只有 /mcp-pub 工具
  const readable = [...files].filter(([file, bytes]) => file === "SKILL.md" || (file.startsWith("references/") && textFile(bytes))).map(([file, bytes]) => [file, decode(bytes) ?? ""]);
  // mcp-bindings.json 这类契约会列出全部工具，不能算作依赖。
  const instructions = readable.filter(([file]) => !dataFile(file));
  for (const [file, content] of readable)
    for (const [pattern, label] of hostPrivate)
      if (pattern.test(content)) add("KS2.1", "error", file, `出现宿主私有运行时：${label}。`);
  let declared = new Set();
  if ("allowed-tools" in meta) {
    if (typeof meta["allowed-tools"] !== "string") add("KS2.2", "error", "SKILL.md", "allowed-tools 必须是空格分隔的字符串。");
    else declared = new Set(meta["allowed-tools"].split(/\s+/).filter(Boolean));
    for (const tool of declared) {
      if (!toolNames.has(tool)) add("KS2.2", "error", "SKILL.md", `allowed-tools 中的 ${tool} 不在 /mcp-pub 工具清单中。`);
    }
  }
  const used = new Set();
  for (const [, content] of instructions)
    for (const tool of toolNames) if (new RegExp(`\\b${tool}\\b`).test(content)) used.add(tool);
  const undeclared = [...used].filter(tool => !declared.has(tool)).sort();
  if (undeclared.length) add("KS2.2", "error", "SKILL.md", `正文用到但未在 allowed-tools 声明的工具：${undeclared.join(", ")}。`);
  const hasScripts = [...files.keys()].some(file => file.startsWith("scripts/"));
  if (hasScripts && !meta.compatibility) add("KS2.3", "warn", "SKILL.md", "带 scripts/ 但未在 compatibility 声明运行前提（如 Python 3 与文件读写）。");
  if (/[㐀-鿿]/.test(body)) add("KS2.5", "warn", "SKILL.md", "正文含中文字符；skill 内容一律英文。");

  // KS3：长度
  const measure = (file, content) => {
    const lines = content.split("\n").length;
    if (lines > maxLines || content.length > maxChars)
      add(file === "SKILL.md" ? "KS3.1" : "KS3.2", "error", file, `${lines} 行、${content.length} 字符，上限 ${maxLines} 行、${maxChars} 字符；${file === "SKILL.md" ? "超出部分移到 references/" : "拆成可按需读取的小文件"}。`);
  };
  measure("SKILL.md", body);
  for (const [file, bytes] of files)
    if (file.startsWith("references/") && textFile(bytes) && !file.endsWith(".schema.json")) measure(file, decode(bytes) ?? "");

  // KS4：不嵌套
  for (const file of files.keys())
    if (file !== "SKILL.md" && path.posix.basename(file) === "SKILL.md") add("KS4.1", "error", file, "skill 内含嵌套的 SKILL.md。");
  const others = [...skillIds].filter(other => other !== id);
  for (const [file, bytes] of files) {
    if (!textFile(bytes)) continue;
    const content = decode(bytes) ?? "";
    for (const other of others) {
      const pathRef = new RegExp(`(?:skills/|\\.\\./)${other}/|\\b${other}/(?:scripts|references|assets|SKILL\\.md)`);
      if (pathRef.test(content)) add("KS4.2", "error", file, `读取或调用另一个 skill：${other}。`);
      // 共享脚本会按 skill 名分支（如按平台取值），字面量本身不等于嵌套，交给人工判断。
      else if (file.startsWith("scripts/") && new RegExp(`["']${other}["']`).test(content))
        add("KS4.2", "audit", file, `脚本出现另一个 skill 的名称 ${other}，确认没有读取或调用它。`);
    }
  }

  // KS5：许可证
  if ("license" in meta && !licenseAllowlist.has(meta.license)) add("KS5.1", "error", "SKILL.md", `license ${meta.license} 不在白名单中。`);
  for (const [file, bytes] of files) {
    if (!textFile(bytes)) continue;
    const content = decode(bytes) ?? "";
    const base = path.posix.basename(file).toUpperCase();
    const licenseFile = /^(?:LICENSE|LICENCE|COPYING|NOTICE)/.test(base);
    const spdx = [...content.matchAll(/SPDX-License-Identifier:[ \t]*([^\r\n*]+)/g)].flatMap(match => spdxIds(match[1].replace(/-->\s*$/, "")));
    if ((licenseFile && restrictiveLicense.test(content)) || spdx.some(id => !licenseAllowlist.has(id)))
      add("KS5.2", "error", file, "含白名单之外的许可证内容（GPL/AGPL/LGPL/NC 等）。");
    else if (licenseFile && !allowedLicenseText.test(content))
      add("KS5.2", "audit", file, "认不出是白名单内的许可证，人工确认来源与许可证。");
  }

  // KS6：非标准文件
  if (files.has("manifest.json")) add("KS6.1", "error", "manifest.json", "manifest.json 不是开放规范的一部分，内容按规范迁到 frontmatter 后删除。");
  if (files.has("references/mcp-bindings.json")) add("KS6.2", "error", "references/mcp-bindings.json", "逻辑 connector 映射由 allowed-tools 与直接调用 /mcp-pub 工具名取代。");
  for (const file of files.keys())
    if (file.startsWith("agents/")) add("KS6.3", "error", file, "不得有 agents/ 目录；隐式调用默认开启，MCP 由插件 mcp.json 声明。");

  // KS7：脚本
  for (const [file, bytes] of files) {
    if (!/\.(?:py|sh|js|mjs)$/.test(file)) continue;
    const content = decode(bytes) ?? "";
    if (hostState.test(content)) add("KS7.1", "error", file, "读取宿主会话记录或内部状态。");
    if (!file.startsWith("scripts/")) add("KS7.4", "audit", file, "可执行脚本不在 scripts/ 下。");
    if (networkUse.test(content) || (/\.m?js$/.test(file) && /\bfetch\(/.test(content))) add("KS7.3", "audit", file, "有网络访问，确认只访问 Kabo 域名，或 Kabo 工具结果给出的 storage.googleapis.com 签名下载链接（只 GET、主机精确匹配、不跟随重定向）。");
    if (installUse.test(content)) add("KS7.2", "audit", file, "出现安装命令，确认只是提示文字，运行时不安装软件。");
  }
  return findings;
}

export function lintSkills({ directory = root, only } = {}) {
  const tools = JSON.parse(readFileSync(path.join(directory, "contracts/directory-mcp/tools-list.json"), "utf8")).tools;
  const toolNames = new Set(tools.map(tool => tool.name));
  const enforced = new Set(JSON.parse(readFileSync(path.join(directory, "skills-spec.json"), "utf8")).enforced);
  const skillIds = new Set(readdirSync(path.join(directory, "skills")).filter(name => lstatSync(path.join(directory, "skills", name)).isDirectory()));
  for (const id of enforced) if (!skillIds.has(id)) throw new Error(`skills-spec.json 启用了不存在的 Skill：${id}`);
  const results = [];
  for (const id of [...skillIds].sort()) {
    if (only && id !== only) continue;
    const findings = lintSkill(id, walk(path.join(directory, "skills", id)), { toolNames, skillIds });
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
  if (values.skill && !results.length) throw new Error(`没有这个 Skill：${values.skill}`);
  // 门禁逐个 skill 开启：未启用的只报告，不让存量阻塞 verify。
  const blocking = results.filter(result => (values.strict || result.enforced) && count(result.findings, "error"));
  if (values.json) console.log(JSON.stringify(results, null, 2));
  else
    for (const { id, enforced, findings } of results) {
      const mode = enforced ? "门禁" : "未启用门禁";
      console.log(`${id}（${mode}）：错误 ${count(findings, "error")}，警告 ${count(findings, "warn")}，审计 ${count(findings, "audit")}`);
      if (values.summary && !enforced) continue;
      for (const finding of findings) console.log(`  ${finding.level} ${finding.rule} ${finding.file}：${finding.message}`);
    }
  if (blocking.length) {
    console.error(`Skills 规范门禁未通过：${blocking.map(result => result.id).join(", ")}`);
    process.exitCode = 1;
  }
}
