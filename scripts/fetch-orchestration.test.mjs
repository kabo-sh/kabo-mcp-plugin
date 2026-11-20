// Mechanical gate for the backend closed loop of data-fetch orchestration (docs/skills-spec.md KS9); both
// are ratchets that only go down:
// 1. Handover rounds: every call of a hand-over helper (any name starting with `fetch_round`,
//    `fetch_or_hand_over` or `hand_over`, e.g. `hand_over_media(` or `cd.fetch_round_compact(`) in a driver is
//    one round of "print call: -> the host model calls them one by one -> write to disk -> resume", costing two
//    or three extra model calls per round. The existing count per skill is recorded in HANDOVER_SITES; new
//    skills may not have any, and existing skills may not gain more. When a skill migrates to the backend API
//    and the count drops, lower the number here in the same PR (a mismatched number also fails, so the ratchet
//    cannot loosen). A renamed helper cannot slip past: every line that prints the host's hand-over markers
//    (`Hand-over: `, `call: `) must sit inside a function the call pattern names (HANDOVER_PRINT).
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

export const HANDOVER_CALL = /\b(?:fetch_round|fetch_or_hand_over|hand_over)\w*\(/;
const HANDOVER_HELPER = /^(?:fetch_round|fetch_or_hand_over|hand_over)\w*$/;
// What the host reads as a hand-over: the `Hand-over: ` instruction line and the `call: ` lines under it.
export const HANDOVER_PRINT = /["'](?:Hand-over|call): |\bHANDOVER_PREFIX\s*\+/;
// The one module-level marker allowed: the prefix constant the connector drivers print through.
const PREFIX_CONSTANT = /^HANDOVER_PREFIX = "call: "$/;
export const HOST_PROBE = /connector-outbox|\boutbox_dir\b|\bCODEX_THREAD_ID\b|\bturn_token\b/;

const HANDOVER_SITES = {
  // analyze-content-video, 7 sites. observe_video.py hand_over_calls: (1) begin(): the observation request, also
  // reached once through fall_back() for the single fallback source; (2) resume(): the whole-video viewing
  // started after the media call measured the duration (or the same start resent once with its original
  // arguments) -- the known pre-round of docs/skills-spec.md KS9: analyze_content_video neither reports the
  // duration nor refuses a video over the 10-minute limit, so the measurement has to come first until the backend
  // tool checks the duration itself; (3) resume(): the bounded wait (KS8) on the same viewing and media jobs. The
  // side calls (identify_video_song, summarize_video_comments) ride in site (1)'s first hand-over and add no site.
  // collect_media.py hand_over_media (its own CLI): (4) the request, (5)-(7) the same call again: still running
  // (bounded wait) or resent without the frame options the server refused.
  "analyze-content-video": 7,
  "analyze-creator-competitors": 6,
  "analyze-tiktok-competitors": 3,
  "diagnose-reach-drop": 1,
  // 5 cd.fetch_round sites, plus hand_over_lean (2), hand_over_inline and fetch_round_compact: wrappers around
  // cd.fetch_round / cd.hand_over that an exact-name pattern missed.
  "research-instagram-trends": 9,
  "research-tiktok-trends": 3,
  "research-youtube-trends": 3,
  "review-creator-account": 1,
  // watch_media.py hand_over_media: the media request and its bounded wait on the same jobs.
  "review-creator-account-deep": 2,
  "verify-platform-rule": 1,
};

const HOST_PROBE_FILES = [];

export function handoverSites(files = scripts()) {
  const counts = {};
  for (const file of files) {
    if (file.endsWith("/connector_driver.py")) continue; // The definition site, not the call site
    const skill = file.split("/")[1];
    for (const line of text(file).split("\n")) {
      if (HANDOVER_CALL.test(line) && !/^\s*(?:def\s|#)/.test(line)) counts[skill] = (counts[skill] ?? 0) + 1;
    }
  }
  return counts;
}

// "file:line in <function>" for every line that prints a hand-over marker outside a hand-over helper.
export function strayHandoverPrints(files = scripts(), read = text) {
  const stray = [];
  for (const file of files) {
    const stack = []; // [indent, name] of the enclosing defs
    read(file).split("\n").forEach((line, index) => {
      const code = line.trim();
      if (!code || code.startsWith("#")) return;
      const indent = line.length - line.trimStart().length;
      while (stack.length && indent <= stack.at(-1)[0]) stack.pop();
      const def = /^(?:async\s+)?def\s+(\w+)/.exec(code);
      if (def) stack.push([indent, def[1]]);
      if (!HANDOVER_PRINT.test(line)) return;
      if (!stack.length && PREFIX_CONSTANT.test(code)) return;
      if (stack.some(([, name]) => HANDOVER_HELPER.test(name))) return;
      stray.push(`${file}:${index + 1} in ${stack.at(-1)?.[1] ?? "<module>"}`);
    });
  }
  return stray;
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

test("only a hand-over helper prints a hand-over, so a renamed helper is still counted (KS9)", () => {
  assert.deepEqual(
    strayHandoverPrints(),
    [],
    "a function that is not named fetch_round* / fetch_or_hand_over* / hand_over* prints a hand-over for the host; " +
      "name it so its call sites are counted in HANDOVER_SITES, or better, move the round into a backend tool (KS9).",
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
  assert.ok(HANDOVER_CALL.test("    hand_over_calls(current, start_viewer=True)"));
  assert.ok(HANDOVER_CALL.test("    cd.fetch_round_compact(calls, args, place)"));
  assert.ok(!HANDOVER_CALL.test("original_hand_over(printed, why)"));
  const fixture = {
    "skills/x/scripts/a.py": 'def give_host(calls):\n    say("Hand-over: make this call")\n',
    "skills/x/scripts/b.py": 'HANDOVER_PREFIX = "call: "\ndef hand_over_x(calls):\n    def line(c):\n' +
      '        return HANDOVER_PREFIX + c\n    say("call: " + c)\ndef after():\n    say("call: " + c)\n',
  };
  assert.deepEqual(strayHandoverPrints(Object.keys(fixture), (file) => fixture[file]),
    ["skills/x/scripts/a.py:2 in give_host", "skills/x/scripts/b.py:7 in after"]);
  assert.ok(HOST_PROBE.test('root / "connector-outbox-host"'));
});
