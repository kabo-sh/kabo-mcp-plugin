import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("content-ideas count, continuation input and calendar candidate handoff keep their boundaries", () => {
  execFileSync("python3", ["-B", "scripts/ideas-count-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
