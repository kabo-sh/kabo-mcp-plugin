import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("选题数量、续接输入与日历候选交接保留边界", () => {
  execFileSync("python3", ["-B", "scripts/ideas-count-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
