#!/usr/bin/env node
// The Web channel for plugin skills (kabo-agent-service DEPLOY.md, "Web channel for plugin skills"). Called at
//   release time by this repo's
// .github/workflows/web-publish.yml (moved here on 2026-11-06 from creator-skills scripts/skill-registry/,
//   logic unchanged).
//
// 2026-11-05 user ruling: desktop and kabo-alpha are frozen on the old version in the production channel, and
//   only Web runs the skills of
// kabo-mcp-plugin. So this script **never changes any channel index**: plugin packages are only written into
//   bundles/ (content-addressed,
// create-only), and then a Web-specific mutable overlay is written:
//   - channels/production/overlays/web-plugin/index.json  production Web (written automatically by CI on
//   plugin release)
//   - channels/production/overlays/web-plugin/test.json   the copy seen by test accounts registered on pre
//   - channels/production/overlays/web-plugin/test-accounts.json  the list of pre test accounts
// Before each overlay write, the new content is saved to history/<sha256>.json (create-only), and `restore`
//   goes back to any historical version by digest.
//
// Subcommands:
//   publish      --plugin-root <dir> --plugin-commit <sha> [--target index|test] [--skills a,b] [--hold a,b]
//                [--debut a,b]
//   restore      --sha <history digest> [--target index|test]
//   clear        [--target index|test]          write an empty overlay (Web goes back to reading only the live
//   index)
//   show         [--target index|test]
//   released                                   print the plugin commit the production overlay currently
//   corresponds to
//   test-accounts add <user_id> [--note text] | remove <user_id> | list
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

import { buildPluginBundle, bundleObjectName, stableJson } from './bundle.mjs';
import { GcsObjectStore, validateIndex } from './store.mjs';

export const OVERLAY_PREFIX = 'channels/production/overlays/web-plugin/';
export const TARGETS = { index: `${OVERLAY_PREFIX}index.json`, test: `${OVERLAY_PREFIX}test.json` };
export const TEST_ACCOUNTS_OBJECT = `${OVERLAY_PREFIX}test-accounts.json`;
// The highest version each skill has used on any overlay. If an overlay is cleared, a skill is held back and
//   then put back, or a release goes to the test target first,
// looking only at "channel + current overlay" would issue a version number that was already used (with
//   different content), and /health could not tell old from new.
export const VERSIONS_OBJECT = `${OVERLAY_PREFIX}versions.json`;
const historyObject = (sha) => `${OVERLAY_PREFIX}history/${sha}.json`;
// Remake on Web is handled by creator-remake-web (production channel); the plugin's remake-viral-video uses a
//   different tool surface and does not go to Web.
export const EXCLUDED = new Set(['remake-viral-video']);

const SEMVER = /^(\d+)\.(\d+)\.(\d+)$/;
const COMMIT = /^[0-9a-f]{40}$/;
const SKILL_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

function fail(message) {
  throw new Error(`plugin_web_failed: ${message}`);
}

