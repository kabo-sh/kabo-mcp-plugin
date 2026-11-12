import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { stableJson } from './web-publish/bundle.mjs';
import { MemoryObjectStore } from './web-publish/store.mjs';
import { TARGETS, TEST_ACCOUNTS_OBJECT, VERSIONS_OBJECT, clear, publish, restore, testAccounts, versionFor } from './web-publish/plugin-web.mjs';

const COMMIT = 'c'.repeat(40);

function pluginRepo(skills) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'plugin-web-'));
  for (const [id, body] of Object.entries(skills)) {
    const dir = path.join(root, 'skills', id);
    fs.mkdirSync(path.join(dir, 'scripts'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'SKILL.md'), `---\nname: ${id}\ndescription: "A ${id} fixture"\n---\n${body}\n`);
    fs.writeFileSync(path.join(dir, 'scripts', 'static_host.py'), 'print("ok")\n');
  }
  return root;
}

async function liveStore() {
  const store = new MemoryObjectStore();
  const index = (channel, skills) => ({ format_version: 1, channel, updated_at: '2026-11-05T00:00:00.000Z', skills });
  const entry = (id, version) => ({ version, object: `bundles/${id}/${version}/${'a'.repeat(64)}.json`, content_checksum: `sha256:${'a'.repeat(64)}` });
  const production = index('production', { 'alpha-skill': entry('alpha-skill', '1.2.3'), 'beta-skill': entry('beta-skill', '0.4.10') });
  const internal = index('internal', { 'alpha-skill': entry('alpha-skill', '1.2.5') });
  await store.write('channels/production/index.json', Buffer.from(stableJson(production)), 0);
  await store.write('channels/internal/index.json', Buffer.from(stableJson(internal)), 0);
  return { store, production, internal };
}

test('publish: writes only bundles and the Web overlay, leaves the channel index byte-for-byte untouched; versions continue upward from production; skills absent from the channel are not first-published', async () => {
  const { store } = await liveStore();
  const before = (await store.read('channels/production/index.json')).bytes;
  const root = pluginRepo({ 'alpha-skill': '# a1', 'beta-skill': '# b1', 'new-skill': '# n', 'remake-viral-video': '# r' });
  const result = await publish({ store, pluginRoot: root, pluginCommit: COMMIT, now: new Date('2026-11-05T01:00:00Z') });
  assert.deepEqual(Object.fromEntries(Object.entries(result.skills).map(([id, e]) => [id, e.version])), { 'alpha-skill': '1.2.6', 'beta-skill': '0.4.11' });
  assert.deepEqual(result.skipped, [{ id: 'new-skill', reason: 'not live on any channel' }]);
  assert.ok((await store.read('channels/production/index.json')).bytes.equals(before));
  const overlay = JSON.parse((await store.read(TARGETS.index)).bytes);
  for (const entry of Object.values(overlay.skills)) {
    const bundle = JSON.parse((await store.read(entry.object)).bytes);
    assert.equal(bundle.source.repository, 'kabo-sh/kabo-mcp-plugin');
    assert.equal(bundle.manifest, null);
  }
  // Publish again: unchanged skill versions stay put; only changed ones get +1
  fs.writeFileSync(path.join(root, 'skills', 'beta-skill', 'SKILL.md'), '---\nname: beta-skill\ndescription: "A beta-skill fixture"\n---\n# b2\n');
  const second = await publish({ store, pluginRoot: root, pluginCommit: 'd'.repeat(40) });
  assert.equal(second.skills['alpha-skill'].version, '1.2.6');
  assert.equal(second.skills['beta-skill'].version, '0.4.12');
});

test('restore returns to any historical version; clear writes an empty overlay; the test target and the production target do not affect each other', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'alpha-skill': '# a1' });
  const first = await publish({ store, pluginRoot: root, pluginCommit: COMMIT });
  fs.writeFileSync(path.join(root, 'skills', 'alpha-skill', 'SKILL.md'), '---\nname: alpha-skill\ndescription: "x"\n---\n# a2\n');
  await publish({ store, pluginRoot: root, pluginCommit: 'e'.repeat(40) });
  await restore({ store, sha: first.overlay.sha256 });
  const restored = (await store.read(TARGETS.index)).bytes;
  assert.equal(crypto.createHash('sha256').update(restored).digest('hex'), first.overlay.sha256);
  await publish({ store, pluginRoot: root, pluginCommit: 'e'.repeat(40), targetName: 'test' });
  await clear({ store });
  assert.deepEqual(JSON.parse((await store.read(TARGETS.index)).bytes).skills, {});
  assert.equal(Object.keys(JSON.parse((await store.read(TARGETS.test)).bytes).skills).length, 1);
});

