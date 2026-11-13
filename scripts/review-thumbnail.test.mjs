import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import test from 'node:test';

test('thumbnail input, binary verdict, evidence, priorities and unchanged delivery contract', () => {
  execFileSync('python3', ['-B', new URL('./review-thumbnail-regression.py', import.meta.url).pathname], { encoding: 'utf8', timeout: 30000 });
});

test('the native thumbnail skill produces a complete, readable Web bundle', async () => {
  const { buildPluginBundle, validateBundle } = await import('./web-publish/bundle.mjs');
  const bundle = buildPluginBundle({ skillDirectory: new URL('../skills/review-thumbnail', import.meta.url).pathname, sourceCommit: 'a'.repeat(40), version: '0.1.3' });
  assert.equal(validateBundle(bundle).id, 'review-thumbnail');
  for (const path of ['SKILL.md','scripts/review_thumbnail.py','references/rubric.json','references/labels-zh.json','references/contract.md','references/rubric.md'])
    assert.ok(bundle.files.some(file=>file.path===path),path);
});
