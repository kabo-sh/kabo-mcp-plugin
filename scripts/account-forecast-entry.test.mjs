import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("the one-command forecast builds its own inputs from the request's facts", () => {
  execFileSync("python3", ["-B", "scripts/account-forecast-entry.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
