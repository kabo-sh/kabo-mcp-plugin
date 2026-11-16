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

/** Read only Git blobs of the pinned commit; never read the working tree, adjacent repository sources, or run any script in the package. */
export function readPackageFiles({ repository = root, commit, packagePath = "." }) {
  if (!/^[a-f0-9]{40}$/.test(commit ?? "") || !(packagePath === "." || relativePath(packagePath)))
    throw new Error("A full commit SHA and a repository-relative package path are required.");
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: repository,
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
      maxBuffer: 32 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  if (git("cat-file", "-t", commit).toString().trim() !== "commit")
    throw new Error("The source revision must be a commit.");
  const allEntries = git("ls-tree", "-r", "-z", packagePath === "." ? commit : `${commit}:${packagePath}`)
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
  if (packagePath === ".") assertNoHiddenComponents(allEntries.map(entry => entry.slice(entry.indexOf("\t") + 1)));
  const entries = allEntries.filter(entry => packagePath !== "." || isPackageFile(entry.slice(entry.indexOf("\t") + 1)));
  if (!entries.length || entries.length > 2048)
    throw new Error("The package must have 1-2048 files.");
  let total = 0;
  const files = entries.map((entry) => {
    const match = /^(100644|100755) blob ([a-f0-9]{40})\t(.+)$/.exec(entry);
    if (!match || !relativePath(match[3]))
      throw new Error("Only regular files are allowed in the package: no links, submodules or out-of-bounds paths.");
    const size = Number(git("cat-file", "-s", match[2]).toString().trim());
    total += size;
    if (
      !Number.isSafeInteger(size) ||
      size < 0 ||
      size > 16 * 1024 * 1024 ||
      total > 64 * 1024 * 1024
    )
      throw new Error("The package exceeds the local build limits: 16 MiB per file, 64 MiB total.");
    return {
      name: match[3],
      mode: Number.parseInt(match[1], 8),
      bytes: git("cat-file", "blob", match[2]),
    };
  });
  return files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** Format and project safety gate; does not pose as an OpenAI backend scan and does not require a fixed number of Skills. */
export function validatePackage(files) {
  const byName = new Map();
  for (const file of files) {
    if (!relativePath(file.name) || byName.has(file.name))
      throw new Error("Package file path is invalid or duplicated.");
    byName.set(file.name, file);
    if (
      /(?:^|\/)(?:hooks|apps|registry|internal|private|\.git)(?:\/|$)|(?:^|\/)(?:\.app\.json|\.env(?:\.[^/]*)?|credentials\.json)$/i.test(
        file.name,
      )
    )
      throw new Error("Contains an unsupported component or private configuration file.");
    const text = file.bytes.toString("utf8");
    if (
      /-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|\bAIza[A-Za-z0-9_-]{30,}|\bBearer\s+eyJ[A-Za-z0-9_.-]+|(?:https?:\/\/)(?:localhost|127\.0\.0\.1|pre\.kabo\.sh)(?:[:/\s"']|$)|\/(?:home|Users)\/[^\s"']+/.test(
        text,
      )
    )
      throw new Error(
        "Package content hit the credential, test-address or local-path check; the matched text is not printed.",
      );
    if (file.name.toLowerCase().endsWith(".json")) {
      const inspect = (value) => {
        if (!value || typeof value !== "object") return;
        for (const [key, child] of Object.entries(value)) {
          // The `hooks` in the business schema are video-opening fields, not lifecycle configuration; real components
          //   and credentials are still forbidden.
          if (
            /^(?:test_credentials|reviewer_instructions|client_secret|access_token|refresh_token|password|api_key|authorization)$/i.test(key) ||
            (/^(?:hooks|apps)$/i.test(key) && !/^skills\/[^/]+\/references\/[^/]+\.schema\.json$/.test(file.name))
          )
            throw new Error(
              "JSON contains components, reviewer material or credential fields that are not allowed in the package.",
            );
          inspect(child);
        }
      };
      try {
        inspect(JSON.parse(text));
      } catch (error) {
        if (error instanceof SyntaxError)
          throw new Error("JSON in the package is invalid; the original text is not printed.");
        throw error;
      }
    }
  }
  const parse = (name) => {
    const file = byName.get(name);
    if (!file) throw new Error(`Missing ${name}.`);
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
    throw new Error("A portable plugin.json schema and a valid package name are required.");
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
    throw new Error("The build must use an explicit SemVer version.");
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
    throw new Error("This build entry accepts only one credential-free Kabo production MCP configuration.");
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
      throw new Error(`Directory field ${key} is missing or exceeds the limit.`);
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
      throw new Error(`Directory field ${key} must be a Kabo production HTTPS page.`);
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
      throw new Error(`Icon ${key} must reference an in-package assets file.`);
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
      "capabilities must be at most 20 capability descriptions of at most 120 characters each.",
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
        "defaultPrompt allows at most 3 entries, which must be unique, contain no @mention, and be at most 128 characters each.",
      );
  }
  if (
    openai.onboardingSkill &&
    (!openai.onboardingSkill.startsWith("./skills/") ||
      !openai.onboardingSkill.endsWith("/SKILL.md") ||
      !byName.has(openai.onboardingSkill.slice(2)))
  )
    throw new Error("onboardingSkill must point to a Skill actually in the package.");
  validateSkills(byName, servers[0].url);
  validateRuntime(byName, mcp);
  return { name: manifest.name, version: manifest.version };
}

/** ZIP STORE + fixed 1980-01-01 timestamp and Unix mode, so a compression library or checkout mtime cannot change the digest. */
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
      "Requires --commit <full SHA> --package-path <repository directory> --output <new directory>.",
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
    throw new Error("The submission gate for the same plugin has not passed.");
  }
  const name = `${identity.name}-${identity.version}.zip`;
  const output = path.resolve(values.output);
  // A new directory refuses to overwrite a previous delivery; for a repeated build, pick another directory and
  //   compare SHA-256.
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
      "Plugin package build failed. Check the pinned revision, package content and output directory; package text and credentials are not printed.",
    );
    process.exitCode = 1;
  });
}