function compare(left, right) {
  const a = SEMVER.exec(left).slice(1).map(Number);
  const b = SEMVER.exec(right).slice(1).map(Number);
  for (let i = 0; i < 3; i += 1) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

function target(name = 'index') {
  const object = TARGETS[name];
  if (!object) fail(`target must be one of ${Object.keys(TARGETS).join(', ')}`);
  return object;
}

async function readIndex(store, object, channel = 'production') {
  const raw = await store.read(object);
  if (!raw) return null;
  return { index: validateIndex(JSON.parse(raw.bytes), channel), generation: raw.generation };
}

/** Highest version of this skill in the readable channels (when the Internal publishing identity cannot read production, only the readable one counts). */
function liveVersion(id, indexes) {
  const versions = indexes
    .map((index) => index?.skills?.[id])
    .filter((entry) => entry && !entry.tombstone && SEMVER.test(entry.version ?? ''))
    .map((entry) => entry.version);
  return versions.length ? versions.sort(compare).at(-1) : null;
}

/**
 * Version: if the content equals the existing overlay entry, keep it as-is; if changed, take the larger of the "current channel version" and the "existing overlay version"
 * and bump the patch number by 1. So Web version numbers continue upward from production, and each plugin release bumps only the skills that really changed.
 */
export function versionFor(id, checksum, liveIndexes, current, declared = null, used = []) {
  const existing = current?.skills?.[id];
  if (existing && existing.content_checksum === checksum) return existing.version;
  // used: the versions of this skill recorded in other overlay targets and in versions.json; it only raises the
  //   floor and does not let a skill that is not in the channel debut.
  const live = [liveVersion(id, liveIndexes), existing?.version].filter(Boolean);
  if (!live.length) return null;
  const candidates = [...live, ...used.filter((version) => SEMVER.test(version ?? ''))];
  if (!candidates.length) return null;
  const latest = candidates.sort(compare).at(-1);
  // SKILL.md declares metadata.version (scripts read it, e.g. the content calendar): use it, but it must be
  //   higher than the versions live and on the overlay.
  if (declared) {
    if (!SEMVER.test(declared) || compare(declared, latest) <= 0)
      fail(`${id}: SKILL.md metadata.version ${declared} must be above the live version ${latest}; bump it in kabo-mcp-plugin`);
    return declared;
  }
  const [major, minor, patch] = SEMVER.exec(latest).slice(1).map(Number);
  return `${major}.${minor}.${patch + 1}`;
}

/**
 * Debut: the version a skill that is on no channel and not in the current overlay takes on its first Web publish.
 * Only called for skills in the debut list (PLUGIN_WEB_DEBUT). The version is the one SKILL.md declares in
 * metadata.version (required: there is no live version to continue from), and it must be above every version this
 * skill has already used on an overlay (versions.json / the other target), so a number is never reused.
 */
export function debutVersion(id, declared, used = []) {
  if (!declared) fail(`${id}: is in the debut list but SKILL.md has no metadata.version; declare one to debut it on Web`);
  if (!SEMVER.test(declared)) fail(`${id}: SKILL.md metadata.version ${JSON.stringify(declared)} must be x.y.z to debut it on Web`);
  const prior = used.filter((version) => SEMVER.test(version ?? '')).sort(compare).at(-1);
  if (prior && compare(declared, prior) <= 0)
    fail(`${id}: SKILL.md metadata.version ${declared} must be above ${prior}, already used on the Web overlay; bump it in kabo-mcp-plugin`);
  return declared;
}

// expectedGeneration: the generation of the overlay when publish read it (0 = did not exist then); if someone
//   else changed it in between, error out and rerun, rather than overwriting their newer write with old
//   entries.
async function writeOverlay(store, object, overlay, expectedGeneration) {
  const bytes = Buffer.from(stableJson(validateIndex(overlay, 'production')));
  const digest = sha256(bytes);
  const history = historyObject(digest);
  const saved = await store.read(history);
  if (!saved) {
    const created = await store.write(history, bytes, 0);
    if (!created.ok) fail(`history object appeared concurrently: ${history}`);
  } else if (!saved.bytes.equals(bytes)) {
    fail(`history collision: ${history}`);
  }
  const current = await store.read(object);
  if (expectedGeneration !== undefined && (current?.generation ?? 0) !== expectedGeneration) fail(`${object} changed while publishing; rerun`);
  if (current?.bytes.equals(bytes)) return { object, sha256: digest, generation: current.generation, unchanged: true };
  const written = await store.write(object, bytes, current?.generation ?? 0);
  if (!written.ok) fail(`${object} changed while writing; rerun`);
  const readback = await store.read(object);
  if (!readback?.bytes.equals(bytes)) fail(`readback mismatch for ${object}`);
  return { object, sha256: digest, generation: readback.generation, unchanged: false };
}

/** A skill at a plugin repository commit -> plugin package (bundles/, create-only) -> write the overlay. No channel index is touched. */
export const RELEASE_OBJECT = `${OVERLAY_PREFIX}release.json`;

/**
 * `bundleStore` writes bundles/ (in CI this is the Internal publishing identity, the only one that can write bundles/); `store` reads channels and writes
 * the overlay (in CI this is the Production publishing identity, which can write channels/production/ but not bundles/). Locally both are the same.
 */
export async function publish({ store, bundleStore = store, pluginRoot, pluginCommit, pluginTag = null, targetName = 'index', skills, hold = [], debut = [], now = new Date() }) {
  if (!COMMIT.test(pluginCommit ?? '')) fail('plugin commit must be 40 lowercase hex characters');
  const object = target(targetName);
  const readChannel = async (channel) => {
    try {
      return (await readIndex(store, `channels/${channel}/index.json`, channel))?.index ?? null;
    } catch (error) {
      if (/returned 403/.test(error.message)) return null;
      throw error;
    }
  };
  const live = [await readChannel('production'), await readChannel('internal')];
  if (!live.some(Boolean)) fail('cannot read any live channel index');
  const currentRead = await readIndex(store, object);
  const current = currentRead?.index ?? null;
  // The overlay of the other target (production / test): if the same content already has a version number there,
  //   use the same number and the same package.
  const others = await Promise.all(Object.entries(TARGETS).filter(([name]) => name !== targetName)
    .map(async ([, other]) => (await readIndex(store, other))?.index ?? null));
  const versionsRaw = await store.read(VERSIONS_OBJECT);
  const highwater = versionsRaw ? JSON.parse(versionsRaw.bytes) : { format_version: 1, skills: {} };
  const available = fs.readdirSync(path.join(pluginRoot, 'skills'))
    .filter((id) => SKILL_ID.test(id) && fs.existsSync(path.join(pluginRoot, 'skills', id, 'SKILL.md')));
  // hold: skills that do not go into the overlay this time (Web keeps using the original Registry version),
  //   passed in by the workflow's PLUGIN_WEB_HOLD.
  // debut: skills allowed to make their first Web appearance (PLUGIN_WEB_DEBUT). Hold wins over debut: a skill in
  //   both is filtered out by hold below and never reaches the debut check. Excluded skills cannot debut either.
  const invalidDebut = debut.filter((id) => !SKILL_ID.test(id));
  if (invalidDebut.length) fail(`debut list has invalid skill ids: ${invalidDebut.join(', ')}`);
  const wanted = (skills?.length ? skills : available.filter((id) => !EXCLUDED.has(id))).filter((id) => !hold.includes(id));
  const unknown = wanted.filter((id) => !available.includes(id));
  if (unknown.length) fail(`not in the plugin at ${pluginCommit}: ${unknown.join(', ')}`);
  // Package everything and compute versions first; if any one fails the checks, write nothing for the whole
  //   batch.
  const skipped = [];
  const debuted = [];
  const bundles = [];
  const kept = {};
  for (const id of wanted) {
    const directory = path.join(pluginRoot, 'skills', id);
    const probe = buildPluginBundle({ skillDirectory: directory, sourceCommit: pluginCommit, version: '0.0.1', probe: true });
    const existing = current?.skills?.[id];
    // New to Web (no channel has it and the current overlay does not either): only skills in the debut list may
    //   go on, including by reusing an identical package from the other target (e.g. debuted on test first).
    const isNew = !existing && !liveVersion(id, live);
    if (isNew && !debut.includes(id)) { skipped.push({ id, reason: 'not live on any channel' }); continue; }
    if (isNew) debuted.push(id);
    // Content unchanged: reuse the existing overlay entry as is (the package is already in the bucket, and
    //   source.commit records the commit that first released it).
    if (existing && existing.content_checksum === probe.content_checksum) { kept[id] = existing; continue; }
    const twin = others.map((index) => index?.skills?.[id]).find((entry) => entry?.content_checksum === probe.content_checksum);
    if (twin && (await bundleStore.read(twin.object))) { kept[id] = twin; continue; }
    const used = [...others.map((index) => index?.skills?.[id]?.version), highwater.skills?.[id]].filter(Boolean);
    // A skill that has never been in the channel (e.g. plugin-only ones) does not debut unless it is in the debut
    //   list (Web needs an entry point and chip policy for it first); then it takes its declared version.
    const version = isNew
      ? debutVersion(id, probe.declared_version, used)
      : versionFor(id, probe.content_checksum, live, current, probe.declared_version, used);
    bundles.push(buildPluginBundle({ skillDirectory: directory, sourceCommit: pluginCommit, version }));
  }
  if (!bundles.length && !Object.keys(kept).length) fail('nothing to publish');
  // The test target is shared by several people: entries this plugin commit cannot produce (skills that other
  //   branches released under an alias, etc.) are kept as is,
  // otherwise every release's incidental refresh of test would wipe out versions others are testing.
  if (targetName === 'test')
    for (const [id, entry] of Object.entries(current?.skills ?? {}))
      if (!available.includes(id) && !hold.includes(id) && !kept[id]) kept[id] = entry;
  for (const bundle of bundles) {
    const objectName = bundleObjectName(bundle);
    const bytes = Buffer.from(stableJson(bundle));
    await bundleStore.write(objectName, bytes, 0);
    const saved = await bundleStore.read(objectName);
    // An object with the same name is already in the bucket: the name already contains the id, the version and the
    //   content checksum, so if these three in the envelope match it is the same content
    // (another commit packaged the same files first, and only source.commit differs); reuse the one in the bucket.
    const same = saved && (saved.bytes.equals(bytes) || (() => {
      const existing = JSON.parse(saved.bytes);
      return existing.id === bundle.id && existing.version === bundle.version &&
        existing.content_checksum === bundle.content_checksum && existing.source?.repository === bundle.source.repository;
    })());
    if (!same) fail(`bundle object collision or readback mismatch: ${objectName}`);
  }
  const overlay = {
    format_version: 1,
    channel: 'production',
    updated_at: now.toISOString(),
    skills: Object.fromEntries([
      ...Object.entries(kept),
      ...bundles.map((bundle) => [bundle.id, {
        version: bundle.version,
        object: bundleObjectName(bundle),
        content_checksum: bundle.content_checksum,
      }]),
    ].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))),
  };
  const written = await writeOverlay(store, object, overlay, currentRead?.generation ?? 0);
  // Record the highest version each skill has used (only goes up, never down).
  const nextHighwater = { format_version: 1, skills: { ...(highwater.skills ?? {}) } };
  for (const [id, entry] of Object.entries(overlay.skills)) {
    const prior = nextHighwater.skills[id];
    if (!prior || compare(entry.version, prior) > 0) nextHighwater.skills[id] = entry.version;
  }
  if (stableJson(nextHighwater) !== stableJson(highwater)) {
    const saved = await store.write(VERSIONS_OBJECT, Buffer.from(stableJson(nextHighwater)), versionsRaw?.generation ?? 0);
    if (!saved.ok) fail(`${VERSIONS_OBJECT} changed while writing; rerun`);
  }
  if (targetName === 'index') {
    // Record which plugin release this production overlay comes from: the scheduled task uses it to decide whether
    //   a new release has not yet reached Web.
    const record = Buffer.from(stableJson({ plugin_commit: pluginCommit, plugin_tag: pluginTag, overlay_sha256: written.sha256, published_at: now.toISOString() }));
    const previous = await store.read(RELEASE_OBJECT);
    const saved = await store.write(RELEASE_OBJECT, record, previous?.generation ?? 0);
    if (!saved.ok) fail(`${RELEASE_OBJECT} changed while writing; rerun`);
  }
  return {
    plugin_commit: pluginCommit,
    channels_unchanged: true,
    overlay: written,
    previous: current ? Object.fromEntries(Object.entries(current.skills).map(([id, entry]) => [id, entry.version])) : {},
    skills: overlay.skills,
    skipped,
    debuted,
  };
}

