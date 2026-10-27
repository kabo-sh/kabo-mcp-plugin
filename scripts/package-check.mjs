#!/usr/bin/env node
import { lstat, readdir, readFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { parseArgs } from "node:util";
import { validatePackage, readPackageFiles, deterministicZip } from "./openai-plugin-package.mjs";
import { assessSubmission } from "./package-standard.mjs";
import { packageComponents, assertNoHiddenComponents, isPackageFile } from "./package-layout.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));

// 日常检查覆盖工作区变更；正式出包仍由打包器只读 Git blob。
export async function packageFiles(directory = root) {
  assertNoHiddenComponents(await readdir(directory));
  const files = [];
  let total = 0;
  async function visit(relative) {
    const target = path.join(directory, relative);
    const stat = await lstat(target);
    if (stat.isSymbolicLink()) throw new Error("包目录不得包含符号链接。");
    if (stat.isDirectory()) {
      for (const name of (await readdir(target)).sort())
        await visit(relative ? `${relative}/${name}` : name);
      return;
    }
    if (!isPackageFile(relative)) return;
    total += stat.size;
    if (
      !stat.isFile() ||
      files.length >= 2048 ||
      stat.size > 16 * 1024 * 1024 ||
      total > 64 * 1024 * 1024
    )
      throw new Error("包目录含特殊文件或超过本地构建上限。");
    files.push({
      name: relative,
      mode: stat.mode,
      bytes: await readFile(target),
    });
  }
  for (const component of packageComponents) await visit(component);
  return files;
}

export async function checkPackage(directory = root) {
  const files = await packageFiles(directory);
  return { ...validatePackage(files), fileCount: files.length, ...assessSubmission(files) };
}

if (
  process.argv[1] &&
  realpathSync(fileURLToPath(import.meta.url)) === realpathSync(process.argv[1])
) {
  const { values } = parseArgs({ options: {
    submission: { type: "boolean", default: false },
    commit: { type: "string" }, evidence: { type: "string" },
  } });
  const check = async () => {
    if (!values.commit) {
      if (values.evidence) throw new Error("验收证据只能检查锁定 commit。");
      return checkPackage();
    }
    const files = readPackageFiles({ commit: values.commit });
    const identity = validatePackage(files);
    const sha256 = createHash("sha256").update(deterministicZip(files)).digest("hex");
    return { ...identity, commit: values.commit, sha256, fileCount: files.length,
      ...assessSubmission(files, { evidencePath: values.evidence, commit: values.commit, version: identity.version, zipSha256: sha256 }),
    };
  };
  check().then(
    (result) => {
      if (values.submission) {
        console.log(JSON.stringify(result, null, 2));
        if (!result.submissionReady) process.exitCode = 1;
        return;
      }
      console.log(
        `${result.name} ${result.version}: ${result.fileCount} 个文件通过本地检查；submissionReady=${result.submissionReady}`,
      );
    },
    () => {
      console.error(
        "包检查失败；检查根目录组件的格式、路径与内容，不输出包正文。",
      );
      process.exitCode = 1;
    },
  );
}
