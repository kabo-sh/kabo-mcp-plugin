import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("account forecast handoffs preserve dates, sources, assumptions and independent metrics", () => {
  execFileSync("python3", ["-B", "scripts/account-growth-handoff.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
