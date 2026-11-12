#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { checkPackage } from "./package-check.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
if (Number(process.versions.node.split(".")[0]) < 24)
  throw new Error("Build and verification require Node 24 or newer.");
const scripts = (await readdir(path.join(root, "scripts")))
  .filter((name) => name.endsWith(".mjs"))
  .sort();
for (const name of scripts)
  execFileSync(process.execPath, ["--check", `scripts/${name}`], {
    cwd: root,
    stdio: "inherit",
  });
// Compile the syntax in memory, without generating __pycache__ in the fixed Skills directory.
execFileSync("python3", ["-c", "import ast,pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path('skills').rglob('*.py')]"], { cwd: root, stdio: "inherit" });
const identity = await checkPackage();
console.log(`${identity.name} ${identity.version}: package material check passed`);
// The Skills spec gate is not enabled (enforced is empty); here only a summary is output, without blocking.
execFileSync(process.execPath, ["scripts/skills-lint.mjs", "--summary"], {
  cwd: root,
  stdio: "inherit",
});
const tests = scripts.filter((name) => name.endsWith(".test.mjs"));
if (!tests.length) throw new Error("No tests found; cannot report acceptance as passed.");
execFileSync(
  process.execPath,
  ["--test", ...tests.map((name) => `scripts/${name}`)],
  {
    cwd: root,
    stdio: "inherit",
  },
);
