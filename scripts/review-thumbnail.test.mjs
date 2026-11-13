import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { validateStaticSkills } from './static-skills.mjs';

test('thumbnail input, binary verdict, evidence, priorities and unchanged delivery contract', () => {
  execFileSync('python3', ['-B', new URL('./review-thumbnail-regression.py', import.meta.url).pathname], { encoding: 'utf8', timeout: 30000 });
});

test('native skill provenance is explicit; imported provenance cannot be fabricated', async () => {
  const lock=JSON.parse(await readFile(new URL('../skills.lock.json',import.meta.url),'utf8'));
  const make=()=>new Map([['skills.lock.json',{bytes:Buffer.from(JSON.stringify(lock))}], ...lock.skills.map(s=>[`skills/${s.id}/SKILL.md`,{bytes:Buffer.from('fixture')}])]);
  assert.equal(validateStaticSkills(make()).skills.at(-1).origin,'native');
  lock.skills.at(-1).derivedFromVersion='1.0.0';
  assert.throws(()=>validateStaticSkills(make()));
  delete lock.skills.at(-1).derivedFromVersion;
  lock.skills.at(-1).sourcePath='creator-skills/runtime/review-thumbnail';
  assert.throws(()=>validateStaticSkills(make()));
});

test('the native thumbnail skill produces a complete, readable Web bundle', async () => {
  const { buildPluginBundle, validateBundle } = await import('./web-publish/bundle.mjs');
  const bundle = buildPluginBundle({ skillDirectory: new URL('../skills/review-thumbnail', import.meta.url).pathname, sourceCommit: 'a'.repeat(40), version: '0.1.3' });
  assert.equal(validateBundle(bundle).id, 'review-thumbnail');
  for (const path of ['SKILL.md','scripts/review_thumbnail.py','references/rubric.json','references/labels-zh.json','references/contract.md','references/rubric.md'])
    assert.ok(bundle.files.some(file=>file.path===path),path);
});
