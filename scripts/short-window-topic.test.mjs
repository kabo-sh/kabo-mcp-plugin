import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("behavior regression for the short-window niche gate, exact dates, and the full report", () => {
  execFileSync("python3", ["-B", "scripts/short-window-topic-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
