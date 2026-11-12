import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("end-to-end regression for this run's goal, cold start, and slot allocation", () => {
  execFileSync("python3", ["-B", "scripts/trends-goal-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
