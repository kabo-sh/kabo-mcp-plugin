import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("behavior regression for three-platform language admission, evidence conflicts, and unknown languages", () => {
  execFileSync("python3", ["-B", "scripts/content-language-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
