import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("account report validators reject leaks, not creator prose, and fit display length", () => {
  execFileSync("python3", ["-B", "scripts/account-review-validators.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