export async function restore({ store, sha, targetName = 'index' }) {
  if (!/^[0-9a-f]{64}$/.test(sha ?? '')) fail('sha must be 64 lowercase hex characters');
  const saved = await store.read(historyObject(sha));
  if (!saved) fail(`no history object ${sha}`);
  if (sha256(saved.bytes) !== sha) fail('history object does not match its name');
  return writeOverlay(store, target(targetName), JSON.parse(saved.bytes));
}

export async function clear({ store, targetName = 'index', now = new Date() }) {
  return writeOverlay(store, target(targetName), { format_version: 1, channel: 'production', updated_at: now.toISOString(), skills: {} });
}

export async function testAccounts({ store, action, userId, note }) {
  const raw = await store.read(TEST_ACCOUNTS_OBJECT);
  const current = raw ? JSON.parse(raw.bytes) : { format_version: 1, accounts: [] };
  if (action === 'list') return current;
  if (!userId || userId.length > 128) fail('user id is required');
  const others = current.accounts.filter((account) => account.user_id !== userId);
  const next = {
    format_version: 1,
    accounts: action === 'add'
      ? [...others, { user_id: userId, ...(note ? { note: note.slice(0, 200) } : {}) }]
      : action === 'remove' ? others : fail(`unknown test-accounts action ${action}`),
  };
  if (next.accounts.length > 50) fail('at most 50 test accounts');
  const written = await store.write(TEST_ACCOUNTS_OBJECT, Buffer.from(stableJson(next)), raw?.generation ?? 0);
  if (!written.ok) fail('test account list changed while writing; rerun');
  return next;
}

