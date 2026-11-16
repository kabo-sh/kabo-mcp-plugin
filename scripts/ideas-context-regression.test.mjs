import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("content-ideas chat transcript handoff, standalone error aggregation and the two-revision budget", () => {
  execFileSync("python3", ["-B", "scripts/ideas-context-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
