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

// Standard artifacts are pinned by digest; routine checks do not access the standard site or the backend
//   repository.
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
        throw new Error("Pinned artifact digest mismatch; re-review the import source.");
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
  // workspace:write goes into the first authorization (user decision, 2026-11-11, overriding the on-demand
  //   top-up of e2801c0): in a real host Codex
  // authorizes by defaultScopes in host-auth.json and does not top up permissions on a 403 challenge, so
  //   start-with-kabo could not get write access
  // for binding an account, generating the profile or saving pillar edits. Users with an old authorization are
  //   still covered by each Skill's insufficient_scope fallback prompt to re-authorize.
  [publicEndpoint, ["data", "video", "workspace:read", "workspace:write"]],
]);

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keys(value, names) {
  return (
    object(value) && Object.keys(value).every((name) => names.includes(name))
  );
}

/** Validate portable MCP as-is; Codex rejects server extensions, and OAuth uses standard discovery. */
export function validateManifests(manifest, mcp, auth) {
  checkPins();
  if (!pluginSchema(manifest))
    throw new Error("plugin.json does not match the portable 1.0.0 schema.");
  if (!mcpSchema(mcp))
    throw new Error("mcp.json does not match the portable 1.0.0 schema; do not strip fields to pass.");
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
      JSON.stringify(server.url === publicEndpoint ? ["openid", "profile", "email", "offline_access"] : ["openid", "email", "offline_access"]) ||
    JSON.stringify(auth.defaultScopes) !== JSON.stringify(scopesByResource.get(server.url))
  )
    throw new Error("OAuth configuration must match the actual MCP resource, DCR and its scopes.");
}

function yaml(text) {
  const document = parseDocument(text, { uniqueKeys: true });
  if (document.errors.length) throw new Error("Skill YAML is invalid or has duplicate fields.");
  const value = document.toJS({ maxAliasCount: 0 });
  if (!object(value)) throw new Error("Skill YAML must be an object.");
  return value;
}

// The PNG limits follow this project's static brand asset spec: 8-bit RGB/RGBA, non-interlaced; the CRC and
//   decompressed length are validated.
export function validateIcon(bytes) {
  if (
    bytes.length > 5 * 1024 * 1024 ||
    !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  )
    throw new Error("The icon must be a PNG smaller than 5 MiB.");
  let offset = 8;
  let header;
  let ended = false;
  const imageData = [];
  while (offset < bytes.length) {
    if (offset + 12 > bytes.length) throw new Error("PNG file is truncated.");
    const size = bytes.readUInt32BE(offset);
    if (offset + size + 12 > bytes.length) throw new Error("PNG chunk is truncated.");
    const type = bytes.toString("ascii", offset + 4, offset + 8);
    const data = bytes.subarray(offset + 8, offset + 8 + size);
    if (
      crc32(bytes.subarray(offset + 4, offset + 8 + size)) !==
      bytes.readUInt32BE(offset + 8 + size)
    )
      throw new Error("PNG chunk checksum mismatch.");
    if (!header && type !== "IHDR") throw new Error("PNG is missing the leading IHDR.");
    if (type === "IHDR") {
      if (header || size !== 13) throw new Error("PNG image header is invalid.");
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
          "The icon must be a square 48-4096 px, 8-bit RGB/RGBA non-interlaced PNG.",
        );
      header = { width, height, channels: data[9] === 6 ? 4 : 3 };
    } else if (type === "IDAT") imageData.push(data);
    else if (type === "IEND") {
      if (size || offset + 12 !== bytes.length)
        throw new Error("PNG end chunk is invalid.");
      ended = true;
    }
    offset += size + 12;
  }
  if (!header || !imageData.length || !ended)
    throw new Error("PNG image is incomplete.");
  const stride = header.width * header.channels + 1;
  const expected = stride * header.height;
  const decoded = inflateSync(Buffer.concat(imageData), {
    maxOutputLength: expected,
  });
  if (decoded.length !== expected) throw new Error("PNG pixel length mismatch.");
  for (let row = 0; row < header.height; row++)
    if (decoded[row * stride] > 4) throw new Error("PNG row filter type is invalid.");
}

