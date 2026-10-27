#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { crc32 } from "node:zlib";
import { isPackageFile, assertNoHiddenComponents } from "./package-layout.mjs";
import {
  validateIcon,
  validateManifests,
  validateSkills,
  validateRuntime,
  assessSubmission,
} from "./package-standard.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const json = (value) => JSON.stringify(value, null, 2) + "\n";

function relativePath(value) {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9_./-]+$/.test(value) &&
    !value.startsWith("/") &&
    value.split("/").every((part) => part && part !== "." && part !== "..")
  );
}

/** 只读锁定 commit 的 Git blob，不读取工作区、相邻仓源码或执行包里的任何脚本。 */
export function readPackageFiles({ repository = root, commit, packagePath = "." }) {
  if (!/^[a-f0-9]{40}$/.test(commit ?? "") || !(packagePath === "." || relativePath(packagePath)))
    throw new Error("必须提供完整 commit SHA 和仓内相对 package path。");
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: repository,
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
      maxBuffer: 32 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  if (git("cat-file", "-t", commit).toString().trim() !== "commit")
    throw new Error("源版本必须是 commit。");
  const allEntries = git("ls-tree", "-r", "-z", packagePath === "." ? commit : `${commit}:${packagePath}`)
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
  if (packagePath === ".") assertNoHiddenComponents(allEntries.map(entry => entry.slice(entry.indexOf("\t") + 1)));
  const entries = allEntries.filter(entry => packagePath !== "." || isPackageFile(entry.slice(entry.indexOf("\t") + 1)));
  if (!entries.length || entries.length > 2048)
    throw new Error("包必须有 1～2048 个文件。");
  let total = 0;
  const files = entries.map((entry) => {
    const match = /^(100644|100755) blob ([a-f0-9]{40})\t(.+)$/.exec(entry);
    if (!match || !relativePath(match[3]))
      throw new Error("包内只允许普通文件，不能包含链接、子模块或越界路径。");
    const size = Number(git("cat-file", "-s", match[2]).toString().trim());
    total += size;
    if (
      !Number.isSafeInteger(size) ||
      size < 0 ||
      size > 16 * 1024 * 1024 ||
      total > 64 * 1024 * 1024
    )
      throw new Error("包超过本地构建上限：单文件 16 MiB、总计 64 MiB。");
    return {
      name: match[3],
      mode: Number.parseInt(match[1], 8),
      bytes: git("cat-file", "blob", match[2]),
    };
  });
  return files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** 格式与项目安全门，不冒充 OpenAI 后台扫描，也不要求固定数量的 Skills。 */
export function validatePackage(files) {
  const byName = new Map();
  for (const file of files) {
    if (!relativePath(file.name) || byName.has(file.name))
      throw new Error("包文件路径无效或重复。");
    byName.set(file.name, file);
    if (
      /(?:^|\/)(?:hooks|apps|registry|internal|private|\.git)(?:\/|$)|(?:^|\/)(?:\.app\.json|\.env(?:\.[^/]*)?|credentials\.json)$/i.test(
        file.name,
      )
    )
      throw new Error("包含不支持的组件或私有配置文件。");
    const text = file.bytes.toString("utf8");
    if (
      /-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|\bAIza[A-Za-z0-9_-]{30,}|\bBearer\s+eyJ[A-Za-z0-9_.-]+|(?:https?:\/\/)(?:localhost|127\.0\.0\.1|pre\.kabo\.sh)(?:[:/\s"']|$)|\/(?:home|Users)\/[^\s"']+/.test(
        text,
      )
    )
      throw new Error(
        "包内容命中凭据、测试地址或本机路径检查；不输出命中原文。",
      );
    if (file.name.toLowerCase().endsWith(".json")) {
      const inspect = (value) => {
        if (!value || typeof value !== "object") return;
        for (const [key, child] of Object.entries(value)) {
          // 业务 schema 的 hooks 是视频开场字段，不是生命周期配置；仍禁止真实组件和凭据。
          if (
            /^(?:test_credentials|reviewer_instructions|client_secret|access_token|refresh_token|password|api_key|authorization)$/i.test(key) ||
            (/^(?:hooks|apps)$/i.test(key) && !/^skills\/[^/]+\/references\/[^/]+\.schema\.json$/.test(file.name))
          )
            throw new Error(
              "JSON 含不允许入包的组件、Reviewer 资料或凭据字段。",
            );
          inspect(child);
        }
      };
      try {
        inspect(JSON.parse(text));
      } catch (error) {
        if (error instanceof SyntaxError)
          throw new Error("包内 JSON 无效；不输出原文。");
        throw error;
      }
    }
  }
  const parse = (name) => {
    const file = byName.get(name);
    if (!file) throw new Error(`缺少 ${name}。`);
    return JSON.parse(file.bytes.toString("utf8"));
  };
  const manifest = parse("plugin.json");
  if (
    manifest?.$schema !==
      "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json" ||
    typeof manifest.name !== "string" ||
    !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(manifest.name ?? "") ||
    manifest.name.length > 64
  )
    throw new Error("需要 portable plugin.json schema 和有效的包名。");
  const version =
    /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.exec(
      manifest.version ?? "",
    );
  if (
    typeof manifest.version !== "string" ||
    !version ||
    manifest.version.length > 64 ||
    version[4]?.split(".").some((part) => /^0\d+$/.test(part))
  )
    throw new Error("构建必须使用显式 SemVer 版本。");
  const mcp = parse("mcp.json");
  const servers = Object.values(mcp?.mcpServers ?? {});
  if (
    mcp?.$schema !==
      "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json" ||
    !mcp.mcpServers ||
    typeof mcp.mcpServers !== "object" ||
    Array.isArray(mcp.mcpServers) ||
    servers.length !== 1 ||
    servers[0]?.type !== "streamable-http" ||
    !["https://kabo.sh/mcp", "https://kabo.sh/mcp-pub"].includes(servers[0]?.url) ||
    Object.keys(servers[0]).some(
      (key) => !["type", "url"].includes(key),
    )
  )
    throw new Error("本构建入口只接受一个无凭据的 Kabo 生产 MCP 配置。");
  validateManifests(manifest, mcp, parse("host-auth.json"));
  const openai = manifest.extensions?.["com.openai"];
  const listing = openai?.interface;
  for (const [key, limit] of Object.entries({
    displayName: 30,
    shortDescription: 30,
    longDescription: 4000,
    developerName: 80,
    category: 120,
  })) {
    const value = listing?.[key];
    if (typeof value !== "string" || !value.trim() || [...value].length > limit)
      throw new Error(`目录字段 ${key} 缺失或超过限制。`);
  }
  for (const key of [
    "websiteURL",
    "supportURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
  ]) {
    try {
      const url = new URL(listing[key]);
      if (
        url.origin !== "https://kabo.sh" ||
        url.username ||
        url.password ||
        url.search ||
        url.hash ||
        listing[key].length > 1024
      )
        throw new Error();
    } catch {
      throw new Error(`目录字段 ${key} 必须是 Kabo 生产 HTTPS 页面。`);
    }
  }
  for (const key of ["logo", "composerIcon", "logoDark", "composerIconDark"]) {
    const value = listing[key];
    if (value === undefined && ["logoDark", "composerIconDark"].includes(key))
      continue;
    if (
      typeof value !== "string" ||
      !value.startsWith("./assets/") ||
      !byName.has(value.slice(2))
    )
      throw new Error(`图标 ${key} 必须引用包内 assets 文件。`);
    validateIcon(byName.get(value.slice(2)).bytes);
  }
  if (
    listing.capabilities !== undefined &&
    (!Array.isArray(listing.capabilities) ||
      listing.capabilities.length > 20 ||
      listing.capabilities.some(
        (item) =>
          typeof item !== "string" || !item.trim() || [...item].length > 120,
      ))
  )
    throw new Error(
      "capabilities 必须是不超过 20 个、每个不超过 120 字符的能力说明。",
    );
  if (listing.defaultPrompt !== undefined) {
    const prompts =
      typeof listing.defaultPrompt === "string"
        ? [listing.defaultPrompt]
        : listing.defaultPrompt;
    if (
      !Array.isArray(prompts) ||
      prompts.length > 3 ||
      new Set(prompts).size !== prompts.length ||
      prompts.some(
        (item) =>
          typeof item !== "string" ||
          !item.trim() ||
          [...item].length > 128 ||
          item.includes("@"),
      )
    )
      throw new Error(
        "defaultPrompt 最多 3 条，必须唯一、不含 @mention 且每条不超过 128 字符。",
      );
  }
  if (
    openai.onboardingSkill &&
    (!openai.onboardingSkill.startsWith("./skills/") ||
      !openai.onboardingSkill.endsWith("/SKILL.md") ||
      !byName.has(openai.onboardingSkill.slice(2)))
  )
    throw new Error("onboardingSkill 必须指向实际入包的 Skill。");
  validateSkills(byName, servers[0].url);
  validateRuntime(byName, mcp);
  return { name: manifest.name, version: manifest.version };
}

/** ZIP STORE + 固定 1980-01-01 时间和 Unix 模式，避免压缩库或 checkout mtime 改变摘要。 */
export function deterministicZip(files) {
  const local = [],
    central = [];
  let offset = 0;
  for (const file of [...files].sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  )) {
    const name = Buffer.from(file.name);
    const checksum = crc32(file.bytes);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50, 0);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x800, 6);
    header.writeUInt16LE(33, 12);
    header.writeUInt32LE(checksum, 14);
    header.writeUInt32LE(file.bytes.length, 18);
    header.writeUInt32LE(file.bytes.length, 22);
    header.writeUInt16LE(name.length, 26);
    local.push(header, name, file.bytes);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50, 0);
    record.writeUInt16LE(0x0314, 4);
    record.writeUInt16LE(20, 6);
    record.writeUInt16LE(0x800, 8);
    record.writeUInt16LE(33, 14);
    record.writeUInt32LE(checksum, 16);
    record.writeUInt32LE(file.bytes.length, 20);
    record.writeUInt32LE(file.bytes.length, 24);
    record.writeUInt16LE(name.length, 28);
    record.writeUInt32LE(((file.mode ?? 0o100644) << 16) >>> 0, 38);
    record.writeUInt32LE(offset, 42);
    central.push(record, name);
    offset += header.length + name.length + file.bytes.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, directory, end]);
}

