// The overview frame plan (analyze-content-video/scripts/acv_timing.py) is one rule on two machines: the connector's
// extract_keyframes with `overview: true` and the local extractor must pick the same seconds for the same inputs.
// scripts/fixtures/acv-overview-parity.json holds the shared golden vectors (luma grids and their change units;
// durations, budgets, cuts, windows and per-second units with the frames each side must pick). The connector's test
// reads the same file as public-video-media-overview.parity.json and pins the same sha256, so neither side can drift
// alone. Videos up to 50 s keep today's plan exactly.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const PARITY_SHA256 = "689cf1703d92a55cd5cc2a3733cd200e12c81c7df6b1b817399db0ae9dfe172f";

test("the overview golden vectors are the file the connector's test pins", () => {
  const raw = readFileSync(new URL("fixtures/acv-overview-parity.json", import.meta.url));
  assert.equal(createHash("sha256").update(raw).digest("hex"), PARITY_SHA256);
  const document = JSON.parse(raw.toString("utf8"));
  assert.ok(document.plans.length >= 30);
  for (const duration of [30, 120, 600, 1800]) assert.ok(document.plans.some((plan) => plan.duration_s === duration), `${duration}s`);
});

test("the local planner reproduces every golden vector, and up to 50 s the overview changes nothing", () => {
  execFileSync("python3", ["-B", "scripts/acv-overview-parity.py"], { cwd: root, encoding: "utf8", stdio: "pipe" });
});
