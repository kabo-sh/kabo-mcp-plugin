// Time-limit regression for local-file frame extraction/measurement: the two measurement passes each decode one
// stream, the command stops itself at the deadline, frames are written to disk first, and --signals-only
// measures on its own.
// End-to-end cases are skipped automatically on machines without ffmpeg; the mock cases still run.
import { execFileSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("analyze-content-video local measurement no longer hangs frame extraction", () => {
  execFileSync("python3", ["-B", "scripts/acv-local-measure-regression.py", "-v"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  });
});
