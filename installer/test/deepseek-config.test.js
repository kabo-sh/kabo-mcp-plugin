"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { parse } = require("yaml");
const { updateDeepSeekPatch } = require("../bin/deepseek-config.js");

const wanted = { id: "mcp-kabo", name: "@deepseek-ai/dsh-mcp-client", config: { serverName: "kabo", transport: "stdio" } };
const entry = JSON.stringify([{ insert: [wanted] }]);
const plugins = (source) => parse(source).flatMap((item) => item.insert || []);

for (const id of ["id: mcp-kabo", "id: mcp-kabo # personal connection", '"id": mcp-kabo', "'id': 'mcp-kabo'"]) {
  test(`updates ${id} once and preserves the other plugin in the group`, () => {
    const original = `# my connections\n- insert:\n    - ${id}\n      name: old-kabo\n      disabled: false\n    - "id": other-plugin\n      name: other-plugin\n      config: {enabled: true}\n`;
    const { next, connection } = updateDeepSeekPatch(original, entry);
    assert.equal(connection, "replaced");
    assert.deepEqual(plugins(next), [{ ...wanted, disabled: false }, { id: "other-plugin", name: "other-plugin", config: { enabled: true } }]);
    assert.match(next, /# my connections/);
    assert.deepEqual(updateDeepSeekPatch(next, entry), { next, connection: "unchanged" });
  });
}

test("adds to empty or flow-style lists and preserves unrelated aliases", () => {
  for (const original of [undefined, "", "# my connections\n", "[]\n", "---\n[]\n"]) {
    assert.deepEqual(plugins(updateDeepSeekPatch(original, entry).next), [wanted]);
  }
  const original = '- insert: [{id: other, config: &shared {enabled: true}}]\n- insert: [{id: another, config: *shared}]\n';
  const updated = updateDeepSeekPatch(original, entry).next;
  assert.deepEqual(plugins(updated).slice(0, 2), plugins(original));
  assert.deepEqual(plugins(updated).at(-1), wanted);
  assert.match(updated, /&shared/);
  assert.match(updated, /\*shared/);
});

const unsafe = {
  anchor: '- insert:\n    - id: mcp-kabo\n      config: &shared {serverName: kabo}\n- insert:\n    - id: other\n      config: *shared\n',
  alias: '- insert:\n    - id: other\n      config: &shared {serverName: other}\n    - id: mcp-kabo\n      config: *shared\n',
  groupAnchor: '- insert: &shared [{id: mcp-kabo, name: old}]\n- insert: *shared\n',
  duplicate: '- insert: [{id: mcp-kabo}, {"id": mcp-kabo}]\n',
  invalid: '- insert: [\n',
  badAlias: '- insert: [{id: other, config: *missing}]\n',
  wrongRoot: 'insert: []\n',
  duplicateKey: '- insert: [{id: mcp-kabo, id: other}]\n',
};

for (const [name, original] of Object.entries(unsafe)) {
  test(`refuses ${name} before the CLI writes the user's patch file`, (t) => {
    assert.throws(() => updateDeepSeekPatch(original, entry));
    const { patch, run } = fixtureFor(t, original);
    const result = run();
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stdout, /Not touching it/);
    assert.equal(fs.readFileSync(patch, "utf8"), original);
    assert.deepEqual(fs.readdirSync(path.dirname(patch)), ["cordis.patch.yml"]);
  });
}

function fixtureFor(t, original) {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "kabo-installer-config-"));
  t.after(() => fs.rmSync(fixture, { recursive: true, force: true }));
  const patch = path.join(fixture, ".dsh/profiles/desktop/cordis.patch.yml");
  fs.mkdirSync(path.dirname(patch), { recursive: true });
  fs.writeFileSync(patch, original);
  fs.mkdirSync(path.join(fixture, "kabo-mcp-plugin/.git"), { recursive: true });
  const bin = path.join(fixture, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, "npx"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  const preload = path.join(fixture, "isolate.cjs");
  fs.writeFileSync(preload, `require('node:os').homedir = () => process.env.KABO_INSTALLER_TEST_ROOT;\nrequire('node:child_process').spawnSync = () => ({status: 0, stdout: ''});\n`);
  const run = () => spawnSync(process.execPath, ["--require", preload, path.resolve(__dirname, "../bin/kabo.js"), "install", "--host", "deepseek"], {
    env: { ...process.env, KABO_INSTALLER_TEST_ROOT: fixture, PATH: `${bin}${path.delimiter}${process.env.PATH || ""}` },
    encoding: "utf8",
  });
  return { patch, fixture, run };
}

test("the real CLI preserves sibling entries, backs up once and is idempotent", (t) => {
  const original = '- insert:\n    - id: mcp-kabo # keep one\n      name: old-kabo\n    - "id": other-plugin\n      config: {enabled: true}\n';
  const { patch, fixture, run } = fixtureFor(t, original);
  const skill = path.join(fixture, "kabo-mcp-plugin/skills/test-skill");
  fs.mkdirSync(skill, { recursive: true });
  fs.writeFileSync(path.join(skill, "SKILL.md"), "---\nname: test-skill\ndescription: Fixture\n---\n");
  const first = run();
  assert.equal(first.status, 0, first.stdout + first.stderr);
  const installed = fs.readFileSync(patch, "utf8");
  const entries = plugins(installed);
  assert.equal(entries.filter((item) => item.id === "mcp-kabo").length, 1);
  assert.deepEqual(entries[1], { id: "other-plugin", config: { enabled: true } });
  assert.equal(entries[0].config.args.at(-1), JSON.stringify({ scope: "openid profile email offline_access data video workspace:read workspace:write" }));
  const beforeRetry = fs.readdirSync(path.dirname(patch));
  const backups = beforeRetry.filter((name) => name.includes(".kabo-backup-"));
  assert.equal(backups.length, 1);
  assert.equal(fs.readFileSync(path.join(path.dirname(patch), backups[0]), "utf8"), original);
  const second = run();
  assert.equal(second.status, 0, second.stdout + second.stderr);
  assert.equal(fs.readFileSync(patch, "utf8"), installed);
  assert.deepEqual(fs.readdirSync(path.dirname(patch)), beforeRetry);
  assert.equal(fs.readFileSync(path.join(path.dirname(patch), backups[0]), "utf8"), original);
});