/** Validate the actual Skill references, MCP dependencies and input/output artifacts, so a legacy entry point that cannot work is not migrated in. */
export function validateSkills(files, endpoint) {
  const names = new Set();
  for (const [name, file] of files) {
    if (!name.startsWith("skills/")) continue;
    const parts = name.split("/");
    if (parts.length < 3) throw new Error("Each Skill must have its own directory.");
    names.add(parts[1]);
    if (file.bytes.length > (parts.at(-1) === "SKILL.md" ? 256 : 1024) * 1024)
      throw new Error("A Skill file exceeds the project import limit.");
  }
  for (const name of names) {
    const root = `skills/${name}`;
    const entry = files.get(`${root}/SKILL.md`);
    if (!entry || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name) || name.length > 64)
      throw new Error("Skill directory or entry is missing.");
    const text = decoder.decode(entry.bytes);
    const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
    if (!front) throw new Error("Skill is missing YAML frontmatter.");
    const metadata = yaml(front[1]);
    if (
      metadata.name !== name ||
      typeof metadata.description !== "string" ||
      !metadata.description.trim() ||
      metadata.description.length > 1024 ||
      !text.slice(front[0].length).trim()
    )
      throw new Error("Skill name, description or body is invalid.");
    const resources = [...files].filter(([key]) => key.startsWith(root + "/"));
    if (
      resources.length > 512 ||
      resources.reduce((size, [, item]) => size + item.bytes.length, 0) >
        5 * 1024 * 1024
    )
      throw new Error("Skill support files exceed the static package resource budget.");
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
          throw new Error("Skill references a missing or out-of-bounds support file.");
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
        throw new Error("Skill dependencies must point to the same Kabo MCP the plugin declares.");
    }
  }
}

