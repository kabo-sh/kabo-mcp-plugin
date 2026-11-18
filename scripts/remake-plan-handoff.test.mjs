import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// remake-viral-video in the plugin plans the video and hands it to Kabo's producer: the Skill must
// name exactly the pinned video tools it uses, and its wording must keep the hand-off rules.
const root = fileURLToPath(new URL("..", import.meta.url));
const pinned = new Map(JSON.parse(await readFile(path.join(root, "contracts/directory-mcp/tools-list.json"), "utf8")).tools.map(t => [t.name, t]));
const doc = async (p) => readFile(path.join(root, "skills/remake-viral-video", p), "utf8");

test("hand-off tools are pinned with the video permission; get_remake_video reads project and producer and cancels", () => {
  for (const name of ["start_video_project", "check_video_plan", "make_video", "reply_to_video"]) {
    const tool = pinned.get(name);
    assert.ok(tool, name);
    assert.deepEqual(tool.securitySchemes, [{ scopes: ["video"], type: "oauth2" }]);
  }
  assert.equal(pinned.get("check_video_plan").annotations.readOnlyHint, true);
  for (const name of ["make_video", "reply_to_video"])
    assert.ok(pinned.get(name).inputSchema.properties.idempotency_key, name);
  const get = pinned.get("get_remake_video");
  for (const key of ["project", "producer", "cancel"]) assert.ok(get.inputSchema.properties[key], key);
  assert.equal(get.annotations.destructiveHint, true);
  for (const gone of ["start_remake_video", "render_remake_video", "edit_remake_video", "make_video_step", "finish_video_project"])
    assert.equal(pinned.has(gone), false, gone);
});

test("allowed-tools names only pinned tools, and every hand-off tool", async () => {
  const skill = await doc("SKILL.md");
  const allowed = /^allowed-tools: (.*)$/m.exec(skill)[1].split(/\s+/);
  for (const name of allowed) assert.ok(pinned.has(name), name);
  for (const name of ["start_video_project", "check_video_plan", "make_video", "reply_to_video", "get_remake_video", "upload_file"])
    assert.ok(allowed.includes(name), name);
});

test("G8: description triggers only when a finished video is wanted or changed, not for script writing, breakdown or account diagnosis, and stays within 500 characters", async () => {
  const description = /^description: "(.*)"$/m.exec(await doc("SKILL.md"))[1];
  assert.ok(description.length <= 500, String(description.length));
  assert.match(description, /only when the user wants the video itself made or changed/);
  assert.match(description, /not for writing or adapting a script, breaking down a video, or reviewing an account/);
});

test("plugin hand-off wording: quote before make_video, relay needs_reply verbatim, cancel says it is still stopping", async () => {
  const host = await doc("references/host-plugin.md");
  assert.match(host, /check_video_plan/);
  assert.match(host, /`quote_usd`/);
  assert.match(host, /Never work out a price\s+yourself/);
  assert.match(host, /`needs_reply`/);
  assert.match(host, /Never answer for them/);
  assert.match(host, /cancel was requested and is still stopping/);
});

test("no prices in the step references; a running step hitting quota_exceeded is not described as the quota being used up", async () => {
  for (const p of ["plan.md", "atoms.md", "project.md", "edits.md", "motion-graphics.md"]) {
    const text = await doc(`references/steps/${p}`);
    assert.doesNotMatch(text, /\$\d|\bfree\b(?! of content| too)|costs? (?:little|nothing|next to)|billed|quote_usd|est_usd/i, p);
  }
  assert.match(await doc("references/steps/project.md"), /still running:\s+not a limit/);
  assert.match(await doc("references/steps/edits.md"), /another remake or step is still running,\s+wait for it/);
});
