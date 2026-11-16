// Mechanical gate for the backend closed loop of data-fetch orchestration (docs/skills-spec.md KS9); both
// are ratchets that only go down:
// 1. Handover rounds: every `fetch_round` / `fetch_or_hand_over` / `hand_over` call in a driver is one
// round of
//    "print call: -> the host model calls them one by one -> write to disk -> resume", costing two or
//    three extra model calls per round. The existing count per skill is recorded in
//    HANDOVER_SITES; new skills may not have any, and existing skills may not gain more. When a skill
//    migrates to the backend API and the count drops, lower
//    the number here in the same PR (a mismatched number also fails, so the ratchet cannot loosen).
// 2. Host probing: scripts may not take different fetch paths per host (connector-outbox, session thread
// id, turn token). Existing
//    files are recorded in HOST_PROBE_FILES; once one is removed, take it off the list in the same PR.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = () =>
  execFileSync("git", ["ls-files", "-z", "--", "skills"], { cwd: root, encoding: "utf8" })
    .split("\0")
    .filter((file) => /^skills\/[^/]+\/scripts\/[^/]+\.py$/.test(file));
const text = (file) => readFileSync(path.join(root, file), "utf8");

export const HANDOVER_CALL = /\b(?:fetch_round|fetch_or_hand_over|hand_over)\(/;
export const HOST_PROBE = /connector-outbox|\boutbox_dir\b|\bCODEX_THREAD_ID\b|\bturn_token\b/;

const HANDOVER_SITES = {
  "analyze-creator-competitors": 6,
  "analyze-tiktok-competitors": 3,
  "diagnose-reach-drop": 1,
  "research-instagram-trends": 5,
  "research-tiktok-trends": 3,
  "research-youtube-trends": 3,
  "review-creator-account": 1,
  "verify-platform-rule": 1,
};

const HOST_PROBE_FILES = [];

export function handoverSites(files = scripts()) {
  const counts = {};
  for (const file of files) {
    if (file.endsWith("/connector_driver.py")) continue; // The definition site, not the call site
    const skill = file.split("/")[1];
    for (const line of text(file).split("\n")) {
      if (HANDOVER_CALL.test(line) && !/^\s*def\s/.test(line)) counts[skill] = (counts[skill] ?? 0) + 1;
    }
  }
  return counts;
}

export function hostProbeFiles(files = scripts()) {
  return files.filter((file) => HOST_PROBE.test(text(file))).sort();
}

test("handoff rounds only decrease, never increase: new multi-round fetches must be one backend call (KS9)", () => {
  assert.deepEqual(
    handoverSites(),
    HANDOVER_SITES,
    "drivers hand a fetch round to the host model more (or fewer) times than recorded. A new round belongs in a " +
      "backend endpoint that runs the whole fetch (docs/skills-spec.md KS9); after removing rounds, lower the numbers here.",
  );
});

test("scripts do not pick the fetch path by probing the host (KS9)", () => {
  assert.deepEqual(
    hostProbeFiles(),
    [...HOST_PROBE_FILES].sort(),
    "a script probes for a host-only fetch channel. Fetching must not branch on the host (docs/skills-spec.md KS9); " +
      "after deleting a probe, drop the file from HOST_PROBE_FILES.",
  );
});

test("the check itself catches violations", () => {
  assert.ok(HANDOVER_CALL.test("    cd.fetch_round(calls, args, place)"));
  assert.ok(!HANDOVER_CALL.test("original_hand_over(printed, why)"));
  assert.ok(HOST_PROBE.test('root / "connector-outbox-host"'));
});
