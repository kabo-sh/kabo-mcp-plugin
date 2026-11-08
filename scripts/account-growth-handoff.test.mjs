import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("账号预测交付保留日期、来源、用户假设与独立指标", () => {
  execFileSync("python3", ["-B", "scripts/account-growth-handoff.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