async function main() {
  const { values } = parseArgs({
    options: {
      commit: { type: "string" },
      "package-path": { type: "string" },
      output: { type: "string" },
      submission: { type: "boolean", default: false },
      evidence: { type: "string" },
    },
  });
  if (!values.output)
    throw new Error(
      "需要 --commit <完整 SHA> --package-path <仓内目录> --output <新目录>。",
    );
  const files = readPackageFiles({
    commit: values.commit,
    packagePath: values["package-path"],
  });
  const identity = validatePackage(files);
  const bytes = deterministicZip(files);
  const readiness = assessSubmission(files, {
    evidencePath: values.evidence, commit: values.commit,
    version: identity.version, zipSha256: hash(bytes),
  });
  if (values.submission && !readiness.submissionReady) {
    console.error(JSON.stringify(readiness, null, 2));
    throw new Error("同一插件的提交门尚未通过。");
  }
  const name = `${identity.name}-${identity.version}.zip`;
  const output = path.resolve(values.output);
  // 新目录拒绝覆盖旧交付；重复构建请另选目录再比较 SHA-256。
  await mkdir(path.dirname(output), { recursive: true });
  await mkdir(output);
  await writeFile(path.join(output, name), bytes, { flag: "wx" });
  const sha256 = hash(bytes);
  await writeFile(path.join(output, `${name}.sha256`), `${sha256}  ${name}\n`, {
    flag: "wx",
  });
  await writeFile(
    path.join(output, "manifest.json"),
    json({
      format: "kabo.openai-package.v1",
      ...identity,
      commit: values.commit,
      packagePath: values["package-path"],
      filename: name,
      sha256,
      submissionReady: readiness.submissionReady,
      submissionBlockers: readiness.blockers,
      acceptanceEvidence: readiness.acceptanceEvidence,
      validation: "portable-schema-and-local-policy",
      files: files.map((file) => ({
        path: file.name,
        mode: file.mode,
        bytes: file.bytes.length,
        sha256: hash(file.bytes),
      })),
    }),
    { flag: "wx" },
  );
  console.log(`${name}: SHA-256 ${sha256}; submissionReady=${readiness.submissionReady}`);
}

if (
  process.argv[1] &&
  realpathSync(fileURLToPath(import.meta.url)) === realpathSync(process.argv[1])
) {
  main().catch(() => {
    console.error(
      "插件包构建失败。检查锁定版本、包内容与输出目录；不输出包正文或凭据。",
    );
    process.exitCode = 1;
  });
}
