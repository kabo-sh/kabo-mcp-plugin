import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { crc32, inflateSync } from "node:zlib";
import Ajv2020 from "ajv/dist/2020.js";
import { parseDocument } from "yaml";
import { validateStaticSkills } from "./static-skills.mjs";
import { assessAcceptance } from "./submission-evidence.mjs";

const jsonFile = (name) =>
  JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), "utf8"));
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
const decoder = new TextDecoder("utf-8", { fatal: true });

// 标准制品按摘要固定；日常检查不访问标准站点或后端仓库。
export function checkPins() {
  for (const directory of [
    "schemas/agent-plugins-1.0.0",
    "contracts/directory-mcp",
  ]) {
    const pin = jsonFile(`${directory}/pin.json`);
    for (const [name, expected] of Object.entries(pin.files)) {
      const bytes = readFileSync(
        new URL(`../${directory}/${name}`, import.meta.url),
      );
      if (digest(bytes) !== expected.sha256)
        throw new Error("固定制品摘要不符，必须重新审核导入来源。");
    }
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
const pluginSchema = ajv.compile(
  jsonFile("schemas/agent-plugins-1.0.0/plugin.schema.json"),
);
const mcpSchema = ajv.compile(
  jsonFile("schemas/agent-plugins-1.0.0/mcp.schema.json"),
);
const publicEndpoint = "https://kabo.sh/mcp-pub";
const scopesByResource = new Map([
  ["https://kabo.sh/mcp", ["account:read", "registry", "telemetry", "data"]],
  [publicEndpoint, ["data", "video"]],
]);

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keys(value, names) {
  return (
    object(value) && Object.keys(value).every((name) => names.includes(name))
  );
}

/** 原样验证 portable MCP；Codex 会拒绝 server extensions，OAuth 走标准发现。 */
export function validateManifests(manifest, mcp, auth) {
  checkPins();
  if (!pluginSchema(manifest))
    throw new Error("plugin.json 不符合 portable 1.0.0 schema。");
  if (!mcpSchema(mcp))
    throw new Error("mcp.json 不符合 portable 1.0.0 schema；不得剥离字段后冒充通过。");
  const server = mcp?.mcpServers?.kabo;
  if (
    !object(server) ||
    !keys(auth, [
      "type",
      "client",
      "resource",
      "baseScopes",
      "defaultScopes",
    ]) ||
    auth.type !== "oauth" ||
    !scopesByResource.has(server.url) ||
    auth.resource !== server.url ||
    !keys(auth.client, ["mode"]) ||
    auth.client.mode !== "dcr" ||
    JSON.stringify(auth.baseScopes) !==
      JSON.stringify(["openid", "email", "offline_access"]) ||
    JSON.stringify(auth.defaultScopes) !== JSON.stringify(scopesByResource.get(server.url))
  )
    throw new Error("OAuth 配置必须匹配实际 MCP 资源、DCR 与其权限。");
}

function yaml(text) {
  const document = parseDocument(text, { uniqueKeys: true });
  if (document.errors.length) throw new Error("Skill YAML 无效或含重复字段。");
  const value = document.toJS({ maxAliasCount: 0 });
  if (!object(value)) throw new Error("Skill YAML 必须为对象。");
  return value;
}

// PNG 限制采用本项目静态品牌资产规格：8-bit RGB/RGBA、非交错；验证 CRC 和解压长度。
export function validateIcon(bytes) {
  if (
    bytes.length > 5 * 1024 * 1024 ||
    !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  )
    throw new Error("图标必须是小于 5 MiB 的 PNG。");
  let offset = 8;
  let header;
  let ended = false;
  const imageData = [];
  while (offset < bytes.length) {
    if (offset + 12 > bytes.length) throw new Error("PNG 文件截断。");
    const size = bytes.readUInt32BE(offset);
    if (offset + size + 12 > bytes.length) throw new Error("PNG 数据块截断。");
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    const data = bytes.subarray(offset + 8, offset + 8 + size);
    if (
      crc32(bytes.subarray(offset + 4, offset + 8 + size)) !==
      bytes.readUInt32BE(offset + 8 + size)
    )
      throw new Error("PNG 数据块摘要不符。");
    if (!header && type !== "IHDR") throw new Error("PNG 缺少首个 IHDR。");
    if (type === "IHDR") {
      if (header || size !== 13) throw new Error("PNG 图像头无效。");
      const width = data.readUInt32BE(0),
        height = data.readUInt32BE(4);
      if (
        width !== height ||
        width < 48 ||
        width > 4096 ||
        data[8] !== 8 ||
        ![2, 6].includes(data[9]) ||
        data[10] !== 0 ||
        data[11] !== 0 ||
        data[12] !== 0
      )
        throw new Error(
          "图标必须为 48～4096 方形、8-bit RGB/RGBA 非交错 PNG。",
        );
      header = { width, height, channels: data[9] === 6 ? 4 : 3 };
    } else if (type === "IDAT") imageData.push(data);
    else if (type === "IEND") {
      if (size || offset + 12 !== bytes.length)
        throw new Error("PNG 结束块无效。");
      ended = true;
    }
    offset += size + 12;
  }
  if (!header || !imageData.length || !ended)
    throw new Error("PNG 图像不完整。");
  const stride = header.width * header.channels + 1;
  const expected = stride * header.height;
  const decoded = inflateSync(Buffer.concat(imageData), {
    maxOutputLength: expected,
  });
  if (decoded.length !== expected) throw new Error("PNG 像素长度不符。");
  for (let row = 0; row < header.height; row++)
    if (decoded[row * stride] > 4) throw new Error("PNG 行过滤类型无效。");
}

/** 校验实际 Skill 的引用、MCP 依赖与输入输出制品，避免迁入无法工作的旧入口。 */
export function validateSkills(files, endpoint) {
  const names = new Set();
  for (const [name, file] of files) {
    if (!name.startsWith("skills/")) continue;
    const parts = name.split("/");
    if (parts.length < 3) throw new Error("每个 Skill 必须有独立目录。");
    names.add(parts[1]);
    if (file.bytes.length > (parts.at(-1) === "SKILL.md" ? 256 : 1024) * 1024)
      throw new Error("Skill 文件超过项目导入上限。");
  }
  for (const name of names) {
    const root = `skills/${name}`;
    const entry = files.get(`${root}/SKILL.md`);
    if (!entry || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name) || name.length > 64)
      throw new Error("Skill 目录或入口缺失。");
    const text = decoder.decode(entry.bytes);
    const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
    if (!front) throw new Error("Skill 缺少 YAML frontmatter。");
    const metadata = yaml(front[1]);
    if (
      metadata.name !== name ||
      typeof metadata.description !== "string" ||
      !metadata.description.trim() ||
      metadata.description.length > 1024 ||
      !text.slice(front[0].length).trim()
    )
      throw new Error("Skill 名称、描述或正文无效。");
    const resources = [...files].filter(([key]) => key.startsWith(root + "/"));
    if (
      resources.length > 512 ||
      resources.reduce((size, [, item]) => size + item.bytes.length, 0) >
        5 * 1024 * 1024
    )
      throw new Error("Skill 支持文件超过静态包资源预算。");
    for (const [resource, item] of resources) {
      if (!resource.endsWith(".md")) continue;
      for (const match of decoder
        .decode(item.bytes)
        .matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
        if (/^(?:https:\/\/|#)/.test(match[1])) continue;
        const target = path.posix.normalize(
          path.posix.join(path.posix.dirname(resource), match[1].split("#")[0]),
        );
        if (!target.startsWith("skills/") || !files.has(target))
          throw new Error("Skill 引用了缺失或越界的支持文件。");
      }
    }
    const ui = files.get(`${root}/agents/openai.yaml`);
    if (ui) {
      const config = yaml(decoder.decode(ui.bytes));
      const tools = config.dependencies?.tools;
      if (
        tools !== undefined &&
        (!Array.isArray(tools) ||
          tools.length !== 1 ||
          tools[0]?.type !== "mcp" ||
          tools[0]?.value !== "kabo" ||
          tools[0]?.transport !== "streamable_http" ||
          tools[0]?.url !== endpoint)
      )
        throw new Error("Skill 依赖必须指向插件声明的同一个 Kabo MCP。");
    }
  }
}

/** 静态宿主只依赖固定公开工具和包内 Skills；旧动态下载运行时已退出本包。 */
export function validateRuntime(files, mcp) {
  const runtimeFile = files.get("runtime-contract.json");
  if (!runtimeFile) {
    if (files.has("skills.lock.json")) throw new Error("静态包缺少运行契约。");
    return;
  }
  const runtime = JSON.parse(runtimeFile.bytes);
  if (runtime.format !== "kabo.static-host-runtime.v1" || runtime.execution !== "host" || runtime.skillDistribution !== "bundled" || runtime.server !== "kabo" || runtime.resource !== mcp.mcpServers.kabo.url)
    throw new Error("静态宿主执行边界无效。");
  const lock = validateStaticSkills(files);
  checkPins();
  const approved = jsonFile("contracts/directory-mcp/data-tool-bindings.json");
  const same = (actual, expected) => Array.isArray(actual) && new Set(actual).size === actual.length && JSON.stringify([...actual].sort()) === JSON.stringify([...expected].sort());
  if (!same(runtime.requiredTools, approved.requiredTools) || !same(runtime.optionalTools, Object.values(approved.connectorTools)) || !object(runtime.connectorTools) ||
      JSON.stringify(Object.entries(runtime.connectorTools).sort()) !== JSON.stringify(Object.entries(approved.connectorTools).sort()))
    throw new Error("静态宿主工具绑定必须匹配提供方公开契约。");
  if (!same(runtime.skills, lock.skills.map(skill => skill.id))) throw new Error("选定 Skills 与固定内容不符。");
  // 绑定表与 manifest 随特化逐步退出；还在的必须与公开契约一致。
  for (const skill of lock.skills) {
    const prefix = `skills/${skill.id}/`;
    const bindings = files.get(prefix + "references/mcp-bindings.json");
    if (bindings && (digest(bindings.bytes) !== lock.mcp.sha256 || !same(JSON.parse(bindings.bytes).requiredTools, approved.requiredTools) ||
        JSON.stringify(JSON.parse(bindings.bytes).connectorTools) !== JSON.stringify(approved.connectorTools)))
      throw new Error("Skill 与插件的公开工具契约不一致。");
    const metadata = files.get(prefix + "manifest.json");
    for (const connector of metadata ? JSON.parse(metadata.bytes).required?.connectors ?? [] : []) for (const operation of connector.operations)
      if (!runtime.connectorTools[`${connector.connector_id}/${operation}`]) throw new Error("Skill 声明了未公开的操作。");
  }
  for (const [name, value] of files) {
    if (name.startsWith("bin/") || name === "trusted-keys.json" || name.startsWith("scripts/runtime/"))
      throw new Error("静态包不得重新包含动态运行器。");
  }
  const manifest = JSON.parse(files.get("plugin.json").bytes);
  for (const directory of [".claude-plugin"]) {
    const compatibility = JSON.parse(files.get(`${directory}/plugin.json`)?.bytes ?? "null");
    // license 与 privacyPolicyUrl 是目录提交元数据；许可必须与主清单一致。
    if (!compatibility || compatibility.name !== manifest.name || compatibility.version !== manifest.version ||
        compatibility.license !== manifest.license ||
        !keys(compatibility, ["name", "version", "description", "author", "homepage", "license", "privacyPolicyUrl", "icon"]))
      throw new Error("宿主适配只能声明同一插件身份，不能另配 Skills 或执行器。");
    // icon 只供目录展示（Claude Code 运行时不读）；必须是包内同一份图标，不能另带一套资源。
    if (compatibility.icon !== undefined && (typeof compatibility.icon !== "string" || !compatibility.icon.startsWith("./assets/") || !files.has(compatibility.icon.slice(2))))
      throw new Error("宿主适配的图标必须引用包内 assets 文件。");
  }
  const legacy = JSON.parse(files.get(".mcp.json")?.bytes ?? "null");
  if (JSON.stringify(legacy) !== JSON.stringify({ mcpServers: { kabo: { type: "http", url: mcp.mcpServers.kabo.url } } }))
    throw new Error("宿主 MCP 适配与唯一连接不一致。");
}

/** 提交门只检查同一包，不生成删功能的另一个版本；生产验收始终另行提供。 */
export function assessSubmission(files, acceptance = {}) {
  checkPins();
  const byName = files instanceof Map ? files : new Map(files.map(file => [file.name, file]));
  const mcp = JSON.parse(decoder.decode(byName.get("mcp.json").bytes));
  const blockers = [];
  if (mcp.mcpServers.kabo.url !== publicEndpoint)
    blockers.push({ code: "MCP_SURFACE_NOT_DIRECTORY", message: "插件必须连接公开目录的独立 OAuth 资源。" });
  const runtime = byName.get("runtime-contract.json");
  if (runtime) {
    const requirements = JSON.parse(decoder.decode(runtime.bytes));
    const available = new Set(jsonFile("contracts/directory-mcp/tools-list.json").tools.map(tool => tool.name));
    const missing = [...requirements.requiredTools, ...requirements.optionalTools].filter(name => !available.has(name));
    if (missing.length) blockers.push({ code: "PUBLIC_TOOL_CONTRACT_GAP", tools: [...new Set(missing)].sort(), message: "目录契约缺少插件依赖的业务工具；不得绕过此门或公开通用执行器。" });
  }
  const checked = assessAcceptance({ ...acceptance, toolsSha256: digest(readFileSync(new URL('../contracts/directory-mcp/tools-list.json', import.meta.url))) });
  blockers.push(...checked.blockers);
  return { submissionReady: blockers.length === 0, blockers, acceptanceEvidence: checked.evidence };
}
