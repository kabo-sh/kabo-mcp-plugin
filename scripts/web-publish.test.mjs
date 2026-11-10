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

test('publish：只写 bundles 与 Web overlay，频道 index 一个字节不动；版本接着线上往上走；频道里没有的不首发', async () => {
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
  // 再发一次：没变的 skill 版本不动；变了的才 +1
  fs.writeFileSync(path.join(root, 'skills', 'beta-skill', 'SKILL.md'), '---\nname: beta-skill\ndescription: "A beta-skill fixture"\n---\n# b2\n');
  const second = await publish({ store, pluginRoot: root, pluginCommit: 'd'.repeat(40) });
  assert.equal(second.skills['alpha-skill'].version, '1.2.6');
  assert.equal(second.skills['beta-skill'].version, '0.4.12');
});

test('restore 回到任一历史版本；clear 写空 overlay；test 目标与生产目标互不影响', async () => {
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

test('版本号不复用：clear 或暂扣后再发接着用过的最高号往上走；test 目标已有同内容就沿用同号同包', async () => {
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
  // 频道里没有的 skill 仍不首发，即使 versions.json 里有记录
  assert.equal(versionFor('new-skill', 'sha256:z', [], null, null, ['9.9.9']), null);
});

test('测试账号名单：add / remove / list，重复 add 只留一条', async () => {
  const { store } = await liveStore();
  await testAccounts({ store, action: 'add', userId: 'u1', note: 'rose' });
  await testAccounts({ store, action: 'add', userId: 'u1', note: 'rose' });
  await testAccounts({ store, action: 'add', userId: 'u2' });
  await testAccounts({ store, action: 'remove', userId: 'u2' });
  assert.deepEqual(JSON.parse((await store.read(TEST_ACCOUNTS_OBJECT)).bytes), { format_version: 1, accounts: [{ user_id: 'u1', note: 'rose' }] });
});

test('versionFor：内容相同沿用，变了取线上与 overlay 较大者 +1，两边都没有为 null', () => {
  const live = [{ skills: { a: { version: '1.0.0' } } }];
  assert.equal(versionFor('a', 'sha256:x', live, { skills: { a: { version: '1.0.4', content_checksum: 'sha256:x' } } }), '1.0.4');
  assert.equal(versionFor('a', 'sha256:y', live, { skills: { a: { version: '1.0.4', content_checksum: 'sha256:x' } } }), '1.0.5');
  assert.equal(versionFor('a', 'sha256:y', live, null), '1.0.1');
  assert.equal(versionFor('b', 'sha256:y', live, null), null);
});

test('publish --hold：被扣下的 skill 不进 overlay（Web 用 Registry 原版本），其余照发', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'alpha-skill': '# a1', 'beta-skill': '# b1' });
  const result = await publish({ store, pluginRoot: root, pluginCommit: COMMIT, hold: ['beta-skill'] });
  assert.deepEqual(Object.keys(result.skills), ['alpha-skill']);
  const overlay = JSON.parse((await store.read(TARGETS.index)).bytes);
  assert.deepEqual(Object.keys(overlay.skills), ['alpha-skill']);
});

test('复刻合一：test 目标以 Web 的 skill id 登记插件的 remake-viral-video，生产目标仍排除', async () => {
  const { store } = await liveStore();
  const prod = JSON.parse((await store.read('channels/production/index.json')).bytes);
  prod.skills['creator-remake-web'] = { version: '0.1.46', object: `bundles/creator-remake-web/0.1.46/${'b'.repeat(64)}.json`, content_checksum: `sha256:${'b'.repeat(64)}` };
  await store.write('channels/production/index.json', Buffer.from(stableJson(prod)), (await store.read('channels/production/index.json')).generation);
  const root = pluginRepo({ 'alpha-skill': '# a1', 'remake-viral-video': '# r' });
  const index = await publish({ store, pluginRoot: root, pluginCommit: COMMIT });
  assert.equal('creator-remake-web' in index.skills, false);
  assert.equal('remake-viral-video' in index.skills, false);
  const tested = await publish({ store, pluginRoot: root, pluginCommit: COMMIT, targetName: 'test' });
  assert.equal(tested.skills['creator-remake-web'].version, '0.1.47');
  assert.equal('remake-viral-video' in tested.skills, false);
  const bundle = JSON.parse((await store.read(tested.skills['creator-remake-web'].object)).bytes);
  assert.equal(bundle.id, 'creator-remake-web');
  const skill = Buffer.from(bundle.files.find((f) => f.path === 'SKILL.md').content_base64, 'base64').toString('utf8');
  assert.match(skill, /^name: creator-remake-web$/m);
  assert.match(skill, /# r/);
});

test('publish --merge：只发点名的 skill，overlay 里别人的条目原样保留', async () => {
  const { store } = await liveStore();
  const root = pluginRepo({ 'alpha-skill': '# a1', 'beta-skill': '# b1' });
  await publish({ store, pluginRoot: root, pluginCommit: COMMIT, targetName: 'test' });
  const before = JSON.parse((await store.read(TARGETS.test)).bytes).skills['beta-skill'];
  fs.writeFileSync(path.join(root, 'skills', 'alpha-skill', 'SKILL.md'), '---\nname: alpha-skill\ndescription: "x"\n---\n# a2\n');
  fs.writeFileSync(path.join(root, 'skills', 'beta-skill', 'SKILL.md'), '---\nname: beta-skill\ndescription: "x"\n---\n# b2\n');
  const merged = await publish({ store, pluginRoot: root, pluginCommit: 'f'.repeat(40), targetName: 'test', skills: ['alpha-skill'], merge: true });
  assert.deepEqual(merged.skills['beta-skill'], before);
  assert.equal(merged.skills['alpha-skill'].version, '1.2.7');
});
