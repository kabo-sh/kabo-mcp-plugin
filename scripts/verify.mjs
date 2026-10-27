#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { checkPackage } from "./package-check.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
if (Number(process.versions.node.split(".")[0]) < 24)
  throw new Error("构建与验证需要 Node 24 或更新版本。");
const scripts = (await readdir(path.join(root, "scripts")))
  .filter((name) => name.endsWith(".mjs"))
  .sort();
for (const name of scripts)
  execFileSync(process.execPath, ["--check", `scripts/${name}`], {
    cwd: root,
    stdio: "inherit",
  });
// 语法编译到内存，不在固定 Skills 目录生成 __pycache__。
execFileSync("python3", ["-c", "import ast,pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path('skills').rglob('*.py')]"], { cwd: root, stdio: "inherit" });
const identity = await checkPackage();
console.log(`${identity.name} ${identity.version}: 包材料检查通过`);
// Skills 规范门禁不启用（enforced 为空）；这里只输出摘要，不阻塞。
execFileSync(process.execPath, ["scripts/skills-lint.mjs", "--summary"], {
  cwd: root,
  stdio: "inherit",
});
const tests = scripts.filter((name) => name.endsWith(".test.mjs"));
if (!tests.length) throw new Error("未发现测试，不能报告验收通过。");
execFileSync(
  process.execPath,
  ["--test", ...tests.map((name) => `scripts/${name}`)],
  {
    cwd: root,
    stdio: "inherit",
  },
);
