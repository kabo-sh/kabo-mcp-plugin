import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("content-ideas batches collect idempotently, assemble completely and allow one aggregate revision", () => {
  execFileSync("python3", ["-B", "scripts/ideas-batches-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