function option(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  try {
    const store = new GcsObjectStore({ bucket: process.env.KABO_SKILL_REGISTRY_BUCKET || fail('KABO_SKILL_REGISTRY_BUCKET is required'), accessToken: process.env.GCS_ACCESS_TOKEN });
    const command = process.argv[2];
    const targetName = option('--target') ?? 'index';
    let result;
    if (command === 'publish') {
      const skills = (option('--skills') ?? '').split(',').map((item) => item.trim()).filter(Boolean);
      const bundleStore = process.env.GCS_BUNDLE_ACCESS_TOKEN
        ? new GcsObjectStore({ bucket: store.bucket, accessToken: process.env.GCS_BUNDLE_ACCESS_TOKEN })
        : store;
      const hold = (option('--hold') ?? '').split(',').map((item) => item.trim()).filter(Boolean);
      const debut = (option('--debut') ?? '').split(',').map((item) => item.trim()).filter(Boolean);
      result = await publish({ store, bundleStore, pluginRoot: option('--plugin-root'), pluginCommit: option('--plugin-commit'), pluginTag: option('--plugin-tag') ?? null, targetName, skills, hold, debut });
    } else if (command === 'released') {
      // For the scheduled task: print the plugin commit the production overlay currently corresponds to (empty
      //   string if none).
      const raw = await store.read(RELEASE_OBJECT);
      console.log(raw ? JSON.parse(raw.bytes).plugin_commit : '');
      process.exit(0);
    } else if (command === 'restore') {
      result = await restore({ store, sha: option('--sha'), targetName });
    } else if (command === 'clear') {
      result = await clear({ store, targetName });
    } else if (command === 'show') {
      result = (await readIndex(store, target(targetName))) ?? { absent: true };
    } else if (command === 'test-accounts') {
      result = await testAccounts({ store, action: process.argv[3], userId: process.argv[4], note: option('--note') });
    } else {
      fail('usage: plugin-web.mjs publish|restore|clear|show|test-accounts');
    }
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
