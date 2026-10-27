#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";
import { acceptanceChecks } from "./submission-evidence.mjs";
import { readPackageFiles, validatePackage, deterministicZip } from "./openai-plugin-package.mjs";

const digest = bytes => createHash("sha256").update(bytes).digest("hex");
try {
  const { values } = parseArgs({ options: { commit: { type: "string" }, output: { type: "string" } } });
  if (!values.output) throw new Error("需要输出目录。");
  const files = readPackageFiles({ commit: values.commit });
  const { version } = validatePackage(files);
  const root = path.resolve(values.output);
  await mkdir(path.dirname(root), { recursive: true });
  await mkdir(root);
  const placeholder = "Pending production acceptance. This check has not been run.\n";
  await writeFile(path.join(root, "pending.txt"), placeholder, { flag: "wx", mode: 0o600 });
  const receipt = {
    format: "kabo.openai-acceptance.v1", environment: "production", resource: "https://kabo.sh/mcp-pub",
    release: {
      commit: values.commit, version, zipSha256: digest(deterministicZip(files)),
      toolsSha256: digest(await readFile(new URL("../contracts/directory-mcp/tools-list.json", import.meta.url))),
    },
    checks: acceptanceChecks.map(id => ({ id, status: "not-run", performedAt: null, artifact: "pending.txt", sha256: digest(placeholder) })),
  };
  await writeFile(path.join(root, "acceptance.json"), JSON.stringify(receipt, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  console.log(`验收索引已初始化：${acceptanceChecks.length} 项均未执行，submissionReady=false。`);
} catch {
  console.error("无法创建验收索引。使用完整 commit 和不存在的输出目录。");
  process.exitCode = 1;
}
