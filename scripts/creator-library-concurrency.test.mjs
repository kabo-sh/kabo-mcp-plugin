import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("creator libraries serialize host processes and recover from interrupted writes", () => {
  execFileSync("python3", ["-I", "-B", fileURLToPath(new URL("./creator-library-concurrency.py", import.meta.url))], {
    stdio: "pipe",
    timeout: 60_000,
  });
});