test('version numbers are never reused: after clear or hold, the next publish continues above the highest used number; the test target reuses the same number and package when it already has identical content', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'beta-skill': '# b1' });
  const first = await publish({ store, pluginRoot: root, pluginCommit: COMMIT });
  assert.equal(first.skills['beta-skill'].version, '0.4.11');
  await clear({ store });
  fs.writeFileSync(path.join(root, 'skills', 'beta-skill', 'SKILL.md'), '---\nname: beta-skill\ndescription: "x"\n---\n# b2\n');
  const test1 = await publish({ store, pluginRoot: root, pluginCommit: 'd'.repeat(40), targetName: 'test' });
  assert.equal(test1.skills['beta-skill'].version, '0.4.12');
  const prod = await publish({ store, pluginRoot: root, pluginCommit: 'e'.repeat(40) });
  assert.deepEqual(prod.skills['beta-skill'], test1.skills['beta-skill']);
  assert.equal(JSON.parse((await store.read(VERSIONS_OBJECT)).bytes).skills['beta-skill'], '0.4.12');
  // Skills not in the channel are still not published for the first time, even if versions.json has a record
  assert.equal(versionFor('new-skill', 'sha256:z', [], null, null, ['9.9.9']), null);
});

test('test account list: add / remove / list; a duplicate add keeps only one entry', async () => {
  const { store } = await liveStore();
  await testAccounts({ store, action: 'add', userId: 'u1', note: 'rose' });
  await testAccounts({ store, action: 'add', userId: 'u1', note: 'rose' });
  await testAccounts({ store, action: 'add', userId: 'u2' });
  await testAccounts({ store, action: 'remove', userId: 'u2' });
  assert.deepEqual(JSON.parse((await store.read(TEST_ACCOUNTS_OBJECT)).bytes), { format_version: 1, accounts: [{ user_id: 'u1', note: 'rose' }] });
});

test('versionFor: identical content keeps the version; changed content takes the larger of production and overlay, plus 1; null when neither has it', () => {
  const live = [{ skills: { a: { version: '1.0.0' } } }];
  assert.equal(versionFor('a', 'sha256:x', live, { skills: { a: { version: '1.0.4', content_checksum: 'sha256:x' } } }), '1.0.4');
  assert.equal(versionFor('a', 'sha256:y', live, { skills: { a: { version: '1.0.4', content_checksum: 'sha256:x' } } }), '1.0.5');
  assert.equal(versionFor('a', 'sha256:y', live, null), '1.0.1');
  assert.equal(versionFor('b', 'sha256:y', live, null), null);
});

test('publish --hold: a held skill stays out of the overlay (Web uses the original Registry version) and the rest publish as usual', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'alpha-skill': '# a1', 'beta-skill': '# b1' });
  const result = await publish({ store, pluginRoot: root, pluginCommit: COMMIT, hold: ['beta-skill'] });
  assert.deepEqual(Object.keys(result.skills), ['alpha-skill']);
  const overlay = JSON.parse((await store.read(TARGETS.index)).bytes);
  assert.deepEqual(Object.keys(overlay.skills), ['alpha-skill']);
});

test('test target: entries this plugin cannot produce (published via an alias) are preserved as-is; the production target does not preserve them', async () => {
  const { store } = await liveStore();
  const foreign = { version: '0.1.52', object: `bundles/creator-remake-web/0.1.52/${'b'.repeat(64)}.json`, content_checksum: `sha256:${'b'.repeat(64)}` };
  const seed = { format_version: 1, channel: 'production', updated_at: '2026-11-05T00:00:00.000Z', skills: { 'creator-remake-web': foreign } };
  await store.write(TARGETS.test, Buffer.from(stableJson(seed)), 0);
  const root = pluginRepo({ 'alpha-skill': '# a1' });
  const result = await publish({ store, pluginRoot: root, pluginCommit: COMMIT, targetName: 'test' });
  assert.deepEqual(result.skills['creator-remake-web'], foreign);
  assert.ok(result.skills['alpha-skill']);
  await store.write(TARGETS.index, Buffer.from(stableJson(seed)), (await store.read(TARGETS.index))?.generation ?? 0);
  const prod = await publish({ store, pluginRoot: root, pluginCommit: 'd'.repeat(40) });
  assert.equal(prod.skills['creator-remake-web'], undefined);
});

test('publish: if someone changed the overlay after it was read, error out and rerun instead of overwriting with stale entries', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'alpha-skill': '# a1' });
  const seed = { format_version: 1, channel: 'production', updated_at: '2026-11-05T00:00:00.000Z', skills: {} };
  await store.write(TARGETS.test, Buffer.from(stableJson(seed)), 0);
  const bundleStore = {
    read: (...a) => store.read(...a),
    write: async (...a) => {
      const now = await store.read(TARGETS.test);
      await store.write(TARGETS.test, Buffer.from(stableJson({ ...seed, updated_at: '2026-11-05T02:00:00.000Z' })), now.generation);
      return store.write(...a);
    },
  };
  await assert.rejects(publish({ store, bundleStore, pluginRoot: root, pluginCommit: COMMIT, targetName: 'test' }), /changed while publishing/);
});