/** The static host depends only on the pinned public tools and in-package Skills; the legacy dynamic download runtime has left this package. */
export function validateRuntime(files, mcp) {
  const runtimeFile = files.get("runtime-contract.json");
  if (!runtimeFile) {
    if (files.has("skills.lock.json")) throw new Error("Static package is missing the runtime contract.");
    return;
  }
  const runtime = JSON.parse(runtimeFile.bytes);
  if (runtime.format !== "kabo.static-host-runtime.v1" || runtime.execution !== "host" || runtime.skillDistribution !== "bundled" || runtime.server !== "kabo" || runtime.resource !== mcp.mcpServers.kabo.url)
    throw new Error("Static host execution boundary is invalid.");
  const lock = validateStaticSkills(files);
  checkPins();
  const approved = jsonFile("contracts/directory-mcp/data-tool-bindings.json");
  const same = (actual, expected) => Array.isArray(actual) && new Set(actual).size === actual.length && JSON.stringify([...actual].sort()) === JSON.stringify([...expected].sort());
  if (!same(runtime.requiredTools, approved.requiredTools) || !same(runtime.optionalTools, Object.values(approved.connectorTools)) || !object(runtime.connectorTools) ||
      JSON.stringify(Object.entries(runtime.connectorTools).sort()) !== JSON.stringify(Object.entries(approved.connectorTools).sort()))
    throw new Error("Static host tool bindings must match the provider's public contract.");
  if (!same(runtime.skills, lock.skills.map(skill => skill.id))) throw new Error("Selected Skills do not match the pinned content.");
  // The binding table and manifest are being retired as skills get specialized; any that remain must match the
  //   public contract.
  for (const skill of lock.skills) {
    const prefix = `skills/${skill.id}/`;
    const bindings = files.get(prefix + "references/mcp-bindings.json");
    if (bindings && (digest(bindings.bytes) !== lock.mcp.sha256 || !same(JSON.parse(bindings.bytes).requiredTools, approved.requiredTools) ||
        JSON.stringify(JSON.parse(bindings.bytes).connectorTools) !== JSON.stringify(approved.connectorTools)))
      throw new Error("Skill and plugin public tool contracts are inconsistent.");
    const metadata = files.get(prefix + "manifest.json");
    for (const connector of metadata ? JSON.parse(metadata.bytes).required?.connectors ?? [] : []) for (const operation of connector.operations)
      if (!runtime.connectorTools[`${connector.connector_id}/${operation}`]) throw new Error("Skill declares an operation that is not public.");
  }
  for (const [name, value] of files) {
    if (name.startsWith("bin/") || name === "trusted-keys.json" || name.startsWith("scripts/runtime/"))
      throw new Error("The static package must not include a dynamic runner again.");
  }
  const manifest = JSON.parse(files.get("plugin.json").bytes);
  // The skills CLI copies only a single Skill directory: the license must be written in each Skill's own
  //   frontmatter and match the main manifest.
  for (const skill of lock.skills) {
    const text = decoder.decode(files.get(`skills/${skill.id}/SKILL.md`).bytes);
    if (yaml(/^---\r?\n([\s\S]*?)\r?\n---/.exec(text)[1]).license !== manifest.license)
      throw new Error("The Skill license must match the plugin manifest.");
  }
  for (const directory of [".claude-plugin"]) {
    const compatibility = JSON.parse(files.get(`${directory}/plugin.json`)?.bytes ?? "null");
    // license and privacyPolicyUrl are directory-submission metadata; the license must match the main manifest.
    if (!compatibility || compatibility.name !== manifest.name || compatibility.version !== manifest.version ||
        compatibility.license !== manifest.license ||
        !keys(compatibility, ["name", "version", "description", "author", "homepage", "license", "privacyPolicyUrl", "icon"]))
      throw new Error("Host adapters may only declare the same plugin identity, not separate Skills or executors.");
    // icon is only for directory display (the Claude Code runtime does not read it); it must be the same
    //   in-package icon, not a separate set of resources.
    if (compatibility.icon !== undefined && (typeof compatibility.icon !== "string" || !compatibility.icon.startsWith("./assets/") || !files.has(compatibility.icon.slice(2))))
      throw new Error("The host adapter icon must reference an in-package assets file.");
  }
  const legacy = JSON.parse(files.get(".mcp.json")?.bytes ?? "null");
  if (JSON.stringify(legacy) !== JSON.stringify({ mcpServers: { kabo: { type: "http", url: mcp.mcpServers.kabo.url } } }))
    throw new Error("Host MCP adapter does not match the single connection.");
}

/** The submission gate checks the same package only and does not generate another version with features removed; production acceptance is always provided separately. */
export function assessSubmission(files, acceptance = {}) {
  checkPins();
  const byName = files instanceof Map ? files : new Map(files.map(file => [file.name, file]));
  const mcp = JSON.parse(decoder.decode(byName.get("mcp.json").bytes));
  const blockers = [];
  if (mcp.mcpServers.kabo.url !== publicEndpoint)
    blockers.push({ code: "MCP_SURFACE_NOT_DIRECTORY", message: "The plugin must connect to the public directory's standalone OAuth resource." });
  const runtime = byName.get("runtime-contract.json");
  if (runtime) {
    const requirements = JSON.parse(decoder.decode(runtime.bytes));
    const available = new Set(jsonFile("contracts/directory-mcp/tools-list.json").tools.map(tool => tool.name));
    const missing = [...requirements.requiredTools, ...requirements.optionalTools].filter(name => !available.has(name));
    if (missing.length) blockers.push({ code: "PUBLIC_TOOL_CONTRACT_GAP", tools: [...new Set(missing)].sort(), message: "The directory contract lacks business tools the plugin depends on; do not bypass this gate or expose a generic executor." });
  }
  const checked = assessAcceptance({ ...acceptance, toolsSha256: digest(readFileSync(new URL('../contracts/directory-mcp/tools-list.json', import.meta.url))) });
  blockers.push(...checked.blockers);
  return { submissionReady: blockers.length === 0, blockers, acceptanceEvidence: checked.evidence };
}
